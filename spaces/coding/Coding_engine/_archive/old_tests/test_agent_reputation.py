"""Test agent reputation system."""
import sys
sys.path.insert(0, ".")

from src.services.agent_reputation import AgentReputation


def test_register():
    """Register and unregister agents."""
    rep = AgentReputation()
    assert rep.register("Builder", initial_score=60.0, tags={"core"}) is True
    assert rep.register("Builder") is False  # Duplicate

    agent = rep.get_agent("Builder")
    assert agent is not None
    assert agent["score"] == 60.0
    assert "core" in agent["tags"]

    assert rep.unregister("Builder") is True
    assert rep.unregister("Builder") is False
    assert rep.get_agent("Builder") is None
    print("OK: register")


def test_record_success():
    """Record successful task."""
    rep = AgentReputation(success_weight=5.0)
    rep.register("Builder")

    assert rep.record_success("Builder", task_type="build") is True
    agent = rep.get_agent("Builder")
    assert agent["score"] == 55.0
    assert agent["total_tasks"] == 1
    assert agent["successful_tasks"] == 1

    assert rep.record_success("nonexistent") is False
    print("OK: record success")


def test_record_failure():
    """Record failed task."""
    rep = AgentReputation(failure_weight=10.0)
    rep.register("Builder")

    assert rep.record_failure("Builder", task_type="build") is True
    agent = rep.get_agent("Builder")
    assert agent["score"] == 40.0
    assert agent["failed_tasks"] == 1

    assert rep.record_failure("nonexistent") is False
    print("OK: record failure")


def test_score_bounds():
    """Score stays within 0-100."""
    rep = AgentReputation(success_weight=60.0, failure_weight=60.0)
    rep.register("High", initial_score=90.0)
    rep.register("Low", initial_score=10.0)

    rep.record_success("High")
    assert rep.get_agent("High")["score"] == 100.0

    rep.record_failure("Low")
    assert rep.get_agent("Low")["score"] == 0.0
    print("OK: score bounds")


def test_reward():
    """Manual reward."""
    rep = AgentReputation()
    rep.register("Builder")

    assert rep.reward("Builder", 10.0, reason="Great work") is True
    assert rep.get_agent("Builder")["score"] == 60.0
    assert rep.get_agent("Builder")["total_rewards"] == 10.0

    assert rep.reward("nonexistent", 5.0) is False
    print("OK: reward")


def test_penalize():
    """Manual penalty."""
    rep = AgentReputation()
    rep.register("Builder")

    assert rep.penalize("Builder", 15.0, reason="Timeout") is True
    assert rep.get_agent("Builder")["score"] == 35.0
    assert rep.get_agent("Builder")["total_penalties"] == 15.0

    assert rep.penalize("nonexistent", 5.0) is False
    print("OK: penalize")


def test_decay():
    """Decay pulls scores toward 50."""
    rep = AgentReputation(decay_factor=0.5)
    rep.register("High", initial_score=90.0)
    rep.register("Low", initial_score=10.0)
    rep.register("Mid", initial_score=50.0)

    affected = rep.apply_decay()
    assert affected == 2  # Mid doesn't change

    high = rep.get_agent("High")["score"]
    low = rep.get_agent("Low")["score"]
    assert 50.0 < high < 90.0  # Decayed toward 50
    assert 10.0 < low < 50.0
    print("OK: decay")


def test_list_agents():
    """List agents with filters."""
    rep = AgentReputation()
    rep.register("A", initial_score=80.0, tags={"core"})
    rep.register("B", initial_score=30.0)
    rep.register("C", initial_score=60.0, tags={"core"})

    all_agents = rep.list_agents()
    assert len(all_agents) == 3
    # Sorted by score desc
    assert all_agents[0]["agent_name"] == "A"

    filtered = rep.list_agents(min_score=50.0)
    assert len(filtered) == 2

    by_tag = rep.list_agents(tag="core")
    assert len(by_tag) == 2

    limited = rep.list_agents(limit=1)
    assert len(limited) == 1
    print("OK: list agents")


def test_ranking():
    """Get agent ranking."""
    rep = AgentReputation()
    rep.register("A", initial_score=80.0)
    rep.register("B", initial_score=90.0)
    rep.register("C", initial_score=70.0)

    ranking = rep.get_ranking()
    assert ranking[0]["agent_name"] == "B"
    assert ranking[0]["rank"] == 1
    assert ranking[1]["rank"] == 2
    print("OK: ranking")


