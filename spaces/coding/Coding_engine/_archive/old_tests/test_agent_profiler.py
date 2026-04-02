"""Test agent performance profiler."""
import asyncio
import sys
import time
sys.path.insert(0, ".")

from src.services.agent_profiler import (
    AgentProfiler,
    AgentStats,
    ExecutionRecord,
    AnomalyAlert,
    get_agent_profiler,
)


async def test_record_execution():
    """Basic execution recording."""
    profiler = AgentProfiler()
    profiler.record_execution(
        agent_name="frontend",
        task_id="t1",
        duration_ms=5000,
        input_tokens=1000,
        output_tokens=2000,
        llm_calls=2,
        tool_calls=3,
        success=True,
        cost_usd=0.027,
    )

    report = profiler.get_agent_report("frontend")
    assert report is not None
    assert report["total_executions"] == 1
    assert report["total_successes"] == 1
    assert report["total_tokens"] == 3000
    assert report["total_llm_calls"] == 2
    assert report["total_tool_calls"] == 3
    assert report["avg_duration_ms"] == 5000.0
    assert report["success_rate"] == 100.0
    print("OK: record execution")


async def test_context_manager_success():
    """Context manager profiles successful execution."""
    profiler = AgentProfiler()

    with profiler.profile("backend", task_id="gen-api") as record:
        time.sleep(0.05)  # Simulate work
        record.total_tokens = 1500
        record.llm_calls = 1

    report = profiler.get_agent_report("backend")
    assert report["total_executions"] == 1
    assert report["total_successes"] == 1
    assert report["avg_duration_ms"] >= 40  # At least 40ms
    assert report["total_tokens"] == 1500
    print("OK: context manager success")


async def test_context_manager_failure():
    """Context manager captures errors."""
    profiler = AgentProfiler()

    try:
        with profiler.profile("testing", task_id="run-tests") as record:
            record.total_tokens = 500
            raise ValueError("test failed")
    except ValueError:
        pass

    report = profiler.get_agent_report("testing")
    assert report["total_executions"] == 1
    assert report["total_failures"] == 1
    assert report["success_rate"] == 0.0
    assert report["errors_by_type"]["ValueError"] == 1
    print("OK: context manager failure")


async def test_multiple_executions():
    """Multiple executions aggregate correctly."""
    profiler = AgentProfiler()

    for i in range(5):
        profiler.record_execution(
            agent_name="frontend",
            duration_ms=1000 * (i + 1),
            input_tokens=100 * (i + 1),
            output_tokens=200 * (i + 1),
            success=i < 4,  # Last one fails
            error_type="TimeoutError" if i == 4 else "",
        )

    report = profiler.get_agent_report("frontend")
    assert report["total_executions"] == 5
    assert report["total_successes"] == 4
    assert report["total_failures"] == 1
    assert report["success_rate"] == 80.0
    assert report["min_duration_ms"] == 1000
    assert report["max_duration_ms"] == 5000
    assert report["avg_duration_ms"] == 3000.0
    assert report["total_tokens"] == sum(300 * (i + 1) for i in range(5))
    print("OK: multiple executions")


async def test_percentiles():
    """P50/P95/P99 durations calculated correctly."""
    profiler = AgentProfiler()

    # Record 100 executions with durations 1-100ms
    for i in range(1, 101):
        profiler.record_execution(
            agent_name="metrics_test",
            duration_ms=i * 10,
        )

    report = profiler.get_agent_report("metrics_test")
    p50 = report["p50_duration_ms"]
    p95 = report["p95_duration_ms"]
    p99 = report["p99_duration_ms"]

    assert p50 is not None
    assert p95 is not None
    assert p99 is not None
    assert p50 < p95 < p99
    # P50 should be around 500ms (50th of 10..1000)
    assert 400 <= p50 <= 600
    # P95 should be around 950ms
    assert 900 <= p95 <= 1000
    print("OK: percentiles")


async def test_anomaly_slow_execution():
    """Slow execution anomaly detected."""
    profiler = AgentProfiler(slow_threshold_multiplier=2.0)

    # Build baseline: 4 normal executions at ~100ms
    for _ in range(4):
        profiler.record_execution(agent_name="slow_test", duration_ms=100)

    # Now a very slow one (500ms > 2x * 100ms average)
    profiler.record_execution(agent_name="slow_test", duration_ms=500)

    anomalies = profiler.get_anomalies(agent_name="slow_test")
    assert len(anomalies) >= 1
    slow_alerts = [a for a in anomalies if a["alert_type"] == "slow_execution"]
    assert len(slow_alerts) >= 1
    assert slow_alerts[0]["value"] == 500.0
    print("OK: slow execution anomaly")


async def test_anomaly_token_spike():
    """Token spike anomaly detected."""
    profiler = AgentProfiler(token_spike_multiplier=2.0)

    # Build baseline: 4 normal at ~100 tokens
    for _ in range(4):
        profiler.record_execution(
            agent_name="spike_test",
            duration_ms=100,
            input_tokens=50,
            output_tokens=50,
        )

    # Spike: 500 tokens > 2x * 100 avg
    profiler.record_execution(
        agent_name="spike_test",
        duration_ms=100,
        input_tokens=250,
        output_tokens=250,
    )

    anomalies = profiler.get_anomalies(agent_name="spike_test")
    token_alerts = [a for a in anomalies if a["alert_type"] == "token_spike"]
    assert len(token_alerts) >= 1
    print("OK: token spike anomaly")


