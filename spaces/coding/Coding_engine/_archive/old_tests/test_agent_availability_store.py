"""Test agent availability store -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_availability_store import AgentAvailabilityStore


def test_set_availability():
    a = AgentAvailabilityStore()
    rid = a.set_availability("agent-1", "available", reason="ready to work")
    assert len(rid) > 0
    assert rid.startswith("aav-")
    av = a.get_availability("agent-1")
    assert av is not None
    assert av["status"] == "available"
    print("OK: set availability")


def test_is_available():
    a = AgentAvailabilityStore()
    a.set_availability("agent-1", "available")
    a.set_availability("agent-2", "busy")
    assert a.is_available("agent-1") is True
    assert a.is_available("agent-2") is False
    assert a.is_available("nonexistent") is False
    print("OK: is available")


def test_get_available_agents():
    a = AgentAvailabilityStore()
    a.set_availability("agent-1", "available")
    a.set_availability("agent-2", "busy")
    a.set_availability("agent-3", "available")
    avail = a.get_available_agents()
    assert len(avail) == 2
    print("OK: get available agents")


def test_get_agents_by_status():
    a = AgentAvailabilityStore()
    a.set_availability("agent-1", "available")
    a.set_availability("agent-2", "busy")
    a.set_availability("agent-3", "offline")
    busy = a.get_agents_by_status("busy")
    assert len(busy) == 1
    print("OK: get agents by status")


def test_availability_history():
    a = AgentAvailabilityStore()
    a.set_availability("agent-1", "available")
    a.set_availability("agent-1", "busy")
    a.set_availability("agent-1", "available")
    hist = a.get_availability_history("agent-1")
    assert len(hist) >= 2
    print("OK: availability history")


def test_capacity():
    a = AgentAvailabilityStore()
    assert a.set_capacity("agent-1", 10) is True
    assert a.get_capacity("agent-1") == 10
    assert a.get_capacity("nonexistent") == 0
    print("OK: capacity")


def test_list_agents():
    a = AgentAvailabilityStore()
    a.set_availability("agent-1", "available")
    a.set_availability("agent-2", "busy")
    agents = a.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    a = AgentAvailabilityStore()
    fired = []
    a.on_change("mon", lambda act, d: fired.append(act))
    a.set_availability("agent-1", "available")
    assert len(fired) >= 1
    assert a.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    a = AgentAvailabilityStore()
    a.set_availability("agent-1", "available")
    stats = a.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    a = AgentAvailabilityStore()
    a.set_availability("agent-1", "available")
    a.reset()
    assert a.list_agents() == []
    print("OK: reset")


def main():
    print("=== Agent Availability Store Tests ===\n")
    test_set_availability()
    test_is_available()
    test_get_available_agents()
    test_get_agents_by_status()
    test_availability_history()
    test_capacity()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")


if __name__ == "__main__":
    main()
