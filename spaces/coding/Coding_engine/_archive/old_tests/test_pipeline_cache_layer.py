"""Test pipeline cache layer."""
import sys
import time
sys.path.insert(0, ".")

from src.services.pipeline_cache_layer import PipelineCacheLayer


def test_set_get():
    """Set and get value."""
    cache = PipelineCacheLayer()
    assert cache.set("key1", "value1") is True
    assert cache.get("key1") == "value1"
    assert cache.get("nonexistent") is None
    assert cache.get("nonexistent", default="def") == "def"
    print("OK: set get")


def test_invalid_set():
    """Invalid key rejected."""
    cache = PipelineCacheLayer()
    assert cache.set("", "val") is False
    print("OK: invalid set")


def test_update():
    """Update existing key."""
    cache = PipelineCacheLayer()
    cache.set("key1", "v1")
    cache.set("key1", "v2")
    assert cache.get("key1") == "v2"
    print("OK: update")


def test_delete():
    """Delete key."""
    cache = PipelineCacheLayer()
    cache.set("key1", "v1")
    assert cache.delete("key1") is True
    assert cache.delete("key1") is False
    assert cache.get("key1") is None
    print("OK: delete")


def test_exists():
    """Check key exists."""
    cache = PipelineCacheLayer()
    cache.set("key1", "v1")
    assert cache.exists("key1") is True
    assert cache.exists("nonexistent") is False
    print("OK: exists")


def test_ttl_expiry():
    """TTL expiry works."""
    cache = PipelineCacheLayer()
    cache.set("key1", "v1", ttl_seconds=0.001)
    time.sleep(0.01)
    assert cache.get("key1") is None
    print("OK: ttl expiry")


def test_exists_expiry():
    """Exists returns false for expired."""
    cache = PipelineCacheLayer()
    cache.set("key1", "v1", ttl_seconds=0.001)
    time.sleep(0.01)
    assert cache.exists("key1") is False
    print("OK: exists expiry")


def test_namespaces():
    """Namespace isolation."""
    cache = PipelineCacheLayer()
    cache.set("key1", "v1", namespace="ns1")
    cache.set("key1", "v2", namespace="ns2")

    assert cache.get("key1", namespace="ns1") == "v1"
    assert cache.get("key1", namespace="ns2") == "v2"
    print("OK: namespaces")


def test_clear_namespace():
    """Clear all entries in a namespace."""
    cache = PipelineCacheLayer()
    cache.set("a", "1", namespace="ns1")
    cache.set("b", "2", namespace="ns1")
    cache.set("c", "3", namespace="ns2")

    removed = cache.clear_namespace("ns1")
    assert removed == 2
    assert cache.get("a", namespace="ns1") is None
    assert cache.get("c", namespace="ns2") == "3"
    print("OK: clear namespace")


def test_get_namespace_keys():
    """Get keys in a namespace."""
    cache = PipelineCacheLayer()
    cache.set("a", "1", namespace="ns1")
    cache.set("b", "2", namespace="ns1")
    cache.set("c", "3", namespace="ns2")

    keys = cache.get_namespace_keys("ns1")
    assert sorted(keys) == ["a", "b"]
    print("OK: get namespace keys")


def test_lru_eviction():
    """LRU eviction when at capacity."""
    cache = PipelineCacheLayer(max_entries=2)
    cache.set("a", "1")
    cache.set("b", "2")
    cache.set("c", "3")  # evicts "a" (LRU)

    assert cache.get("a") is None
    assert cache.get("b") == "2"
    assert cache.get("c") == "3"
    print("OK: lru eviction")


def test_access_moves_to_end():
    """Accessing moves to end of LRU."""
    cache = PipelineCacheLayer(max_entries=2)
    cache.set("a", "1")
    cache.set("b", "2")
    cache.get("a")  # touch "a", making "b" LRU
    cache.set("c", "3")  # evicts "b"

    assert cache.get("a") == "1"
    assert cache.get("b") is None
    assert cache.get("c") == "3"
    print("OK: access moves to end")


def test_get_or_set():
    """Get or set with factory."""
    cache = PipelineCacheLayer()
    calls = [0]

    def factory():
        calls[0] += 1
        return "computed"

    val = cache.get_or_set("key1", factory)
    assert val == "computed"
    assert calls[0] == 1

    val = cache.get_or_set("key1", factory)
    assert val == "computed"
    assert calls[0] == 1  # not called again
    print("OK: get or set")


def test_cleanup_expired():
    """Cleanup expired entries."""
    cache = PipelineCacheLayer()
    cache.set("short", "1", ttl_seconds=0.001)
    cache.set("long", "2", ttl_seconds=9999)

    time.sleep(0.01)
    removed = cache.cleanup_expired()
    assert removed == 1
    assert cache.size() == 1
    print("OK: cleanup expired")


def test_get_info():
    """Get entry info."""
    cache = PipelineCacheLayer()
    cache.set("key1", "v1", ttl_seconds=60)

    info = cache.get_info("key1")
    assert info is not None
    assert info["key"] == "key1"
    assert info["ttl_seconds"] == 60
    assert info["remaining_ttl"] > 0

    assert cache.get_info("nonexistent") is None
    print("OK: get info")


def test_size():
    """Size returns current count."""
    cache = PipelineCacheLayer()
    assert cache.size() == 0
    cache.set("a", "1")
    cache.set("b", "2")
    assert cache.size() == 2
    print("OK: size")


def test_callbacks():
    """Callback registration."""
    cache = PipelineCacheLayer()
    assert cache.on_change("mon", lambda a, d: None) is True
    assert cache.on_change("mon", lambda a, d: None) is False
    assert cache.remove_callback("mon") is True
    assert cache.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    cache = PipelineCacheLayer()
    cache.set("a", "1")
    cache.get("a")  # hit
    cache.get("b")  # miss

    stats = cache.get_stats()
    assert stats["current_entries"] == 1
    assert stats["total_sets"] == 1
    assert stats["total_gets"] == 2
    assert stats["total_hits"] == 1
    assert stats["total_misses"] == 1
    assert abs(stats["hit_rate_pct"] - 50.0) < 0.01
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    cache = PipelineCacheLayer()
    cache.set("a", "1")

    cache.reset()
    assert cache.size() == 0
    stats = cache.get_stats()
    assert stats["current_entries"] == 0
    assert stats["total_sets"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Cache Layer Tests ===\n")
    test_set_get()
    test_invalid_set()
    test_update()
    test_delete()
    test_exists()
    test_ttl_expiry()
    test_exists_expiry()
    test_namespaces()
    test_clear_namespace()
    test_get_namespace_keys()
    test_lru_eviction()
    test_access_moves_to_end()
    test_get_or_set()
    test_cleanup_expired()
    test_get_info()
    test_size()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 19 TESTS PASSED ===")


if __name__ == "__main__":
    main()
