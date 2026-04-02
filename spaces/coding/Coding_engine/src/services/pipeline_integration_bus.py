"""Pipeline Integration Bus – orchestrates cross-module integration chains.

Connects standalone modules into coherent pipelines by routing data between
them in defined chains.  Each chain is a sequence of steps where the output
of one module feeds into the next.

Chains:
  1. Auth:      TokenManager → PermissionManager → SandboxManager
  2. Execution: LeaseManager → PoolManager → StateMachine → ResourceTracker
  3. Quality:   CircuitAnalyzer → RetryPolicy → ReputationTracker → TrustNetwork
  4. Cost:      BudgetController → TelemetryCollector → ConfigStore
  5. Release:   FeatureFlag → ABTestManager → DeploymentManager → MigrationRunner
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _ChainStep:
    name: str
    handler: Callable  # fn(context) -> context
    module_name: str


@dataclass
class _Chain:
    chain_id: str
    name: str
    steps: List[_ChainStep]
    tags: List[str]
    created_at: float
    execution_count: int
    total_duration: float
    failure_count: int


@dataclass
class _ChainEvent:
    event_id: str
    chain_name: str
    step_name: str
    action: str  # started, step_completed, step_failed, chain_completed, chain_failed
    duration: float
    timestamp: float


class PipelineIntegrationBus:
    """Orchestrates cross-module integration chains."""

    def __init__(self, max_chains: int = 100, max_history: int = 100000):
        self._chains: Dict[str, _Chain] = {}
        self._name_index: Dict[str, str] = {}  # name -> chain_id
        self._history: List[_ChainEvent] = []
        self._callbacks: Dict[str, Callable] = {}
        self._max_chains = max_chains
        self._max_history = max_history
        self._seq = 0

        # stats
        self._total_created = 0
        self._total_executions = 0
        self._total_step_executions = 0
        self._total_failures = 0

    # ------------------------------------------------------------------
    # Chain registration
    # ------------------------------------------------------------------

    def register_chain(
        self,
        name: str,
        tags: Optional[List[str]] = None,
    ) -> str:
        if not name or name in self._name_index:
            return ""
        if len(self._chains) >= self._max_chains:
            return ""

        self._seq += 1
        now = time.time()
        raw = f"{name}-{now}-{self._seq}"
        cid = "chn-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        chain = _Chain(
            chain_id=cid,
            name=name,
            steps=[],
            tags=tags or [],
            created_at=now,
            execution_count=0,
            total_duration=0.0,
            failure_count=0,
        )
        self._chains[cid] = chain
        self._name_index[name] = cid
        self._total_created += 1
        self._fire("chain_registered", {"chain_id": cid, "name": name})
        return cid

    def add_step(
        self,
        chain_name: str,
        step_name: str,
        handler: Callable,
        module_name: str = "",
    ) -> bool:
        cid = self._name_index.get(chain_name)
        if not cid or not step_name or not handler:
            return False
        chain = self._chains[cid]
        # No duplicate step names within a chain
        for s in chain.steps:
            if s.name == step_name:
                return False
        chain.steps.append(_ChainStep(
            name=step_name,
            handler=handler,
            module_name=module_name or step_name,
        ))
        return True

    def remove_chain(self, name: str) -> bool:
        cid = self._name_index.pop(name, None)
        if not cid:
            return False
        self._chains.pop(cid, None)
        return True

    def get_chain(self, name: str) -> Optional[Dict[str, Any]]:
        cid = self._name_index.get(name)
        if not cid:
            return None
        c = self._chains[cid]
        avg_duration = (c.total_duration / c.execution_count) if c.execution_count > 0 else 0.0
        return {
            "chain_id": c.chain_id,
            "name": c.name,
            "steps": [{"name": s.name, "module": s.module_name} for s in c.steps],
            "step_count": len(c.steps),
            "execution_count": c.execution_count,
            "total_duration": c.total_duration,
            "avg_duration": avg_duration,
            "failure_count": c.failure_count,
            "tags": list(c.tags),
            "created_at": c.created_at,
        }

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def execute(self, chain_name: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute a chain, passing context through each step sequentially.

        Returns {success, steps_completed, context, error, duration}.
        """
        cid = self._name_index.get(chain_name)
        if not cid:
            return {"success": False, "error": "chain_not_found", "steps_completed": 0}

        chain = self._chains[cid]
        if not chain.steps:
            return {"success": False, "error": "chain_empty", "steps_completed": 0}

        ctx = dict(context or {})
        ctx["_chain"] = chain_name
        ctx["_started_at"] = time.time()

        chain_start = time.time()
        steps_completed = 0

        self._fire("chain_started", {"chain": chain_name, "steps": len(chain.steps)})

        for step in chain.steps:
            step_start = time.time()
            try:
                ctx = step.handler(ctx)
                if ctx is None:
                    ctx = {}
                step_duration = time.time() - step_start
                steps_completed += 1
                self._total_step_executions += 1
                self._record_event(chain_name, step.name, "step_completed", step_duration)
                self._fire("step_completed", {
                    "chain": chain_name, "step": step.name,
                    "duration": step_duration, "steps_completed": steps_completed,
                })
            except Exception as exc:
                step_duration = time.time() - step_start
                chain_duration = time.time() - chain_start
                chain.failure_count += 1
                self._total_failures += 1
                self._record_event(chain_name, step.name, "step_failed", step_duration)
                self._fire("chain_failed", {
                    "chain": chain_name, "step": step.name,
                    "error": str(exc), "steps_completed": steps_completed,
                })

                chain.execution_count += 1
                chain.total_duration += chain_duration
                self._total_executions += 1

                return {
                    "success": False,
                    "steps_completed": steps_completed,
                    "failed_step": step.name,
                    "error": str(exc),
                    "context": ctx,
                    "duration": chain_duration,
                }

        chain_duration = time.time() - chain_start
        chain.execution_count += 1
        chain.total_duration += chain_duration
        self._total_executions += 1

        self._record_event(chain_name, "", "chain_completed", chain_duration)
        self._fire("chain_completed", {
            "chain": chain_name, "steps_completed": steps_completed,
            "duration": chain_duration,
        })

        return {
            "success": True,
            "steps_completed": steps_completed,
            "context": ctx,
            "duration": chain_duration,
        }

    def execute_step(self, chain_name: str, step_name: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute a single step from a chain."""
        cid = self._name_index.get(chain_name)
        if not cid:
            return {"success": False, "error": "chain_not_found"}
        chain = self._chains[cid]

        step = None
        for s in chain.steps:
            if s.name == step_name:
                step = s
                break
        if not step:
            return {"success": False, "error": "step_not_found"}

        ctx = dict(context or {})
        start = time.time()
        try:
            result_ctx = step.handler(ctx)
            duration = time.time() - start
            self._total_step_executions += 1
            self._record_event(chain_name, step_name, "step_completed", duration)
            return {"success": True, "context": result_ctx or {}, "duration": duration}
        except Exception as exc:
            duration = time.time() - start
            self._total_failures += 1
            self._record_event(chain_name, step_name, "step_failed", duration)
            return {"success": False, "error": str(exc), "duration": duration}

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list_chains(self, tag: str = "") -> List[Dict[str, Any]]:
        results = []
        for c in self._chains.values():
            if tag and tag not in c.tags:
                continue
            results.append(self.get_chain(c.name))
        return results

    def get_chain_names(self) -> List[str]:
        return sorted(self._name_index.keys())

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def get_history(
        self,
        chain_name: str = "",
        action: str = "",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        results = []
        for ev in reversed(self._history):
            if chain_name and ev.chain_name != chain_name:
                continue
            if action and ev.action != action:
                continue
            results.append({
                "event_id": ev.event_id,
                "chain_name": ev.chain_name,
                "step_name": ev.step_name,
                "action": ev.action,
                "duration": ev.duration,
                "timestamp": ev.timestamp,
            })
            if len(results) >= limit:
                break
        return results

    def _record_event(self, chain_name: str, step_name: str, action: str, duration: float) -> None:
        self._seq += 1
        now = time.time()
        raw = f"{chain_name}-{step_name}-{action}-{now}-{self._seq}"
        evid = "ibe-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        event = _ChainEvent(
            event_id=evid, chain_name=chain_name, step_name=step_name,
            action=action, duration=duration, timestamp=now,
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
            "total_chains": len(self._chains),
            "total_created": self._total_created,
            "total_executions": self._total_executions,
            "total_step_executions": self._total_step_executions,
            "total_failures": self._total_failures,
            "history_size": len(self._history),
        }

    def reset(self) -> None:
        self._chains.clear()
        self._name_index.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_created = 0
        self._total_executions = 0
        self._total_step_executions = 0
        self._total_failures = 0
