"""
Pipeline Hooks — Event-driven extension points for custom pipeline behavior.

Provides:
- Hook registration at defined pipeline lifecycle points
- Before/after hooks for phases, steps, agents, and events
- Hook priorities and ordering
- Conditional hooks (only fire when conditions match)
- Hook chains with short-circuit on failure
- Async-compatible hook execution
- Hook stats and debugging

Usage:
    hooks = PipelineHookManager()

    # Register a hook
    hooks.register("before_phase", "log_start",
        callback=lambda ctx: print(f"Starting {ctx['phase']}"),
        priority=10,
    )

    # Fire hooks at a lifecycle point
    results = hooks.fire("before_phase", {"phase": "planning"})
"""

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

import structlog

logger = structlog.get_logger(__name__)


class HookPoint(str, Enum):
    """Standard pipeline lifecycle hook points."""
    BEFORE_PIPELINE = "before_pipeline"
    AFTER_PIPELINE = "after_pipeline"
    BEFORE_PHASE = "before_phase"
    AFTER_PHASE = "after_phase"
    BEFORE_STEP = "before_step"
    AFTER_STEP = "after_step"
    BEFORE_AGENT = "before_agent"
    AFTER_AGENT = "after_agent"
    ON_ERROR = "on_error"
    ON_RETRY = "on_retry"
    ON_ROLLBACK = "on_rollback"
    ON_CHECKPOINT = "on_checkpoint"
    CUSTOM = "custom"


@dataclass
class HookRegistration:
    """A registered hook."""
    hook_id: str
    hook_point: str
    name: str
    callback: Callable
    priority: int = 50          # Lower = runs first
    enabled: bool = True
    condition: Optional[Callable] = None  # Optional guard
    tags: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    # Runtime stats
    invocations: int = 0
    successes: int = 0
    failures: int = 0
    total_duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        avg_ms = (
            self.total_duration_ms / self.invocations
            if self.invocations > 0 else 0.0
        )
        return {
            "hook_id": self.hook_id,
            "hook_point": self.hook_point,
            "name": self.name,
            "priority": self.priority,
            "enabled": self.enabled,
            "tags": sorted(self.tags),
            "invocations": self.invocations,
            "successes": self.successes,
            "failures": self.failures,
            "avg_duration_ms": round(avg_ms, 2),
        }


@dataclass
class HookResult:
    """Result from firing a single hook."""
    hook_id: str
    name: str
    success: bool
    result: Any = None
    error: str = ""
    duration_ms: float = 0.0
    skipped: bool = False


