"""Test agent reputation tracker -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_reputation_tracker import AgentReputationTracker


def test_register_agent():
    rt = AgentReputationTracker()
    aid = rt.register_agent("agent-1", initial_score=50.0, tags=["backend"])
    assert aid.startswith("art-")
    rep = rt.get_reputation("agent-1")
    assert rep is not None
    assert rep["agent_id"] == "agent-1"
    assert rt.register_agent("agent-1") == ""  # dup
    print("OK: register agent")


def test_record_outcome():
    rt = AgentReputationTracker()
    rt.register_agent("agent-1", initial_score=50.0)
    assert rt.record_outcome("agent-1", "task-1", success=True, quality=0.9) is True
    rep = rt.get_reputation("agent-1")
    assert rep["total_tasks"] == 1
    assert rep["success_rate"] == 1.0
    rt.record_outcome("agent-1", "task-2", success=False, quality=0.2)
    rep2 = rt.get_reputation("agent-1")
    assert rep2["total_tasks"] == 2
    assert rep2["success_rate"] == 0.5
    print("OK: record outcome")


def test_rankings():
    rt = AgentReputationTracker()
    rt.register_agent("a1", initial_score=50.0)
    rt.register_agent("a2", initial_score=50.0)
    rt.register_agent("a3", initial_score=50.0)
    for i in range(5):
        rt.record_outcome("a1", f"t{i}", success=True, quality=0.95)
    for i in range(5):
        rt.record_outcome("a2", f"t{i}", success=True, quality=0.5)
    for i in range(5):
        rt.record_outcome("a3", f"t{i}", success=False, quality=0.1)
    rankings = rt.get_rankings(limit=3)
    assert len(rankings) == 3
    assert rankings[0]["agent_id"] == "a1"
    print("OK: rankings")


def test_underperformers():
    rt = AgentReputationTracker()
    rt.register_agent("good", initial_score=80.0)
    rt.register_agent("bad", initial_score=20.0)
    under = rt.get_underperformers(threshold=30.0)
    assert len(under) >= 1
    assert any(a["agent_id"] == "bad" for a in under)
    print("OK: underperformers")


def test_decay():
    rt = AgentReputationTracker()
    rt.register_agent("a1", initial_score=90.0)
    count = rt.apply_decay(decay_factor=0.9)
    assert count >= 1
    rep = rt.get_reputation("a1")
    assert rep["score"] < 90.0
    print("OK: decay")


def test_compare():
    rt = AgentReputationTracker()
    rt.register_agent("a1", initial_score=80.0)
    rt.register_agent("a2", initial_score=40.0)
    comp = rt.compare_agents("a1", "a2")
    assert comp is not None
    print("OK: compare")


def test_list_agents():
    rt = AgentReputationTracker()
    rt.register_agent("a1", tags=["gpu"])
    rt.register_agent("a2")
    assert len(rt.list_agents()) == 2
    assert len(rt.list_agents(tag="gpu")) == 1
    print("OK: list agents")


def test_remove():
    rt = AgentReputationTracker()
    rt.register_agent("a1")
    assert rt.remove_agent("a1") is True
    assert rt.remove_agent("a1") is False
    print("OK: remove")


def test_history():
    rt = AgentReputationTracker()
    rt.register_agent("a1")
    hist = rt.get_history()
    assert len(hist) >= 1
    print("OK: history")


def test_callbacks():
    rt = AgentReputationTracker()
    fired = []
    rt.on_change("mon", lambda a, d: fired.append(a))
    rt.register_agent("a1")
    assert len(fired) >= 1
    assert rt.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    rt = AgentReputationTracker()
    rt.register_agent("a1")
    stats = rt.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    rt = AgentReputationTracker()
    rt.register_agent("a1")
    rt.reset()
    assert rt.list_agents() == []
    print("OK: reset")


def main():
    print("=== Agent Reputation Tracker Tests ===\n")
    test_register_agent()
    test_record_outcome()
    test_rankings()
    test_underperformers()
    test_decay()
    test_compare()
    test_list_agents()
    test_remove()
    test_history()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 12 TESTS PASSED ===")


if __name__ == "__main__":
    main()
