"""Pipeline Data Transformer — register, apply, chain, map, and filter transforms.

Provides a registry of named transform functions that can be applied individually,
chained in sequence, mapped over collections, or used as predicates for filtering.
Tracks per-transform execution statistics and maintains an auditable history.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Transform:
    transform_id: str
    name: str
    transform_fn: Callable
    description: str
    tags: List[str]
    call_count: int
    total_time: float
    error_count: int
    created_at: float


@dataclass
class _HistoryEntry:
    action: str
    transform_id: str
    name: str
    timestamp: float
    detail: str


class PipelineDataTransformer:
    """Register, apply, chain, map, and filter data transforms."""

    def __init__(self, max_entries: int = 10000, max_history: int = 50000):
        self._transforms: Dict[str, _Transform] = {}
        self._name_index: Dict[str, str] = {}
        self._history: List[_HistoryEntry] = []
        self._callbacks: Dict[str, Callable] = {}
        self._max_entries = max_entries
        self._max_history = max_history
        self._seq = 0

        # aggregate stats
        self._total_registered = 0
        self._total_applied = 0
        self._total_errors = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, name: str) -> str:
        self._seq += 1
        raw = f"{name}-{time.time()}-{self._seq}"
        return "pdt-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def _record_history(self, action: str, transform_id: str, name: str, detail: str = "") -> None:
        if len(self._history) >= self._max_history:
            self._history = self._history[len(self._history) // 4:]
        self._history.append(_HistoryEntry(
            action=action,
            transform_id=transform_id,
            name=name,
            timestamp=time.time(),
            detail=detail,
        ))

    def get_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Return recent history entries."""
        entries = self._history[-limit:] if limit < len(self._history) else self._history
        return [
            {
                "action": e.action,
                "transform_id": e.transform_id,
                "name": e.name,
                "timestamp": e.timestamp,
                "detail": e.detail,
            }
            for e in reversed(entries)
        ]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _fire(self, event: str, data: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(event, data)
            except Exception:
                pass

    def on_change(self, callback: Callable) -> str:
        """Register a change callback. Returns callback id."""
        self._seq += 1
        cb_id = f"cb-{self._seq}"
        self._callbacks[cb_id] = callback
        return cb_id

    def remove_callback(self, cb_id: str) -> bool:
        """Remove a registered callback."""
        if cb_id not in self._callbacks:
            return False
        del self._callbacks[cb_id]
        return True

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        if len(self._transforms) < self._max_entries:
            return
        # remove oldest entries
        by_age = sorted(self._transforms.values(), key=lambda t: t.created_at)
        to_remove = by_age[: len(by_age) // 4]
        for t in to_remove:
            del self._transforms[t.transform_id]
            self._name_index.pop(t.name, None)

    # ------------------------------------------------------------------
    # Transform registration
    # ------------------------------------------------------------------

    def register_transform(
        self,
        name: str,
        transform_fn: Callable,
        description: str = "",
        tags: Optional[List[str]] = None,
    ) -> str:
        """Register a transform function. Returns ID (pdt-...). Dup name returns ''."""
        if not name or not callable(transform_fn):
            return ""
        if name in self._name_index:
            return ""

        self._prune_if_needed()
        tid = self._generate_id(name)
        now = time.time()

        self._transforms[tid] = _Transform(
            transform_id=tid,
            name=name,
            transform_fn=transform_fn,
            description=description,
            tags=list(tags) if tags else [],
            call_count=0,
            total_time=0.0,
            error_count=0,
            created_at=now,
        )
        self._name_index[name] = tid
        self._total_registered += 1
        self._record_history("register", tid, name)
        self._fire("transform_registered", {"transform_id": tid, "name": name})
        return tid

    # ------------------------------------------------------------------
    # Apply
    # ------------------------------------------------------------------

    def apply(self, name: str, data: Any) -> Dict[str, Any]:
        """Apply a named transform to data. Returns result dict."""
        tid = self._name_index.get(name)
        if tid is None or tid not in self._transforms:
            return {"success": False, "result": None, "error": "transform_not_found"}

        t = self._transforms[tid]
        start = time.time()
        try:
            result = t.transform_fn(data)
            elapsed = time.time() - start
            t.call_count += 1
            t.total_time += elapsed
            self._total_applied += 1
            self._record_history("apply", tid, name)
            self._fire("transform_applied", {"transform_id": tid, "name": name})
            return {"success": True, "result": result, "error": ""}
        except Exception as exc:
            elapsed = time.time() - start
            t.call_count += 1
            t.total_time += elapsed
            t.error_count += 1
            self._total_errors += 1
            self._record_history("apply_error", tid, name, detail=str(exc))
            return {"success": False, "result": None, "error": str(exc)}

    # ------------------------------------------------------------------
    # Chain
    # ------------------------------------------------------------------

    def chain(self, names: List[str], data: Any) -> Dict[str, Any]:
        """Chain multiple transforms in order. Returns final result."""
        current = data
        for name in names:
            result = self.apply(name, current)
            if not result["success"]:
                return {
                    "success": False,
                    "result": None,
                    "error": f"failed at '{name}': {result['error']}",
                }
            current = result["result"]
        return {"success": True, "result": current, "error": ""}

    # ------------------------------------------------------------------
    # Map
    # ------------------------------------------------------------------

    def map_transform(self, name: str, items: List[Any]) -> Dict[str, Any]:
        """Apply transform to each item in list."""
        tid = self._name_index.get(name)
        if tid is None or tid not in self._transforms:
            return {"success": False, "results": [], "error": "transform_not_found"}

        results: List[Any] = []
        errors: List[str] = []
        for item in items:
            r = self.apply(name, item)
            if r["success"]:
                results.append(r["result"])
            else:
                errors.append(r["error"])
                results.append(None)

        success = len(errors) == 0
        return {
            "success": success,
            "results": results,
            "error": "; ".join(errors) if errors else "",
        }

    # ------------------------------------------------------------------
    # Filter
    # ------------------------------------------------------------------

    def filter_transform(self, name: str, items: List[Any]) -> Dict[str, Any]:
        """Filter items using transform as predicate."""
        tid = self._name_index.get(name)
        if tid is None or tid not in self._transforms:
            return {"success": False, "results": [], "error": "transform_not_found"}

        kept: List[Any] = []
        for item in items:
            r = self.apply(name, item)
            if not r["success"]:
                return {"success": False, "results": [], "error": r["error"]}
            if r["result"]:
                kept.append(item)

        return {"success": True, "results": kept, "error": ""}

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_transform(self, name: str) -> Optional[Dict[str, Any]]:
        """Get transform info by name."""
        tid = self._name_index.get(name)
        if tid is None or tid not in self._transforms:
            return None
        t = self._transforms[tid]
        return {
            "transform_id": t.transform_id,
            "name": t.name,
            "description": t.description,
            "tags": list(t.tags),
            "call_count": t.call_count,
            "total_time": t.total_time,
            "error_count": t.error_count,
            "created_at": t.created_at,
        }

    def list_transforms(self, tag: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all transforms, optionally filtered by tag."""
        result: List[Dict[str, Any]] = []
        for t in self._transforms.values():
            if tag is not None and tag not in t.tags:
                continue
            result.append({
                "transform_id": t.transform_id,
                "name": t.name,
                "description": t.description,
                "tags": list(t.tags),
                "call_count": t.call_count,
                "error_count": t.error_count,
                "created_at": t.created_at,
            })
        return result

    def remove_transform(self, name: str) -> bool:
        """Remove a transform by name."""
        tid = self._name_index.get(name)
        if tid is None or tid not in self._transforms:
            return False
        t = self._transforms.pop(tid)
        self._name_index.pop(name, None)
        self._record_history("remove", tid, name)
        self._fire("transform_removed", {"transform_id": tid, "name": name})
        return True

    # ------------------------------------------------------------------
    # Execution stats
    # ------------------------------------------------------------------

    def get_execution_stats(self, name: str) -> Dict[str, Any]:
        """Per-transform execution stats."""
        tid = self._name_index.get(name)
        if tid is None or tid not in self._transforms:
            return {}
        t = self._transforms[tid]
        avg_time = (t.total_time / t.call_count) if t.call_count > 0 else 0.0
        return {
            "name": t.name,
            "call_count": t.call_count,
            "avg_time": avg_time,
            "total_time": t.total_time,
            "errors": t.error_count,
        }

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Overall service stats."""
        return {
            "total_transforms": len(self._transforms),
            "total_registered": self._total_registered,
            "total_applied": self._total_applied,
            "total_errors": self._total_errors,
            "history_size": len(self._history),
            "callbacks": len(self._callbacks),
            "max_entries": self._max_entries,
            "max_history": self._max_history,
        }

    def reset(self) -> None:
        """Reset all state."""
        self._transforms.clear()
        self._name_index.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_registered = 0
        self._total_applied = 0
        self._total_errors = 0
