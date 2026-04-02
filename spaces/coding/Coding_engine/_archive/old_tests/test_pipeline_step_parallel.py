"""Tests for PipelineStepParallel."""

import sys
import unittest

sys.path.insert(0, ".")
from src.services.pipeline_step_parallel import PipelineStepParallel


class TestPipelineStepParallel(unittest.TestCase):

    def setUp(self):
        self.psp = PipelineStepParallel()

    def test_create_group(self):
        gid = self.psp.create_group("pipe1", "group_a", ["s1", "s2"])
        self.assertTrue(gid.startswith("psp-"))
        group = self.psp.get_group(gid)
        self.assertIsNotNone(group)
        self.assertEqual(group["pipeline_id"], "pipe1")
        self.assertEqual(group["group_name"], "group_a")
        self.assertEqual(group["steps"], ["s1", "s2"])

    def test_create_group_no_steps(self):
        gid = self.psp.create_group("pipe1", "empty")
        group = self.psp.get_group(gid)
        self.assertEqual(group["steps"], [])

    def test_add_step(self):
        gid = self.psp.create_group("pipe1", "g1")
        self.assertTrue(self.psp.add_step(gid, "step_x"))
        group = self.psp.get_group(gid)
        self.assertIn("step_x", group["steps"])

    def test_add_step_duplicate(self):
        gid = self.psp.create_group("pipe1", "g1", ["s1"])
        self.assertFalse(self.psp.add_step(gid, "s1"))

    def test_add_step_invalid_group(self):
        self.assertFalse(self.psp.add_step("psp-nonexistent", "s1"))

    def test_remove_step(self):
        gid = self.psp.create_group("pipe1", "g1", ["s1", "s2"])
        self.assertTrue(self.psp.remove_step(gid, "s1"))
        group = self.psp.get_group(gid)
        self.assertNotIn("s1", group["steps"])
        self.assertIn("s2", group["steps"])

    def test_remove_step_not_found(self):
        gid = self.psp.create_group("pipe1", "g1")
        self.assertFalse(self.psp.remove_step(gid, "nope"))

    def test_execute_group_success(self):
        gid = self.psp.create_group("pipe1", "g1", ["add", "mul"])
        fns = {
            "add": lambda ctx: ctx["a"] + ctx["b"],
            "mul": lambda ctx: ctx["a"] * ctx["b"],
        }
        result = self.psp.execute_group(gid, context={"a": 3, "b": 4}, step_fns=fns)
        self.assertTrue(result["success"])
        self.assertEqual(result["results"]["add"], 7)
        self.assertEqual(result["results"]["mul"], 12)
        self.assertEqual(result["errors"], [])

    def test_execute_group_missing_fn(self):
        gid = self.psp.create_group("pipe1", "g1", ["s1"])
        result = self.psp.execute_group(gid, step_fns={})
        self.assertFalse(result["success"])
        self.assertIsNone(result["results"]["s1"])
        self.assertTrue(len(result["errors"]) > 0)

    def test_execute_group_step_error(self):
        gid = self.psp.create_group("pipe1", "g1", ["bad"])
        fns = {"bad": lambda ctx: 1 / 0}
        result = self.psp.execute_group(gid, step_fns=fns)
        self.assertFalse(result["success"])
        self.assertIsNone(result["results"]["bad"])

    def test_execute_group_not_found(self):
        result = self.psp.execute_group("psp-fake")
        self.assertFalse(result["success"])
        self.assertIn("Group not found", result["errors"])

    def test_get_groups_by_pipeline(self):
        self.psp.create_group("p1", "g1")
        self.psp.create_group("p1", "g2")
        self.psp.create_group("p2", "g3")
        groups = self.psp.get_groups("p1")
        self.assertEqual(len(groups), 2)

    def test_get_group_count(self):
        self.psp.create_group("p1", "g1")
        self.psp.create_group("p2", "g2")
        self.assertEqual(self.psp.get_group_count(), 2)
        self.assertEqual(self.psp.get_group_count("p1"), 1)

    def test_list_pipelines(self):
        self.psp.create_group("alpha", "g1")
        self.psp.create_group("beta", "g2")
        self.psp.create_group("alpha", "g3")
        pipelines = self.psp.list_pipelines()
        self.assertEqual(sorted(pipelines), ["alpha", "beta"])

    def test_get_group_none(self):
        self.assertIsNone(self.psp.get_group("psp-missing"))

    def test_callbacks(self):
        events = []
        cb_id = self.psp.on_change(lambda evt, data: events.append(evt))
        self.psp.create_group("p1", "g1")
        self.assertIn("group_created", events)
        self.assertTrue(self.psp.remove_callback(cb_id))
        self.assertFalse(self.psp.remove_callback(cb_id))

    def test_get_stats(self):
        self.psp.create_group("p1", "g1")
        stats = self.psp.get_stats()
        self.assertEqual(stats["total_groups"], 1)
        self.assertIn("uptime", stats)
        self.assertIn("seq", stats)

    def test_reset(self):
        self.psp.create_group("p1", "g1")
        self.psp.on_change(lambda e, d: None)
        self.psp.reset()
        self.assertEqual(self.psp.get_group_count(), 0)
        stats = self.psp.get_stats()
        self.assertEqual(stats["total_callbacks"], 0)

    def test_id_prefix(self):
        gid = self.psp.create_group("p1", "g1")
        self.assertTrue(gid.startswith("psp-"))
        self.assertEqual(len(gid), 4 + 16)  # "psp-" + 16 hex chars


if __name__ == "__main__":
    unittest.main()
