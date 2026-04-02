"""Test agent context tracker."""
import sys
sys.path.insert(0, ".")

from src.services.agent_context_tracker import AgentContextTracker


def test_create_context():
    """Create and retrieve context."""
    ct = AgentContextTracker()
    eid = ct.create_context("worker1", scope="task", data={"step": 1}, tags=["active"])
    assert eid.startswith("ctx-")

    c = ct.get_context(eid)
    assert c is not None
    assert c["agent"] == "worker1"
    assert c["scope"] == "task"
    assert c["data"] == {"step": 1}

    assert ct.remove_context(eid) is True
    assert ct.remove_context(eid) is False
    print("OK: create context")


def test_invalid_create():
    """Invalid creation rejected."""
    ct = AgentContextTracker()
    assert ct.create_context("") == ""
    assert ct.create_context("agent", scope="invalid") == ""
    print("OK: invalid create")


def test_duplicate():
    """Duplicate agent+scope rejected."""
    ct = AgentContextTracker()
    ct.create_context("w1", scope="task")
    assert ct.create_context("w1", scope="task") == ""
    # different scope ok
    assert ct.create_context("w1", scope="session") != ""
    print("OK: duplicate")


def test_max_entries():
    """Max entries enforced."""
    ct = AgentContextTracker(max_entries=2)
    ct.create_context("a", scope="task")
    ct.create_context("b", scope="task")
    assert ct.create_context("c", scope="task") == ""
    print("OK: max entries")


def test_get_by_agent_scope():
    """Get context by agent and scope."""
    ct = AgentContextTracker()
    ct.create_context("w1", scope="task", data={"x": 1})

    c = ct.get_by_agent_scope("w1", "task")
    assert c is not None
    assert c["data"]["x"] == 1
    assert ct.get_by_agent_scope("w1", "session") is None
    print("OK: get by agent scope")


def test_set_get_value():
    """Set and get individual values."""
    ct = AgentContextTracker()
    eid = ct.create_context("w1", scope="task")

    assert ct.set_value(eid, "key1", "value1") is True
    assert ct.get_value(eid, "key1") == "value1"
    assert ct.get_value(eid, "nonexistent", "default") == "default"
    assert ct.get_value("bad_id", "key") is None

    assert ct.set_value(eid, "", "val") is False
    assert ct.set_value("bad_id", "k", "v") is False
    print("OK: set get value")


def test_delete_value():
    """Delete individual value."""
    ct = AgentContextTracker()
    eid = ct.create_context("w1", scope="task", data={"a": 1, "b": 2})

    assert ct.delete_value(eid, "a") is True
    assert ct.get_value(eid, "a") is None
    assert ct.delete_value(eid, "nonexistent") is False
    print("OK: delete value")


def test_merge_data():
    """Merge data into context."""
    ct = AgentContextTracker()
    eid = ct.create_context("w1", scope="task", data={"a": 1})

    assert ct.merge_data(eid, {"b": 2, "c": 3}) is True
    c = ct.get_context(eid)
    assert c["data"] == {"a": 1, "b": 2, "c": 3}

    assert ct.merge_data("bad_id", {"x": 1}) is False
    print("OK: merge data")


def test_clear_data():
    """Clear all data in context."""
    ct = AgentContextTracker()
    eid = ct.create_context("w1", scope="task", data={"a": 1, "b": 2})

    assert ct.clear_data(eid) is True
    c = ct.get_context(eid)
    assert c["data"] == {}
    print("OK: clear data")


def test_ttl_expiry():
    """TTL expiry works."""
    ct = AgentContextTracker()
    eid = ct.create_context("w1", scope="task", ttl_seconds=0.001)

    import time
    time.sleep(0.01)

    assert ct.get_context(eid) is None  # expired
    assert ct.get_stats()["total_expired"] == 1
    print("OK: ttl expiry")


