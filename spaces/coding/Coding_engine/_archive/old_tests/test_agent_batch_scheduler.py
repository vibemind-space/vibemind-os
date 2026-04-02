"""Tests for AgentBatchScheduler."""

import sys
import unittest

sys.path.insert(0, ".")
from src.services.agent_batch_scheduler import AgentBatchScheduler


class TestAgentBatchScheduler(unittest.TestCase):
    def setUp(self):
        self.scheduler = AgentBatchScheduler()

    def test_create_batch(self):
        batch_id = self.scheduler.create_batch("agent-1", [{"cmd": "a"}, {"cmd": "b"}])
        self.assertTrue(batch_id.startswith("abs-"))
        batch = self.scheduler.get_batch(batch_id)
        self.assertIsNotNone(batch)
        self.assertEqual(batch["status"], "pending")
        self.assertEqual(batch["agent_id"], "agent-1")
        self.assertEqual(len(batch["tasks"]), 2)

    def test_create_batch_with_priority(self):
        batch_id = self.scheduler.create_batch("agent-1", [{"x": 1}], priority=5)
        batch = self.scheduler.get_batch(batch_id)
        self.assertEqual(batch["priority"], 5)

    def test_start_batch(self):
        batch_id = self.scheduler.create_batch("agent-1", [{"x": 1}])
        self.assertTrue(self.scheduler.start_batch(batch_id))
        batch = self.scheduler.get_batch(batch_id)
        self.assertEqual(batch["status"], "running")
        self.assertIsNotNone(batch["started_at"])

    def test_start_batch_invalid(self):
        self.assertFalse(self.scheduler.start_batch("abs-nonexistent"))

    def test_start_batch_not_pending(self):
        batch_id = self.scheduler.create_batch("agent-1", [{"x": 1}])
        self.scheduler.start_batch(batch_id)
        self.assertFalse(self.scheduler.start_batch(batch_id))

    def test_complete_task(self):
        batch_id = self.scheduler.create_batch("agent-1", [{"x": 1}, {"x": 2}])
        self.scheduler.start_batch(batch_id)
        self.assertTrue(self.scheduler.complete_task(batch_id, 0, result="done"))
        batch = self.scheduler.get_batch(batch_id)
        self.assertTrue(batch["tasks"][0]["completed"])
        self.assertEqual(batch["tasks"][0]["result"], "done")
        self.assertFalse(batch["tasks"][1]["completed"])

    def test_complete_task_invalid_index(self):
        batch_id = self.scheduler.create_batch("agent-1", [{"x": 1}])
        self.assertFalse(self.scheduler.complete_task(batch_id, 5))

    def test_complete_task_already_completed(self):
        batch_id = self.scheduler.create_batch("agent-1", [{"x": 1}])
        self.scheduler.complete_task(batch_id, 0)
        self.assertFalse(self.scheduler.complete_task(batch_id, 0))

    def test_get_progress(self):
        batch_id = self.scheduler.create_batch("agent-1", [{"x": 1}, {"x": 2}, {"x": 3}, {"x": 4}])
        self.scheduler.complete_task(batch_id, 0)
        self.scheduler.complete_task(batch_id, 2)
        progress = self.scheduler.get_progress(batch_id)
        self.assertEqual(progress["total"], 4)
        self.assertEqual(progress["completed"], 2)
        self.assertEqual(progress["remaining"], 2)
        self.assertAlmostEqual(progress["percent"], 50.0)

    def test_get_progress_nonexistent(self):
        progress = self.scheduler.get_progress("abs-nope")
        self.assertEqual(progress["total"], 0)

    def test_complete_batch(self):
        batch_id = self.scheduler.create_batch("agent-1", [{"x": 1}])
        self.scheduler.start_batch(batch_id)
        self.assertTrue(self.scheduler.complete_batch(batch_id))
        batch = self.scheduler.get_batch(batch_id)
        self.assertEqual(batch["status"], "completed")
        self.assertIsNotNone(batch["completed_at"])

    def test_complete_batch_already_completed(self):
        batch_id = self.scheduler.create_batch("agent-1", [{"x": 1}])
        self.scheduler.complete_batch(batch_id)
        self.assertFalse(self.scheduler.complete_batch(batch_id))

    def test_get_batches_by_agent(self):
        self.scheduler.create_batch("agent-1", [{"x": 1}])
        self.scheduler.create_batch("agent-1", [{"x": 2}])
        self.scheduler.create_batch("agent-2", [{"x": 3}])
        batches = self.scheduler.get_batches("agent-1")
        self.assertEqual(len(batches), 2)

    def test_get_batches_by_status(self):
        b1 = self.scheduler.create_batch("agent-1", [{"x": 1}])
        self.scheduler.create_batch("agent-1", [{"x": 2}])
        self.scheduler.start_batch(b1)
        running = self.scheduler.get_batches("agent-1", status="running")
        self.assertEqual(len(running), 1)
        pending = self.scheduler.get_batches("agent-1", status="pending")
        self.assertEqual(len(pending), 1)

    def test_get_batch_count(self):
        self.scheduler.create_batch("agent-1", [{"x": 1}])
        self.scheduler.create_batch("agent-2", [{"x": 2}])
        self.assertEqual(self.scheduler.get_batch_count(), 2)
        self.assertEqual(self.scheduler.get_batch_count("agent-1"), 1)

    def test_list_agents(self):
        self.scheduler.create_batch("agent-b", [{"x": 1}])
        self.scheduler.create_batch("agent-a", [{"x": 2}])
        self.scheduler.create_batch("agent-b", [{"x": 3}])
        agents = self.scheduler.list_agents()
        self.assertEqual(agents, ["agent-a", "agent-b"])

    def test_get_stats(self):
        self.scheduler.create_batch("agent-1", [{"x": 1}])
        b2 = self.scheduler.create_batch("agent-1", [{"x": 2}])
        self.scheduler.start_batch(b2)
        stats = self.scheduler.get_stats()
        self.assertEqual(stats["total_batches"], 2)
        self.assertEqual(stats["by_status"]["pending"], 1)
        self.assertEqual(stats["by_status"]["running"], 1)
        self.assertEqual(stats["total_agents"], 1)

    def test_reset(self):
        self.scheduler.create_batch("agent-1", [{"x": 1}])
        self.scheduler.reset()
        self.assertEqual(self.scheduler.get_batch_count(), 0)
        self.assertEqual(self.scheduler.list_agents(), [])

    def test_callbacks(self):
        events = []
        self.scheduler.on_change("test", lambda action, detail: events.append((action, detail)))
        self.scheduler.create_batch("agent-1", [{"x": 1}])
        self.assertTrue(len(events) > 0)
        self.assertEqual(events[0][0], "create_batch")

    def test_remove_callback(self):
        self.scheduler.on_change("cb1", lambda a, d: None)
        self.assertTrue(self.scheduler.remove_callback("cb1"))
        self.assertFalse(self.scheduler.remove_callback("cb1"))

    def test_get_batch_nonexistent(self):
        self.assertIsNone(self.scheduler.get_batch("abs-nope"))

    def test_unique_ids(self):
        b1 = self.scheduler.create_batch("agent-1", [{"x": 1}])
        b2 = self.scheduler.create_batch("agent-1", [{"x": 1}])
        self.assertNotEqual(b1, b2)


if __name__ == "__main__":
    unittest.main()
