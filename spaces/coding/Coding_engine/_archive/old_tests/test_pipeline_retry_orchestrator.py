"""Test pipeline retry orchestrator."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_retry_orchestrator import PipelineRetryOrchestrator


def test_create_policy():
    """Create and remove policies."""
    r = PipelineRetryOrchestrator()
    pid = r.create_policy("default", max_retries=5, base_delay=1.0, backoff="exponential")
    assert pid.startswith("rpol-")

    policy = r.get_policy(pid)
    assert policy is not None
    assert policy["max_retries"] == 5
    assert policy["backoff"] == "exponential"

    assert r.remove_policy(pid) is True
    assert r.remove_policy(pid) is False
    print("OK: create policy")


def test_invalid_policy():
    """Invalid policies rejected."""
    r = PipelineRetryOrchestrator()
    assert r.create_policy("bad", backoff="invalid") == ""
    assert r.create_policy("bad", max_retries=0) == ""
    assert r.create_policy("bad", base_delay=-1) == ""
    print("OK: invalid policy")


def test_list_policies():
    """List policies."""
    r = PipelineRetryOrchestrator()
    r.create_policy("A")
    r.create_policy("B")
    assert len(r.list_policies()) == 2
    print("OK: list policies")


def test_fixed_delay():
    """Fixed backoff gives constant delay."""
    r = PipelineRetryOrchestrator()
    pid = r.create_policy("fixed", base_delay=2.0, backoff="fixed", jitter=0.0)

    d1 = r.calculate_delay(pid, 1)
    d2 = r.calculate_delay(pid, 3)
    assert d1 == 2.0
    assert d2 == 2.0
    print("OK: fixed delay")


def test_linear_delay():
    """Linear backoff grows linearly."""
    r = PipelineRetryOrchestrator()
    pid = r.create_policy("linear", base_delay=1.0, backoff="linear", jitter=0.0)

    d1 = r.calculate_delay(pid, 1)
    d2 = r.calculate_delay(pid, 3)
    assert d1 == 1.0
    assert d2 == 3.0
    print("OK: linear delay")


def test_exponential_delay():
    """Exponential backoff doubles each time."""
    r = PipelineRetryOrchestrator()
    pid = r.create_policy("exp", base_delay=1.0, backoff="exponential",
                          jitter=0.0, max_delay=100.0)

    d1 = r.calculate_delay(pid, 1)
    d2 = r.calculate_delay(pid, 2)
    d3 = r.calculate_delay(pid, 3)
    assert d1 == 1.0
    assert d2 == 2.0
    assert d3 == 4.0
    print("OK: exponential delay")


def test_max_delay_cap():
    """Delay is capped at max_delay."""
    r = PipelineRetryOrchestrator()
    pid = r.create_policy("exp", base_delay=10.0, max_delay=20.0,
                          backoff="exponential", jitter=0.0)

    d = r.calculate_delay(pid, 5)
    assert d <= 20.0
    print("OK: max delay cap")


def test_start_session():
    """Start a retry session."""
    r = PipelineRetryOrchestrator()
    pid = r.create_policy("default")
    sid = r.start_session("build", pid)
    assert sid.startswith("rsess-")

    session = r.get_session(sid)
    assert session is not None
    assert session["task_name"] == "build"
    assert session["status"] == "active"
    assert session["current_attempt"] == 0
    print("OK: start session")


def test_start_session_invalid_policy():
    """Can't start session with invalid policy."""
    r = PipelineRetryOrchestrator()
    assert r.start_session("build", "fake") == ""
    print("OK: start session invalid policy")


def test_next_attempt():
    """Get next retry attempt."""
    r = PipelineRetryOrchestrator()
    pid = r.create_policy("default", max_retries=3, base_delay=1.0,
                          backoff="fixed", jitter=0.0)
    sid = r.start_session("build", pid)

    a1 = r.next_attempt(sid)
    assert a1 is not None
    assert a1["attempt_number"] == 1
    assert a1["remaining_retries"] == 2

    a2 = r.next_attempt(sid)
    assert a2["attempt_number"] == 2
    assert a2["remaining_retries"] == 1
    print("OK: next attempt")


def test_exhaust_retries():
    """Session exhausts when max retries reached."""
    r = PipelineRetryOrchestrator()
    pid = r.create_policy("default", max_retries=2)
    sid = r.start_session("build", pid)

    r.next_attempt(sid)
    r.record_failure(sid, "err1")
    r.next_attempt(sid)
    r.record_failure(sid, "err2")

    # Should be exhausted now
    a3 = r.next_attempt(sid)
    assert a3 is None
    assert r.get_session(sid)["status"] == "exhausted"
    print("OK: exhaust retries")


def test_record_success():
    """Record success ends session."""
    r = PipelineRetryOrchestrator()
    pid = r.create_policy("default")
    sid = r.start_session("build", pid)

    r.next_attempt(sid)
    assert r.record_success(sid) is True
    assert r.get_session(sid)["status"] == "succeeded"

    # Can't succeed again
    assert r.record_success(sid) is False
    print("OK: record success")