def test_cleanup_expired():
    """Cleanup expired contexts."""
    ct = AgentContextTracker()
    ct.create_context("w1", scope="task", ttl_seconds=0.001)
    ct.create_context("w2", scope="task")  # no TTL

    import time
    time.sleep(0.01)

    removed = ct.cleanup_expired()
    assert removed == 1
    assert ct.get_stats()["current_contexts"] == 1
    print("OK: cleanup expired")


def test_no_ttl_no_expiry():
    """No TTL means no expiry."""
    ct = AgentContextTracker()
    eid = ct.create_context("w1", scope="task", ttl_seconds=0.0)

    c = ct.get_context(eid)
    assert c is not None
    print("OK: no ttl no expiry")


def test_access_count():
    """Access count increments on read."""
    ct = AgentContextTracker()
    eid = ct.create_context("w1", scope="task")

    ct.get_context(eid)
    ct.get_context(eid)
    ct.get_value(eid, "anything")

    c = ct.get_context(eid)
    assert c["access_count"] == 4  # 3 prior + this one
    print("OK: access count")


def test_get_agent_contexts():
    """Get all contexts for an agent."""
    ct = AgentContextTracker()
    ct.create_context("w1", scope="task")
    ct.create_context("w1", scope="session")
    ct.create_context("w2", scope="task")

    w1 = ct.get_agent_contexts("w1")
    assert len(w1) == 2
    assert ct.get_agent_contexts("nonexistent") == []
    print("OK: get agent contexts")


def test_list_contexts():
    """List contexts with filters."""
    ct = AgentContextTracker()
    ct.create_context("w1", scope="task", tags=["active"])
    ct.create_context("w2", scope="session")

    all_c = ct.list_contexts()
    assert len(all_c) == 2

    by_agent = ct.list_contexts(agent="w1")
    assert len(by_agent) == 1

    by_scope = ct.list_contexts(scope="session")
    assert len(by_scope) == 1

    by_tag = ct.list_contexts(tag="active")
    assert len(by_tag) == 1
    print("OK: list contexts")


def test_history():
    """History tracking."""
    ct = AgentContextTracker()
    eid = ct.create_context("w1", scope="task")
    ct.set_value(eid, "key1", "val1")
    ct.set_value(eid, "key2", "val2")

    hist = ct.get_history()
    assert len(hist) == 2

    by_agent = ct.get_history(agent="w1")
    assert len(by_agent) == 2

    limited = ct.get_history(limit=1)
    assert len(limited) == 1
    print("OK: history")


def test_callback():
    """Callback fires on events."""
    ct = AgentContextTracker()
    fired = []
    ct.on_change("mon", lambda a, d: fired.append(a))

    ct.create_context("w1", scope="task")
    assert "context_created" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    ct = AgentContextTracker()
    assert ct.on_change("mon", lambda a, d: None) is True
    assert ct.on_change("mon", lambda a, d: None) is False
    assert ct.remove_callback("mon") is True
    assert ct.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    ct = AgentContextTracker()
    eid = ct.create_context("w1", scope="task")
    ct.create_context("w2", scope="task")
    ct.set_value(eid, "k", "v")
    ct.get_value(eid, "k")

    stats = ct.get_stats()
    assert stats["current_contexts"] == 2
    assert stats["total_created"] == 2
    assert stats["total_writes"] == 1
    assert stats["total_reads"] == 1
    assert stats["unique_agents"] == 2
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    ct = AgentContextTracker()
    ct.create_context("w1", scope="task")

    ct.reset()
    assert ct.list_contexts() == []
    stats = ct.get_stats()
    assert stats["current_contexts"] == 0
    print("OK: reset")


def main():
    print("=== Agent Context Tracker Tests ===\n")
    test_create_context()
    test_invalid_create()
    test_duplicate()
    test_max_entries()
    test_get_by_agent_scope()
    test_set_get_value()
    test_delete_value()
    test_merge_data()
    test_clear_data()
    test_ttl_expiry()
    test_cleanup_expired()
    test_no_ttl_no_expiry()
    test_access_count()
    test_get_agent_contexts()
    test_list_contexts()
    test_history()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 20 TESTS PASSED ===")


if __name__ == "__main__":
    main()
