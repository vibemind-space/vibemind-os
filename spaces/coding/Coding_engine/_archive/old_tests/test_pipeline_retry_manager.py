"""Test pipeline retry manager."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_retry_manager import PipelineRetryManager


def test_create_policy():
    """Create and retrieve policy."""
    rm = PipelineRetryManager()
    pid = rm.create_policy("default", max_attempts=5,
                           base_delay_ms=500, max_delay_ms=30000,
                           backoff_multiplier=2.0,
                           retryable_errors=["timeout", "503"],
                           tags=["api"])
    assert pid.startswith("rpol-")

    p = rm.get_policy(pid)
    assert p is not None
    assert p["name"] == "default"
    assert p["max_attempts"] == 5
    assert p["base_delay_ms"] == 500
    assert p["backoff_multiplier"] == 2.0
    assert p["status"] == "active"

    assert rm.remove_policy(pid) is True
    assert rm.remove_policy(pid) is False
    print("OK: create policy")


def test_invalid_policy():
    """Invalid policy rejected."""
    rm = PipelineRetryManager()
    assert rm.create_policy("") == ""
    assert rm.create_policy("x", max_attempts=0) == ""
    print("OK: invalid policy")


def test_disable_enable_policy():
    """Disable and enable policy."""
    rm = PipelineRetryManager()
    pid = rm.create_policy("test")

    assert rm.disable_policy(pid) is True
    assert rm.get_policy(pid)["status"] == "disabled"
    assert rm.disable_policy(pid) is False

    assert rm.enable_policy(pid) is True
    assert rm.get_policy(pid)["status"] == "active"
    assert rm.enable_policy(pid) is False
    print("OK: disable enable policy")


def test_record_attempt():
    """Record and retrieve attempt."""
    rm = PipelineRetryManager()
    pid = rm.create_policy("test", base_delay_ms=100, backoff_multiplier=2)
    aid = rm.record_attempt(pid, "deploy", attempt_number=1,
                            error="timeout", tags=["ci"])
    assert aid.startswith("ratt-")

    a = rm.get_attempt(aid)
    assert a is not None
    assert a["policy_id"] == pid
    assert a["operation"] == "deploy"
    assert a["attempt_number"] == 1
    assert a["delay_ms"] == 100  # base * 2^0

    assert rm.remove_attempt(aid) is True
    assert rm.remove_attempt(aid) is False
    print("OK: record attempt")


def test_invalid_attempt():
    """Invalid attempt rejected."""
    rm = PipelineRetryManager()
    pid = rm.create_policy("test")
    assert rm.record_attempt("", "op", 1) == ""
    assert rm.record_attempt(pid, "", 1) == ""
    assert rm.record_attempt("nonexistent", "op", 1) == ""
    assert rm.record_attempt(pid, "op", 1, status="invalid") == ""
    print("OK: invalid attempt")


def test_backoff_calculation():
    """Backoff delay calculated correctly."""
    rm = PipelineRetryManager()
    pid = rm.create_policy("test", base_delay_ms=100,
                           max_delay_ms=1000, backoff_multiplier=2)

    assert rm.calculate_delay(pid, 1) == 100    # 100 * 2^0
    assert rm.calculate_delay(pid, 2) == 200    # 100 * 2^1
    assert rm.calculate_delay(pid, 3) == 400    # 100 * 2^2
    assert rm.calculate_delay(pid, 4) == 800    # 100 * 2^3
    assert rm.calculate_delay(pid, 5) == 1000   # capped at max
    print("OK: backoff calculation")


def test_should_retry():
    """Should retry logic."""
    rm = PipelineRetryManager()
    pid = rm.create_policy("test", max_attempts=3,
                           retryable_errors=["timeout"])

    assert rm.should_retry(pid, 1) is True
    assert rm.should_retry(pid, 2) is True
    assert rm.should_retry(pid, 3) is False  # at max

    assert rm.should_retry(pid, 1, "timeout occurred") is True
    assert rm.should_retry(pid, 1, "auth failed") is False
    print("OK: should retry")


def test_disabled_policy_no_retry():
    """Disabled policy prevents retry."""
    rm = PipelineRetryManager()
    pid = rm.create_policy("test", max_attempts=3)
    rm.disable_policy(pid)

    assert rm.should_retry(pid, 1) is False
    print("OK: disabled policy no retry")


def test_mark_succeeded():
    """Mark attempt succeeded."""
    rm = PipelineRetryManager()
    pid = rm.create_policy("test")
    aid = rm.record_attempt(pid, "op", 1)

    assert rm.mark_succeeded(aid) is True
    assert rm.get_attempt(aid)["status"] == "succeeded"
    assert rm.mark_succeeded(aid) is False
    print("OK: mark succeeded")


def test_mark_failed():
    """Mark attempt failed."""
    rm = PipelineRetryManager()
    pid = rm.create_policy("test")
    aid = rm.record_attempt(pid, "op", 1)

    assert rm.mark_failed(aid) is True
    assert rm.get_attempt(aid)["status"] == "failed"
    assert rm.mark_failed(aid) is False
    print("OK: mark failed")


def test_mark_exhausted():
    """Mark attempt exhausted."""
    rm = PipelineRetryManager()
    pid = rm.create_policy("test")
    aid = rm.record_attempt(pid, "op", 1)

    assert rm.mark_exhausted(aid) is True
    assert rm.get_attempt(aid)["status"] == "exhausted"
    assert rm.mark_exhausted(aid) is False
    print("OK: mark exhausted")


def test_operation_attempts():
    """Get attempts for an operation."""
    rm = PipelineRetryManager()
    pid = rm.create_policy("test")
    rm.record_attempt(pid, "deploy", 1)
    rm.record_attempt(pid, "deploy", 2)
    rm.record_attempt(pid, "build", 1)

    attempts = rm.get_operation_attempts("deploy")
    assert len(attempts) == 2
    assert attempts[0]["attempt_number"] == 1
    print("OK: operation attempts")


def test_search_attempts():
    """Search attempts with filters."""
    rm = PipelineRetryManager()
    p1 = rm.create_policy("p1")
    p2 = rm.create_policy("p2")
    a1 = rm.record_attempt(p1, "deploy", 1, tags=["ci"])
    rm.mark_succeeded(a1)
    rm.record_attempt(p2, "build", 1)

    by_policy = rm.search_attempts(policy_id=p1)
    assert len(by_policy) == 1

    by_op = rm.search_attempts(operation="deploy")
    assert len(by_op) == 1

    by_status = rm.search_attempts(status="succeeded")
    assert len(by_status) == 1

    by_tag = rm.search_attempts(tag="ci")
    assert len(by_tag) == 1
    print("OK: search attempts")


def test_search_limit():
    """Search respects limit."""
    rm = PipelineRetryManager()
    pid = rm.create_policy("test")
    for i in range(20):
        rm.record_attempt(pid, "op", i)

    results = rm.search_attempts(limit=5)
    assert len(results) == 5
    print("OK: search limit")


def test_list_policies():
    """List policies with filters."""
    rm = PipelineRetryManager()
    rm.create_policy("a", tags=["api"])
    p2 = rm.create_policy("b")
    rm.disable_policy(p2)

    all_p = rm.list_policies()
    assert len(all_p) == 2

    active = rm.list_policies(status="active")
    assert len(active) == 1

    by_tag = rm.list_policies(tag="api")
    assert len(by_tag) == 1
    print("OK: list policies")


def test_retry_summary():
    """Get retry summary."""
    rm = PipelineRetryManager()
    pid = rm.create_policy("test")
    a1 = rm.record_attempt(pid, "op", 1)
    a2 = rm.record_attempt(pid, "op", 2)
    a3 = rm.record_attempt(pid, "op", 3)
    rm.mark_succeeded(a1)
    rm.mark_failed(a2)
    rm.mark_exhausted(a3)

    summary = rm.get_retry_summary(pid)
    assert summary["total"] == 3
    assert summary["succeeded"] == 1
    assert summary["failed"] == 1
    assert summary["exhausted"] == 1
    assert abs(summary["success_rate"] - 33.3) < 0.1
    print("OK: retry summary")


def test_callback():
    """Callback fires on policy create."""
    rm = PipelineRetryManager()
    fired = []
    rm.on_change("mon", lambda a, d: fired.append(a))

    rm.create_policy("test")
    assert "policy_created" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    rm = PipelineRetryManager()
    assert rm.on_change("mon", lambda a, d: None) is True
    assert rm.on_change("mon", lambda a, d: None) is False
    assert rm.remove_callback("mon") is True
    assert rm.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    rm = PipelineRetryManager()
    pid = rm.create_policy("test")
    rm.record_attempt(pid, "op", 1, status="succeeded")
    rm.record_attempt(pid, "op", 2, status="exhausted")

    stats = rm.get_stats()
    assert stats["total_policies_created"] == 1
    assert stats["total_attempts"] == 2
    assert stats["total_succeeded"] == 1
    assert stats["total_exhausted"] == 1
    assert stats["current_policies"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    rm = PipelineRetryManager()
    pid = rm.create_policy("test")
    rm.record_attempt(pid, "op", 1)

    rm.reset()
    assert rm.list_policies() == []
    assert rm.search_attempts() == []
    stats = rm.get_stats()
    assert stats["current_policies"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Retry Manager Tests ===\n")
    test_create_policy()
    test_invalid_policy()
    test_disable_enable_policy()
    test_record_attempt()
    test_invalid_attempt()
    test_backoff_calculation()
    test_should_retry()
    test_disabled_policy_no_retry()
    test_mark_succeeded()
    test_mark_failed()
    test_mark_exhausted()
    test_operation_attempts()
    test_search_attempts()
    test_search_limit()
    test_list_policies()
    test_retry_summary()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 20 TESTS PASSED ===")


if __name__ == "__main__":
    main()
