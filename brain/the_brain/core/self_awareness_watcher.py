"""
Phase S.4 — Self-Awareness Watcher.

Background loop that detects code changes to seeded sources and re-seeds
only the affected concept-nodes in brain-semantic (preserves linked.*
edges). Tick interval default 1h.

Reuses content-extraction logic from scripts/seed_self_awareness.py to
avoid duplication. The script is imported as a module.

Stats are exposed via /api/self_awareness/manifest_stats and
/api/self_awareness/reseed (manual trigger).

Pattern lifted from DiscourseAggregator.start/stop/tick_once.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Discover seed_self_awareness module under scripts/
_THIS = Path(__file__).resolve()
_BRAIN_DIR = _THIS.parent.parent
_SCRIPTS_DIR = _BRAIN_DIR / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

# We import lazily inside the methods to avoid import errors at module-load
# time if the script's path setup hasn't happened yet.

# Config
ENABLED = os.environ.get("SELF_AWARENESS_ENABLED", "1") == "1"
TICK_INTERVAL_S = float(os.environ.get("SELF_AWARENESS_INTERVAL_S", "3600"))
INITIAL_DELAY_S = float(os.environ.get("SELF_AWARENESS_INITIAL_DELAY", "120"))


class SelfAwarenessWatcher:
    """Periodic file-hash-based re-seeder of self-awareness substrate."""

    def __init__(self, kg) -> None:
        """
        Args:
            kg: QdrantKG instance — uses kg._upsert_point and kg.client for
                deletes.
        """
        self.kg = kg
        self._stop = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self.stats: Dict[str, Any] = {
            "ticks": 0,
            "checks": 0,
            "unchanged": 0,
            "updated": 0,
            "added": 0,
            "removed": 0,
            "errors": 0,
            "last_error": None,
            "last_tick_ts": None,
        }

    # ── Lifecycle ────────────────────────────────────────────────────

    def start(self) -> None:
        if not ENABLED:
            logger.info("[self-aware] disabled")
            return
        if self._worker and self._worker.is_alive():
            return
        self._stop.clear()
        self._worker = threading.Thread(
            target=self._loop, daemon=True, name="SelfAwarenessWatcher",
        )
        self._worker.start()
        logger.info(
            f"[self-aware] watcher started (every {TICK_INTERVAL_S}s)"
        )

    def stop(self) -> None:
        self._stop.set()
        if self._worker:
            self._worker.join(timeout=5)

    def _loop(self) -> None:
        self._stop.wait(INITIAL_DELAY_S)
        while not self._stop.is_set():
            try:
                self.tick_once()
                self.stats["ticks"] += 1
                self.stats["last_tick_ts"] = time.time()
            except Exception as e:
                self.stats["errors"] += 1
                self.stats["last_error"] = f"tick: {type(e).__name__}: {e}"
                logger.warning(f"[self-aware] tick failed: {e}")
            self._stop.wait(TICK_INTERVAL_S)

    # ── Tick logic ───────────────────────────────────────────────────

    def tick_once(self) -> Dict[str, Any]:
        """One reseed-check pass. Returns delta-dict."""
        try:
            import seed_self_awareness as sa  # type: ignore
        except Exception as e:
            self.stats["last_error"] = f"import: {e}"
            return {"ok": False, "reason": f"import: {e}"}

        # Collect current sources
        sources = sa.collect_sources()
        manifest = sa.load_manifest()
        old_sources: Dict[str, Dict[str, Any]] = manifest.get("sources") or {}

        checked = 0
        unchanged = 0
        updated = 0
        added = 0

        # Track seen external_ids to detect removals at end
        seen_ids = set()

        for src in sources:
            checked += 1
            seen_ids.add(src["external_id"])
            h = sa.hash_for_source(src)
            prev = old_sources.get(src["external_id"])
            if prev and prev.get("hash") == h:
                unchanged += 1
                continue
            # Re-seed (covers both 'updated' and 'added')
            pid = sa.upsert_source(self.kg, src)
            if pid:
                old_sources[src["external_id"]] = {
                    "hash": h,
                    "node_id": pid,
                    "title": src["title"],
                    "subsystem": src["subsystem"],
                    "kind": src["kind"],
                    "path": src["path"],
                    "last_seeded_at": int(time.time()),
                }
                if prev:
                    updated += 1
                else:
                    added += 1
            else:
                self.stats["errors"] += 1

        # Detect removals: manifest entries whose external_id no longer in sources
        removed = 0
        to_remove: List[str] = []
        for ext_id, entry in list(old_sources.items()):
            if ext_id in seen_ids:
                continue
            # Source no longer exists. Delete the KG node.
            node_id = entry.get("node_id")
            if node_id:
                try:
                    self.kg.client.delete(
                        collection_name="brain-semantic",
                        points_selector=[node_id],
                        wait=True,
                    )
                except Exception as e:
                    logger.warning(
                        f"[self-aware] delete failed for {ext_id}: {e}"
                    )
            to_remove.append(ext_id)
            removed += 1
        for ext_id in to_remove:
            old_sources.pop(ext_id, None)

        # Save manifest
        manifest["sources"] = old_sources
        manifest["last_checked_at"] = int(time.time())
        sa.save_manifest(manifest)

        # Update cumulative stats
        self.stats["checks"] += checked
        self.stats["unchanged"] += unchanged
        self.stats["updated"] += updated
        self.stats["added"] += added
        self.stats["removed"] += removed

        return {
            "ok": True,
            "checked": checked,
            "unchanged": unchanged,
            "updated": updated,
            "added": added,
            "removed": removed,
        }

    # ── Public stats ─────────────────────────────────────────────────

    def stats_dict(self) -> Dict[str, Any]:
        return {
            "enabled": ENABLED,
            "tick_interval_s": TICK_INTERVAL_S,
            "running": bool(self._worker and self._worker.is_alive()),
            **self.stats,
        }
