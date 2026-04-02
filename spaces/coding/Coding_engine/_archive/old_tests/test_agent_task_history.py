"""Test agent task history -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_task_history import AgentTaskHistory


def test_record_task():
    th = AgentTaskHistory()
    rid = th.record_task("agent-1", "build", duration=5.0)
    assert len(rid) > 0
    assert rid.startswith("ath-")
    print("OK: record task")


def test_get_record():
    th = AgentTaskHistory()
    rid = th.record_task("agent-1", "build", duration=5.0, metadata={"env": "prod"})
    rec = th.get_record(rid)
    assert rec is not None
    assert rec["record_id"] == rid
    assert rec["agent_id"] == "agent-1"
    assert rec["task_type"] == "build"
    assert rec["status"] == "completed"
    assert th.get_record("nonexistent") is None
    print("OK: get record")


def test_get_agent_history():
    th = AgentTaskHistory()
    th.record_task("agent-1", "build")
    th.record_task("agent-1", "test")
    th.record_task("agent-2", "deploy")
    history = th.get_agent_history("agent-1")
    assert len(history) == 2
    print("OK: get agent history")


def test_get_task_types():
    th = AgentTaskHistory()
    th.record_task("agent-1", "build")
    th.record_task("agent-1", "test")
    types = th.get_task_types("agent-1")
    assert "build" in types
    assert "test" in types
    print("OK: get task types")


def test_get_success_rate():
    th = AgentTaskHistory()
    th.record_task("agent-1", "build", status="completed")
    th.record_task("agent-1", "build", status="completed")
    th.record_task("agent-1", "build", status="failed")
    rate = th.get_success_rate("agent-1")
    assert abs(rate - 2.0/3.0) < 0.01
    print("OK: get success rate")


def test_get_average_duration():
    th = AgentTaskHistory()
    th.record_task("agent-1", "build", duration=10.0)
    th.record_task("agent-1", "build", duration=20.0)
    avg = th.get_average_duration("agent-1")
    assert avg == 15.0
    print("OK: get average duration")


def test_get_record_count():
    th = AgentTaskHistory()
    th.record_task("agent-1", "build")
    th.record_task("agent-1", "test")
    assert th.get_record_count("agent-1") == 2
    assert th.get_record_count() >= 2
    print("OK: get record count")


def test_purge():
    th = AgentTaskHistory()
    for i in range(10):
        th.record_task("agent-1", f"task-{i}")
    removed = th.purge("agent-1", keep_latest=3)
    assert removed == 7
    assert th.get_record_count("agent-1") == 3
    print("OK: purge")


def test_list_agents():
    th = AgentTaskHistory()
    th.record_task("agent-1", "build")
    th.record_task("agent-2", "test")
    agents = th.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_search_history():
    th = AgentTaskHistory()
    th.record_task("agent-1", "build", status="completed")
    th.record_task("agent-1", "test", status="failed")
    th.record_task("agent-2", "build", status="completed")
    results = th.search_history(task_type="build")
    assert len(results) == 2
    print("OK: search history")


def test_callbacks():
    th = AgentTaskHistory()
    fired = []
    th.on_change("mon", lambda a, d: fired.append(a))
    th.record_task("agent-1", "build")
    assert len(fired) >= 1
    assert th.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    th = AgentTaskHistory()
    th.record_task("agent-1", "build")
    stats = th.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    th = AgentTaskHistory()
    th.record_task("agent-1", "build")
    th.reset()
    assert th.get_record_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Task History Tests ===\n")
    test_record_task()
    test_get_record()
    test_get_agent_history()
    test_get_task_types()
    test_get_success_rate()
    test_get_average_duration()
    test_get_record_count()
    test_purge()
    test_list_agents()
    test_search_history()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 13 TESTS PASSED ===")


if __name__ == "__main__":
    main()
