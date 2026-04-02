"""Tests for PipelineStepChain service."""

import sys
import unittest

sys.path.insert(0, ".")
from src.services.pipeline_step_chain import PipelineStepChain, PipelineStepChainState


class TestPipelineStepChain(unittest.TestCase):

    def setUp(self):
        self.psc = PipelineStepChain()

    def test_create_chain(self):
        chain_id = self.psc.create_chain("pipe1", "my_chain")
        self.assertTrue(chain_id.startswith("psc3-"))
        chain = self.psc.get_chain(chain_id)
        self.assertIsNotNone(chain)
        self.assertEqual(chain["pipeline_id"], "pipe1")
        self.assertEqual(chain["chain_name"], "my_chain")

    def test_add_step(self):
        chain_id = self.psc.create_chain("pipe1", "chain1")
        step_id = self.psc.add_step(chain_id, "step1", lambda x: x, order=1)
        self.assertTrue(step_id.startswith("psc3-"))
        chain = self.psc.get_chain(chain_id)
        self.assertEqual(len(chain["steps"]), 1)
        self.assertEqual(chain["steps"][0]["step_name"], "step1")

    def test_add_step_invalid_chain(self):
        with self.assertRaises(ValueError):
            self.psc.add_step("nonexistent", "step1")

    def test_execute_chain_passthrough(self):
        chain_id = self.psc.create_chain("pipe1", "chain1")
        self.psc.add_step(chain_id, "noop_step", None, order=0)
        result = self.psc.execute_chain(chain_id, initial_data={"key": "val"})
        self.assertTrue(result["success"])
        self.assertEqual(result["steps_executed"], 1)
        self.assertEqual(result["result"], {"key": "val"})
        self.assertEqual(result["errors"], [])

    def test_execute_chain_with_functions(self):
        chain_id = self.psc.create_chain("pipe1", "math_chain")
        self.psc.add_step(chain_id, "double", lambda x: x * 2, order=1)
        self.psc.add_step(chain_id, "add_ten", lambda x: x + 10, order=2)
        result = self.psc.execute_chain(chain_id, initial_data=5)
        self.assertTrue(result["success"])
        self.assertEqual(result["steps_executed"], 2)
        self.assertEqual(result["result"], 20)

    def test_execute_chain_step_order(self):
        chain_id = self.psc.create_chain("pipe1", "ordered")
        self.psc.add_step(chain_id, "last", lambda x: x + "_last", order=10)
        self.psc.add_step(chain_id, "first", lambda x: x + "_first", order=1)
        result = self.psc.execute_chain(chain_id, initial_data="start")
        self.assertTrue(result["success"])
        self.assertEqual(result["result"], "start_first_last")

    def test_execute_chain_with_error(self):
        chain_id = self.psc.create_chain("pipe1", "error_chain")
        self.psc.add_step(chain_id, "fail", lambda x: 1 / 0, order=1)
        self.psc.add_step(chain_id, "never", lambda x: x, order=2)
        result = self.psc.execute_chain(chain_id)
        self.assertFalse(result["success"])
        self.assertEqual(result["steps_executed"], 0)
        self.assertEqual(len(result["errors"]), 1)
        self.assertIn("fail", result["errors"][0])

    def test_execute_nonexistent_chain(self):
        result = self.psc.execute_chain("fake_id")
        self.assertFalse(result["success"])
        self.assertIn("Chain not found", result["errors"][0])

    def test_remove_chain(self):
        chain_id = self.psc.create_chain("pipe1", "to_remove")
        self.psc.add_step(chain_id, "s1", None, order=0)
        self.assertTrue(self.psc.remove_chain(chain_id))
        self.assertIsNone(self.psc.get_chain(chain_id))
        self.assertFalse(self.psc.remove_chain(chain_id))

    def test_get_chains_and_count(self):
        self.psc.create_chain("pipeA", "c1")
        self.psc.create_chain("pipeA", "c2")
        self.psc.create_chain("pipeB", "c3")
        self.assertEqual(len(self.psc.get_chains("pipeA")), 2)
        self.assertEqual(len(self.psc.get_chains("pipeB")), 1)
        self.assertEqual(self.psc.get_chain_count("pipeA"), 2)
        self.assertEqual(self.psc.get_chain_count(), 3)

    def test_list_pipelines(self):
        self.psc.create_chain("alpha", "c1")
        self.psc.create_chain("beta", "c2")
        self.psc.create_chain("alpha", "c3")
        pipelines = self.psc.list_pipelines()
        self.assertEqual(pipelines, ["alpha", "beta"])

    def test_callbacks(self):
        events = []
        self.psc.on_change("tracker", lambda a, d: events.append(a))
        self.psc.create_chain("p1", "c1")
        self.assertIn("create_chain", events)
        self.assertTrue(self.psc.remove_callback("tracker"))
        self.assertFalse(self.psc.remove_callback("tracker"))

    def test_get_stats(self):
        chain_id = self.psc.create_chain("p1", "c1")
        self.psc.add_step(chain_id, "s1", None)
        stats = self.psc.get_stats()
        self.assertEqual(stats["total_chains"], 1)
        self.assertEqual(stats["total_steps"], 1)
        self.assertIn("uptime", stats)

    def test_reset(self):
        self.psc.create_chain("p1", "c1")
        self.psc.on_change("cb1", lambda a, d: None)
        self.psc.reset()
        self.assertEqual(self.psc.get_chain_count(), 0)
        stats = self.psc.get_stats()
        self.assertEqual(stats["total_callbacks"], 0)

    def test_id_uniqueness(self):
        ids = set()
        for i in range(50):
            cid = self.psc.create_chain("p", f"chain_{i}")
            ids.add(cid)
        self.assertEqual(len(ids), 50)


if __name__ == "__main__":
    unittest.main()
