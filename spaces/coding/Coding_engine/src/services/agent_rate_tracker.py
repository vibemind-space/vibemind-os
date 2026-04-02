"""Agent rate tracker.

Tracks agent operation rates (ops/sec, throughput, error rates) using
sliding time windows.  Provides per-agent and per-operation-type
analytics for real-time performance monitoring.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class _OperationRecord:
    """A single recorded operation."""
    timestamp: float = 0.0
    operation_type: str = "default"
    success: bool = True


@dataclass
class _AgentEntry:
    """Registered agent with its operation history."""
    agent_id: str = ""
    tags: List[str] = field(default_factory=list)
    operations: List[_OperationRecord] = field(default_factory=list)
    registered_at: float = 0.0
    seq: int = 0


class AgentRateTracker:
    """Tracks operation rates for registered agents."""

    def __init__(self, max_entries: int = 10000):
        self._max_entries = max_entries
        self._agents: Dict[str, _AgentEntry] = {}
        self._seq = 0
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_agents_registered": 0,
            "total_agents_removed": 0,
            "total_operations_recorded": 0,
            "total_successful_ops": 0,
            "total_failed_ops": 0,
        }

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _make_id(self, seed: str) -> str:
        self._seq += 1
        raw = f"{seed}{time.time()}{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"art-{digest}"

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_agents(self) -> None:
        """Remove oldest agents when capacity is exceeded."""
        if len(self._agents) <= self._max_entries:
            return
        sorted_ids = sorted(
            self._agents,
            key=lambda k: self._agents[k].registered_at,
        )
        to_remove = len(self._agents) - self._max_entries
        for aid in sorted_ids[:to_remove]:
            del self._agents[aid]
            logger.debug("agent_pruned", agent_id=aid)

    def _prune_operations(self, entry: _AgentEntry,
                          max_ops: int = 10000) -> None:
        """Keep only the most recent operations per agent."""
        if len(entry.operations) > max_ops:
            entry.operations = entry.operations[-max_ops:]

    # ------------------------------------------------------------------
    # Agent registration
    # ------------------------------------------------------------------

    def register_agent(self, agent_id: str,
                       tags: Optional[List[str]] = None) -> str:
        """Register an agent for rate tracking.

        Returns the agent_id on success or "" if duplicate.
        """
        if agent_id in self._agents:
            logger.warning("duplicate_agent", agent_id=agent_id)
            return ""

        if len(self._agents) >= self._max_entries:
            self._prune_agents()

        now = time.time()
        entry = _AgentEntry(
            agent_id=agent_id,
            tags=list(tags) if tags else [],
            registered_at=now,
            seq=self._seq,
        )
        self._agents[agent_id] = entry
        self._stats["total_agents_registered"] += 1

        logger.info("agent_registered", agent_id=agent_id, tags=entry.tags)
        self._fire("agent_registered", {"agent_id": agent_id, "tags": entry.tags})
        return agent_id

    # ------------------------------------------------------------------
    # Operation recording
    # ------------------------------------------------------------------

    def record_operation(self, agent_id: str,
                         operation_type: str = "default",
                         success: bool = True) -> bool:
        """Record an operation for a registered agent.

        Returns True on success, False if agent not found.
        """
        entry = self._agents.get(agent_id)
        if entry is None:
            logger.warning("agent_not_found", agent_id=agent_id)
            return False

        now = time.time()
        record = _OperationRecord(
            timestamp=now,
            operation_type=operation_type,
            success=success,
        )
        entry.operations.append(record)
        self._prune_operations(entry)

        self._stats["total_operations_recorded"] += 1
        if success:
            self._stats["total_successful_ops"] += 1
        else:
            self._stats["total_failed_ops"] += 1

        logger.debug(
            "operation_recorded",
            agent_id=agent_id,
            operation_type=operation_type,
            success=success,
        )
        self._fire("operation_recorded", {
            "agent_id": agent_id,
            "operation_type": operation_type,
            "success": success,
        })
        return True

    # ------------------------------------------------------------------
    # Rate calculation
    # ------------------------------------------------------------------

    def _compute_rate(self, operations: List[_OperationRecord],
                      operation_type: str,
                      window_seconds: float) -> Dict[str, Any]:
        """Compute rate metrics for a specific operation type within a window."""
        now = time.time()
        cutoff = now - window_seconds

        windowed = [
            op for op in operations
            if op.operation_type == operation_type and op.timestamp >= cutoff
        ]

        total_ops = len(windowed)
        successful = sum(1 for op in windowed if op.success)
        failed = total_ops - successful

        ops_per_second = total_ops / window_seconds if window_seconds > 0 else 0.0
        success_rate = successful / total_ops if total_ops > 0 else 0.0
        error_rate = failed / total_ops if total_ops > 0 else 0.0

        return {
            "ops_per_second": round(ops_per_second, 6),
            "total_ops": total_ops,
            "success_rate": round(success_rate, 6),
            "error_rate": round(error_rate, 6),
        }

    def get_rate(self, agent_id: str,
                 operation_type: str = "default",
                 window_seconds: float = 60) -> Dict[str, Any]:
        """Get the rate for a specific agent and operation type.

        Returns a dict with ops_per_second, total_ops, success_rate,
        error_rate.  Returns zeroed dict if agent not found.
        """
        entry = self._agents.get(agent_id)
        if entry is None:
            logger.warning("agent_not_found_for_rate", agent_id=agent_id)
            return {
                "ops_per_second": 0.0,
                "total_ops": 0,
                "success_rate": 0.0,
                "error_rate": 0.0,
            }

        return self._compute_rate(entry.operations, operation_type,
                                  window_seconds)

    def get_agent_rates(self, agent_id: str,
                        window_seconds: float = 60) -> Dict[str, Any]:
        """Get rates for all operation types of a given agent.

        Returns a dict keyed by operation_type, each value being
        a rate dict.  Returns empty dict if agent not found.
        """
        entry = self._agents.get(agent_id)
        if entry is None:
            logger.warning("agent_not_found_for_rates", agent_id=agent_id)
            return {}

        op_types: set = set()
        for op in entry.operations:
            op_types.add(op.operation_type)

        result: Dict[str, Any] = {}
        for op_type in sorted(op_types):
            result[op_type] = self._compute_rate(
                entry.operations, op_type, window_seconds,
            )
        return result

    # ------------------------------------------------------------------
    # Top agents
    # ------------------------------------------------------------------

    def get_top_agents(self, operation_type: str = "default",
                       limit: int = 10,
                       window_seconds: float = 60) -> List[Dict[str, Any]]:
        """Return top agents sorted by ops_per_second for a given type.

        Each entry contains agent_id, tags, and the rate dict.
        """
        ranked: List[Dict[str, Any]] = []
        for agent_id, entry in self._agents.items():
            rate = self._compute_rate(
                entry.operations, operation_type, window_seconds,
            )
            if rate["total_ops"] == 0:
                continue
            ranked.append({
                "agent_id": agent_id,
                "tags": list(entry.tags),
                **rate,
            })

        ranked.sort(key=lambda r: r["ops_per_second"], reverse=True)
        return ranked[:limit]

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_agents(self, tag: Optional[str] = None) -> List[Dict[str, Any]]:
        """List registered agents, optionally filtered by tag."""
        results: List[Dict[str, Any]] = []
        for agent_id, entry in self._agents.items():
            if tag is not None and tag not in entry.tags:
                continue
            results.append({
                "agent_id": agent_id,
                "tags": list(entry.tags),
                "registered_at": entry.registered_at,
                "operation_count": len(entry.operations),
            })
        return results

    # ------------------------------------------------------------------
    # Removal
    # ------------------------------------------------------------------

    def remove_agent(self, agent_id: str) -> bool:
        """Remove a registered agent. Returns True if removed."""
        if agent_id not in self._agents:
            logger.warning("remove_agent_not_found", agent_id=agent_id)
            return False

        del self._agents[agent_id]
        self._stats["total_agents_removed"] += 1

        logger.info("agent_removed", agent_id=agent_id)
        self._fire("agent_removed", {"agent_id": agent_id})
        return True

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a callback. Returns False if name already taken."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name. Returns False if not found."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, data: Dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("callback_error", action=action)

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return aggregate statistics."""
        total_ops_in_memory = sum(
            len(e.operations) for e in self._agents.values()
        )
        op_types_seen: set = set()
        for entry in self._agents.values():
            for op in entry.operations:
                op_types_seen.add(op.operation_type)

        return {
            **self._stats,
            "current_agents": len(self._agents),
            "total_operations_in_memory": total_ops_in_memory,
            "distinct_operation_types": len(op_types_seen),
            "callbacks_registered": len(self._callbacks),
            "max_entries": self._max_entries,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._agents.clear()
        self._seq = 0
        self._callbacks.clear()
        for key in self._stats:
            self._stats[key] = 0
        logger.info("rate_tracker_reset")
