"""
Agent Performance Profiler — Tracks and analyzes agent execution metrics.

Provides:
- Per-agent execution timing (total, LLM calls, tool calls)
- Token usage tracking with cost estimation
- Success/failure rates and error classification
- Throughput metrics (tasks per minute, tokens per second)
- Performance anomaly detection (slow calls, token spikes)
- Historical comparison for regression detection

Usage::

    profiler = AgentProfiler()

    with profiler.profile("frontend_agent", task_id="gen-login-page"):
        result = await agent.execute(prompt)

    report = profiler.get_agent_report("frontend_agent")
    # {'avg_duration_ms': 4500, 'avg_tokens': 2000, 'success_rate': 95.0, ...}
"""

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ExecutionRecord:
    """Record of a single agent execution."""
    agent_name: str
    task_id: str
    started_at: float
    completed_at: Optional[float] = None
    duration_ms: Optional[int] = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    llm_calls: int = 0
    tool_calls: int = 0
    success: bool = True
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    cost_usd: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def finalize(self):
        """Set completed_at and calculate duration."""
        self.completed_at = time.time()
        self.duration_ms = int((self.completed_at - self.started_at) * 1000)


@dataclass
class AgentStats:
    """Aggregate statistics for an agent."""
    agent_name: str
    total_executions: int = 0
    total_successes: int = 0
    total_failures: int = 0
    total_tokens: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_llm_calls: int = 0
    total_tool_calls: int = 0
    total_cost_usd: float = 0.0
    total_duration_ms: int = 0
    min_duration_ms: Optional[int] = None
    max_duration_ms: Optional[int] = None
    errors_by_type: Dict[str, int] = field(default_factory=dict)

    # For percentile calculation
    _durations: List[int] = field(default_factory=list)
    _token_counts: List[int] = field(default_factory=list)

    @property
    def avg_duration_ms(self) -> float:
        if self.total_executions == 0:
            return 0.0
        return self.total_duration_ms / self.total_executions

    @property
    def avg_tokens(self) -> float:
        if self.total_executions == 0:
            return 0.0
        return self.total_tokens / self.total_executions

    @property
    def success_rate(self) -> float:
        if self.total_executions == 0:
            return 0.0
        return (self.total_successes / self.total_executions) * 100.0

    @property
    def tokens_per_second(self) -> float:
        if self.total_duration_ms == 0:
            return 0.0
        return self.total_tokens / (self.total_duration_ms / 1000.0)

    @property
    def tasks_per_minute(self) -> float:
        if self.total_duration_ms == 0:
            return 0.0
        minutes = self.total_duration_ms / 60000.0
        return self.total_executions / minutes

    def p50_duration_ms(self) -> Optional[int]:
        return self._percentile(self._durations, 50)

    def p95_duration_ms(self) -> Optional[int]:
        return self._percentile(self._durations, 95)

    def p99_duration_ms(self) -> Optional[int]:
        return self._percentile(self._durations, 99)

    @staticmethod
    def _percentile(data: List[int], pct: int) -> Optional[int]:
        if not data:
            return None
        sorted_data = sorted(data)
        idx = int(len(sorted_data) * pct / 100)
        idx = min(idx, len(sorted_data) - 1)
        return sorted_data[idx]

    def to_dict(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "total_executions": self.total_executions,
            "total_successes": self.total_successes,
            "total_failures": self.total_failures,
            "success_rate": round(self.success_rate, 1),
            "avg_duration_ms": round(self.avg_duration_ms, 1),
            "min_duration_ms": self.min_duration_ms,
            "max_duration_ms": self.max_duration_ms,
            "p50_duration_ms": self.p50_duration_ms(),
            "p95_duration_ms": self.p95_duration_ms(),
            "p99_duration_ms": self.p99_duration_ms(),
            "avg_tokens": round(self.avg_tokens, 1),
            "total_tokens": self.total_tokens,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_llm_calls": self.total_llm_calls,
            "total_tool_calls": self.total_tool_calls,
            "tokens_per_second": round(self.tokens_per_second, 1),
            "tasks_per_minute": round(self.tasks_per_minute, 2),
            "total_cost_usd": round(self.total_cost_usd, 4),
            "errors_by_type": self.errors_by_type,
        }


@dataclass
class AnomalyAlert:
    """Performance anomaly detected."""
    agent_name: str
    alert_type: str  # slow_execution, token_spike, high_failure_rate
    message: str
    value: float
    threshold: float
    timestamp: float = field(default_factory=time.time)


