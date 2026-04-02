"""Test agent state snapshot -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_state_snapshot import AgentStateSnapshot


def test_create_snapshot():
    ss = AgentStateSnapshot()
    sid = ss.create_snapshot("agent-1", {"status": "idle", "memory": 512})
    assert len(sid) > 0
    assert sid.startswith("asn-")
    print("OK: create snapshot")


def test_get_snapshot():
    ss = AgentStateSnapshot()
    sid = ss.create_snapshot("agent-1", {"status": "idle"})
    snap = ss.get_snapshot(sid)
    assert snap is not None
    assert snap["agent_id"] == "agent-1"
    assert snap["state_data"]["status"] == "idle"
    assert ss.get_snapshot("nonexistent") is None
    print("OK: get snapshot")


def test_get_agent_snapshots():
    ss = AgentStateSnapshot()
    ss.create_snapshot("agent-1", {"step": 1})
    ss.create_snapshot("agent-1", {"step": 2})
    ss.create_snapshot("agent-2", {"step": 1})
    snaps = ss.get_agent_snapshots("agent-1")
    assert len(snaps) == 2
    print("OK: get agent snapshots")


def test_get_latest_snapshot():
    ss = AgentStateSnapshot()
    ss.create_snapshot("agent-1", {"v": 1})
    ss.create_snapshot("agent-1", {"v": 2})
    latest = ss.get_latest_snapshot("agent-1")
    assert latest is not None
    assert latest["state_data"]["v"] == 2
    assert ss.get_latest_snapshot("agent-999") is None
    print("OK: get latest snapshot")


def test_compare_snapshots():
    ss = AgentStateSnapshot()
    s1 = ss.create_snapshot("agent-1", {"a": 1, "b": 2})
    s2 = ss.create_snapshot("agent-1", {"a": 1, "b": 3, "c": 4})
    diff = ss.compare_snapshots(s1, s2)
    assert isinstance(diff, dict)
    print("OK: compare snapshots")


def test_restore_snapshot():
    ss = AgentStateSnapshot()
    sid = ss.create_snapshot("agent-1", {"status": "running"})
    result = ss.restore_snapshot(sid)
    assert result is True
    assert ss.restore_snapshot("nonexistent") is False
    print("OK: restore snapshot")


def test_delete_snapshot():
    ss = AgentStateSnapshot()
    sid = ss.create_snapshot("agent-1", {"status": "idle"})
    assert ss.delete_snapshot(sid) is True
    assert ss.delete_snapshot(sid) is False
    print("OK: delete snapshot")


def test_purge():
    ss = AgentStateSnapshot()
    ss.create_snapshot("agent-1", {"v": 1})
    ss.create_snapshot("agent-1", {"v": 2})
    ss.create_snapshot("agent-2", {"v": 1})
    count = ss.purge("agent-1")
    assert count == 2
    assert ss.get_snapshot_count() == 1
    print("OK: purge")


def test_list_agents():
    ss = AgentStateSnapshot()
    ss.create_snapshot("agent-1", {"v": 1})
    ss.create_snapshot("agent-2", {"v": 1})
    agents = ss.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    ss = AgentStateSnapshot()
    fired = []
    ss.on_change("mon", lambda a, d: fired.append(a))
    ss.create_snapshot("agent-1", {"v": 1})
    assert len(fired) >= 1
    assert ss.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    ss = AgentStateSnapshot()
    ss.create_snapshot("agent-1", {"v": 1})
    stats = ss.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    ss = AgentStateSnapshot()
    ss.create_snapshot("agent-1", {"v": 1})
    ss.reset()
    assert ss.get_snapshot_count() == 0
    print("OK: reset")


def main():
    print("=== Agent State Snapshot Tests ===\n")
    test_create_snapshot()
    test_get_snapshot()
    test_get_agent_snapshots()
    test_get_latest_snapshot()
    test_compare_snapshots()
    test_restore_snapshot()
    test_delete_snapshot()
    test_purge()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 12 TESTS PASSED ===")


if __name__ == "__main__":
    main()
