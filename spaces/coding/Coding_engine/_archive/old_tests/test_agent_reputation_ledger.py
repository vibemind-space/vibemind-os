"""Test agent reputation ledger."""
import sys
sys.path.insert(0, ".")

from src.services.agent_reputation_ledger import AgentReputationLedger


def test_record_event():
    """Record reputation events."""
    rl = AgentReputationLedger()
    eid = rl.record("agent-1", "reward", 10.0, category="quality", reason="clean code")
    assert eid.startswith("rep-")
    assert rl.get_score("agent-1") == 10.0
    print("OK: record event")


def test_invalid_record():
    """Invalid record rejected."""
    rl = AgentReputationLedger()
    assert rl.record("", "reward", 5.0) == ""
    assert rl.record("a", "", 5.0) == ""
    assert rl.record("a", "invalid_action", 5.0) == ""
    assert rl.record("a", "reward", 5.0, category="invalid_cat") == ""
    print("OK: invalid record")


def test_accumulate_score():
    """Score accumulates correctly."""
    rl = AgentReputationLedger()
    rl.record("agent-1", "reward", 10.0)
    rl.record("agent-1", "reward", 5.0)
    rl.record("agent-1", "penalty", -3.0)

    assert rl.get_score("agent-1") == 12.0
    print("OK: accumulate score")


def test_nonexistent_agent_score():
    """Nonexistent agent returns 0."""
    rl = AgentReputationLedger()
    assert rl.get_score("nonexistent") == 0.0
    print("OK: nonexistent agent score")


def test_agent_history():
    """Get agent history with filters."""
    rl = AgentReputationLedger()
    rl.record("agent-1", "reward", 5.0, category="quality")
    rl.record("agent-1", "penalty", -2.0, category="reliability")
    rl.record("agent-1", "reward", 3.0, category="quality")
    rl.record("agent-2", "reward", 1.0)

    history = rl.get_agent_history("agent-1")
    assert len(history) == 3

    by_cat = rl.get_agent_history("agent-1", category="quality")
    assert len(by_cat) == 2

    by_action = rl.get_agent_history("agent-1", action="penalty")
    assert len(by_action) == 1
    print("OK: agent history")


def test_history_limit():
    """History respects limit."""
    rl = AgentReputationLedger()
    for i in range(10):
        rl.record("a", "reward", 1.0)

    history = rl.get_agent_history("a", limit=3)
    assert len(history) == 3
    print("OK: history limit")


def test_rankings():
    """Get top agents by score."""
    rl = AgentReputationLedger()
    rl.record("agent-1", "reward", 30.0)
    rl.record("agent-2", "reward", 50.0)
    rl.record("agent-3", "reward", 10.0)

    rankings = rl.get_rankings(limit=2)
    assert len(rankings) == 2
    assert rankings[0]["agent"] == "agent-2"
    assert rankings[0]["rank"] == 1
    assert rankings[1]["agent"] == "agent-1"
    print("OK: rankings")


def test_bottom_agents():
    """Get lowest reputation agents."""
    rl = AgentReputationLedger()
    rl.record("high", "reward", 100.0)
    rl.record("low", "penalty", -50.0)
    rl.record("mid", "reward", 10.0)

    bottom = rl.get_bottom_agents(limit=2)
    assert len(bottom) == 2
    assert bottom[0]["agent"] == "low"
    print("OK: bottom agents")


def test_agent_summary():
    """Get agent reputation summary."""
    rl = AgentReputationLedger()
    rl.record("agent-1", "reward", 10.0, category="quality")
    rl.record("agent-1", "reward", 5.0, category="speed")
    rl.record("agent-1", "penalty", -3.0, category="quality")

    summary = rl.get_agent_summary("agent-1")
    assert summary["score"] == 12.0
    assert summary["total_positive"] == 15.0
    assert summary["total_negative"] == -3.0
    assert summary["count_positive"] == 2
    assert summary["count_negative"] == 1
    assert summary["by_category"]["quality"] == 7.0

    assert rl.get_agent_summary("nonexistent") == {}
    print("OK: agent summary")


def test_category_leaders():
    """Get leaders in a category."""
    rl = AgentReputationLedger()
    rl.record("agent-1", "reward", 20.0, category="quality")
    rl.record("agent-2", "reward", 30.0, category="quality")
    rl.record("agent-1", "reward", 5.0, category="speed")

    leaders = rl.get_category_leaders("quality", limit=2)
    assert len(leaders) == 2
    assert leaders[0]["agent"] == "agent-2"
    print("OK: category leaders")


def test_recent_activity():
    """Get recent activity."""
    rl = AgentReputationLedger()
    rl.record("a", "reward", 1.0)
    rl.record("b", "penalty", -2.0)

    recent = rl.get_recent_activity(limit=5)
    assert len(recent) == 2
    assert recent[0]["agent"] == "b"  # Most recent first
    print("OK: recent activity")


def test_all_agents():
    """Get all tracked agents."""
    rl = AgentReputationLedger()
    rl.record("charlie", "reward", 1.0)
    rl.record("alice", "reward", 1.0)
    rl.record("bob", "reward", 1.0)

    agents = rl.get_all_agents()
    assert agents == ["alice", "bob", "charlie"]
    print("OK: all agents")


def test_entry_pruning():
    """Entries pruned when max exceeded."""
    rl = AgentReputationLedger(max_entries=10)
    for i in range(15):
        rl.record("a", "reward", 1.0)

    # Should have pruned to half
    assert len(rl.get_agent_history("a", limit=1000)) <= 10
    print("OK: entry pruning")


def test_callback():
    """Callback fires on record."""
    rl = AgentReputationLedger()
    fired = []
    rl.on_change("mon", lambda a, d: fired.append(a))

    rl.record("a", "reward", 5.0)
    assert "reputation_recorded" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    rl = AgentReputationLedger()
    assert rl.on_change("mon", lambda a, d: None) is True
    assert rl.on_change("mon", lambda a, d: None) is False
    assert rl.remove_callback("mon") is True
    assert rl.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    rl = AgentReputationLedger()
    rl.record("a", "reward", 10.0)
    rl.record("a", "penalty", -3.0)
    rl.record("b", "reward", 5.0)

    stats = rl.get_stats()
    assert stats["total_entries"] == 3
    assert stats["total_rewards"] == 2
    assert stats["total_penalties"] == 1
    assert stats["tracked_agents"] == 2
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    rl = AgentReputationLedger()
    rl.record("a", "reward", 10.0)

    rl.reset()
    assert rl.get_score("a") == 0.0
    assert rl.get_all_agents() == []
    stats = rl.get_stats()
    assert stats["current_entries"] == 0
    print("OK: reset")


def main():
    print("=== Agent Reputation Ledger Tests ===\n")
    test_record_event()
    test_invalid_record()
    test_accumulate_score()
    test_nonexistent_agent_score()
    test_agent_history()
    test_history_limit()
    test_rankings()
    test_bottom_agents()
    test_agent_summary()
    test_category_leaders()
    test_recent_activity()
    test_all_agents()
    test_entry_pruning()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 17 TESTS PASSED ===")


if __name__ == "__main__":
    main()
