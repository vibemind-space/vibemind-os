"""Tests for PipelineStepOrchestrator service."""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_step_orchestrator import PipelineStepOrchestrator


class TestBasic(unittest.TestCase):
    """Basic orchestration tests."""

    def setUp(self):
        self.svc = PipelineStepOrchestrator()

    def test_orchestrate_returns_id_with_prefix(self):
        rid = self.svc.orchestrate("p1", "step_a")
        self.assertIsInstance(rid, str)
        self.assertTrue(rid.startswith("psor-"))

    def test_orchestrate_stores_fields(self):
        rid = self.svc.orchestrate("p1", "step_a", strategy="parallel", metadata={"k": "v"})
        entry = self.svc.get_orchestration(rid)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["record_id"], rid)
        self.assertEqual(entry["pipeline_id"], "p1")
        self.assertEqual(entry["step_name"], "step_a")
        self.assertEqual(entry["strategy"], "parallel")
        self.assertEqual(entry["metadata"], {"k": "v"})
        self.assertIn("created_at", entry)
        self.assertIn("updated_at", entry)
        self.assertIn("_seq", entry)

    def test_orchestrate_default_strategy_sequential(self):
        rid = self.svc.orchestrate("p1", "step_a")
        entry = self.svc.get_orchestration(rid)
        self.assertEqual(entry["strategy"], "sequential")

    def test_orchestrate_deepcopy_metadata(self):
        meta = {"nested": {"a": 1}}
        rid = self.svc.orchestrate("p1", "step_a", metadata=meta)
        meta["nested"]["a"] = 999
        entry = self.svc.get_orchestration(rid)
        self.assertEqual(entry["metadata"]["nested"]["a"], 1)

    def test_orchestrate_empty_pipeline_id_returns_empty(self):
        result = self.svc.orchestrate("", "step_a")
        self.assertEqual(result, "")

    def test_orchestrate_empty_step_name_returns_empty(self):
        result = self.svc.orchestrate("p1", "")
        self.assertEqual(result, "")

    def test_orchestrate_both_empty_returns_empty(self):
        result = self.svc.orchestrate("", "")
        self.assertEqual(result, "")

    def test_orchestrate_default_metadata_empty_dict(self):
        rid = self.svc.orchestrate("p1", "step_a")
        entry = self.svc.get_orchestration(rid)
        self.assertEqual(entry["metadata"], {})


class TestGet(unittest.TestCase):
    """Tests for get_orchestration."""

    def setUp(self):
        self.svc = PipelineStepOrchestrator()

    def test_get_orchestration_not_found(self):
        result = self.svc.get_orchestration("nonexistent")
        self.assertIsNone(result)

    def test_get_orchestration_returns_copy(self):
        rid = self.svc.orchestrate("p1", "step_a")
        entry = self.svc.get_orchestration(rid)
        entry["pipeline_id"] = "modified"
        original = self.svc.get_orchestration(rid)
        self.assertEqual(original["pipeline_id"], "p1")

    def test_get_orchestration_has_all_keys(self):
        rid = self.svc.orchestrate("p1", "step_a")
        entry = self.svc.get_orchestration(rid)
        expected_keys = {"record_id", "pipeline_id", "step_name", "strategy",
                         "metadata", "created_at", "updated_at", "_seq"}
        self.assertTrue(expected_keys.issubset(set(entry.keys())))


class TestList(unittest.TestCase):
    """Tests for get_orchestrations."""

    def setUp(self):
        self.svc = PipelineStepOrchestrator()

    def test_get_orchestrations_empty(self):
        result = self.svc.get_orchestrations()
        self.assertEqual(result, [])

    def test_get_orchestrations_newest_first(self):
        rid1 = self.svc.orchestrate("p1", "step_a")
        rid2 = self.svc.orchestrate("p1", "step_b")
        rid3 = self.svc.orchestrate("p1", "step_c")
        result = self.svc.get_orchestrations()
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["record_id"], rid3)
        self.assertEqual(result[2]["record_id"], rid1)

    def test_get_orchestrations_filter_pipeline_id(self):
        self.svc.orchestrate("p1", "step_a")
        self.svc.orchestrate("p2", "step_b")
        self.svc.orchestrate("p1", "step_c")
        result = self.svc.get_orchestrations(pipeline_id="p1")
        self.assertEqual(len(result), 2)
        for r in result:
            self.assertEqual(r["pipeline_id"], "p1")

    def test_get_orchestrations_limit(self):
        for i in range(10):
            self.svc.orchestrate("p1", f"step_{i}")
        result = self.svc.get_orchestrations(limit=3)
        self.assertEqual(len(result), 3)

    def test_get_orchestrations_no_match(self):
        self.svc.orchestrate("p1", "step_a")
        result = self.svc.get_orchestrations(pipeline_id="p99")
        self.assertEqual(result, [])

    def test_get_orchestrations_returns_dicts(self):
        self.svc.orchestrate("p1", "step_a")
        result = self.svc.get_orchestrations()
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], dict)


