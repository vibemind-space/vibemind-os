"""Test pipeline progress reporter -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_progress_reporter import PipelineProgressReporter


def test_start_report():
    pr = PipelineProgressReporter()
    rid = pr.start_report("pipeline-1", total_steps=10)
    assert len(rid) > 0
    assert rid.startswith("ppr-")
    print("OK: start report")


def test_update_progress():
    pr = PipelineProgressReporter()
    rid = pr.start_report("pipeline-1", total_steps=10)
    assert pr.update_progress(rid, completed_steps=5, message="halfway") is True
    print("OK: update progress")


def test_get_progress():
    pr = PipelineProgressReporter()
    rid = pr.start_report("pipeline-1", total_steps=4)
    pr.update_progress(rid, completed_steps=2)
    prog = pr.get_progress(rid)
    assert prog is not None
    assert prog["completed_steps"] == 2
    assert abs(prog["percentage"] - 50.0) < 0.1
    print("OK: get progress")


def test_get_latest_report():
    pr = PipelineProgressReporter()
    pr.start_report("pipeline-1", total_steps=5)
    r2 = pr.start_report("pipeline-1", total_steps=10)
    pr.update_progress(r2, completed_steps=3)
    latest = pr.get_latest_report("pipeline-1")
    assert latest is not None
    assert latest["total_steps"] == 10
    print("OK: get latest report")


def test_list_pipelines():
    pr = PipelineProgressReporter()
    pr.start_report("pipeline-1", total_steps=5)
    pr.start_report("pipeline-2", total_steps=3)
    pipelines = pr.list_pipelines()
    assert "pipeline-1" in pipelines
    assert "pipeline-2" in pipelines
    print("OK: list pipelines")


def test_callbacks():
    pr = PipelineProgressReporter()
    fired = []
    pr.on_change("mon", lambda a, d: fired.append(a))
    pr.start_report("pipeline-1", total_steps=5)
    assert len(fired) >= 1
    assert pr.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    pr = PipelineProgressReporter()
    pr.start_report("pipeline-1", total_steps=5)
    stats = pr.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    pr = PipelineProgressReporter()
    pr.start_report("pipeline-1", total_steps=5)
    pr.reset()
    assert pr.get_report_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Progress Reporter Tests ===\n")
    test_start_report()
    test_update_progress()
    test_get_progress()
    test_get_latest_report()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 8 TESTS PASSED ===")


if __name__ == "__main__":
    main()
