"""Tests for AgentAuditTrail service."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src", "services"))

from agent_audit_trail import AgentAuditTrail


def test_record():
    trail = AgentAuditTrail()
    eid = trail.record("agent-1", "deploy", resource="/api/v1", details={"version": "2.0"})
    assert eid.startswith("aat-"), f"Expected aat- prefix, got {eid}"
    assert len(eid) > 4
    # empty agent/action returns ""
    assert trail.record("", "deploy") == ""
    assert trail.record("agent-1", "") == ""
    print("  test_record PASSED")


def test_get_entries():
    trail = AgentAuditTrail()
    trail.record("agent-1", "deploy")
    trail.record("agent-1", "restart")
    trail.record("agent-2", "deploy")
    entries = trail.get_entries("agent-1")
    assert len(entries) == 2
    assert all(e["agent_id"] == "agent-1" for e in entries)
    # newest first
    assert entries[0]["_seq_num"] > entries[1]["_seq_num"]
    print("  test_get_entries PASSED")


def test_get_entries_filtered():
    trail = AgentAuditTrail()
    trail.record("agent-1", "deploy")
    trail.record("agent-1", "restart")
    trail.record("agent-1", "deploy")
    entries = trail.get_entries("agent-1", action="deploy")
    assert len(entries) == 2
    assert all(e["action"] == "deploy" for e in entries)
    print("  test_get_entries_filtered PASSED")


def test_get_latest_entry():
    trail = AgentAuditTrail()
    assert trail.get_latest_entry("agent-1") is None
    trail.record("agent-1", "deploy")
    trail.record("agent-1", "restart")
    latest = trail.get_latest_entry("agent-1")
    assert latest is not None
    assert latest["action"] == "restart"
    # seq_num deterministic
    assert latest["_seq_num"] == 2
    print("  test_get_latest_entry PASSED")


def test_get_entry_count():
    trail = AgentAuditTrail()
    trail.record("agent-1", "deploy")
    trail.record("agent-1", "restart")
    trail.record("agent-2", "deploy")
    assert trail.get_entry_count() == 3
    assert trail.get_entry_count("agent-1") == 2
    assert trail.get_entry_count("agent-2") == 1
    assert trail.get_entry_count("agent-3") == 0
    print("  test_get_entry_count PASSED")


def test_clear_entries():
    trail = AgentAuditTrail()
    trail.record("agent-1", "deploy")
    trail.record("agent-1", "restart")
    trail.record("agent-2", "deploy")
    removed = trail.clear_entries("agent-1")
    assert removed == 2
    assert trail.get_entry_count("agent-1") == 0
    assert trail.get_entry_count("agent-2") == 1
    # clearing again returns 0
    assert trail.clear_entries("agent-1") == 0
    print("  test_clear_entries PASSED")


def test_list_agents():
    trail = AgentAuditTrail()
    trail.record("agent-1", "deploy")
    trail.record("agent-2", "restart")
    trail.record("agent-3", "deploy")
    agents = trail.list_agents()
    assert set(agents) == {"agent-1", "agent-2", "agent-3"}
    print("  test_list_agents PASSED")


def test_search():
    trail = AgentAuditTrail()
    trail.record("agent-1", "deploy", resource="/api")
    trail.record("agent-2", "deploy", resource="/web")
    trail.record("agent-1", "restart", resource="/api")
    # search by action
    results = trail.search(action="deploy")
    assert len(results) == 2
    # search by resource
    results = trail.search(resource="/api")
    assert len(results) == 2
    # search by both
    results = trail.search(action="deploy", resource="/api")
    assert len(results) == 1
    assert results[0]["agent_id"] == "agent-1"
    # empty search returns all
    results = trail.search()
    assert len(results) == 3
    print("  test_search PASSED")


def test_callbacks():
    trail = AgentAuditTrail()
    events = []
    trail.on_change("cb1", lambda action, detail: events.append((action, detail)))
    trail.record("agent-1", "deploy")
    assert len(events) == 1
    assert events[0][0] == "entry_recorded"
    # remove_callback returns True/False
    assert trail.remove_callback("cb1") is True
    assert trail.remove_callback("cb1") is False
    trail.record("agent-1", "restart")
    assert len(events) == 1  # no new event after removal
    print("  test_callbacks PASSED")


def test_stats():
    trail = AgentAuditTrail()
    trail.record("agent-1", "deploy")
    trail.record("agent-1", "restart")
    trail.get_entries("agent-1")
    stats = trail.get_stats()
    assert stats["total_recorded"] == 2
    assert stats["current_entries"] == 2
    assert stats["total_queries"] >= 1
    assert "max_entries" in stats
    print("  test_stats PASSED")


def test_reset():
    trail = AgentAuditTrail()
    trail.record("agent-1", "deploy")
    trail.record("agent-2", "restart")
    trail.reset()
    assert trail.get_entry_count() == 0
    assert trail.list_agents() == []
    stats = trail.get_stats()
    assert stats["total_recorded"] == 0
    assert stats["current_entries"] == 0
    print("  test_reset PASSED")


if __name__ == "__main__":
    test_record()
    test_get_entries()
    test_get_entries_filtered()
    test_get_latest_entry()
    test_get_entry_count()
    test_clear_entries()
    test_list_agents()
    test_search()
    test_callbacks()
    test_stats()
    test_reset()
    print("=== ALL 11 TESTS PASSED ===")