def test_task_type_scores():
    """Per-task-type scoring."""
    rep = AgentReputation(success_weight=5.0, failure_weight=10.0)
    rep.register("Builder")

    rep.record_success("Builder", task_type="build")
    rep.record_success("Builder", task_type="build")
    rep.record_failure("Builder", task_type="test")

    leaders = rep.get_task_type_leaders("build")
    assert len(leaders) == 1
    assert leaders[0]["count"] == 2
    assert leaders[0]["successes"] == 2
    assert leaders[0]["success_rate"] == 100.0

    test_leaders = rep.get_task_type_leaders("test")
    assert len(test_leaders) == 1
    assert test_leaders[0]["success_rate"] == 0.0
    print("OK: task type scores")


def test_recommend():
    """Recommend agents for task type."""
    rep = AgentReputation()
    rep.register("Builder", initial_score=80.0)
    rep.register("Tester", initial_score=60.0)
    rep.register("Bad", initial_score=20.0)

    recs = rep.recommend(min_score=30.0)
    assert len(recs) == 2  # Bad excluded
    assert recs[0]["agent_name"] == "Builder"
    print("OK: recommend")


def test_history():
    """Get reputation history."""
    rep = AgentReputation()
    rep.register("Builder")
    rep.record_success("Builder", task_type="build")
    rep.record_failure("Builder", task_type="test")
    rep.reward("Builder", 5.0, reason="bonus")

    history = rep.get_history("Builder")
    assert len(history) == 3
    assert history[0]["event_type"] == "success"
    assert history[1]["event_type"] == "failure"
    assert history[2]["event_type"] == "reward"

    successes = rep.get_history("Builder", event_type="success")
    assert len(successes) == 1

    assert rep.get_history("nonexistent") == []
    print("OK: history")


def test_trend():
    """Get reputation trend."""
    rep = AgentReputation(success_weight=5.0)
    rep.register("Builder")

    # No history
    assert rep.get_trend("nonexistent") is None

    # Single event
    rep.record_success("Builder")
    trend = rep.get_trend("Builder")
    assert trend["direction"] == "stable"

    # Improving
    for _ in range(5):
        rep.record_success("Builder")
    trend = rep.get_trend("Builder")
    assert trend["direction"] == "improving"
    assert trend["change"] > 0

    # Declining
    rep2 = AgentReputation(failure_weight=10.0)
    rep2.register("Bad")
    for _ in range(5):
        rep2.record_failure("Bad")
    trend = rep2.get_trend("Bad")
    assert trend["direction"] == "declining"
    assert trend["change"] < 0
    print("OK: trend")


def test_custom_weight():
    """Record with custom weight."""
    rep = AgentReputation()
    rep.register("Builder")

    rep.record_success("Builder", weight=20.0)
    assert rep.get_agent("Builder")["score"] == 70.0
    print("OK: custom weight")


def test_stats():
    """Stats are accurate."""
    rep = AgentReputation()
    rep.register("A")
    rep.register("B")
    rep.record_success("A")
    rep.record_failure("B")
    rep.reward("A", 5.0)
    rep.penalize("B", 3.0)

    stats = rep.get_stats()
    assert stats["total_registered"] == 2
    assert stats["total_agents"] == 2
    assert stats["total_events"] == 4
    assert stats["total_rewards"] == 1
    assert stats["total_penalties"] == 1
    assert stats["avg_score"] > 0
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    rep = AgentReputation()
    rep.register("Builder")
    rep.record_success("Builder")

    rep.reset()
    assert rep.get_agent("Builder") is None
    assert rep.list_agents() == []
    stats = rep.get_stats()
    assert stats["total_agents"] == 0
    print("OK: reset")


def main():
    print("=== Agent Reputation Tests ===\n")
    test_register()
    test_record_success()
    test_record_failure()
    test_score_bounds()
    test_reward()
    test_penalize()
    test_decay()
    test_list_agents()
    test_ranking()
    test_task_type_scores()
    test_recommend()
    test_history()
    test_trend()
    test_custom_weight()
    test_stats()
    test_reset()
    print("\n=== ALL 16 TESTS PASSED ===")


if __name__ == "__main__":
    main()
