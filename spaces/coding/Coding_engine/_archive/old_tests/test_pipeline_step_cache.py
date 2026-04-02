"""Tests for PipelineStepCache service."""

import sys
import time
import unittest

sys.path.insert(0, ".")
from src.services.pipeline_step_cache import PipelineStepCache, PipelineStepCacheState


class TestPipelineStepCache(unittest.TestCase):
    """Tests for PipelineStepCache."""

    def setUp(self):
        self.cache = PipelineStepCache()

    def test_configure_returns_id_with_prefix(self):
        """Configure should return an ID with the pstc- prefix."""
        cache_id = self.cache.configure("pipeline-1", "step-a", ttl_seconds=60.0, max_size=50)
        self.assertTrue(cache_id.startswith("pstc-"))
        self.assertGreater(len(cache_id), len("pstc-"))

    def test_cache_and_retrieve_result(self):
        """Caching a result and retrieving it should return the same value."""
        self.cache.configure("p1", "s1", ttl_seconds=300.0)
        result = {"output": [1, 2, 3]}
        self.assertTrue(self.cache.cache_result("p1", "s1", "hash-abc", result))
        cached = self.cache.get_cached("p1", "s1", "hash-abc")
        self.assertEqual(cached, result)

    def test_get_cached_returns_none_for_missing(self):
        """Getting a non-existent cache entry should return None."""
        self.cache.configure("p1", "s1")
        self.assertIsNone(self.cache.get_cached("p1", "s1", "nonexistent"))

    def test_ttl_expiration(self):
        """Expired entries should not be returned."""
        self.cache.configure("p1", "s1", ttl_seconds=0.01)
        self.cache.cache_result("p1", "s1", "h1", "value")
        time.sleep(0.02)
        self.assertIsNone(self.cache.get_cached("p1", "s1", "h1"))

    def test_has_cached(self):
        """has_cached should reflect whether a valid entry exists."""
        self.cache.configure("p1", "s1")
        self.assertFalse(self.cache.has_cached("p1", "s1", "h1"))
        self.cache.cache_result("p1", "s1", "h1", "val")
        self.assertTrue(self.cache.has_cached("p1", "s1", "h1"))

    def test_invalidate_single_entry(self):
        """Invalidating a single entry should remove only that entry."""
        self.cache.configure("p1", "s1")
        self.cache.cache_result("p1", "s1", "h1", "v1")
        self.cache.cache_result("p1", "s1", "h2", "v2")
        count = self.cache.invalidate("p1", "s1", "h1")
        self.assertEqual(count, 1)
        self.assertIsNone(self.cache.get_cached("p1", "s1", "h1"))
        self.assertEqual(self.cache.get_cached("p1", "s1", "h2"), "v2")

    def test_invalidate_all_for_step(self):
        """Invalidating with empty hash should remove all entries for the step."""
        self.cache.configure("p1", "s1")
        self.cache.cache_result("p1", "s1", "h1", "v1")
        self.cache.cache_result("p1", "s1", "h2", "v2")
        count = self.cache.invalidate("p1", "s1")
        self.assertEqual(count, 2)
        self.assertEqual(self.cache.get_cache_count("p1"), 0)

    def test_get_cache_info(self):
        """get_cache_info should return hits, misses, size, hit_rate."""
        cache_id = self.cache.configure("p1", "s1")
        self.cache.cache_result("p1", "s1", "h1", "val")
        self.cache.get_cached("p1", "s1", "h1")  # hit
        self.cache.get_cached("p1", "s1", "h1")  # hit
        self.cache.get_cached("p1", "s1", "missing")  # miss
        info = self.cache.get_cache_info(cache_id)
        self.assertEqual(info["hits"], 2)
        self.assertEqual(info["misses"], 1)
        self.assertEqual(info["size"], 1)
        self.assertAlmostEqual(info["hit_rate"], 2 / 3, places=2)

    def test_get_cache_count(self):
        """get_cache_count should count entries, optionally by pipeline."""
        self.cache.configure("p1", "s1")
        self.cache.configure("p2", "s1")
        self.cache.cache_result("p1", "s1", "h1", "v1")
        self.cache.cache_result("p1", "s1", "h2", "v2")
        self.cache.cache_result("p2", "s1", "h1", "v3")
        self.assertEqual(self.cache.get_cache_count("p1"), 2)
        self.assertEqual(self.cache.get_cache_count("p2"), 1)
        self.assertEqual(self.cache.get_cache_count(), 3)

    def test_list_pipelines(self):
        """list_pipelines should return sorted unique pipeline IDs."""
        self.cache.configure("beta", "s1")
        self.cache.configure("alpha", "s1")
        self.cache.configure("alpha", "s2")
        pipelines = self.cache.list_pipelines()
        self.assertEqual(pipelines, ["alpha", "beta"])

    def test_callbacks(self):
        """on_change callbacks should fire on cache events."""
        events = []
        cb_id = self.cache.on_change(lambda evt, data: events.append(evt))
        self.assertTrue(cb_id.startswith("pstc-"))
        self.cache.configure("p1", "s1")
        self.cache.cache_result("p1", "s1", "h1", "v")
        self.cache.invalidate("p1", "s1", "h1")
        self.assertIn("configured", events)
        self.assertIn("cached", events)
        self.assertIn("invalidated", events)
        # Remove callback
        self.assertTrue(self.cache.remove_callback(cb_id))
        self.assertFalse(self.cache.remove_callback("nonexistent"))

    def test_get_stats(self):
        """get_stats should return overall statistics."""
        self.cache.configure("p1", "s1")
        self.cache.cache_result("p1", "s1", "h1", "v1")
        self.cache.get_cached("p1", "s1", "h1")
        stats = self.cache.get_stats()
        self.assertEqual(stats["total_entries"], 1)
        self.assertEqual(stats["total_configs"], 1)
        self.assertGreaterEqual(stats["total_hits"], 1)
        self.assertEqual(stats["pipelines"], 1)

    def test_reset(self):
        """reset should clear all state."""
        self.cache.configure("p1", "s1")
        self.cache.cache_result("p1", "s1", "h1", "v1")
        self.cache.reset()
        self.assertEqual(self.cache.get_cache_count(), 0)
        self.assertEqual(self.cache.list_pipelines(), [])

    def test_max_size_enforcement(self):
        """Configuring max_size should evict oldest entries when exceeded."""
        self.cache.configure("p1", "s1", max_size=3)
        for i in range(5):
            self.cache.cache_result("p1", "s1", f"h{i}", f"v{i}")
        # Should only have 3 entries for this step
        count = self.cache.get_cache_count("p1")
        self.assertLessEqual(count, 3)
        # Most recent should still be present
        self.assertEqual(self.cache.get_cached("p1", "s1", "h4"), "v4")

    def test_cache_without_configure(self):
        """Caching without prior configure should still work with defaults."""
        self.assertTrue(self.cache.cache_result("px", "sx", "hx", "vx"))
        self.assertEqual(self.cache.get_cached("px", "sx", "hx"), "vx")

    def test_dataclass_state(self):
        """PipelineStepCacheState should be a proper dataclass."""
        state = PipelineStepCacheState()
        self.assertIsInstance(state.entries, dict)
        self.assertEqual(state._seq, 0)


if __name__ == "__main__":
    unittest.main()
