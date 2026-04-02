"""Pipeline step sequencer - manages execution sequences for pipeline steps.

Defines and enforces step ordering, ensuring pipeline steps execute
in the correct sequence with valid transitions between steps.
"""

import time
import hashlib
import dataclasses
import logging

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class PipelineStepSequencerState:
    entries: dict = dataclasses.field(default_factory=dict)
    _seq: int = 0


class PipelineStepSequencer:
    """Manages execution sequences for pipeline steps.

    Defines and enforces step ordering, validates transitions,
    and tracks execution counts for registered sequences.
    """

    PREFIX = "psseq-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = PipelineStepSequencerState()
        self._callbacks = {}
        self._on_change = None
        logger.info("PipelineStepSequencer initialized")

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _prune(self):
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries.keys(),
                key=lambda k: self._state.entries[k].get("created_at", 0),
            )
            while len(self._state.entries) > self.MAX_ENTRIES:
                del self._state.entries[sorted_keys.pop(0)]

    def _fire(self, event: str, data: dict):
        if self._on_change:
            try:
                self._on_change(event, data)
            except Exception as e:
                logger.error("on_change error: %s", e)
        for cb in list(self._callbacks.values()):
            try:
                cb(event, data)
            except Exception as e:
                logger.error("Callback error: %s", e)

    @property
    def on_change(self):
        return self._on_change

    @on_change.setter
    def on_change(self, callback):
        self._on_change = callback

    def remove_callback(self, name: str) -> bool:
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    # ------------------------------------------------------------------
    # Register sequence
    # ------------------------------------------------------------------

    def register_sequence(self, name: str, steps: list) -> str:
        """Register an ordered sequence of step names.

        Returns a sequence ID (psseq-xxx).
        """
        self._prune()
        seq_id = self._generate_id(name)
        now = time.time()
        self._state.entries[seq_id] = {
            "sequence_id": seq_id,
            "name": name,
            "steps": list(steps),
            "created_at": now,
            "execution_count": 0,
        }
        self._fire("sequence_registered", {"sequence_id": seq_id, "name": name})
        return seq_id

    # ------------------------------------------------------------------
    # Get next step
    # ------------------------------------------------------------------

    def get_next_step(self, sequence_id: str, current_step: str = "") -> str:
        """Return next step in sequence after current_step.

        If current_step is empty, return the first step.
        Returns empty string if at end or sequence not found.
        """
        entry = self._state.entries.get(sequence_id)
        if not entry:
            return ""
        steps = entry["steps"]
        if not steps:
            return ""
        if current_step == "":
            return steps[0]
        try:
            idx = steps.index(current_step)
        except ValueError:
            return ""
        if idx + 1 < len(steps):
            return steps[idx + 1]
        return ""

    # ------------------------------------------------------------------
    # Validate transition
    # ------------------------------------------------------------------

    def is_valid_transition(self, sequence_id: str, from_step: str, to_step: str) -> bool:
        """Check if from_step -> to_step is a valid adjacent transition."""
        entry = self._state.entries.get(sequence_id)
        if not entry:
            return False
        steps = entry["steps"]
        try:
            idx = steps.index(from_step)
        except ValueError:
            return False
        if idx + 1 < len(steps) and steps[idx + 1] == to_step:
            return True
        return False

    # ------------------------------------------------------------------
    # Execute sequence
    # ------------------------------------------------------------------

    def execute_sequence(self, sequence_id: str) -> dict:
        """Walk through all steps in the sequence.

        Returns {"sequence_id", "steps_executed": list, "total_steps": N}.
        Increments execution_count.
        """
        entry = self._state.entries.get(sequence_id)
        if not entry:
            return {"sequence_id": sequence_id, "steps_executed": [], "total_steps": 0}
        steps = entry["steps"]
        entry["execution_count"] += 1
        self._fire("sequence_executed", {
            "sequence_id": sequence_id,
            "name": entry["name"],
            "execution_count": entry["execution_count"],
        })
        return {
            "sequence_id": sequence_id,
            "steps_executed": list(steps),
            "total_steps": len(steps),
        }

    # ------------------------------------------------------------------
    # Get sequence
    # ------------------------------------------------------------------

    def get_sequence(self, sequence_id: str) -> dict:
        """Get a sequence by ID. Returns dict or empty dict."""
        entry = self._state.entries.get(sequence_id)
        if not entry:
            return {}
        return dict(entry)

    # ------------------------------------------------------------------
    # Get sequences
    # ------------------------------------------------------------------

    def get_sequences(self) -> list:
        """Return all registered sequences."""
        return [dict(e) for e in self._state.entries.values()]

    # ------------------------------------------------------------------
    # Get sequence count
    # ------------------------------------------------------------------

    def get_sequence_count(self) -> int:
        """Return total number of registered sequences."""
        return len(self._state.entries)

    # ------------------------------------------------------------------
    # Remove sequence
    # ------------------------------------------------------------------

    def remove_sequence(self, sequence_id: str) -> bool:
        """Remove a sequence. Returns True if removed."""
        if sequence_id not in self._state.entries:
            return False
        info = self._state.entries.pop(sequence_id)
        self._fire("sequence_removed", {
            "sequence_id": sequence_id,
            "name": info["name"],
        })
        return True

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return operational statistics."""
        total_executions = sum(
            e["execution_count"] for e in self._state.entries.values()
        )
        return {
            "total_sequences": len(self._state.entries),
            "total_executions": total_executions,
        }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self):
        """Clear all stored sequences, callbacks, and reset sequence counter."""
        self._state.entries.clear()
        self._callbacks.clear()
        self._on_change = None
        self._state._seq = 0
