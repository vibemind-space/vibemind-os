"""Tests for AgentPermissionCache."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src", "services"))

from agent_permission_cache import AgentPermissionCache


def test_grant():
    cache = AgentPermissionCache()
    pid = cache.grant("agent-1", "/data/files", "read")
    assert pid.startswith("apc-"), f"Expected apc- prefix, got {pid}"
    assert len(cache.permissions) == 1
    # Granting same permission again returns same ID
    pid2 = cache.grant("agent-1", "/data/files", "read")
    assert pid2 == pid
    assert len(cache.permissions) == 1
    # Different action creates new entry
    pid3 = cache.grant("agent-1", "/data/files", "write")
    assert pid3 != pid
    assert len(cache.permissions) == 2
    print("  test_grant PASSED")


def test_revoke():
    cache = AgentPermissionCache()
    cache.grant("agent-1", "/data/files", "read")
    result = cache.revoke("agent-1", "/data/files", "read")
    assert result is True
    assert len(cache.permissions) == 0
    # Revoking non-existent returns False
    result2 = cache.revoke("agent-1", "/data/files", "read")
    assert result2 is False
    print("  test_revoke PASSED")


def test_is_allowed():
    cache = AgentPermissionCache()
    assert cache.is_allowed("agent-1", "/data/files") is False
    cache.grant("agent-1", "/data/files", "read")
    assert cache.is_allowed("agent-1", "/data/files", "read") is True
    assert cache.is_allowed("agent-1", "/data/files", "write") is False
    assert cache.is_allowed("agent-2", "/data/files", "read") is False
    print("  test_is_allowed PASSED")


def test_get_permissions():
    cache = AgentPermissionCache()
    cache.grant("agent-1", "/data/files", "read")
    cache.grant("agent-1", "/data/logs", "write")
    cache.grant("agent-2", "/data/files", "read")
    perms = cache.get_permissions("agent-1")
    assert len(perms) == 2
    resources = {p["resource"] for p in perms}
    assert resources == {"/data/files", "/data/logs"}
    # Agent with no permissions
    assert cache.get_permissions("agent-99") == []
    print("  test_get_permissions PASSED")


def test_get_permission_count():
    cache = AgentPermissionCache()
    cache.grant("agent-1", "/data/files", "read")
    cache.grant("agent-1", "/data/logs", "write")
    cache.grant("agent-2", "/data/files", "read")
    assert cache.get_permission_count() == 3
    assert cache.get_permission_count("agent-1") == 2
    assert cache.get_permission_count("agent-2") == 1
    assert cache.get_permission_count("agent-99") == 0
    print("  test_get_permission_count PASSED")


def test_list_agents():
    cache = AgentPermissionCache()
    cache.grant("agent-b", "/res", "read")
    cache.grant("agent-a", "/res", "read")
    agents = cache.list_agents()
    assert agents == ["agent-a", "agent-b"]
    print("  test_list_agents PASSED")


def test_list_resources():
    cache = AgentPermissionCache()
    cache.grant("agent-1", "/data/logs", "read")
    cache.grant("agent-1", "/data/files", "write")
    cache.grant("agent-2", "/data/logs", "write")
    resources = cache.list_resources()
    assert resources == ["/data/files", "/data/logs"]
    print("  test_list_resources PASSED")


def test_callbacks():
    cache = AgentPermissionCache()
    events = []

    def on_event(action, detail):
        events.append((action, detail))

    assert cache.on_change("cb1", on_event) is True
    # Duplicate name returns False
    assert cache.on_change("cb1", on_event) is False

    cache.grant("agent-1", "/res", "read")
    assert len(events) == 1
    assert events[0][0] == "granted"

    cache.revoke("agent-1", "/res", "read")
    assert len(events) == 2
    assert events[1][0] == "revoked"

    # remove_callback returns True/False
    assert cache.remove_callback("cb1") is True
    assert cache.remove_callback("cb1") is False
    assert cache.remove_callback("nonexistent") is False

    cache.grant("agent-1", "/res2", "read")
    assert len(events) == 2  # no new events after callback removed
    print("  test_callbacks PASSED")


def test_stats():
    cache = AgentPermissionCache()
    cache.grant("agent-1", "/res", "read")
    cache.is_allowed("agent-1", "/res", "read")
    cache.is_allowed("agent-1", "/res", "write")
    cache.revoke("agent-1", "/res", "read")

    stats = cache.get_stats()
    assert isinstance(stats, dict)
    assert stats["total_grants"] == 1
    assert stats["total_revocations"] == 1
    assert stats["total_checks"] == 2
    assert stats["total_hits"] == 1
    assert stats["total_misses"] == 1
    assert stats["current_entries"] == 0
    assert "max_entries" in stats
    assert "seq" in stats
    print("  test_stats PASSED")


def test_reset():
    cache = AgentPermissionCache()
    cache.grant("agent-1", "/res", "read")
    cache.on_change("cb1", lambda a, d: None)
    cache.is_allowed("agent-1", "/res", "read")

    cache.reset()
    assert len(cache.permissions) == 0
    assert cache.get_permission_count() == 0
    stats = cache.get_stats()
    assert stats["total_grants"] == 0
    assert stats["total_checks"] == 0
    assert stats["callbacks_registered"] == 0
    assert stats["seq"] == 0
    print("  test_reset PASSED")


if __name__ == "__main__":
    test_grant()
    test_revoke()
    test_is_allowed()
    test_get_permissions()
    test_get_permission_count()
    test_list_agents()
    test_list_resources()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")
