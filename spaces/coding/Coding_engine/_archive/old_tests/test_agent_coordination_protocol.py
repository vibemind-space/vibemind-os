"""Test agent coordination protocol."""
import sys
import time
sys.path.insert(0, ".")

from src.services.agent_coordination_protocol import AgentCoordinationProtocol


def test_acquire_release_lock():
    """Acquire and release locks."""
    p = AgentCoordinationProtocol()
    assert p.acquire_lock("resource", "Agent-A") is True
    assert p.acquire_lock("resource", "Agent-B") is False  # Already held

    assert p.is_locked("resource") is True

    lock = p.get_lock("resource")
    assert lock is not None
    assert lock["holder"] == "Agent-A"

    # Only holder can release
    assert p.release_lock("resource", "Agent-B") is False
    assert p.release_lock("resource", "Agent-A") is True
    assert p.is_locked("resource") is False
    print("OK: acquire release lock")


def test_lock_timeout():
    """Lock expires after timeout."""
    p = AgentCoordinationProtocol()
    p.acquire_lock("res", "A", timeout_seconds=0.02)

    time.sleep(0.03)
    assert p.is_locked("res") is False

    # Can re-acquire after timeout
    assert p.acquire_lock("res", "B") is True
    print("OK: lock timeout")


def test_force_release_lock():
    """Force release regardless of holder."""
    p = AgentCoordinationProtocol()
    p.acquire_lock("res", "A")

    assert p.force_release_lock("res") is True
    assert p.force_release_lock("res") is False
    assert p.is_locked("res") is False
    print("OK: force release lock")


def test_list_locks():
    """List active locks."""
    p = AgentCoordinationProtocol()
    p.acquire_lock("a", "Agent-A")
    p.acquire_lock("b", "Agent-B")
    p.acquire_lock("c", "Agent-A")

    all_locks = p.list_locks()
    assert len(all_locks) == 3

    agent_a_locks = p.list_locks(holder="Agent-A")
    assert len(agent_a_locks) == 2
    print("OK: list locks")


def test_create_barrier():
    """Create barriers."""
    p = AgentCoordinationProtocol()
    assert p.create_barrier("sync", required=3) is True
    assert p.create_barrier("sync", required=3) is False  # Duplicate
    assert p.create_barrier("bad", required=0) is False

    barrier = p.get_barrier("sync")
    assert barrier is not None
    assert barrier["required"] == 3
    assert barrier["released"] is False
    print("OK: create barrier")


def test_barrier_sync():
    """Agents synchronize at barrier."""
    p = AgentCoordinationProtocol()
    p.create_barrier("sync", required=3)

    r1 = p.arrive_at_barrier("sync", "A")
    assert r1["arrived"] is True
    assert r1["released"] is False
    assert r1["waiting_count"] == 2

    r2 = p.arrive_at_barrier("sync", "B")
    assert r2["released"] is False

    r3 = p.arrive_at_barrier("sync", "C")
    assert r3["released"] is True
    assert len(r3["agents"]) == 3
    print("OK: barrier sync")


def test_barrier_already_released():
    """Arriving at released barrier succeeds."""
    p = AgentCoordinationProtocol()
    p.create_barrier("sync", required=1)
    p.arrive_at_barrier("sync", "A")

    r = p.arrive_at_barrier("sync", "B")
    assert r["arrived"] is True
    assert r["was_already_released"] is True
    print("OK: barrier already released")


def test_barrier_not_found():
    """Arrive at nonexistent barrier."""
    p = AgentCoordinationProtocol()
    r = p.arrive_at_barrier("fake", "A")
    assert r["arrived"] is False
    assert r["reason"] == "barrier_not_found"
    print("OK: barrier not found")


def test_remove_barrier():
    """Remove a barrier."""
    p = AgentCoordinationProtocol()
    p.create_barrier("sync", required=2)
    assert p.remove_barrier("sync") is True
    assert p.remove_barrier("sync") is False
    print("OK: remove barrier")


def test_list_barriers():
    """List barriers with filter."""
    p = AgentCoordinationProtocol()
    p.create_barrier("a", required=2)
    p.create_barrier("b", required=1)
    p.arrive_at_barrier("b", "X")  # Releases b

    all_b = p.list_barriers()
    assert len(all_b) == 2

    pending = p.list_barriers(released=False)
    assert len(pending) == 1
    assert pending[0]["name"] == "a"
    print("OK: list barriers")


def test_create_session():
    """Create a coordination session."""
    p = AgentCoordinationProtocol()
    sid = p.create_session("deploy", "Leader")
    assert sid.startswith("cs-")

    session = p.get_session(sid)
    assert session is not None
    assert session["leader"] == "Leader"
    assert session["member_count"] == 1
    assert session["status"] == "active"
    print("OK: create session")


