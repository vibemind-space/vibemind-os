"""Test resource pool manager."""
import sys
import time
sys.path.insert(0, ".")

from src.services.resource_pool import (
    ResourcePoolManager,
    LeaseStatus,
)


def test_create_pool():
    """Pool creation with capacity."""
    mgr = ResourcePoolManager()
    pool = mgr.create_pool("api_slots", capacity=5, description="API rate limit slots")

    assert pool.name == "api_slots"
    assert pool.capacity == 5
    assert pool.available == 5
    assert pool.active_count == 0
    print("OK: create pool")


def test_acquire_release():
    """Basic acquire and release flow."""
    mgr = ResourcePoolManager()
    mgr.create_pool("slots", capacity=3)

    lease = mgr.acquire("slots", holder="agent1")
    assert lease is not None
    assert lease.pool_name == "slots"
    assert lease.holder == "agent1"
    assert lease.is_active

    pool = mgr.get_pool("slots")
    assert pool.available == 2
    assert pool.active_count == 1

    released = mgr.release(lease.lease_id)
    assert released is True
    assert pool.available == 3
    print("OK: acquire release")


def test_capacity_enforcement():
    """Pool denies acquisition when full."""
    mgr = ResourcePoolManager()
    mgr.create_pool("limited", capacity=2)

    l1 = mgr.acquire("limited", holder="a1")
    l2 = mgr.acquire("limited", holder="a2")
    assert l1 is not None
    assert l2 is not None

    l3 = mgr.acquire("limited", holder="a3")
    assert l3 is None  # Pool full

    pool = mgr.get_pool("limited")
    assert pool.total_denials == 1

    # Release one, then acquire succeeds
    mgr.release(l1.lease_id)
    l3 = mgr.acquire("limited", holder="a3")
    assert l3 is not None
    print("OK: capacity enforcement")


def test_lease_expiry():
    """Expired leases are automatically cleaned up."""
    mgr = ResourcePoolManager()
    mgr.create_pool("temp", capacity=1)

    lease = mgr.acquire("temp", holder="agent1", timeout_seconds=0.1)
    assert lease is not None

    # Wait for expiry
    time.sleep(0.15)

    # Expired lease should be cleaned up on next acquire
    l2 = mgr.acquire("temp", holder="agent2")
    assert l2 is not None  # Should succeed after cleanup

    pool = mgr.get_pool("temp")
    assert pool.total_timeouts == 1
    print("OK: lease expiry")


def test_release_all():
    """Release all resources held by a holder."""
    mgr = ResourcePoolManager()
    mgr.create_pool("p1", capacity=5)
    mgr.create_pool("p2", capacity=5)

    mgr.acquire("p1", holder="greedy")
    mgr.acquire("p1", holder="greedy")
    mgr.acquire("p2", holder="greedy")

    released = mgr.release_all("greedy")
    assert released == 3

    assert mgr.get_pool("p1").available == 5
    assert mgr.get_pool("p2").available == 5
    print("OK: release all")


def test_revoke():
    """Leases can be forcefully revoked."""
    mgr = ResourcePoolManager()
    mgr.create_pool("gpu", capacity=1)

    lease = mgr.acquire("gpu", holder="slow_agent")
    assert lease is not None

    revoked = mgr.revoke(lease.lease_id, reason="priority preemption")
    assert revoked is True
    assert lease.status == LeaseStatus.REVOKED

    pool = mgr.get_pool("gpu")
    assert pool.total_revocations == 1
    print("OK: revoke")


def test_holder_resources():
    """Track all resources held by a holder."""
    mgr = ResourcePoolManager()
    mgr.create_pool("a", capacity=5)
    mgr.create_pool("b", capacity=5)

    mgr.acquire("a", holder="worker1")
    mgr.acquire("b", holder="worker1")
    mgr.acquire("a", holder="worker2")

    resources = mgr.get_holder_resources("worker1")
    assert len(resources) == 2

    resources2 = mgr.get_holder_resources("worker2")
    assert len(resources2) == 1

    resources3 = mgr.get_holder_resources("nobody")
    assert len(resources3) == 0
    print("OK: holder resources")


def test_pool_leases():
    """Get active leases in a pool."""
    mgr = ResourcePoolManager()
    mgr.create_pool("pool1", capacity=5)

    mgr.acquire("pool1", holder="a1")
    mgr.acquire("pool1", holder="a2")

    leases = mgr.get_pool_leases("pool1")
    assert len(leases) == 2

    holders = mgr.get_pool_holders("pool1")
    assert "a1" in holders
    assert "a2" in holders
    print("OK: pool leases")


def test_resize_pool():
    """Pool capacity can be resized."""
    mgr = ResourcePoolManager()
    mgr.create_pool("elastic", capacity=3)

    assert mgr.get_pool("elastic").capacity == 3

    result = mgr.resize_pool("elastic", 10)
    assert result is True
    assert mgr.get_pool("elastic").capacity == 10

    result2 = mgr.resize_pool("nonexistent", 5)
    assert result2 is False
    print("OK: resize pool")


