"""Agent skill store.

Manages agent skills with proficiency tracking and endorsements.
Provides skill discovery, proficiency updates, and endorsement
management for the emergent pipeline system.
"""

import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# ======================================================================
# Data model
# ======================================================================

@dataclass
class SkillRecord:
    """A single skill registered against an agent."""

    skill_id: str = ""
    agent_id: str = ""
    skill_name: str = ""
    proficiency: float = 0.5
    endorsements: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Serialise the record to a plain dictionary."""
        return {
            "skill_id": self.skill_id,
            "agent_id": self.agent_id,
            "skill_name": self.skill_name,
            "proficiency": self.proficiency,
            "endorsements": list(self.endorsements),
            "endorsement_count": len(self.endorsements),
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


# ======================================================================
# Store
# ======================================================================

class AgentSkillStore:
    """Manages agent skills with proficiency tracking and endorsements.

    Thread-safe store that supports registration, proficiency updates,
    endorsements, and skill-based agent discovery.  Entries are pruned
    when the store exceeds *max_entries* (oldest first).

    ID prefix: ``ask-``
    """

    def __init__(self, max_entries: int = 10_000) -> None:
        self._max_entries: int = max_entries

        # Primary storage: skill_id -> SkillRecord
        self._records: Dict[str, SkillRecord] = {}

        # Secondary index: agent_id -> { skill_name -> skill_id }
        self._agent_index: Dict[str, Dict[str, str]] = {}

        self._seq: int = 0
        self._lock = threading.Lock()
        self._callbacks: Dict[str, Callable] = {}
        self._stats: Dict[str, int] = {
            "total_skills_added": 0,
            "total_skills_removed": 0,
            "total_proficiency_updates": 0,
            "total_endorsements": 0,
            "total_lookups": 0,
        }

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self, seed: str) -> str:
        """Generate a deterministic, collision-free ID with prefix ``ask-``.

        Uses SHA-256 of *seed*, the current timestamp, and an internal
        sequence counter to guarantee uniqueness.
        """
        self._seq += 1
        raw = f"{seed}:{time.time()}:{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"ask-{digest}"

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Remove oldest records when the store is at capacity.

        Must be called while holding ``self._lock``.
        """
        if len(self._records) < self._max_entries:
            return

        sorted_records = sorted(
            self._records.values(), key=lambda r: r.created_at
        )
        remove_count = len(self._records) - self._max_entries + 1
        for record in sorted_records[:remove_count]:
            self._remove_record(record)
            logger.debug("skill_pruned: skill_id=%s", record.skill_id)

    def _remove_record(self, record: SkillRecord) -> None:
        """Delete a record from all indices.  Caller holds ``_lock``."""
        self._records.pop(record.skill_id, None)
        agent_skills = self._agent_index.get(record.agent_id)
        if agent_skills is not None:
            agent_skills.pop(record.skill_name, None)
            if not agent_skills:
                del self._agent_index[record.agent_id]
        self._stats["total_skills_removed"] += 1

    # ------------------------------------------------------------------
    # Skill management
    # ------------------------------------------------------------------

    def add_skill(
        self,
        agent_id: str,
        skill_name: str,
        proficiency: float = 0.5,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Register a skill for an agent.

        Parameters
        ----------
        agent_id:
            The agent registering the skill.
        skill_name:
            Human-readable skill identifier (e.g. ``"code-review"``).
        proficiency:
            Initial proficiency in the ``[0.0, 1.0]`` range.
        metadata:
            Arbitrary key/value pairs attached to the skill record.

        Returns
        -------
        str
            The generated ``ask-`` prefixed skill ID, or ``""`` if the
            agent already has this skill or the inputs are invalid.
        """
        if not agent_id or not skill_name:
            return ""
        if not (0.0 <= proficiency <= 1.0):
            return ""

        with self._lock:
            # Duplicate check
            agent_skills = self._agent_index.get(agent_id, {})
            if skill_name in agent_skills:
                logger.warning(
                    "duplicate_skill: agent_id=%s skill_name=%s",
                    agent_id,
                    skill_name,
                )
                return ""

            self._prune_if_needed()

            now = time.time()
            skill_id = self._next_id(f"{agent_id}:{skill_name}")

            record = SkillRecord(
                skill_id=skill_id,
                agent_id=agent_id,
                skill_name=skill_name,
                proficiency=proficiency,
                endorsements=[],
                metadata=dict(metadata) if metadata else {},
                created_at=now,
                updated_at=now,
            )

            self._records[skill_id] = record

            if agent_id not in self._agent_index:
                self._agent_index[agent_id] = {}
            self._agent_index[agent_id][skill_name] = skill_id

            self._stats["total_skills_added"] += 1

        logger.info(
            "skill_added: skill_id=%s agent_id=%s skill_name=%s proficiency=%.2f",
            skill_id,
            agent_id,
            skill_name,
            proficiency,
        )
        self._fire("skill_added", {
            "skill_id": skill_id,
            "agent_id": agent_id,
            "skill_name": skill_name,
            "proficiency": proficiency,
        })
        return skill_id

    def get_skill(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a single skill record by its ID.

        Returns
        -------
        dict or None
            The skill record as a plain dict, or ``None`` if not found.
        """
        with self._lock:
            self._stats["total_lookups"] += 1
            record = self._records.get(skill_id)
            if record is None:
                return None
            return record.to_dict()

    def get_agent_skills(self, agent_id: str) -> List[Dict[str, Any]]:
        """Return all skills registered for *agent_id*.

        Results are sorted alphabetically by skill name.
        """
        with self._lock:
            self._stats["total_lookups"] += 1
            agent_skills = self._agent_index.get(agent_id, {})
            result: List[Dict[str, Any]] = []
            for skill_name in sorted(agent_skills):
                skill_id = agent_skills[skill_name]
                record = self._records.get(skill_id)
                if record is not None:
                    result.append(record.to_dict())
            return result

    def remove_skill(self, agent_id: str, skill_name: str) -> bool:
        """Remove a skill from an agent.

        Returns
        -------
        bool
            ``True`` if the skill was found and removed, ``False`` otherwise.
        """
        with self._lock:
            agent_skills = self._agent_index.get(agent_id, {})
            skill_id = agent_skills.get(skill_name)
            if skill_id is None:
                return False

            record = self._records.get(skill_id)
            if record is None:
                return False

            self._remove_record(record)

        logger.info(
            "skill_removed: agent_id=%s skill_name=%s",
            agent_id,
            skill_name,
        )
        self._fire("skill_removed", {
            "agent_id": agent_id,
            "skill_name": skill_name,
        })
        return True

    # ------------------------------------------------------------------
    # Proficiency
    # ------------------------------------------------------------------

    def update_proficiency(
        self, agent_id: str, skill_name: str, proficiency: float
    ) -> bool:
        """Update the proficiency level for an agent's skill.

        Parameters
        ----------
        agent_id:
            Owner of the skill.
        skill_name:
            Name of the skill to update.
        proficiency:
            New proficiency value in ``[0.0, 1.0]``.

        Returns
        -------
        bool
            ``False`` if the skill was not found or *proficiency* is out
            of range.
        """
        if not (0.0 <= proficiency <= 1.0):
            return False

        with self._lock:
            agent_skills = self._agent_index.get(agent_id, {})
            skill_id = agent_skills.get(skill_name)
            if skill_id is None:
                return False

            record = self._records.get(skill_id)
            if record is None:
                return False

            record.proficiency = proficiency
            record.updated_at = time.time()
            self._stats["total_proficiency_updates"] += 1

        logger.debug(
            "proficiency_updated: agent_id=%s skill_name=%s proficiency=%.2f",
            agent_id,
            skill_name,
            proficiency,
        )
        self._fire("proficiency_updated", {
            "agent_id": agent_id,
            "skill_name": skill_name,
            "proficiency": proficiency,
        })
        return True

    # ------------------------------------------------------------------
    # Endorsements
    # ------------------------------------------------------------------

    def endorse(
        self, agent_id: str, skill_name: str, endorser_id: str
    ) -> bool:
        """Add an endorsement to an agent's skill.

        Parameters
        ----------
        agent_id:
            The agent whose skill is being endorsed.
        skill_name:
            The skill to endorse.
        endorser_id:
            The agent or entity providing the endorsement.

        Returns
        -------
        bool
            ``False`` if the skill record was not found.  ``True`` if
            the endorsement was added.  A duplicate *endorser_id* is
            silently ignored (still returns ``True``).
        """
        if not endorser_id:
            return False

        with self._lock:
            agent_skills = self._agent_index.get(agent_id, {})
            skill_id = agent_skills.get(skill_name)
            if skill_id is None:
                return False

            record = self._records.get(skill_id)
            if record is None:
                return False

            if endorser_id in record.endorsements:
                # Duplicate endorser -- silently accept.
                return True

            record.endorsements.append(endorser_id)
            record.updated_at = time.time()
            self._stats["total_endorsements"] += 1

        logger.debug(
            "skill_endorsed: agent_id=%s skill_name=%s endorser_id=%s",
            agent_id,
            skill_name,
            endorser_id,
        )
        self._fire("skill_endorsed", {
            "agent_id": agent_id,
            "skill_name": skill_name,
            "endorser_id": endorser_id,
        })
        return True

    def get_endorsements(
        self, agent_id: str, skill_name: str
    ) -> List[str]:
        """Return the list of endorser IDs for an agent's skill.

        Returns an empty list if the skill is not found.
        """
        with self._lock:
            agent_skills = self._agent_index.get(agent_id, {})
            skill_id = agent_skills.get(skill_name)
            if skill_id is None:
                return []

            record = self._records.get(skill_id)
            if record is None:
                return []

            return list(record.endorsements)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def find_agents_with_skill(
        self, skill_name: str, min_proficiency: float = 0.0
    ) -> List[Dict[str, Any]]:
        """Find agents that possess *skill_name* at or above *min_proficiency*.

        Results are sorted by proficiency descending.
        """
        with self._lock:
            self._stats["total_lookups"] += 1
            result: List[Dict[str, Any]] = []
            for record in self._records.values():
                if record.skill_name != skill_name:
                    continue
                if record.proficiency < min_proficiency:
                    continue
                result.append({
                    "agent_id": record.agent_id,
                    "skill_id": record.skill_id,
                    "proficiency": record.proficiency,
                    "endorsement_count": len(record.endorsements),
                })
            result.sort(key=lambda r: -r["proficiency"])
            return result

    def get_top_skilled(
        self, skill_name: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Return the top agents for *skill_name*, sorted by proficiency desc.

        Parameters
        ----------
        skill_name:
            The skill to rank agents by.
        limit:
            Maximum number of results to return.

        Returns
        -------
        list[dict]
            Each dict contains ``agent_id``, ``skill_id``,
            ``proficiency``, and ``endorsement_count``.
        """
        with self._lock:
            self._stats["total_lookups"] += 1
            candidates: List[Dict[str, Any]] = []
            for record in self._records.values():
                if record.skill_name != skill_name:
                    continue
                candidates.append({
                    "agent_id": record.agent_id,
                    "skill_id": record.skill_id,
                    "proficiency": record.proficiency,
                    "endorsement_count": len(record.endorsements),
                })
            candidates.sort(key=lambda r: -r["proficiency"])
            return candidates[:limit]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a callback that fires on store mutations.

        Parameters
        ----------
        name:
            Unique identifier for the callback.
        callback:
            ``callback(action: str, detail: dict)`` signature.
        """
        with self._lock:
            self._callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback.

        Returns ``False`` if *name* was not registered.
        """
        with self._lock:
            if name not in self._callbacks:
                return False
            del self._callbacks[name]
            return True

    def _fire(self, action: str, detail: Dict[str, Any]) -> None:
        """Invoke all registered callbacks with *action* and *detail*.

        Exceptions raised by individual callbacks are logged and
        swallowed so that one failing callback does not block others.
        """
        with self._lock:
            cbs = list(self._callbacks.values())

        for cb in cbs:
            try:
                cb(action, detail)
            except Exception:
                logger.exception("callback_error: action=%s", action)

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return a snapshot of store statistics.

        Includes both cumulative counters (``total_*``) and live gauges
        (``current_entries``, ``unique_agents``, etc.).
        """
        with self._lock:
            unique_skills: Set[str] = set()
            total_endorsements = 0
            for record in self._records.values():
                unique_skills.add(record.skill_name)
                total_endorsements += len(record.endorsements)

            return {
                **self._stats,
                "current_entries": len(self._records),
                "unique_agents": len(self._agent_index),
                "unique_skills": len(unique_skills),
                "current_endorsements": total_endorsements,
                "max_entries": self._max_entries,
                "callbacks_registered": len(self._callbacks),
            }

    def reset(self) -> None:
        """Clear all state -- records, indices, callbacks, counters."""
        with self._lock:
            self._records.clear()
            self._agent_index.clear()
            self._callbacks.clear()
            self._seq = 0
            self._stats = {k: 0 for k in self._stats}
        logger.info("store_reset")