def test_record_failure():
    """Record failure on attempt."""
    r = PipelineRetryOrchestrator()
    pid = r.create_policy("default")
    sid = r.start_session("build", pid)

    r.next_attempt(sid)
    assert r.record_failure(sid, "timeout") is True

    attempts = r.get_session_attempts(sid)
    assert len(attempts) == 1
    assert attempts[0]["status"] == "failed"
    assert attempts[0]["error"] == "timeout"
    print("OK: record failure")


def test_cancel_session():
    """Cancel a session."""
    r = PipelineRetryOrchestrator()
    pid = r.create_policy("default")
    sid = r.start_session("build", pid)

    assert r.cancel_session(sid) is True
    assert r.get_session(sid)["status"] == "cancelled"
    assert r.cancel_session(sid) is False
    print("OK: cancel session")


def test_should_retry():
    """Check retry eligibility."""
    r = PipelineRetryOrchestrator()
    pid = r.create_policy("default", max_retries=2, retry_on=["timeout", "network"])
    sid = r.start_session("build", pid)

    assert r.should_retry(sid, "timeout") is True
    assert r.should_retry(sid, "syntax") is False  # Not in retry_on

    r.next_attempt(sid)
    r.next_attempt(sid)
    assert r.should_retry(sid) is False  # Exhausted
    print("OK: should retry")


def test_should_retry_no_filter():
    """Retry on any error when no filter set."""
    r = PipelineRetryOrchestrator()
    pid = r.create_policy("default", max_retries=3)
    sid = r.start_session("build", pid)

    assert r.should_retry(sid, "anything") is True
    print("OK: should retry no filter")


def test_list_sessions():
    """List sessions with filter."""
    r = PipelineRetryOrchestrator()
    pid = r.create_policy("default")
    s1 = r.start_session("A", pid)
    s2 = r.start_session("B", pid)
    r.cancel_session(s2)

    all_s = r.list_sessions()
    assert len(all_s) == 2

    active = r.list_sessions(status="active")
    assert len(active) == 1
    print("OK: list sessions")


def test_get_attempt():
    """Get attempt info."""
    r = PipelineRetryOrchestrator()
    pid = r.create_policy("default")
    sid = r.start_session("build", pid)

    a = r.next_attempt(sid)
    info = r.get_attempt(a["attempt_id"])
    assert info is not None
    assert info["attempt_number"] == 1
    assert info["status"] == "pending"
    print("OK: get attempt")


def test_session_attempts():
    """Get all attempts for a session."""
    r = PipelineRetryOrchestrator()
    pid = r.create_policy("default", max_retries=3)
    sid = r.start_session("build", pid)

    r.next_attempt(sid)
    r.record_failure(sid, "err1")
    r.next_attempt(sid)
    r.record_success(sid)

    attempts = r.get_session_attempts(sid)
    assert len(attempts) == 2
    assert attempts[0]["status"] == "failed"
    assert attempts[1]["status"] == "success"
    print("OK: session attempts")


def test_callbacks():
    """Event callbacks fire."""
    r = PipelineRetryOrchestrator()
    pid = r.create_policy("default", max_retries=1)

    fired = []
    assert r.on_event("mon", lambda evt, sid, name: fired.append((evt, name))) is True
    assert r.on_event("mon", lambda e, s, n: None) is False

    sid = r.start_session("build", pid)
    r.next_attempt(sid)
    r.record_failure(sid)
    r.next_attempt(sid)  # Exhausted

    assert len(fired) == 1
    assert fired[0] == ("exhausted", "build")

    assert r.remove_callback("mon") is True
    assert r.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    r = PipelineRetryOrchestrator()
    pid = r.create_policy("default", max_retries=2)

    s1 = r.start_session("A", pid)
    r.next_attempt(s1)
    r.record_success(s1)

    s2 = r.start_session("B", pid)
    r.next_attempt(s2)
    r.record_failure(s2)
    r.next_attempt(s2)
    r.record_failure(s2)
    r.next_attempt(s2)  # Exhausted

    stats = r.get_stats()
    assert stats["total_sessions"] == 2
    assert stats["total_attempts"] == 3
    assert stats["total_successes"] == 1
    assert stats["total_exhausted"] == 1
    assert stats["success_rate"] == 50.0
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    r = PipelineRetryOrchestrator()
    pid = r.create_policy("default")
    r.start_session("build", pid)

    r.reset()
    assert r.list_policies() == []
    assert r.list_sessions() == []
    stats = r.get_stats()
    assert stats["total_sessions"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Retry Orchestrator Tests ===\n")
    test_create_policy()
    test_invalid_policy()
    test_list_policies()
    test_fixed_delay()
    test_linear_delay()
    test_exponential_delay()
    test_max_delay_cap()
    test_start_session()
    test_start_session_invalid_policy()
    test_next_attempt()
    test_exhaust_retries()
    test_record_success()
    test_record_failure()
    test_cancel_session()
    test_should_retry()
    test_should_retry_no_filter()
    test_list_sessions()
    test_get_attempt()
    test_session_attempts()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 22 TESTS PASSED ===")


if __name__ == "__main__":
    main()
