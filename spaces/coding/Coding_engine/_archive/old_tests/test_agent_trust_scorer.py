"""Test agent trust scorer."""
import sys
sys.path.insert(0, ".")

from src.services.agent_trust_scorer import AgentTrustScorer


def test_register_agent():
    """Register and unregister agents."""
    ts = AgentTrustScorer()
    assert ts.register_agent("agent-1") is True
    assert ts.register_agent("agent-1") is False  # Duplicate

    a = ts.get_agent("agent-1")
    assert a is not None
    assert a["score"] == 50.0
    assert a["total_positive"] == 0

    assert ts.unregister_agent("agent-1") is True
    assert ts.unregister_agent("agent-1") is False
    print("OK: register agent")


def test_invalid_registration():
    """Invalid registration rejected."""
    ts = AgentTrustScorer()
    assert ts.register_agent("") is False
    print("OK: invalid registration")


def test_max_agents():
    """Max agents enforced."""
    ts = AgentTrustScorer(max_agents=2)
    ts.register_agent("a")
    ts.register_agent("b")
    assert ts.register_agent("c") is False
    print("OK: max agents")


def test_initial_score():
    """Custom initial score."""
    ts = AgentTrustScorer()
    ts.register_agent("agent-1", initial_score=80.0)
    assert ts.get_score("agent-1") == 80.0
    print("OK: initial score")


def test_record_event():
    """Record trust events."""
    ts = AgentTrustScorer()
    ts.register_agent("agent-1")

    rid = ts.record_event("agent-1", "task_completed", reason="built module")
    assert rid.startswith("trust-")
    assert ts.get_score("agent-1") == 52.0  # 50 + 2 default delta
    print("OK: record event")


def test_invalid_event():
    """Invalid event rejected."""
    ts = AgentTrustScorer()
    ts.register_agent("agent-1")
    assert ts.record_event("nonexistent", "task_completed") == ""
    assert ts.record_event("agent-1", "invalid_type") == ""
    print("OK: invalid event")


def test_custom_delta():
    """Custom delta overrides default."""
    ts = AgentTrustScorer()
    ts.register_agent("agent-1")

    ts.record_event("agent-1", "task_completed", delta=10.0)
    assert ts.get_score("agent-1") == 60.0
    print("OK: custom delta")


def test_score_bounds():
    """Score stays within min/max bounds."""
    ts = AgentTrustScorer(min_score=0.0, max_score=100.0)
    ts.register_agent("agent-1", initial_score=95.0)

    ts.record_event("agent-1", "manual_boost", delta=20.0)
    assert ts.get_score("agent-1") == 100.0  # Capped

    ts2 = AgentTrustScorer()
    ts2.register_agent("agent-2", initial_score=5.0)
    ts2.record_event("agent-2", "violation", delta=-20.0)
    assert ts2.get_score("agent-2") == 0.0  # Floored
    print("OK: score bounds")


def test_positive_negative_counts():
    """Track positive and negative event counts."""
    ts = AgentTrustScorer()
    ts.register_agent("agent-1")

    ts.record_event("agent-1", "task_completed")  # +2
    ts.record_event("agent-1", "task_completed")  # +2
    ts.record_event("agent-1", "task_failed")  # -3

    a = ts.get_agent("agent-1")
    assert a["total_positive"] == 2
    assert a["total_negative"] == 1
    print("OK: positive negative counts")


def test_get_history():
    """Get trust history."""
    ts = AgentTrustScorer()
    ts.register_agent("agent-1")

    ts.record_event("agent-1", "task_completed", reason="first")
    ts.record_event("agent-1", "task_failed", reason="second")

    history = ts.get_history("agent-1")
    assert len(history) == 2
    assert history[0]["reason"] == "second"  # Newest first
    print("OK: get history")


def test_history_pruning():
    """History pruned when max exceeded."""
    ts = AgentTrustScorer(max_history=3)
    ts.register_agent("agent-1")

    for i in range(5):
        ts.record_event("agent-1", "task_completed", reason=f"event-{i}")

    history = ts.get_history("agent-1")
    assert len(history) == 3
    print("OK: history pruning")


