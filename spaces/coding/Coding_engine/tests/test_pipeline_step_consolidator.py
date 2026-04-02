from __future__ import annotations

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "services"))

from pipeline_step_consolidator import PipelineStepConsolidator


class TestPipelineStepConsolidator(unittest.TestCase):

    def setUp(self) -> None:
        self.consolidator = PipelineStepConsolidator()

    # -- prefix --
    def test_prefix(self) -> None:
        rid = self.consolidator.consolidate("pipe-1", "step-a")
        self.assertTrue(rid.startswith("pscn-"))

    # -- fields --
    def test_fields_stored(self) -> None:
        rid = self.consolidator.consolidate("pipe-1", "step-a", target="gpu", metadata={"k": "v"})
        entry = self.consolidator.get_consolidation(rid)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["record_id"], rid)
        self.assertEqual(entry["pipeline_id"], "pipe-1")
        self.assertEqual(entry["step_name"], "step-a")
        self.assertEqual(entry["target"], "gpu")
        self.assertEqual(entry["metadata"], {"k": "v"})
        self.assertIn("created_at", entry)
        self.assertIn("_seq", entry)

    # -- default target --
    def test_default_target(self) -> None:
        rid = self.consolidator.consolidate("pipe-1", "step-a")
        entry = self.consolidator.get_consolidation(rid)
        self.assertEqual(entry["target"], "default")

    # -- deepcopy metadata --
    def test_metadata_deepcopy(self) -> None:
        meta = {"nested": {"x": 1}}
        rid = self.consolidator.consolidate("pipe-1", "step-a", metadata=meta)
        meta["nested"]["x"] = 999
        entry = self.consolidator.get_consolidation(rid)
        self.assertEqual(entry["metadata"]["nested"]["x"], 1)

    # -- empty returns "" --
    def test_empty_pipeline_id_returns_empty(self) -> None:
        self.assertEqual(self.consolidator.consolidate("", "step-a"), "")

    def test_empty_step_name_returns_empty(self) -> None:
        self.assertEqual(self.consolidator.consolidate("pipe-1", ""), "")

    # -- get found / not found / copy --
    def test_get_consolidation_found(self) -> None:
        rid = self.consolidator.consolidate("pipe-1", "step-a")
        self.assertIsNotNone(self.consolidator.get_consolidation(rid))

    def test_get_consolidation_not_found(self) -> None:
        self.assertIsNone(self.consolidator.get_consolidation("nonexistent"))

    def test_get_consolidation_returns_copy(self) -> None:
        rid = self.consolidator.consolidate("pipe-1", "step-a", metadata={"a": 1})
        copy1 = self.consolidator.get_consolidation(rid)
        copy2 = self.consolidator.get_consolidation(rid)
        self.assertEqual(copy1, copy2)
        copy1["pipeline_id"] = "mutated"
        copy3 = self.consolidator.get_consolidation(rid)
        self.assertEqual(copy3["pipeline_id"], "pipe-1")

    # -- list --
    def test_get_consolidations_all(self) -> None:
        self.consolidator.consolidate("pipe-1", "s1")
        self.consolidator.consolidate("pipe-2", "s2")
        self.consolidator.consolidate("pipe-1", "s3")
        results = self.consolidator.get_consolidations()
        self.assertEqual(len(results), 3)
        # sorted desc by _seq
        seqs = [r["_seq"] for r in results]
        self.assertEqual(seqs, sorted(seqs, reverse=True))

    def test_get_consolidations_filtered(self) -> None:
        self.consolidator.consolidate("pipe-1", "s1")
        self.consolidator.consolidate("pipe-2", "s2")
        self.consolidator.consolidate("pipe-1", "s3")
        results = self.consolidator.get_consolidations(pipeline_id="pipe-1")
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertEqual(r["pipeline_id"], "pipe-1")

    def test_get_consolidations_limit(self) -> None:
        for i in range(10):
            self.consolidator.consolidate("pipe-1", f"s{i}")
        results = self.consolidator.get_consolidations(limit=3)
        self.assertEqual(len(results), 3)

    # -- count --
    def test_count_all(self) -> None:
        self.consolidator.consolidate("pipe-1", "s1")
        self.consolidator.consolidate("pipe-2", "s2")
        self.assertEqual(self.consolidator.get_consolidation_count(), 2)

    def test_count_filtered(self) -> None:
        self.consolidator.consolidate("pipe-1", "s1")
        self.consolidator.consolidate("pipe-2", "s2")
        self.consolidator.consolidate("pipe-1", "s3")
        self.assertEqual(self.consolidator.get_consolidation_count(pipeline_id="pipe-1"), 2)

    # -- stats --
    def test_stats(self) -> None:
        self.consolidator.consolidate("pipe-1", "s1")
        self.consolidator.consolidate("pipe-2", "s2")
        self.consolidator.consolidate("pipe-1", "s3")
        stats = self.consolidator.get_stats()
        self.assertEqual(stats["total_consolidations"], 3)
        self.assertEqual(stats["unique_pipelines"], 2)

    # -- callbacks --
    def test_on_change_called(self) -> None:
        calls = []
        self.consolidator.on_change = lambda: calls.append("changed")
        self.consolidator.consolidate("pipe-1", "s1")
        self.assertEqual(len(calls), 1)

    def test_registered_callback_called(self) -> None:
        calls = []
        self.consolidator._state.callbacks["cb1"] = lambda: calls.append("cb1")
        self.consolidator.consolidate("pipe-1", "s1")
        self.assertIn("cb1", calls)

    def test_remove_callback(self) -> None:
        self.consolidator._state.callbacks["cb1"] = lambda: None
        self.assertTrue(self.consolidator.remove_callback("cb1"))
        self.assertFalse(self.consolidator.remove_callback("cb1"))

    # -- prune --
    def test_prune(self) -> None:
        PipelineStepConsolidator.MAX_ENTRIES = 5
        try:
            for i in range(7):
                self.consolidator.consolidate(f"pipe-{i}", f"step-{i}")
            # after 6th entry (>5), prune removes 6//4=1; after 7th (>5 again if 6 remain), removes again
            self.assertLessEqual(len(self.consolidator._state.entries), 6)
        finally:
            PipelineStepConsolidator.MAX_ENTRIES = 10000

    # -- reset --
    def test_reset(self) -> None:
        self.consolidator.consolidate("pipe-1", "s1")
        self.consolidator.on_change = lambda: None
        self.consolidator.reset()
        self.assertEqual(len(self.consolidator._state.entries), 0)
        self.assertEqual(self.consolidator._state._seq, 0)
        self.assertIsNone(self.consolidator.on_change)


if __name__ == "__main__":
    unittest.main()