def test_join_leave_session():
    """Join and leave sessions."""
    p = AgentCoordinationProtocol()
    sid = p.create_session("deploy", "A")

    assert p.join_session(sid, "B") is True
    assert p.join_session(sid, "C") is True
    assert p.get_session(sid)["member_count"] == 3

    assert p.leave_session(sid, "B") is True
    assert p.get_session(sid)["member_count"] == 2

    # Leave nonexistent
    assert p.leave_session(sid, "B") is False
    assert p.join_session("fake", "X") is False
    print("OK: join leave session")


def test_leader_leaves():
    """New leader elected when leader leaves."""
    p = AgentCoordinationProtocol()
    sid = p.create_session("deploy", "C")
    p.join_session(sid, "A")
    p.join_session(sid, "B")

    p.leave_session(sid, "C")  # Leader leaves
    session = p.get_session(sid)
    assert session["leader"] == "A"  # min("A", "B") = "A"
    print("OK: leader leaves")


def test_all_leave_completes():
    """Session completes when all leave."""
    p = AgentCoordinationProtocol()
    sid = p.create_session("deploy", "A")
    p.leave_session(sid, "A")

    assert p.get_session(sid)["status"] == "completed"
    print("OK: all leave completes")


def test_complete_cancel_session():
    """Complete and cancel sessions."""
    p = AgentCoordinationProtocol()
    sid1 = p.create_session("a", "X")
    sid2 = p.create_session("b", "Y")

    assert p.complete_session(sid1) is True
    assert p.complete_session(sid1) is False  # Already completed
    assert p.get_session(sid1)["status"] == "completed"

    assert p.cancel_session(sid2) is True
    assert p.cancel_session(sid2) is False
    assert p.get_session(sid2)["status"] == "cancelled"
    print("OK: complete cancel session")


def test_list_sessions():
    """List sessions with filter."""
    p = AgentCoordinationProtocol()
    s1 = p.create_session("a", "X")
    s2 = p.create_session("b", "Y")
    p.complete_session(s1)

    all_s = p.list_sessions()
    assert len(all_s) == 2

    active = p.list_sessions(status="active")
    assert len(active) == 1
    print("OK: list sessions")


def test_elect_leader():
    """Elect a new leader."""
    p = AgentCoordinationProtocol()
    sid = p.create_session("deploy", "C")
    p.join_session(sid, "A")
    p.join_session(sid, "B")

    leader = p.elect_leader(sid)
    assert leader == "A"  # min of {A, B, C}
    assert p.is_leader(sid, "A") is True
    assert p.is_leader(sid, "B") is False

    assert p.elect_leader("fake") is None
    print("OK: elect leader")


def test_get_leader():
    """Get current leader."""
    p = AgentCoordinationProtocol()
    sid = p.create_session("deploy", "Leader")

    assert p.get_leader(sid) == "Leader"
    assert p.get_leader("fake") is None
    print("OK: get leader")


def test_stats():
    """Stats are accurate."""
    p = AgentCoordinationProtocol()
    p.acquire_lock("a", "A")
    p.release_lock("a", "A")
    p.create_barrier("b", required=1)
    p.create_session("s", "X")

    stats = p.get_stats()
    assert stats["total_locks_acquired"] == 1
    assert stats["total_locks_released"] == 1
    assert stats["total_barriers_created"] == 1
    assert stats["total_sessions_created"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    p = AgentCoordinationProtocol()
    p.acquire_lock("a", "A")
    p.create_barrier("b", required=1)
    p.create_session("s", "X")

    p.reset()
    assert p.list_locks() == []
    assert p.list_barriers() == []
    assert p.list_sessions() == []
    stats = p.get_stats()
    assert stats["total_active_locks"] == 0
    print("OK: reset")


def main():
    print("=== Agent Coordination Protocol Tests ===\n")
    test_acquire_release_lock()
    test_lock_timeout()
    test_force_release_lock()
    test_list_locks()
    test_create_barrier()
    test_barrier_sync()
    test_barrier_already_released()
    test_barrier_not_found()
    test_remove_barrier()
    test_list_barriers()
    test_create_session()
    test_join_leave_session()
    test_leader_leaves()
    test_all_leave_completes()
    test_complete_cancel_session()
    test_list_sessions()
    test_elect_leader()
    test_get_leader()
    test_stats()
    test_reset()
    print("\n=== ALL 20 TESTS PASSED ===")


if __name__ == "__main__":
    main()
