from __future__ import annotations

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "services"))

from pipeline_data_previewer import PipelineDataPreviewer


class TestPipelineDataPreviewer(unittest.TestCase):
    def setUp(self) -> None:
        self.svc = PipelineDataPreviewer()

    # -- prefix --
    def test_prefix(self) -> None:
        rid = self.svc.preview("p1", "k1")
        self.assertTrue(rid.startswith("pdpv-"))

    # -- fields --
    def test_fields_stored(self) -> None:
        rid = self.svc.preview("p1", "k1", format="csv", metadata={"a": 1})
        entry = self.svc.get_preview(rid)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["record_id"], rid)
        self.assertEqual(entry["pipeline_id"], "p1")
        self.assertEqual(entry["data_key"], "k1")
        self.assertEqual(entry["format"], "csv")
        self.assertEqual(entry["metadata"], {"a": 1})
        self.assertIn("created_at", entry)
        self.assertIn("_seq", entry)

    # -- default format --
    def test_default_format_json(self) -> None:
        rid = self.svc.preview("p1", "k1")
        entry = self.svc.get_preview(rid)
        self.assertEqual(entry["format"], "json")

    # -- metadata deepcopy --
    def test_metadata_deepcopy(self) -> None:
        meta = {"x": [1, 2]}
        rid = self.svc.preview("p1", "k1", metadata=meta)
        meta["x"].append(3)
        entry = self.svc.get_preview(rid)
        self.assertEqual(entry["metadata"]["x"], [1, 2])

    # -- empty pipeline_id or data_key --
    def test_empty_pipeline_id_returns_empty(self) -> None:
        self.assertEqual(self.svc.preview("", "k1"), "")

    def test_empty_data_key_returns_empty(self) -> None:
        self.assertEqual(self.svc.preview("p1", ""), "")

    # -- get_preview found / not found / copy --
    def test_get_preview_found(self) -> None:
        rid = self.svc.preview("p1", "k1")
        self.assertIsNotNone(self.svc.get_preview(rid))

    def test_get_preview_not_found(self) -> None:
        self.assertIsNone(self.svc.get_preview("nonexistent"))

    def test_get_preview_returns_copy(self) -> None:
        rid = self.svc.preview("p1", "k1")
        a = self.svc.get_preview(rid)
        b = self.svc.get_preview(rid)
        self.assertEqual(a, b)
        a["pipeline_id"] = "modified"
        self.assertNotEqual(a["pipeline_id"], self.svc.get_preview(rid)["pipeline_id"])

    # -- get_previews: all / filter / newest first --
    def test_get_previews_all(self) -> None:
        self.svc.preview("p1", "k1")
        self.svc.preview("p2", "k2")
        results = self.svc.get_previews()
        self.assertEqual(len(results), 2)

    def test_get_previews_filter(self) -> None:
        self.svc.preview("p1", "k1")
        self.svc.preview("p2", "k2")
        self.svc.preview("p1", "k3")
        results = self.svc.get_previews(pipeline_id="p1")
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertEqual(r["pipeline_id"], "p1")

    def test_get_previews_newest_first(self) -> None:
        self.svc.preview("p1", "k1")
        self.svc.preview("p1", "k2")
        results = self.svc.get_previews(pipeline_id="p1")
        self.assertGreaterEqual(results[0]["_seq"], results[1]["_seq"])

    # -- count --
    def test_get_preview_count_all(self) -> None:
        self.svc.preview("p1", "k1")
        self.svc.preview("p2", "k2")
        self.assertEqual(self.svc.get_preview_count(), 2)

    def test_get_preview_count_filtered(self) -> None:
        self.svc.preview("p1", "k1")
        self.svc.preview("p2", "k2")
        self.svc.preview("p1", "k3")
        self.assertEqual(self.svc.get_preview_count("p1"), 2)

    # -- stats --
    def test_get_stats(self) -> None:
        self.svc.preview("p1", "k1")
        self.svc.preview("p2", "k2")
        self.svc.preview("p1", "k3")
        stats = self.svc.get_stats()
        self.assertEqual(stats["total_previews"], 3)
        self.assertEqual(stats["unique_pipelines"], 2)

    # -- on_change callback --
    def test_on_change_callback(self) -> None:
        events = []
        self.svc.on_change = lambda e: events.append(e)
        self.svc.preview("p1", "k1")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["action"], "preview")

    # -- remove_callback --
    def test_remove_callback_true(self) -> None:
        self.svc._state.callbacks["cb1"] = lambda e: None
        self.assertTrue(self.svc.remove_callback("cb1"))
        self.assertNotIn("cb1", self.svc._state.callbacks)

    def test_remove_callback_false(self) -> None:
        self.assertFalse(self.svc.remove_callback("nonexistent"))

    # -- prune --
    def test_prune(self) -> None:
        PipelineDataPreviewer.MAX_ENTRIES = 5
        try:
            for i in range(8):
                self.svc.preview("p1", f"k{i}")
            self.assertEqual(self.svc.get_preview_count(), 5)
        finally:
            PipelineDataPreviewer.MAX_ENTRIES = 10000

    # -- reset --
    def test_reset_clears_entries(self) -> None:
        self.svc.preview("p1", "k1")
        self.svc.on_change = lambda e: None
        self.svc.reset()
        self.assertEqual(self.svc.get_preview_count(), 0)
        self.assertIsNone(self.svc.on_change)

    def test_reset_seq_zero(self) -> None:
        self.svc.preview("p1", "k1")
        self.svc.reset()
        self.assertEqual(self.svc._state._seq, 0)


if __name__ == "__main__":
    unittest.main()
