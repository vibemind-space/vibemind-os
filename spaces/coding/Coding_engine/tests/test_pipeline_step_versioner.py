from __future__ import annotations

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "services"))

from pipeline_step_versioner import PipelineStepVersioner, PipelineStepVersionerState


class TestPipelineStepVersioner(unittest.TestCase):
    def setUp(self) -> None:
        self.svc = PipelineStepVersioner()

    # --- prefix ---
    def test_prefix(self) -> None:
        rid = self.svc.version("pipe1", "step1")
        self.assertTrue(rid.startswith("psvn-"))

    # --- fields ---
    def test_fields(self) -> None:
        rid = self.svc.version("pipe1", "step1", version_tag="v2", metadata={"k": 1})
        rec = self.svc.get_version(rid)
        self.assertIsNotNone(rec)
        self.assertEqual(rec["record_id"], rid)
        self.assertEqual(rec["pipeline_id"], "pipe1")
        self.assertEqual(rec["step_name"], "step1")
        self.assertEqual(rec["version_tag"], "v2")
        self.assertEqual(rec["metadata"], {"k": 1})
        self.assertIn("created_at", rec)
        self.assertIn("_seq", rec)

    # --- default version_tag ---
    def test_default_version_tag(self) -> None:
        rid = self.svc.version("pipe1", "step1")
        rec = self.svc.get_version(rid)
        self.assertEqual(rec["version_tag"], "v1")

    # --- metadata deepcopy ---
    def test_metadata_deepcopy(self) -> None:
        meta = {"key": [1, 2]}
        rid = self.svc.version("pipe1", "step1", metadata=meta)
        meta["key"].append(3)
        rec = self.svc.get_version(rid)
        self.assertEqual(rec["metadata"]["key"], [1, 2])

    # --- empty returns "" ---
    def test_empty_pipeline_id(self) -> None:
        self.assertEqual(self.svc.version("", "step1"), "")

    def test_empty_step_name(self) -> None:
        self.assertEqual(self.svc.version("pipe1", ""), "")

    def test_both_empty(self) -> None:
        self.assertEqual(self.svc.version("", ""), "")

    # --- get_version found/not_found/copy ---
    def test_get_version_found(self) -> None:
        rid = self.svc.version("pipe1", "step1")
        self.assertIsNotNone(self.svc.get_version(rid))

    def test_get_version_not_found(self) -> None:
        self.assertIsNone(self.svc.get_version("nonexistent"))

    def test_get_version_returns_copy(self) -> None:
        rid = self.svc.version("pipe1", "step1", metadata={"x": 1})
        a = self.svc.get_version(rid)
        b = self.svc.get_version(rid)
        self.assertEqual(a, b)
        a["metadata"]["x"] = 999
        c = self.svc.get_version(rid)
        self.assertEqual(c["metadata"]["x"], 1)

    # --- get_versions: all, filter, newest_first ---
    def test_get_versions_all(self) -> None:
        self.svc.version("pipe1", "s1")
        self.svc.version("pipe2", "s2")
        results = self.svc.get_versions()
        self.assertEqual(len(results), 2)

    def test_get_versions_filter(self) -> None:
        self.svc.version("pipe1", "s1")
        self.svc.version("pipe2", "s2")
        self.svc.version("pipe1", "s3")
        results = self.svc.get_versions(pipeline_id="pipe1")
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertEqual(r["pipeline_id"], "pipe1")

    def test_get_versions_newest_first(self) -> None:
        r1 = self.svc.version("pipe1", "s1")
        r2 = self.svc.version("pipe1", "s2")
        results = self.svc.get_versions()
        self.assertEqual(results[0]["record_id"], r2)
        self.assertEqual(results[1]["record_id"], r1)

    # --- get_version_count ---
    def test_get_version_count_all(self) -> None:
        self.svc.version("pipe1", "s1")
        self.svc.version("pipe2", "s2")
        self.assertEqual(self.svc.get_version_count(), 2)

    def test_get_version_count_filtered(self) -> None:
        self.svc.version("pipe1", "s1")
        self.svc.version("pipe2", "s2")
        self.svc.version("pipe1", "s3")
        self.assertEqual(self.svc.get_version_count("pipe1"), 2)

    # --- get_stats ---
    def test_get_stats(self) -> None:
        self.svc.version("pipe1", "s1")
        self.svc.version("pipe2", "s2")
        self.svc.version("pipe1", "s3")
        stats = self.svc.get_stats()
        self.assertEqual(stats["total_versions"], 3)
        self.assertEqual(stats["unique_pipelines"], 2)

    # --- callbacks ---
    def test_on_change_callback(self) -> None:
        events = []
        self.svc.on_change = lambda e: events.append(e)
        self.svc.version("pipe1", "s1")
        self.assertEqual(events, ["version"])

    def test_named_callback(self) -> None:
        events = []
        self.svc._state.callbacks["cb1"] = lambda e: events.append(e)
        self.svc.version("pipe1", "s1")
        self.assertEqual(events, ["version"])

    def test_remove_callback_exists(self) -> None:
        self.svc._state.callbacks["cb1"] = lambda e: None
        self.assertTrue(self.svc.remove_callback("cb1"))
        self.assertNotIn("cb1", self.svc._state.callbacks)

    def test_remove_callback_missing(self) -> None:
        self.assertFalse(self.svc.remove_callback("nope"))

    # --- prune ---
    def test_prune(self) -> None:
        self.svc.MAX_ENTRIES = 5
        for i in range(8):
            self.svc.version("pipe1", f"step{i}")
        self.assertEqual(len(self.svc._state.entries), 5)

    # --- reset ---
    def test_reset(self) -> None:
        self.svc.on_change = lambda e: None
        self.svc.version("pipe1", "s1")
        self.svc.reset()
        self.assertEqual(len(self.svc._state.entries), 0)
        self.assertIsNone(self.svc._on_change)
        self.assertEqual(self.svc.get_version_count(), 0)


if __name__ == "__main__":
    unittest.main()
