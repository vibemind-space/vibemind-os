"""Test agent audit store -- unit tests."""
import sys, time
sys.path.insert(0, ".")

from src.services.agent_audit_store import AgentAuditStore


def test_record():
    a = AgentAuditStore()
    eid = a.record("agent-1", "deploy", resource="prod-server", details={"version": "2.0"})
    assert len(eid) > 0
    assert eid.startswith("aas-")
    e = a.get_entry(eid)
    assert e is not None
    assert e["agent_id"] == "agent-1"
    assert e["action"] == "deploy"
    print("OK: record")


def test_get_agent_audit():
    a = AgentAuditStore()
    a.record("agent-1", "login")
    a.record("agent-1", "deploy")
    a.record("agent-2", "login")
    trail = a.get_agent_audit("agent-1")
    assert len(trail) == 2
    print("OK: get agent audit")


def test_search_audit():
    a = AgentAuditStore()
    a.record("agent-1", "deploy", resource="prod")
    a.record("agent-1", "restart", resource="staging")
    a.record("agent-2", "deploy", resource="prod")
    by_action = a.search_audit(action="deploy")
    assert len(by_action) == 2
    by_agent = a.search_audit(agent_id="agent-1")
    assert len(by_agent) == 2
    by_resource = a.search_audit(resource="prod")
    assert len(by_resource) == 2
    print("OK: search audit")


def test_get_audit_count():
    a = AgentAuditStore()
    a.record("agent-1", "login")
    a.record("agent-1", "deploy")
    a.record("agent-2", "login")
    assert a.get_audit_count() == 3
    assert a.get_audit_count(agent_id="agent-1") == 2
    print("OK: get audit count")


def test_purge():
    a = AgentAuditStore()
    a.record("agent-1", "old_action")
    time.sleep(0.01)
    count = a.purge(before_timestamp=time.time() + 1)
    assert count >= 1
    print("OK: purge")


def test_list_agents():
    a = AgentAuditStore()
    a.record("agent-1", "login")
    a.record("agent-2", "login")
    agents = a.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_actions_summary():
    a = AgentAuditStore()
    a.record("agent-1", "deploy")
    a.record("agent-1", "deploy")
    a.record("agent-1", "restart")
    summary = a.get_actions_summary("agent-1")
    assert summary.get("deploy", 0) == 2
    assert summary.get("restart", 0) == 1
    print("OK: actions summary")


def test_callbacks():
    a = AgentAuditStore()
    fired = []
    a.on_change("mon", lambda act, d: fired.append(act))
    a.record("agent-1", "login")
    assert len(fired) >= 1
    assert a.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    a = AgentAuditStore()
    a.record("agent-1", "login")
    stats = a.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    a = AgentAuditStore()
    a.record("agent-1", "login")
    a.reset()
    assert a.get_audit_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Audit Store Tests ===\n")
    test_record()
    test_get_agent_audit()
    test_search_audit()
    test_get_audit_count()
    test_purge()
    test_list_agents()
    test_actions_summary()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")


if __name__ == "__main__":
    main()
