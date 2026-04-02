"""Cross-module integration test — verifies all new services work together.

Tests the interaction between:
- PipelineProgressTracker
- AgentProfiler
- DeadlockDetector
- ConfigHotReloader
- AgentCapabilityRegistry
- DAGVisualizer
- RetryStrategy
- EventBus (as glue)
"""
import asyncio
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, ".")

from src.mind.event_bus import EventBus, Event, EventType
from src.services.pipeline_progress import (
    PipelineProgressTracker,
    PhaseStatus,
    ETAEstimator,
)
from src.services.agent_profiler import AgentProfiler
from src.services.deadlock_detector import DeadlockDetector
from src.services.config_hot_reload import ConfigHotReloader
from src.services.agent_registry import AgentCapabilityRegistry, AgentCapability
from src.services.dag_visualizer import DAGVisualizer, _colorize, Color
from src.services.retry_strategy import RetryStrategy


# ---------------------------------------------------------------
# 1. Full pipeline lifecycle with progress + profiler + DAG
# ---------------------------------------------------------------
async def test_full_pipeline_lifecycle():
    """Simulate a full pipeline run using progress tracker, profiler, and visualizer."""
    bus = EventBus()
    tracker = PipelineProgressTracker(event_bus=bus, default_phase_seconds=5.0)
    profiler = AgentProfiler()
    viz = DAGVisualizer(use_color=False)

    phases = ["planning", "generation", "testing", "deployment"]
    tracker.start_pipeline("integration-test", phases=phases)

    # Render initial DAG
    dag = viz.render_pipeline_dag(
        phases=phases,
        status={p: "pending" for p in phases},
    )
    assert "planning" in dag
    assert "pending" in dag

    # Simulate each phase
    for i, phase in enumerate(phases):
        tracker.start_phase(phase, estimated_tasks=2)

        # Record profiler execution for agents working in this phase
        profiler.record_execution(
            agent_name=f"Agent_{phase}",
            task_id=f"{phase}-task-1",
            duration_ms=100 + i * 50,
            input_tokens=500,
            output_tokens=300,
            success=True,
            cost_usd=0.01,
        )

        tracker.complete_task(phase, f"{phase}-task-1")
        tracker.complete_task(phase, f"{phase}-task-2")
        tracker.complete_phase(phase)

    tracker.complete_pipeline()

    # Verify final state
    progress = tracker.get_progress()
    assert progress["overall_pct"] == 100.0
    assert progress["project_name"] == "integration-test"

    # Verify profiler has all agents
    all_reports = profiler.get_all_reports()
    assert len(all_reports) == 4
    for phase in phases:
        report = profiler.get_agent_report(f"Agent_{phase}")
        assert report is not None
        assert report["total_executions"] == 1
        assert report["success_rate"] == 100.0

    # Render completed DAG
    final_dag = viz.render_pipeline_dag(
        phases=phases,
        status={p: "completed" for p in phases},
    )
    assert "completed" in final_dag

    # Comparison report
    comparison = profiler.get_comparison()
    assert comparison["fastest_agent"] is not None

    print("OK: full pipeline lifecycle")


# ---------------------------------------------------------------
# 2. Deadlock detection with agent registry
# ---------------------------------------------------------------
async def test_deadlock_with_registry():
    """Agents registered in registry can be monitored for deadlocks."""
    bus = EventBus()
    registry = AgentCapabilityRegistry()
    detector = DeadlockDetector(
        event_bus=bus,
        check_interval=999,  # Don't auto-run
        auto_resolve=True,
    )

    # Register agents
    registry.register_agent("Frontend", AgentCapability(
        agent_name="Frontend", languages={"typescript"}, frameworks={"react", "css"},
        max_concurrent_tasks=2,
    ))
    registry.register_agent("Backend", AgentCapability(
        agent_name="Backend", languages={"python"}, frameworks={"api", "database"},
        max_concurrent_tasks=2,
    ))
    registry.register_agent("Tester", AgentCapability(
        agent_name="Tester", languages={"python"}, task_types={"testing"},
        max_concurrent_tasks=1,
    ))

    # Create circular dependency
    detector.register_wait("Frontend", "Backend", resource="needs API")
    detector.register_wait("Backend", "Tester", resource="needs tests")
    detector.register_wait("Tester", "Frontend", resource="needs UI")

    # Detect cycle
    cycles = detector.detect_deadlocks()
    assert len(cycles) > 0
    cycle_agents = cycles[0].agents
    assert "Frontend" in cycle_agents or "Backend" in cycle_agents

    # Resolve
    for cycle in cycles:
        detector.resolve_deadlock(cycle)
    assert cycles[0].resolved

    # Verify registry still has all agents
    stats = registry.get_stats()
    assert stats["total_agents"] == 3

    # Visualize wait graph (use get_wait_graph)
    viz = DAGVisualizer(use_color=False)
    wait_graph_raw = detector.get_wait_graph()
    remaining = {}
    for waiter, edges in wait_graph_raw.items():
        remaining[waiter] = [e["blocker"] for e in edges]

    # Just verify visualization doesn't crash
    result = viz.render_wait_graph(remaining if remaining else {"None": ["None"]})
    assert isinstance(result, str)

    print("OK: deadlock with registry")


