"""Test agent delegation engine."""
import sys
sys.path.insert(0, ".")

from src.services.agent_delegation_engine import AgentDelegationEngine


def test_delegate():
    """Delegate and retrieve."""
    de = AgentDelegationEngine()
    did = de.delegate("Build feature X", "agent_a", "agent_b",
                      priority=8, reason="expertise", tags=["sprint1"])
    assert did.startswith("dlg-")

    d = de.get_delegation(did)
    assert d is not None
    assert d["task_name"] == "Build feature X"
    assert d["from_agent"] == "agent_a"
    assert d["to_agent"] == "agent_b"
    assert d["status"] == "pending"
    assert d["priority"] == 8

    assert de.remove_delegation(did) is True
    assert de.remove_delegation(did) is False
    print("OK: delegate")


def test_invalid_delegation():
    """Invalid delegation rejected."""
    de = AgentDelegationEngine()
    assert de.delegate("", "a", "b") == ""
    assert de.delegate("task", "", "b") == ""
    assert de.delegate("task", "a", "") == ""
    assert de.delegate("task", "a", "a") == ""  # self-delegation
    assert de.delegate("task", "a", "b", parent_delegation_id="nonexistent") == ""
    print("OK: invalid delegation")


def test_max_delegations():
    """Max delegations enforced."""
    de = AgentDelegationEngine(max_delegations=2)
    de.delegate("a", "x", "y")
    de.delegate("b", "x", "y")
    assert de.delegate("c", "x", "y") == ""
    print("OK: max delegations")


def test_accept():
    """Accept delegation."""
    de = AgentDelegationEngine()
    did = de.delegate("task", "a", "b")

    assert de.accept(did) is True
    assert de.get_delegation(did)["status"] == "accepted"
    assert de.accept(did) is False  # already accepted
    print("OK: accept")


def test_reject():
    """Reject delegation."""
    de = AgentDelegationEngine()
    did = de.delegate("task", "a", "b")

    assert de.reject(did, reason="too busy") is True
    assert de.get_delegation(did)["status"] == "rejected"
    assert de.reject(did) is False
    print("OK: reject")


def test_complete():
    """Complete delegation."""
    de = AgentDelegationEngine()
    did = de.delegate("task", "a", "b")
    de.accept(did)

    assert de.complete(did, result="Done!") is True
    assert de.get_delegation(did)["status"] == "completed"
    assert de.get_delegation(did)["result"] == "Done!"
    assert de.complete(did) is False
    print("OK: complete")


def test_fail():
    """Fail delegation."""
    de = AgentDelegationEngine()
    did = de.delegate("task", "a", "b")
    de.accept(did)

    assert de.fail(did, reason="error") is True
    assert de.get_delegation(did)["status"] == "failed"
    assert de.fail(did) is False
    print("OK: fail")


def test_cancel():
    """Cancel delegation."""
    de = AgentDelegationEngine()
    did = de.delegate("task", "a", "b")

    assert de.cancel(did) is True
    assert de.get_delegation(did)["status"] == "cancelled"
    assert de.cancel(did) is False
    print("OK: cancel")


def test_delegations_from():
    """Get delegations from agent."""
    de = AgentDelegationEngine()
    de.delegate("t1", "agent_a", "agent_b")
    de.delegate("t2", "agent_a", "agent_c")
    de.delegate("t3", "agent_b", "agent_c")

    from_a = de.get_delegations_from("agent_a")
    assert len(from_a) == 2
    print("OK: delegations from")


def test_delegations_to():
    """Get delegations to agent."""
    de = AgentDelegationEngine()
    de.delegate("t1", "agent_a", "agent_b")
    de.delegate("t2", "agent_c", "agent_b")
    de.delegate("t3", "agent_a", "agent_c")

    to_b = de.get_delegations_to("agent_b")
    assert len(to_b) == 2
    print("OK: delegations to")


def test_search_delegations():
    """Search delegations."""
    de = AgentDelegationEngine()
    d1 = de.delegate("t1", "a", "b", tags=["sprint1"])
    de.accept(d1)
    de.delegate("t2", "c", "d")

    all_d = de.search_delegations()
    assert len(all_d) == 2

    by_from = de.search_delegations(from_agent="a")
    assert len(by_from) == 1

    by_to = de.search_delegations(to_agent="b")
    assert len(by_to) == 1

    by_status = de.search_delegations(status="accepted")
    assert len(by_status) == 1

    by_tag = de.search_delegations(tag="sprint1")
    assert len(by_tag) == 1
    print("OK: search delegations")


def test_delegation_chain():
    """Get delegation chain."""
    de = AgentDelegationEngine()
    d1 = de.delegate("task", "a", "b")
    d2 = de.delegate("subtask", "b", "c", parent_delegation_id=d1)
    d3 = de.delegate("subsubtask", "c", "d", parent_delegation_id=d2)

    chain = de.get_delegation_chain(d3)
    assert len(chain) == 3
    assert chain[0]["delegation_id"] == d1
    assert chain[2]["delegation_id"] == d3
    print("OK: delegation chain")


def test_success_rate():
    """Get agent success rate."""
    de = AgentDelegationEngine()
    d1 = de.delegate("t1", "a", "b")
    de.accept(d1)
    de.complete(d1)
    d2 = de.delegate("t2", "a", "b")
    de.accept(d2)
    de.complete(d2)
    d3 = de.delegate("t3", "a", "b")
    de.accept(d3)
    de.fail(d3)

    rate = de.get_agent_success_rate("b")
    assert rate["total_resolved"] == 3
    assert rate["completed"] == 2
    assert rate["failed"] == 1
    assert abs(rate["success_rate"] - 66.7) < 0.1
    print("OK: success rate")


def test_callback():
    """Callback fires on delegation events."""
    de = AgentDelegationEngine()
    fired = []
    de.on_change("mon", lambda a, d: fired.append(a))

    did = de.delegate("task", "a", "b")
    assert "task_delegated" in fired

    de.accept(did)
    assert "delegation_accepted" in fired

    de.complete(did)
    assert "delegation_completed" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    de = AgentDelegationEngine()
    assert de.on_change("mon", lambda a, d: None) is True
    assert de.on_change("mon", lambda a, d: None) is False
    assert de.remove_callback("mon") is True
    assert de.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    de = AgentDelegationEngine()
    d1 = de.delegate("t1", "a", "b")
    de.accept(d1)
    de.complete(d1)
    d2 = de.delegate("t2", "a", "c")
    de.reject(d2)
    d3 = de.delegate("t3", "a", "d")
    de.accept(d3)
    de.fail(d3)

    stats = de.get_stats()
    assert stats["total_delegations"] == 3
    assert stats["total_accepted"] == 2
    assert stats["total_rejected"] == 1
    assert stats["total_completed"] == 1
    assert stats["total_failed"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    de = AgentDelegationEngine()
    de.delegate("task", "a", "b")

    de.reset()
    assert de.search_delegations() == []
    stats = de.get_stats()
    assert stats["current_delegations"] == 0
    print("OK: reset")


def main():
    print("=== Agent Delegation Engine Tests ===\n")
    test_delegate()
    test_invalid_delegation()
    test_max_delegations()
    test_accept()
    test_reject()
    test_complete()
    test_fail()
    test_cancel()
    test_delegations_from()
    test_delegations_to()
    test_search_delegations()
    test_delegation_chain()
    test_success_rate()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 17 TESTS PASSED ===")


if __name__ == "__main__":
    main()
