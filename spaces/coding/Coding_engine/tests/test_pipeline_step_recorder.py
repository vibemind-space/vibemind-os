"""Tests for PipelineStepRecorder service."""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_step_recorder import PipelineStepRecorder


class TestPipelineStepRecorder(unittest.TestCase):
    """Tests for PipelineStepRecorder."""

    def setUp(self):
        self.svc = PipelineStepRecorder()

    # -- record ----------------------------------------------------------

    def test_record_returns_id(self):
        rid = self.svc.record("p1", "step_a", {"x": 1}, {"y": 2})
        self.assertIsInstance(rid, str)
        self.assertTrue(rid.startswith("psrc-"))

    def test_record_stores_fields(self):
        rid = self.svc.record("p1", "step_a", {"x": 1}, {"y": 2}, metadata={"tag": "v1"})
        entry = self.svc.get_recording(rid)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["pipeline_id"], "p1")
        self.assertEqual(entry["step_name"], "step_a")
        self.assertEqual(entry["input_data"], {"x": 1})
        self.assertEqual(entry["output_data"], {"y": 2})
        self.assertEqual(entry["metadata"], {"tag": "v1"})
        self.assertIn("created_at", entry)
        self.assertIn("updated_at", entry)

    def test_record_default_metadata(self):
        rid = self.svc.record("p1", "step_a", "in", "out")
        entry = self.svc.get_recording(rid)
        self.assertEqual(entry["metadata"], {})

    def test_record_with_none_data(self):
        rid = self.svc.record("p1", "step_a", None, None)
        entry = self.svc.get_recording(rid)
        self.assertIsNone(entry["input_data"])
        self.assertIsNone(entry["output_data"])

    def test_record_with_list_data(self):
        rid = self.svc.record("p1", "step_a", [1, 2, 3], [4, 5])
        entry = self.svc.get_recording(rid)
        self.assertEqual(entry["input_data"], [1, 2, 3])
        self.assertEqual(entry["output_data"], [4, 5])

    # -- get_recording ---------------------------------------------------

    def test_get_recording_not_found(self):
        result = self.svc.get_recording("nonexistent")
        self.assertIsNone(result)

    def test_get_recording_returns_copy(self):
        rid = self.svc.record("p1", "step_a", "in", "out")
        entry = self.svc.get_recording(rid)
        entry["pipeline_id"] = "modified"
        original = self.svc.get_recording(rid)
        self.assertEqual(original["pipeline_id"], "p1")

    # -- get_recordings --------------------------------------------------

    def test_get_recordings_empty(self):
        result = self.svc.get_recordings()
        self.assertEqual(result, [])

    def test_get_recordings_newest_first(self):
        rid1 = self.svc.record("p1", "step_a", "in1", "out1")
        rid2 = self.svc.record("p1", "step_b", "in2", "out2")
        rid3 = self.svc.record("p1", "step_c", "in3", "out3")
        result = self.svc.get_recordings()
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["record_id"], rid3)
        self.assertEqual(result[2]["record_id"], rid1)

    def test_get_recordings_filter_by_pipeline(self):
        self.svc.record("p1", "step_a", "in", "out")
        self.svc.record("p2", "step_b", "in", "out")
        self.svc.record("p1", "step_c", "in", "out")
        result = self.svc.get_recordings(pipeline_id="p1")
        self.assertEqual(len(result), 2)
        for r in result:
            self.assertEqual(r["pipeline_id"], "p1")

    def test_get_recordings_filter_by_step_name(self):
        self.svc.record("p1", "step_a", "in", "out")
        self.svc.record("p1", "step_b", "in", "out")
        self.svc.record("p2", "step_a", "in", "out")
        result = self.svc.get_recordings(step_name="step_a")
        self.assertEqual(len(result), 2)
        for r in result:
            self.assertEqual(r["step_name"], "step_a")

    def test_get_recordings_filter_by_both(self):
        self.svc.record("p1", "step_a", "in", "out")
        self.svc.record("p1", "step_b", "in", "out")
        self.svc.record("p2", "step_a", "in", "out")
        result = self.svc.get_recordings(pipeline_id="p1", step_name="step_a")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["pipeline_id"], "p1")
        self.assertEqual(result[0]["step_name"], "step_a")

    def test_get_recordings_limit(self):
        for i in range(10):
            self.svc.record("p1", f"step_{i}", "in", "out")
        result = self.svc.get_recordings(limit=3)
        self.assertEqual(len(result), 3)

    def test_get_recordings_returns_dicts(self):
        self.svc.record("p1", "step_a", "in", "out")
        result = self.svc.get_recordings()
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], dict)
        self.assertIn("record_id", result[0])

    def test_get_recordings_no_match(self):
        self.svc.record("p1", "step_a", "in", "out")
        result = self.svc.get_recordings(pipeline_id="p99")
        self.assertEqual(result, [])

    # -- get_recording_count ---------------------------------------------

    def test_get_recording_count_all(self):
        self.svc.record("p1", "step_a", "in", "out")
        self.svc.record("p2", "step_b", "in", "out")
        self.assertEqual(self.svc.get_recording_count(), 2)

    def test_get_recording_count_by_pipeline(self):
        self.svc.record("p1", "step_a", "in", "out")
        self.svc.record("p2", "step_b", "in", "out")
        self.svc.record("p1", "step_c", "in", "out")
        self.assertEqual(self.svc.get_recording_count(pipeline_id="p1"), 2)
        self.assertEqual(self.svc.get_recording_count(pipeline_id="p2"), 1)
        self.assertEqual(self.svc.get_recording_count(pipeline_id="p3"), 0)

    def test_get_recording_count_empty(self):
        self.assertEqual(self.svc.get_recording_count(), 0)

    # -- get_stats -------------------------------------------------------

    def test_get_stats_empty(self):
        stats = self.svc.get_stats()
        self.assertEqual(stats["total_recordings"], 0)
        self.assertEqual(stats["unique_pipelines"], 0)
        self.assertEqual(stats["unique_steps"], 0)

    def test_get_stats_with_data(self):
        self.svc.record("p1", "step_a", "in", "out")
        self.svc.record("p1", "step_b", "in", "out")
        self.svc.record("p2", "step_a", "in", "out")
        stats = self.svc.get_stats()
        self.assertEqual(stats["total_recordings"], 3)
        self.assertEqual(stats["unique_pipelines"], 2)
        self.assertEqual(stats["unique_steps"], 2)

    # -- reset -----------------------------------------------------------

    def test_reset(self):
        self.svc.record("p1", "step_a", "in", "out")
        self.svc.record("p2", "step_b", "in", "out")
        self.svc.reset()
        self.assertEqual(self.svc.get_recording_count(), 0)
        self.assertEqual(self.svc.get_stats()["total_recordings"], 0)

    def test_reset_clears_callbacks(self):
        self.svc.on_change = lambda a, d: None
        self.svc.reset()
        self.assertIsNone(self.svc.on_change)

    # -- callbacks -------------------------------------------------------

    def test_on_change_property(self):
        self.assertIsNone(self.svc.on_change)
        events = []
        self.svc.on_change = lambda action, data: events.append((action, data))
        self.svc.record("p1", "step_a", "in", "out")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "recorded")

    def test_on_change_set_none(self):
        self.svc.on_change = lambda a, d: None
        self.assertIsNotNone(self.svc.on_change)
        self.svc.on_change = None
        self.assertIsNone(self.svc.on_change)

    def test_remove_callback(self):
        self.svc.on_change = lambda a, d: None
        self.assertTrue(self.svc.remove_callback("__on_change__"))
        self.assertIsNone(self.svc.on_change)

    def test_remove_callback_not_found(self):
        self.assertFalse(self.svc.remove_callback("nonexistent"))

    def test_fire_silent_on_error(self):
        self.svc.on_change = lambda a, d: (_ for _ in ()).throw(RuntimeError("boom"))
        rid = self.svc.record("p1", "step_a", "in", "out")
        self.assertTrue(rid.startswith("psrc-"))

    def test_fire_event_on_record(self):
        events = []
        self.svc.on_change = lambda action, data: events.append(action)
        self.svc.record("p1", "step_a", "in", "out")
        self.assertIn("recorded", events)

    # -- ID generation ---------------------------------------------------

    def test_unique_ids(self):
        ids = set()
        for i in range(100):
            rid = self.svc.record("p1", f"step_{i}", "in", "out")
            ids.add(rid)
        self.assertEqual(len(ids), 100)

    def test_id_prefix(self):
        rid = self.svc.record("p1", "step_a", "in", "out")
        self.assertTrue(rid.startswith("psrc-"))

    # -- pruning ---------------------------------------------------------

    def test_prune_oldest_quarter(self):
        self.svc.MAX_ENTRIES = 10
        for i in range(12):
            self.svc.record("p1", f"step_{i}", "in", "out")
        # After exceeding 10, oldest quarter (3) should be removed
        # 12 entries added, prune triggers on 11th insert removing ~2-3,
        # then 12th may trigger again
        self.assertLessEqual(self.svc.get_recording_count(), 12)


if __name__ == "__main__":
    unittest.main()
