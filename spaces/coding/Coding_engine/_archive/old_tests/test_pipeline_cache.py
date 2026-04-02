"""Test pipeline cache."""
import sys
import time
sys.path.insert(0, ".")

from src.services.pipeline_cache import PipelineCache


def test_set_get():
    """Basic set and get."""
    cache = PipelineCache()
    assert cache.set("key1", "value1") is True
    assert cache.get("key1") == "value1"
    assert cache.get("nonexistent") is None
    assert cache.get("key1", namespace="other") is None
    print("OK: set get")


def test_namespaces():
    """Namespace isolation."""
    cache = PipelineCache()
    cache.set("k", "global_val", namespace="global")
    cache.set("k", "agent_val", namespace="agent-1")

    assert cache.get("k", "global") == "global_val"
    assert cache.get("k", "agent-1") == "agent_val"
    print("OK: namespaces")


def test_ttl_expiration():
    """Entries expire after TTL."""
    cache = PipelineCache(default_ttl=3600.0)
    cache.set("fast", "data", ttl=0.01)
    assert cache.get("fast") == "data"

    time.sleep(0.02)
    assert cache.get("fast") is None
    print("OK: ttl expiration")


def test_has():
    """Check existence without counting as get."""
    cache = PipelineCache()
    cache.set("k", "v")
    assert cache.has("k") is True
    assert cache.has("missing") is False
    # has() should not increment gets
    assert cache.get_stats()["total_gets"] == 0
    print("OK: has")


def test_delete():
    """Delete specific entry."""
    cache = PipelineCache()
    cache.set("k", "v")
    assert cache.delete("k") is True
    assert cache.get("k") is None
    assert cache.delete("k") is False
    print("OK: delete")


def test_update():
    """Update existing key."""
    cache = PipelineCache()
    cache.set("k", "v1")
    cache.set("k", "v2")
    assert cache.get("k") == "v2"
    # Should have 1 entry, not 2
    assert cache.get_stats()["total_entries"] == 1
    print("OK: update")


def test_list_namespaces():
    """List namespaces with stats."""
    cache = PipelineCache()
    cache.set("a", "1", namespace="ns1")
    cache.set("b", "2", namespace="ns2")
    cache.set("c", "3", namespace="ns2")

    ns = cache.list_namespaces()
    assert len(ns) == 2
    ns1 = [n for n in ns if n["namespace"] == "ns1"][0]
    assert ns1["entry_count"] == 1
    ns2 = [n for n in ns if n["namespace"] == "ns2"][0]
    assert ns2["entry_count"] == 2
    print("OK: list namespaces")


def test_clear_namespace():
    """Clear all entries in a namespace."""
    cache = PipelineCache()
    cache.set("a", "1", namespace="temp")
    cache.set("b", "2", namespace="temp")
    cache.set("c", "3", namespace="keep")

    count = cache.clear_namespace("temp")
    assert count == 2
    assert cache.get("a", "temp") is None
    assert cache.get("c", "keep") == "3"
    assert cache.clear_namespace("nonexistent") == 0
    print("OK: clear namespace")


def test_list_keys():
    """List keys in a namespace."""
    cache = PipelineCache()
    cache.set("beta", "b")
    cache.set("alpha", "a")
    cache.set("gamma", "g")

    keys = cache.list_keys()
    assert len(keys) == 3
    assert cache.list_keys(namespace="missing") == []

    limited = cache.list_keys(limit=2)
    assert len(limited) == 2
    print("OK: list keys")


def test_tag_invalidation():
    """Invalidate by tag."""
    cache = PipelineCache()
    cache.set("a", "1", tags={"release", "v1"})
    cache.set("b", "2", tags={"debug"})
    cache.set("c", "3", tags={"release", "v2"})

    removed = cache.invalidate_by_tag("release")
    assert removed == 2
    assert cache.get("a") is None
    assert cache.get("b") == "2"
    assert cache.get("c") is None
    print("OK: tag invalidation")


def test_tags_invalidation():
    """Invalidate by multiple tags."""
    cache = PipelineCache()
    cache.set("a", "1", tags={"release"})
    cache.set("b", "2", tags={"debug"})
    cache.set("c", "3", tags={"test"})

    removed = cache.invalidate_by_tags({"release", "debug"})
    assert removed == 2
    assert cache.get("c") == "3"
    print("OK: tags invalidation")


def test_warm():
    """Bulk warm cache."""
    cache = PipelineCache()
    loaded = cache.warm([
        {"key": "a", "value": "1"},
        {"key": "b", "value": "2", "ttl": 60.0},
        {"key": "", "value": "skip"},  # Empty key skipped
    ], namespace="warm")

    assert loaded == 2
    assert cache.get("a", "warm") == "1"
    assert cache.get("b", "warm") == "2"
    print("OK: warm")


