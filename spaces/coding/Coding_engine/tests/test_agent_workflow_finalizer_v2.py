from __future__ import annotations

import time
import unittest

from src.services.agent_workflow_finalizer_v2 import (
    AgentWorkflowFinalizerV2,
    AgentWorkflowFinalizerV2State,
)


class TestBasic(unittest.TestCase):
    def setUp(self) -> None:
        self.fin = AgentWorkflowFinalizerV2()

    def test_prefix(self) -> None:
        rid = self.fin.finalize_v2("a1", "wf1")
        self.assertTrue(rid.startswith("awfv-"))

    def test_fields_stored(self) -> None:
        rid = self.fin.finalize_v2("a1", "wf1", metadata={"k": "v"})
        rec = self.fin.get_finalization(rid)
        self.assertIsNotNone(rec)
        self.assertEqual(rec["agent_id"], "a1")
        self.assertEqual(rec["workflow_name"], "wf1")
        self.assertEqual(rec["metadata"], {"k": "v"})
        self.assertIn("created_at", rec)
        self.assertIn("_seq", rec)

    def test_default_status_completed(self) -> None:
        rid = self.fin.finalize_v2("a1", "wf1")
        rec = self.fin.get_finalization(rid)
        self.assertEqual(rec["status"], "completed")

    def test_custom_status(self) -> None:
        rid = self.fin.finalize_v2("a1", "wf1", status="failed")
        rec = self.fin.get_finalization(rid)
        self.assertEqual(rec["status"], "failed")

    def test_deepcopy_metadata(self) -> None:
        meta = {"nested": [1, 2, 3]}
        rid = self.fin.finalize_v2("a1", "wf1", metadata=meta)
        meta["nested"].append(999)
        rec = self.fin.get_finalization(rid)
        self.assertNotIn(999, rec["metadata"]["nested"])

    def test_empty_agent_id_returns_empty(self) -> None:
        self.assertEqual(self.fin.finalize_v2("", "wf1"), "")

    def test_empty_workflow_returns_empty(self) -> None:
        self.assertEqual(self.fin.finalize_v2("a1", ""), "")


class TestGet(unittest.TestCase):
    def setUp(self) -> None:
        self.fin = AgentWorkflowFinalizerV2()

    def test_get_existing(self) -> None:
        rid = self.fin.finalize_v2("a1", "wf1")
        self.assertIsNotNone(self.fin.get_finalization(rid))

    def test_get_missing(self) -> None:
        self.assertIsNone(self.fin.get_finalization("nonexistent"))

    def test_get_returns_copy(self) -> None:
        rid = self.fin.finalize_v2("a1", "wf1")
        rec1 = self.fin.get_finalization(rid)
        rec2 = self.fin.get_finalization(rid)
        self.assertEqual(rec1, rec2)
        self.assertIsNot(rec1, rec2)


class TestList(unittest.TestCase):
    def setUp(self) -> None:
        self.fin = AgentWorkflowFinalizerV2()

    def test_filter_by_agent_id(self) -> None:
        self.fin.finalize_v2("a1", "wf1")
        self.fin.finalize_v2("a2", "wf2")
        self.fin.finalize_v2("a1", "wf3")
        results = self.fin.get_finalizations(agent_id="a1")
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertEqual(r["agent_id"], "a1")

    def test_newest_first(self) -> None:
        self.fin.finalize_v2("a1", "wf1")
        self.fin.finalize_v2("a1", "wf2")
        results = self.fin.get_finalizations(agent_id="a1")
        self.assertGreaterEqual(results[0]["_seq"], results[1]["_seq"])

    def test_limit(self) -> None:
        for i in range(10):
            self.fin.finalize_v2("a1", f"wf{i}")
        results = self.fin.get_finalizations(limit=3)
        self.assertEqual(len(results), 3)


class TestCount(unittest.TestCase):
    def test_total_count(self) -> None:
        fin = AgentWorkflowFinalizerV2()
        fin.finalize_v2("a1", "wf1")
        fin.finalize_v2("a2", "wf2")
        self.assertEqual(fin.get_finalization_count(), 2)

    def test_agent_count(self) -> None:
        fin = AgentWorkflowFinalizerV2()
        fin.finalize_v2("a1", "wf1")
        fin.finalize_v2("a2", "wf2")
        fin.finalize_v2("a1", "wf3")
        self.assertEqual(fin.get_finalization_count(agent_id="a1"), 2)


class TestStats(unittest.TestCase):
    def test_stats(self) -> None:
        fin = AgentWorkflowFinalizerV2()
        fin.finalize_v2("a1", "wf1")
        fin.finalize_v2("a2", "wf2")
        fin.finalize_v2("a1", "wf3")
        stats = fin.get_stats()
        self.assertEqual(stats["total_finalizations"], 3)
        self.assertEqual(stats["unique_agents"], 2)


class TestCallbacks(unittest.TestCase):
    def test_on_change_called(self) -> None:
        events = []
        fin = AgentWorkflowFinalizerV2(_on_change=lambda action, data: events.append((action, data)))
        fin.finalize_v2("a1", "wf1")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "finalize")
        self.assertIn("record_id", events[0][1])

    def test_registered_callback(self) -> None:
        events = []
        fin = AgentWorkflowFinalizerV2()
        fin._state.callbacks["cb1"] = lambda action, data: events.append((action, data))
        fin.finalize_v2("a1", "wf1")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "finalize")


class TestPrune(unittest.TestCase):
    def test_prune_at_max(self) -> None:
        fin = AgentWorkflowFinalizerV2()
        fin.MAX_ENTRIES = 5
        for i in range(7):
            fin.finalize_v2("a1", f"wf{i}")
        self.assertEqual(len(fin._state.entries), 5)

    def test_prune_keeps_newest(self) -> None:
        fin = AgentWorkflowFinalizerV2()
        fin.MAX_ENTRIES = 5
        rids = []
        for i in range(7):
            rids.append(fin.finalize_v2("a1", f"wf{i}"))
        # Oldest two should be pruned
        self.assertIsNone(fin.get_finalization(rids[0]))
        self.assertIsNone(fin.get_finalization(rids[1]))
        self.assertIsNotNone(fin.get_finalization(rids[6]))


class TestReset(unittest.TestCase):
    def test_reset_clears_state(self) -> None:
        fin = AgentWorkflowFinalizerV2(_on_change=lambda a, d: None)
        fin.finalize_v2("a1", "wf1")
        fin.reset()
        self.assertEqual(fin.get_finalization_count(), 0)
        self.assertIsNone(fin._on_change)

    def test_reset_allows_reuse(self) -> None:
        fin = AgentWorkflowFinalizerV2()
        fin.finalize_v2("a1", "wf1")
        fin.reset()
        rid = fin.finalize_v2("a2", "wf2")
        self.assertEqual(fin.get_finalization_count(), 1)
        rec = fin.get_finalization(rid)
        self.assertEqual(rec["agent_id"], "a2")


if __name__ == "__main__":
    unittest.main()
