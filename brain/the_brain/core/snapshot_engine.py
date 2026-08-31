"""
Phase M — State Snapshots.

Periodic background job that captures Brain's current cognitive state
(bridges + modulation + consciousness + radial-meta) into the
`brain-state` Qdrant collection as `snapshot` nodes.

Why: enables temporal queries ("how did Brain feel yesterday at 14:00",
"compare current bridges to last hour") and feeds back into routing once
the consolidator (Phase L) starts clustering similar states.

TTL is enforced lazily on read (not deleted) — old snapshots stay
available for retrospection but are filtered by `created_at` cutoff in
queries.

Environment:
  SNAPSHOT_TICK_INTERVAL_S    default 300  (5 min)
  SNAPSHOT_ENABLED            default 1
  SNAPSHOT_TTL_HOURS          default 168 (7 days, soft TTL)
  SNAPSHOT_MAX_TOTAL          default 5000 (hard cap, drops oldest)
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


TICK_INTERVAL_S = float(os.environ.get("SNAPSHOT_TICK_INTERVAL_S", "300"))
ENABLED = os.environ.get("SNAPSHOT_ENABLED", "1").lower() in ("1", "true", "yes")
TTL_HOURS = float(os.environ.get("SNAPSHOT_TTL_HOURS", "168"))
MAX_TOTAL = int(os.environ.get("SNAPSHOT_MAX_TOTAL", "5000"))


class SnapshotEngine:
    """Periodic Brain self-state snapshotter into brain-state collection."""

    def __init__(
        self,
        kg,
        bridges_provider: Optional[Callable[[], Dict[str, Any]]] = None,
        state_provider: Optional[Callable[[], Dict[str, Any]]] = None,
        modulation_provider: Optional[Callable[[], Dict[str, Any]]] = None,
    ) -> None:
        """
        Args:
            kg: QdrantKG instance (must have ensure_collections ran)
            bridges_provider: () -> dict of bridge states
            state_provider: () -> dict of brain-state (radial meta)
            modulation_provider: () -> dict of composite modulation
        """
        self.kg = kg
        self.get_bridges = bridges_provider or (lambda: {})
        self.get_state = state_provider or (lambda: {})
        self.get_modulation = modulation_provider or (lambda: {})

        self._stop = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self.stats: Dict[str, Any] = {
            "ticks": 0,
            "snapshots_written": 0,
            "errors": 0,
            "last_error": None,
            "last_tick_ts": None,
            "last_snapshot_id": None,
        }

    # ── Lifecycle ────────────────────────────────────────────────────

    def start(self) -> None:
        if not ENABLED:
            logger.info("[Snapshot] disabled via SNAPSHOT_ENABLED=0")
            return
        if self._worker and self._worker.is_alive():
            return
        self._stop.clear()
        self._worker = threading.Thread(
            target=self._loop, daemon=True, name="SnapshotEngine",
        )
        self._worker.start()
        logger.info(
            f"[Snapshot] started (every {TICK_INTERVAL_S}s -> brain-state)"
        )

    def stop(self) -> None:
        self._stop.set()
        if self._worker:
            self._worker.join(timeout=5)

    def _loop(self) -> None:
        # Wait briefly for Brain to settle so first snapshot is meaningful
        self._stop.wait(30.0)
        while not self._stop.is_set():
            try:
                self.snapshot_now()
                self.stats["ticks"] += 1
                self.stats["last_tick_ts"] = time.time()
            except Exception as e:
                self.stats["errors"] += 1
                self.stats["last_error"] = str(e)
                logger.warning(f"[Snapshot] tick failed: {e}")
            self._stop.wait(TICK_INTERVAL_S)

    # ── Core ─────────────────────────────────────────────────────────

    def snapshot_now(self) -> Optional[str]:
        """Capture one snapshot point. Returns external snapshot_id."""
        from core.qdrant_kg import COLLECTIONS, NT_SNAPSHOT, _point_id, _empty_linked

        ts = time.time()
        sid = f"snap-{int(ts * 1000)}-{uuid.uuid4().hex[:6]}"

        # Pull live state with defensive fallbacks — providers may raise
        try:
            bridges = self.get_bridges() or {}
        except Exception as e:
            bridges = {"_error": str(e)}
        try:
            state = self.get_state() or {}
        except Exception as e:
            state = {"_error": str(e)}
        try:
            modulation = self.get_modulation() or {}
        except Exception as e:
            modulation = {"_error": str(e)}

        # Build a compact text view for the embedding so similar states
        # cluster together. We hash bridges + key modulation values.
        text = self._summarize(bridges, modulation, state)

        payload = {
            "snapshot_id": sid,
            "bridges": _slim(bridges, max_depth=3, max_str=200),
            "modulation": _slim(modulation, max_depth=3, max_str=200),
            "state_summary": _slim(
                self._extract_state_summary(state),
                max_depth=2, max_str=200,
            ),
            "ts": int(ts),
        }

        try:
            pid = self.kg._upsert_point(sid, NT_SNAPSHOT, text, payload)
            if pid:
                self.stats["snapshots_written"] += 1
                self.stats["last_snapshot_id"] = sid
                # Hard-cap: drop oldest if over MAX_TOTAL
                self._enforce_cap()
                return sid
        except Exception as e:
            self.stats["errors"] += 1
            self.stats["last_error"] = f"upsert: {e}"
            logger.warning(f"[Snapshot] upsert failed: {e}")
        return None

    # ── Helpers ─────────────────────────────────────────────────────

    def _summarize(
        self, bridges: Dict[str, Any], modulation: Dict[str, Any],
        state: Dict[str, Any],
    ) -> str:
        """Build a short textual summary for the semantic embedding so
        similar states cluster in vector space."""
        parts = []

        # Bridges: name=status pairs
        b = bridges.get("bridges") if isinstance(bridges.get("bridges"), dict) else bridges
        if isinstance(b, dict):
            sigs = []
            for name, v in list(b.items())[:12]:
                if isinstance(v, dict):
                    s = v.get("status") or v.get("level") or v.get("activation")
                    sigs.append(f"{name}={s}")
                else:
                    sigs.append(f"{name}={v}")
            if sigs:
                parts.append("bridges: " + ", ".join(sigs))

        # Modulation: top-level numeric values
        if isinstance(modulation, dict):
            sigs = []
            for k, v in list(modulation.items())[:8]:
                if isinstance(v, (int, float)):
                    sigs.append(f"{k}={v:.2f}")
            if sigs:
                parts.append("mod: " + ", ".join(sigs))

        # Consciousness level if present
        cl = (modulation.get("consciousness_level")
              if isinstance(modulation, dict) else None)
        if cl is not None:
            parts.append(f"consciousness={cl}")

        return " | ".join(parts) if parts else "snapshot"

    def _extract_state_summary(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Pull just the small/numeric/string scalars out of state, drop
        the giant vector arrays (vision, audio, etc.) so the snapshot
        payload stays small."""
        if not isinstance(state, dict):
            return {}
        s = state.get("state") if isinstance(state.get("state"), dict) else state
        out: Dict[str, Any] = {}
        for k, v in (s or {}).items():
            if isinstance(v, (int, float, bool, str)):
                out[k] = v
            elif isinstance(v, dict):
                # one level of nesting only, scalars only
                inner = {kk: vv for kk, vv in v.items()
                         if isinstance(vv, (int, float, bool, str))}
                if inner:
                    out[k] = inner
        return out

    def _enforce_cap(self) -> None:
        """If total snapshots exceed MAX_TOTAL, drop the oldest 10%."""
        try:
            from core.qdrant_kg import COLLECTIONS
            from qdrant_client.http import models as qm
            coll = COLLECTIONS["state"]
            count = self.kg.client.count(collection_name=coll, exact=False).count
            if count <= MAX_TOTAL:
                return
            cutoff_ts = int(time.time() - TTL_HOURS * 3600)
            self.kg.client.delete(
                collection_name=coll,
                points_selector=qm.FilterSelector(
                    filter=qm.Filter(must=[qm.FieldCondition(
                        key="created_at",
                        range=qm.Range(lt=cutoff_ts),
                    )])
                ),
            )
            logger.info(f"[Snapshot] enforced cap, deleted snapshots older than {TTL_HOURS}h")
        except Exception as e:
            logger.debug(f"[Snapshot] cap enforce failed: {e}")


def _slim(obj: Any, max_depth: int = 3, max_str: int = 200, _d: int = 0) -> Any:
    """Recursively slim a payload so we don't store huge vectors / nested junk."""
    if _d >= max_depth:
        return repr(obj)[:max_str] if not isinstance(obj, (int, float, bool, str, type(None))) else obj
    if isinstance(obj, dict):
        return {str(k): _slim(v, max_depth, max_str, _d + 1) for k, v in list(obj.items())[:50]}
    if isinstance(obj, list):
        # Drop large numeric arrays (vectors). Keep small lists.
        if len(obj) > 16 and all(isinstance(x, (int, float)) for x in obj[:8]):
            return f"<vector len={len(obj)}>"
        return [_slim(v, max_depth, max_str, _d + 1) for v in obj[:32]]
    if isinstance(obj, str):
        return obj[:max_str]
    return obj
