"""Tests for PipelineDataWindow service."""

import sys
import unittest

sys.path.insert(0, ".")
from src.services.pipeline_data_window import PipelineDataWindow


class TestPipelineDataWindow(unittest.TestCase):

    def setUp(self):
        self.pdw = PipelineDataWindow()

    def test_create_window_returns_id(self):
        wid = self.pdw.create_window("pipe-1")
        self.assertTrue(wid.startswith("pdw-"))

    def test_create_window_default_params(self):
        wid = self.pdw.create_window("pipe-1")
        w = self.pdw.get_window(wid)
        self.assertIsNotNone(w)
        self.assertEqual(w["window_type"], "sliding")
        self.assertEqual(w["size"], 10)
        self.assertEqual(w["slide"], 1)
        self.assertEqual(w["pipeline_id"], "pipe-1")

    def test_create_tumbling_window(self):
        wid = self.pdw.create_window("pipe-2", window_type="tumbling", size=3)
        w = self.pdw.get_window(wid)
        self.assertEqual(w["window_type"], "tumbling")
        self.assertEqual(w["size"], 3)

    def test_add_record_tumbling_completes(self):
        wid = self.pdw.create_window("pipe-1", window_type="tumbling", size=3)
        self.assertEqual(self.pdw.add_record(wid, "a"), [])
        self.assertEqual(self.pdw.add_record(wid, "b"), [])
        result = self.pdw.add_record(wid, "c")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], ["a", "b", "c"])
        # After completion, records should be empty
        self.assertEqual(self.pdw.get_current(wid), [])

    def test_add_record_sliding_completes(self):
        wid = self.pdw.create_window("pipe-1", window_type="sliding", size=3, slide=1)
        self.pdw.add_record(wid, "a")
        self.pdw.add_record(wid, "b")
        result = self.pdw.add_record(wid, "c")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], ["a", "b", "c"])
        # After slide=1, "a" should be removed, leaving ["b", "c"]
        self.assertEqual(self.pdw.get_current(wid), ["b", "c"])

    def test_add_record_nonexistent_window(self):
        result = self.pdw.add_record("pdw-nonexistent", "x")
        self.assertEqual(result, [])

    def test_get_current_empty(self):
        wid = self.pdw.create_window("pipe-1")
        self.assertEqual(self.pdw.get_current(wid), [])

    def test_get_window_not_found(self):
        self.assertIsNone(self.pdw.get_window("pdw-missing"))

    def test_get_windows_for_pipeline(self):
        self.pdw.create_window("pipe-a")
        self.pdw.create_window("pipe-a")
        self.pdw.create_window("pipe-b")
        self.assertEqual(len(self.pdw.get_windows("pipe-a")), 2)
        self.assertEqual(len(self.pdw.get_windows("pipe-b")), 1)
        self.assertEqual(len(self.pdw.get_windows("pipe-c")), 0)

    def test_get_window_count(self):
        self.pdw.create_window("pipe-a")
        self.pdw.create_window("pipe-b")
        self.pdw.create_window("pipe-b")
        self.assertEqual(self.pdw.get_window_count(), 3)
        self.assertEqual(self.pdw.get_window_count("pipe-a"), 1)
        self.assertEqual(self.pdw.get_window_count("pipe-b"), 2)
        self.assertEqual(self.pdw.get_window_count("pipe-z"), 0)

    def test_list_pipelines(self):
        self.pdw.create_window("pipe-x")
        self.pdw.create_window("pipe-y")
        self.pdw.create_window("pipe-x")
        pipelines = self.pdw.list_pipelines()
        self.assertIn("pipe-x", pipelines)
        self.assertIn("pipe-y", pipelines)
        self.assertEqual(len(pipelines), 2)

    def test_callbacks(self):
        events = []
        self.pdw.on_change("tracker", lambda action, detail: events.append((action, detail)))
        wid = self.pdw.create_window("pipe-1", window_type="tumbling", size=2)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "create_window")

        self.pdw.add_record(wid, "a")
        self.pdw.add_record(wid, "b")  # completes
        self.assertEqual(len(events), 2)
        self.assertEqual(events[1][0], "window_completed")

        self.assertTrue(self.pdw.remove_callback("tracker"))
        self.assertFalse(self.pdw.remove_callback("tracker"))

    def test_get_stats(self):
        self.pdw.create_window("pipe-1")
        self.pdw.create_window("pipe-2")
        stats = self.pdw.get_stats()
        self.assertEqual(stats["total_windows"], 2)
        self.assertEqual(stats["total_pipelines"], 2)
        self.assertGreater(stats["seq"], 0)

    def test_reset(self):
        self.pdw.create_window("pipe-1")
        self.pdw.on_change("cb1", lambda a, d: None)
        self.pdw.reset()
        self.assertEqual(self.pdw.get_window_count(), 0)
        self.assertEqual(self.pdw.get_stats()["callbacks"], 0)

    def test_unique_ids(self):
        ids = set()
        for i in range(20):
            wid = self.pdw.create_window(f"pipe-{i}")
            ids.add(wid)
        self.assertEqual(len(ids), 20)


if __name__ == "__main__":
    unittest.main()
