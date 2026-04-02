"""Test agent fault detector -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_fault_detector import AgentFaultDetector


def test_register_agent():
    fd = AgentFaultDetector()
    eid = fd.register_agent("agent-1", error_threshold=0.5, max_consecutive_failures=3)
    assert len(eid) > 0
    assert eid.startswith("afd2-")
    print("OK: register agent")


def test_record_success():
    fd = AgentFaultDetector()
    fd.register_agent("agent-1")
    fd.record_success("agent-1")
    assert fd.get_consecutive_failures("agent-1") == 0
    print("OK: record success")


def test_record_failure():
    fd = AgentFaultDetector()
    fd.register_agent("agent-1")
    fd.record_failure("agent-1", reason="timeout")
    assert fd.get_consecutive_failures("agent-1") == 1
    print("OK: record failure")


def test_is_faulty_consecutive():
    fd = AgentFaultDetector()
    fd.register_agent("agent-1", error_threshold=1.0, max_consecutive_failures=3)
    fd.record_failure("agent-1")
    fd.record_failure("agent-1")
    assert fd.is_faulty("agent-1") is False  # 2 < 3, and error_rate <= 1.0
    fd.record_failure("agent-1")
    assert fd.is_faulty("agent-1") is True  # 3 >= 3
    print("OK: is faulty consecutive")


def test_is_faulty_error_rate():
    fd = AgentFaultDetector()
    fd.register_agent("agent-1", error_threshold=0.5, max_consecutive_failures=10)
    fd.record_success("agent-1")
    fd.record_failure("agent-1")
    fd.record_failure("agent-1")
    # 2 failures, 1 success = ~66% error rate > 50% threshold
    assert fd.is_faulty("agent-1") is True
    print("OK: is faulty error rate")


def test_get_error_rate():
    fd = AgentFaultDetector()
    fd.register_agent("agent-1")
    fd.record_success("agent-1")
    fd.record_success("agent-1")
    fd.record_failure("agent-1")
    rate = fd.get_error_rate("agent-1")
    assert abs(rate - 1/3) < 0.01
    print("OK: get error rate")


def test_reset_agent():
    fd = AgentFaultDetector()
    fd.register_agent("agent-1")
    fd.record_failure("agent-1")
    fd.record_failure("agent-1")
    assert fd.reset_agent("agent-1") is True
    assert fd.get_consecutive_failures("agent-1") == 0
    print("OK: reset agent")


def test_success_resets_consecutive():
    fd = AgentFaultDetector()
    fd.register_agent("agent-1", max_consecutive_failures=5)
    fd.record_failure("agent-1")
    fd.record_failure("agent-1")
    fd.record_success("agent-1")
    assert fd.get_consecutive_failures("agent-1") == 0
    print("OK: success resets consecutive")


def test_list_agents():
    fd = AgentFaultDetector()
    fd.register_agent("agent-1")
    fd.register_agent("agent-2")
    agents = fd.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    fd = AgentFaultDetector()
    fired = []
    fd.on_change("mon", lambda a, d: fired.append(a))
    fd.register_agent("agent-1")
    assert len(fired) >= 1
    assert fd.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    fd = AgentFaultDetector()
    fd.register_agent("agent-1")
    stats = fd.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    fd = AgentFaultDetector()
    fd.register_agent("agent-1")
    fd.reset()
    assert fd.get_agent_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Fault Detector Tests ===\n")
    test_register_agent()
    test_record_success()
    test_record_failure()
    test_is_faulty_consecutive()
    test_is_faulty_error_rate()
    test_get_error_rate()
    test_reset_agent()
    test_success_resets_consecutive()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 12 TESTS PASSED ===")


if __name__ == "__main__":
    main()
