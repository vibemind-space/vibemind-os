"""Test pipeline step retry -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_step_retry import PipelineStepRetry


def test_configure_retry():
    sr = PipelineStepRetry()
    rid = sr.configure_retry("pipeline-1", "extract", max_retries=3)
    assert len(rid) > 0
    assert rid.startswith("psr2-")
    print("OK: configure retry")


def test_record_attempt_success():
    sr = PipelineStepRetry()
    sr.configure_retry("pipeline-1", "extract", max_retries=3)
    result = sr.record_attempt("pipeline-1", "extract", success=True)
    assert result["attempt"] == 1
    assert result["should_retry"] is False
    print("OK: record attempt success")


def test_record_attempt_failure():
    sr = PipelineStepRetry()
    sr.configure_retry("pipeline-1", "extract", max_retries=3)
    result = sr.record_attempt("pipeline-1", "extract", success=False)
    assert result["attempt"] == 1
    assert result["should_retry"] is True
    assert result["exhausted"] is False
    print("OK: record attempt failure")


def test_record_attempt_exhausted():
    sr = PipelineStepRetry()
    sr.configure_retry("pipeline-1", "extract", max_retries=2)
    sr.record_attempt("pipeline-1", "extract", success=False)
    result = sr.record_attempt("pipeline-1", "extract", success=False)
    assert result["attempt"] == 2
    assert result["should_retry"] is False
    assert result["exhausted"] is True
    print("OK: record attempt exhausted")


def test_get_attempt_count():
    sr = PipelineStepRetry()
    sr.configure_retry("pipeline-1", "extract", max_retries=5)
    sr.record_attempt("pipeline-1", "extract", success=False)
    sr.record_attempt("pipeline-1", "extract", success=False)
    assert sr.get_attempt_count("pipeline-1", "extract") == 2
    print("OK: get attempt count")


def test_should_retry():
    sr = PipelineStepRetry()
    sr.configure_retry("pipeline-1", "extract", max_retries=3)
    sr.record_attempt("pipeline-1", "extract", success=False)
    assert sr.should_retry("pipeline-1", "extract") is True
    sr.record_attempt("pipeline-1", "extract", success=False)
    sr.record_attempt("pipeline-1", "extract", success=False)
    assert sr.should_retry("pipeline-1", "extract") is False
    print("OK: should retry")


def test_reset_retries():
    sr = PipelineStepRetry()
    sr.configure_retry("pipeline-1", "extract", max_retries=2)
    sr.record_attempt("pipeline-1", "extract", success=False)
    sr.record_attempt("pipeline-1", "extract", success=False)
    assert sr.should_retry("pipeline-1", "extract") is False
    assert sr.reset_retries("pipeline-1", "extract") is True
    assert sr.should_retry("pipeline-1", "extract") is True
    assert sr.reset_retries("pipeline-1", "nonexistent") is False
    print("OK: reset retries")


def test_get_retry_count():
    sr = PipelineStepRetry()
    sr.configure_retry("pipeline-1", "extract")
    sr.configure_retry("pipeline-2", "load")
    assert sr.get_retry_count() == 2
    assert sr.get_retry_count("pipeline-1") == 1
    print("OK: get retry count")


def test_list_pipelines():
    sr = PipelineStepRetry()
    sr.configure_retry("pipeline-1", "extract")
    sr.configure_retry("pipeline-2", "load")
    pipelines = sr.list_pipelines()
    assert "pipeline-1" in pipelines
    assert "pipeline-2" in pipelines
    print("OK: list pipelines")


def test_callbacks():
    sr = PipelineStepRetry()
    fired = []
    sr.on_change("mon", lambda a, d: fired.append(a))
    sr.configure_retry("pipeline-1", "extract")
    assert len(fired) >= 1
    assert sr.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    sr = PipelineStepRetry()
    sr.configure_retry("pipeline-1", "extract")
    stats = sr.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    sr = PipelineStepRetry()
    sr.configure_retry("pipeline-1", "extract")
    sr.reset()
    assert sr.get_retry_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Step Retry Tests ===\n")
    test_configure_retry()
    test_record_attempt_success()
    test_record_attempt_failure()
    test_record_attempt_exhausted()
    test_get_attempt_count()
    test_should_retry()
    test_reset_retries()
    test_get_retry_count()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 12 TESTS PASSED ===")


if __name__ == "__main__":
    main()
