"""Pipeline Signal Handler – manages inter-component signaling.

Provides a pub/sub signal system where components can emit named
signals and register handlers. Supports signal priorities, filtering,
and one-shot handlers that auto-deregister after first invocation.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Signal:
    signal_id: str
    name: str
    source: str
    payload: Dict[str, Any]
    priority: int
    created_at: float


@dataclass
class _Handler:
    handler_id: str
    signal_name: str
    component: str
    one_shot: bool
    active: bool
    total_invocations: int
    tags: List[str]
    created_at: float


class PipelineSignalHandler:
    """Pub/sub signal system for pipeline components."""

    def __init__(self, max_handlers: int = 10000, max_history: int = 100000):
        self._handlers: Dict[str, _Handler] = {}
        self._handler_fns: Dict[str, Callable] = {}
        self._signal_history: List[_Signal] = []
        self._name_index: Dict[str, str] = {}  # handler component -> handler_id
        self._callbacks: Dict[str, Callable] = {}
        self._max_handlers = max_handlers
        self._max_history = max_history
        self._seq = 0

        # stats
        self._total_handlers = 0
        self._total_signals = 0
        self._total_deliveries = 0

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def register_handler(
        self,
        signal_name: str,
        component: str,
        handler_fn: Optional[Callable] = None,
        one_shot: bool = False,
        tags: Optional[List[str]] = None,
    ) -> str:
        if not signal_name or not component:
            return ""
        # unique by (signal_name, component)
        key = f"{signal_name}:{component}"
        if key in self._name_index:
            return ""
        if len(self._handlers) >= self._max_handlers:
            return ""

        self._seq += 1
        now = time.time()
        raw = f"{signal_name}-{component}-{now}-{self._seq}"
        hid = "hdl-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        h = _Handler(
            handler_id=hid,
            signal_name=signal_name,
            component=component,
            one_shot=one_shot,
            active=True,
            total_invocations=0,
            tags=tags or [],
            created_at=now,
        )
        self._handlers[hid] = h
        self._name_index[key] = hid
        if handler_fn:
            self._handler_fns[hid] = handler_fn
        self._total_handlers += 1
        self._fire("handler_registered", {"handler_id": hid, "signal_name": signal_name})
        return hid

    def get_handler(self, handler_id: str) -> Optional[Dict[str, Any]]:
        h = self._handlers.get(handler_id)
        if not h:
            return None
        return {
            "handler_id": h.handler_id,
            "signal_name": h.signal_name,
            "component": h.component,
            "one_shot": h.one_shot,
            "active": h.active,
            "total_invocations": h.total_invocations,
            "tags": list(h.tags),
            "created_at": h.created_at,
        }

    def remove_handler(self, handler_id: str) -> bool:
        h = self._handlers.pop(handler_id, None)
        if not h:
            return False
        key = f"{h.signal_name}:{h.component}"
        self._name_index.pop(key, None)
        self._handler_fns.pop(handler_id, None)
        self._fire("handler_removed", {"handler_id": handler_id})
        return True

    def disable_handler(self, handler_id: str) -> bool:
        h = self._handlers.get(handler_id)
        if not h or not h.active:
            return False
        h.active = False
        return True

    def enable_handler(self, handler_id: str) -> bool:
        h = self._handlers.get(handler_id)
        if not h or h.active:
            return False
        h.active = True
        return True

    def list_handlers(
        self,
        signal_name: str = "",
        component: str = "",
        active: Optional[bool] = None,
        tag: str = "",
    ) -> List[Dict[str, Any]]:
        results = []
        for h in self._handlers.values():
            if signal_name and h.signal_name != signal_name:
                continue
            if component and h.component != component:
                continue
            if active is not None and h.active != active:
                continue
            if tag and tag not in h.tags:
                continue
            results.append(self.get_handler(h.handler_id))
        return results

    # ------------------------------------------------------------------
    # Emit signals
    # ------------------------------------------------------------------

    def emit(
        self,
        signal_name: str,
        source: str = "",
        payload: Optional[Dict[str, Any]] = None,
        priority: int = 5,
    ) -> int:
        """Emit a signal. Returns number of handlers invoked."""
        if not signal_name:
            return 0

        self._seq += 1
        now = time.time()
        raw = f"{signal_name}-{source}-{now}-{self._seq}"
        sid = "sig-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        signal = _Signal(
            signal_id=sid,
            name=signal_name,
            source=source,
            payload=payload or {},
            priority=priority,
            created_at=now,
        )

        # store in history (bounded)
        if len(self._signal_history) >= self._max_history:
            self._signal_history = self._signal_history[-(self._max_history // 2):]
        self._signal_history.append(signal)
        self._total_signals += 1

        # invoke handlers
        invoked = 0
        to_remove = []
        for hid, h in self._handlers.items():
            if h.signal_name != signal_name or not h.active:
                continue
            h.total_invocations += 1
            invoked += 1
            fn = self._handler_fns.get(hid)
            if fn:
                try:
                    fn(signal_name, payload or {})
                except Exception:
                    pass
            if h.one_shot:
                to_remove.append(hid)

        for hid in to_remove:
            self.remove_handler(hid)

        self._total_deliveries += invoked
        self._fire("signal_emitted", {
            "signal_name": signal_name, "handlers_invoked": invoked
        })
        return invoked

    def get_signal_history(
        self,
        signal_name: str = "",
        source: str = "",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        results = []
        for s in reversed(self._signal_history):
            if signal_name and s.name != signal_name:
                continue
            if source and s.source != source:
                continue
            results.append({
                "signal_id": s.signal_id,
                "name": s.name,
                "source": s.source,
                "payload": dict(s.payload),
                "priority": s.priority,
                "created_at": s.created_at,
            })
            if len(results) >= limit:
                break
        return results

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        return self._callbacks.pop(name, None) is not None

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        return {
            "current_handlers": len(self._handlers),
            "signal_history_size": len(self._signal_history),
            "total_handlers": self._total_handlers,
            "total_signals": self._total_signals,
            "total_deliveries": self._total_deliveries,
            "active_handlers": sum(1 for h in self._handlers.values() if h.active),
        }

    def reset(self) -> None:
        self._handlers.clear()
        self._handler_fns.clear()
        self._signal_history.clear()
        self._name_index.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_handlers = 0
        self._total_signals = 0
        self._total_deliveries = 0
