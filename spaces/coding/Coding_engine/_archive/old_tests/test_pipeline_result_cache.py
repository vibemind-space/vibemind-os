"""Test pipeline result cache -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_result_cache import PipelineResultCache


def test_put_and_get():
    rc = PipelineResultCache()
    cid = rc.put("key1", {"result": 42}, ttl_seconds=300)
    assert len(cid) > 0
    val = rc.get("key1")
    assert val is not None
    assert val["result"] == 42
    print("OK: put and get")


def test_get_miss():
    rc = PipelineResultCache()
    val = rc.get("nonexistent")
    assert val is None
    print("OK: get miss")


def test_delete():
    rc = PipelineResultCache()
    rc.put("key1", "value1")
    assert rc.delete("key1") is True
    assert rc.delete("key1") is False
    assert rc.get("key1") is None
    print("OK: delete")


def test_has():
    rc = PipelineResultCache()
    rc.put("key1", "value1")
    assert rc.has("key1") is True
    assert rc.has("missing") is False
    print("OK: has")


def test_get_or_compute():
    rc = PipelineResultCache()
    call_count = [0]
    def compute():
        call_count[0] += 1
        return {"computed": True}
    val1 = rc.get_or_compute("expensive", compute, ttl_seconds=300)
    assert val1["computed"] is True
    assert call_count[0] == 1
    val2 = rc.get_or_compute("expensive", compute, ttl_seconds=300)
    assert val2["computed"] is True
    assert call_count[0] == 1  # should use cache
    print("OK: get or compute")


def test_clear():
    rc = PipelineResultCache()
    rc.put("k1", "v1", tags=["group_a"])
    rc.put("k2", "v2", tags=["group_b"])
    rc.put("k3", "v3", tags=["group_a"])
    count = rc.clear(tag="group_a")
    assert count >= 2
    assert rc.has("k2") is True
    print("OK: clear")


def test_cache_stats():
    rc = PipelineResultCache()
    rc.put("k1", "v1")
    rc.get("k1")  # hit
    rc.get("k1")  # hit
    rc.get("missing")  # miss
    stats = rc.get_cache_stats()
    assert stats["hits"] >= 2
    assert stats["misses"] >= 1
    print("OK: cache stats")


def test_list_keys():
    rc = PipelineResultCache()
    rc.put("k1", "v1", tags=["a"])
    rc.put("k2", "v2", tags=["b"])
    keys = rc.list_keys()
    assert "k1" in keys
    assert "k2" in keys
    tagged = rc.list_keys(tag="a")
    assert "k1" in tagged
    assert "k2" not in tagged
    print("OK: list keys")


def test_callbacks():
    rc = PipelineResultCache()
    fired = []
    rc.on_change("mon", lambda a, d: fired.append(a))
    rc.put("k1", "v1")
    assert len(fired) >= 1
    assert rc.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    rc = PipelineResultCache()
    rc.put("k1", "v1")
    stats = rc.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    rc = PipelineResultCache()
    rc.put("k1", "v1")
    rc.reset()
    assert rc.list_keys() == []
    print("OK: reset")


def main():
    print("=== Pipeline Result Cache Tests ===\n")
    test_put_and_get()
    test_get_miss()
    test_delete()
    test_has()
    test_get_or_compute()
    test_clear()
    test_cache_stats()
    test_list_keys()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
