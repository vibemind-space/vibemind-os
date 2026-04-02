"""Test pipeline progress tracker and ETA estimation."""
import asyncio
import sys
import time
sys.path.insert(0, ".")

from src.mind.event_bus import EventBus
from src.services.pipeline_progress import (
    PipelineProgressTracker,
    PhaseProgress,
    PhaseStatus,
    TaskProgress,
    ETAEstimator,
)


async def test_start_pipeline():
    """Pipeline starts with correct initial state."""
    tracker = PipelineProgressTracker()
    tracker.start_pipeline("test-project", phases=["plan", "generate", "test", "deploy"])

    assert tracker.project_name == "test-project"
    assert len(tracker.phase_order) == 4
    assert tracker.overall_pct == 0.0
    assert tracker.pipeline_started_at is not None

    progress = tracker.get_progress()
    assert progress["project_name"] == "test-project"
    assert progress["overall_pct"] == 0.0
    assert len(progress["phases"]) == 4
    print("OK: start pipeline")


async def test_phase_lifecycle():
    """Phase goes through pending -> running -> completed."""
    tracker = PipelineProgressTracker()
    tracker.start_pipeline("test", phases=["alpha", "beta"])

    phase = tracker.phases["alpha"]
    assert phase.status == PhaseStatus.PENDING

    tracker.start_phase("alpha", estimated_tasks=2)
    assert phase.status == PhaseStatus.RUNNING
    assert phase.started_at is not None

    tracker.complete_task("alpha", "task1")
    assert phase.completed_tasks == 1
    assert phase.completion_pct == 50.0

    tracker.complete_task("alpha", "task2")
    assert phase.completed_tasks == 2
    assert phase.completion_pct == 100.0

    tracker.complete_phase("alpha")
    assert phase.status == PhaseStatus.COMPLETED
    assert phase.completed_at is not None
    assert phase.duration_ms is not None
    print("OK: phase lifecycle")


async def test_task_tracking():
    """Tasks can be started, completed, and failed."""
    tracker = PipelineProgressTracker()
    tracker.start_pipeline("test", phases=["p1"])
    tracker.start_phase("p1", estimated_tasks=3)

    tracker.start_task("p1", "t1", description="First task")
    task = tracker.phases["p1"].tasks["t1"]
    assert task.status == PhaseStatus.RUNNING
    assert task.started_at is not None

    tracker.complete_task("p1", "t1")
    assert task.status == PhaseStatus.COMPLETED
    assert task.duration_ms is not None

    tracker.start_task("p1", "t2", description="Second task")
    tracker.fail_task("p1", "t2", error="something broke")
    t2 = tracker.phases["p1"].tasks["t2"]
    assert t2.status == PhaseStatus.FAILED
    assert t2.error == "something broke"
    print("OK: task tracking")


async def test_auto_create_task_on_complete():
    """Completing a task that wasn't explicitly started auto-creates it."""
    tracker = PipelineProgressTracker()
    tracker.start_pipeline("test", phases=["p1"])
    tracker.start_phase("p1", estimated_tasks=2)

    tracker.complete_task("p1", "auto_task")
    assert "auto_task" in tracker.phases["p1"].tasks
    assert tracker.phases["p1"].tasks["auto_task"].status == PhaseStatus.COMPLETED
    print("OK: auto-create task on complete")


async def test_overall_percentage():
    """Overall percentage tracks across phases."""
    tracker = PipelineProgressTracker()
    tracker.start_pipeline("test", phases=["a", "b", "c", "d"])

    # 0/4 phases
    assert tracker.overall_pct == 0.0

    # Complete first phase
    tracker.start_phase("a", estimated_tasks=1)
    tracker.complete_task("a", "t1")
    tracker.complete_phase("a")
    # 1/4 = 25%
    assert abs(tracker.overall_pct - 25.0) < 0.1

    # Complete second phase
    tracker.start_phase("b", estimated_tasks=1)
    tracker.complete_task("b", "t1")
    tracker.complete_phase("b")
    # 2/4 = 50%
    assert abs(tracker.overall_pct - 50.0) < 0.1

    # Skip third
    tracker.skip_phase("c")
    # 3/4 = 75%
    assert abs(tracker.overall_pct - 75.0) < 0.1

    print("OK: overall percentage")