def test_list_agents():
    """List agents with score filters."""
    ts = AgentTrustScorer()
    ts.register_agent("high", initial_score=90.0)
    ts.register_agent("mid", initial_score=50.0)
    ts.register_agent("low", initial_score=10.0)

    all_a = ts.list_agents()
    assert len(all_a) == 3
    assert all_a[0]["agent"] == "high"  # Sorted by score desc

    high_only = ts.list_agents(min_score=70.0)
    assert len(high_only) == 1
    print("OK: list agents")


def test_ranking():
    """Get top ranked agents."""
    ts = AgentTrustScorer()
    ts.register_agent("a", initial_score=30.0)
    ts.register_agent("b", initial_score=90.0)
    ts.register_agent("c", initial_score=60.0)

    ranking = ts.get_ranking(limit=2)
    assert len(ranking) == 2
    assert ranking[0]["agent"] == "b"
    print("OK: ranking")


def test_trusted_untrusted():
    """Get trusted and untrusted agents."""
    ts = AgentTrustScorer()
    ts.register_agent("trusted", initial_score=80.0)
    ts.register_agent("untrusted", initial_score=20.0)
    ts.register_agent("mid", initial_score=50.0)

    trusted = ts.get_trusted_agents(min_score=70.0)
    assert "trusted" in trusted
    assert "mid" not in trusted

    untrusted = ts.get_untrusted_agents(max_score=30.0)
    assert "untrusted" in untrusted
    print("OK: trusted untrusted")


def test_average_score():
    """Average score calculation."""
    ts = AgentTrustScorer()
    ts.register_agent("a", initial_score=60.0)
    ts.register_agent("b", initial_score=40.0)

    assert ts.get_average_score() == 50.0
    print("OK: average score")


def test_low_trust_callback():
    """Callback fires when trust drops below 20."""
    ts = AgentTrustScorer()
    ts.register_agent("agent-1", initial_score=25.0)

    fired = []
    ts.on_change("mon", lambda a, d: fired.append(a))

    ts.record_event("agent-1", "violation", delta=-10.0)  # 25->15
    assert "trust_low" in fired
    print("OK: low trust callback")


def test_high_trust_callback():
    """Callback fires when trust rises above 80."""
    ts = AgentTrustScorer()
    ts.register_agent("agent-1", initial_score=75.0)

    fired = []
    ts.on_change("mon", lambda a, d: fired.append(a))

    ts.record_event("agent-1", "manual_boost", delta=10.0)  # 75->85
    assert "trust_high" in fired
    print("OK: high trust callback")


def test_callbacks():
    """Callback registration."""
    ts = AgentTrustScorer()
    assert ts.on_change("mon", lambda a, d: None) is True
    assert ts.on_change("mon", lambda a, d: None) is False
    assert ts.remove_callback("mon") is True
    assert ts.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    ts = AgentTrustScorer()
    ts.register_agent("a")
    ts.record_event("a", "task_completed")
    ts.record_event("a", "task_failed")

    stats = ts.get_stats()
    assert stats["total_registered"] == 1
    assert stats["total_events"] == 2
    assert stats["total_positive"] == 1
    assert stats["total_negative"] == 1
    assert stats["current_agents"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    ts = AgentTrustScorer()
    ts.register_agent("a")

    ts.reset()
    assert ts.list_agents() == []
    stats = ts.get_stats()
    assert stats["current_agents"] == 0
    print("OK: reset")


def main():
    print("=== Agent Trust Scorer Tests ===\n")
    test_register_agent()
    test_invalid_registration()
    test_max_agents()
    test_initial_score()
    test_record_event()
    test_invalid_event()
    test_custom_delta()
    test_score_bounds()
    test_positive_negative_counts()
    test_get_history()
    test_history_pruning()
    test_list_agents()
    test_ranking()
    test_trusted_untrusted()
    test_average_score()
    test_low_trust_callback()
    test_high_trust_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 20 TESTS PASSED ===")


if __name__ == "__main__":
    main()
