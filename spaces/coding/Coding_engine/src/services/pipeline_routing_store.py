"""Pipeline routing store.

Manages pipeline routing rules -- defines how pipeline executions are routed
to different targets based on conditions and priority.  Supports adding,
enabling, disabling, updating, and deleting routing rules with priority-based
route resolution, callback notifications, thread-safe access, and automatic
max-entries pruning.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class RoutingRule:
    """A single pipeline routing rule definition."""

    rule_id: str = ""
    pipeline_name: str = ""
    condition: str = ""
    target: str = ""
    priority: int = 5
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0


# ---------------------------------------------------------------------------
# Pipeline Routing Store
# ---------------------------------------------------------------------------

class PipelineRoutingStore:
    """Manages pipeline routing rules with priority-based route resolution,
    enable/disable toggling, callback notifications, and thread-safe access."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._max_entries = max_entries
        self._rules: Dict[str, RoutingRule] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._lock = threading.Lock()
        self._seq: int = 0
        self._stats = {
            "total_created": 0,
            "total_deleted": 0,
            "total_updated": 0,
            "total_enabled": 0,
            "total_disabled": 0,
            "total_lookups": 0,
            "total_resolutions": 0,
            "total_resolution_misses": 0,
        }

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self, seed: str) -> str:
        """Generate a collision-free ID with prefix prs-."""
        self._seq += 1
        raw = f"{seed}:{time.time()}:{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"prs-{digest}"

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Remove oldest entries when at capacity.  Caller must hold lock."""
        if len(self._rules) < self._max_entries:
            return
        sorted_entries = sorted(
            self._rules.values(), key=lambda r: r.created_at
        )
        remove_count = len(self._rules) - self._max_entries + 1
        for entry in sorted_entries[:remove_count]:
            del self._rules[entry.rule_id]
            logger.debug("rule_pruned: %s", entry.rule_id)

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _rule_to_dict(rule: RoutingRule) -> Dict[str, Any]:
        """Convert a RoutingRule to a plain dict."""
        return {
            "rule_id": rule.rule_id,
            "pipeline_name": rule.pipeline_name,
            "condition": rule.condition,
            "target": rule.target,
            "priority": rule.priority,
            "enabled": rule.enabled,
            "metadata": dict(rule.metadata),
            "created_at": rule.created_at,
            "updated_at": rule.updated_at,
        }

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a change callback under *name*.

        If a callback with the same name already exists it is silently
        replaced.
        """
        with self._lock:
            self._callbacks[name] = callback
            logger.debug("callback_registered: %s", name)

    def remove_callback(self, name: str) -> bool:
        """Remove a registered callback.  Returns False if *name* not found."""
        with self._lock:
            if name not in self._callbacks:
                return False
            del self._callbacks[name]
            logger.debug("callback_removed: %s", name)
            return True

    def _fire(self, action: str, detail: Dict[str, Any]) -> None:
        """Invoke all registered callbacks with *action* and *detail*.

        Exceptions inside individual callbacks are logged but do not
        propagate.
        """
        with self._lock:
            cbs = list(self._callbacks.values())

        for cb in cbs:
            try:
                cb(action, detail)
            except Exception:
                logger.exception("callback_error: action=%s", action)

    # ------------------------------------------------------------------
    # add_rule
    # ------------------------------------------------------------------

    def add_rule(
        self,
        pipeline_name: str,
        condition: str,
        target: str,
        priority: int = 5,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Add a new routing rule for a pipeline.

        The rule starts in the *enabled* state.  Returns the new
        ``rule_id`` (prefixed ``prs-``).
        """
        if not pipeline_name or not condition or not target:
            logger.warning(
                "add_rule_invalid_input: pipeline_name=%s condition=%s target=%s",
                pipeline_name,
                condition,
                target,
            )
            return ""

        with self._lock:
            self._prune_if_needed()

            now = time.time()
            rule_id = self._next_id(f"{pipeline_name}:{condition}:{target}")

            rule = RoutingRule(
                rule_id=rule_id,
                pipeline_name=pipeline_name,
                condition=condition,
                target=target,
                priority=priority,
                enabled=True,
                metadata=dict(metadata) if metadata else {},
                created_at=now,
                updated_at=now,
            )

            self._rules[rule_id] = rule
            self._stats["total_created"] += 1

        logger.info(
            "rule_added: id=%s pipeline=%s target=%s priority=%d",
            rule_id,
            pipeline_name,
            target,
            priority,
        )
        self._fire("rule_added", self._rule_to_dict(rule))
        return rule_id

    # ------------------------------------------------------------------
    # get_rule
    # ------------------------------------------------------------------

    def get_rule(self, rule_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a rule by ID.  Returns ``None`` if not found."""
        with self._lock:
            self._stats["total_lookups"] += 1
            rule = self._rules.get(rule_id)
            if rule is None:
                return None
            return self._rule_to_dict(rule)

    # ------------------------------------------------------------------
    # enable_rule / disable_rule
    # ------------------------------------------------------------------

    def enable_rule(self, rule_id: str) -> bool:
        """Enable a routing rule.  Returns ``False`` if *rule_id* not found."""
        with self._lock:
            rule = self._rules.get(rule_id)
            if rule is None:
                logger.warning("enable_rule_not_found: %s", rule_id)
                return False
            if rule.enabled:
                return True
            rule.enabled = True
            rule.updated_at = time.time()
            self._stats["total_enabled"] += 1

        logger.info("rule_enabled: %s", rule_id)
        self._fire("rule_enabled", self._rule_to_dict(rule))
        return True

    def disable_rule(self, rule_id: str) -> bool:
        """Disable a routing rule.  Returns ``False`` if *rule_id* not found."""
        with self._lock:
            rule = self._rules.get(rule_id)
            if rule is None:
                logger.warning("disable_rule_not_found: %s", rule_id)
                return False
            if not rule.enabled:
                return True
            rule.enabled = False
            rule.updated_at = time.time()
            self._stats["total_disabled"] += 1

        logger.info("rule_disabled: %s", rule_id)
        self._fire("rule_disabled", self._rule_to_dict(rule))
        return True

    # ------------------------------------------------------------------
    # delete_rule
    # ------------------------------------------------------------------

    def delete_rule(self, rule_id: str) -> bool:
        """Delete a routing rule.

        Returns ``False`` if the *rule_id* is not found.
        """
        with self._lock:
            rule = self._rules.get(rule_id)
            if rule is None:
                logger.warning("delete_rule_not_found: %s", rule_id)
                return False

            del self._rules[rule_id]
            self._stats["total_deleted"] += 1
            snapshot = self._rule_to_dict(rule)

        logger.info("rule_deleted: %s", rule_id)
        self._fire("rule_deleted", snapshot)
        return True

    # ------------------------------------------------------------------
    # get_rules_for_pipeline
    # ------------------------------------------------------------------

    def get_rules_for_pipeline(
        self, pipeline_name: str
    ) -> List[Dict[str, Any]]:
        """Return all enabled rules for *pipeline_name*.

        Results are sorted by ``priority`` descending (highest priority
        first).
        """
        with self._lock:
            self._stats["total_lookups"] += 1
            results = [
                self._rule_to_dict(r)
                for r in self._rules.values()
                if r.pipeline_name == pipeline_name and r.enabled
            ]
        results.sort(key=lambda d: d["priority"], reverse=True)
        return results

    # ------------------------------------------------------------------
    # resolve_route
    # ------------------------------------------------------------------

    def resolve_route(
        self,
        pipeline_name: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Find the best matching route target for *pipeline_name*.

        Returns the ``target`` of the highest-priority enabled rule for
        the given pipeline.  When multiple rules share the same priority
        the one created earliest wins.  Returns ``None`` if no enabled
        rules exist for the pipeline.

        The *context* parameter is reserved for future condition-matching
        logic and is currently unused beyond callback notification.
        """
        with self._lock:
            self._stats["total_resolutions"] += 1

            candidates: List[RoutingRule] = [
                r
                for r in self._rules.values()
                if r.pipeline_name == pipeline_name and r.enabled
            ]

            if not candidates:
                self._stats["total_resolution_misses"] += 1
                logger.debug(
                    "resolve_route_no_match: pipeline=%s", pipeline_name
                )
                return None

            # Highest priority first; ties broken by earliest created_at.
            best = max(
                candidates,
                key=lambda r: (r.priority, -r.created_at),
            )
            target = best.target

        logger.info(
            "route_resolved: pipeline=%s target=%s rule=%s priority=%d",
            pipeline_name,
            target,
            best.rule_id,
            best.priority,
        )
        self._fire("route_resolved", {
            "pipeline_name": pipeline_name,
            "target": target,
            "rule_id": best.rule_id,
            "priority": best.priority,
            "context": dict(context) if context else None,
        })
        return target

    # ------------------------------------------------------------------
    # list_rules
    # ------------------------------------------------------------------

    def list_rules(
        self,
        pipeline_name: Optional[str] = None,
        enabled_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """List all rules, optionally filtered by pipeline and/or status.

        Results are sorted by ``created_at`` descending (newest first).
        """
        with self._lock:
            self._stats["total_lookups"] += 1
            results: List[Dict[str, Any]] = []
            for rule in self._rules.values():
                if pipeline_name is not None and rule.pipeline_name != pipeline_name:
                    continue
                if enabled_only and not rule.enabled:
                    continue
                results.append(self._rule_to_dict(rule))
        results.sort(key=lambda d: d["created_at"], reverse=True)
        return results

    # ------------------------------------------------------------------
    # update_rule
    # ------------------------------------------------------------------

    def update_rule(self, rule_id: str, **kwargs: Any) -> bool:
        """Update mutable fields of a routing rule.

        Supported keyword arguments: ``condition``, ``target``,
        ``priority``, ``metadata``.  Any unsupported keys are silently
        ignored.  Returns ``False`` if *rule_id* is not found.
        """
        allowed_fields = {"condition", "target", "priority", "metadata"}

        with self._lock:
            rule = self._rules.get(rule_id)
            if rule is None:
                logger.warning("update_rule_not_found: %s", rule_id)
                return False

            changed = False
            for key, value in kwargs.items():
                if key not in allowed_fields:
                    continue
                if key == "condition" and isinstance(value, str):
                    rule.condition = value
                    changed = True
                elif key == "target" and isinstance(value, str):
                    rule.target = value
                    changed = True
                elif key == "priority" and isinstance(value, int):
                    rule.priority = value
                    changed = True
                elif key == "metadata" and isinstance(value, dict):
                    rule.metadata = dict(value)
                    changed = True

            if changed:
                rule.updated_at = time.time()
                self._stats["total_updated"] += 1
                snapshot = self._rule_to_dict(rule)
            else:
                snapshot = self._rule_to_dict(rule)

        if changed:
            logger.info("rule_updated: %s", rule_id)
            self._fire("rule_updated", snapshot)

        return True

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics for the store."""
        with self._lock:
            enabled_count = sum(
                1 for r in self._rules.values() if r.enabled
            )
            return {
                **self._stats,
                "current_rules": len(self._rules),
                "current_enabled": enabled_count,
                "current_disabled": len(self._rules) - enabled_count,
                "current_callbacks": len(self._callbacks),
                "max_entries": self._max_entries,
            }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all rules, callbacks, and counters."""
        with self._lock:
            self._rules.clear()
            self._callbacks.clear()
            self._seq = 0
            self._stats = {k: 0 for k in self._stats}
        logger.info("pipeline_routing_store_reset")
