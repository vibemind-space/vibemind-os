"""Test pipeline execution tracker -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_execution_tracker import PipelineExecutionTracker


def test_start_execution():
    et = PipelineExecutionTracker()
    eid = et.start_execution("pipeline-1", total_steps=5)
    assert len(eid) > 0
    assert eid.startswith("pet-")
    print("OK: start execution")


def test_complete_step():
    et = PipelineExecutionTracker()
    eid = et.start_execution("pipeline-1", total_steps=3)
    assert et.complete_step(eid, "step-1") is True
    print("OK: complete step")


def test_get_progress():
    et = PipelineExecutionTracker()
    eid = et.start_execution("pipeline-1", total_steps=4)
    et.complete_step(eid, "step-1")
    et.complete_step(eid, "step-2")
    progress = et.get_progress(eid)
    assert abs(progress - 0.5) < 0.01
    print("OK: get progress")


def test_fail_execution():
    et = PipelineExecutionTracker()
    eid = et.start_execution("pipeline-1", total_steps=3)
    assert et.fail_execution(eid, reason="timeout") is True
    print("OK: fail execution")


def test_finish_execution():
    et = PipelineExecutionTracker()
    eid = et.start_execution("pipeline-1", total_steps=2)
    et.complete_step(eid, "step-1")
    et.complete_step(eid, "step-2")
    assert et.finish_execution(eid) is True
    print("OK: finish execution")


def test_get_execution():
    et = PipelineExecutionTracker()
    eid = et.start_execution("pipeline-1", total_steps=3)
    ex = et.get_execution(eid)
    assert ex is not None
    assert ex["pipeline_id"] == "pipeline-1"
    assert et.get_execution("nonexistent") is None
    print("OK: get execution")


def test_get_active_executions():
    et = PipelineExecutionTracker()
    e1 = et.start_execution("pipeline-1", total_steps=3)
    e2 = et.start_execution("pipeline-2", total_steps=2)
    et.finish_execution(e1)
    active = et.get_active_executions()
    assert len(active) >= 1
    print("OK: get active executions")


def test_list_pipelines():
    et = PipelineExecutionTracker()
    et.start_execution("pipeline-1")
    et.start_execution("pipeline-2")
    pipelines = et.list_pipelines()
    assert "pipeline-1" in pipelines
    assert "pipeline-2" in pipelines
    print("OK: list pipelines")


def test_callbacks():
    et = PipelineExecutionTracker()
    fired = []
    et.on_change("mon", lambda a, d: fired.append(a))
    et.start_execution("pipeline-1")
    assert len(fired) >= 1
    assert et.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    et = PipelineExecutionTracker()
    et.start_execution("pipeline-1")
    stats = et.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    et = PipelineExecutionTracker()
    et.start_execution("pipeline-1")
    et.reset()
    assert et.get_execution_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Execution Tracker Tests ===\n")
    test_start_execution()
    test_complete_step()
    test_get_progress()
    test_fail_execution()
    test_finish_execution()
    test_get_execution()
    test_get_active_executions()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
