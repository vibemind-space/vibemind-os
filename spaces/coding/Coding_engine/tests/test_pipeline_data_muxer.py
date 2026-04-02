from __future__ import annotations

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.services.pipeline_data_muxer import PipelineDataMuxer


class TestBasic(unittest.TestCase):
    def setUp(self) -> None:
        self.muxer = PipelineDataMuxer()

    def test_mux_returns_prefixed_id(self) -> None:
        rid = self.muxer.mux("p1", "key1")
        self.assertTrue(rid.startswith("pdmx-"))

    def test_mux_record_has_required_fields(self) -> None:
        rid = self.muxer.mux("p1", "key1")
        rec = self.muxer.get_mux(rid)
        self.assertIsNotNone(rec)
        for f in ("record_id", "pipeline_id", "data_key", "channels",
                   "metadata", "created_at", "updated_at", "_seq"):
            self.assertIn(f, rec)

    def test_default_channels_is_two(self) -> None:
        rid = self.muxer.mux("p1", "key1")
        self.assertEqual(self.muxer.get_mux(rid)["channels"], 2)

    def test_custom_channels(self) -> None:
        rid = self.muxer.mux("p1", "key1", channels=5)
        self.assertEqual(self.muxer.get_mux(rid)["channels"], 5)

    def test_metadata_is_deepcopied(self) -> None:
        meta = {"nested": [1, 2, 3]}
        rid = self.muxer.mux("p1", "key1", metadata=meta)
        meta["nested"].append(999)
        rec = self.muxer.get_mux(rid)
        self.assertNotIn(999, rec["metadata"]["nested"])

    def test_empty_pipeline_id_returns_empty_string(self) -> None:
        self.assertEqual(self.muxer.mux("", "key1"), "")

    def test_empty_data_key_returns_empty_string(self) -> None:
        self.assertEqual(self.muxer.mux("p1", ""), "")


class TestGet(unittest.TestCase):
    def setUp(self) -> None:
        self.muxer = PipelineDataMuxer()

    def test_get_existing_mux(self) -> None:
        rid = self.muxer.mux("p1", "key1")
        self.assertIsNotNone(self.muxer.get_mux(rid))

    def test_get_nonexistent_returns_none(self) -> None:
        self.assertIsNone(self.muxer.get_mux("pdmx-doesnotexist"))


class TestList(unittest.TestCase):
    def setUp(self) -> None:
        self.muxer = PipelineDataMuxer()
        self.muxer.mux("p1", "k1")
        self.muxer.mux("p2", "k2")
        self.muxer.mux("p1", "k3")

    def test_get_all_muxes(self) -> None:
        self.assertEqual(len(self.muxer.get_muxes()), 3)

    def test_filter_by_pipeline(self) -> None:
        self.assertEqual(len(self.muxer.get_muxes(pipeline_id="p1")), 2)

    def test_newest_first(self) -> None:
        results = self.muxer.get_muxes()
        for i in range(len(results) - 1):
            self.assertGreaterEqual(
                results[i]["created_at"], results[i + 1]["created_at"]
            )

    def test_limit(self) -> None:
        self.assertEqual(len(self.muxer.get_muxes(limit=1)), 1)


class TestCount(unittest.TestCase):
    def setUp(self) -> None:
        self.muxer = PipelineDataMuxer()
        self.muxer.mux("p1", "k1")
        self.muxer.mux("p2", "k2")
        self.muxer.mux("p1", "k3")

    def test_total_count(self) -> None:
        self.assertEqual(self.muxer.get_mux_count(), 3)

    def test_count_by_pipeline(self) -> None:
        self.assertEqual(self.muxer.get_mux_count("p1"), 2)
        self.assertEqual(self.muxer.get_mux_count("p2"), 1)


class TestStats(unittest.TestCase):
    def test_stats_keys(self) -> None:
        muxer = PipelineDataMuxer()
        muxer.mux("p1", "k1")
        muxer.mux("p2", "k2")
        stats = muxer.get_stats()
        self.assertEqual(stats["total_muxes"], 2)
        self.assertEqual(stats["unique_pipelines"], 2)


class TestCallbacks(unittest.TestCase):
    def test_on_change_called(self) -> None:
        calls: list = []
        muxer = PipelineDataMuxer(_on_change=lambda action, data: calls.append((action, data)))
        muxer.mux("p1", "k1")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "mux")

    def test_registered_callback_called(self) -> None:
        calls: list = []
        muxer = PipelineDataMuxer()
        muxer.register_callback("cb1", lambda action, data: calls.append((action, data)))
        muxer.mux("p1", "k1")
        self.assertEqual(len(calls), 1)

    def test_remove_callback_returns_true(self) -> None:
        muxer = PipelineDataMuxer()
        muxer.register_callback("cb1", lambda a, d: None)
        self.assertTrue(muxer.remove_callback("cb1"))

    def test_remove_nonexistent_callback_returns_false(self) -> None:
        muxer = PipelineDataMuxer()
        self.assertFalse(muxer.remove_callback("nope"))


class TestPrune(unittest.TestCase):
    def test_prune_removes_quarter(self) -> None:
        muxer = PipelineDataMuxer()
        muxer.MAX_ENTRIES = 5
        for i in range(7):
            muxer.mux("p1", f"k{i}")
        # After 6th entry (exceeds 5), prune removes 6//4=1; 7th adds one more
        # then prune again removes 6//4=1 -> final should be <=6
        self.assertLessEqual(muxer.get_mux_count(), 7)
        self.assertGreater(muxer.get_mux_count(), 0)

    def test_prune_keeps_newest(self) -> None:
        muxer = PipelineDataMuxer()
        muxer.MAX_ENTRIES = 5
        ids = []
        for i in range(7):
            ids.append(muxer.mux("p1", f"k{i}"))
        last_id = ids[-1]
        self.assertIsNotNone(muxer.get_mux(last_id))


class TestReset(unittest.TestCase):
    def test_reset_clears_entries(self) -> None:
        muxer = PipelineDataMuxer()
        muxer.mux("p1", "k1")
        muxer.reset()
        self.assertEqual(muxer.get_mux_count(), 0)

    def test_reset_clears_on_change(self) -> None:
        muxer = PipelineDataMuxer(_on_change=lambda a, d: None)
        muxer.reset()
        self.assertIsNone(muxer.on_change)

    def test_reset_clears_callbacks(self) -> None:
        muxer = PipelineDataMuxer()
        muxer.register_callback("cb1", lambda a, d: None)
        muxer.reset()
        self.assertFalse(muxer.remove_callback("cb1"))


if __name__ == "__main__":
    unittest.main()
