"""Test agent feedback loop."""
import sys
sys.path.insert(0, ".")

from src.services.agent_feedback_loop import AgentFeedbackLoop


def test_submit_feedback():
    """Submit and retrieve feedback."""
    fl = AgentFeedbackLoop()
    fid = fl.submit_feedback("worker1", score=0.8, category="quality",
                              comment="good work", source="reviewer")
    assert fid.startswith("fbk-")

    f = fl.get_feedback(fid)
    assert f is not None
    assert f["agent"] == "worker1"
    assert f["score"] == 0.8
    assert f["category"] == "quality"

    assert fl.remove_feedback(fid) is True
    assert fl.remove_feedback(fid) is False
    print("OK: submit feedback")


def test_invalid_feedback():
    """Invalid feedback rejected."""
    fl = AgentFeedbackLoop()
    assert fl.submit_feedback("", score=0.5) == ""
    assert fl.submit_feedback("agent", score=0.5, category="invalid") == ""
    assert fl.submit_feedback("agent", score=-0.1) == ""
    assert fl.submit_feedback("agent", score=1.1) == ""
    print("OK: invalid feedback")


def test_agent_score():
    """Aggregate agent score."""
    fl = AgentFeedbackLoop()
    fl.submit_feedback("w1", score=0.8, category="quality")
    fl.submit_feedback("w1", score=0.6, category="quality")
    fl.submit_feedback("w1", score=1.0, category="speed")

    score = fl.get_agent_score("w1")
    assert score["count"] == 3
    assert abs(score["avg_score"] - 0.8) < 0.01
    assert score["min_score"] == 0.6
    assert score["max_score"] == 1.0

    by_cat = fl.get_agent_score("w1", category="quality")
    assert by_cat["count"] == 2

    empty = fl.get_agent_score("nonexistent")
    assert empty["count"] == 0
    print("OK: agent score")


def test_agent_score_limit():
    """Agent score with limit."""
    fl = AgentFeedbackLoop()
    for i in range(10):
        fl.submit_feedback("w1", score=float(i) / 10)

    score = fl.get_agent_score("w1", limit=3)
    assert score["count"] == 3
    print("OK: agent score limit")


def test_category_breakdown():
    """Category breakdown for agent."""
    fl = AgentFeedbackLoop()
    fl.submit_feedback("w1", score=0.8, category="quality")
    fl.submit_feedback("w1", score=0.6, category="quality")
    fl.submit_feedback("w1", score=0.9, category="speed")

    breakdown = fl.get_category_breakdown("w1")
    assert "quality" in breakdown
    assert "speed" in breakdown
    assert abs(breakdown["quality"] - 0.7) < 0.01
    assert abs(breakdown["speed"] - 0.9) < 0.01
    print("OK: category breakdown")


def test_search_feedback():
    """Search feedback with filters."""
    fl = AgentFeedbackLoop()
    fl.submit_feedback("w1", score=0.8, category="quality", source="rev1")
    fl.submit_feedback("w2", score=0.6, category="speed", source="rev2")

    all_f = fl.search_feedback()
    assert len(all_f) == 2

    by_agent = fl.search_feedback(agent="w1")
    assert len(by_agent) == 1

    by_cat = fl.search_feedback(category="speed")
    assert len(by_cat) == 1

    by_source = fl.search_feedback(source="rev1")
    assert len(by_source) == 1
    print("OK: search feedback")


def test_trend():
    """Agent trend analysis."""
    fl = AgentFeedbackLoop()
    # not enough data
    trend = fl.get_agent_trend("w1", window=5)
    assert trend["trend"] == "insufficient_data"

    # add enough data: 10 older (low) + 10 recent (high)
    for _ in range(10):
        fl.submit_feedback("w1", score=0.3)
    for _ in range(10):
        fl.submit_feedback("w1", score=0.9)

    trend = fl.get_agent_trend("w1", window=10)
    assert trend["trend"] == "improving"
    assert trend["recent_avg"] > trend["older_avg"]
    print("OK: trend")


def test_eviction():
    """Entries evicted when max reached."""
    fl = AgentFeedbackLoop(max_entries=10)
    for i in range(15):
        fl.submit_feedback("w1", score=0.5)
    assert fl.get_stats()["current_entries"] <= 10
    print("OK: eviction")


def test_callback():
    """Callback fires on events."""
    fl = AgentFeedbackLoop()
    fired = []
    fl.on_change("mon", lambda a, d: fired.append(a))

    fl.submit_feedback("w1", score=0.8)
    assert "feedback_submitted" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    fl = AgentFeedbackLoop()
    assert fl.on_change("mon", lambda a, d: None) is True
    assert fl.on_change("mon", lambda a, d: None) is False
    assert fl.remove_callback("mon") is True
    assert fl.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    fl = AgentFeedbackLoop()
    fl.submit_feedback("w1", score=0.8)
    fl.submit_feedback("w2", score=0.6)

    stats = fl.get_stats()
    assert stats["total_entries"] == 2
    assert stats["unique_agents"] == 2
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    fl = AgentFeedbackLoop()
    fl.submit_feedback("w1", score=0.8)

    fl.reset()
    assert fl.search_feedback() == []
    stats = fl.get_stats()
    assert stats["current_entries"] == 0
    print("OK: reset")


def main():
    print("=== Agent Feedback Loop Tests ===\n")
    test_submit_feedback()
    test_invalid_feedback()
    test_agent_score()
    test_agent_score_limit()
    test_category_breakdown()
    test_search_feedback()
    test_trend()
    test_eviction()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 12 TESTS PASSED ===")


if __name__ == "__main__":
    main()
