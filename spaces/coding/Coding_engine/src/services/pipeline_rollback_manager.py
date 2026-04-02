"""Pipeline rollback manager for saving checkpoints and rolling back to them."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class PipelineRollbackManager:
    """Manages pipeline rollback operations: save snapshots, rollback to them."""

    max_entries: int = 10000
    _snapshots: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = field(default=0)
    _callbacks: Dict[str, Callable] = field(default_factory=dict)
    _total_saves: int = field(default=0)
    _total_rollbacks: int = field(default=0)
    _total_deletes: int = field(default=0)

    def _next_id(self, pipeline_id: str) -> str:
        self._seq += 1
        raw = hashlib.sha256(f"{pipeline_id}{self._seq}".encode()).hexdigest()[:12]
        return f"prm-{raw}"

    def _prune(self) -> None:
        while len(self._snapshots) > self.max_entries:
            oldest_id = min(
                self._snapshots,
                key=lambda sid: (
                    self._snapshots[sid]["created_at"],
                    self._snapshots[sid]["seq"],
                ),
            )
            del self._snapshots[oldest_id]
            logger.debug("pipeline_rollback_manager.pruned", snapshot_id=oldest_id)

    def _fire(self, event: str, **kwargs: Any) -> None:
        for name, cb in list(self._callbacks.items()):
            try:
                cb(event, **kwargs)
            except Exception:
                logger.exception(
                    "pipeline_rollback_manager.callback_error",
                    callback=name,
                    event=event,
                )

    # ── public API ──────────────────────────────────────────────

    def save_snapshot(
        self, pipeline_id: str, state: dict, label: str = ""
    ) -> str:
        snapshot_id = self._next_id(pipeline_id)
        now = time.time()
        entry: Dict[str, Any] = {
            "snapshot_id": snapshot_id,
            "pipeline_id": pipeline_id,
            "state": dict(state),
            "label": label,
            "created_at": now,
            "seq": self._seq,
        }
        self._snapshots[snapshot_id] = entry
        self._total_saves += 1
        self._prune()
        logger.info(
            "pipeline_rollback_manager.snapshot_saved",
            snapshot_id=snapshot_id,
            pipeline_id=pipeline_id,
            label=label,
        )
        self._fire("snapshot_saved", snapshot_id=snapshot_id, pipeline_id=pipeline_id)
        return snapshot_id

    def create_checkpoint(
        self, name: str, pipeline_id: str, state: Optional[dict] = None
    ) -> str:
        """Backward-compatible alias: create_checkpoint(name, pipeline_id, state={})."""
        return self.save_snapshot(pipeline_id, state or {}, label=name)

    def rollback(
        self, pipeline_id: str, label: str = ""
    ) -> Optional[Dict[str, Any]]:
        if label:
            # Find snapshot by label
            matches = [
                s for s in self._snapshots.values()
                if s["pipeline_id"] == pipeline_id and s["label"] == label
            ]
            if not matches:
                logger.warning(
                    "pipeline_rollback_manager.rollback_no_snapshot",
                    pipeline_id=pipeline_id,
                    label=label,
                )
                return None
            target = max(matches, key=lambda s: (s["created_at"], s["seq"]))
        else:
            target = self.get_latest_snapshot(pipeline_id)
            if target is None:
                logger.warning(
                    "pipeline_rollback_manager.rollback_no_snapshot",
                    pipeline_id=pipeline_id,
                )
                return None
        self._total_rollbacks += 1
        logger.info(
            "pipeline_rollback_manager.rollback",
            pipeline_id=pipeline_id,
            snapshot_id=target["snapshot_id"],
        )
        self._fire(
            "rollback", pipeline_id=pipeline_id, snapshot_id=target["snapshot_id"]
        )
        return {"success": True, "restored_state": target["state"], **target}

    def get_snapshot(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        entry = self._snapshots.get(snapshot_id)
        if entry is None:
            return None
        return dict(entry)

    def get_snapshots(self, pipeline_id: str) -> List[Dict[str, Any]]:
        matches = [
            dict(s)
            for s in self._snapshots.values()
            if s["pipeline_id"] == pipeline_id
        ]
        matches.sort(key=lambda s: (s["created_at"], s["seq"]))
        return matches

    def get_latest_snapshot(self, pipeline_id: str) -> Optional[Dict[str, Any]]:
        matches = [
            s for s in self._snapshots.values() if s["pipeline_id"] == pipeline_id
        ]
        if not matches:
            return None
        latest = max(matches, key=lambda s: (s["created_at"], s["seq"]))
        return dict(latest)

    def delete_snapshot(self, snapshot_id: str) -> bool:
        if snapshot_id not in self._snapshots:
            return False
        del self._snapshots[snapshot_id]
        self._total_deletes += 1
        logger.info(
            "pipeline_rollback_manager.snapshot_deleted", snapshot_id=snapshot_id
        )
        self._fire("snapshot_deleted", snapshot_id=snapshot_id)
        return True

    def get_snapshot_count(self) -> int:
        return len(self._snapshots)

    def list_pipelines(self) -> List[str]:
        seen: set[str] = set()
        result: List[str] = []
        for s in self._snapshots.values():
            pid = s["pipeline_id"]
            if pid not in seen:
                seen.add(pid)
                result.append(pid)
        return result

    # ── callbacks ───────────────────────────────────────────────

    def on_change(self, name: str, callback: Callable) -> None:
        self._callbacks[name] = callback
        logger.debug("pipeline_rollback_manager.callback_registered", name=name)

    def remove_callback(self, name: str) -> bool:
        if name in self._callbacks:
            del self._callbacks[name]
            logger.debug("pipeline_rollback_manager.callback_removed", name=name)
            return True
        return False

    # ── stats / reset ───────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_snapshots": len(self._snapshots),
            "total_saves": self._total_saves,
            "total_rollbacks": self._total_rollbacks,
            "total_deletes": self._total_deletes,
            "max_entries": self.max_entries,
            "pipelines": len(self.list_pipelines()),
            "callbacks": len(self._callbacks),
        }

    def reset(self) -> None:
        self._snapshots.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_saves = 0
        self._total_rollbacks = 0
        self._total_deletes = 0
        logger.info("pipeline_rollback_manager.reset")
