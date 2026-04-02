"""Test pipeline retry handler."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_retry_handler import PipelineRetryHandler


def test_create_policy():
    """Create and remove policy."""
    rh = PipelineRetryHandler()
    pid = rh.create_policy("api_retry", max_retries=5,
                           backoff_type="exponential",
                           base_delay=2.0, max_delay=120.0,
                           retry_on=["timeout"], tags=["api"])
    assert pid.startswith("rpol-")

    p = rh.get_policy(pid)
    assert p is not None
    assert p["name"] == "api_retry"
    assert p["max_retries"] == 5
    assert p["backoff_type"] == "exponential"
    assert p["base_delay"] == 2.0

    assert rh.remove_policy(pid) is True
    assert rh.remove_policy(pid) is False
    print("OK: create policy")


def test_invalid_policy():
    """Invalid policy rejected."""
    rh = PipelineRetryHandler()
    assert rh.create_policy("") == ""
    assert rh.create_policy("x", backoff_type="invalid") == ""
    assert rh.create_policy("x", max_retries=0) == ""
    assert rh.create_policy("x", base_delay=0) == ""
    assert rh.create_policy("x", max_delay=0) == ""
    print("OK: invalid policy")


def test_max_policies():
    """Max policies enforced."""
    rh = PipelineRetryHandler(max_policies=2)
    rh.create_policy("a")
    rh.create_policy("b")
    assert rh.create_policy("c") == ""
    print("OK: max policies")


def test_list_policies():
    """List policies with filter."""
    rh = PipelineRetryHandler()
    rh.create_policy("a", tags=["api"])
    rh.create_policy("b")

    all_p = rh.list_policies()
    assert len(all_p) == 2

    by_tag = rh.list_policies(tag="api")
    assert len(by_tag) == 1
    print("OK: list policies")


def test_create_record():
    """Create and remove record."""
    rh = PipelineRetryHandler()
    rid = rh.create_record("build_image", source="agent-1",
                           tags=["ci"], max_retries=3)
    assert rid.startswith("rr-")

    r = rh.get_record(rid)
    assert r is not None
    assert r["operation"] == "build_image"
    assert r["status"] == "pending"
    assert r["attempt"] == 0
    assert r["max_retries"] == 3
    assert r["source"] == "agent-1"

    assert rh.remove_record(rid) is True
    assert rh.remove_record(rid) is False
    print("OK: create record")


def test_invalid_record():
    """Invalid record rejected."""
    rh = PipelineRetryHandler()
    assert rh.create_record("") == ""
    print("OK: invalid record")


def test_record_with_policy():
    """Record uses policy max_retries."""
    rh = PipelineRetryHandler()
    pid = rh.create_policy("api", max_retries=7)
    rid = rh.create_record("call_api", policy_id=pid)

    r = rh.get_record(rid)
    assert r["max_retries"] == 7
    print("OK: record with policy")


def test_retry_attempts():
    """Record retry attempts."""
    rh = PipelineRetryHandler()
    rid = rh.create_record("deploy", max_retries=3)

    assert rh.record_attempt(rid, error="timeout") is True
    r = rh.get_record(rid)
    assert r["status"] == "retrying"
    assert r["attempt"] == 1
    assert r["last_error"] == "timeout"
    assert len(r["errors"]) == 1

    rh.record_attempt(rid, error="refused")
    r = rh.get_record(rid)
    assert r["attempt"] == 2
    assert r["last_error"] == "refused"
    assert len(r["errors"]) == 2
    print("OK: retry attempts")


def test_exhaust_retries():
    """Exhaust all retries."""
    rh = PipelineRetryHandler()
    rid = rh.create_record("flaky_op", max_retries=2)

    rh.record_attempt(rid, error="fail1")
    assert rh.get_record(rid)["status"] == "retrying"

    rh.record_attempt(rid, error="fail2")
    r = rh.get_record(rid)
    assert r["status"] == "exhausted"
    assert r["attempt"] == 2

    # Can't retry after exhausted
    assert rh.record_attempt(rid) is False
    print("OK: exhaust retries")


def test_mark_succeeded():
    """Mark retry as succeeded."""
    rh = PipelineRetryHandler()
    rid = rh.create_record("op", max_retries=5)
    rh.record_attempt(rid, error="try1")
    rh.record_attempt(rid, error="try2")

    assert rh.mark_succeeded(rid) is True
    r = rh.get_record(rid)
    assert r["status"] == "succeeded"
    assert r["attempt"] == 2

    assert rh.mark_succeeded(rid) is False
    print("OK: mark succeeded")


def test_cancel_record():
    """Cancel a retry record."""
    rh = PipelineRetryHandler()
    rid = rh.create_record("op")
    rh.record_attempt(rid, error="err")

    assert rh.cancel_record(rid) is True
    assert rh.get_record(rid)["status"] == "cancelled"
    assert rh.cancel_record(rid) is False
    print("OK: cancel record")


def test_dead_letter():
    """Exhausted records go to dead letter."""
    rh = PipelineRetryHandler()
    rid = rh.create_record("bad_op", max_retries=1, source="agent-1")
    rh.record_attempt(rid, error="fatal")

    dlq = rh.get_dead_letter_queue()
    assert len(dlq) == 1
    assert dlq[0]["operation"] == "bad_op"
    assert dlq[0]["last_error"] == "fatal"

    count = rh.clear_dead_letter()
    assert count == 1
    assert len(rh.get_dead_letter_queue()) == 0
    print("OK: dead letter")


def test_ready_retries():
    """Get records ready for retry."""
    rh = PipelineRetryHandler()
    rid = rh.create_record("op", max_retries=5)
    rh.record_attempt(rid, error="err")

    # next_retry_at is in the future, but very close
    # In practice it should be ready almost immediately with default backoff
    import time
    time.sleep(0.01)
    # Force next_retry_at to now
    rh._records[rid].next_retry_at = time.time() - 1

    ready = rh.get_ready_retries()
    assert len(ready) == 1
    assert ready[0]["record_id"] == rid
    print("OK: ready retries")


def test_backoff_fixed():
    """Fixed backoff delay."""
    rh = PipelineRetryHandler()
    pid = rh.create_policy("fix", backoff_type="fixed",
                           base_delay=5.0)
    rid = rh.create_record("op", policy_id=pid)
    rh.record_attempt(rid)

    delay = rh.calculate_delay(rid)
    assert delay == 5.0
    print("OK: backoff fixed")


def test_backoff_linear():
    """Linear backoff delay."""
    rh = PipelineRetryHandler()
    pid = rh.create_policy("lin", backoff_type="linear",
                           base_delay=2.0, max_delay=100.0)
    rid = rh.create_record("op", policy_id=pid)
    rh.record_attempt(rid)  # attempt 1
    delay1 = rh.calculate_delay(rid)
    rh.record_attempt(rid)  # attempt 2
    delay2 = rh.calculate_delay(rid)

    assert delay1 == 2.0  # 2.0 * 1
    assert delay2 == 4.0  # 2.0 * 2
    print("OK: backoff linear")


def test_backoff_exponential():
    """Exponential backoff delay."""
    rh = PipelineRetryHandler()
    pid = rh.create_policy("exp", backoff_type="exponential",
                           base_delay=1.0, max_delay=100.0)
    rid = rh.create_record("op", policy_id=pid)
    rh.record_attempt(rid)  # attempt 1
    delay1 = rh.calculate_delay(rid)
    rh.record_attempt(rid)  # attempt 2
    delay2 = rh.calculate_delay(rid)
    rh.record_attempt(rid)  # attempt 3
    delay3 = rh.calculate_delay(rid)

    assert delay1 == 1.0   # 1.0 * 2^0
    assert delay2 == 2.0   # 1.0 * 2^1
    assert delay3 == 4.0   # 1.0 * 2^2
    print("OK: backoff exponential")


def test_backoff_max_cap():
    """Backoff respects max_delay."""
    rh = PipelineRetryHandler()
    pid = rh.create_policy("cap", backoff_type="exponential",
                           base_delay=10.0, max_delay=20.0,
                           max_retries=10)
    rid = rh.create_record("op", policy_id=pid)
    rh.record_attempt(rid)  # 1: 10
    rh.record_attempt(rid)  # 2: 20
    rh.record_attempt(rid)  # 3: would be 40, capped at 20
    delay = rh.calculate_delay(rid)
    assert delay == 20.0
    print("OK: backoff max cap")


def test_default_backoff():
    """Default backoff without policy."""
    rh = PipelineRetryHandler()
    rid = rh.create_record("op", max_retries=10)
    rh.record_attempt(rid)  # attempt 1
    delay = rh.calculate_delay(rid)
    assert delay == 2.0  # 2^1
    rh.record_attempt(rid)  # attempt 2
    delay = rh.calculate_delay(rid)
    assert delay == 4.0  # 2^2
    print("OK: default backoff")


def test_list_records():
    """List records with filters."""
    rh = PipelineRetryHandler()
    r1 = rh.create_record("build", source="ci")
    r2 = rh.create_record("deploy", source="cd")
    rh.record_attempt(r1)
    rh.mark_succeeded(r1)

    all_r = rh.list_records()
    assert len(all_r) == 2

    by_status = rh.list_records(status="succeeded")
    assert len(by_status) == 1

    by_op = rh.list_records(operation="deploy")
    assert len(by_op) == 1

    by_source = rh.list_records(source="ci")
    assert len(by_source) == 1
    print("OK: list records")


def test_retry_rate():
    """Get retry success rate."""
    rh = PipelineRetryHandler()
    r1 = rh.create_record("op", max_retries=5)
    rh.record_attempt(r1)
    rh.mark_succeeded(r1)

    r2 = rh.create_record("op", max_retries=1)
    rh.record_attempt(r2)

    rate = rh.get_retry_rate()
    assert rate["total"] == 2
    assert rate["succeeded"] == 1
    assert rate["exhausted"] == 1
    assert rate["success_rate"] == 50.0
    print("OK: retry rate")


def test_retry_rate_by_operation():
    """Retry rate filtered by operation."""
    rh = PipelineRetryHandler()
    r1 = rh.create_record("build", max_retries=5)
    rh.record_attempt(r1)
    rh.mark_succeeded(r1)

    r2 = rh.create_record("deploy", max_retries=1)
    rh.record_attempt(r2)

    rate = rh.get_retry_rate(operation="build")
    assert rate["total"] == 1
    assert rate["success_rate"] == 100.0
    print("OK: retry rate by operation")


def test_exhausted_callback():
    """Callback fires on exhaustion."""
    rh = PipelineRetryHandler()
    fired = []
    rh.on_change("mon", lambda a, d: fired.append(a))

    rid = rh.create_record("op", max_retries=1)
    rh.record_attempt(rid, error="err")

    assert "retries_exhausted" in fired
    print("OK: exhausted callback")


def test_succeeded_callback():
    """Callback fires on success."""
    rh = PipelineRetryHandler()
    fired = []
    rh.on_change("mon", lambda a, d: fired.append(a))

    rid = rh.create_record("op")
    rh.record_attempt(rid)
    rh.mark_succeeded(rid)

    assert "retry_succeeded" in fired
    print("OK: succeeded callback")


def test_callbacks():
    """Callback registration."""
    rh = PipelineRetryHandler()
    assert rh.on_change("mon", lambda a, d: None) is True
    assert rh.on_change("mon", lambda a, d: None) is False
    assert rh.remove_callback("mon") is True
    assert rh.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    rh = PipelineRetryHandler()
    pid = rh.create_policy("p")
    r1 = rh.create_record("a", max_retries=5)
    rh.record_attempt(r1)
    rh.mark_succeeded(r1)

    r2 = rh.create_record("b", max_retries=1)
    rh.record_attempt(r2)

    r3 = rh.create_record("c")
    rh.cancel_record(r3)

    stats = rh.get_stats()
    assert stats["total_records_created"] == 3
    assert stats["total_retries_attempted"] == 2
    assert stats["total_succeeded"] == 1
    assert stats["total_exhausted"] == 1
    assert stats["total_cancelled"] == 1
    assert stats["current_records"] == 3
    assert stats["current_policies"] == 1
    assert stats["dead_letter_size"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    rh = PipelineRetryHandler()
    rh.create_policy("p")
    rh.create_record("op")

    rh.reset()
    assert rh.list_policies() == []
    assert rh.list_records() == []
    assert rh.get_dead_letter_queue() == []
    stats = rh.get_stats()
    assert stats["current_records"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Retry Handler Tests ===\n")
    test_create_policy()
    test_invalid_policy()
    test_max_policies()
    test_list_policies()
    test_create_record()
    test_invalid_record()
    test_record_with_policy()
    test_retry_attempts()
    test_exhaust_retries()
    test_mark_succeeded()
    test_cancel_record()
    test_dead_letter()
    test_ready_retries()
    test_backoff_fixed()
    test_backoff_linear()
    test_backoff_exponential()
    test_backoff_max_cap()
    test_default_backoff()
    test_list_records()
    test_retry_rate()
    test_retry_rate_by_operation()
    test_exhausted_callback()
    test_succeeded_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 26 TESTS PASSED ===")


if __name__ == "__main__":
    main()
