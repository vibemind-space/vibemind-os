"""Test agent state machine."""
import sys
sys.path.insert(0, ".")

from src.services.agent_state_machine import AgentStateMachine


def test_create():
    """Create and retrieve machine."""
    sm = AgentStateMachine()
    mid = sm.create_machine("worker", "idle", states=["idle", "running", "done"], tags=["core"])
    assert mid.startswith("sm-")

    m = sm.get_machine("worker")
    assert m is not None
    assert m["name"] == "worker"
    assert m["current_state"] == "idle"
    assert "idle" in m["states"]

    assert sm.remove_machine("worker") is True
    assert sm.remove_machine("worker") is False
    print("OK: create")


def test_invalid_create():
    """Invalid create rejected."""
    sm = AgentStateMachine()
    assert sm.create_machine("", "idle") == ""
    assert sm.create_machine("m1", "") == ""
    print("OK: invalid create")


def test_duplicate():
    """Duplicate name rejected."""
    sm = AgentStateMachine()
    sm.create_machine("m1", "idle")
    assert sm.create_machine("m1", "idle") == ""
    print("OK: duplicate")


def test_max_machines():
    """Max machines enforced."""
    sm = AgentStateMachine(max_machines=2)
    sm.create_machine("a", "idle")
    sm.create_machine("b", "idle")
    assert sm.create_machine("c", "idle") == ""
    print("OK: max machines")


def test_add_state():
    """Add state to machine."""
    sm = AgentStateMachine()
    sm.create_machine("m1", "idle")

    assert sm.add_state("m1", "running") is True
    assert sm.add_state("m1", "running") is False  # duplicate
    assert sm.add_state("m1", "") is False
    assert sm.add_state("nonexistent", "s") is False

    m = sm.get_machine("m1")
    assert "running" in m["states"]
    print("OK: add state")


def test_add_transition():
    """Add transition between states."""
    sm = AgentStateMachine()
    sm.create_machine("m1", "idle", states=["idle", "running", "done"])

    assert sm.add_transition("m1", "idle", "running") is True
    assert sm.add_transition("m1", "running", "done") is True

    # invalid states
    assert sm.add_transition("m1", "idle", "nonexistent") is False
    assert sm.add_transition("nonexistent", "a", "b") is False
    print("OK: add transition")


def test_transition():
    """Execute valid transition."""
    sm = AgentStateMachine()
    sm.create_machine("m1", "idle", states=["idle", "running", "done"])
    sm.add_transition("m1", "idle", "running")
    sm.add_transition("m1", "running", "done")

    assert sm.transition("m1", "running") is True
    assert sm.get_state("m1") == "running"

    assert sm.transition("m1", "done") is True
    assert sm.get_state("m1") == "done"
    print("OK: transition")


def test_invalid_transition():
    """Invalid transition rejected."""
    sm = AgentStateMachine()
    sm.create_machine("m1", "idle", states=["idle", "running"])
    sm.add_transition("m1", "idle", "running")

    # Can't go to a state not in transitions
    assert sm.transition("m1", "nonexistent") is False

    # Can't skip states
    sm.add_state("m1", "done")
    sm.add_transition("m1", "running", "done")
    assert sm.transition("m1", "done") is False  # must go idle->running first
    print("OK: invalid transition")


def test_can_transition():
    """Check if transition is valid."""
    sm = AgentStateMachine()
    sm.create_machine("m1", "idle", states=["idle", "running"])
    sm.add_transition("m1", "idle", "running")

    assert sm.can_transition("m1", "running") is True
    assert sm.can_transition("m1", "idle") is False
    assert sm.can_transition("nonexistent", "x") is False
    print("OK: can transition")


def test_force_state():
    """Force state without validation."""
    sm = AgentStateMachine()
    sm.create_machine("m1", "idle", states=["idle", "running", "done"])

    assert sm.force_state("m1", "done") is True
    assert sm.get_state("m1") == "done"

    assert sm.force_state("m1", "nonexistent") is False
    assert sm.force_state("nonexistent", "idle") is False
    print("OK: force state")


def test_get_state():
    """Get current state."""
    sm = AgentStateMachine()
    sm.create_machine("m1", "idle")
    assert sm.get_state("m1") == "idle"
    assert sm.get_state("nonexistent") == ""
    print("OK: get state")


def test_available_transitions():
    """Get available transitions from current state."""
    sm = AgentStateMachine()
    sm.create_machine("m1", "idle", states=["idle", "running", "paused"])
    sm.add_transition("m1", "idle", "running")
    sm.add_transition("m1", "idle", "paused")

    avail = sm.get_available_transitions("m1")
    assert sorted(avail) == ["paused", "running"]

    assert sm.get_available_transitions("nonexistent") == []
    print("OK: available transitions")


def test_list_machines():
    """List machines with filters."""
    sm = AgentStateMachine()
    sm.create_machine("m1", "idle", tags=["core"])
    sm.create_machine("m2", "running", states=["running"])

    all_m = sm.list_machines()
    assert len(all_m) == 2

    by_state = sm.list_machines(state="idle")
    assert len(by_state) == 1

    by_tag = sm.list_machines(tag="core")
    assert len(by_tag) == 1
    print("OK: list machines")


def test_history():
    """History tracking."""
    sm = AgentStateMachine()
    sm.create_machine("m1", "idle", states=["idle", "running"])
    sm.add_transition("m1", "idle", "running")
    sm.transition("m1", "running")

    hist = sm.get_history()
    assert len(hist) == 1

    by_machine = sm.get_history(machine_name="m1")
    assert len(by_machine) == 1

    limited = sm.get_history(limit=1)
    assert len(limited) == 1
    print("OK: history")


def test_callback():
    """Callback fires on events."""
    sm = AgentStateMachine()
    fired = []
    sm.on_change("mon", lambda a, d: fired.append(a))

    sm.create_machine("m1", "idle", states=["idle", "running"])
    assert "machine_created" in fired

    sm.add_transition("m1", "idle", "running")
    sm.transition("m1", "running")
    assert "state_changed" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    sm = AgentStateMachine()
    assert sm.on_change("mon", lambda a, d: None) is True
    assert sm.on_change("mon", lambda a, d: None) is False
    assert sm.remove_callback("mon") is True
    assert sm.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    sm = AgentStateMachine()
    sm.create_machine("m1", "idle", states=["idle", "running"])
    sm.add_transition("m1", "idle", "running")
    sm.transition("m1", "running")

    stats = sm.get_stats()
    assert stats["current_machines"] == 1
    assert stats["total_created"] == 1
    assert stats["total_transitions"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    sm = AgentStateMachine()
    sm.create_machine("m1", "idle")

    sm.reset()
    assert sm.list_machines() == []
    stats = sm.get_stats()
    assert stats["current_machines"] == 0
    assert stats["total_created"] == 0
    print("OK: reset")


def main():
    print("=== Agent State Machine Tests ===\n")
    test_create()
    test_invalid_create()
    test_duplicate()
    test_max_machines()
    test_add_state()
    test_add_transition()
    test_transition()
    test_invalid_transition()
    test_can_transition()
    test_force_state()
    test_get_state()
    test_available_transitions()
    test_list_machines()
    test_history()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 18 TESTS PASSED ===")


if __name__ == "__main__":
    main()
