"""Test resource governor."""
import sys
import time
sys.path.insert(0, ".")

from src.services.resource_governor import ResourceGovernor


def test_register_agent():
    """Register and unregister agents."""
    gov = ResourceGovernor()
    assert gov.register_agent("Builder") is True
    assert gov.register_agent("Builder") is False

    agent = gov.get_agent("Builder")
    assert agent is not None
    assert agent["agent_name"] == "Builder"

    assert gov.unregister_agent("Builder") is True
    assert gov.unregister_agent("Builder") is False
    print("OK: register agent")


def test_set_quota():
    """Set and remove quotas."""
    gov = ResourceGovernor()
    gov.register_agent("Builder")

    assert gov.set_quota("Builder", "cpu", 80.0, 100.0, unit="percent") is True
    assert gov.set_quota("Builder", "bad", 100.0, 50.0) is False  # hard < soft
    assert gov.set_quota("nonexistent", "cpu", 50.0, 100.0) is False

    agent = gov.get_agent("Builder")
    assert "cpu" in agent["quotas"]
    assert agent["quotas"]["cpu"]["soft_limit"] == 80.0

    assert gov.remove_quota("Builder", "cpu") is True
    assert gov.remove_quota("Builder", "cpu") is False
    print("OK: set quota")


def test_record_usage_within_limits():
    """Record usage within limits."""
    gov = ResourceGovernor()
    gov.register_agent("Builder")
    gov.set_quota("Builder", "tasks", 5.0, 10.0, unit="count")

    result = gov.record_usage("Builder", "tasks", 3.0)
    assert result["allowed"] is True
    assert result["reason"] == "within_limits"
    print("OK: record usage within limits")


def test_record_usage_soft_limit():
    """Record usage exceeding soft limit."""
    gov = ResourceGovernor()
    gov.register_agent("Builder")
    gov.set_quota("Builder", "tasks", 5.0, 10.0)

    gov.record_usage("Builder", "tasks", 6.0)
    usage = gov.get_usage("Builder")
    assert len(usage) == 1
    assert usage[0]["over_soft"] is True
    assert usage[0]["over_hard"] is False
    print("OK: record usage soft limit")


def test_record_usage_hard_limit():
    """Record usage exceeding hard limit triggers throttle."""
    gov = ResourceGovernor()
    gov.register_agent("Builder")
    gov.set_quota("Builder", "tasks", 5.0, 10.0)

    result = gov.record_usage("Builder", "tasks", 11.0)
    assert result["allowed"] is False
    assert result["reason"] == "hard_limit_exceeded"

    assert gov.is_throttled("Builder") is True
    print("OK: record usage hard limit")


def test_no_quota():
    """Usage with no quota is unlimited."""
    gov = ResourceGovernor()
    gov.register_agent("Builder")

    result = gov.record_usage("Builder", "memory", 1000.0)
    assert result["allowed"] is True
    assert result["reason"] == "no_quota"
    print("OK: no quota")


def test_unregistered_agent():
    """Usage for unregistered agent."""
    gov = ResourceGovernor()
    result = gov.record_usage("Unknown", "cpu", 50.0)
    assert result["allowed"] is False
    assert result["reason"] == "agent_not_registered"
    print("OK: unregistered agent")


def test_get_usage():
    """Get usage details."""
    gov = ResourceGovernor()
    gov.register_agent("Builder")
    gov.set_quota("Builder", "cpu", 80.0, 100.0, unit="percent")
    gov.set_quota("Builder", "memory", 1024.0, 2048.0, unit="MB")
    gov.record_usage("Builder", "cpu", 50.0)

    usage = gov.get_usage("Builder")
    assert len(usage) == 2

    cpu = [u for u in usage if u["resource_type"] == "cpu"][0]
    assert cpu["current_usage"] == 50.0
    assert cpu["usage_percent"] == 50.0

    # Filter
    cpu_only = gov.get_usage("Builder", resource_type="cpu")
    assert len(cpu_only) == 1
    print("OK: get usage")


def test_reset_usage():
    """Reset usage counters."""
    gov = ResourceGovernor()
    gov.register_agent("Builder")
    gov.set_quota("Builder", "tasks", 5.0, 10.0)
    gov.record_usage("Builder", "tasks", 11.0)

    assert gov.is_throttled("Builder") is True
    assert gov.reset_usage("Builder") is True
    assert gov.is_throttled("Builder") is False

    usage = gov.get_usage("Builder")
    assert usage[0]["current_usage"] == 0.0

    assert gov.reset_usage("nonexistent") is False
    print("OK: reset usage")


