"""Test pipeline retry store -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_retry_store import PipelineRetryStore


def test_set_policy():
    rs = PipelineRetryStore()
    pid = rs.set_policy("deploy", max_retries=5, backoff_seconds=2.0)
    assert len(pid) > 0
    assert pid.startswith("prt-")
    p = rs.get_policy("deploy")
    assert p is not None
    assert p["max_retries"] == 5
    print("OK: set policy")


def test_record_attempt():
    rs = PipelineRetryStore()
    aid = rs.record_attempt("deploy", "exec-1", False, error="timeout")
    assert len(aid) > 0
    assert aid.startswith("prt-")
    print("OK: record attempt")


def test_get_attempts():
    rs = PipelineRetryStore()
    rs.record_attempt("deploy", "exec-1", False, error="err1")
    rs.record_attempt("deploy", "exec-1", False, error="err2")
    rs.record_attempt("deploy", "exec-2", True)
    all_a = rs.get_attempts("deploy")
    assert len(all_a) == 3
    exec1 = rs.get_attempts("deploy", execution_id="exec-1")
    assert len(exec1) == 2
    print("OK: get attempts")


def test_get_retry_count():
    rs = PipelineRetryStore()
    rs.record_attempt("deploy", "exec-1", False)
    rs.record_attempt("deploy", "exec-1", False)
    assert rs.get_retry_count("deploy", "exec-1") == 2
    print("OK: get retry count")


def test_should_retry():
    rs = PipelineRetryStore()
    rs.set_policy("deploy", max_retries=2)
    rs.record_attempt("deploy", "exec-1", False)
    assert rs.should_retry("deploy", "exec-1") is True
    rs.record_attempt("deploy", "exec-1", False)
    assert rs.should_retry("deploy", "exec-1") is False  # Hit max
    print("OK: should retry")


def test_get_success_rate():
    rs = PipelineRetryStore()
    rs.record_attempt("deploy", "e1", True)
    rs.record_attempt("deploy", "e2", True)
    rs.record_attempt("deploy", "e3", False)
    rate = rs.get_success_rate("deploy")
    assert abs(rate - 2/3) < 0.01
    print("OK: get success rate")


def test_clear_attempts():
    rs = PipelineRetryStore()
    rs.record_attempt("deploy", "e1", False)
    rs.record_attempt("deploy", "e2", True)
    count = rs.clear_attempts("deploy")
    assert count == 2
    assert rs.get_attempts("deploy") == []
    print("OK: clear attempts")


def test_list_pipelines():
    rs = PipelineRetryStore()
    rs.set_policy("deploy", max_retries=3)
    rs.record_attempt("test", "e1", True)
    pipes = rs.list_pipelines()
    assert "deploy" in pipes
    assert "test" in pipes
    print("OK: list pipelines")


def test_callbacks():
    rs = PipelineRetryStore()
    fired = []
    rs.on_change("mon", lambda a, d: fired.append(a))
    rs.set_policy("deploy", max_retries=3)
    assert len(fired) >= 1
    assert rs.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    rs = PipelineRetryStore()
    rs.set_policy("deploy", max_retries=3)
    stats = rs.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    rs = PipelineRetryStore()
    rs.set_policy("deploy", max_retries=3)
    rs.record_attempt("deploy", "e1", False)
    rs.reset()
    assert rs.list_pipelines() == []
    print("OK: reset")


def main():
    print("=== Pipeline Retry Store Tests ===\n")
    test_set_policy()
    test_record_attempt()
    test_get_attempts()
    test_get_retry_count()
    test_should_retry()
    test_get_success_rate()
    test_clear_attempts()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
