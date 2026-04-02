"""Test agent cache store -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_cache_store import AgentCacheStore


def test_put_and_get():
    cs = AgentCacheStore()
    cid = cs.put("agent-1", "result", {"data": 42}, namespace="compute", ttl=3600)
    assert len(cid) > 0
    val = cs.get("agent-1", "result", namespace="compute")
    assert val is not None
    assert val == {"data": 42} or val.get("data") == 42
    print("OK: put and get")


def test_get_missing():
    cs = AgentCacheStore()
    val = cs.get("agent-1", "nonexistent")
    assert val is None
    print("OK: get missing")


def test_delete():
    cs = AgentCacheStore()
    cs.put("agent-1", "key1", "value1")
    assert cs.delete("agent-1", "key1") is True
    assert cs.delete("agent-1", "key1") is False
    print("OK: delete")


def test_has():
    cs = AgentCacheStore()
    cs.put("agent-1", "key1", "value1")
    assert cs.has("agent-1", "key1") is True
    assert cs.has("agent-1", "missing") is False
    print("OK: has")


def test_clear_agent():
    cs = AgentCacheStore()
    cs.put("agent-1", "k1", "v1")
    cs.put("agent-1", "k2", "v2")
    cs.put("agent-2", "k1", "v1")
    count = cs.clear_agent("agent-1")
    assert count == 2
    assert cs.has("agent-2", "k1") is True
    print("OK: clear agent")


def test_get_or_compute():
    cs = AgentCacheStore()
    val = cs.get_or_compute("agent-1", "computed", lambda: 42)
    assert val == 42
    # Second call should hit cache
    val2 = cs.get_or_compute("agent-1", "computed", lambda: 999)
    assert val2 == 42  # cached value, not recomputed
    print("OK: get or compute")


def test_list_keys():
    cs = AgentCacheStore()
    cs.put("agent-1", "k1", "v1")
    cs.put("agent-1", "k2", "v2")
    keys = cs.list_keys("agent-1")
    assert "k1" in keys
    assert "k2" in keys
    print("OK: list keys")


def test_ttl_expiry():
    cs = AgentCacheStore()
    cs.put("agent-1", "short", "value", ttl=0.01)
    import time
    time.sleep(0.02)
    val = cs.get("agent-1", "short")
    assert val is None  # expired
    print("OK: TTL expiry")


def test_cache_stats():
    cs = AgentCacheStore()
    cs.put("agent-1", "k1", "v1")
    cs.get("agent-1", "k1")  # hit
    cs.get("agent-1", "missing")  # miss
    stats = cs.get_cache_stats()
    assert stats["hits"] >= 1
    assert stats["misses"] >= 1
    print("OK: cache stats")


def test_callbacks():
    cs = AgentCacheStore()
    fired = []
    cs.on_change("mon", lambda a, d: fired.append(a))
    cs.put("agent-1", "k1", "v1")
    assert len(fired) >= 1
    assert cs.remove_callback("mon") is True
    print("OK: callbacks")


def test_reset():
    cs = AgentCacheStore()
    cs.put("agent-1", "k1", "v1")
    cs.reset()
    assert cs.has("agent-1", "k1") is False
    print("OK: reset")


def main():
    print("=== Agent Cache Store Tests ===\n")
    test_put_and_get()
    test_get_missing()
    test_delete()
    test_has()
    test_clear_agent()
    test_get_or_compute()
    test_list_keys()
    test_ttl_expiry()
    test_cache_stats()
    test_callbacks()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