class PipelineHookManager:
    """Manages event-driven hooks for pipeline lifecycle points."""

    def __init__(self):
        # hook_point -> [HookRegistration]
        self._hooks: Dict[str, List[HookRegistration]] = {}

        # Stats
        self._total_registered = 0
        self._total_fired = 0
        self._total_invocations = 0
        self._total_errors = 0

    # ── Registration ─────────────────────────────────────────────────

    def register(
        self,
        hook_point: str,
        name: str,
        callback: Callable,
        priority: int = 50,
        condition: Optional[Callable] = None,
        tags: Optional[Set[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Register a hook at a lifecycle point."""
        hook_id = f"hook-{uuid.uuid4().hex[:8]}"

        registration = HookRegistration(
            hook_id=hook_id,
            hook_point=hook_point,
            name=name,
            callback=callback,
            priority=priority,
            condition=condition,
            tags=set(tags) if tags else set(),
            metadata=metadata or {},
        )

        if hook_point not in self._hooks:
            self._hooks[hook_point] = []
        self._hooks[hook_point].append(registration)
        self._total_registered += 1

        # Keep sorted by priority
        self._hooks[hook_point].sort(key=lambda h: h.priority)

        logger.debug(
            "hook_registered",
            component="pipeline_hooks",
            hook_point=hook_point,
            name=name,
            priority=priority,
            hook_id=hook_id,
        )

        return hook_id

    def unregister(self, hook_id: str) -> bool:
        """Remove a hook by ID."""
        for point, hooks in self._hooks.items():
            for i, h in enumerate(hooks):
                if h.hook_id == hook_id:
                    hooks.pop(i)
                    return True
        return False

    def enable(self, hook_id: str) -> bool:
        """Enable a hook."""
        hook = self._find_hook(hook_id)
        if hook:
            hook.enabled = True
            return True
        return False

    def disable(self, hook_id: str) -> bool:
        """Disable a hook."""
        hook = self._find_hook(hook_id)
        if hook:
            hook.enabled = False
            return True
        return False

    # ── Firing ───────────────────────────────────────────────────────

    def fire(
        self,
        hook_point: str,
        context: Optional[Dict[str, Any]] = None,
        stop_on_failure: bool = False,
    ) -> List[HookResult]:
        """Fire all hooks at a lifecycle point."""
        self._total_fired += 1
        hooks = self._hooks.get(hook_point, [])
        ctx = context or {}

        results = []
        for hook in hooks:
            if not hook.enabled:
                results.append(HookResult(
                    hook_id=hook.hook_id,
                    name=hook.name,
                    success=True,
                    skipped=True,
                ))
                continue

            # Check condition
            if hook.condition:
                try:
                    if not hook.condition(ctx):
                        results.append(HookResult(
                            hook_id=hook.hook_id,
                            name=hook.name,
                            success=True,
                            skipped=True,
                        ))
                        continue
                except Exception:
                    results.append(HookResult(
                        hook_id=hook.hook_id,
                        name=hook.name,
                        success=True,
                        skipped=True,
                    ))
                    continue

            # Execute hook
            start = time.time()
            hook.invocations += 1
            self._total_invocations += 1

            try:
                result = hook.callback(ctx)
                duration_ms = (time.time() - start) * 1000
                hook.successes += 1
                hook.total_duration_ms += duration_ms

                results.append(HookResult(
                    hook_id=hook.hook_id,
                    name=hook.name,
                    success=True,
                    result=result,
                    duration_ms=round(duration_ms, 2),
                ))

            except Exception as e:
                duration_ms = (time.time() - start) * 1000
                hook.failures += 1
                hook.total_duration_ms += duration_ms
                self._total_errors += 1

                results.append(HookResult(
                    hook_id=hook.hook_id,
                    name=hook.name,
                    success=False,
                    error=str(e),
                    duration_ms=round(duration_ms, 2),
                ))

                if stop_on_failure:
                    break

        return results

    def fire_and_collect(
        self,
        hook_point: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Fire hooks and return a summary."""
        results = self.fire(hook_point, context)

        executed = [r for r in results if not r.skipped]
        failed = [r for r in executed if not r.success]

        return {
            "hook_point": hook_point,
            "total_hooks": len(results),
            "executed": len(executed),
            "skipped": len(results) - len(executed),
            "succeeded": len(executed) - len(failed),
            "failed": len(failed),
            "errors": [{"name": r.name, "error": r.error} for r in failed],
            "results": [
                {"name": r.name, "result": r.result}
                for r in executed if r.success
            ],
        }

    # ── Queries ──────────────────────────────────────────────────────

    def list_hooks(
        self,
        hook_point: Optional[str] = None,
        tags: Optional[Set[str]] = None,
    ) -> List[Dict[str, Any]]:
        """List registered hooks."""
        results = []
        points = (
            {hook_point: self._hooks.get(hook_point, [])}
            if hook_point
            else self._hooks
        )

        for hooks in points.values():
            for h in hooks:
                if tags and not tags.issubset(h.tags):
                    continue
                results.append(h.to_dict())

        return results

    def get_hook(self, hook_id: str) -> Optional[Dict[str, Any]]:
        """Get hook details by ID."""
        hook = self._find_hook(hook_id)
        return hook.to_dict() if hook else None

    def list_hook_points(self) -> List[str]:
        """List all hook points that have registered hooks."""
        return sorted(self._hooks.keys())

    def get_hook_count(self, hook_point: str) -> int:
        """Get number of hooks registered at a point."""
        return len(self._hooks.get(hook_point, []))

    # ── Stats ────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Get hook manager statistics."""
        total_hooks = sum(len(h) for h in self._hooks.values())
        return {
            "total_hooks": total_hooks,
            "total_registered": self._total_registered,
            "total_fired": self._total_fired,
            "total_invocations": self._total_invocations,
            "total_errors": self._total_errors,
            "hook_points": len(self._hooks),
            "hooks_per_point": {
                point: len(hooks)
                for point, hooks in self._hooks.items()
            },
        }

    def reset(self):
        """Reset all hooks."""
        self._hooks.clear()
        self._total_registered = 0
        self._total_fired = 0
        self._total_invocations = 0
        self._total_errors = 0

    # ── Internal ─────────────────────────────────────────────────────

    def _find_hook(self, hook_id: str) -> Optional[HookRegistration]:
        """Find a hook by ID across all points."""
        for hooks in self._hooks.values():
            for h in hooks:
                if h.hook_id == hook_id:
                    return h
        return None
