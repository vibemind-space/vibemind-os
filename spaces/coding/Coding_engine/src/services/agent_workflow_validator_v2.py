"""Agent Workflow Validator V2 -- validates agent workflows.

Validates agent workflows by agent ID and workflow name, applying
configurable rule sets.  Each validation produces a tracked record
with full metadata.

Collision-free IDs are generated with SHA-256 + a monotonic sequence
counter.  Automatic pruning removes the oldest quarter of entries when
the configurable maximum is reached.
"""

from __future__ import annotations

import copy
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Internal dataclass
# ------------------------------------------------------------------

@dataclass
class AgentWorkflowValidatorV2State:
    """Internal state container for the validator."""

    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

class AgentWorkflowValidatorV2:
    """Validates agent workflows against named rule sets.

    Each call to :meth:`validate_v2` creates a validation record keyed
    by a unique ID.  Records can be queried by agent, counted, and
    summarised via :meth:`get_stats`.
    """

    PREFIX = "awvv-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentWorkflowValidatorV2State()
        self._on_change: Optional[Callable] = None

    # ----------------------------------------------------------
    # ID generation
    # ----------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self._state._seq}-{datetime.now(timezone.utc).isoformat()}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ----------------------------------------------------------
    # Pruning
    # ----------------------------------------------------------

    def _prune(self) -> None:
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries,
                key=lambda k: (
                    self._state.entries[k].get("created_at", ""),
                    self._state.entries[k].get("_seq", 0),
                ),
            )
            to_remove = len(sorted_keys) // 4 or 1
            for key in sorted_keys[:to_remove]:
                del self._state.entries[key]

    # ----------------------------------------------------------
    # Event firing
    # ----------------------------------------------------------

    def _fire(self, action: str, **detail: Any) -> None:
        data = {"action": action, **detail}
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                logger.exception("on_change callback error")
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("callback error")

    # ----------------------------------------------------------
    # Callback management
    # ----------------------------------------------------------

    @property
    def on_change(self) -> Optional[Callable]:
        return self._on_change

    @on_change.setter
    def on_change(self, callback: Optional[Callable]) -> None:
        self._on_change = callback

    def remove_callback(self, name: str) -> bool:
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    # ----------------------------------------------------------
    # Validation
    # ----------------------------------------------------------

    def validate_v2(
        self,
        agent_id: str,
        workflow_name: str,
        rules: str = "default",
        metadata: Optional[dict] = None,
    ) -> str:
        """Create a validation record for an agent workflow.

        Parameters
        ----------
        agent_id:
            Identifier of the agent whose workflow is validated.
        workflow_name:
            Name of the workflow being validated.
        rules:
            Rule set to apply (default ``"default"``).
        metadata:
            Optional metadata dict attached to the record.

        Returns
        -------
        str
            The generated record ID, or ``""`` if inputs are invalid.
        """
        if not agent_id or not workflow_name:
            return ""

        record_id = self._generate_id()
        entry = {
            "record_id": record_id,
            "agent_id": agent_id,
            "workflow_name": workflow_name,
            "rules": rules,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        self._prune()
        self._fire("validate_v2", agent_id=agent_id, record_id=record_id)
        return record_id

    # ----------------------------------------------------------
    # Queries
    # ----------------------------------------------------------

    def get_validation(self, record_id: str) -> Optional[dict]:
        """Return a deep copy of a validation record, or ``None``."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return copy.deepcopy(entry)

    def get_validations(self, agent_id: str = "", limit: int = 50) -> List[dict]:
        """Return validation records, newest first.

        Parameters
        ----------
        agent_id:
            If non-empty, only records for this agent are returned.
        limit:
            Maximum number of records to return.
        """
        values = list(self._state.entries.values())
        if agent_id:
            values = [v for v in values if v.get("agent_id") == agent_id]
        values.sort(
            key=lambda v: (v.get("created_at", ""), v.get("_seq", 0)),
            reverse=True,
        )
        return [copy.deepcopy(v) for v in values[:limit]]

    def get_validation_count(self, agent_id: str = "") -> int:
        """Return the number of validation records."""
        if agent_id:
            return sum(
                1 for v in self._state.entries.values()
                if v.get("agent_id") == agent_id
            )
        return len(self._state.entries)

    # ----------------------------------------------------------
    # Stats
    # ----------------------------------------------------------

    def get_stats(self) -> dict:
        """Return summary statistics."""
        unique_agents = {
            v.get("agent_id") for v in self._state.entries.values()
        }
        return {
            "total_validations": len(self._state.entries),
            "unique_agents": len(unique_agents),
        }

    # ----------------------------------------------------------
    # Reset
    # ----------------------------------------------------------

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentWorkflowValidatorV2State()
        self._on_change = None
