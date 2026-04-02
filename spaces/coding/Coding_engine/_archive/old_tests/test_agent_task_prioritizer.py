"""Test agent task prioritizer -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_task_prioritizer import AgentTaskPrioritizer


def test_set_priority():
    tp = AgentTaskPrioritizer()
    pid = tp.set_priority("agent-1", "build", priority=8)
    assert len(pid) > 0
    assert pid.startswith("atp-")
    print("OK: set priority")


def test_get_priority():
    tp = AgentTaskPrioritizer()
    tp.set_priority("agent-1", "build", priority=8)
    assert tp.get_priority("agent-1", "build") == 8
    assert tp.get_priority("agent-1", "nonexistent") == 0
    print("OK: get priority")


def test_get_top_tasks():
    tp = AgentTaskPrioritizer()
    tp.set_priority("agent-1", "low", priority=1)
    tp.set_priority("agent-1", "high", priority=10)
    tp.set_priority("agent-1", "medium", priority=5)
    top = tp.get_top_tasks("agent-1", limit=2)
    assert len(top) == 2
    assert top[0]["task_name"] == "high"
    assert top[0]["priority"] == 10
    print("OK: get top tasks")


def test_remove_priority():
    tp = AgentTaskPrioritizer()
    tp.set_priority("agent-1", "build", priority=5)
    assert tp.remove_priority("agent-1", "build") is True
    assert tp.remove_priority("agent-1", "nonexistent") is False
    assert tp.get_priority("agent-1", "build") == 0
    print("OK: remove priority")


def test_get_task_count():
    tp = AgentTaskPrioritizer()
    tp.set_priority("agent-1", "build", priority=5)
    tp.set_priority("agent-1", "test", priority=3)
    tp.set_priority("agent-2", "deploy", priority=7)
    assert tp.get_task_count("agent-1") == 2
    assert tp.get_task_count() == 3
    print("OK: get task count")


def test_list_agents():
    tp = AgentTaskPrioritizer()
    tp.set_priority("agent-1", "build")
    tp.set_priority("agent-2", "test")
    agents = tp.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    tp = AgentTaskPrioritizer()
    fired = []
    tp.on_change("mon", lambda a, d: fired.append(a))
    tp.set_priority("agent-1", "build")
    assert len(fired) >= 1
    assert tp.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    tp = AgentTaskPrioritizer()
    tp.set_priority("agent-1", "build")
    stats = tp.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    tp = AgentTaskPrioritizer()
    tp.set_priority("agent-1", "build")
    tp.reset()
    assert tp.get_task_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Task Prioritizer Tests ===\n")
    test_set_priority()
    test_get_priority()
    test_get_top_tasks()
    test_remove_priority()
    test_get_task_count()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 9 TESTS PASSED ===")


if __name__ == "__main__":
    main()
