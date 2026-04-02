"""Tests for AgentDecisionLogger."""

import sys
import time

sys.path.insert(0, "src/services")

from agent_decision_logger import AgentDecisionLogger


def test_log_decision():
    svc = AgentDecisionLogger()
    did = svc.log_decision("agent-1", "use model A", reasoning="faster", alternatives=["model B", "model C"], outcome="pending")
    assert did.startswith("adl-"), f"Expected adl- prefix, got {did}"
    assert len(did) > 5
    # verify stored
    rec = svc.get_decision(did)
    assert rec is not None
    assert rec["agent_id"] == "agent-1"
    assert rec["decision"] == "use model A"
    assert rec["reasoning"] == "faster"
    assert rec["alternatives"] == ["model B", "model C"]
    assert rec["outcome"] == "pending"
    assert "timestamp" in rec
    print("  test_log_decision PASSED")


def test_get_decisions():
    svc = AgentDecisionLogger()
    svc.log_decision("agent-1", "d1")
    time.sleep(0.01)
    svc.log_decision("agent-1", "d2")
    time.sleep(0.01)
    svc.log_decision("agent-2", "d3")

    decs = svc.get_decisions("agent-1")
    assert len(decs) == 2
    # most recent first
    assert decs[0]["decision"] == "d2"
    assert decs[1]["decision"] == "d1"

    # limit
    decs2 = svc.get_decisions("agent-1", limit=1)
    assert len(decs2) == 1
    assert decs2[0]["decision"] == "d2"
    print("  test_get_decisions PASSED")


def test_get_decision():
    svc = AgentDecisionLogger()
    did = svc.log_decision("agent-1", "pick X", reasoning="best option")
    rec = svc.get_decision(did)
    assert rec is not None
    assert rec["decision"] == "pick X"
    assert rec["reasoning"] == "best option"

    # nonexistent
    assert svc.get_decision("adl-nonexistent") is None
    print("  test_get_decision PASSED")


def test_update_outcome():
    svc = AgentDecisionLogger()
    did = svc.log_decision("agent-1", "choose path", outcome="pending")
    assert svc.update_outcome(did, "success") is True
    rec = svc.get_decision(did)
    assert rec["outcome"] == "success"

    # nonexistent
    assert svc.update_outcome("adl-fake", "fail") is False
    print("  test_update_outcome PASSED")


def test_get_decision_count():
    svc = AgentDecisionLogger()
    svc.log_decision("agent-1", "d1")
    svc.log_decision("agent-1", "d2")
    svc.log_decision("agent-2", "d3")

    assert svc.get_decision_count() == 3
    assert svc.get_decision_count("agent-1") == 2
    assert svc.get_decision_count("agent-2") == 1
    assert svc.get_decision_count("agent-99") == 0
    # empty string means all
    assert svc.get_decision_count("") == 3
    print("  test_get_decision_count PASSED")


def test_clear_decisions():
    svc = AgentDecisionLogger()
    svc.log_decision("agent-1", "d1")
    svc.log_decision("agent-1", "d2")
    svc.log_decision("agent-2", "d3")

    removed = svc.clear_decisions("agent-1")
    assert removed == 2
    assert svc.get_decision_count("agent-1") == 0
    assert svc.get_decision_count("agent-2") == 1
    assert svc.get_decision_count() == 1
    print("  test_clear_decisions PASSED")


def test_list_agents():
    svc = AgentDecisionLogger()
    svc.log_decision("agent-b", "d1")
    svc.log_decision("agent-a", "d2")
    svc.log_decision("agent-b", "d3")

    agents = svc.list_agents()
    assert agents == ["agent-a", "agent-b"]
    print("  test_list_agents PASSED")


def test_callbacks():
    svc = AgentDecisionLogger()
    events = []

    def handler(action, detail):
        events.append((action, detail))

    svc.on_change("cb1", handler)
    svc.log_decision("agent-1", "d1")
    assert len(events) == 1
    assert events[0][0] == "decision_logged"
    assert events[0][1]["agent_id"] == "agent-1"

    # remove_callback returns bool
    assert svc.remove_callback("cb1") is True
    assert svc.remove_callback("cb1") is False

    svc.log_decision("agent-1", "d2")
    assert len(events) == 1  # no new event
    print("  test_callbacks PASSED")


def test_stats():
    svc = AgentDecisionLogger()
    svc.log_decision("agent-1", "d1")
    svc.log_decision("agent-2", "d2")

    stats = svc.get_stats()
    assert stats["total_logged"] == 2
    assert stats["current_entries"] == 2
    assert stats["unique_agents"] == 2
    assert stats["max_entries"] == 10000
    assert "total_pruned" in stats
    print("  test_stats PASSED")


def test_reset():
    svc = AgentDecisionLogger()
    svc.log_decision("agent-1", "d1")
    svc.log_decision("agent-2", "d2")
    assert svc.get_decision_count() == 2

    svc.reset()
    assert svc.get_decision_count() == 0
    assert svc.list_agents() == []
    stats = svc.get_stats()
    assert stats["total_logged"] == 0
    assert stats["current_entries"] == 0
    print("  test_reset PASSED")


if __name__ == "__main__":
    test_log_decision()
    test_get_decisions()
    test_get_decision()
    test_update_outcome()
    test_get_decision_count()
    test_clear_decisions()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")