class TestCount(unittest.TestCase):
    """Tests for get_orchestration_count."""

    def setUp(self):
        self.svc = PipelineStepOrchestrator()

    def test_count_all(self):
        self.svc.orchestrate("p1", "step_a")
        self.svc.orchestrate("p2", "step_b")
        self.assertEqual(self.svc.get_orchestration_count(), 2)

    def test_count_by_pipeline(self):
        self.svc.orchestrate("p1", "step_a")
        self.svc.orchestrate("p2", "step_b")
        self.svc.orchestrate("p1", "step_c")
        self.assertEqual(self.svc.get_orchestration_count(pipeline_id="p1"), 2)
        self.assertEqual(self.svc.get_orchestration_count(pipeline_id="p2"), 1)
        self.assertEqual(self.svc.get_orchestration_count(pipeline_id="p3"), 0)

    def test_count_empty(self):
        self.assertEqual(self.svc.get_orchestration_count(), 0)


class TestStats(unittest.TestCase):
    """Tests for get_stats."""

    def setUp(self):
        self.svc = PipelineStepOrchestrator()

    def test_stats_empty(self):
        stats = self.svc.get_stats()
        self.assertEqual(stats["total_orchestrations"], 0)
        self.assertEqual(stats["unique_pipelines"], 0)

    def test_stats_with_data(self):
        self.svc.orchestrate("p1", "step_a")
        self.svc.orchestrate("p1", "step_b")
        self.svc.orchestrate("p2", "step_a")
        stats = self.svc.get_stats()
        self.assertEqual(stats["total_orchestrations"], 3)
        self.assertEqual(stats["unique_pipelines"], 2)


class TestCallbacks(unittest.TestCase):
    """Tests for callback functionality."""

    def setUp(self):
        self.svc = PipelineStepOrchestrator()

    def test_on_change_fires_on_orchestrate(self):
        events = []
        self.svc._on_change = lambda action, data: events.append((action, data))
        self.svc.orchestrate("p1", "step_a")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "orchestrated")
        self.assertIn("action", events[0][1])

    def test_on_change_none_by_default(self):
        self.assertIsNone(self.svc._on_change)

    def test_state_callback_fires(self):
        events = []
        self.svc._state.callbacks["test_cb"] = lambda action, data: events.append(action)
        self.svc.orchestrate("p1", "step_a")
        self.assertIn("orchestrated", events)

    def test_on_change_error_is_logged_not_raised(self):
        def bad_cb(action, data):
            raise RuntimeError("boom")
        self.svc._on_change = bad_cb
        rid = self.svc.orchestrate("p1", "step_a")
        self.assertTrue(rid.startswith("psor-"))

    def test_state_callback_error_is_logged_not_raised(self):
        def bad_cb(action, data):
            raise ValueError("fail")
        self.svc._state.callbacks["bad"] = bad_cb
        rid = self.svc.orchestrate("p1", "step_a")
        self.assertTrue(rid.startswith("psor-"))

    def test_both_on_change_and_state_callback_fire(self):
        events_a = []
        events_b = []
        self.svc._on_change = lambda action, data: events_a.append(action)
        self.svc._state.callbacks["cb1"] = lambda action, data: events_b.append(action)
        self.svc.orchestrate("p1", "step_a")
        self.assertEqual(len(events_a), 1)
        self.assertEqual(len(events_b), 1)


class TestPrune(unittest.TestCase):
    """Tests for pruning behavior."""

    def setUp(self):
        self.svc = PipelineStepOrchestrator()

    def test_prune_when_exceeding_max(self):
        self.svc.MAX_ENTRIES = 5
        for i in range(7):
            self.svc.orchestrate("p1", f"step_{i}")
        count = self.svc.get_orchestration_count()
        self.assertLessEqual(count, 7)
        self.assertGreater(count, 0)

    def test_prune_removes_oldest(self):
        self.svc.MAX_ENTRIES = 5
        first_rid = self.svc.orchestrate("p1", "step_first")
        for i in range(6):
            self.svc.orchestrate("p1", f"step_{i}")
        entry = self.svc.get_orchestration(first_rid)
        self.assertIsNone(entry)


class TestReset(unittest.TestCase):
    """Tests for reset."""

    def setUp(self):
        self.svc = PipelineStepOrchestrator()

    def test_reset_clears_entries(self):
        self.svc.orchestrate("p1", "step_a")
        self.svc.orchestrate("p2", "step_b")
        self.svc.reset()
        self.assertEqual(self.svc.get_orchestration_count(), 0)
        self.assertEqual(self.svc.get_stats()["total_orchestrations"], 0)

    def test_reset_clears_on_change(self):
        self.svc._on_change = lambda a, d: None
        self.svc.reset()
        self.assertIsNone(self.svc._on_change)

    def test_reset_clears_state_callbacks(self):
        self.svc._state.callbacks["cb1"] = lambda a, d: None
        self.svc.reset()
        self.assertEqual(len(self.svc._state.callbacks), 0)

    def test_reset_allows_new_orchestrations(self):
        self.svc.orchestrate("p1", "step_a")
        self.svc.reset()
        rid = self.svc.orchestrate("p2", "step_b")
        self.assertTrue(rid.startswith("psor-"))
        self.assertEqual(self.svc.get_orchestration_count(), 1)


class TestUniqueIds(unittest.TestCase):
    """Tests for ID uniqueness."""

    def setUp(self):
        self.svc = PipelineStepOrchestrator()

    def test_unique_ids(self):
        ids = set()
        for i in range(100):
            rid = self.svc.orchestrate("p1", f"step_{i}")
            ids.add(rid)
        self.assertEqual(len(ids), 100)


if __name__ == "__main__":
    unittest.main()
