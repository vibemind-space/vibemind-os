"""Test pipeline resource limiter."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_resource_limiter import PipelineResourceLimiter


def test_add_limit():
    """Add and retrieve limit."""
    rl = PipelineResourceLimiter()
    eid = rl.add_limit("api", resource="rate", max_value=100.0, tags=["prod"])
    assert eid.startswith("lmt-")

    e = rl.get_limit(eid)
    assert e is not None
    assert e["component"] == "api"
    assert e["resource"] == "rate"
    assert e["max_value"] == 100.0
    assert e["current_value"] == 0.0

    assert rl.remove_limit(eid) is True
    assert rl.remove_limit(eid) is False
    print("OK: add limit")


def test_invalid_add():
    """Invalid add rejected."""
    rl = PipelineResourceLimiter()
    assert rl.add_limit("") == ""
    assert rl.add_limit("api", resource="invalid") == ""
    assert rl.add_limit("api", resource="rate", max_value=-1.0) == ""
    print("OK: invalid add")


def test_duplicate():
    """Duplicate component+resource rejected."""
    rl = PipelineResourceLimiter()
    rl.add_limit("api", resource="rate", max_value=100.0)
    assert rl.add_limit("api", resource="rate", max_value=200.0) == ""
    # different resource is ok
    assert rl.add_limit("api", resource="concurrency", max_value=10.0) != ""
    print("OK: duplicate")


def test_max_entries():
    """Max entries enforced."""
    rl = PipelineResourceLimiter(max_entries=2)
    rl.add_limit("a", resource="rate", max_value=10.0)
    rl.add_limit("b", resource="rate", max_value=10.0)
    assert rl.add_limit("c", resource="rate", max_value=10.0) == ""
    print("OK: max entries")


def test_get_by_component():
    """Get limit by component and resource."""
    rl = PipelineResourceLimiter()
    rl.add_limit("api", resource="rate", max_value=100.0)

    e = rl.get_limit_by_component("api", "rate")
    assert e is not None
    assert e["component"] == "api"
    assert rl.get_limit_by_component("api", "memory") is None
    print("OK: get by component")


def test_acquire():
    """Acquire resource."""
    rl = PipelineResourceLimiter()
    eid = rl.add_limit("api", resource="concurrency", max_value=3.0)

    assert rl.acquire(eid, 1.0) is True
    assert rl.acquire(eid, 1.0) is True
    assert rl.acquire(eid, 1.0) is True
    assert rl.acquire(eid, 1.0) is False  # exceeded

    e = rl.get_limit(eid)
    assert e["current_value"] == 3.0
    assert e["total_requests"] == 4
    assert e["total_rejected"] == 1
    print("OK: acquire")


def test_acquire_by_component():
    """Acquire by component name."""
    rl = PipelineResourceLimiter()
    rl.add_limit("api", resource="rate", max_value=10.0)

    assert rl.acquire_by_component("api", "rate", 5.0) is True
    assert rl.acquire_by_component("api", "rate", 5.0) is True
    assert rl.acquire_by_component("api", "rate", 1.0) is False
    assert rl.acquire_by_component("nonexistent", "rate", 1.0) is False
    print("OK: acquire by component")


def test_release():
    """Release resource."""
    rl = PipelineResourceLimiter()
    eid = rl.add_limit("api", resource="concurrency", max_value=3.0)

    rl.acquire(eid, 2.0)
    assert rl.release(eid, 1.0) is True

    e = rl.get_limit(eid)
    assert e["current_value"] == 1.0

    # release more than current clamps to 0
    rl.release(eid, 10.0)
    e = rl.get_limit(eid)
    assert e["current_value"] == 0.0
    print("OK: release")


def test_release_by_component():
    """Release by component name."""
    rl = PipelineResourceLimiter()
    rl.add_limit("api", resource="concurrency", max_value=5.0)
    rl.acquire_by_component("api", "concurrency", 3.0)

    assert rl.release_by_component("api", "concurrency", 1.0) is True
    assert rl.release_by_component("nonexistent", "concurrency", 1.0) is False
    print("OK: release by component")


def test_burst():
    """Burst allowance."""
    rl = PipelineResourceLimiter()
    eid = rl.add_limit("api", resource="rate", max_value=10.0, burst_max=5.0)

    e = rl.get_limit(eid)
    assert e["effective_max"] == 15.0

    assert rl.acquire(eid, 12.0) is True  # within burst
    assert rl.acquire(eid, 4.0) is False  # exceeds burst
    print("OK: burst")


def test_usage_pct():
    """Usage percentage calculation."""
    rl = PipelineResourceLimiter()
    eid = rl.add_limit("api", resource="rate", max_value=200.0)

    rl.acquire(eid, 100.0)
    e = rl.get_limit(eid)
    assert abs(e["usage_pct"] - 50.0) < 0.01
    print("OK: usage pct")


def test_reset_usage():
    """Reset usage for entry."""
    rl = PipelineResourceLimiter()
    eid = rl.add_limit("api", resource="rate", max_value=10.0)
    rl.acquire(eid, 5.0)

    assert rl.reset_usage(eid) is True
    assert rl.get_limit(eid)["current_value"] == 0.0
    assert rl.reset_usage("nonexistent") is False
    print("OK: reset usage")


def test_update_limit():
    """Update limit values."""
    rl = PipelineResourceLimiter()
    eid = rl.add_limit("api", resource="rate", max_value=10.0)

    assert rl.update_limit(eid, max_value=20.0) is True
    assert rl.get_limit(eid)["max_value"] == 20.0

    assert rl.update_limit(eid, burst_max=5.0) is True
    assert rl.get_limit(eid)["burst_max"] == 5.0

    assert rl.update_limit("nonexistent") is False
    print("OK: update limit")


def test_get_component_limits():
    """Get all limits for a component."""
    rl = PipelineResourceLimiter()
    rl.add_limit("api", resource="rate", max_value=100.0)
    rl.add_limit("api", resource="concurrency", max_value=10.0)
    rl.add_limit("worker", resource="memory", max_value=1024.0)

    api_limits = rl.get_component_limits("api")
    assert len(api_limits) == 2
    assert rl.get_component_limits("nonexistent") == []
    print("OK: get component limits")


def test_get_exceeded():
    """Get entries exceeding their limit."""
    rl = PipelineResourceLimiter()
    eid1 = rl.add_limit("api", resource="rate", max_value=10.0, burst_max=5.0)
    eid2 = rl.add_limit("worker", resource="rate", max_value=10.0)

    rl.acquire(eid1, 12.0)  # over max but within burst
    rl.acquire(eid2, 5.0)   # under max

    exceeded = rl.get_exceeded()
    assert len(exceeded) == 1
    assert exceeded[0]["component"] == "api"
    print("OK: get exceeded")


def test_list_limits():
    """List limits with filters."""
    rl = PipelineResourceLimiter()
    rl.add_limit("api", resource="rate", max_value=100.0, tags=["prod"])
    rl.add_limit("worker", resource="memory", max_value=1024.0)

    all_l = rl.list_limits()
    assert len(all_l) == 2

    by_comp = rl.list_limits(component="api")
    assert len(by_comp) == 1

    by_res = rl.list_limits(resource="memory")
    assert len(by_res) == 1

    by_tag = rl.list_limits(tag="prod")
    assert len(by_tag) == 1
    print("OK: list limits")


def test_history():
    """Event history."""
    rl = PipelineResourceLimiter()
    eid = rl.add_limit("api", resource="rate", max_value=10.0)
    rl.acquire(eid, 5.0)
    rl.release(eid, 2.0)
    rl.acquire(eid, 20.0)  # rejected

    hist = rl.get_history()
    assert len(hist) == 3

    by_comp = rl.get_history(component="api")
    assert len(by_comp) == 3

    rejected = rl.get_history(action="rejected")
    assert len(rejected) == 1

    limited = rl.get_history(limit=1)
    assert len(limited) == 1
    print("OK: history")


def test_callback():
    """Callback fires on events."""
    rl = PipelineResourceLimiter()
    fired = []
    rl.on_change("mon", lambda a, d: fired.append(a))

    eid = rl.add_limit("api", resource="rate", max_value=5.0)
    assert "limit_added" in fired

    rl.acquire(eid, 10.0)  # exceeds
    assert "limit_exceeded" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    rl = PipelineResourceLimiter()
    assert rl.on_change("mon", lambda a, d: None) is True
    assert rl.on_change("mon", lambda a, d: None) is False
    assert rl.remove_callback("mon") is True
    assert rl.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    rl = PipelineResourceLimiter()
    eid = rl.add_limit("api", resource="rate", max_value=10.0)
    rl.acquire(eid, 5.0)
    rl.acquire(eid, 3.0)
    rl.acquire(eid, 5.0)  # rejected

    stats = rl.get_stats()
    assert stats["current_limits"] == 1
    assert stats["total_created"] == 1
    assert stats["total_requests"] == 3
    assert stats["total_allowed"] == 2
    assert stats["total_rejected"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    rl = PipelineResourceLimiter()
    rl.add_limit("api", resource="rate", max_value=10.0)

    rl.reset()
    assert rl.list_limits() == []
    stats = rl.get_stats()
    assert stats["current_limits"] == 0
    assert stats["history_size"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Resource Limiter Tests ===\n")
    test_add_limit()
    test_invalid_add()
    test_duplicate()
    test_max_entries()
    test_get_by_component()
    test_acquire()
    test_acquire_by_component()
    test_release()
    test_release_by_component()
    test_burst()
    test_usage_pct()
    test_reset_usage()
    test_update_limit()
    test_get_component_limits()
    test_get_exceeded()
    test_list_limits()
    test_history()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 21 TESTS PASSED ===")


if __name__ == "__main__":
    main()