async def test_partial_phase_percentage():
    """Running phase contributes partial percentage to overall."""
    tracker = PipelineProgressTracker()
    tracker.start_pipeline("test", phases=["a", "b"])

    tracker.start_phase("a", estimated_tasks=2)
    tracker.complete_task("a", "t1")
    # Phase a is 50% complete = 0.5 out of 2 phases = 25% overall
    assert abs(tracker.overall_pct - 25.0) < 0.1
    print("OK: partial phase percentage")


async def test_eta_estimator_basic():
    """ETA estimator produces reasonable estimates."""
    est = ETAEstimator(alpha=0.3)

    # No history: returns default
    assert est.estimate_phase_duration("unknown", default_seconds=30.0) == 30.0

    # Record some durations
    est.record_phase_duration("planning", 10.0)
    est.record_phase_duration("planning", 12.0)
    est.record_phase_duration("planning", 8.0)

    # EMA should be somewhere around 8-12
    estimate = est.estimate_phase_duration("planning")
    assert 5.0 <= estimate <= 15.0

    print("OK: ETA estimator basic")


async def test_eta_estimator_remaining():
    """ETA estimates remaining time for pipeline."""
    est = ETAEstimator(alpha=0.5)
    est.record_phase_duration("plan", 10.0)
    est.record_phase_duration("generate", 30.0)
    est.record_phase_duration("test", 20.0)

    # Remaining = current partial + future full phases
    remaining = est.estimate_remaining(
        remaining_phases=["test"],
        current_phase_id="generate",
        current_phase_pct=50.0,
        default_seconds=60.0,
    )

    # ~15s remaining in generate (50% of 30) + ~20s for test = ~35s
    assert 20.0 <= remaining <= 50.0
    print("OK: ETA estimator remaining")


async def test_eta_with_tracker():
    """ETA estimation through tracker integration."""
    tracker = PipelineProgressTracker(default_phase_seconds=10.0)
    tracker.start_pipeline("test", phases=["a", "b", "c"])

    # Simulate phase a taking 5 seconds
    tracker.start_phase("a", estimated_tasks=1)
    tracker.phases["a"].started_at = time.time() - 5.0
    tracker.complete_task("a", "t1")
    tracker.complete_phase("a")

    # Start phase b
    tracker.start_phase("b", estimated_tasks=2)
    tracker.complete_task("b", "t1")
    # b is 50% done

    eta = tracker.eta_seconds
    assert eta is not None
    assert eta > 0
    print("OK: ETA with tracker")


async def test_phase_to_dict():
    """Phase serialization includes all fields."""
    tracker = PipelineProgressTracker()
    tracker.start_pipeline("test", phases=["p1"])
    tracker.start_phase("p1", estimated_tasks=2, label="Planning Phase")
    tracker.start_task("p1", "t1", "Task one")
    tracker.complete_task("p1", "t1")

    d = tracker.phases["p1"].to_dict()
    assert d["phase_id"] == "p1"
    assert d["label"] == "Planning Phase"
    assert d["status"] == "running"
    assert d["completion_pct"] == 50.0
    assert d["completed_tasks"] == 1
    assert d["total_tasks"] == 2
    assert "t1" in d["tasks"]
    assert d["tasks"]["t1"]["status"] == "completed"
    print("OK: phase to_dict")


async def test_get_progress_full():
    """Full progress snapshot is complete."""
    tracker = PipelineProgressTracker()
    tracker.start_pipeline("proj", phases=["plan", "build"])
    tracker.start_phase("plan", estimated_tasks=1)
    tracker.complete_task("plan", "t1")
    tracker.complete_phase("plan")

    progress = tracker.get_progress()
    assert progress["project_name"] == "proj"
    assert progress["overall_pct"] == 50.0
    assert "plan" in progress["phases"]
    assert "build" in progress["phases"]
    assert progress["phases"]["plan"]["status"] == "completed"
    assert progress["phases"]["build"]["status"] == "pending"
    assert progress["total_duration_ms"] is not None
    assert "eta_estimator" in progress
    print("OK: full progress snapshot")