class AgentProfiler:
    """
    Profiles agent execution performance with anomaly detection.
    """

    def __init__(
        self,
        slow_threshold_multiplier: float = 3.0,
        token_spike_multiplier: float = 2.5,
        failure_rate_threshold: float = 30.0,
        max_history_per_agent: int = 1000,
    ):
        self.slow_threshold_multiplier = slow_threshold_multiplier
        self.token_spike_multiplier = token_spike_multiplier
        self.failure_rate_threshold = failure_rate_threshold
        self.max_history = max_history_per_agent

        self._stats: Dict[str, AgentStats] = {}
        self._history: Dict[str, List[ExecutionRecord]] = {}
        self._anomalies: List[AnomalyAlert] = []
        self._active_records: Dict[str, ExecutionRecord] = {}

        self.logger = logger.bind(component="agent_profiler")

    @contextmanager
    def profile(self, agent_name: str, task_id: str = "", **metadata):
        """
        Context manager to profile an agent execution.

        Usage::
            with profiler.profile("frontend", task_id="task-1"):
                result = await agent.execute(prompt)
        """
        record = ExecutionRecord(
            agent_name=agent_name,
            task_id=task_id,
            started_at=time.time(),
            metadata=metadata,
        )
        key = f"{agent_name}:{task_id}"
        self._active_records[key] = record

        try:
            yield record
        except Exception as e:
            record.success = False
            record.error_type = type(e).__name__
            record.error_message = str(e)[:500]
            raise
        finally:
            record.finalize()
            self._active_records.pop(key, None)
            self._record_execution(record)

    def record_execution(
        self,
        agent_name: str,
        task_id: str = "",
        duration_ms: int = 0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        llm_calls: int = 1,
        tool_calls: int = 0,
        success: bool = True,
        error_type: str = "",
        cost_usd: float = 0.0,
    ):
        """Record an execution directly (without context manager)."""
        record = ExecutionRecord(
            agent_name=agent_name,
            task_id=task_id,
            started_at=time.time() - (duration_ms / 1000.0),
            completed_at=time.time(),
            duration_ms=duration_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            llm_calls=llm_calls,
            tool_calls=tool_calls,
            success=success,
            error_type=error_type if not success else None,
            cost_usd=cost_usd,
        )
        self._record_execution(record)

    def _record_execution(self, record: ExecutionRecord):
        """Process and store an execution record."""
        name = record.agent_name

        # Ensure stats exist
        if name not in self._stats:
            self._stats[name] = AgentStats(agent_name=name)
        if name not in self._history:
            self._history[name] = []

        stats = self._stats[name]

        # Update aggregate stats
        stats.total_executions += 1
        if record.success:
            stats.total_successes += 1
        else:
            stats.total_failures += 1
            if record.error_type:
                stats.errors_by_type[record.error_type] = (
                    stats.errors_by_type.get(record.error_type, 0) + 1
                )

        stats.total_tokens += record.total_tokens
        stats.total_input_tokens += record.input_tokens
        stats.total_output_tokens += record.output_tokens
        stats.total_llm_calls += record.llm_calls
        stats.total_tool_calls += record.tool_calls
        stats.total_cost_usd += record.cost_usd

        if record.duration_ms is not None:
            stats.total_duration_ms += record.duration_ms
            stats._durations.append(record.duration_ms)
            stats._token_counts.append(record.total_tokens)

            if stats.min_duration_ms is None or record.duration_ms < stats.min_duration_ms:
                stats.min_duration_ms = record.duration_ms
            if stats.max_duration_ms is None or record.duration_ms > stats.max_duration_ms:
                stats.max_duration_ms = record.duration_ms

        # Store in history
        self._history[name].append(record)
        if len(self._history[name]) > self.max_history:
            self._history[name] = self._history[name][-self.max_history:]

        # Check for anomalies
        self._check_anomalies(record, stats)

    def _check_anomalies(self, record: ExecutionRecord, stats: AgentStats):
        """Detect performance anomalies."""
        name = record.agent_name

        # Slow execution detection
        if stats.total_executions > 3 and record.duration_ms is not None:
            avg = stats.avg_duration_ms
            if avg > 0 and record.duration_ms > avg * self.slow_threshold_multiplier:
                alert = AnomalyAlert(
                    agent_name=name,
                    alert_type="slow_execution",
                    message=f"{name} execution took {record.duration_ms}ms (avg: {avg:.0f}ms)",
                    value=float(record.duration_ms),
                    threshold=avg * self.slow_threshold_multiplier,
                )
                self._anomalies.append(alert)
                self.logger.warning("anomaly_detected", **alert.__dict__)

        # Token spike detection
        if stats.total_executions > 3 and record.total_tokens > 0:
            avg_tokens = stats.avg_tokens
            if avg_tokens > 0 and record.total_tokens > avg_tokens * self.token_spike_multiplier:
                alert = AnomalyAlert(
                    agent_name=name,
                    alert_type="token_spike",
                    message=f"{name} used {record.total_tokens} tokens (avg: {avg_tokens:.0f})",
                    value=float(record.total_tokens),
                    threshold=avg_tokens * self.token_spike_multiplier,
                )
                self._anomalies.append(alert)
                self.logger.warning("anomaly_detected", **alert.__dict__)

        # High failure rate detection
        if stats.total_executions >= 5:
            failure_rate = 100.0 - stats.success_rate
            if failure_rate > self.failure_rate_threshold:
                # Only alert once per 10 executions
                if stats.total_executions % 10 == 0:
                    alert = AnomalyAlert(
                        agent_name=name,
                        alert_type="high_failure_rate",
                        message=f"{name} failure rate: {failure_rate:.1f}%",
                        value=failure_rate,
                        threshold=self.failure_rate_threshold,
                    )
                    self._anomalies.append(alert)
                    self.logger.warning("anomaly_detected", **alert.__dict__)

    # ------------------------------------------------------------------
    # Reports
    # ------------------------------------------------------------------

    def get_agent_report(self, agent_name: str) -> Optional[dict]:
        """Get performance report for a specific agent."""
        stats = self._stats.get(agent_name)
        if not stats:
            return None
        return stats.to_dict()

    def get_all_reports(self) -> Dict[str, dict]:
        """Get performance reports for all agents."""
        return {name: stats.to_dict() for name, stats in self._stats.items()}

    def get_anomalies(self, agent_name: Optional[str] = None, limit: int = 50) -> List[dict]:
        """Get detected anomalies, optionally filtered by agent."""
        anomalies = self._anomalies
        if agent_name:
            anomalies = [a for a in anomalies if a.agent_name == agent_name]
        return [
            {
                "agent_name": a.agent_name,
                "alert_type": a.alert_type,
                "message": a.message,
                "value": a.value,
                "threshold": a.threshold,
                "timestamp": a.timestamp,
            }
            for a in anomalies[-limit:]
        ]

    def get_comparison(self) -> dict:
        """Compare all agents side-by-side."""
        agents = {}
        for name, stats in self._stats.items():
            agents[name] = {
                "executions": stats.total_executions,
                "success_rate": round(stats.success_rate, 1),
                "avg_duration_ms": round(stats.avg_duration_ms, 1),
                "avg_tokens": round(stats.avg_tokens, 1),
                "tokens_per_second": round(stats.tokens_per_second, 1),
                "cost_usd": round(stats.total_cost_usd, 4),
            }

        # Find best/worst performers
        if agents:
            fastest = min(agents.items(), key=lambda x: x[1]["avg_duration_ms"] or float('inf'))
            most_reliable = max(agents.items(), key=lambda x: x[1]["success_rate"])
            most_efficient = max(agents.items(), key=lambda x: x[1]["tokens_per_second"] or 0)
        else:
            fastest = most_reliable = most_efficient = (None, None)

        return {
            "agents": agents,
            "fastest_agent": fastest[0],
            "most_reliable_agent": most_reliable[0],
            "most_efficient_agent": most_efficient[0],
        }

    def get_summary(self) -> dict:
        """Get overall profiler summary."""
        total_execs = sum(s.total_executions for s in self._stats.values())
        total_tokens = sum(s.total_tokens for s in self._stats.values())
        total_cost = sum(s.total_cost_usd for s in self._stats.values())
        total_duration = sum(s.total_duration_ms for s in self._stats.values())

        return {
            "total_agents_profiled": len(self._stats),
            "total_executions": total_execs,
            "total_tokens": total_tokens,
            "total_cost_usd": round(total_cost, 4),
            "total_duration_ms": total_duration,
            "total_anomalies": len(self._anomalies),
            "agents": list(self._stats.keys()),
        }

    def get_history(self, agent_name: str, limit: int = 20) -> List[dict]:
        """Get recent execution history for an agent."""
        records = self._history.get(agent_name, [])
        return [
            {
                "task_id": r.task_id,
                "duration_ms": r.duration_ms,
                "total_tokens": r.total_tokens,
                "success": r.success,
                "error_type": r.error_type,
                "started_at": r.started_at,
            }
            for r in records[-limit:]
        ]

    def reset(self, agent_name: Optional[str] = None):
        """Reset profiler data, optionally for a specific agent."""
        if agent_name:
            self._stats.pop(agent_name, None)
            self._history.pop(agent_name, None)
            self._anomalies = [a for a in self._anomalies if a.agent_name != agent_name]
        else:
            self._stats.clear()
            self._history.clear()
            self._anomalies.clear()


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_profiler: Optional[AgentProfiler] = None


def get_agent_profiler(**kwargs) -> AgentProfiler:
    """Get or create the global agent profiler."""
    global _profiler
    if _profiler is None:
        _profiler = AgentProfiler(**kwargs)
    return _profiler
