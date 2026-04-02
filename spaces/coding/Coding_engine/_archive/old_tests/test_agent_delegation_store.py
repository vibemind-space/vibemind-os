"""Test agent delegation store -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_delegation_store import AgentDelegationStore


def test_delegate():
    ds = AgentDelegationStore()
    did = ds.delegate("agent-1", "agent-2", "process data", priority="high", metadata={"urgency": "now"})
    assert len(did) > 0
    assert did.startswith("ads-")
    d = ds.get_delegation(did)
    assert d is not None
    assert d["from_agent"] == "agent-1"
    assert d["to_agent"] == "agent-2"
    assert d["status"] == "pending"
    print("OK: delegate")


def test_accept():
    ds = AgentDelegationStore()
    did = ds.delegate("agent-1", "agent-2", "task")
    assert ds.accept(did) is True
    d = ds.get_delegation(did)
    assert d["status"] == "accepted"
    # Cannot accept again
    assert ds.accept(did) is False
    print("OK: accept")


def test_reject():
    ds = AgentDelegationStore()
    did = ds.delegate("agent-1", "agent-2", "task")
    assert ds.reject(did, reason="too busy") is True
    d = ds.get_delegation(did)
    assert d["status"] == "rejected"
    # Cannot reject again
    assert ds.reject(did) is False
    print("OK: reject")


def test_complete():
    ds = AgentDelegationStore()
    did = ds.delegate("agent-1", "agent-2", "task")
    # Cannot complete if not accepted
    assert ds.complete(did) is False
    ds.accept(did)
    assert ds.complete(did, result={"output": 42}) is True
    d = ds.get_delegation(did)
    assert d["status"] == "completed"
    print("OK: complete")


def test_cancel():
    ds = AgentDelegationStore()
    did1 = ds.delegate("agent-1", "agent-2", "task1")
    did2 = ds.delegate("agent-1", "agent-2", "task2")
    ds.accept(did2)
    # Cancel pending
    assert ds.cancel(did1) is True
    # Cancel accepted
    assert ds.cancel(did2) is True
    # Cannot cancel completed
    did3 = ds.delegate("agent-1", "agent-2", "task3")
    ds.accept(did3)
    ds.complete(did3)
    assert ds.cancel(did3) is False
    print("OK: cancel")


def test_get_delegations_from():
    ds = AgentDelegationStore()
    ds.delegate("agent-1", "agent-2", "t1")
    ds.delegate("agent-1", "agent-3", "t2")
    ds.delegate("agent-2", "agent-3", "t3")
    from_1 = ds.get_delegations_from("agent-1")
    assert len(from_1) == 2
    print("OK: get delegations from")


def test_get_delegations_to():
    ds = AgentDelegationStore()
    ds.delegate("agent-1", "agent-2", "t1")
    ds.delegate("agent-3", "agent-2", "t2")
    ds.delegate("agent-1", "agent-3", "t3")
    to_2 = ds.get_delegations_to("agent-2")
    assert len(to_2) == 2
    print("OK: get delegations to")


def test_get_pending_for():
    ds = AgentDelegationStore()
    did1 = ds.delegate("agent-1", "agent-2", "t1")
    ds.delegate("agent-1", "agent-2", "t2")
    ds.accept(did1)
    pending = ds.get_pending_for("agent-2")
    assert len(pending) == 1
    print("OK: get pending for")


def test_list_delegations():
    ds = AgentDelegationStore()
    ds.delegate("a", "b", "t1")
    did2 = ds.delegate("a", "b", "t2")
    ds.accept(did2)
    all_d = ds.list_delegations()
    assert len(all_d) == 2
    pending = ds.list_delegations(status="pending")
    assert len(pending) == 1
    print("OK: list delegations")


def test_callbacks():
    ds = AgentDelegationStore()
    fired = []
    ds.on_change("mon", lambda a, d: fired.append(a))
    ds.delegate("a", "b", "task")
    assert len(fired) >= 1
    assert ds.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    ds = AgentDelegationStore()
    ds.delegate("a", "b", "task")
    stats = ds.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    ds = AgentDelegationStore()
    ds.delegate("a", "b", "task")
    ds.reset()
    assert ds.list_delegations() == []
    print("OK: reset")


def main():
    print("=== Agent Delegation Store Tests ===\n")
    test_delegate()
    test_accept()
    test_reject()
    test_complete()
    test_cancel()
    test_get_delegations_from()
    test_get_delegations_to()
    test_get_pending_for()
    test_list_delegations()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 12 TESTS PASSED ===")


if __name__ == "__main__":
    main()
