"""Test agent status reporter -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_status_reporter import AgentStatusReporter


def test_report_status():
    r = AgentStatusReporter()
    rid = r.report_status("agent-1", "idle", {"cpu": 10})
    assert len(rid) > 0
    assert rid.startswith("asr-")
    print("OK: report status")


def test_get_status():
    r = AgentStatusReporter()
    r.report_status("agent-1", "idle")
    r.report_status("agent-1", "busy")
    status = r.get_status("agent-1")
    assert status is not None
    assert status["status"] == "busy"
    assert r.get_status("nonexistent") is None
    print("OK: get status")


def test_get_status_history():
    r = AgentStatusReporter()
    r.report_status("agent-1", "idle")
    r.report_status("agent-1", "busy")
    r.report_status("agent-1", "error")
    history = r.get_status_history("agent-1", limit=2)
    assert len(history) == 2
    assert history[-1]["status"] == "error"
    print("OK: get status history")


def test_get_agents_by_status():
    r = AgentStatusReporter()
    r.report_status("agent-1", "idle")
    r.report_status("agent-2", "busy")
    r.report_status("agent-3", "idle")
    idle_agents = r.get_agents_by_status("idle")
    assert "agent-1" in idle_agents
    assert "agent-3" in idle_agents
    assert "agent-2" not in idle_agents
    print("OK: get agents by status")


def test_get_report_count():
    r = AgentStatusReporter()
    r.report_status("agent-1", "idle")
    r.report_status("agent-2", "busy")
    assert r.get_report_count() == 2
    assert r.get_report_count("agent-1") == 1
    print("OK: get report count")


def test_list_agents():
    r = AgentStatusReporter()
    r.report_status("agent-1", "idle")
    r.report_status("agent-2", "busy")
    agents = r.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    r = AgentStatusReporter()
    fired = []
    r.on_change("mon", lambda a, d: fired.append(a))
    r.report_status("agent-1", "idle")
    assert len(fired) >= 1
    assert r.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    r = AgentStatusReporter()
    r.report_status("agent-1", "idle")
    stats = r.get_stats()
    assert len(stats) > 0
    assert stats["total_reported"] == 1
    print("OK: stats")


def test_reset():
    r = AgentStatusReporter()
    r.report_status("agent-1", "idle")
    r.reset()
    assert r.get_report_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Status Reporter Tests ===\n")
    test_report_status()
    test_get_status()
    test_get_status_history()
    test_get_agents_by_status()
    test_get_report_count()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 9 TESTS PASSED ===")


if __name__ == "__main__":
    main()
