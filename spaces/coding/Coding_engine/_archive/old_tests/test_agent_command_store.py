"""Test agent command store -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_command_store import AgentCommandStore


def test_send_command():
    cs = AgentCommandStore()
    cid = cs.send_command("agent-1", "restart", payload={"reason": "update"})
    assert len(cid) > 0
    assert cid.startswith("acm-")
    print("OK: send command")


def test_get_command():
    cs = AgentCommandStore()
    cid = cs.send_command("agent-1", "restart")
    cmd = cs.get_command(cid)
    assert cmd is not None
    assert cmd["command_id"] == cid
    assert cmd["agent_id"] == "agent-1"
    assert cmd["command_type"] == "restart"
    assert cmd["status"] == "pending"
    assert cs.get_command("nonexistent") is None
    print("OK: get command")


def test_get_pending_commands():
    cs = AgentCommandStore()
    cs.send_command("agent-1", "low", priority=1)
    cs.send_command("agent-1", "high", priority=10)
    cs.send_command("agent-2", "other")
    pending = cs.get_pending_commands("agent-1")
    assert len(pending) == 2
    assert pending[0]["command_type"] == "high"
    print("OK: get pending commands")


def test_acknowledge():
    cs = AgentCommandStore()
    cid = cs.send_command("agent-1", "restart")
    assert cs.acknowledge(cid) is True
    cmd = cs.get_command(cid)
    assert cmd["status"] == "acknowledged"
    assert cs.acknowledge("nonexistent") is False
    print("OK: acknowledge")


def test_complete_command():
    cs = AgentCommandStore()
    cid = cs.send_command("agent-1", "restart")
    assert cs.complete_command(cid, result={"ok": True}) is True
    cmd = cs.get_command(cid)
    assert cmd["status"] == "completed"
    assert cs.complete_command("nonexistent") is False
    print("OK: complete command")


def test_fail_command():
    cs = AgentCommandStore()
    cid = cs.send_command("agent-1", "restart")
    assert cs.fail_command(cid, error="timeout") is True
    cmd = cs.get_command(cid)
    assert cmd["status"] == "failed"
    assert cs.fail_command("nonexistent") is False
    print("OK: fail command")


def test_cancel_command():
    cs = AgentCommandStore()
    cid = cs.send_command("agent-1", "restart")
    assert cs.cancel_command(cid) is True
    cmd = cs.get_command(cid)
    assert cmd["status"] == "cancelled"
    # Can't cancel completed
    cid2 = cs.send_command("agent-1", "stop")
    cs.complete_command(cid2)
    assert cs.cancel_command(cid2) is False
    print("OK: cancel command")


def test_get_command_history():
    cs = AgentCommandStore()
    cs.send_command("agent-1", "cmd1")
    cs.send_command("agent-1", "cmd2")
    cs.send_command("agent-2", "cmd3")
    history = cs.get_command_history("agent-1")
    assert len(history) == 2
    print("OK: get command history")


def test_get_command_count():
    cs = AgentCommandStore()
    cs.send_command("agent-1", "cmd1")
    cs.send_command("agent-1", "cmd2")
    cs.send_command("agent-2", "cmd3")
    assert cs.get_command_count("agent-1") == 2
    assert cs.get_command_count() == 3
    print("OK: get command count")


def test_list_agents():
    cs = AgentCommandStore()
    cs.send_command("agent-1", "cmd1")
    cs.send_command("agent-2", "cmd2")
    agents = cs.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    cs = AgentCommandStore()
    fired = []
    cs.on_change("mon", lambda a, d: fired.append(a))
    cs.send_command("agent-1", "restart")
    assert len(fired) >= 1
    assert cs.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    cs = AgentCommandStore()
    cs.send_command("agent-1", "restart")
    stats = cs.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    cs = AgentCommandStore()
    cs.send_command("agent-1", "restart")
    cs.reset()
    assert cs.get_command_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Command Store Tests ===\n")
    test_send_command()
    test_get_command()
    test_get_pending_commands()
    test_acknowledge()
    test_complete_command()
    test_fail_command()
    test_cancel_command()
    test_get_command_history()
    test_get_command_count()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 13 TESTS PASSED ===")


if __name__ == "__main__":
    main()
