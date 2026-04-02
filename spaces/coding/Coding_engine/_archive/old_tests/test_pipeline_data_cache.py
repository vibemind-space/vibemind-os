"""Test pipeline data cache."""
import sys
import time
sys.path.insert(0, ".")

from src.services.pipeline_data_cache import PipelineDataCache


def test_cache_set():
    cache = PipelineDataCache()
    entry_id = cache.cache_set("p1", "k1", "v1")
    assert entry_id.startswith("pdc-"), f"bad id: {entry_id}"
    assert cache.get_cache_size() == 1
    print("OK: cache_set")


def test_cache_get():
    cache = PipelineDataCache()
    cache.cache_set("p1", "k1", {"data": 42})
    assert cache.cache_get("p1", "k1") == {"data": 42}
    assert cache.cache_get("p1", "missing") is None
    assert cache.cache_get("p2", "k1") is None
    print("OK: cache_get")


def test_cache_has():
    cache = PipelineDataCache()
    cache.cache_set("p1", "k1", "v1")
    assert cache.cache_has("p1", "k1") is True
    assert cache.cache_has("p1", "missing") is False
    assert cache.cache_has("p2", "k1") is False
    print("OK: cache_has")


def test_cache_delete():
    cache = PipelineDataCache()
    cache.cache_set("p1", "k1", "v1")
    assert cache.cache_delete("p1", "k1") is True
    assert cache.cache_get("p1", "k1") is None
    assert cache.cache_delete("p1", "k1") is False
    print("OK: cache_delete")


def test_cache_clear():
    cache = PipelineDataCache()
    cache.cache_set("p1", "a", 1)
    cache.cache_set("p1", "b", 2)
    cache.cache_set("p2", "a", 3)
    cleared = cache.cache_clear("p1")
    assert cleared == 2
    assert cache.get_cache_size() == 1
    assert cache.cache_get("p2", "a") == 3
    print("OK: cache_clear")


def test_cache_ttl_expired():
    cache = PipelineDataCache()
    cache.cache_set("p1", "fast", "data", ttl_seconds=0.001)
    assert cache.cache_get("p1", "fast") == "data"
    time.sleep(0.01)
    assert cache.cache_get("p1", "fast") is None
    assert cache.cache_has("p1", "fast") is False
    print("OK: cache_ttl_expired")


def test_get_cache_size():
    cache = PipelineDataCache()
    assert cache.get_cache_size() == 0
    cache.cache_set("p1", "a", 1)
    cache.cache_set("p1", "b", 2)
    cache.cache_set("p2", "a", 3)
    assert cache.get_cache_size() == 3
    assert cache.get_cache_size("p1") == 2
    assert cache.get_cache_size("p2") == 1
    assert cache.get_cache_size("p3") == 0
    print("OK: get_cache_size")


def test_list_pipelines():
    cache = PipelineDataCache()
    assert cache.list_pipelines() == []
    cache.cache_set("p2", "a", 1)
    cache.cache_set("p1", "a", 2)
    assert cache.list_pipelines() == ["p1", "p2"]
    print("OK: list_pipelines")


def test_list_keys():
    cache = PipelineDataCache()
    cache.cache_set("p1", "b", 1)
    cache.cache_set("p1", "a", 2)
    cache.cache_set("p2", "c", 3)
    assert cache.list_keys("p1") == ["a", "b"]
    assert cache.list_keys("p2") == ["c"]
    assert cache.list_keys("p3") == []
    print("OK: list_keys")


def test_callbacks():
    cache = PipelineDataCache()
    events = []
    cache.on_change("test_cb", lambda action, detail: events.append((action, detail)))
    cache.cache_set("p1", "k1", "v1")
    assert len(events) == 1
    assert events[0][0] == "cache_set"
    cache.cache_delete("p1", "k1")
    assert len(events) == 2
    assert events[1][0] == "cache_delete"
    # duplicate name returns False
    assert cache.on_change("test_cb", lambda a, d: None) is False
    # remove
    assert cache.remove_callback("test_cb") is True
    assert cache.remove_callback("test_cb") is False
    print("OK: callbacks")


def test_stats():
    cache = PipelineDataCache()
    cache.cache_set("p1", "a", 1)
    cache.cache_set("p2", "b", 2)
    stats = cache.get_stats()
    assert stats["total_entries"] == 2
    assert stats["total_pipelines"] == 2
    print("OK: stats")


def test_reset():
    cache = PipelineDataCache()
    cache.cache_set("p1", "a", 1)
    cache.on_change("cb1", lambda a, d: None)
    cache.reset()
    assert cache.get_cache_size() == 0
    assert cache.list_pipelines() == []
    assert cache.get_stats()["total_entries"] == 0
    # callbacks cleared
    assert cache.on_change("cb1", lambda a, d: None) is True
    print("OK: reset")


def main():
    tests = [
        test_cache_set,
        test_cache_get,
        test_cache_has,
        test_cache_delete,
        test_cache_clear,
        test_cache_ttl_expired,
        test_get_cache_size,
        test_list_pipelines,
        test_list_keys,
        test_callbacks,
        test_stats,
        test_reset,
    ]
    for t in tests:
        t()
    print(f"=== ALL {len(tests)} TESTS PASSED ===")


if __name__ == "__main__":
    main()
