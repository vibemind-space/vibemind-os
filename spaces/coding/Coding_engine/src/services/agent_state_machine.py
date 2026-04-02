"""Agent State Machine – manages finite state machines for agents.

Registers states and transitions, enforces valid transitions, tracks
state history, and fires callbacks on state changes.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set


@dataclass
class _StateMachine:
    machine_id: str
    name: str
    current_state: str
    states: Set[str]
    transitions: Dict[str, Set[str]]  # from_state -> {to_states}
    tags: List[str]
    created_at: float
    updated_at: float


@dataclass
class _StateEvent:
    event_id: str
    machine_name: str
    from_state: str
    to_state: str
    action: str  # transitioned, reset
    timestamp: float


class AgentStateMachine:
    """Manages finite state machines for agents."""

    def __init__(self, max_machines: int = 10000, max_history: int = 100000):
        self._machines: Dict[str, _StateMachine] = {}
        self._name_index: Dict[str, str] = {}  # name -> machine_id
        self._history: List[_StateEvent] = []
        self._callbacks: Dict[str, Callable] = {}
        self._max_machines = max_machines
        self._max_history = max_history
        self._seq = 0

        # stats
        self._total_created = 0
        self._total_transitions = 0

    # ------------------------------------------------------------------
    # Creation
    # ------------------------------------------------------------------

    def create_machine(
        self,
        name: str,
        initial_state: str,
        states: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        if not name or not initial_state:
            return ""
        if name in self._name_index:
            return ""
        if len(self._machines) >= self._max_machines:
            return ""

        state_set = set(states) if states else set()
        state_set.add(initial_state)

        self._seq += 1
        now = time.time()
        raw = f"{name}-{now}-{self._seq}"
        mid = "sm-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        machine = _StateMachine(
            machine_id=mid,
            name=name,
            current_state=initial_state,
            states=state_set,
            transitions={},
            tags=tags or [],
            created_at=now,
            updated_at=now,
        )
        self._machines[mid] = machine
        self._name_index[name] = mid
        self._total_created += 1
        self._fire("machine_created", {"machine_id": mid, "name": name, "state": initial_state})
        return mid

    def get_machine(self, name: str) -> Optional[Dict[str, Any]]:
        mid = self._name_index.get(name)
        if not mid:
            return None
        m = self._machines[mid]
        transitions = {k: sorted(v) for k, v in m.transitions.items()}
        return {
            "machine_id": m.machine_id,
            "name": m.name,
            "current_state": m.current_state,
            "states": sorted(m.states),
            "transitions": transitions,
            "tags": list(m.tags),
            "created_at": m.created_at,
            "updated_at": m.updated_at,
        }

    def remove_machine(self, name: str) -> bool:
        mid = self._name_index.pop(name, None)
        if not mid:
            return False
        self._machines.pop(mid, None)
        return True

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def add_state(self, name: str, state: str) -> bool:
        mid = self._name_index.get(name)
        if not mid or not state:
            return False
        m = self._machines[mid]
        if state in m.states:
            return False
        m.states.add(state)
        return True

    def add_transition(self, name: str, from_state: str, to_state: str) -> bool:
        mid = self._name_index.get(name)
        if not mid:
            return False
        m = self._machines[mid]
        if from_state not in m.states or to_state not in m.states:
            return False
        m.transitions.setdefault(from_state, set()).add(to_state)
        return True

    def can_transition(self, name: str, to_state: str) -> bool:
        mid = self._name_index.get(name)
        if not mid:
            return False
        m = self._machines[mid]
        allowed = m.transitions.get(m.current_state, set())
        return to_state in allowed

    # ------------------------------------------------------------------
    # Transitions
    # ------------------------------------------------------------------

    def transition(self, name: str, to_state: str) -> bool:
        """Attempt to transition to a new state."""
        mid = self._name_index.get(name)
        if not mid:
            return False
        m = self._machines[mid]

        if to_state not in m.states:
            return False

        allowed = m.transitions.get(m.current_state, set())
        if to_state not in allowed:
            return False

        old_state = m.current_state
        m.current_state = to_state
        m.updated_at = time.time()
        self._total_transitions += 1
        self._record_event(name, old_state, to_state, "transitioned")
        self._fire("state_changed", {"name": name, "from": old_state, "to": to_state})
        return True

    def force_state(self, name: str, state: str) -> bool:
        """Force set state without transition validation."""
        mid = self._name_index.get(name)
        if not mid:
            return False
        m = self._machines[mid]
        if state not in m.states:
            return False
        old_state = m.current_state
        m.current_state = state
        m.updated_at = time.time()
        self._record_event(name, old_state, state, "forced")
        self._fire("state_forced", {"name": name, "from": old_state, "to": state})
        return True

    def get_state(self, name: str) -> str:
        mid = self._name_index.get(name)
        if not mid:
            return ""
        return self._machines[mid].current_state

    def get_available_transitions(self, name: str) -> List[str]:
        mid = self._name_index.get(name)
        if not mid:
            return []
        m = self._machines[mid]
        return sorted(m.transitions.get(m.current_state, set()))

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list_machines(self, state: str = "", tag: str = "") -> List[Dict[str, Any]]:
        results = []
        for m in self._machines.values():
            if state and m.current_state != state:
                continue
            if tag and tag not in m.tags:
                continue
            results.append(self.get_machine(m.name))
        return results

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def get_history(
        self,
        machine_name: str = "",
        action: str = "",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        results = []
        for ev in reversed(self._history):
            if machine_name and ev.machine_name != machine_name:
                continue
            if action and ev.action != action:
                continue
            results.append({
                "event_id": ev.event_id,
                "machine_name": ev.machine_name,
                "from_state": ev.from_state,
                "to_state": ev.to_state,
                "action": ev.action,
                "timestamp": ev.timestamp,
            })
            if len(results) >= limit:
                break
        return results

    def _record_event(self, machine_name: str, from_state: str, to_state: str, action: str) -> None:
        self._seq += 1
        now = time.time()
        raw = f"{machine_name}-{from_state}-{to_state}-{now}-{self._seq}"
        evid = "sme-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        event = _StateEvent(
            event_id=evid, machine_name=machine_name,
            from_state=from_state, to_state=to_state,
            action=action, timestamp=now,
        )
        if len(self._history) >= self._max_history:
            self._history.pop(0)
        self._history.append(event)

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
            "current_machines": len(self._machines),
            "total_created": self._total_created,
            "total_transitions": self._total_transitions,
            "history_size": len(self._history),
        }

    def reset(self) -> None:
        self._machines.clear()
        self._name_index.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_created = 0
        self._total_transitions = 0
