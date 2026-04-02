"""Test capability negotiation protocol."""
import sys
sys.path.insert(0, ".")

from src.services.capability_negotiation import (
    CapabilityNegotiationProtocol,
    Proficiency,
    NegotiationStatus,
)


def test_advertise():
    """Advertise agent capabilities."""
    proto = CapabilityNegotiationProtocol()
    is_new = proto.advertise("Builder", {"code_gen": 5, "testing": 3}, max_load=5)
    assert is_new is True

    # Update existing
    is_new2 = proto.advertise("Builder", {"code_gen": 5, "testing": 4})
    assert is_new2 is False

    agent = proto.get_agent("Builder")
    assert agent is not None
    assert agent["capabilities"]["testing"] == 4
    print("OK: advertise")


def test_withdraw():
    """Withdraw agent."""
    proto = CapabilityNegotiationProtocol()
    proto.advertise("Agent", {"x": 1})
    assert proto.withdraw("Agent") is True
    assert proto.get_agent("Agent") is None
    assert proto.withdraw("Agent") is False
    print("OK: withdraw")


def test_set_availability():
    """Set agent availability."""
    proto = CapabilityNegotiationProtocol()
    proto.advertise("Agent", {"x": 1})

    assert proto.set_availability("Agent", False) is True
    assert proto.get_agent("Agent")["available"] is False
    assert proto.set_availability("nope", True) is False
    print("OK: set availability")


def test_update_load():
    """Update agent load."""
    proto = CapabilityNegotiationProtocol()
    proto.advertise("Agent", {"x": 1}, max_load=5)

    assert proto.update_load("Agent", 3) is True
    assert proto.get_agent("Agent")["current_load"] == 3
    assert proto.get_agent("Agent")["load_ratio"] == 0.6
    print("OK: update load")


def test_list_agents():
    """List agents with filters."""
    proto = CapabilityNegotiationProtocol()
    proto.advertise("Builder", {"code_gen": 5, "testing": 3}, max_load=5)
    proto.advertise("Tester", {"testing": 5, "code_gen": 1}, max_load=5)
    proto.advertise("Busy", {"code_gen": 3}, max_load=1)
    proto.update_load("Busy", 1)  # At max

    all_agents = proto.list_agents()
    assert len(all_agents) == 3

    available = proto.list_agents(available_only=True)
    assert len(available) == 2  # Busy excluded

    coders = proto.list_agents(capability="code_gen", min_proficiency=3)
    assert len(coders) == 2  # Builder(5) and Busy(3), Tester(1) excluded
    print("OK: list agents")


def test_post_task():
    """Post a task."""
    proto = CapabilityNegotiationProtocol()
    tid = proto.post_task("Build auth", {"code_gen": 3}, preferred_capabilities={"testing": 2})
    assert tid.startswith("task-")

    task = proto.get_task(tid)
    assert task is not None
    assert task["name"] == "Build auth"
    assert task["required_capabilities"]["code_gen"] == 3
    print("OK: post task")


def test_list_tasks():
    """List tasks."""
    proto = CapabilityNegotiationProtocol()
    proto.advertise("Builder", {"code_gen": 5})
    t1 = proto.post_task("Low", {"code_gen": 1}, priority=10)
    t2 = proto.post_task("High", {"code_gen": 1}, priority=90)

    tasks = proto.list_tasks()
    assert len(tasks) == 2
    assert tasks[0]["priority"] > tasks[1]["priority"]

    proto.assign_task(t1, "Builder")
    unassigned = proto.list_tasks(unassigned_only=True)
    assert len(unassigned) == 1
    print("OK: list tasks")


def test_remove_task():
    """Remove a task."""
    proto = CapabilityNegotiationProtocol()
    tid = proto.post_task("Temp", {"x": 1})
    assert proto.remove_task(tid) is True
    assert proto.remove_task(tid) is False
    print("OK: remove task")


def test_find_best_agents():
    """Find best matching agents for a task."""
    proto = CapabilityNegotiationProtocol()
    proto.advertise("Expert", {"code_gen": 5, "testing": 4}, max_load=10)
    proto.advertise("Junior", {"code_gen": 2, "testing": 1}, max_load=10)
    proto.advertise("Specialist", {"code_gen": 4, "testing": 5}, max_load=10)

    tid = proto.post_task("Build module",
                          required_capabilities={"code_gen": 3},
                          preferred_capabilities={"testing": 3})

    matches = proto.find_best_agents(tid)
    assert len(matches) == 2  # Junior doesn't meet code_gen=3
    assert matches[0]["score"] >= matches[1]["score"]
    print("OK: find best agents")


