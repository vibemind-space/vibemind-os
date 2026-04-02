"""Test pipeline failure handler -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_failure_handler import PipelineFailureHandler


def test_register_handler():
    fh = PipelineFailureHandler()
    hid = fh.register_handler("pipeline-1", strategy="retry", max_retries=3)
    assert len(hid) > 0
    assert hid.startswith("pfh-")
    print("OK: register handler")


def test_record_failure():
    fh = PipelineFailureHandler()
    fh.register_handler("pipeline-1", strategy="retry", max_retries=3)
    fid = fh.record_failure("pipeline-1", "step-2", error="timeout")
    assert len(fid) > 0
    print("OK: record failure")


def test_get_recovery_action_retry():
    fh = PipelineFailureHandler()
    fh.register_handler("pipeline-1", strategy="retry", max_retries=3)
    fh.record_failure("pipeline-1", "step-1", error="timeout")
    action = fh.get_recovery_action("pipeline-1")
    assert action == "retry"
    print("OK: get recovery action retry")


def test_get_recovery_action_abort():
    fh = PipelineFailureHandler()
    fh.register_handler("pipeline-1", strategy="retry", max_retries=2)
    fh.record_failure("pipeline-1", "step-1")
    fh.record_failure("pipeline-1", "step-1")
    action = fh.get_recovery_action("pipeline-1")
    assert action == "abort"  # exceeded max retries
    print("OK: get recovery action abort")


def test_get_failure_count():
    fh = PipelineFailureHandler()
    fh.register_handler("pipeline-1")
    fh.record_failure("pipeline-1", "step-1")
    fh.record_failure("pipeline-1", "step-2")
    assert fh.get_failure_count("pipeline-1") == 2
    print("OK: get failure count")


def test_get_failures():
    fh = PipelineFailureHandler()
    fh.register_handler("pipeline-1")
    fh.record_failure("pipeline-1", "step-1", error="disk full")
    failures = fh.get_failures("pipeline-1")
    assert len(failures) == 1
    print("OK: get failures")


def test_reset_failures():
    fh = PipelineFailureHandler()
    fh.register_handler("pipeline-1")
    fh.record_failure("pipeline-1", "step-1")
    assert fh.reset_failures("pipeline-1") is True
    assert fh.get_failure_count("pipeline-1") == 0
    print("OK: reset failures")


def test_list_pipelines():
    fh = PipelineFailureHandler()
    fh.register_handler("pipeline-1")
    fh.register_handler("pipeline-2")
    pipelines = fh.list_pipelines()
    assert "pipeline-1" in pipelines
    assert "pipeline-2" in pipelines
    print("OK: list pipelines")


def test_callbacks():
    fh = PipelineFailureHandler()
    fired = []
    fh.on_change("mon", lambda a, d: fired.append(a))
    fh.register_handler("pipeline-1")
    assert len(fired) >= 1
    assert fh.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    fh = PipelineFailureHandler()
    fh.register_handler("pipeline-1")
    stats = fh.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    fh = PipelineFailureHandler()
    fh.register_handler("pipeline-1")
    fh.reset()
    assert fh.get_handler_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Failure Handler Tests ===\n")
    test_register_handler()
    test_record_failure()
    test_get_recovery_action_retry()
    test_get_recovery_action_abort()
    test_get_failure_count()
    test_get_failures()
    test_reset_failures()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
