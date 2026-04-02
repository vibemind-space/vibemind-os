"""Test agent lease manager."""
import sys
import time
sys.path.insert(0, ".")

from src.services.agent_lease_manager import AgentLeaseManager


def test_acquire():
    """Acquire and get lease."""
    lm = AgentLeaseManager()
    lid = lm.acquire("db_lock", "worker1", tags=["critical"])
    assert lid.startswith("lse-")

    lease = lm.get_lease(lid)
    assert lease is not None
    assert lease["resource"] == "db_lock"
    assert lease["holder"] == "worker1"
    assert lease["remaining"] > 0
    print("OK: acquire")


def test_invalid_acquire():
    """Invalid acquire rejected."""
    lm = AgentLeaseManager()
    assert lm.acquire("", "holder") == ""
    assert lm.acquire("res", "") == ""
    print("OK: invalid acquire")


def test_resource_locked():
    """Resource locked by active lease."""
    lm = AgentLeaseManager()
    lm.acquire("res1", "holder1", duration=60.0)
    assert lm.acquire("res1", "holder2") == ""
    print("OK: resource locked")


def test_release():
    """Release lease."""
    lm = AgentLeaseManager()
    lid = lm.acquire("res1", "holder1")

    assert lm.release(lid) is True
    assert lm.release(lid) is False  # already released
    assert lm.is_locked("res1") is False
    print("OK: release")


def test_renew():
    """Renew lease."""
    lm = AgentLeaseManager()
    lid = lm.acquire("res1", "holder1", duration=60.0)

    assert lm.renew(lid) is True
    lease = lm.get_lease(lid)
    assert lease["renewed_count"] == 1

    assert lm.renew("nonexistent") is False
    print("OK: renew")


def test_max_renewals():
    """Max renewals enforced."""
    lm = AgentLeaseManager(max_renewals=2)
    lid = lm.acquire("res1", "holder1", duration=60.0)
    lm.renew(lid)
    lm.renew(lid)
    assert lm.renew(lid) is False
    print("OK: max renewals")


def test_is_locked():
    """Check resource lock status."""
    lm = AgentLeaseManager()
    assert lm.is_locked("res1") is False

    lid = lm.acquire("res1", "holder1", duration=60.0)
    assert lm.is_locked("res1") is True

    lm.release(lid)
    assert lm.is_locked("res1") is False
    print("OK: is locked")


def test_expiry():
    """Expired lease frees resource."""
    lm = AgentLeaseManager()
    lm.acquire("res1", "holder1", duration=0.001)
    time.sleep(0.01)

    assert lm.is_locked("res1") is False
    # Can acquire again
    lid2 = lm.acquire("res1", "holder2")
    assert lid2 != ""
    print("OK: expiry")


def test_renew_expired():
    """Cannot renew expired lease."""
    lm = AgentLeaseManager()
    lid = lm.acquire("res1", "holder1", duration=0.001)
    time.sleep(0.01)
    assert lm.renew(lid) is False
    print("OK: renew expired")


def test_get_resource_lease():
    """Get lease for resource."""
    lm = AgentLeaseManager()
    lm.acquire("res1", "holder1", duration=60.0)

    lease = lm.get_resource_lease("res1")
    assert lease is not None
    assert lease["holder"] == "holder1"

    assert lm.get_resource_lease("nonexistent") is None
    print("OK: get resource lease")


def test_holder_leases():
    """Get leases by holder."""
    lm = AgentLeaseManager()
    lm.acquire("res1", "holder1", duration=60.0)
    lm.acquire("res2", "holder1", duration=60.0)
    lm.acquire("res3", "holder2", duration=60.0)

    leases = lm.get_holder_leases("holder1")
    assert len(leases) == 2
    print("OK: holder leases")


def test_list_leases():
    """List leases with filters."""
    lm = AgentLeaseManager()
    lm.acquire("res1", "holder1", duration=60.0, tags=["db"])
    lm.acquire("res2", "holder2", duration=60.0)

    all_l = lm.list_leases()
    assert len(all_l) == 2

    by_holder = lm.list_leases(holder="holder1")
    assert len(by_holder) == 1

    by_tag = lm.list_leases(tag="db")
    assert len(by_tag) == 1
    print("OK: list leases")


def test_cleanup_expired():
    """Cleanup expired leases."""
    lm = AgentLeaseManager()
    lm.acquire("res1", "h1", duration=0.001)
    lm.acquire("res2", "h2", duration=9999)

    time.sleep(0.01)
    count = lm.cleanup_expired()
    assert count == 1
    print("OK: cleanup expired")


def test_max_leases():
    """Max leases enforced."""
    lm = AgentLeaseManager(max_leases=2)
    lm.acquire("res1", "h1")
    lm.acquire("res2", "h2")
    assert lm.acquire("res3", "h3") == ""
    print("OK: max leases")


def test_history():
    """History tracking."""
    lm = AgentLeaseManager()
    lid = lm.acquire("res1", "h1")
    lm.renew(lid)
    lm.release(lid)

    hist = lm.get_history()
    assert len(hist) == 3  # acquired, renewed, released

    by_action = lm.get_history(action="renewed")
    assert len(by_action) == 1

    by_resource = lm.get_history(resource="res1")
    assert len(by_resource) == 3

    limited = lm.get_history(limit=1)
    assert len(limited) == 1
    print("OK: history")


def test_callback():
    """Callback fires on events."""
    lm = AgentLeaseManager()
    fired = []
    lm.on_change("mon", lambda a, d: fired.append(a))

    lid = lm.acquire("res1", "h1")
    assert "lease_acquired" in fired

    lm.release(lid)
    assert "lease_released" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    lm = AgentLeaseManager()
    assert lm.on_change("mon", lambda a, d: None) is True
    assert lm.on_change("mon", lambda a, d: None) is False
    assert lm.remove_callback("mon") is True
    assert lm.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    lm = AgentLeaseManager()
    lid = lm.acquire("res1", "h1", duration=60.0)
    lm.acquire("res2", "h2", duration=60.0)
    lm.release(lid)

    stats = lm.get_stats()
    assert stats["total_acquired"] == 2
    assert stats["total_released"] == 1
    assert stats["current_leases"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    lm = AgentLeaseManager()
    lm.acquire("res1", "h1")

    lm.reset()
    assert lm.list_leases() == []
    stats = lm.get_stats()
    assert stats["current_leases"] == 0
    assert stats["total_acquired"] == 0
    print("OK: reset")


def main():
    print("=== Agent Lease Manager Tests ===\n")
    test_acquire()
    test_invalid_acquire()
    test_resource_locked()
    test_release()
    test_renew()
    test_max_renewals()
    test_is_locked()
    test_expiry()
    test_renew_expired()
    test_get_resource_lease()
    test_holder_leases()
    test_list_leases()
    test_cleanup_expired()
    test_max_leases()
    test_history()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 19 TESTS PASSED ===")


if __name__ == "__main__":
    main()
