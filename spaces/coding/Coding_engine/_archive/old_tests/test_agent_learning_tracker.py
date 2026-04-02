"""Test agent learning tracker -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_learning_tracker import AgentLearningTracker


def test_register_agent():
    lt = AgentLearningTracker()
    aid = lt.register_agent("agent-1", tags=["ml"])
    assert len(aid) > 0
    p = lt.get_agent_profile("agent-1")
    assert p is not None
    assert lt.register_agent("agent-1") == ""  # dup
    print("OK: register agent")


def test_record_learning():
    lt = AgentLearningTracker()
    lt.register_agent("agent-1")
    assert lt.record_learning("agent-1", "python", 0.6) is True
    assert lt.record_learning("agent-1", "python", 0.8) is True
    print("OK: record learning")


def test_skill_progress():
    lt = AgentLearningTracker()
    lt.register_agent("agent-1")
    lt.record_learning("agent-1", "python", 0.5)
    lt.record_learning("agent-1", "python", 0.7)
    lt.record_learning("agent-1", "python", 0.9)
    prog = lt.get_skill_progress("agent-1", "python")
    assert prog is not None
    print("OK: skill progress")


def test_learning_curve():
    lt = AgentLearningTracker()
    lt.register_agent("agent-1")
    for score in [0.3, 0.5, 0.7, 0.9]:
        lt.record_learning("agent-1", "python", score)
    curve = lt.get_learning_curve("agent-1", "python")
    assert len(curve) == 4
    print("OK: learning curve")


def test_top_learners():
    lt = AgentLearningTracker()
    lt.register_agent("a1")
    lt.register_agent("a2")
    lt.record_learning("a1", "python", 0.7)
    lt.record_learning("a1", "python", 0.9)
    lt.record_learning("a2", "python", 0.5)
    lt.record_learning("a2", "python", 0.3)
    top = lt.get_top_learners(limit=2)
    assert len(top) >= 1
    print("OK: top learners")


def test_struggling_agents():
    lt = AgentLearningTracker()
    lt.register_agent("good")
    lt.register_agent("bad")
    lt.record_learning("good", "python", 0.9)
    lt.record_learning("bad", "python", 0.1)
    struggling = lt.get_struggling_agents(threshold=0.3)
    assert len(struggling) >= 1
    print("OK: struggling agents")


def test_list_agents():
    lt = AgentLearningTracker()
    lt.register_agent("a1", tags=["ml"])
    lt.register_agent("a2")
    assert len(lt.list_agents()) == 2
    assert len(lt.list_agents(tag="ml")) == 1
    print("OK: list agents")


def test_remove_agent():
    lt = AgentLearningTracker()
    lt.register_agent("a1")
    assert lt.remove_agent("a1") is True
    assert lt.remove_agent("a1") is False
    print("OK: remove agent")


def test_callbacks():
    lt = AgentLearningTracker()
    fired = []
    lt.on_change("mon", lambda a, d: fired.append(a))
    lt.register_agent("a1")
    assert len(fired) >= 1
    assert lt.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    lt = AgentLearningTracker()
    lt.register_agent("a1")
    stats = lt.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    lt = AgentLearningTracker()
    lt.register_agent("a1")
    lt.reset()
    assert lt.list_agents() == []
    print("OK: reset")


def main():
    print("=== Agent Learning Tracker Tests ===\n")
    test_register_agent()
    test_record_learning()
    test_skill_progress()
    test_learning_curve()
    test_top_learners()
    test_struggling_agents()
    test_list_agents()
    test_remove_agent()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
