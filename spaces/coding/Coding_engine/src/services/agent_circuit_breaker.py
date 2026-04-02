"""Agent circuit breaker.

Circuit breaker pattern for agent operations. Track failures and
open/close circuits to protect against cascading failures in
autonomous agent pipelines.
"""

import hashlib
import time
import dataclasses
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentCircuitBreakerState:
    """Internal state for the circuit breaker."""
    entries: dict = field(default_factory=dict)
    _seq: int = 0


class AgentCircuitBreaker:
    """Circuit breaker pattern for agent operations.

    Tracks failures per agent+operation pair and transitions circuits
    through closed -> open -> half_open -> closed states.
    """

    def __init__(self) -> None:
        self._state = AgentCircuitBreakerState(entries={})
        self._callbacks: Dict[str, Callable] = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_key(self, agent_id: str, operation: str) -> str:
        return f"{agent_id}::{operation}"

    def _gen_id(self, data: str) -> str:
        raw = hashlib.sha256(f"{data}{self._state._seq}".encode()).hexdigest()[:16]
        self._state._seq += 1
        return f"acb-{raw}"

    def _prune(self) -> None:
        if len(self._state.entries) > 10000:
            sorted_keys = sorted(
                self._state.entries.keys(),
                key=lambda k: self._state.entries[k].get("created_at", 0),
            )
            keep = sorted_keys[-5000:]
            self._state.entries = {k: self._state.entries[k] for k in keep}

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, cb: Callable) -> None:
        self._callbacks[name] = cb

    def remove_callback(self, name: str) -> bool:
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    def _fire(self, action: str, detail: dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                logger.exception("callback_error action=%s", action)

    # ------------------------------------------------------------------
    # Circuit management
    # ------------------------------------------------------------------

    def create_circuit(
        self,
        agent_id: str,
        operation: str,
        failure_threshold: int = 5,
        reset_timeout: float = 60.0,
    ) -> str:
        """Create a circuit breaker for an agent operation.

        Returns the circuit_id. State starts as 'closed' (requests allowed).
        """
        key = self._make_key(agent_id, operation)
        if key in self._state.entries:
            return self._state.entries[key]["circuit_id"]

        circuit_id = self._gen_id(f"{agent_id}{operation}{time.time()}")
        now = time.time()

        self._state.entries[key] = {
            "circuit_id": circuit_id,
            "agent_id": agent_id,
            "operation": operation,
            "state": "closed",
            "failure_count": 0,
            "success_count": 0,
            "failure_threshold": failure_threshold,
            "reset_timeout": reset_timeout,
            "open_since": 0.0,
            "created_at": now,
            "updated_at": now,
        }

        self._prune()

        logger.info(
            "circuit_created agent_id=%s operation=%s circuit_id=%s",
            agent_id, operation, circuit_id,
        )
        self._fire("circuit_created", {
            "circuit_id": circuit_id,
            "agent_id": agent_id,
            "operation": operation,
        })
        return circuit_id

    def record_success(self, agent_id: str, operation: str) -> bool:
        """Record a successful operation.

        If circuit is half_open, transitions to closed. Resets failure count.
        Returns True if a circuit exists for the pair, False otherwise.
        """
        key = self._make_key(agent_id, operation)
        entry = self._state.entries.get(key)
        if entry is None:
            return False

        old_state = entry["state"]
        entry["failure_count"] = 0
        entry["success_count"] += 1
        entry["updated_at"] = time.time()

        if old_state == "half_open":
            entry["state"] = "closed"
            entry["open_since"] = 0.0
            logger.info(
                "circuit_closed agent_id=%s operation=%s",
                agent_id, operation,
            )
            self._fire("circuit_closed", {
                "circuit_id": entry["circuit_id"],
                "agent_id": agent_id,
                "operation": operation,
                "previous_state": old_state,
            })

        return True

    def record_failure(self, agent_id: str, operation: str) -> dict:
        """Record a failed operation.

        Increments failure count. If failures >= threshold, opens the circuit.
        Returns dict with circuit_id, state, failure_count.
        """
        key = self._make_key(agent_id, operation)
        entry = self._state.entries.get(key)
        if entry is None:
            return {}

        entry["failure_count"] += 1
        entry["updated_at"] = time.time()

        if entry["failure_count"] >= entry["failure_threshold"] and entry["state"] != "open":
            entry["state"] = "open"
            entry["open_since"] = time.time()
            logger.warning(
                "circuit_opened agent_id=%s operation=%s failures=%d",
                agent_id, operation, entry["failure_count"],
            )
            self._fire("circuit_opened", {
                "circuit_id": entry["circuit_id"],
                "agent_id": agent_id,
                "operation": operation,
                "failure_count": entry["failure_count"],
            })

        return {
            "circuit_id": entry["circuit_id"],
            "state": entry["state"],
            "failure_count": entry["failure_count"],
        }

    def get_state(self, agent_id: str, operation: str) -> str:
        """Return current circuit state: closed, open, or half_open.

        If state is open and reset_timeout has elapsed, transitions to half_open.
        """
        key = self._make_key(agent_id, operation)
        entry = self._state.entries.get(key)
        if entry is None:
            return ""

        if entry["state"] == "open" and entry["open_since"] > 0:
            elapsed = time.time() - entry["open_since"]
            if elapsed >= entry["reset_timeout"]:
                entry["state"] = "half_open"
                entry["updated_at"] = time.time()
                logger.info(
                    "circuit_half_open agent_id=%s operation=%s",
                    agent_id, operation,
                )
                self._fire("circuit_half_open", {
                    "circuit_id": entry["circuit_id"],
                    "agent_id": agent_id,
                    "operation": operation,
                })

        return entry["state"]

    def is_allowed(self, agent_id: str, operation: str) -> bool:
        """Return True if the operation is allowed (circuit closed or half_open).

        If circuit is open but timeout has elapsed, transitions to half_open
        and returns True.
        """
        state = self.get_state(agent_id, operation)
        if state == "":
            return True  # no circuit means no restriction
        return state in ("closed", "half_open")

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def get_circuit(self, circuit_id: str) -> Optional[dict]:
        """Get circuit details by circuit_id."""
        for entry in self._state.entries.values():
            if entry["circuit_id"] == circuit_id:
                return dict(entry)
        return None

    def get_circuits(self, agent_id: str) -> list:
        """Get all circuits for a given agent."""
        results = []
        for entry in self._state.entries.values():
            if entry["agent_id"] == agent_id:
                results.append(dict(entry))
        return results

    def get_circuit_count(self, agent_id: str = "") -> int:
        """Count circuits, optionally filtered by agent_id."""
        if not agent_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values() if e["agent_id"] == agent_id
        )

    def list_agents(self) -> list:
        """List unique agent IDs that have circuits."""
        agents = set()
        for entry in self._state.entries.values():
            agents.add(entry["agent_id"])
        return sorted(agents)

    # ------------------------------------------------------------------
    # Stats / reset
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return summary statistics."""
        total = len(self._state.entries)
        closed = sum(1 for e in self._state.entries.values() if e["state"] == "closed")
        opened = sum(1 for e in self._state.entries.values() if e["state"] == "open")
        half_open = sum(1 for e in self._state.entries.values() if e["state"] == "half_open")
        return {
            "total_circuits": total,
            "closed": closed,
            "open": opened,
            "half_open": half_open,
            "agents": len(self.list_agents()),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentCircuitBreakerState(entries={})
        logger.info("circuit_breaker_reset")
        self._fire("reset", {})
