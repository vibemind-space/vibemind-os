"""Test agent error buffer -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_error_buffer import AgentErrorBuffer


def test_record_error():
    eb = AgentErrorBuffer()
    eid = eb.record_error("agent-1", "timeout", "Connection timed out")
    assert len(eid) > 0
    assert eid.startswith("aeb-")
    print("OK: record error")


def test_get_errors():
    eb = AgentErrorBuffer()
    eb.record_error("agent-1", "timeout", "msg1")
    eb.record_error("agent-1", "parse", "msg2")
    errors = eb.get_errors("agent-1")
    assert len(errors) == 2
    print("OK: get errors")


def test_get_errors_filtered():
    eb = AgentErrorBuffer()
    eb.record_error("agent-1", "timeout", "msg1")
    eb.record_error("agent-1", "parse", "msg2")
    eb.record_error("agent-1", "timeout", "msg3")
    errors = eb.get_errors("agent-1", error_type="timeout")
    assert len(errors) == 2
    print("OK: get errors filtered")


def test_get_errors_by_severity():
    eb = AgentErrorBuffer()
    eb.record_error("agent-1", "timeout", "msg1", severity="error")
    eb.record_error("agent-1", "parse", "msg2", severity="warning")
    errors = eb.get_errors("agent-1", severity="warning")
    assert len(errors) == 1
    print("OK: get errors by severity")


def test_get_latest_error():
    eb = AgentErrorBuffer()
    eb.record_error("agent-1", "timeout", "first")
    eb.record_error("agent-1", "parse", "second")
    latest = eb.get_latest_error("agent-1")
    assert latest is not None
    assert latest["message"] == "second"
    assert eb.get_latest_error("nonexistent") is None
    print("OK: get latest error")


def test_get_error_count():
    eb = AgentErrorBuffer()
    eb.record_error("agent-1", "timeout", "msg1")
    eb.record_error("agent-2", "parse", "msg2")
    assert eb.get_error_count() == 2
    assert eb.get_error_count("agent-1") == 1
    print("OK: get error count")


def test_clear_errors():
    eb = AgentErrorBuffer()
    eb.record_error("agent-1", "timeout", "msg1")
    eb.record_error("agent-1", "parse", "msg2")
    cleared = eb.clear_errors("agent-1")
    assert cleared == 2
    assert eb.get_error_count("agent-1") == 0
    print("OK: clear errors")


def test_list_agents():
    eb = AgentErrorBuffer()
    eb.record_error("agent-1", "timeout", "msg")
    eb.record_error("agent-2", "parse", "msg")
    agents = eb.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    eb = AgentErrorBuffer()
    fired = []
    eb.on_change("mon", lambda a, d: fired.append(a))
    eb.record_error("agent-1", "timeout", "msg")
    assert len(fired) >= 1
    assert eb.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    eb = AgentErrorBuffer()
    eb.record_error("agent-1", "timeout", "msg")
    stats = eb.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    eb = AgentErrorBuffer()
    eb.record_error("agent-1", "timeout", "msg")
    eb.reset()
    assert eb.get_error_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Error Buffer Tests ===\n")
    test_record_error()
    test_get_errors()
    test_get_errors_filtered()
    test_get_errors_by_severity()
    test_get_latest_error()
    test_get_error_count()
    test_clear_errors()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