async def test_comparison():
    """Agent comparison report works."""
    profiler = AgentProfiler()

    profiler.record_execution("fast_agent", duration_ms=100, input_tokens=50, output_tokens=50)
    profiler.record_execution("slow_agent", duration_ms=5000, input_tokens=500, output_tokens=500)
    profiler.record_execution("reliable_agent", duration_ms=200, input_tokens=100, output_tokens=100)

    comp = profiler.get_comparison()
    assert len(comp["agents"]) == 3
    assert comp["fastest_agent"] == "fast_agent"
    assert comp["most_reliable_agent"] is not None
    print("OK: agent comparison")


async def test_summary():
    """Global summary is correct."""
    profiler = AgentProfiler()

    profiler.record_execution("a1", duration_ms=100, input_tokens=50, output_tokens=50, cost_usd=0.001)
    profiler.record_execution("a2", duration_ms=200, input_tokens=100, output_tokens=100, cost_usd=0.002)

    summary = profiler.get_summary()
    assert summary["total_agents_profiled"] == 2
    assert summary["total_executions"] == 2
    assert summary["total_tokens"] == 300
    assert summary["total_cost_usd"] == 0.003
    assert set(summary["agents"]) == {"a1", "a2"}
    print("OK: summary")


async def test_history():
    """Execution history is stored and retrievable."""
    profiler = AgentProfiler()

    for i in range(5):
        profiler.record_execution("hist_agent", task_id=f"t{i}", duration_ms=100 * i)

    history = profiler.get_history("hist_agent", limit=3)
    assert len(history) == 3
    assert history[-1]["task_id"] == "t4"
    assert history[0]["task_id"] == "t2"
    print("OK: history")


async def test_history_max_limit():
    """History respects max_history per agent."""
    profiler = AgentProfiler(max_history_per_agent=5)

    for i in range(10):
        profiler.record_execution("limited", task_id=f"t{i}", duration_ms=100)

    history = profiler.get_history("limited", limit=100)
    assert len(history) == 5
    assert history[0]["task_id"] == "t5"  # Oldest kept
    assert history[-1]["task_id"] == "t9"  # Most recent
    print("OK: history max limit")


async def test_reset_specific_agent():
    """Reset clears data for specific agent only."""
    profiler = AgentProfiler()

    profiler.record_execution("keep_me", duration_ms=100)
    profiler.record_execution("delete_me", duration_ms=200)

    profiler.reset(agent_name="delete_me")

    assert profiler.get_agent_report("keep_me") is not None
    assert profiler.get_agent_report("delete_me") is None
    print("OK: reset specific agent")


async def test_reset_all():
    """Reset all clears everything."""
    profiler = AgentProfiler()

    profiler.record_execution("a1", duration_ms=100)
    profiler.record_execution("a2", duration_ms=200)

    profiler.reset()

    assert profiler.get_all_reports() == {}
    assert profiler.get_anomalies() == []
    print("OK: reset all")


async def test_tokens_per_second():
    """Tokens per second metric."""
    profiler = AgentProfiler()
    # 1000 tokens in 2000ms = 500 tokens/sec
    profiler.record_execution("tps", duration_ms=2000, input_tokens=500, output_tokens=500)

    report = profiler.get_agent_report("tps")
    assert abs(report["tokens_per_second"] - 500.0) < 1.0
    print("OK: tokens per second")


async def test_tasks_per_minute():
    """Tasks per minute metric."""
    profiler = AgentProfiler()
    # 6 tasks, each 10 seconds = 10 tasks per minute
    # Actually: total 60000ms = 1 minute, 6 tasks = 6 tasks/min
    for _ in range(6):
        profiler.record_execution("tpm", duration_ms=10000)

    report = profiler.get_agent_report("tpm")
    assert abs(report["tasks_per_minute"] - 6.0) < 0.1
    print("OK: tasks per minute")


async def test_singleton():
    """get_agent_profiler returns singleton."""
    import src.services.agent_profiler as mod
    mod._profiler = None

    p1 = get_agent_profiler()
    p2 = get_agent_profiler()
    assert p1 is p2

    mod._profiler = None  # Cleanup
    print("OK: singleton")


async def test_no_report_for_unknown():
    """get_agent_report returns None for unknown agent."""
    profiler = AgentProfiler()
    assert profiler.get_agent_report("nonexistent") is None
    print("OK: no report for unknown")


async def test_execution_record_finalize():
    """ExecutionRecord.finalize sets completed_at and duration."""
    record = ExecutionRecord(agent_name="test", task_id="t1", started_at=time.time() - 1.0)
    record.finalize()
    assert record.completed_at is not None
    assert record.duration_ms is not None
    assert record.duration_ms >= 900  # At least ~1s
    print("OK: execution record finalize")


async def main():
    print("=== Agent Profiler Tests ===\n")
    await test_record_execution()
    await test_context_manager_success()
    await test_context_manager_failure()
    await test_multiple_executions()
    await test_percentiles()
    await test_anomaly_slow_execution()
    await test_anomaly_token_spike()
    await test_comparison()
    await test_summary()
    await test_history()
    await test_history_max_limit()
    await test_reset_specific_agent()
    await test_reset_all()
    await test_tokens_per_second()
    await test_tasks_per_minute()
    await test_singleton()
    await test_no_report_for_unknown()
    await test_execution_record_finalize()
    print("\n=== ALL 18 TESTS PASSED ===")


if __name__ == "__main__":
    asyncio.run(main())
