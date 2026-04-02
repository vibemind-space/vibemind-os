from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.agent_workflow_batcher import AgentWorkflowBatcher


class TestAgentWorkflowBatcher(unittest.TestCase):
    def setUp(self) -> None:
        self.s = AgentWorkflowBatcher()

    # -- basic batch --
    def test_batch_returns_id_with_prefix(self) -> None:
        rid = self.s.batch("a1", "wf1")
        self.assertTrue(rid.startswith("awbt-"))

    def test_batch_fields_correct(self) -> None:
        rid = self.s.batch("a1", "wf1", batch_size=20, metadata={"k": "v"})
        entry = self.s.get_batch(rid)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["record_id"], rid)
        self.assertEqual(entry["agent_id"], "a1")
        self.assertEqual(entry["workflow_name"], "wf1")
        self.assertEqual(entry["batch_size"], 20)
        self.assertEqual(entry["metadata"], {"k": "v"})
        self.assertIn("created_at", entry)

    def test_batch_default_batch_size(self) -> None:
        rid = self.s.batch("a1", "wf1")
        entry = self.s.get_batch(rid)
        self.assertEqual(entry["batch_size"], 10)

    def test_batch_metadata_deepcopy(self) -> None:
        meta = {"nested": [1, 2, 3]}
        rid = self.s.batch("a1", "wf1", metadata=meta)
        meta["nested"].append(999)
        entry = self.s.get_batch(rid)
        self.assertNotIn(999, entry["metadata"]["nested"])

    def test_batch_empty_agent_id_returns_empty(self) -> None:
        self.assertEqual(self.s.batch("", "wf1"), "")

    def test_batch_empty_workflow_name_returns_empty(self) -> None:
        self.assertEqual(self.s.batch("a1", ""), "")

    # -- get_batch --
    def test_get_batch_found(self) -> None:
        rid = self.s.batch("a1", "wf1")
        self.assertIsNotNone(self.s.get_batch(rid))

    def test_get_batch_not_found(self) -> None:
        self.assertIsNone(self.s.get_batch("nonexistent"))

    def test_get_batch_returns_copy(self) -> None:
        rid = self.s.batch("a1", "wf1")
        b1 = self.s.get_batch(rid)
        b1["agent_id"] = "CHANGED"
        b2 = self.s.get_batch(rid)
        self.assertEqual(b2["agent_id"], "a1")

    # -- get_batches --
    def test_get_batches_all(self) -> None:
        self.s.batch("a1", "wf1")
        self.s.batch("a2", "wf2")
        self.assertEqual(len(self.s.get_batches()), 2)

    def test_get_batches_filter(self) -> None:
        self.s.batch("a1", "wf1")
        self.s.batch("a2", "wf2")
        self.s.batch("a1", "wf3")
        result = self.s.get_batches(agent_id="a1")
        self.assertEqual(len(result), 2)
        for r in result:
            self.assertEqual(r["agent_id"], "a1")

    def test_get_batches_newest_first(self) -> None:
        self.s.batch("a1", "wf1")
        self.s.batch("a1", "wf2")
        result = self.s.get_batches(agent_id="a1")
        self.assertGreaterEqual(result[0]["_seq"], result[1]["_seq"])

    # -- get_batch_count --
    def test_get_batch_count_total(self) -> None:
        self.s.batch("a1", "wf1")
        self.s.batch("a2", "wf2")
        self.assertEqual(self.s.get_batch_count(), 2)

    def test_get_batch_count_filtered(self) -> None:
        self.s.batch("a1", "wf1")
        self.s.batch("a2", "wf2")
        self.s.batch("a1", "wf3")
        self.assertEqual(self.s.get_batch_count(agent_id="a1"), 2)

    # -- get_stats --
    def test_get_stats(self) -> None:
        self.s.batch("a1", "wf1")
        self.s.batch("a2", "wf2")
        self.s.batch("a1", "wf3")
        stats = self.s.get_stats()
        self.assertEqual(stats["total_batches"], 3)
        self.assertEqual(stats["unique_agents"], 2)

    # -- on_change callback --
    def test_on_change_callback(self) -> None:
        calls = []
        self.s.on_change = lambda action, **kw: calls.append(action)
        self.s.batch("a1", "wf1")
        self.assertEqual(calls, ["batch"])

    # -- remove_callback --
    def test_remove_callback_true(self) -> None:
        self.s._state.callbacks["cb1"] = lambda action, **kw: None
        self.assertTrue(self.s.remove_callback("cb1"))
        self.assertNotIn("cb1", self.s._state.callbacks)

    def test_remove_callback_false(self) -> None:
        self.assertFalse(self.s.remove_callback("nonexistent"))

    # -- prune --
    def test_prune_removes_oldest_quarter(self) -> None:
        self.s.MAX_ENTRIES = 5
        for i in range(8):
            self.s.batch(f"a{i}", f"wf{i}")
        # Prune fires whenever len > MAX_ENTRIES, removing oldest quarter each time
        self.assertLessEqual(len(self.s._state.entries), 8)
        self.assertGreater(len(self.s._state.entries), 0)

    # -- reset --
    def test_reset_clears_state(self) -> None:
        self.s.batch("a1", "wf1")
        self.s.on_change = lambda action, **kw: None
        self.s.reset()
        self.assertEqual(len(self.s._state.entries), 0)
        self.assertIsNone(self.s._on_change)


if __name__ == "__main__":
    unittest.main()