def test_get_multi():
    """Get multiple keys."""
    cache = PipelineCache()
    cache.set("a", "1")
    cache.set("b", "2")
    cache.set("c", "3")

    result = cache.get_multi(["a", "c", "missing"])
    assert result == {"a": "1", "c": "3"}
    print("OK: get multi")


def test_entry_info():
    """Get metadata about an entry."""
    cache = PipelineCache()
    cache.set("k", "hello", ttl=60.0, tags={"info"})

    info = cache.get_entry_info("k")
    assert info is not None
    assert info["key"] == "k"
    assert info["ttl"] == 60.0
    assert info["remaining_ttl"] > 0
    assert "info" in info["tags"]
    assert info["expired"] is False

    assert cache.get_entry_info("missing") is None
    print("OK: entry info")


def test_cleanup_expired():
    """Cleanup expired entries."""
    cache = PipelineCache()
    cache.set("fast", "x", ttl=0.01)
    cache.set("slow", "y", ttl=3600.0)

    time.sleep(0.02)
    removed = cache.cleanup_expired()
    assert removed == 1
    assert cache.get("slow") == "y"
    print("OK: cleanup expired")


def test_lru_eviction():
    """LRU eviction when over max entries."""
    cache = PipelineCache(max_entries=3, default_ttl=3600.0)
    cache.set("a", "1")
    cache.set("b", "2")
    cache.set("c", "3")

    # Access 'a' to make it recently used
    cache.get("a")

    # Adding 'd' should evict 'b' (least recently used)
    cache.set("d", "4")

    assert cache.get("a") is not None  # Recently accessed
    assert cache.get("c") is not None or cache.get("d") is not None
    stats = cache.get_stats()
    assert stats["total_evictions"] > 0
    assert stats["total_entries"] <= 3
    print("OK: lru eviction")


def test_size_limit_eviction():
    """Eviction when over max bytes."""
    cache = PipelineCache(max_bytes=100, default_ttl=3600.0)
    cache.set("a", "x" * 40, size_bytes=40)
    cache.set("b", "y" * 40, size_bytes=40)
    # Total = 80, under 100

    cache.set("c", "z" * 40, size_bytes=40)
    # Total would be 120, must evict

    stats = cache.get_stats()
    assert stats["total_bytes"] <= 100
    assert stats["total_evictions"] > 0
    print("OK: size limit eviction")


def test_hit_miss_stats():
    """Hit and miss statistics."""
    cache = PipelineCache()
    cache.set("k", "v")

    cache.get("k")  # Hit
    cache.get("k")  # Hit
    cache.get("missing")  # Miss

    stats = cache.get_stats()
    assert stats["total_hits"] == 2
    assert stats["total_misses"] == 1
    assert stats["hit_rate_percent"] > 0

    ns = cache.list_namespaces()
    assert ns[0]["hits"] == 2
    assert ns[0]["misses"] == 1
    print("OK: hit miss stats")


def test_content_hash():
    """Content hash for string/bytes values."""
    cache = PipelineCache()
    cache.set("k", "hello")
    info = cache.get_entry_info("k")
    assert info["content_hash"] != ""
    assert len(info["content_hash"]) == 16
    print("OK: content hash")


def test_stats():
    """Overall stats."""
    cache = PipelineCache()
    cache.set("a", "1")
    cache.set("b", "2")
    cache.get("a")

    stats = cache.get_stats()
    assert stats["total_sets"] == 2
    assert stats["total_gets"] == 1
    assert stats["total_entries"] == 2
    assert stats["total_namespaces"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    cache = PipelineCache()
    cache.set("a", "1")
    cache.set("b", "2", namespace="ns")

    cache.reset()
    assert cache.get("a") is None
    assert cache.list_namespaces() == []
    stats = cache.get_stats()
    assert stats["total_entries"] == 0
    assert stats["total_bytes"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Cache Tests ===\n")
    test_set_get()
    test_namespaces()
    test_ttl_expiration()
    test_has()
    test_delete()
    test_update()
    test_list_namespaces()
    test_clear_namespace()
    test_list_keys()
    test_tag_invalidation()
    test_tags_invalidation()
    test_warm()
    test_get_multi()
    test_entry_info()
    test_cleanup_expired()
    test_lru_eviction()
    test_size_limit_eviction()
    test_hit_miss_stats()
    test_content_hash()
    test_stats()
    test_reset()
    print("\n=== ALL 21 TESTS PASSED ===")


if __name__ == "__main__":
    main()
