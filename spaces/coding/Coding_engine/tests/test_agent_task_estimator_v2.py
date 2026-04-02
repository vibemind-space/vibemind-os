from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "services"))

from agent_task_estimator_v2 import AgentTaskEstimatorV2, AgentTaskEstimatorV2State


class TestBasic(unittest.TestCase):
    def setUp(self) -> None:
        self.svc = AgentTaskEstimatorV2()

    def test_prefix(self) -> None:
        rid = self.svc.estimate_v2("t1", "a1")
        self.assertTrue(rid.startswith("atev-"))

    def test_fields_present(self) -> None:
        rid = self.svc.estimate_v2("t1", "a1", effort=2.5, metadata={"x": 1})
        rec = self.svc.get_estimate(rid)
        self.assertIsNotNone(rec)
        for key in ("record_id", "task_id", "agent_id", "effort", "metadata", "created_at", "updated_at", "_seq"):
            self.assertIn(key, rec)
        self.assertEqual(rec["task_id"], "t1")
        self.assertEqual(rec["agent_id"], "a1")
        self.assertEqual(rec["effort"], 2.5)
        self.assertEqual(rec["metadata"], {"x": 1})

    def test_default_effort(self) -> None:
        rid = self.svc.estimate_v2("t1", "a1")
        rec = self.svc.get_estimate(rid)
        self.assertEqual(rec["effort"], 1.0)

    def test_metadata_deepcopy(self) -> None:
        meta = {"key": [1, 2, 3]}
        rid = self.svc.estimate_v2("t1", "a1", metadata=meta)
        meta["key"].append(999)
        rec = self.svc.get_estimate(rid)
        self.assertEqual(rec["metadata"]["key"], [1, 2, 3])

    def test_empty_task_id(self) -> None:
        self.assertEqual(self.svc.estimate_v2("", "a1"), "")

    def test_empty_agent_id(self) -> None:
        self.assertEqual(self.svc.estimate_v2("t1", ""), "")

    def test_empty_both(self) -> None:
        self.assertEqual(self.svc.estimate_v2("", ""), "")


class TestGet(unittest.TestCase):
    def setUp(self) -> None:
        self.svc = AgentTaskEstimatorV2()

    def test_get_existing(self) -> None:
        rid = self.svc.estimate_v2("t1", "a1")
        rec = self.svc.get_estimate(rid)
        self.assertIsNotNone(rec)
        self.assertEqual(rec["record_id"], rid)

    def test_get_missing(self) -> None:
        self.assertIsNone(self.svc.get_estimate("nonexistent"))

    def test_get_returns_copy(self) -> None:
        rid = self.svc.estimate_v2("t1", "a1")
        rec = self.svc.get_estimate(rid)
        rec["effort"] = 999.0
        original = self.svc.get_estimate(rid)
        self.assertNotEqual(original["effort"], 999.0)


class TestList(unittest.TestCase):
    def setUp(self) -> None:
        self.svc = AgentTaskEstimatorV2()

    def test_list_all(self) -> None:
        self.svc.estimate_v2("t1", "a1")
        self.svc.estimate_v2("t2", "a2")
        results = self.svc.get_estimates()
        self.assertEqual(len(results), 2)

    def test_list_by_agent(self) -> None:
        self.svc.estimate_v2("t1", "a1")
        self.svc.estimate_v2("t2", "a2")
        self.svc.estimate_v2("t3", "a1")
        results = self.svc.get_estimates(agent_id="a1")
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertEqual(r["agent_id"], "a1")

    def test_list_newest_first(self) -> None:
        r1 = self.svc.estimate_v2("t1", "a1")
        r2 = self.svc.estimate_v2("t2", "a1")
        results = self.svc.get_estimates()
        self.assertEqual(results[0]["record_id"], r2)
        self.assertEqual(results[1]["record_id"], r1)

    def test_list_limit(self) -> None:
        for i in range(10):
            self.svc.estimate_v2(f"t{i}", "a1")
        results = self.svc.get_estimates(limit=3)
        self.assertEqual(len(results), 3)