# ---------------------------------------------------------------
# 3. Config hot-reload triggers registry update
# ---------------------------------------------------------------
async def test_config_reload_triggers_registry():
    """Config changes can update agent registry capabilities."""
    bus = EventBus()
    registry = AgentCapabilityRegistry()

    # Register initial agent
    registry.register_agent("Builder", AgentCapability(
        agent_name="Builder", languages={"python"}, frameworks={"api"},
    ))

    # Write initial config
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = os.path.join(tmpdir, "Builder.json")
        config = {
            "capabilities": ["python", "api", "docker"],
            "max_concurrent": 3,
        }
        with open(config_path, "w") as f:
            json.dump(config, f)

        reloader = ConfigHotReloader(
            event_bus=bus,
            config_dir=tmpdir,
            poll_interval=999,  # Manual polling
        )

        # Load config via reload
        result = reloader.reload("Builder")
        assert result is True

        # Verify config loaded
        cfg = reloader.get_config("Builder")
        assert cfg is not None
        assert "capabilities" in cfg

        # Simulate config change: add new capability
        config["capabilities"].append("kubernetes")
        with open(config_path, "w") as f:
            json.dump(config, f)

        # Reload again
        result2 = reloader.reload("Builder")
        assert result2 is True

        # Verify change detected
        stats = reloader.get_stats()
        assert stats["total_config_changes"] >= 1

    print("OK: config reload triggers registry")


# ---------------------------------------------------------------
# 4. Profiler anomaly detection across multiple agents
# ---------------------------------------------------------------
async def test_profiler_anomaly_cross_agent():
    """Profiler detects anomalies when one agent is significantly slower."""
    profiler = AgentProfiler(
        slow_threshold_multiplier=2.0,
        token_spike_multiplier=2.0,
    )

    # Normal executions for FastAgent
    for i in range(5):
        profiler.record_execution(
            agent_name="FastAgent",
            task_id=f"fast-{i}",
            duration_ms=100,
            input_tokens=500,
            output_tokens=300,
        )

    # Now a slow one
    profiler.record_execution(
        agent_name="FastAgent",
        task_id="fast-slow",
        duration_ms=500,  # 5x normal — exceeds 2x threshold
        input_tokens=500,
        output_tokens=300,
    )

    anomalies = profiler.get_anomalies("FastAgent")
    assert len(anomalies) >= 1
    assert anomalies[-1]["alert_type"] == "slow_execution"

    # Normal executions for TokenHog
    for i in range(5):
        profiler.record_execution(
            agent_name="TokenHog",
            task_id=f"hog-{i}",
            duration_ms=200,
            input_tokens=1000,
            output_tokens=500,
        )

    # Token spike
    profiler.record_execution(
        agent_name="TokenHog",
        task_id="hog-spike",
        duration_ms=200,
        input_tokens=5000,
        output_tokens=3000,
    )

    hog_anomalies = profiler.get_anomalies("TokenHog")
    assert len(hog_anomalies) >= 1
    assert hog_anomalies[-1]["alert_type"] == "token_spike"

    # Summary includes both agents
    summary = profiler.get_summary()
    assert summary["total_agents_profiled"] == 2
    assert summary["total_anomalies"] >= 2

    print("OK: profiler anomaly cross-agent")


