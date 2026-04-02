"""Tests for PipelineStepGuard."""

import sys
import unittest

sys.path.insert(0, ".")
from src.services.pipeline_step_guard import PipelineStepGuard, PipelineStepGuardState


class TestPipelineStepGuard(unittest.TestCase):

    def setUp(self):
        self.guard = PipelineStepGuard()

    def test_add_guard_returns_id_with_prefix(self):
        gid = self.guard.add_guard("pipe1", "step1")
        self.assertTrue(gid.startswith("psg-"))
        self.assertEqual(len(gid), 4 + 16)  # prefix + 16 hex chars

    def test_add_guard_field_present_pass(self):
        self.guard.add_guard("pipe1", "step1", "field_present", {"field": "name"})
        result = self.guard.check_guards("pipe1", "step1", {"name": "Alice"})
        self.assertTrue(result["passed"])
        self.assertEqual(result["failed_guards"], [])

    def test_add_guard_field_present_fail(self):
        self.guard.add_guard("pipe1", "step1", "field_present", {"field": "name"})
        result = self.guard.check_guards("pipe1", "step1", {"age": 30})
        self.assertFalse(result["passed"])
        self.assertEqual(len(result["failed_guards"]), 1)

    def test_field_value_guard(self):
        self.guard.add_guard("pipe1", "step1", "field_value", {"field": "status", "value": "ready"})
        self.assertTrue(self.guard.check_guards("pipe1", "step1", {"status": "ready"})["passed"])
        self.assertFalse(self.guard.check_guards("pipe1", "step1", {"status": "pending"})["passed"])

    def test_custom_guard(self):
        self.guard.add_guard("pipe1", "step1", "custom", {"fn": lambda ctx: ctx.get("x", 0) > 5})
        self.assertTrue(self.guard.check_guards("pipe1", "step1", {"x": 10})["passed"])
        self.assertFalse(self.guard.check_guards("pipe1", "step1", {"x": 2})["passed"])

    def test_remove_guard(self):
        gid = self.guard.add_guard("pipe1", "step1")
        self.assertTrue(self.guard.remove_guard(gid))
        self.assertFalse(self.guard.remove_guard(gid))
        self.assertIsNone(self.guard.get_guard(gid))

    def test_get_guards_filters(self):
        self.guard.add_guard("pipe1", "step1")
        self.guard.add_guard("pipe1", "step2")
        self.guard.add_guard("pipe2", "step1")
        self.assertEqual(len(self.guard.get_guards("pipe1")), 2)
        self.assertEqual(len(self.guard.get_guards("pipe1", "step1")), 1)
        self.assertEqual(len(self.guard.get_guards("pipe2")), 1)

    def test_get_guard_count(self):
        self.guard.add_guard("pipe1", "step1")
        self.guard.add_guard("pipe1", "step2")
        self.guard.add_guard("pipe2", "step1")
        self.assertEqual(self.guard.get_guard_count(), 3)
        self.assertEqual(self.guard.get_guard_count("pipe1"), 2)
        self.assertEqual(self.guard.get_guard_count("pipe2"), 1)

    def test_list_pipelines(self):
        self.guard.add_guard("pipe1", "step1")
        self.guard.add_guard("pipe2", "step1")
        pipelines = self.guard.list_pipelines()
        self.assertIn("pipe1", pipelines)
        self.assertIn("pipe2", pipelines)
        self.assertEqual(len(pipelines), 2)

    def test_get_stats(self):
        self.guard.add_guard("pipe1", "step1")
        self.guard.add_guard("pipe2", "step1")
        stats = self.guard.get_stats()
        self.assertEqual(stats["total_guards"], 2)
        self.assertEqual(stats["total_pipelines"], 2)
        self.assertGreater(stats["seq"], 0)

    def test_reset(self):
        self.guard.add_guard("pipe1", "step1")
        self.guard.reset()
        self.assertEqual(self.guard.get_guard_count(), 0)
        self.assertEqual(self.guard.list_pipelines(), [])

    def test_callbacks_and_on_change(self):
        events = []
        self.guard.on_change = lambda evt, data: events.append(evt)
        self.guard.callbacks["cb1"] = lambda evt, data: events.append(f"cb:{evt}")
        self.guard.add_guard("pipe1", "step1")
        self.assertIn("guard_added", events)
        self.assertIn("cb:guard_added", events)
        self.assertTrue(self.guard.remove_callback("cb1"))
        self.assertFalse(self.guard.remove_callback("cb1"))

    def test_unique_ids(self):
        id1 = self.guard.add_guard("pipe1", "step1")
        id2 = self.guard.add_guard("pipe1", "step1")
        self.assertNotEqual(id1, id2)

    def test_prune_max_entries(self):
        guard = PipelineStepGuard()
        guard.MAX_ENTRIES = 10
        for i in range(15):
            guard.add_guard(f"pipe{i}", "step1")
        self.assertLessEqual(len(guard.state.entries), 10)

    def test_custom_guard_exception(self):
        def bad_fn(ctx):
            raise ValueError("boom")
        self.guard.add_guard("pipe1", "step1", "custom", {"fn": bad_fn})
        result = self.guard.check_guards("pipe1", "step1", {})
        self.assertFalse(result["passed"])

    def test_state_dataclass(self):
        state = PipelineStepGuardState()
        self.assertEqual(state.entries, {})
        self.assertEqual(state._seq, 0)


if __name__ == "__main__":
    unittest.main()