def test_reserve():
    """Reserve resources."""
    gov = ResourceGovernor()
    gov.register_agent("Builder")
    gov.set_quota("Builder", "cpu", 80.0, 100.0)

    rid = gov.reserve("Builder", "cpu", 30.0, duration_seconds=60.0)
    assert rid is not None and rid.startswith("rsrv-")

    res = gov.get_reservation(rid)
    assert res["amount"] == 30.0
    assert res["status"] == "active"

    # Can't exceed hard limit
    assert gov.reserve("Builder", "cpu", 80.0) is None

    # Nonexistent
    assert gov.reserve("fake", "cpu", 10.0) is None
    assert gov.reserve("Builder", "memory", 10.0) is None
    print("OK: reserve")


def test_release():
    """Release a reservation."""
    gov = ResourceGovernor()
    gov.register_agent("Builder")
    gov.set_quota("Builder", "cpu", 80.0, 100.0)

    rid = gov.reserve("Builder", "cpu", 30.0)
    assert gov.release(rid) is True
    assert gov.release(rid) is False  # Already released

    res = gov.get_reservation(rid)
    assert res["status"] == "released"
    print("OK: release")


def test_reservation_expiry():
    """Reservations expire."""
    gov = ResourceGovernor()
    gov.register_agent("Builder")
    gov.set_quota("Builder", "cpu", 80.0, 100.0)

    rid = gov.reserve("Builder", "cpu", 30.0, duration_seconds=0.01)
    time.sleep(0.02)

    res = gov.get_reservation(rid)
    assert res["status"] == "expired"

    cleaned = gov.cleanup_expired_reservations()
    assert cleaned >= 0  # Already expired in get_reservation
    print("OK: reservation expiry")


def test_list_reservations():
    """List reservations."""
    gov = ResourceGovernor()
    gov.register_agent("A")
    gov.register_agent("B")
    gov.set_quota("A", "cpu", 80.0, 100.0)
    gov.set_quota("B", "cpu", 80.0, 100.0)

    gov.reserve("A", "cpu", 10.0)
    gov.reserve("B", "cpu", 20.0)

    all_res = gov.list_reservations()
    assert len(all_res) == 2

    a_res = gov.list_reservations(agent_name="A")
    assert len(a_res) == 1
    print("OK: list reservations")


def test_throttle_unthrottle():
    """Manual throttle and unthrottle."""
    gov = ResourceGovernor()
    gov.register_agent("Builder")

    assert gov.throttle("Builder") is True
    assert gov.is_throttled("Builder") is True

    assert gov.unthrottle("Builder") is True
    assert gov.is_throttled("Builder") is False
    assert gov.unthrottle("Builder") is False  # Not throttled

    assert gov.throttle("nonexistent") is False
    print("OK: throttle unthrottle")


def test_list_agents():
    """List agents with throttle filter."""
    gov = ResourceGovernor()
    gov.register_agent("A")
    gov.register_agent("B")
    gov.throttle("A")

    all_agents = gov.list_agents()
    assert len(all_agents) == 2

    throttled = gov.list_agents(throttled_only=True)
    assert len(throttled) == 1
    assert throttled[0]["agent_name"] == "A"
    print("OK: list agents")


def test_stats():
    """Stats are accurate."""
    gov = ResourceGovernor()
    gov.register_agent("Builder")
    gov.set_quota("Builder", "tasks", 5.0, 10.0)
    gov.record_usage("Builder", "tasks", 3.0)
    gov.record_usage("Builder", "tasks", 8.0)  # Exceeds hard limit

    stats = gov.get_stats()
    assert stats["total_checks"] == 2
    assert stats["total_violations"] == 1
    assert stats["total_throttles"] == 1
    assert stats["total_agents"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    gov = ResourceGovernor()
    gov.register_agent("Builder")
    gov.set_quota("Builder", "cpu", 80.0, 100.0)
    gov.reserve("Builder", "cpu", 10.0)

    gov.reset()
    assert gov.list_agents() == []
    assert gov.list_reservations() == []
    stats = gov.get_stats()
    assert stats["total_agents"] == 0
    print("OK: reset")


def main():
    print("=== Resource Governor Tests ===\n")
    test_register_agent()
    test_set_quota()
    test_record_usage_within_limits()
    test_record_usage_soft_limit()
    test_record_usage_hard_limit()
    test_no_quota()
    test_unregistered_agent()
    test_get_usage()
    test_reset_usage()
    test_reserve()
    test_release()
    test_reservation_expiry()
    test_list_reservations()
    test_throttle_unthrottle()
    test_list_agents()
    test_stats()
    test_reset()
    print("\n=== ALL 17 TESTS PASSED ===")


if __name__ == "__main__":
    main()