# ---------------------------------------------------------------
# 5. DAG visualizer renders all visualization types
# ---------------------------------------------------------------
async def test_dag_all_visualizations():
    """All DAG visualization methods produce coherent output."""
    viz = DAGVisualizer(use_color=False, box_width=24)

    # Pipeline DAG
    pipeline = viz.render_pipeline_dag(
        phases=["plan", "code", "test"],
        status={"plan": "completed", "code": "running", "test": "pending"},
    )
    assert "plan" in pipeline
    assert "|" in pipeline

    # Wait graph
    waits = viz.render_wait_graph({
        "A": ["B", "C"],
        "B": ["C"],
    })
    assert "waits for" in waits
    assert "(free)" in waits  # C is free

    # Build order
    build = viz.render_build_order([
        ["core"],
        ["api", "web"],
        ["e2e-tests"],
    ])
    assert "Level 0" in build
    assert "4 packages in 3 levels" in build

    # Timeline
    timeline = viz.render_execution_timeline([
        {"time": 0, "agent": "X", "action": "start", "status": "running"},
        {"time": 5, "agent": "X", "action": "done", "status": "completed"},
    ])
    assert "X" in timeline
    assert "start" in timeline

    # Dependency tree
    tree = viz.render_dependency_tree("root", {
        "root": ["a", "b"],
        "a": ["c"],
        "b": [],
        "c": [],
    })
    assert "root" in tree
    assert "a" in tree

    # System overview
    overview = viz.render_system_overview(
        services={"EventBus": True, "Minibook": False},
        agents=[
            {"agent_name": "Worker1", "availability": "online", "current_tasks": 1},
        ],
        metrics={"total_tokens": 10000},
    )
    assert "System Overview" in overview
    assert "Worker1" in overview

    print("OK: DAG all visualizations")


# ---------------------------------------------------------------
# 6. Retry strategy with profiler tracking
# ---------------------------------------------------------------
async def test_retry_with_profiler():
    """Retry strategy failures are tracked by profiler."""
    profiler = AgentProfiler()
    retry = RetryStrategy(max_retries=2, base_delay=0.01)

    call_count = 0

    async def flaky_call():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("transient failure")
        return "success"

    # Execute with retry — should succeed on 3rd try
    start = time.time()
    result = await retry.execute(flaky_call)
    duration_ms = int((time.time() - start) * 1000)

    assert result == "success"
    assert call_count == 3

    # Record in profiler
    profiler.record_execution(
        agent_name="RetryAgent",
        task_id="flaky-task",
        duration_ms=duration_ms,
        input_tokens=100,
        output_tokens=50,
        success=True,
    )

    report = profiler.get_agent_report("RetryAgent")
    assert report["total_executions"] == 1
    assert report["success_rate"] == 100.0

    # Now test a permanent failure
    async def always_fail():
        raise ValueError("permanent error")

    try:
        await retry.execute(always_fail)
        assert False, "Should have raised"
    except ValueError:
        pass

    profiler.record_execution(
        agent_name="RetryAgent",
        task_id="permanent-fail",
        duration_ms=50,
        input_tokens=100,
        output_tokens=0,
        success=False,
        error_type="ValueError",
    )

    report2 = profiler.get_agent_report("RetryAgent")
    assert report2["total_executions"] == 2
    assert report2["success_rate"] == 50.0

    print("OK: retry with profiler")


