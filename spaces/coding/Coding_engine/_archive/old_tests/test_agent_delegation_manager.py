"""Test agent delegation manager."""
import sys
sys.path.insert(0, ".")

from src.services.agent_delegation_manager import AgentDelegationManager


def test_delegate():
    """Delegate and retrieve task."""
    dm = AgentDelegationManager()
    did = dm.delegate("build", from_agent="orchestrator", to_agent="builder",
                       payload={"target": "app"}, tags=["ci"])
    assert did.startswith("dlg-")

    d = dm.get_delegation(did)
    assert d is not None
    assert d["task_name"] == "build"
    assert d["from_agent"] == "orchestrator"
    assert d["to_agent"] == "builder"
    assert d["status"] == "pending"

    assert dm.remove_delegation(did) is True
    assert dm.remove_delegation(did) is False
    print("OK: delegate")


def test_invalid_delegate():
    """Invalid delegation rejected."""
    dm = AgentDelegationManager()
    assert dm.delegate("", from_agent="a", to_agent="b") == ""
    assert dm.delegate("t", from_agent="", to_agent="b") == ""
    assert dm.delegate("t", from_agent="a", to_agent="") == ""
    assert dm.delegate("t", from_agent="a", to_agent="a") == ""  # self-delegate
    print("OK: invalid delegate")


def test_max_delegations():
    """Max delegations enforced."""
    dm = AgentDelegationManager(max_delegations=2)
    dm.delegate("a", from_agent="x", to_agent="y")
    dm.delegate("b", from_agent="x", to_agent="z")
    assert dm.delegate("c", from_agent="x", to_agent="w") == ""
    print("OK: max delegations")


def test_accept():
    """Accept delegation."""
    dm = AgentDelegationManager()
    did = dm.delegate("build", from_agent="a", to_agent="b")

    assert dm.accept(did) is True
    assert dm.get_delegation(did)["status"] == "accepted"
    assert dm.accept(did) is False  # not pending anymore
    print("OK: accept")


def test_reject():
    """Reject delegation."""
    dm = AgentDelegationManager()
    did = dm.delegate("build", from_agent="a", to_agent="b")

    assert dm.reject(did, reason="busy") is True
    d = dm.get_delegation(did)
    assert d["status"] == "rejected"
    assert d["result"] == "busy"
    assert dm.reject(did) is False
    print("OK: reject")


def test_complete():
    """Complete delegation."""
    dm = AgentDelegationManager()
    did = dm.delegate("build", from_agent="a", to_agent="b")

    assert dm.complete(did, result="success") is True
    d = dm.get_delegation(did)
    assert d["status"] == "completed"
    assert d["result"] == "success"
    assert d["completed_at"] > 0
    assert dm.complete(did) is False
    print("OK: complete")


def test_complete_after_accept():
    """Complete after accepting."""
    dm = AgentDelegationManager()
    did = dm.delegate("build", from_agent="a", to_agent="b")
    dm.accept(did)

    assert dm.complete(did, result="done") is True
    assert dm.get_delegation(did)["status"] == "completed"
    print("OK: complete after accept")


def test_fail():
    """Fail delegation."""
    dm = AgentDelegationManager()
    did = dm.delegate("build", from_agent="a", to_agent="b")

    assert dm.fail(did, error="crash") is True
    d = dm.get_delegation(did)
    assert d["status"] == "failed"
    assert d["result"] == "crash"
    assert dm.fail(did) is False
    print("OK: fail")


def test_list_delegations():
    """List delegations with filters."""
    dm = AgentDelegationManager()
    d1 = dm.delegate("build", from_agent="a", to_agent="b", tags=["ci"])
    d2 = dm.delegate("test", from_agent="a", to_agent="c")
    dm.complete(d2)

    all_d = dm.list_delegations()
    assert len(all_d) == 2

    by_from = dm.list_delegations(from_agent="a")
    assert len(by_from) == 2

    by_to = dm.list_delegations(to_agent="b")
    assert len(by_to) == 1

    by_status = dm.list_delegations(status="completed")
    assert len(by_status) == 1

    by_tag = dm.list_delegations(tag="ci")
    assert len(by_tag) == 1
    print("OK: list delegations")


def test_get_pending():
    """Get pending delegations for agent."""
    dm = AgentDelegationManager()
    dm.delegate("build", from_agent="a", to_agent="b")
    dm.delegate("test", from_agent="a", to_agent="b")
    d3 = dm.delegate("deploy", from_agent="a", to_agent="b")
    dm.complete(d3)

    pending = dm.get_pending_for_agent("b")
    assert len(pending) == 2
    print("OK: get pending")


def test_callback():
    """Callback fires on events."""
    dm = AgentDelegationManager()
    fired = []
    dm.on_change("mon", lambda a, d: fired.append(a))

    did = dm.delegate("build", from_agent="a", to_agent="b")
    assert "task_delegated" in fired

    dm.accept(did)
    assert "delegation_accepted" in fired

    dm.complete(did)
    assert "delegation_completed" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    dm = AgentDelegationManager()
    assert dm.on_change("mon", lambda a, d: None) is True
    assert dm.on_change("mon", lambda a, d: None) is False
    assert dm.remove_callback("mon") is True
    assert dm.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    dm = AgentDelegationManager()
    d1 = dm.delegate("a", from_agent="x", to_agent="y")
    dm.complete(d1)
    d2 = dm.delegate("b", from_agent="x", to_agent="z")
    dm.fail(d2)
    d3 = dm.delegate("c", from_agent="x", to_agent="w")
    dm.reject(d3)

    stats = dm.get_stats()
    assert stats["total_delegations"] == 3
    assert stats["total_completed"] == 1
    assert stats["total_failed"] == 1
    assert stats["total_rejected"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    dm = AgentDelegationManager()
    dm.delegate("build", from_agent="a", to_agent="b")

    dm.reset()
    assert dm.list_delegations() == []
    stats = dm.get_stats()
    assert stats["current_delegations"] == 0
    print("OK: reset")


def main():
    print("=== Agent Delegation Manager Tests ===\n")
    test_delegate()
    test_invalid_delegate()
    test_max_delegations()
    test_accept()
    test_reject()
    test_complete()
    test_complete_after_accept()
    test_fail()
    test_list_delegations()
    test_get_pending()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 14 TESTS PASSED ===")


if __name__ == "__main__":
    main()
