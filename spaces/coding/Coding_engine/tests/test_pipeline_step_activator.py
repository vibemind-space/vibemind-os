from __future__ import annotations

import copy
import logging
import unittest

from src.services.pipeline_step_activator import (
    PipelineStepActivator,
    PipelineStepActivatorState,
)

logger = logging.getLogger(__name__)


class TestBasic(unittest.TestCase):
    def setUp(self) -> None:
        self.activator = PipelineStepActivator()

    def test_prefix_value(self) -> None:
        self.assertEqual(PipelineStepActivator.PREFIX, "psat-")

    def test_activate_returns_prefixed_id(self) -> None:
        rid = self.activator.activate("p1", "step1")
        self.assertTrue(rid.startswith("psat-"))

    def test_activate_stores_all_fields(self) -> None:
        rid = self.activator.activate("p1", "s1", mode="deferred", metadata={"k": "v"})
        entry = self.activator.get_activation(rid)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["pipeline_id"], "p1")
        self.assertEqual(entry["step_name"], "s1")
        self.assertEqual(entry["mode"], "deferred")
        self.assertEqual(entry["metadata"], {"k": "v"})
        self.assertIn("created_at", entry)
        self.assertIn("_seq", entry)

    def test_default_mode_is_immediate(self) -> None:
        rid = self.activator.activate("p1", "s1")
        entry = self.activator.get_activation(rid)
        self.assertEqual(entry["mode"], "immediate")

    def test_get_activation_returns_deepcopy(self) -> None:
        rid = self.activator.activate("p1", "s1", metadata={"x": [1, 2]})
        a = self.activator.get_activation(rid)
        b = self.activator.get_activation(rid)
        self.assertEqual(a, b)
        a["metadata"]["x"].append(3)
        b2 = self.activator.get_activation(rid)
        self.assertNotIn(3, b2["metadata"]["x"])

    def test_empty_pipeline_id_returns_empty_string(self) -> None:
        self.assertEqual(self.activator.activate("", "s1"), "")

    def test_empty_step_name_returns_empty_string(self) -> None:
        self.assertEqual(self.activator.activate("p1", ""), "")

    def test_metadata_defaults_to_empty_dict(self) -> None:
        rid = self.activator.activate("p1", "s1")
        entry = self.activator.get_activation(rid)
        self.assertEqual(entry["metadata"], {})


class TestGet(unittest.TestCase):
    def setUp(self) -> None:
        self.activator = PipelineStepActivator()

    def test_get_existing(self) -> None:
        rid = self.activator.activate("p1", "s1")
        self.assertIsNotNone(self.activator.get_activation(rid))

    def test_get_nonexistent_returns_none(self) -> None:
        self.assertIsNone(self.activator.get_activation("psat-doesnotexist"))

    def test_get_activation_record_id_matches(self) -> None:
        rid = self.activator.activate("px", "sy")
        entry = self.activator.get_activation(rid)
        self.assertEqual(entry["record_id"], rid)


class TestList(unittest.TestCase):
    def setUp(self) -> None:
        self.activator = PipelineStepActivator()
        self.ids = []
        for i in range(5):
            self.ids.append(self.activator.activate(f"p{i % 2}", f"s{i}"))

    def test_list_all(self) -> None:
        results = self.activator.get_activations()
        self.assertEqual(len(results), 5)

    def test_filter_by_pipeline_id(self) -> None:
        results = self.activator.get_activations(pipeline_id="p0")
        for r in results:
            self.assertEqual(r["pipeline_id"], "p0")

    def test_newest_first(self) -> None:
        results = self.activator.get_activations()
        seqs = [r["_seq"] for r in results]
        self.assertEqual(seqs, sorted(seqs, reverse=True))

    def test_limit(self) -> None:
        results = self.activator.get_activations(limit=2)
        self.assertEqual(len(results), 2)