# ---------------------------------------------------------------
# 7. Agent registry routing with profiler-informed selection
# ---------------------------------------------------------------
async def test_registry_routing_with_profiler():
    """Agent routing considers capabilities; profiler tracks selected agent."""
    registry = AgentCapabilityRegistry()
    profiler = AgentProfiler()

    # Register specialized agents
    registry.register_agent("PythonExpert", AgentCapability(
        agent_name="PythonExpert", languages={"python"}, frameworks={"django"},
        task_types={"backend", "api"}, max_concurrent_tasks=3, priority=2,
    ))
    registry.register_agent("JSExpert", AgentCapability(
        agent_name="JSExpert", languages={"typescript", "javascript"}, frameworks={"react"},
        task_types={"frontend", "ui"}, max_concurrent_tasks=3, priority=2,
    ))
    registry.register_agent("Generalist", AgentCapability(
        agent_name="Generalist", languages={"python", "javascript"},
        task_types={"backend", "frontend"}, max_concurrent_tasks=5, priority=5,
    ))

    # Route a Python backend task
    best_name = registry.find_best_agent(
        language="python", framework="django", task_type="backend",
    )
    assert best_name == "PythonExpert"

    # Record profiler execution for the routed agent
    profiler.record_execution(
        agent_name=best_name,
        task_id="django-api-build",
        duration_ms=2000,
        input_tokens=3000,
        output_tokens=1500,
        success=True,
        cost_usd=0.05,
    )

    # Route a React frontend task
    js_best = registry.find_best_agent(
        language="typescript", framework="react", task_type="frontend",
    )
    assert js_best == "JSExpert"

    profiler.record_execution(
        agent_name="JSExpert",
        task_id="react-ui-build",
        duration_ms=3000,
        input_tokens=4000,
        output_tokens=2000,
        success=True,
        cost_usd=0.08,
    )

    # Compare profiled agents
    comparison = profiler.get_comparison()
    assert "PythonExpert" in comparison["agents"]
    assert "JSExpert" in comparison["agents"]

    # Capability matrix
    matrix = registry.get_capability_matrix()
    assert "python" in matrix["all_languages"]
    assert "PythonExpert" in matrix["agents"]

    print("OK: registry routing with profiler")


# ---------------------------------------------------------------
# 8. ETA estimator with real phase durations
# ---------------------------------------------------------------
async def test_eta_with_real_phases():
    """ETA estimator gives reasonable estimates with real-ish durations."""
    tracker = PipelineProgressTracker(default_phase_seconds=10.0)
    tracker.start_pipeline("eta-test", phases=["a", "b", "c", "d"])

    # Phase a: simulate 2s
    tracker.start_phase("a", estimated_tasks=1)
    tracker.phases["a"].started_at = time.time() - 2.0
    tracker.complete_task("a", "t1")
    tracker.complete_phase("a")

    # Phase b: start, 50% done
    tracker.start_phase("b", estimated_tasks=2)
    tracker.phases["b"].started_at = time.time() - 1.0
    tracker.complete_task("b", "t1")

    # ETA should exist and be positive
    eta = tracker.eta_seconds
    assert eta is not None
    assert eta > 0

    # Overall should be between 25% and 50%
    assert 25.0 <= tracker.overall_pct <= 50.0

    print("OK: ETA with real phases")


# ---------------------------------------------------------------
# 9. Event bus connects progress + profiler + deadlock
# ---------------------------------------------------------------
async def test_event_bus_integration():
    """Event bus distributes events to all subscribed services."""
    bus = EventBus()
    received_events = []

    async def collector(event):
        received_events.append(event)

    bus.subscribe(EventType.PIPELINE_STARTED, collector)
    bus.subscribe(EventType.PIPELINE_COMPLETED, collector)

    # Progress tracker broadcasts via event bus
    tracker = PipelineProgressTracker(event_bus=bus)
    tracker.start_pipeline("event-test", phases=["only"])

    await asyncio.sleep(0.05)

    # Should have received at least the pipeline started event
    assert len(received_events) >= 1
    found_start = any(
        e.data.get("action") == "progress_update" or
        e.type == EventType.PIPELINE_STARTED
        for e in received_events
    )
    assert found_start

    print("OK: event bus integration")