class TestCount(unittest.TestCase):
    def setUp(self) -> None:
        self.svc = AgentTaskEstimatorV2()

    def test_count_all(self) -> None:
        self.svc.estimate_v2("t1", "a1")
        self.svc.estimate_v2("t2", "a2")
        self.assertEqual(self.svc.get_estimate_count(), 2)

    def test_count_by_agent(self) -> None:
        self.svc.estimate_v2("t1", "a1")
        self.svc.estimate_v2("t2", "a2")
        self.svc.estimate_v2("t3", "a1")
        self.assertEqual(self.svc.get_estimate_count(agent_id="a1"), 2)
        self.assertEqual(self.svc.get_estimate_count(agent_id="a2"), 1)

    def test_count_empty(self) -> None:
        self.assertEqual(self.svc.get_estimate_count(), 0)


class TestStats(unittest.TestCase):
    def setUp(self) -> None:
        self.svc = AgentTaskEstimatorV2()

    def test_stats_empty(self) -> None:
        stats = self.svc.get_stats()
        self.assertEqual(stats["total_estimates"], 0)
        self.assertEqual(stats["unique_agents"], 0)

    def test_stats_populated(self) -> None:
        self.svc.estimate_v2("t1", "a1")
        self.svc.estimate_v2("t2", "a2")
        self.svc.estimate_v2("t3", "a1")
        stats = self.svc.get_stats()
        self.assertEqual(stats["total_estimates"], 3)
        self.assertEqual(stats["unique_agents"], 2)


class TestCallbacks(unittest.TestCase):
    def setUp(self) -> None:
        self.svc = AgentTaskEstimatorV2()

    def test_on_change_fires(self) -> None:
        calls = []
        self.svc.on_change = lambda action, **kw: calls.append((action, kw))
        self.svc.estimate_v2("t1", "a1")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "estimate_v2")

    def test_on_change_property(self) -> None:
        fn = lambda action, **kw: None
        self.svc.on_change = fn
        self.assertIs(self.svc.on_change, fn)

    def test_named_callback(self) -> None:
        calls = []
        self.svc._state.callbacks["my_cb"] = lambda action, **kw: calls.append(action)
        self.svc.estimate_v2("t1", "a1")
        self.assertEqual(calls, ["estimate_v2"])

    def test_remove_callback(self) -> None:
        self.svc._state.callbacks["my_cb"] = lambda action, **kw: None
        self.assertTrue(self.svc.remove_callback("my_cb"))
        self.assertFalse(self.svc.remove_callback("my_cb"))

    def test_callback_error_does_not_crash(self) -> None:
        self.svc.on_change = lambda action, **kw: (_ for _ in ()).throw(RuntimeError("boom"))
        # Should not raise
        rid = self.svc.estimate_v2("t1", "a1")
        self.assertTrue(rid.startswith("atev-"))


class TestPrune(unittest.TestCase):
    def test_prune_removes_quarter(self) -> None:
        svc = AgentTaskEstimatorV2()
        svc.MAX_ENTRIES = 5
        for i in range(7):
            svc.estimate_v2(f"t{i}", "a1")
        # After adding 6th entry (exceeds 5), prune removes 6//4=1; then 7th may trigger again
        # Final count should be <= MAX + 1 at most, but pruning happens after each insert
        self.assertLessEqual(len(svc._state.entries), 7)
        # At least some were pruned
        self.assertLess(len(svc._state.entries), 7)

    def test_prune_keeps_newest(self) -> None:
        svc = AgentTaskEstimatorV2()
        svc.MAX_ENTRIES = 5
        ids = []
        for i in range(8):
            ids.append(svc.estimate_v2(f"t{i}", "a1"))
        # The most recent entry should survive
        last = svc.get_estimate(ids[-1])
        self.assertIsNotNone(last)


class TestReset(unittest.TestCase):
    def test_reset_clears_entries(self) -> None:
        svc = AgentTaskEstimatorV2()
        svc.estimate_v2("t1", "a1")
        svc.reset()
        self.assertEqual(svc.get_estimate_count(), 0)

    def test_reset_clears_on_change(self) -> None:
        svc = AgentTaskEstimatorV2(on_change=lambda a, **k: None)
        svc.reset()
        self.assertIsNone(svc.on_change)

    def test_reset_clears_callbacks(self) -> None:
        svc = AgentTaskEstimatorV2()
        svc._state.callbacks["x"] = lambda a, **k: None
        svc.reset()
        self.assertEqual(len(svc._state.callbacks), 0)

    def test_reset_resets_seq(self) -> None:
        svc = AgentTaskEstimatorV2()
        svc.estimate_v2("t1", "a1")
        svc.reset()
        self.assertEqual(svc._state._seq, 0)


if __name__ == "__main__":
    unittest.main()
