"""Test pipeline completion tracker -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_completion_tracker import PipelineCompletionTracker


def test_start_tracking():
    ct = PipelineCompletionTracker()
    tid = ct.start_tracking("pipeline-1", expected_steps=5)
    assert len(tid) > 0
    assert tid.startswith("pct2-")
    print("OK: start tracking")


def test_mark_step_done():
    ct = PipelineCompletionTracker()
    tid = ct.start_tracking("pipeline-1", expected_steps=3)
    assert ct.mark_step_done(tid, "step-1") is True
    print("OK: mark step done")


def test_mark_complete():
    ct = PipelineCompletionTracker()
    tid = ct.start_tracking("pipeline-1")
    assert ct.mark_complete(tid) is True
    assert ct.is_complete(tid) is True
    print("OK: mark complete")


def test_mark_failed():
    ct = PipelineCompletionTracker()
    tid = ct.start_tracking("pipeline-1")
    assert ct.mark_failed(tid, reason="out of memory") is True
    print("OK: mark failed")


def test_get_status():
    ct = PipelineCompletionTracker()
    tid = ct.start_tracking("pipeline-1", expected_steps=4)
    ct.mark_step_done(tid, "step-1")
    ct.mark_step_done(tid, "step-2")
    status = ct.get_status(tid)
    assert status is not None
    assert status["pipeline_id"] == "pipeline-1"
    assert status["steps_done"] == 2
    assert ct.get_status("nonexistent") is None
    print("OK: get status")


def test_is_complete():
    ct = PipelineCompletionTracker()
    tid = ct.start_tracking("pipeline-1")
    assert ct.is_complete(tid) is False
    ct.mark_complete(tid)
    assert ct.is_complete(tid) is True
    print("OK: is complete")


def test_list_pipelines():
    ct = PipelineCompletionTracker()
    ct.start_tracking("pipeline-1")
    ct.start_tracking("pipeline-2")
    pipelines = ct.list_pipelines()
    assert "pipeline-1" in pipelines
    assert "pipeline-2" in pipelines
    print("OK: list pipelines")


def test_callbacks():
    ct = PipelineCompletionTracker()
    fired = []
    ct.on_change("mon", lambda a, d: fired.append(a))
    ct.start_tracking("pipeline-1")
    assert len(fired) >= 1
    assert ct.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    ct = PipelineCompletionTracker()
    ct.start_tracking("pipeline-1")
    stats = ct.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    ct = PipelineCompletionTracker()
    ct.start_tracking("pipeline-1")
    ct.reset()
    assert ct.get_tracking_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Completion Tracker Tests ===\n")
    test_start_tracking()
    test_mark_step_done()
    test_mark_complete()
    test_mark_failed()
    test_get_status()
    test_is_complete()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")


if __name__ == "__main__":
    main()