def test_find_best_agents_load_aware():
    """Load-aware agent matching."""
    proto = CapabilityNegotiationProtocol()
    proto.advertise("Busy", {"code_gen": 5}, max_load=10)
    proto.advertise("Free", {"code_gen": 5}, max_load=10)
    proto.update_load("Busy", 8)
    proto.update_load("Free", 1)

    tid = proto.post_task("Task", required_capabilities={"code_gen": 1})
    matches = proto.find_best_agents(tid)
    assert matches[0]["agent_name"] == "Free"  # Lower load wins
    print("OK: find best agents load aware")


def test_assign_task():
    """Assign a task to an agent."""
    proto = CapabilityNegotiationProtocol()
    proto.advertise("Builder", {"code_gen": 5}, max_load=10)
    tid = proto.post_task("Task", {"code_gen": 1})

    assert proto.assign_task(tid, "Builder") is True
    task = proto.get_task(tid)
    assert task["assigned_to"] == "Builder"
    assert proto.get_agent("Builder")["current_load"] == 1

    # Can't double-assign
    assert proto.assign_task(tid, "Builder") is False
    print("OK: assign task")


def test_unassign_task():
    """Unassign a task."""
    proto = CapabilityNegotiationProtocol()
    proto.advertise("Builder", {"code_gen": 5}, max_load=10)
    tid = proto.post_task("Task", {"code_gen": 1})
    proto.assign_task(tid, "Builder")

    assert proto.unassign_task(tid) is True
    assert proto.get_task(tid)["assigned_to"] is None
    assert proto.get_agent("Builder")["current_load"] == 0
    assert proto.unassign_task(tid) is False  # Already unassigned
    print("OK: unassign task")


def test_auto_assign():
    """Automatically assign to best agent."""
    proto = CapabilityNegotiationProtocol()
    proto.advertise("Expert", {"code_gen": 5}, max_load=10)
    proto.advertise("Novice", {"code_gen": 1}, max_load=10)

    tid = proto.post_task("Task", {"code_gen": 3})
    assigned = proto.auto_assign(tid)
    assert assigned == "Expert"  # Only expert meets requirement
    print("OK: auto assign")


def test_auto_assign_no_match():
    """Auto assign returns None when no match."""
    proto = CapabilityNegotiationProtocol()
    proto.advertise("Novice", {"code_gen": 1})
    tid = proto.post_task("Task", {"code_gen": 5})

    assigned = proto.auto_assign(tid)
    assert assigned is None
    print("OK: auto assign no match")


def test_request_collaboration():
    """Request collaboration between agents."""
    proto = CapabilityNegotiationProtocol()
    proto.advertise("Builder", {"code_gen": 5})
    proto.advertise("Tester", {"testing": 5})
    tid = proto.post_task("Joint task", {"code_gen": 1})

    nid = proto.request_collaboration("Builder", "Tester", tid,
                                       message="Help me test this")
    assert nid is not None
    assert nid.startswith("neg-")

    neg = proto.get_negotiation(nid)
    assert neg["status"] == "open"
    assert neg["initiator"] == "Builder"
    assert neg["target"] == "Tester"
    print("OK: request collaboration")


def test_respond_negotiation_accept():
    """Accept a negotiation."""
    proto = CapabilityNegotiationProtocol()
    proto.advertise("A", {"x": 1})
    proto.advertise("B", {"x": 1})
    tid = proto.post_task("Task", {"x": 1})
    nid = proto.request_collaboration("A", "B", tid)

    assert proto.respond_negotiation(nid, accept=True, response_message="Sure!") is True
    neg = proto.get_negotiation(nid)
    assert neg["status"] == "accepted"
    assert neg["response_message"] == "Sure!"
    print("OK: respond accept")


