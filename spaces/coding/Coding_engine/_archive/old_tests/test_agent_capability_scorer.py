"""Test agent capability scorer."""
import sys
sys.path.insert(0, ".")

from src.services.agent_capability_scorer import AgentCapabilityScorer


def test_score():
    """Score and retrieve capability."""
    cs = AgentCapabilityScorer()
    sid = cs.score("worker1", "coding", 0.9, tags=["core"])
    assert sid.startswith("cap-")

    s = cs.get_score(sid)
    assert s is not None
    assert s["agent"] == "worker1"
    assert s["capability"] == "coding"
    assert s["score"] == 0.9
    assert s["evidence_count"] == 1

    assert cs.remove_score(sid) is True
    assert cs.remove_score(sid) is False
    print("OK: score")


def test_invalid_score():
    """Invalid scoring rejected."""
    cs = AgentCapabilityScorer()
    assert cs.score("", "cap", 0.5) == ""
    assert cs.score("agent", "", 0.5) == ""
    assert cs.score("agent", "cap", -0.1) == ""
    assert cs.score("agent", "cap", 1.1) == ""
    assert cs.score("agent", "cap", 0.5, weight=-1.0) == ""
    print("OK: invalid score")


def test_update_existing():
    """Update score for existing agent+capability."""
    cs = AgentCapabilityScorer()
    sid1 = cs.score("w1", "coding", 0.7)
    sid2 = cs.score("w1", "coding", 0.9)

    assert sid1 == sid2  # same entry updated
    s = cs.get_score(sid1)
    assert s["score"] == 0.9
    assert s["evidence_count"] == 2
    print("OK: update existing")


def test_max_entries():
    """Max entries enforced."""
    cs = AgentCapabilityScorer(max_entries=2)
    cs.score("a", "cap1", 0.5)
    cs.score("b", "cap1", 0.5)
    assert cs.score("c", "cap1", 0.5) == ""
    print("OK: max entries")


def test_agent_profile():
    """Get capability profile for agent."""
    cs = AgentCapabilityScorer()
    cs.score("w1", "coding", 0.9)
    cs.score("w1", "testing", 0.7)
    cs.score("w1", "docs", 0.5)

    profile = cs.get_agent_profile("w1")
    assert profile["coding"] == 0.9
    assert profile["testing"] == 0.7
    assert profile["docs"] == 0.5

    assert cs.get_agent_profile("nonexistent") == {}
    print("OK: agent profile")


def test_weighted_score():
    """Get weighted average score."""
    cs = AgentCapabilityScorer()
    cs.score("w1", "coding", 0.8, weight=2.0)
    cs.score("w1", "testing", 0.4, weight=1.0)

    ws = cs.get_weighted_score("w1")
    # (0.8*2 + 0.4*1) / (2+1) = 2.0/3.0 ≈ 0.667
    assert abs(ws - 0.667) < 0.01

    assert cs.get_weighted_score("nonexistent") == 0.0
    print("OK: weighted score")


def test_rank_agents():
    """Rank agents for capability."""
    cs = AgentCapabilityScorer()
    cs.score("w1", "coding", 0.7)
    cs.score("w2", "coding", 0.9)
    cs.score("w3", "coding", 0.5)

    ranking = cs.rank_agents_for_capability("coding")
    assert len(ranking) == 3
    assert ranking[0]["agent"] == "w2"
    assert ranking[1]["agent"] == "w1"
    assert ranking[2]["agent"] == "w3"
    print("OK: rank agents")


def test_find_best_agent():
    """Find best agent for capability."""
    cs = AgentCapabilityScorer()
    cs.score("w1", "coding", 0.7)
    cs.score("w2", "coding", 0.9)

    assert cs.find_best_agent("coding") == "w2"
    assert cs.find_best_agent("nonexistent") is None
    print("OK: find best agent")


def test_compare_agents():
    """Compare two agents."""
    cs = AgentCapabilityScorer()
    cs.score("w1", "coding", 0.9)
    cs.score("w1", "testing", 0.5)
    cs.score("w2", "coding", 0.6)
    cs.score("w2", "docs", 0.8)

    comp = cs.compare_agents("w1", "w2")
    assert comp["coding"]["winner"] == "w1"
    assert comp["testing"]["winner"] == "w1"
    assert comp["docs"]["winner"] == "w2"
    print("OK: compare agents")


def test_list_scores():
    """List scores with filters."""
    cs = AgentCapabilityScorer()
    cs.score("w1", "coding", 0.9, tags=["core"])
    cs.score("w2", "testing", 0.7)

    all_s = cs.list_scores()
    assert len(all_s) == 2

    by_agent = cs.list_scores(agent="w1")
    assert len(by_agent) == 1

    by_cap = cs.list_scores(capability="testing")
    assert len(by_cap) == 1

    by_tag = cs.list_scores(tag="core")
    assert len(by_tag) == 1
    print("OK: list scores")


def test_callback():
    """Callback fires on events."""
    cs = AgentCapabilityScorer()
    fired = []
    cs.on_change("mon", lambda a, d: fired.append(a))

    cs.score("w1", "coding", 0.9)
    assert "capability_scored" in fired

    cs.score("w1", "coding", 0.8)
    assert "score_updated" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    cs = AgentCapabilityScorer()
    assert cs.on_change("mon", lambda a, d: None) is True
    assert cs.on_change("mon", lambda a, d: None) is False
    assert cs.remove_callback("mon") is True
    assert cs.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    cs = AgentCapabilityScorer()
    cs.score("w1", "coding", 0.9)
    cs.score("w2", "testing", 0.7)
    cs.score("w1", "coding", 0.8)  # update

    stats = cs.get_stats()
    assert stats["current_scores"] == 2
    assert stats["total_scored"] == 2
    assert stats["total_evaluations"] == 3
    assert stats["unique_agents"] == 2
    assert stats["unique_capabilities"] == 2
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    cs = AgentCapabilityScorer()
    cs.score("w1", "coding", 0.9)

    cs.reset()
    assert cs.list_scores() == []
    stats = cs.get_stats()
    assert stats["current_scores"] == 0
    print("OK: reset")


def main():
    print("=== Agent Capability Scorer Tests ===\n")
    test_score()
    test_invalid_score()
    test_update_existing()
    test_max_entries()
    test_agent_profile()
    test_weighted_score()
    test_rank_agents()
    test_find_best_agent()
    test_compare_agents()
    test_list_scores()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 14 TESTS PASSED ===")


if __name__ == "__main__":
    main()