class TestCount(unittest.TestCase):
    def setUp(self) -> None:
        self.activator = PipelineStepActivator()
        self.activator.activate("p1", "s1")
        self.activator.activate("p1", "s2")
        self.activator.activate("p2", "s3")

    def test_total_count(self) -> None:
        self.assertEqual(self.activator.get_activation_count(), 3)

    def test_count_by_pipeline(self) -> None:
        self.assertEqual(self.activator.get_activation_count(pipeline_id="p1"), 2)
        self.assertEqual(self.activator.get_activation_count(pipeline_id="p2"), 1)

    def test_count_unknown_pipeline(self) -> None:
        self.assertEqual(self.activator.get_activation_count(pipeline_id="nope"), 0)


class TestStats(unittest.TestCase):
    def test_stats_empty(self) -> None:
        a = PipelineStepActivator()
        stats = a.get_stats()
        self.assertEqual(stats["total_activations"], 0)
        self.assertEqual(stats["unique_pipelines"], 0)

    def test_stats_populated(self) -> None:
        a = PipelineStepActivator()
        a.activate("p1", "s1")
        a.activate("p1", "s2")
        a.activate("p2", "s3")
        stats = a.get_stats()
        self.assertEqual(stats["total_activations"], 3)
        self.assertEqual(stats["unique_pipelines"], 2)


class TestCallbacks(unittest.TestCase):
    def test_on_change_called(self) -> None:
        calls: list = []
        a = PipelineStepActivator(_on_change=lambda action, data: calls.append((action, data)))
        a.activate("p1", "s1")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "activate")
        self.assertIn("action", calls[0][1])

    def test_state_callback_called(self) -> None:
        calls: list = []
        a = PipelineStepActivator()
        a._state.callbacks["cb1"] = lambda action, data: calls.append((action, data))
        a.activate("p1", "s1")
        self.assertEqual(len(calls), 1)

    def test_both_callbacks_called(self) -> None:
        on_change_calls: list = []
        state_calls: list = []
        a = PipelineStepActivator(
            _on_change=lambda action, data: on_change_calls.append(1),
        )
        a._state.callbacks["x"] = lambda action, data: state_calls.append(1)
        a.activate("p1", "s1")
        self.assertEqual(len(on_change_calls), 1)
        self.assertEqual(len(state_calls), 1)

    def test_callback_receives_action_and_data(self) -> None:
        received: list = []
        a = PipelineStepActivator(_on_change=lambda action, data: received.append(data))
        a.activate("p1", "s1")
        self.assertEqual(received[0]["action"], "activate")
        self.assertEqual(received[0]["pipeline_id"], "p1")


class TestPrune(unittest.TestCase):
    def test_prune_removes_oldest(self) -> None:
        a = PipelineStepActivator()
        a.MAX_ENTRIES = 5
        rids = []
        for i in range(7):
            rids.append(a.activate(f"p{i}", f"s{i}"))
        self.assertEqual(len(a._state.entries), 5)
        # oldest two should be gone
        self.assertIsNone(a.get_activation(rids[0]))
        self.assertIsNone(a.get_activation(rids[1]))
        # newest should remain
        self.assertIsNotNone(a.get_activation(rids[6]))


class TestReset(unittest.TestCase):
    def test_reset_clears_entries(self) -> None:
        a = PipelineStepActivator()
        a.activate("p1", "s1")
        a.reset()
        self.assertEqual(a.get_activation_count(), 0)

    def test_reset_clears_on_change(self) -> None:
        a = PipelineStepActivator(_on_change=lambda action, data: None)
        a.reset()
        self.assertIsNone(a._on_change)

    def test_reset_clears_callbacks(self) -> None:
        a = PipelineStepActivator()
        a._state.callbacks["x"] = lambda action, data: None
        a.reset()
        self.assertEqual(len(a._state.callbacks), 0)

    def test_reset_fresh_state(self) -> None:
        a = PipelineStepActivator()
        a.activate("p1", "s1")
        a.reset()
        stats = a.get_stats()
        self.assertEqual(stats["total_activations"], 0)
        self.assertEqual(stats["unique_pipelines"], 0)


class TestDataclass(unittest.TestCase):
    def test_state_defaults(self) -> None:
        s = PipelineStepActivatorState()
        self.assertEqual(s.entries, {})
        self.assertEqual(s._seq, 0)
        self.assertEqual(s.callbacks, {})


if __name__ == "__main__":
    unittest.main()