def test_wait_queue():
    """Waiters are served when resources free up."""
    mgr = ResourcePoolManager()
    mgr.create_pool("scarce", capacity=1)

    l1 = mgr.acquire("scarce", holder="first")
    assert l1 is not None

    # Can't acquire, add to wait queue
    l2 = mgr.acquire("scarce", holder="second")
    assert l2 is None

    added = mgr.wait_for("scarce", holder="second", priority=5)
    assert added is True

    # No duplicate waiters
    added2 = mgr.wait_for("scarce", holder="second")
    assert added2 is False

    # Release first -> second should be auto-served
    mgr.release(l1.lease_id)

    pool = mgr.get_pool("scarce")
    assert pool.active_count == 1  # second now has the resource
    assert len(pool._waiters) == 0
    print("OK: wait queue")


def test_priority_waiters():
    """Higher priority waiters are served first."""
    mgr = ResourcePoolManager()
    mgr.create_pool("contested", capacity=1)

    l1 = mgr.acquire("contested", holder="current")

    mgr.wait_for("contested", holder="low_prio", priority=9)
    mgr.wait_for("contested", holder="high_prio", priority=1)

    # Release -> high_prio should be served first
    mgr.release(l1.lease_id)

    pool = mgr.get_pool("contested")
    holders = mgr.get_pool_holders("contested")
    assert "high_prio" in holders
    assert len(pool._waiters) == 1  # low_prio still waiting
    print("OK: priority waiters")


def test_utilization():
    """Pool utilization is calculated correctly."""
    mgr = ResourcePoolManager()
    mgr.create_pool("compute", capacity=4)

    assert mgr.get_pool("compute").utilization == 0.0

    mgr.acquire("compute", holder="a1")
    mgr.acquire("compute", holder="a2")
    assert abs(mgr.get_pool("compute").utilization - 0.5) < 0.01

    mgr.acquire("compute", holder="a3")
    mgr.acquire("compute", holder="a4")
    assert abs(mgr.get_pool("compute").utilization - 1.0) < 0.01
    print("OK: utilization")


def test_stats():
    """Pool manager stats are accurate."""
    mgr = ResourcePoolManager()
    mgr.create_pool("p1", capacity=3)
    mgr.create_pool("p2", capacity=2)

    mgr.acquire("p1", holder="a1")
    mgr.acquire("p2", holder="a2")

    stats = mgr.get_stats()
    assert stats["total_pools"] == 2
    assert stats["total_capacity"] == 5
    assert stats["total_active_leases"] == 2
    assert stats["overall_utilization"] == 40.0
    assert "p1" in stats["pools"]
    assert "p2" in stats["pools"]
    print("OK: stats")


def test_pool_not_found():
    """Graceful handling of nonexistent pools."""
    mgr = ResourcePoolManager()

    lease = mgr.acquire("nonexistent", holder="a1")
    assert lease is None

    leases = mgr.get_pool_leases("nonexistent")
    assert leases == []

    stats = mgr.get_pool_stats("nonexistent")
    assert stats is None
    print("OK: pool not found")


def test_lease_metadata():
    """Leases can carry metadata."""
    mgr = ResourcePoolManager()
    mgr.create_pool("resources", capacity=5)

    lease = mgr.acquire(
        "resources", holder="agent1",
        metadata={"task_id": "build-123", "resource_type": "workspace"},
    )

    info = mgr.get_lease(lease.lease_id)
    assert info["metadata"]["task_id"] == "build-123"
    assert info["metadata"]["resource_type"] == "workspace"
    print("OK: lease metadata")


def test_cleanup_all_expired():
    """Cleanup expired across all pools."""
    mgr = ResourcePoolManager()
    mgr.create_pool("fast", capacity=2)
    mgr.create_pool("slow", capacity=2)

    mgr.acquire("fast", holder="a1", timeout_seconds=0.05)
    mgr.acquire("slow", holder="a2", timeout_seconds=0.05)

    time.sleep(0.1)

    cleaned = mgr.cleanup_all_expired()
    assert cleaned == 2
    print("OK: cleanup all expired")


def test_reset():
    """Reset clears everything."""
    mgr = ResourcePoolManager()
    mgr.create_pool("p1", capacity=5)
    mgr.acquire("p1", holder="a1")

    mgr.reset()
    assert mgr.get_pool("p1") is None
    assert mgr.get_stats()["total_pools"] == 0
    print("OK: reset")


def main():
    print("=== Resource Pool Manager Tests ===\n")
    test_create_pool()
    test_acquire_release()
    test_capacity_enforcement()
    test_lease_expiry()
    test_release_all()
    test_revoke()
    test_holder_resources()
    test_pool_leases()
    test_resize_pool()
    test_wait_queue()
    test_priority_waiters()
    test_utilization()
    test_stats()
    test_pool_not_found()
    test_lease_metadata()
    test_cleanup_all_expired()
    test_reset()
    print("\n=== ALL 17 TESTS PASSED ===")


if __name__ == "__main__":
    main()
