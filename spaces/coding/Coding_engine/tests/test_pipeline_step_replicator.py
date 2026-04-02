from __future__ import annotations

import copy
import unittest
from unittest.mock import MagicMock

from src.services.pipeline_step_replicator import (
    PipelineStepReplicator,
    PipelineStepReplicatorState,
)


class TestBasic(unittest.TestCase):
    def setUp(self) -> None:
        self.rep = PipelineStepReplicator()

    def test_prefix(self) -> None:
        self.assertEqual(PipelineStepReplicator.PREFIX, "psrp-")

    def test_record_id_starts_with_prefix(self) -> None:
        rid = self.rep.replicate("p1", "step_a")
        self.assertTrue(rid.startswith("psrp-"))

    def test_fields_stored(self) -> None:
        rid = self.rep.replicate("p1", "step_a", replicas=3, metadata={"k": "v"})
        entry = self.rep.get_replication(rid)
        self.assertEqual(entry["pipeline_id"], "p1")
        self.assertEqual(entry["step_name"], "step_a")
        self.assertEqual(entry["replicas"], 3)
        self.assertEqual(entry["metadata"], {"k": "v"})
        self.assertIn("created_at", entry)

    def test_default_replicas_is_one(self) -> None:
        rid = self.rep.replicate("p1", "step_b")
        entry = self.rep.get_replication(rid)
        self.assertEqual(entry["replicas"], 1)

    def test_deepcopy_metadata(self) -> None:
        meta = {"nested": [1, 2]}
        rid = self.rep.replicate("p1", "step_c", metadata=meta)
        meta["nested"].append(3)
        entry = self.rep.get_replication(rid)
        self.assertEqual(entry["metadata"]["nested"], [1, 2])

    def test_empty_pipeline_id_returns_empty(self) -> None:
        self.assertEqual(self.rep.replicate("", "step_a"), "")

    def test_empty_step_name_returns_empty(self) -> None:
        self.assertEqual(self.rep.replicate("p1", ""), "")


class TestGet(unittest.TestCase):
    def setUp(self) -> None:
        self.rep = PipelineStepReplicator()

    def test_get_existing(self) -> None:
        rid = self.rep.replicate("p1", "s1")
        self.assertIsNotNone(self.rep.get_replication(rid))

    def test_get_missing_returns_none(self) -> None:
        self.assertIsNone(self.rep.get_replication("psrp-nonexistent"))

    def test_get_returns_deepcopy(self) -> None:
        rid = self.rep.replicate("p1", "s1", metadata={"x": 1})
        a = self.rep.get_replication(rid)
        b = self.rep.get_replication(rid)
        a["metadata"]["x"] = 999
        self.assertEqual(b["metadata"]["x"], 1)


class TestList(unittest.TestCase):
    def setUp(self) -> None:
        self.rep = PipelineStepReplicator()

    def test_filter_by_pipeline_id(self) -> None:
        self.rep.replicate("p1", "s1")
        self.rep.replicate("p2", "s2")
        self.rep.replicate("p1", "s3")
        result = self.rep.get_replications(pipeline_id="p1")
        self.assertEqual(len(result), 2)
        for r in result:
            self.assertEqual(r["pipeline_id"], "p1")

    def test_newest_first(self) -> None:
        self.rep.replicate("p1", "s1")
        self.rep.replicate("p1", "s2")
        self.rep.replicate("p1", "s3")
        result = self.rep.get_replications(pipeline_id="p1")
        seqs = [r["_seq"] for r in result]
        self.assertEqual(seqs, sorted(seqs, reverse=True))

    def test_limit(self) -> None:
        for i in range(10):
            self.rep.replicate("p1", f"s{i}")
        result = self.rep.get_replications(limit=3)
        self.assertEqual(len(result), 3)


class TestCount(unittest.TestCase):
    def setUp(self) -> None:
        self.rep = PipelineStepReplicator()

    def test_total_count(self) -> None:
        self.rep.replicate("p1", "s1")
        self.rep.replicate("p2", "s2")
        self.assertEqual(self.rep.get_replication_count(), 2)

    def test_count_by_pipeline(self) -> None:
        self.rep.replicate("p1", "s1")
        self.rep.replicate("p2", "s2")
        self.rep.replicate("p1", "s3")
        self.assertEqual(self.rep.get_replication_count(pipeline_id="p1"), 2)


class TestStats(unittest.TestCase):
    def test_stats(self) -> None:
        rep = PipelineStepReplicator()
        rep.replicate("p1", "s1")
        rep.replicate("p2", "s2")
        rep.replicate("p1", "s3")
        stats = rep.get_stats()
        self.assertEqual(stats["total_replications"], 3)
        self.assertEqual(stats["unique_pipelines"], 2)


class TestCallbacks(unittest.TestCase):
    def test_on_change_called(self) -> None:
        events = []
        cb = lambda action, data: events.append((action, data))
        rep = PipelineStepReplicator(_on_change=cb)
        rep.replicate("p1", "s1")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "replicate")
        self.assertIn("record_id", events[0][1])

    def test_state_callback_called(self) -> None:
        rep = PipelineStepReplicator()
        events = []
        rep._state.callbacks["my_cb"] = lambda action, data: events.append((action, data))
        rep.replicate("p1", "s1")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "replicate")


class TestPrune(unittest.TestCase):
    def test_prune_at_max(self) -> None:
        rep = PipelineStepReplicator()
        rep.MAX_ENTRIES = 5
        for i in range(7):
            rep.replicate("p1", f"step_{i}")
        self.assertEqual(len(rep._state.entries), 5)

    def test_prune_removes_oldest(self) -> None:
        rep = PipelineStepReplicator()
        rep.MAX_ENTRIES = 5
        ids = []
        for i in range(7):
            ids.append(rep.replicate("p1", f"step_{i}"))
        # The first two should have been pruned
        self.assertIsNone(rep.get_replication(ids[0]))
        self.assertIsNone(rep.get_replication(ids[1]))
        self.assertIsNotNone(rep.get_replication(ids[6]))


class TestReset(unittest.TestCase):
    def test_reset_clears_entries(self) -> None:
        rep = PipelineStepReplicator()
        rep.replicate("p1", "s1")
        rep.reset()
        self.assertEqual(rep.get_replication_count(), 0)

    def test_reset_clears_on_change(self) -> None:
        cb = lambda action, data: None
        rep = PipelineStepReplicator(_on_change=cb)
        rep.reset()
        self.assertIsNone(rep._on_change)


if __name__ == "__main__":
    unittest.main()