async def test_fail_phase():
    """Failed phase is tracked correctly."""
    tracker = PipelineProgressTracker()
    tracker.start_pipeline("test", phases=["a"])
    tracker.start_phase("a", estimated_tasks=1)
    tracker.fail_phase("a", error="build failed")

    phase = tracker.phases["a"]
    assert phase.status == PhaseStatus.FAILED
    assert phase.error == "build failed"
    assert phase.completed_at is not None
    print("OK: fail phase")


async def test_complete_pipeline():
    """Pipeline completion sets end time."""
    tracker = PipelineProgressTracker()
    tracker.start_pipeline("test", phases=["a"])
    tracker.start_phase("a", estimated_tasks=1)
    tracker.complete_task("a", "t1")
    tracker.complete_phase("a")
    tracker.complete_pipeline()

    assert tracker.pipeline_completed_at is not None
    assert tracker.total_duration_ms is not None
    assert tracker._current_phase is None
    print("OK: complete pipeline")


async def test_dynamic_phase_addition():
    """Phases added dynamically (not pre-declared) are tracked."""
    tracker = PipelineProgressTracker()
    tracker.start_pipeline("test", phases=["a"])

    # Start a phase not in original list
    tracker.start_phase("surprise", estimated_tasks=1)
    assert "surprise" in tracker.phases
    assert "surprise" in tracker.phase_order

    tracker.complete_task("surprise", "t1")
    tracker.complete_phase("surprise")
    assert tracker.phases["surprise"].status == PhaseStatus.COMPLETED
    print("OK: dynamic phase addition")


async def test_event_bus_broadcast():
    """Progress updates broadcast via event bus."""
    bus = EventBus()
    received = []

    from src.mind.event_bus import EventType
    async def handler(event):
        if event.data.get("action") == "progress_update":
            received.append(event.data["progress"])

    bus.subscribe(EventType.PIPELINE_STARTED, handler)

    tracker = PipelineProgressTracker(event_bus=bus)
    tracker.start_pipeline("test", phases=["a"])

    # Give the event loop a chance to process
    await asyncio.sleep(0.05)

    assert len(received) >= 1
    assert received[0]["project_name"] == "test"
    print("OK: event bus broadcast")


async def test_eta_estimator_ema_convergence():
    """EMA converges toward recent values."""
    est = ETAEstimator(alpha=0.5)

    # First 5 values around 10s
    for _ in range(5):
        est.record_phase_duration("x", 10.0)

    est_before = est.estimate_phase_duration("x")
    assert abs(est_before - 10.0) < 1.0

    # Now 5 values around 20s
    for _ in range(5):
        est.record_phase_duration("x", 20.0)

    est_after = est.estimate_phase_duration("x")
    # Should have moved significantly toward 20
    assert est_after > 15.0
    print("OK: EMA convergence")


async def test_get_phase_progress():
    """get_phase_progress returns single phase or None."""
    tracker = PipelineProgressTracker()
    tracker.start_pipeline("test", phases=["a"])

    p = tracker.get_phase_progress("a")
    assert p is not None
    assert p["phase_id"] == "a"

    p2 = tracker.get_phase_progress("nonexistent")
    assert p2 is None
    print("OK: get_phase_progress")


async def test_empty_phase_completion():
    """Phase with no tasks completes at 100%."""
    phase = PhaseProgress(phase_id="empty", status=PhaseStatus.COMPLETED)
    assert phase.completion_pct == 100.0

    phase2 = PhaseProgress(phase_id="empty2", status=PhaseStatus.PENDING)
    assert phase2.completion_pct == 0.0
    print("OK: empty phase completion")


async def main():
    print("=== Pipeline Progress Tracker Tests ===\n")
    await test_start_pipeline()
    await test_phase_lifecycle()
    await test_task_tracking()
    await test_auto_create_task_on_complete()
    await test_overall_percentage()
    await test_partial_phase_percentage()
    await test_eta_estimator_basic()
    await test_eta_estimator_remaining()
    await test_eta_with_tracker()
    await test_phase_to_dict()
    await test_get_progress_full()
    await test_fail_phase()
    await test_complete_pipeline()
    await test_dynamic_phase_addition()
    await test_event_bus_broadcast()
    await test_eta_estimator_ema_convergence()
    await test_get_phase_progress()
    await test_empty_phase_completion()
    print("\n=== ALL 18 TESTS PASSED ===")


if __name__ == "__main__":
    asyncio.run(main())
