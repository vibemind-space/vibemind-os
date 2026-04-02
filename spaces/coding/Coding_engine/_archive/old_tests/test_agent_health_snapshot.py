"""Test agent health snapshot -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_health_snapshot import AgentHealthSnapshot


def test_take_snapshot():
    hs = AgentHealthSnapshot()
    sid = hs.take_snapshot("agent-1", {"cpu": 45, "memory": 60})
    assert len(sid) > 0
    assert sid.startswith("ahs-")
    print("OK: take snapshot")


def test_get_snapshot():
    hs = AgentHealthSnapshot()
    sid = hs.take_snapshot("agent-1", {"cpu": 45})
    snap = hs.get_snapshot(sid)
    assert snap is not None
    assert snap["health_data"]["cpu"] == 45
    assert hs.get_snapshot("nonexistent") is None
    print("OK: get snapshot")


def test_get_snapshots():
    hs = AgentHealthSnapshot()
    hs.take_snapshot("agent-1", {"cpu": 45})
    hs.take_snapshot("agent-1", {"cpu": 50})
    snaps = hs.get_snapshots("agent-1")
    assert len(snaps) == 2
    print("OK: get snapshots")


def test_get_latest_snapshot():
    hs = AgentHealthSnapshot()
    hs.take_snapshot("agent-1", {"cpu": 45})
    hs.take_snapshot("agent-1", {"cpu": 50})
    latest = hs.get_latest_snapshot("agent-1")
    assert latest is not None
    assert latest["health_data"]["cpu"] == 50
    assert hs.get_latest_snapshot("nonexistent") is None
    print("OK: get latest snapshot")


def test_compare_snapshots():
    hs = AgentHealthSnapshot()
    sid1 = hs.take_snapshot("agent-1", {"cpu": 45, "memory": 60})
    sid2 = hs.take_snapshot("agent-1", {"cpu": 80, "memory": 60})
    diff = hs.compare_snapshots(sid1, sid2)
    assert "changes" in diff
    assert "cpu" in diff["changes"]
    assert diff["changes"]["cpu"]["old"] == 45
    assert diff["changes"]["cpu"]["new"] == 80
    # memory unchanged, should not be in changes
    assert "memory" not in diff["changes"]
    print("OK: compare snapshots")


def test_get_snapshot_count():
    hs = AgentHealthSnapshot()
    hs.take_snapshot("agent-1", {"cpu": 45})
    hs.take_snapshot("agent-2", {"cpu": 60})
    assert hs.get_snapshot_count() == 2
    assert hs.get_snapshot_count("agent-1") == 1
    print("OK: get snapshot count")


def test_list_agents():
    hs = AgentHealthSnapshot()
    hs.take_snapshot("agent-1", {"cpu": 45})
    hs.take_snapshot("agent-2", {"cpu": 60})
    agents = hs.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    hs = AgentHealthSnapshot()
    fired = []
    hs.on_change("mon", lambda a, d: fired.append(a))
    hs.take_snapshot("agent-1", {"cpu": 45})
    assert len(fired) >= 1
    assert hs.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    hs = AgentHealthSnapshot()
    hs.take_snapshot("agent-1", {"cpu": 45})
    stats = hs.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    hs = AgentHealthSnapshot()
    hs.take_snapshot("agent-1", {"cpu": 45})
    hs.reset()
    assert hs.get_snapshot_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Health Snapshot Tests ===\n")
    test_take_snapshot()
    test_get_snapshot()
    test_get_snapshots()
    test_get_latest_snapshot()
    test_compare_snapshots()
    test_get_snapshot_count()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")


if __name__ == "__main__":
    main()
