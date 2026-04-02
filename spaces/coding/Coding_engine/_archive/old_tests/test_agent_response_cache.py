"""Tests for AgentResponseCache."""

import time
import sys
sys.path.insert(0, ".")

from src.services.agent_response_cache import AgentResponseCache


def test_cache_response():
    cache = AgentResponseCache()
    cid = cache.cache_response("agent-1", "req-1", {"result": "ok"})
    assert cid.startswith("arc-"), f"Expected arc- prefix, got {cid}"
    assert len(cid) > 4
    # Caching again should update and return same id
    cid2 = cache.cache_response("agent-1", "req-1", {"result": "updated"})
    assert cid2 == cid, "Should return same cache id on update"
    print("  test_cache_response PASSED")


def test_get_response():
    cache = AgentResponseCache()
    cache.cache_response("agent-1", "req-1", {"data": 42})
    result = cache.get_response("agent-1", "req-1")
    assert result == {"data": 42}, f"Expected data, got {result}"
    # Missing key
    result2 = cache.get_response("agent-1", "req-999")
    assert result2 is None, "Expected None for missing key"
    print("  test_get_response PASSED")


def test_has_response():
    cache = AgentResponseCache()
    cache.cache_response("agent-1", "req-1", "hello")
    assert cache.has_response("agent-1", "req-1") is True
    assert cache.has_response("agent-1", "req-missing") is False
    assert cache.has_response("agent-999", "req-1") is False
    print("  test_has_response PASSED")


def test_invalidate():
    cache = AgentResponseCache()
    cache.cache_response("agent-1", "req-1", "value1")
    assert cache.invalidate("agent-1", "req-1") is True
    assert cache.has_response("agent-1", "req-1") is False
    assert cache.get_response("agent-1", "req-1") is None
    # Invalidate non-existent
    assert cache.invalidate("agent-1", "req-1") is False
    print("  test_invalidate PASSED")


def test_invalidate_all():
    cache = AgentResponseCache()
    cache.cache_response("agent-1", "req-1", "v1")
    cache.cache_response("agent-1", "req-2", "v2")
    cache.cache_response("agent-2", "req-1", "v3")
    count = cache.invalidate_all("agent-1")
    assert count == 2, f"Expected 2 removed, got {count}"
    assert cache.has_response("agent-1", "req-1") is False
    assert cache.has_response("agent-1", "req-2") is False
    assert cache.has_response("agent-2", "req-1") is True
    print("  test_invalidate_all PASSED")


def test_ttl_expiry():
    cache = AgentResponseCache()
    cache.cache_response("agent-1", "req-1", "temp", ttl_seconds=0.3)
    assert cache.has_response("agent-1", "req-1") is True
    assert cache.get_response("agent-1", "req-1") == "temp"
    time.sleep(0.4)
    assert cache.has_response("agent-1", "req-1") is False
    assert cache.get_response("agent-1", "req-1") is None
    print("  test_ttl_expiry PASSED")


def test_get_cache_size():
    cache = AgentResponseCache()
    assert cache.get_cache_size() == 0
    cache.cache_response("agent-1", "req-1", "v1")
    cache.cache_response("agent-1", "req-2", "v2")
    cache.cache_response("agent-2", "req-1", "v3")
    assert cache.get_cache_size() == 3
    assert cache.get_cache_size("agent-1") == 2
    assert cache.get_cache_size("agent-2") == 1
    assert cache.get_cache_size("agent-999") == 0
    print("  test_get_cache_size PASSED")


def test_list_agents():
    cache = AgentResponseCache()
    assert cache.list_agents() == []
    cache.cache_response("agent-b", "req-1", "v1")
    cache.cache_response("agent-a", "req-1", "v2")
    cache.cache_response("agent-b", "req-2", "v3")
    agents = cache.list_agents()
    assert agents == ["agent-a", "agent-b"], f"Expected sorted agents, got {agents}"
    print("  test_list_agents PASSED")


def test_callbacks():
    cache = AgentResponseCache()
    events = []

    def listener(action, data):
        events.append((action, data))

    assert cache.on_change("my_cb", listener) is True
    assert cache.on_change("my_cb", listener) is False  # duplicate

    cache.cache_response("agent-1", "req-1", "val")
    assert len(events) == 1
    assert events[0][0] == "response_cached"

    cache.invalidate("agent-1", "req-1")
    assert len(events) == 2
    assert events[1][0] == "response_invalidated"

    assert cache.remove_callback("my_cb") is True
    assert cache.remove_callback("my_cb") is False  # already removed

    cache.cache_response("agent-1", "req-2", "val2")
    assert len(events) == 2  # no new events
    print("  test_callbacks PASSED")


def test_stats():
    cache = AgentResponseCache()
    cache.cache_response("agent-1", "req-1", "v1")
    cache.get_response("agent-1", "req-1")  # hit
    cache.get_response("agent-1", "req-missing")  # miss

    stats = cache.get_stats()
    assert stats["current_entries"] == 1
    assert stats["total_caches"] == 1
    assert stats["total_gets"] == 2
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["hit_rate"] == 0.5
    print("  test_stats PASSED")


def test_reset():
    cache = AgentResponseCache()
    cache.cache_response("agent-1", "req-1", "v1")
    cache.on_change("cb1", lambda a, d: None)
    cache.get_response("agent-1", "req-1")

    cache.reset()

    assert cache.get_cache_size() == 0
    assert cache.list_agents() == []
    stats = cache.get_stats()
    assert stats["current_entries"] == 0
    assert stats["total_caches"] == 0
    assert stats["total_gets"] == 0
    assert stats["hits"] == 0
    assert stats["misses"] == 0
    assert stats["callbacks"] == 0
    print("  test_reset PASSED")


if __name__ == "__main__":
    tests = [
        test_cache_response,
        test_get_response,
        test_has_response,
        test_invalidate,
        test_invalidate_all,
        test_ttl_expiry,
        test_get_cache_size,
        test_list_agents,
        test_callbacks,
        test_stats,
        test_reset,
    ]
    passed = 0
    for t in tests:
        t()
        passed += 1
    print(f"\n=== ALL {passed} TESTS PASSED ===")
