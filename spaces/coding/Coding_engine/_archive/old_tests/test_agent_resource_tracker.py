"""Test agent resource tracker."""
import sys
sys.path.insert(0, ".")

from src.services.agent_resource_tracker import AgentResourceTracker


def test_track():
    """Track and retrieve resource entry."""
    rt = AgentResourceTracker()
    eid = rt.track("worker1", resource_type="memory", quota=1024.0, tags=["prod"])
    assert eid.startswith("rsc-")

    e = rt.get_entry(eid)
    assert e is not None
    assert e["agent"] == "worker1"
    assert e["resource_type"] == "memory"
    assert e["quota"] == 1024.0
    assert e["current_usage"] == 0.0

    assert rt.remove_entry(eid) is True
    assert rt.remove_entry(eid) is False
    print("OK: track")


def test_invalid_track():
    """Invalid tracking rejected."""
    rt = AgentResourceTracker()
    assert rt.track("") == ""
    assert rt.track("agent", resource_type="invalid") == ""
    print("OK: invalid track")


def test_duplicate_resource():
    """Duplicate agent+resource_type rejected."""
    rt = AgentResourceTracker()
    rt.track("w1", resource_type="cpu")
    assert rt.track("w1", resource_type="cpu") == ""
    # different type is ok
    assert rt.track("w1", resource_type="memory") != ""
    print("OK: duplicate resource")


def test_max_entries():
    """Max entries enforced."""
    rt = AgentResourceTracker(max_entries=2)
    rt.track("a", resource_type="cpu")
    rt.track("b", resource_type="cpu")
    assert rt.track("c", resource_type="cpu") == ""
    print("OK: max entries")


def test_record():
    """Record resource usage."""
    rt = AgentResourceTracker()
    eid = rt.track("w1", resource_type="memory")

    assert rt.record(eid, 512.0) is True
    e = rt.get_entry(eid)
    assert e["current_usage"] == 512.0
    assert e["peak_usage"] == 512.0
    assert e["total_consumed"] == 512.0
    assert e["sample_count"] == 1

    rt.record(eid, 256.0)
    e = rt.get_entry(eid)
    assert e["current_usage"] == 256.0
    assert e["peak_usage"] == 512.0  # peak preserved
    assert e["total_consumed"] == 768.0
    assert e["sample_count"] == 2
    print("OK: record")


def test_record_invalid():
    """Invalid record rejected."""
    rt = AgentResourceTracker()
    eid = rt.track("w1", resource_type="cpu")
    assert rt.record("nonexistent", 10.0) is False
    assert rt.record(eid, -1.0) is False
    print("OK: record invalid")


def test_quota():
    """Quota tracking."""
    rt = AgentResourceTracker()
    eid = rt.track("w1", resource_type="memory", quota=100.0)

    e = rt.get_entry(eid)
    assert e["quota"] == 100.0
    assert e["quota_pct"] == 0.0

    rt.record(eid, 50.0)
    e = rt.get_entry(eid)
    assert abs(e["quota_pct"] - 50.0) < 0.01
    print("OK: quota")


def test_quota_exceeded():
    """Quota exceeded event fires."""
    rt = AgentResourceTracker()
    fired = []
    rt.on_change("mon", lambda a, d: fired.append(a))

    eid = rt.track("w1", resource_type="memory", quota=100.0)
    rt.record(eid, 150.0)  # exceeds quota

    assert "quota_exceeded" in fired
    assert rt.get_stats()["total_quota_exceeded"] == 1
    print("OK: quota exceeded")


def test_set_quota():
    """Set or update quota."""
    rt = AgentResourceTracker()
    eid = rt.track("w1", resource_type="cpu")

    assert rt.set_quota(eid, 200.0) is True
    assert rt.get_entry(eid)["quota"] == 200.0

    assert rt.set_quota(eid, -1.0) is False
    assert rt.set_quota("nonexistent", 100.0) is False
    print("OK: set quota")


def test_get_agent_usage():
    """Get all resources for an agent."""
    rt = AgentResourceTracker()
    rt.track("w1", resource_type="cpu")
    rt.track("w1", resource_type="memory")
    rt.track("w2", resource_type="cpu")

    w1_usage = rt.get_agent_usage("w1")
    assert len(w1_usage) == 2

    assert rt.get_agent_usage("nonexistent") == []
    print("OK: get agent usage")


def test_get_over_quota():
    """Get entries over quota."""
    rt = AgentResourceTracker()
    eid1 = rt.track("w1", resource_type="memory", quota=100.0)
    eid2 = rt.track("w2", resource_type="memory", quota=200.0)

    rt.record(eid1, 150.0)  # over
    rt.record(eid2, 100.0)  # under

    over = rt.get_over_quota()
    assert len(over) == 1
    assert over[0]["agent"] == "w1"
    print("OK: get over quota")


def test_list_entries():
    """List entries with filters."""
    rt = AgentResourceTracker()
    rt.track("w1", resource_type="cpu", tags=["prod"])
    rt.track("w2", resource_type="memory")

    all_e = rt.list_entries()
    assert len(all_e) == 2

    by_agent = rt.list_entries(agent="w1")
    assert len(by_agent) == 1

    by_type = rt.list_entries(resource_type="memory")
    assert len(by_type) == 1

    by_tag = rt.list_entries(tag="prod")
    assert len(by_tag) == 1
    print("OK: list entries")


def test_total_usage_by_type():
    """Get total usage by resource type."""
    rt = AgentResourceTracker()
    eid1 = rt.track("w1", resource_type="cpu")
    eid2 = rt.track("w2", resource_type="cpu")
    rt.track("w3", resource_type="memory")

    rt.record(eid1, 40.0)
    rt.record(eid2, 60.0)

    assert abs(rt.get_total_usage_by_type("cpu") - 100.0) < 0.01
    assert rt.get_total_usage_by_type("memory") == 0.0
    print("OK: total usage by type")


def test_callback():
    """Callback fires on events."""
    rt = AgentResourceTracker()
    fired = []
    rt.on_change("mon", lambda a, d: fired.append(a))

    rt.track("w1", resource_type="cpu")
    assert "resource_tracked" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    rt = AgentResourceTracker()
    assert rt.on_change("mon", lambda a, d: None) is True
    assert rt.on_change("mon", lambda a, d: None) is False
    assert rt.remove_callback("mon") is True
    assert rt.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    rt = AgentResourceTracker()
    eid = rt.track("w1", resource_type="cpu")
    rt.track("w2", resource_type="memory")
    rt.record(eid, 50.0)

    stats = rt.get_stats()
    assert stats["current_entries"] == 2
    assert stats["total_tracked"] == 2
    assert stats["total_recordings"] == 1
    assert stats["unique_agents"] == 2
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    rt = AgentResourceTracker()
    rt.track("w1", resource_type="cpu")

    rt.reset()
    assert rt.list_entries() == []
    stats = rt.get_stats()
    assert stats["current_entries"] == 0
    print("OK: reset")


def main():
    print("=== Agent Resource Tracker Tests ===\n")
    test_track()
    test_invalid_track()
    test_duplicate_resource()
    test_max_entries()
    test_record()
    test_record_invalid()
    test_quota()
    test_quota_exceeded()
    test_set_quota()
    test_get_agent_usage()
    test_get_over_quota()
    test_list_entries()
    test_total_usage_by_type()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 17 TESTS PASSED ===")


if __name__ == "__main__":
    main()