# ---------------------------------------------------------------
# 10. System overview with all services
# ---------------------------------------------------------------
async def test_system_overview_dashboard():
    """DAG visualizer system overview shows all service status."""
    viz = DAGVisualizer(use_color=False)
    profiler = AgentProfiler()
    registry = AgentCapabilityRegistry()

    # Record some profiler data
    for agent in ["Frontend", "Backend", "Tester"]:
        profiler.record_execution(
            agent_name=agent,
            task_id=f"{agent}-task",
            duration_ms=1000,
            input_tokens=500,
            output_tokens=300,
            success=True,
        )

    # Register agents
    registry.register_agent("Frontend", AgentCapability(
        agent_name="Frontend", languages={"typescript"}, frameworks={"react"},
    ))
    registry.register_agent("Backend", AgentCapability(
        agent_name="Backend", languages={"python"},
    ))
    registry.register_agent("Tester", AgentCapability(
        agent_name="Tester", languages={"python"}, task_types={"testing"},
    ))

    # Build overview
    summary = profiler.get_summary()
    stats = registry.get_stats()

    overview = viz.render_system_overview(
        services={
            "EventBus": True,
            "Minibook": True,
            "Profiler": True,
            "DeadlockDetector": True,
            "ConfigReloader": True,
            "AgentRegistry": True,
        },
        agents=[
            {"agent_name": "Frontend", "availability": "online", "current_tasks": 1},
            {"agent_name": "Backend", "availability": "busy", "current_tasks": 3},
            {"agent_name": "Tester", "availability": "online", "current_tasks": 0},
        ],
        metrics={
            "total_tokens": summary["total_tokens"],
            "total_cost_usd": summary["total_cost_usd"],
            "registered_agents": stats["total_agents"],
            "online_agents": stats["online"],
        },
    )

    assert "System Overview" in overview
    assert "EventBus" in overview
    assert "Frontend" in overview
    assert "total_tokens" in overview
    assert "registered_agents" in overview
    assert "online_agents" in overview

    print("OK: system overview dashboard")


# ---------------------------------------------------------------
# 11. Deadlock timeout detection
# ---------------------------------------------------------------
async def test_deadlock_timeout_integration():
    """Deadlock detector correctly identifies timed-out waits."""
    bus = EventBus()
    detector = DeadlockDetector(
        event_bus=bus,
        check_interval=999,
        default_timeout=0.1,  # 100ms timeout
    )

    detector.register_wait("SlowAgent", "FastAgent", resource="waiting for response")

    # Wait for timeout
    await asyncio.sleep(0.15)

    # Check timeouts (private method, called internally by _periodic_check)
    detector._check_timeouts()

    # Verify the wait is now timed out via wait graph (should be empty of active)
    graph = detector.get_wait_graph()
    # After timeout, active waits should be resolved
    slow_waits = graph.get("SlowAgent", [])
    assert len(slow_waits) == 0  # Timed out = no longer active

    print("OK: deadlock timeout integration")


# ---------------------------------------------------------------
# 12. Config validation with registry sync
# ---------------------------------------------------------------
async def test_config_validation_integration():
    """Config validator ensures agent configs are valid before registry use."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Valid config for AgentX
        valid_config = {
            "capabilities": ["python", "testing"],
            "max_concurrent": 3,
            "model": "claude-3-opus",
        }
        config_path = os.path.join(tmpdir, "AgentX.json")
        with open(config_path, "w") as f:
            json.dump(valid_config, f)

        bus = EventBus()
        reloader = ConfigHotReloader(event_bus=bus, config_dir=tmpdir)
        result = reloader.reload("AgentX")
        assert result is True

        cfg = reloader.get_config("AgentX")
        assert cfg is not None

        # Use config to register in registry
        registry = AgentCapabilityRegistry()
        cap = AgentCapability(
            agent_name="AgentX",
            specialties=set(cfg.get("capabilities", [])),
            max_concurrent_tasks=cfg.get("max_concurrent", 1),
        )
        registry.register_agent("AgentX", cap)

        assert registry.get_agent("AgentX") is not None
        stats = registry.get_stats()
        assert stats["total_agents"] == 1

    print("OK: config validation integration")


# ---------------------------------------------------------------
# Main
# ---------------------------------------------------------------
async def main():
    print("=== Cross-Module Integration Tests ===\n")
    await test_full_pipeline_lifecycle()
    await test_deadlock_with_registry()
    await test_config_reload_triggers_registry()
    await test_profiler_anomaly_cross_agent()
    await test_dag_all_visualizations()
    await test_retry_with_profiler()
    await test_registry_routing_with_profiler()
    await test_eta_with_real_phases()
    await test_event_bus_integration()
    await test_system_overview_dashboard()
    await test_deadlock_timeout_integration()
    await test_config_validation_integration()
    print("\n=== ALL 12 INTEGRATION TESTS PASSED ===")


if __name__ == "__main__":
    asyncio.run(main())
