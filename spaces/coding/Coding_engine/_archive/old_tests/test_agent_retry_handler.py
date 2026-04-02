"""Test agent retry handler -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_retry_handler import AgentRetryHandler


def test_create_policy():
    rh = AgentRetryHandler()
    pid = rh.create_policy("agent-1", max_retries=3, backoff="linear", base_delay=1.0)
    assert len(pid) > 0
    assert pid.startswith("arh-")
    print("OK: create policy")


def test_record_attempt():
    rh = AgentRetryHandler()
    rh.create_policy("agent-1", max_retries=3)
    aid = rh.record_attempt("agent-1", "task-A", success=False)
    assert len(aid) > 0
    print("OK: record attempt")


def test_should_retry():
    rh = AgentRetryHandler()
    rh.create_policy("agent-1", max_retries=3)
    rh.record_attempt("agent-1", "task-A", success=False)
    assert rh.should_retry("agent-1", "task-A") is True
    rh.record_attempt("agent-1", "task-A", success=False)
    rh.record_attempt("agent-1", "task-A", success=False)
    assert rh.should_retry("agent-1", "task-A") is False
    print("OK: should retry")


def test_get_attempt_count():
    rh = AgentRetryHandler()
    rh.create_policy("agent-1", max_retries=5)
    rh.record_attempt("agent-1", "task-A", success=False)
    rh.record_attempt("agent-1", "task-A", success=False)
    assert rh.get_attempt_count("agent-1", "task-A") == 2
    print("OK: get attempt count")


def test_get_next_delay_linear():
    rh = AgentRetryHandler()
    rh.create_policy("agent-1", max_retries=5, backoff="linear", base_delay=2.0)
    rh.record_attempt("agent-1", "task-A", success=False)
    delay = rh.get_next_delay("agent-1", "task-A")
    assert delay >= 2.0
    print("OK: get next delay linear")


def test_get_next_delay_exponential():
    rh = AgentRetryHandler()
    rh.create_policy("agent-1", max_retries=5, backoff="exponential", base_delay=1.0)
    rh.record_attempt("agent-1", "task-A", success=False)
    rh.record_attempt("agent-1", "task-A", success=False)
    delay = rh.get_next_delay("agent-1", "task-A")
    assert delay >= 2.0  # exponential: base * 2^(attempt-1)
    print("OK: get next delay exponential")


def test_reset_task():
    rh = AgentRetryHandler()
    rh.create_policy("agent-1", max_retries=3)
    rh.record_attempt("agent-1", "task-A", success=False)
    rh.record_attempt("agent-1", "task-A", success=False)
    assert rh.reset_task("agent-1", "task-A") is True
    assert rh.get_attempt_count("agent-1", "task-A") == 0
    print("OK: reset task")


def test_success_no_retry():
    rh = AgentRetryHandler()
    rh.create_policy("agent-1", max_retries=3)
    rh.record_attempt("agent-1", "task-A", success=False)
    rh.record_attempt("agent-1", "task-A", success=True)
    # After success, no retry needed
    assert rh.should_retry("agent-1", "task-A") is False
    print("OK: success no retry")


def test_list_agents():
    rh = AgentRetryHandler()
    rh.create_policy("agent-1", max_retries=3)
    rh.create_policy("agent-2", max_retries=5)
    agents = rh.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    rh = AgentRetryHandler()
    fired = []
    rh.on_change("mon", lambda a, d: fired.append(a))
    rh.create_policy("agent-1")
    assert len(fired) >= 1
    assert rh.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    rh = AgentRetryHandler()
    rh.create_policy("agent-1")
    stats = rh.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    rh = AgentRetryHandler()
    rh.create_policy("agent-1")
    rh.reset()
    assert rh.get_policy_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Retry Handler Tests ===\n")
    test_create_policy()
    test_record_attempt()
    test_should_retry()
    test_get_attempt_count()
    test_get_next_delay_linear()
    test_get_next_delay_exponential()
    test_reset_task()
    test_success_no_retry()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 12 TESTS PASSED ===")


if __name__ == "__main__":
    main()
