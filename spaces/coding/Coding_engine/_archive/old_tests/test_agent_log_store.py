"""Test agent log store -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_log_store import AgentLogStore


def test_log():
    ls = AgentLogStore()
    lid = ls.log("agent-1", "info", "Task started", context={"task": "build"}, tags=["ops"])
    assert len(lid) > 0
    l = ls.get_log(lid)
    assert l is not None
    assert l["agent_id"] == "agent-1"
    assert l["message"] == "Task started"
    print("OK: log")


def test_get_agent_logs():
    ls = AgentLogStore()
    ls.log("agent-1", "info", "msg1")
    ls.log("agent-1", "error", "msg2")
    ls.log("agent-1", "info", "msg3")
    all_logs = ls.get_agent_logs("agent-1")
    assert len(all_logs) == 3
    info_logs = ls.get_agent_logs("agent-1", level="info")
    assert len(info_logs) == 2
    print("OK: get agent logs")


def test_search_logs():
    ls = AgentLogStore()
    ls.log("agent-1", "info", "Deployment started")
    ls.log("agent-1", "info", "Build complete")
    ls.log("agent-1", "error", "Deployment failed")
    results = ls.search_logs("Deployment")
    assert len(results) == 2
    print("OK: search logs")


def test_get_log_count():
    ls = AgentLogStore()
    ls.log("agent-1", "info", "msg1")
    ls.log("agent-1", "error", "msg2")
    ls.log("agent-2", "info", "msg3")
    assert ls.get_log_count(agent_id="agent-1") == 2
    assert ls.get_log_count(level="info") == 2
    assert ls.get_log_count() == 3
    print("OK: get log count")


def test_list_agents():
    ls = AgentLogStore()
    ls.log("agent-1", "info", "msg")
    ls.log("agent-2", "info", "msg")
    agents = ls.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_purge():
    ls = AgentLogStore()
    ls.log("agent-1", "info", "msg")
    import time
    time.sleep(0.01)
    count = ls.purge(before_timestamp=time.time() + 1)
    assert count >= 1
    print("OK: purge")


def test_callbacks():
    ls = AgentLogStore()
    fired = []
    ls.on_change("mon", lambda a, d: fired.append(a))
    ls.log("agent-1", "info", "msg")
    assert len(fired) >= 1
    assert ls.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    ls = AgentLogStore()
    ls.log("agent-1", "info", "msg")
    stats = ls.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    ls = AgentLogStore()
    ls.log("agent-1", "info", "msg")
    ls.reset()
    assert ls.list_agents() == []
    print("OK: reset")


def main():
    print("=== Agent Log Store Tests ===\n")
    test_log()
    test_get_agent_logs()
    test_search_logs()
    test_get_log_count()
    test_list_agents()
    test_purge()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 9 TESTS PASSED ===")


if __name__ == "__main__":
    main()
