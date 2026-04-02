"""Test pipeline resource allocator."""
import sys
import time
sys.path.insert(0, ".")

from src.services.pipeline_resource_allocator import PipelineResourceAllocator


def test_create_pool():
    """Create and remove pools."""
    a = PipelineResourceAllocator()
    assert a.create_pool("cpu", 100.0, unit="cores") is True
    assert a.create_pool("cpu", 50.0) is False  # Duplicate
    assert a.create_pool("bad", 0) is False  # Zero capacity

    pool = a.get_pool("cpu")
    assert pool is not None
    assert pool["capacity"] == 100.0
    assert pool["available"] == 100.0
    assert pool["unit"] == "cores"

    assert a.remove_pool("cpu") is True
    assert a.remove_pool("cpu") is False
    print("OK: create pool")


def test_allocate_release():
    """Allocate and release resources."""
    a = PipelineResourceAllocator()
    a.create_pool("mem", 1000.0, unit="MB")

    aid = a.allocate("mem", "agent-1", 400.0)
    assert aid.startswith("alloc-")
    assert a.get_pool("mem")["allocated"] == 400.0
    assert a.get_pool("mem")["available"] == 600.0

    assert a.release(aid) is True
    assert a.release(aid) is False  # Already released
    assert a.get_pool("mem")["available"] == 1000.0
    print("OK: allocate release")


def test_over_allocate():
    """Can't exceed capacity."""
    a = PipelineResourceAllocator()
    a.create_pool("gpu", 4.0)

    a1 = a.allocate("gpu", "A", 3.0)
    assert a1 != ""

    a2 = a.allocate("gpu", "B", 2.0)
    assert a2 == ""  # Only 1.0 left

    a3 = a.allocate("gpu", "B", 1.0)
    assert a3 != ""
    print("OK: over allocate")


def test_allocate_nonexistent():
    """Allocate from nonexistent pool."""
    a = PipelineResourceAllocator()
    assert a.allocate("fake", "A", 1.0) == ""
    print("OK: allocate nonexistent")


def test_get_allocation():
    """Get allocation info."""
    a = PipelineResourceAllocator()
    a.create_pool("cpu", 100.0)

    aid = a.allocate("cpu", "worker-1", 25.0)
    info = a.get_allocation(aid)
    assert info is not None
    assert info["holder"] == "worker-1"
    assert info["amount"] == 25.0
    assert info["pool_name"] == "cpu"

    assert a.get_allocation("fake") is None
    print("OK: get allocation")


def test_holder_allocations():
    """Get all allocations for a holder."""
    a = PipelineResourceAllocator()
    a.create_pool("cpu", 100.0)
    a.create_pool("mem", 1000.0)

    a.allocate("cpu", "agent-1", 10.0)
    a.allocate("mem", "agent-1", 200.0)
    a.allocate("cpu", "agent-2", 5.0)

    allocs = a.get_holder_allocations("agent-1")
    assert len(allocs) == 2
    print("OK: holder allocations")


def test_release_holder():
    """Release all allocations for a holder."""
    a = PipelineResourceAllocator()
    a.create_pool("cpu", 100.0)

    a.allocate("cpu", "agent-1", 10.0)
    a.allocate("cpu", "agent-1", 20.0)
    a.allocate("cpu", "agent-2", 5.0)

    count = a.release_holder("agent-1")
    assert count == 2
    assert a.get_pool("cpu")["allocated"] == 5.0
    print("OK: release holder")


def test_resize_pool():
    """Resize a pool."""
    a = PipelineResourceAllocator()
    a.create_pool("cpu", 100.0)

    a.allocate("cpu", "A", 60.0)
    assert a.resize_pool("cpu", 80.0) is True
    assert a.resize_pool("cpu", 50.0) is False  # Below allocated
    assert a.resize_pool("fake", 10.0) is False
    print("OK: resize pool")


def test_cant_remove_with_allocations():
    """Can't remove pool with active allocations."""
    a = PipelineResourceAllocator()
    a.create_pool("cpu", 100.0)

    aid = a.allocate("cpu", "A", 10.0)
    assert a.remove_pool("cpu") is False

    a.release(aid)
    assert a.remove_pool("cpu") is True
    print("OK: cant remove with allocations")


def test_reserve():
    """Reserve resources."""
    a = PipelineResourceAllocator()
    a.create_pool("tokens", 10000.0)

    rid = a.reserve("tokens", "agent-1", 3000.0, timeout_seconds=5.0)
    assert rid.startswith("res-")

    pool = a.get_pool("tokens")
    assert pool["reserved"] == 3000.0
    assert pool["available"] == 7000.0

    res = a.get_reservation(rid)
    assert res is not None
    assert res["holder"] == "agent-1"
    assert res["expired"] is False
    print("OK: reserve")


def test_claim_reservation():
    """Claim a reservation converts to allocation."""
    a = PipelineResourceAllocator()
    a.create_pool("cpu", 100.0)

    rid = a.reserve("cpu", "A", 30.0, timeout_seconds=5.0)
    aid = a.claim_reservation(rid)
    assert aid.startswith("alloc-")

    pool = a.get_pool("cpu")
    assert pool["reserved"] == 0.0
    assert pool["allocated"] == 30.0

    # Reservation gone
    assert a.get_reservation(rid) is None
    print("OK: claim reservation")


def test_cancel_reservation():
    """Cancel a reservation."""
    a = PipelineResourceAllocator()
    a.create_pool("mem", 1000.0)

    rid = a.reserve("mem", "A", 500.0, timeout_seconds=5.0)
    assert a.cancel_reservation(rid) is True
    assert a.cancel_reservation(rid) is False

    assert a.get_pool("mem")["available"] == 1000.0
    print("OK: cancel reservation")


