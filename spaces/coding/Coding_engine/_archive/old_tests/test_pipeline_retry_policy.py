"""Test pipeline retry policy -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_retry_policy import PipelineRetryPolicy


def test_create_policy():
    rp = PipelineRetryPolicy()
    pid = rp.create_policy("pipeline-1", max_retries=3, backoff="exponential", initial_delay=1.0)
    assert len(pid) > 0
    assert pid.startswith("prp-")
    print("OK: create policy")


def test_get_policy():
    rp = PipelineRetryPolicy()
    pid = rp.create_policy("pipeline-1", max_retries=5)
    policy = rp.get_policy(pid)
    assert policy is not None
    assert policy["pipeline_id"] == "pipeline-1"
    assert policy["max_retries"] == 5
    assert rp.get_policy("nonexistent") is None
    print("OK: get policy")


def test_get_policy_for_pipeline():
    rp = PipelineRetryPolicy()
    rp.create_policy("pipeline-1", max_retries=3)
    policy = rp.get_policy_for_pipeline("pipeline-1")
    assert policy is not None
    assert policy["max_retries"] == 3
    assert rp.get_policy_for_pipeline("nonexistent") is None
    print("OK: get policy for pipeline")


def test_should_retry():
    rp = PipelineRetryPolicy()
    rp.create_policy("pipeline-1", max_retries=3)
    assert rp.should_retry("pipeline-1", 1) is True
    assert rp.should_retry("pipeline-1", 2) is True
    assert rp.should_retry("pipeline-1", 3) is False
    print("OK: should retry")


def test_get_delay_exponential():
    rp = PipelineRetryPolicy()
    rp.create_policy("pipeline-1", max_retries=5, backoff="exponential", initial_delay=1.0)
    assert rp.get_delay("pipeline-1", 1) == 1.0
    assert rp.get_delay("pipeline-1", 2) == 2.0
    assert rp.get_delay("pipeline-1", 3) == 4.0
    print("OK: get delay exponential")


def test_get_delay_linear():
    rp = PipelineRetryPolicy()
    rp.create_policy("pipeline-1", max_retries=5, backoff="linear", initial_delay=2.0)
    assert rp.get_delay("pipeline-1", 1) == 2.0
    assert rp.get_delay("pipeline-1", 2) == 4.0
    assert rp.get_delay("pipeline-1", 3) == 6.0
    print("OK: get delay linear")


def test_record_attempt():
    rp = PipelineRetryPolicy()
    rp.create_policy("pipeline-1", max_retries=3)
    result = rp.record_attempt("pipeline-1", success=False)
    assert result is not None
    result2 = rp.record_attempt("pipeline-1", success=True)
    assert result2 is not None
    print("OK: record attempt")


def test_get_attempt_history():
    rp = PipelineRetryPolicy()
    rp.create_policy("pipeline-1", max_retries=3)
    rp.record_attempt("pipeline-1", success=False)
    rp.record_attempt("pipeline-1", success=True)
    history = rp.get_attempt_history("pipeline-1")
    assert len(history) == 2
    print("OK: get attempt history")


def test_update_policy():
    rp = PipelineRetryPolicy()
    pid = rp.create_policy("pipeline-1", max_retries=3)
    assert rp.update_policy(pid, max_retries=5) is True
    policy = rp.get_policy(pid)
    assert policy["max_retries"] == 5
    assert rp.update_policy("nonexistent") is False
    print("OK: update policy")


def test_remove_policy():
    rp = PipelineRetryPolicy()
    pid = rp.create_policy("pipeline-1", max_retries=3)
    assert rp.remove_policy(pid) is True
    assert rp.remove_policy(pid) is False
    print("OK: remove policy")


def test_callbacks():
    rp = PipelineRetryPolicy()
    fired = []
    rp.on_change("mon", lambda a, d: fired.append(a))
    rp.create_policy("pipeline-1", max_retries=3)
    assert len(fired) >= 1
    assert rp.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    rp = PipelineRetryPolicy()
    rp.create_policy("pipeline-1", max_retries=3)
    stats = rp.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    rp = PipelineRetryPolicy()
    rp.create_policy("pipeline-1", max_retries=3)
    rp.reset()
    assert rp.get_policy_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Retry Policy Tests ===\n")
    test_create_policy()
    test_get_policy()
    test_get_policy_for_pipeline()
    test_should_retry()
    test_get_delay_exponential()
    test_get_delay_linear()
    test_record_attempt()
    test_get_attempt_history()
    test_update_policy()
    test_remove_policy()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 13 TESTS PASSED ===")


if __name__ == "__main__":
    main()
