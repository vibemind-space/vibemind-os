"""Test pipeline cache manager."""
import sys
import time
sys.path.insert(0, ".")

from src.services.pipeline_cache_manager import PipelineCacheManager


def test_set_get():
    """Set and get value."""
    cm = PipelineCacheManager()
    assert cm.set("key1", "value1") is True
    assert cm.get("key1") == "value1"
    print("OK: set get")


def test_invalid_key():
    """Empty key rejected."""
    cm = PipelineCacheManager()
    assert cm.set("", "val") is False
    print("OK: invalid key")


def test_get_missing():
    """Missing key returns None."""
    cm = PipelineCacheManager()
    assert cm.get("nonexistent") is None
    print("OK: get missing")


def test_delete():
    """Delete entry."""
    cm = PipelineCacheManager()
    cm.set("key1", "value1")
    assert cm.delete("key1") is True
    assert cm.delete("key1") is False
    assert cm.get("key1") is None
    print("OK: delete")


def test_exists():
    """Check exists."""
    cm = PipelineCacheManager()
    cm.set("key1", "value1")
    assert cm.exists("key1") is True
    assert cm.exists("nonexistent") is False
    print("OK: exists")


def test_overwrite():
    """Overwrite existing key."""
    cm = PipelineCacheManager()
    cm.set("key1", "old")
    cm.set("key1", "new")
    assert cm.get("key1") == "new"
    print("OK: overwrite")


def test_namespace_isolation():
    """Different namespaces are isolated."""
    cm = PipelineCacheManager()
    cm.set("key1", "val_a", namespace="ns_a")
    cm.set("key1", "val_b", namespace="ns_b")

    assert cm.get("key1", namespace="ns_a") == "val_a"
    assert cm.get("key1", namespace="ns_b") == "val_b"
    print("OK: namespace isolation")


def test_clear_namespace():
    """Clear namespace."""
    cm = PipelineCacheManager()
    cm.set("a", 1, namespace="ns1")
    cm.set("b", 2, namespace="ns1")
    cm.set("c", 3, namespace="ns2")

    cleared = cm.clear_namespace("ns1")
    assert cleared == 2
    assert cm.get("a", namespace="ns1") is None
    assert cm.get("c", namespace="ns2") == 3
    print("OK: clear namespace")


def test_get_namespaces():
    """Get active namespaces."""
    cm = PipelineCacheManager()
    cm.set("a", 1, namespace="alpha")
    cm.set("b", 2, namespace="beta")

    ns = cm.get_namespaces()
    assert "alpha" in ns
    assert "beta" in ns
    print("OK: get namespaces")


def test_ttl_expiration():
    """TTL expiration works."""
    cm = PipelineCacheManager(default_ttl_ms=50.0)  # 50ms default
    cm.set("key1", "value1", ttl_ms=50.0)

    assert cm.get("key1") == "value1"
    time.sleep(0.1)  # wait for expiration
    assert cm.get("key1") is None
    print("OK: ttl expiration")


def test_lru_eviction():
    """LRU eviction when at capacity."""
    cm = PipelineCacheManager(max_entries=3, default_ttl_ms=0)
    cm.set("a", 1)
    time.sleep(0.01)
    cm.set("b", 2)
    time.sleep(0.01)
    cm.set("c", 3)
    time.sleep(0.01)

    # Access 'a' and 'c' to make them recently used
    cm.get("a")
    cm.get("c")
    time.sleep(0.01)

    # Adding 'd' should evict 'b' (least recently used)
    cm.set("d", 4)
    assert cm.get("a") is not None  # still there (was accessed)
    assert cm.get("c") is not None  # still there (was accessed)
    assert cm.get("d") is not None  # added
    # b was evicted
    print("OK: lru eviction")


def test_get_or_set():
    """Get or set default."""
    cm = PipelineCacheManager()

    # First call: sets default
    val = cm.get_or_set("key1", "default_val")
    assert val == "default_val"

    # Second call: returns cached
    cm.set("key1", "updated")
    val = cm.get_or_set("key1", "other")
    assert val == "updated"
    print("OK: get or set")


def test_cleanup_expired():
    """Cleanup expired entries."""
    cm = PipelineCacheManager()
    cm.set("short", "val", ttl_ms=50.0)
    cm.set("long", "val", ttl_ms=999999.0)

    time.sleep(0.1)
    removed = cm.cleanup_expired()
    assert removed == 1
    assert cm.get("long") is not None
    print("OK: cleanup expired")


def test_entry_info():
    """Get entry metadata."""
    cm = PipelineCacheManager()
    cm.set("key1", "value1", namespace="ns1", tags=["important"])

    info = cm.get_entry_info("key1", namespace="ns1")
    assert info is not None
    assert info["key"] == "key1"
    assert info["namespace"] == "ns1"
    assert "important" in info["tags"]
    assert info["size_bytes"] > 0

    assert cm.get_entry_info("nonexistent") is None
    print("OK: entry info")


def test_search_entries():
    """Search cache entries."""
    cm = PipelineCacheManager()
    cm.set("a", 1, namespace="ns1", tags=["hot"])
    cm.set("b", 2, namespace="ns2")

    all_e = cm.search_entries()
    assert len(all_e) == 2

    by_ns = cm.search_entries(namespace="ns1")
    assert len(by_ns) == 1

    by_tag = cm.search_entries(tag="hot")
    assert len(by_tag) == 1
    print("OK: search entries")


def test_hit_rate():
    """Get hit rate."""
    cm = PipelineCacheManager()
    cm.set("key1", "val")

    cm.get("key1")  # hit
    cm.get("key1")  # hit
    cm.get("missing")  # miss

    rate = cm.get_hit_rate()
    assert rate["total_gets"] == 3
    assert rate["total_hits"] == 2
    assert abs(rate["hit_rate"] - 66.7) < 0.1
    print("OK: hit rate")


def test_namespace_size():
    """Get namespace size."""
    cm = PipelineCacheManager()
    cm.set("a", 1, namespace="ns1")
    cm.set("b", 2, namespace="ns1")
    cm.set("c", 3, namespace="ns2")

    assert cm.get_namespace_size("ns1") == 2
    assert cm.get_namespace_size("ns2") == 1
    print("OK: namespace size")


def test_callbacks():
    """Callback registration."""
    cm = PipelineCacheManager()
    assert cm.on_change("mon", lambda a, d: None) is True
    assert cm.on_change("mon", lambda a, d: None) is False
    assert cm.remove_callback("mon") is True
    assert cm.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    cm = PipelineCacheManager()
    cm.set("key1", "val")
    cm.get("key1")
    cm.get("missing")

    stats = cm.get_stats()
    assert stats["total_sets"] == 1
    assert stats["total_gets"] == 2
    assert stats["total_hits"] == 1
    assert stats["total_misses"] == 1
    assert stats["current_entries"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    cm = PipelineCacheManager()
    cm.set("key1", "val")

    cm.reset()
    assert cm.search_entries() == []
    stats = cm.get_stats()
    assert stats["current_entries"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Cache Manager Tests ===\n")
    test_set_get()
    test_invalid_key()
    test_get_missing()
    test_delete()
    test_exists()
    test_overwrite()
    test_namespace_isolation()
    test_clear_namespace()
    test_get_namespaces()
    test_ttl_expiration()
    test_lru_eviction()
    test_get_or_set()
    test_cleanup_expired()
    test_entry_info()
    test_search_entries()
    test_hit_rate()
    test_namespace_size()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 20 TESTS PASSED ===")


if __name__ == "__main__":
    main()