def test_reservation_expiry():
    """Expired reservations are cleaned up."""
    a = PipelineResourceAllocator()
    a.create_pool("cpu", 100.0)

    rid = a.reserve("cpu", "A", 50.0, timeout_seconds=0.02)
    assert a.get_pool("cpu")["available"] == 50.0

    time.sleep(0.03)
    # Accessing pool triggers cleanup
    assert a.get_pool("cpu")["available"] == 100.0

    # Can't claim expired
    assert a.claim_reservation(rid) == ""
    print("OK: reservation expiry")


def test_can_allocate():
    """Check allocation feasibility."""
    a = PipelineResourceAllocator()
    a.create_pool("gpu", 4.0)

    assert a.can_allocate("gpu", 3.0) is True
    assert a.can_allocate("gpu", 5.0) is False
    assert a.can_allocate("fake", 1.0) is False

    a.allocate("gpu", "A", 3.0)
    assert a.can_allocate("gpu", 2.0) is False
    assert a.can_allocate("gpu", 1.0) is True
    print("OK: can allocate")


def test_get_available():
    """Get available resources."""
    a = PipelineResourceAllocator()
    a.create_pool("cpu", 100.0)

    assert a.get_available("cpu") == 100.0
    a.allocate("cpu", "A", 40.0)
    assert a.get_available("cpu") == 60.0
    assert a.get_available("fake") == 0.0
    print("OK: get available")


def test_utilization():
    """Get utilization percentage."""
    a = PipelineResourceAllocator()
    a.create_pool("cpu", 100.0)

    assert a.get_utilization("cpu") == 0.0
    a.allocate("cpu", "A", 75.0)
    assert a.get_utilization("cpu") == 75.0
    assert a.get_utilization("fake") == 0.0
    print("OK: utilization")


def test_list_pools():
    """List pools with filter."""
    a = PipelineResourceAllocator()
    a.create_pool("cpu", 100.0)
    a.create_pool("mem", 1000.0)
    a.allocate("cpu", "A", 80.0)

    all_pools = a.list_pools()
    assert len(all_pools) == 2

    high_util = a.list_pools(min_utilization=50.0)
    assert len(high_util) == 1
    assert high_util[0]["name"] == "cpu"
    print("OK: list pools")


def test_list_allocations():
    """List allocations with filters."""
    a = PipelineResourceAllocator()
    a.create_pool("cpu", 100.0)
    a.create_pool("mem", 1000.0)

    a.allocate("cpu", "A", 10.0)
    a.allocate("cpu", "B", 20.0)
    a.allocate("mem", "A", 100.0)

    all_allocs = a.list_allocations()
    assert len(all_allocs) == 3

    cpu_allocs = a.list_allocations(pool_name="cpu")
    assert len(cpu_allocs) == 2

    a_allocs = a.list_allocations(holder="A")
    assert len(a_allocs) == 2
    print("OK: list allocations")


def test_callbacks():
    """Allocation change callbacks."""
    a = PipelineResourceAllocator()
    a.create_pool("cpu", 100.0)

    fired = []
    assert a.on_change("mon", lambda act, p, h, amt: fired.append((act, p, h, amt))) is True
    assert a.on_change("mon", lambda act, p, h, amt: None) is False

    aid = a.allocate("cpu", "A", 10.0)
    a.release(aid)

    assert len(fired) == 2
    assert fired[0] == ("allocate", "cpu", "A", 10.0)
    assert fired[1] == ("release", "cpu", "A", 10.0)

    assert a.remove_callback("mon") is True
    assert a.remove_callback("mon") is False
    print("OK: callbacks")


def test_summary():
    """Pool summary."""
    a = PipelineResourceAllocator()
    a.create_pool("cpu", 100.0)
    a.create_pool("mem", 1000.0)
    a.allocate("cpu", "A", 50.0)

    summary = a.get_summary()
    assert "cpu" in summary
    assert summary["cpu"]["utilization"] == 50.0
    assert summary["mem"]["utilization"] == 0.0
    print("OK: summary")


def test_stats():
    """Stats are accurate."""
    a = PipelineResourceAllocator()
    a.create_pool("cpu", 100.0)
    aid = a.allocate("cpu", "A", 10.0)
    a.release(aid)
    a.allocate("fake", "B", 5.0)  # Denied

    stats = a.get_stats()
    assert stats["total_pools"] == 1
    assert stats["total_allocations"] == 1
    assert stats["total_releases"] == 1
    assert stats["total_denied"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    a = PipelineResourceAllocator()
    a.create_pool("cpu", 100.0)
    a.allocate("cpu", "A", 10.0)

    a.reset()
    assert a.list_pools() == []
    stats = a.get_stats()
    assert stats["total_pools"] == 0
    assert stats["total_active_allocations"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Resource Allocator Tests ===\n")
    test_create_pool()
    test_allocate_release()
    test_over_allocate()
    test_allocate_nonexistent()
    test_get_allocation()
    test_holder_allocations()
    test_release_holder()
    test_resize_pool()
    test_cant_remove_with_allocations()
    test_reserve()
    test_claim_reservation()
    test_cancel_reservation()
    test_reservation_expiry()
    test_can_allocate()
    test_get_available()
    test_utilization()
    test_list_pools()
    test_list_allocations()
    test_callbacks()
    test_summary()
    test_stats()
    test_reset()
    print("\n=== ALL 22 TESTS PASSED ===")


if __name__ == "__main__":
    main()
