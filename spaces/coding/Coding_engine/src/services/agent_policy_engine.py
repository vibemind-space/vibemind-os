"""Agent Policy Enforcement Engine — evaluates agent actions against configurable policies.

Features:
- Create, update, enable, disable, and delete policies
- Rule-based evaluation: allow/deny effects per action
- Per-agent evaluation logging with query support
- Collision-free IDs via SHA256 + sequence counter
- Change callbacks for reactive integrations
- Thread-safe with threading.Lock
- Configurable max_entries pruning
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PolicyEntry:
    """A single agent policy."""
    policy_id: str
    name: str
    rules: List[Dict[str, str]]
    description: str
    enabled: bool
    created_at: float
    seq: int


@dataclass
class EvaluationRecord:
    """A single evaluation result."""
    agent_id: str
    action: str
    context: Dict[str, Any]
    allowed: bool
    matched_policies: List[str]
    denied_by: Optional[str]
    timestamp: float


# ---------------------------------------------------------------------------
# Agent Policy Engine
# ---------------------------------------------------------------------------

class AgentPolicyEngine:
    """Evaluates agent actions against configurable allow/deny policies."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._max_entries = max_entries
        self._policies: Dict[str, PolicyEntry] = {}
        self._name_index: Dict[str, str] = {}  # name -> policy_id
        self._evaluation_log: List[EvaluationRecord] = []
        self._seq = 0
        self._lock = threading.Lock()
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_policies_created": 0,
            "total_policies_deleted": 0,
            "total_evaluations": 0,
        }

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self, seed: str) -> str:
        """Generate a collision-free ID with the ``ape-`` prefix."""
        self._seq += 1
        raw = f"{seed}-{self._seq}-{time.time()}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return f"ape-{digest}_{self._seq}"

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a change callback.

        Args:
            name: Unique name for the callback registration.
            callback: A callable accepting ``(action: str, details: dict)``.

        Returns:
            ``True`` if registered, ``False`` if *name* already exists.
        """
        with self._lock:
            if name in self._callbacks:
                return False
            self._callbacks[name] = callback
            return True

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback.

        Returns:
            ``True`` if removed, ``False`` if *name* was not found.
        """
        with self._lock:
            if name not in self._callbacks:
                return False
            del self._callbacks[name]
            return True

    def _fire(self, action: str, details: Dict) -> None:
        """Notify all registered callbacks."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, details)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_log(self) -> None:
        """Remove oldest evaluation log entries when exceeding max_entries."""
        if len(self._evaluation_log) <= self._max_entries:
            return
        overflow = len(self._evaluation_log) - self._max_entries
        self._evaluation_log = self._evaluation_log[overflow:]

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def create_policy(
        self,
        name: str,
        rules: List[Dict[str, str]],
        description: str = "",
        enabled: bool = True,
    ) -> str:
        """Create a new policy.

        Args:
            name: Unique policy name.
            rules: List of rule dicts with ``action`` and ``effect``
                (``"allow"`` or ``"deny"``).
            description: Optional human-readable description.
            enabled: Whether the policy is active immediately.

        Returns:
            The generated policy_id string, or ``""`` if *name* already exists.
        """
        with self._lock:
            if name in self._name_index:
                return ""

            policy_id = self._next_id(name)
            entry = PolicyEntry(
                policy_id=policy_id,
                name=name,
                rules=list(rules),
                description=description,
                enabled=enabled,
                created_at=time.time(),
                seq=self._seq,
            )
            self._policies[policy_id] = entry
            self._name_index[name] = policy_id
            self._stats["total_policies_created"] += 1

        logger.debug(
            "policy_created: policy_id=%s name=%s enabled=%s",
            policy_id, name, enabled,
        )
        self._fire("policy_created", {
            "policy_id": policy_id,
            "name": name,
            "enabled": enabled,
        })
        return policy_id

    def get_policy(self, policy_id: str) -> Optional[Dict]:
        """Retrieve a single policy by its ID.

        Returns:
            Policy dict or ``None`` if not found.
        """
        with self._lock:
            entry = self._policies.get(policy_id)
            if entry is None:
                return None
            return self._entry_to_dict(entry)

    def get_policy_by_name(self, name: str) -> Optional[Dict]:
        """Retrieve a single policy by its unique name.

        Returns:
            Policy dict or ``None`` if not found.
        """
        with self._lock:
            policy_id = self._name_index.get(name)
            if policy_id is None:
                return None
            entry = self._policies.get(policy_id)
            if entry is None:
                return None
            return self._entry_to_dict(entry)

    def evaluate(
        self,
        agent_id: str,
        action: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict:
        """Evaluate an agent action against all enabled policies.

        Rules are checked across all enabled policies. If any ``"deny"``
        rule matches the action, the result is denied.  If no deny and at
        least one ``"allow"`` rule matches, the result is allowed.  If no
        rules match at all the default is allowed.

        Args:
            agent_id: Identifier of the agent performing the action.
            action: The action string to evaluate.
            context: Optional context dict for the evaluation.

        Returns:
            Dict with ``allowed`` (bool), ``matched_policies`` (list),
            and ``denied_by`` (str or None).
        """
        ctx = dict(context) if context else {}

        with self._lock:
            matched_policies: List[str] = []
            denied_by: Optional[str] = None
            has_allow = False

            for entry in self._policies.values():
                if not entry.enabled:
                    continue
                for rule in entry.rules:
                    if rule.get("action") == action:
                        matched_policies.append(entry.policy_id)
                        effect = rule.get("effect", "")
                        if effect == "deny":
                            denied_by = entry.name
                        elif effect == "allow":
                            has_allow = True
                        break  # one match per policy is enough

            if denied_by is not None:
                allowed = False
            else:
                allowed = True  # default to allowed (even if no allow rule)

            record = EvaluationRecord(
                agent_id=agent_id,
                action=action,
                context=ctx,
                allowed=allowed,
                matched_policies=list(matched_policies),
                denied_by=denied_by,
                timestamp=time.time(),
            )
            self._evaluation_log.append(record)
            self._stats["total_evaluations"] += 1
            self._prune_log()

        result = {
            "allowed": allowed,
            "matched_policies": matched_policies,
            "denied_by": denied_by,
        }

        self._fire("evaluation", {
            "agent_id": agent_id,
            "action": action,
            "allowed": allowed,
        })
        return result

    def enable_policy(self, policy_id: str) -> bool:
        """Enable a policy.

        Returns:
            ``True`` if the policy was found and enabled, ``False`` otherwise.
        """
        with self._lock:
            entry = self._policies.get(policy_id)
            if entry is None:
                return False
            entry.enabled = True

        self._fire("policy_enabled", {"policy_id": policy_id})
        return True

    def disable_policy(self, policy_id: str) -> bool:
        """Disable a policy.

        Returns:
            ``True`` if the policy was found and disabled, ``False`` otherwise.
        """
        with self._lock:
            entry = self._policies.get(policy_id)
            if entry is None:
                return False
            entry.enabled = False

        self._fire("policy_disabled", {"policy_id": policy_id})
        return True

    def update_policy(
        self,
        policy_id: str,
        rules: Optional[List[Dict[str, str]]] = None,
        description: Optional[str] = None,
    ) -> bool:
        """Update a policy's rules and/or description.

        Returns:
            ``True`` if the policy was found and updated, ``False`` otherwise.
        """
        with self._lock:
            entry = self._policies.get(policy_id)
            if entry is None:
                return False
            if rules is not None:
                entry.rules = list(rules)
            if description is not None:
                entry.description = description

        self._fire("policy_updated", {"policy_id": policy_id})
        return True

    def delete_policy(self, policy_id: str) -> bool:
        """Delete a policy.

        Returns:
            ``True`` if the policy was found and deleted, ``False`` otherwise.
        """
        with self._lock:
            entry = self._policies.get(policy_id)
            if entry is None:
                return False
            del self._policies[policy_id]
            self._name_index.pop(entry.name, None)
            self._stats["total_policies_deleted"] += 1

        self._fire("policy_deleted", {"policy_id": policy_id})
        return True

    def list_policies(self, enabled_only: bool = False) -> List[Dict]:
        """List all policies, optionally filtering to enabled-only.

        Args:
            enabled_only: If ``True``, return only enabled policies.

        Returns:
            List of policy dicts.
        """
        with self._lock:
            results: List[Dict] = []
            for entry in self._policies.values():
                if enabled_only and not entry.enabled:
                    continue
                results.append(self._entry_to_dict(entry))
            return results

    def get_policy_count(self) -> int:
        """Return the number of stored policies."""
        with self._lock:
            return len(self._policies)

    def get_evaluation_log(
        self,
        agent_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """Return recent evaluation results, optionally filtered by agent.

        Args:
            agent_id: If provided, only return evaluations for this agent.
            limit: Maximum number of results to return.

        Returns:
            List of evaluation result dicts, most-recent first.
        """
        with self._lock:
            results: List[Dict] = []
            for record in reversed(self._evaluation_log):
                if agent_id and record.agent_id != agent_id:
                    continue
                results.append({
                    "agent_id": record.agent_id,
                    "action": record.action,
                    "context": record.context,
                    "allowed": record.allowed,
                    "matched_policies": record.matched_policies,
                    "denied_by": record.denied_by,
                    "timestamp": record.timestamp,
                })
                if len(results) >= limit:
                    break
            return results

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Return internal counters and current sizes.

        Returns:
            Dict with lifetime counters and current policy/callback counts.
        """
        with self._lock:
            return {
                **self._stats,
                "current_policies": len(self._policies),
                "current_enabled": sum(
                    1 for e in self._policies.values() if e.enabled
                ),
                "current_evaluation_log_size": len(self._evaluation_log),
                "current_callbacks": len(self._callbacks),
                "current_seq": self._seq,
            }

    def reset(self) -> None:
        """Clear all policies, evaluation log, callbacks, and counters."""
        with self._lock:
            self._policies.clear()
            self._name_index.clear()
            self._evaluation_log.clear()
            self._seq = 0
            self._callbacks.clear()
            self._stats = {k: 0 for k in self._stats}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _entry_to_dict(self, e: PolicyEntry) -> Dict:
        """Convert an internal dataclass to a plain dict."""
        return {
            "policy_id": e.policy_id,
            "name": e.name,
            "rules": list(e.rules),
            "description": e.description,
            "enabled": e.enabled,
            "created_at": e.created_at,
        }