def test_respond_negotiation_reject():
    """Reject a negotiation."""
    proto = CapabilityNegotiationProtocol()
    proto.advertise("A", {"x": 1})
    proto.advertise("B", {"x": 1})
    tid = proto.post_task("Task", {"x": 1})
    nid = proto.request_collaboration("A", "B", tid)

    assert proto.respond_negotiation(nid, accept=False, response_message="Too busy") is True
    neg = proto.get_negotiation(nid)
    assert neg["status"] == "rejected"
    print("OK: respond reject")


def test_cancel_negotiation():
    """Cancel a negotiation."""
    proto = CapabilityNegotiationProtocol()
    proto.advertise("A", {"x": 1})
    proto.advertise("B", {"x": 1})
    tid = proto.post_task("Task", {"x": 1})
    nid = proto.request_collaboration("A", "B", tid)

    assert proto.cancel_negotiation(nid) is True
    assert proto.get_negotiation(nid)["status"] == "cancelled"
    assert proto.cancel_negotiation(nid) is False  # Already cancelled
    print("OK: cancel negotiation")


def test_get_agent_negotiations():
    """Get negotiations for an agent."""
    proto = CapabilityNegotiationProtocol()
    proto.advertise("A", {"x": 1})
    proto.advertise("B", {"x": 1})
    proto.advertise("C", {"x": 1})
    tid = proto.post_task("Task", {"x": 1})

    proto.request_collaboration("A", "B", tid)
    proto.request_collaboration("A", "C", tid)

    a_negs = proto.get_agent_negotiations("A")
    assert len(a_negs) == 2

    b_negs = proto.get_agent_negotiations("B")
    assert len(b_negs) == 1
    print("OK: get agent negotiations")


def test_expire_negotiations():
    """Expire old negotiations."""
    proto = CapabilityNegotiationProtocol(negotiation_ttl=0.1)
    proto.advertise("A", {"x": 1})
    proto.advertise("B", {"x": 1})
    tid = proto.post_task("Task", {"x": 1})
    nid = proto.request_collaboration("A", "B", tid)

    import time
    time.sleep(0.15)

    expired = proto.expire_old_negotiations()
    assert expired == 1
    assert proto.get_negotiation(nid)["status"] == "expired"
    print("OK: expire negotiations")


def test_request_invalid():
    """Invalid negotiation requests."""
    proto = CapabilityNegotiationProtocol()
    proto.advertise("A", {"x": 1})
    tid = proto.post_task("Task", {"x": 1})

    # Target doesn't exist
    assert proto.request_collaboration("A", "nonexistent", tid) is None
    # Task doesn't exist
    assert proto.request_collaboration("A", "A", "fake-task") is None
    print("OK: request invalid")


def test_stats():
    """Stats are accurate."""
    proto = CapabilityNegotiationProtocol()
    proto.advertise("A", {"x": 1})
    proto.advertise("B", {"x": 1})
    tid = proto.post_task("Task", {"x": 1})
    proto.assign_task(tid, "A")
    nid = proto.request_collaboration("A", "B", tid)
    proto.respond_negotiation(nid, accept=True)

    stats = proto.get_stats()
    assert stats["total_agents"] == 2
    assert stats["total_tasks"] == 1
    assert stats["total_assignments"] == 1
    assert stats["total_negotiations"] == 1
    assert stats["total_accepted"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    proto = CapabilityNegotiationProtocol()
    proto.advertise("A", {"x": 1})
    proto.post_task("Task", {"x": 1})

    proto.reset()
    assert proto.list_agents() == []
    assert proto.list_tasks() == []
    stats = proto.get_stats()
    assert stats["total_agents"] == 0
    print("OK: reset")


def main():
    print("=== Capability Negotiation Tests ===\n")
    test_advertise()
    test_withdraw()
    test_set_availability()
    test_update_load()
    test_list_agents()
    test_post_task()
    test_list_tasks()
    test_remove_task()
    test_find_best_agents()
    test_find_best_agents_load_aware()
    test_assign_task()
    test_unassign_task()
    test_auto_assign()
    test_auto_assign_no_match()
    test_request_collaboration()
    test_respond_negotiation_accept()
    test_respond_negotiation_reject()
    test_cancel_negotiation()
    test_get_agent_negotiations()
    test_expire_negotiations()
    test_request_invalid()
    test_stats()
    test_reset()
    print("\n=== ALL 23 TESTS PASSED ===")


if __name__ == "__main__":
    main()
