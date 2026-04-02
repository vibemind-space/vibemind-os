"""Pipeline State Machine -- manages pipeline state transitions with
defined valid transitions, history tracking, and change callbacks.

Enforces a fixed set of valid state transitions for pipeline lifecycle
management: idle -> running -> paused/completed/failed, with reset
capability from terminal states.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class _MachineEntry:
    """A pipeline state machine instance."""
    machine_id: str
    pipeline_id: str
    current_state: str
    initial_state: str
    states: List[str]
    history: List[Dict[str, Any]]
    created_at: float = field(default_factory=time.time)
    seq: int = 0


# ---------------------------------------------------------------------------
# Valid transitions
# ---------------------------------------------------------------------------

_VALID_TRANSITIONS: Dict[str, List[str]] = {
    "idle": ["running"],
    "running": ["paused", "completed", "failed"],
    "paused": ["running"],
    "failed": ["idle"],
}

_DEFAULT_STATES = ["idle", "running", "paused", "completed", "failed"]
_TERMINAL_STATES = {"completed", "failed"}


# ---------------------------------------------------------------------------
# Pipeline State Machine
# ---------------------------------------------------------------------------

class PipelineStateMachine:
    """Manages pipeline state transitions with defined valid transitions."""

    def __init__(self) -> None:
        self._machines: Dict[str, _MachineEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0
        self._max_entries: int = 10000

        # internal counters
        self._total_created: int = 0
        self._total_transitions: int = 0
        self._total_resets: int = 0
        self._total_failed_transitions: int = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, key: str) -> str:
        self._seq += 1
        raw = f"{key}-{uuid.uuid4()}-{self._seq}"
        return "psm-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Machine lifecycle
    # ------------------------------------------------------------------

    def create_machine(
        self,
        pipeline_id: str,
        states: Optional[List[str]] = None,
        initial_state: str = "idle",
    ) -> str:
        """Create a state machine for a pipeline. Returns machine ID."""
        if not pipeline_id:
            return ""
        if pipeline_id in self._machines:
            return ""
        if len(self._machines) >= self._max_entries:
            self._prune()

        resolved_states = list(states) if states else list(_DEFAULT_STATES)
        if initial_state not in resolved_states:
            resolved_states.append(initial_state)

        mid = self._generate_id(pipeline_id)
        entry = _MachineEntry(
            machine_id=mid,
            pipeline_id=pipeline_id,
            current_state=initial_state,
            initial_state=initial_state,
            states=resolved_states,
            history=[],
        )
        self._machines[pipeline_id] = entry
        self._total_created += 1

        logger.info(
            "pipeline_state_machine.created",
            pipeline_id=pipeline_id,
            machine_id=mid,
            initial_state=initial_state,
        )
        self._fire("machine_created", {
            "pipeline_id": pipeline_id,
            "machine_id": mid,
            "state": initial_state,
        })
        return mid

    def get_state(self, pipeline_id: str) -> str:
        """Return the current state of a pipeline, or 'unknown' if not found."""
        entry = self._machines.get(pipeline_id)
        if not entry:
            return "unknown"
        return entry.current_state

    def transition(self, pipeline_id: str, to_state: str) -> bool:
        """Attempt a state transition. Returns True on success."""
        entry = self._machines.get(pipeline_id)
        if not entry:
            logger.warning("pipeline_state_machine.transition_not_found", pipeline_id=pipeline_id)
            return False

        current = entry.current_state

        # Check if transition is valid
        allowed = _VALID_TRANSITIONS.get(current, [])
        if to_state not in allowed:
            self._total_failed_transitions += 1
            logger.warning(
                "pipeline_state_machine.invalid_transition",
                pipeline_id=pipeline_id,
                from_state=current,
                to_state=to_state,
                allowed=allowed,
            )
            return False

        # Check target state is in the machine's state list
        if to_state not in entry.states:
            self._total_failed_transitions += 1
            return False

        old_state = current
        entry.current_state = to_state
        entry.seq += 1

        # Record history
        record = {
            "from_state": old_state,
            "to_state": to_state,
            "timestamp": time.time(),
        }
        entry.history.append(record)

        self._total_transitions += 1

        logger.info(
            "pipeline_state_machine.transitioned",
            pipeline_id=pipeline_id,
            from_state=old_state,
            to_state=to_state,
        )
        self._fire("state_changed", {
            "pipeline_id": pipeline_id,
            "from_state": old_state,
            "to_state": to_state,
        })
        return True

    def get_history(self, pipeline_id: str) -> List[Dict]:
        """Return the transition history for a pipeline."""
        entry = self._machines.get(pipeline_id)
        if not entry:
            return []
        return list(entry.history)

    def is_terminal(self, pipeline_id: str) -> bool:
        """Return True if the pipeline is in a terminal state (completed or failed)."""
        entry = self._machines.get(pipeline_id)
        if not entry:
            return False
        return entry.current_state in _TERMINAL_STATES

    def reset_machine(self, pipeline_id: str) -> bool:
        """Reset a pipeline state machine to its initial state."""
        entry = self._machines.get(pipeline_id)
        if not entry:
            return False

        old_state = entry.current_state
        entry.current_state = entry.initial_state
        entry.seq += 1

        record = {
            "from_state": old_state,
            "to_state": entry.initial_state,
            "timestamp": time.time(),
        }
        entry.history.append(record)
        self._total_resets += 1

        logger.info(
            "pipeline_state_machine.reset",
            pipeline_id=pipeline_id,
            from_state=old_state,
            to_state=entry.initial_state,
        )
        self._fire("machine_reset", {
            "pipeline_id": pipeline_id,
            "from_state": old_state,
            "to_state": entry.initial_state,
        })
        return True

    def list_pipelines(self) -> List[str]:
        """Return all pipeline IDs."""
        return sorted(self._machines.keys())

    def get_machine_count(self) -> int:
        """Return the number of registered state machines."""
        return len(self._machines)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a callback for state changes."""
        self._callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a registered callback. Returns True if it existed."""
        return self._callbacks.pop(name, None) is not None

    def _fire(self, action: str, detail: Dict[str, Any]) -> None:
        """Fire all registered callbacks."""
        for cb_name, cb in list(self._callbacks.items()):
            try:
                cb(action, detail)
            except Exception:
                logger.exception(
                    "pipeline_state_machine.callback_error",
                    callback=cb_name,
                    action=action,
                )

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics."""
        terminal_count = sum(
            1 for e in self._machines.values()
            if e.current_state in _TERMINAL_STATES
        )
        return {
            "total_machines": len(self._machines),
            "total_created": self._total_created,
            "total_transitions": self._total_transitions,
            "total_resets": self._total_resets,
            "total_failed_transitions": self._total_failed_transitions,
            "terminal_count": terminal_count,
            "active_count": len(self._machines) - terminal_count,
            "callback_count": len(self._callbacks),
        }

    def reset(self) -> None:
        """Clear all machines, callbacks, and counters."""
        self._machines.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_created = 0
        self._total_transitions = 0
        self._total_resets = 0
        self._total_failed_transitions = 0
        logger.info("pipeline_state_machine.full_reset")

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Remove oldest terminal machines when at capacity."""
        terminal = [
            (pid, e) for pid, e in self._machines.items()
            if e.current_state in _TERMINAL_STATES
        ]
        terminal.sort(key=lambda x: x[1].created_at)
        to_remove = max(1, len(self._machines) - self._max_entries + 1)
        for pid, _ in terminal[:to_remove]:
            del self._machines[pid]
