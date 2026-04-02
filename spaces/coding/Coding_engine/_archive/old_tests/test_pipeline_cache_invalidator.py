"""Test pipeline cache invalidator -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_cache_invalidator import PipelineCacheInvalidator


def test_register_cache():
    ci = PipelineCacheInvalidator()
    cid = ci.register_cache("pipeline-1", "transform_cache", ttl_seconds=300.0)
    assert len(cid) > 0
    assert cid.startswith("pci-")
    print("OK: register cache")


def test_is_valid():
    ci = PipelineCacheInvalidator()
    ci.register_cache("pipeline-1", "results", ttl_seconds=3600.0)
    assert ci.is_valid("pipeline-1", "results") is True
    print("OK: is valid")


def test_invalidate():
    ci = PipelineCacheInvalidator()
    ci.register_cache("pipeline-1", "results")
    assert ci.invalidate("pipeline-1", "results") is True
    assert ci.is_valid("pipeline-1", "results") is False
    print("OK: invalidate")


def test_get_cache():
    ci = PipelineCacheInvalidator()
    ci.register_cache("pipeline-1", "results", ttl_seconds=600.0)
    cache = ci.get_cache("pipeline-1", "results")
    assert cache is not None
    assert ci.get_cache("pipeline-1", "nonexistent") is None
    print("OK: get cache")


def test_invalidate_all():
    ci = PipelineCacheInvalidator()
    ci.register_cache("pipeline-1", "cache-a")
    ci.register_cache("pipeline-1", "cache-b")
    count = ci.invalidate_all("pipeline-1")
    assert count == 2
    print("OK: invalidate all")


def test_list_caches():
    ci = PipelineCacheInvalidator()
    ci.register_cache("pipeline-1", "a")
    ci.register_cache("pipeline-2", "b")
    caches = ci.list_caches()
    assert len(caches) >= 2
    print("OK: list caches")


def test_callbacks():
    ci = PipelineCacheInvalidator()
    fired = []
    ci.on_change("mon", lambda a, d: fired.append(a))
    ci.register_cache("pipeline-1", "test")
    assert len(fired) >= 1
    assert ci.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    ci = PipelineCacheInvalidator()
    ci.register_cache("pipeline-1", "test")
    stats = ci.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    ci = PipelineCacheInvalidator()
    ci.register_cache("pipeline-1", "test")
    ci.reset()
    assert ci.get_cache_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Cache Invalidator Tests ===\n")
    test_register_cache()
    test_is_valid()
    test_invalidate()
    test_get_cache()
    test_invalidate_all()
    test_list_caches()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 9 TESTS PASSED ===")


if __name__ == "__main__":
    main()
