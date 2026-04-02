"""Tests for AgentTaskBuffer service."""

import sys
import unittest

sys.path.insert(0, ".")
from src.services.agent_task_buffer import AgentTaskBuffer


class TestAgentTaskBuffer(unittest.TestCase):
    def setUp(self):
        self.buf = AgentTaskBuffer()

    def test_create_buffer(self):
        bid = self.buf.create_buffer("agent-1", capacity=50)
        self.assertTrue(bid.startswith("atb-"))
        info = self.buf.get_buffer(bid)
        self.assertIsNotNone(info)
        self.assertEqual(info["agent_id"], "agent-1")
        self.assertEqual(info["capacity"], 50)
        self.assertEqual(info["size"], 0)

    def test_push_and_pop_fifo(self):
        bid = self.buf.create_buffer("agent-1")
        self.assertTrue(self.buf.push(bid, "task-a"))
        self.assertTrue(self.buf.push(bid, "task-b"))
        self.assertTrue(self.buf.push(bid, "task-c"))
        self.assertEqual(self.buf.pop(bid), "task-a")
        self.assertEqual(self.buf.pop(bid), "task-b")
        self.assertEqual(self.buf.pop(bid), "task-c")
        self.assertIsNone(self.buf.pop(bid))

    def test_push_at_capacity(self):
        bid = self.buf.create_buffer("agent-1", capacity=2)
        self.assertTrue(self.buf.push(bid, "t1"))
        self.assertTrue(self.buf.push(bid, "t2"))
        self.assertFalse(self.buf.push(bid, "t3"))
        self.assertEqual(self.buf.get_size(bid), 2)

    def test_peek(self):
        bid = self.buf.create_buffer("agent-1")
        self.assertIsNone(self.buf.peek(bid))
        self.buf.push(bid, "task-x")
        self.assertEqual(self.buf.peek(bid), "task-x")
        self.assertEqual(self.buf.get_size(bid), 1)  # peek doesn't remove

    def test_get_size(self):
        bid = self.buf.create_buffer("agent-1")
        self.assertEqual(self.buf.get_size(bid), 0)
        self.buf.push(bid, "t1")
        self.buf.push(bid, "t2")
        self.assertEqual(self.buf.get_size(bid), 2)
        self.assertEqual(self.buf.get_size("nonexistent"), 0)

    def test_get_buffer_not_found(self):
        self.assertIsNone(self.buf.get_buffer("atb-nonexistent"))

    def test_get_buffers_by_agent(self):
        b1 = self.buf.create_buffer("agent-1")
        b2 = self.buf.create_buffer("agent-1")
        b3 = self.buf.create_buffer("agent-2")
        buffers = self.buf.get_buffers("agent-1")
        self.assertEqual(len(buffers), 2)
        ids = [b["buffer_id"] for b in buffers]
        self.assertIn(b1, ids)
        self.assertIn(b2, ids)

    def test_flush(self):
        bid = self.buf.create_buffer("agent-1")
        self.buf.push(bid, "t1")
        self.buf.push(bid, "t2")
        self.buf.push(bid, "t3")
        tasks = self.buf.flush(bid)
        self.assertEqual(tasks, ["t1", "t2", "t3"])
        self.assertEqual(self.buf.get_size(bid), 0)
        self.assertEqual(self.buf.flush("nonexistent"), [])

    def test_get_buffer_count(self):
        self.buf.create_buffer("agent-1")
        self.buf.create_buffer("agent-1")
        self.buf.create_buffer("agent-2")
        self.assertEqual(self.buf.get_buffer_count(), 3)
        self.assertEqual(self.buf.get_buffer_count("agent-1"), 2)
        self.assertEqual(self.buf.get_buffer_count("agent-2"), 1)
        self.assertEqual(self.buf.get_buffer_count("agent-999"), 0)

    def test_list_agents(self):
        self.buf.create_buffer("agent-b")
        self.buf.create_buffer("agent-a")
        self.buf.create_buffer("agent-b")
        agents = self.buf.list_agents()
        self.assertEqual(agents, ["agent-a", "agent-b"])

    def test_get_stats(self):
        b1 = self.buf.create_buffer("agent-1")
        b2 = self.buf.create_buffer("agent-2")
        self.buf.push(b1, "t1")
        self.buf.push(b1, "t2")
        self.buf.push(b2, "t3")
        stats = self.buf.get_stats()
        self.assertEqual(stats["total_buffers"], 2)
        self.assertEqual(stats["total_tasks"], 3)
        self.assertEqual(stats["total_agents"], 2)
        self.assertIn("agent-1", stats["agents"])
        self.assertIn("agent-2", stats["agents"])

    def test_reset(self):
        b1 = self.buf.create_buffer("agent-1")
        self.buf.push(b1, "t1")
        self.buf.reset()
        self.assertEqual(self.buf.get_buffer_count(), 0)
        self.assertEqual(self.buf.list_agents(), [])
        self.assertIsNone(self.buf.get_buffer(b1))

    def test_callbacks(self):
        events = []
        self.buf.on_change(lambda e, d: events.append(("change", e, d)))
        self.buf.register_callback("cb1", lambda e, d: events.append(("cb1", e, d)))
        bid = self.buf.create_buffer("agent-1")
        self.buf.push(bid, "task-1")
        self.assertTrue(len(events) >= 2)
        # Remove callback
        self.assertTrue(self.buf.remove_callback("cb1"))
        self.assertFalse(self.buf.remove_callback("cb1"))

    def test_unique_ids(self):
        ids = set()
        for i in range(100):
            bid = self.buf.create_buffer(f"agent-{i % 5}")
            self.assertNotIn(bid, ids)
            ids.add(bid)

    def test_push_to_nonexistent_buffer(self):
        self.assertFalse(self.buf.push("atb-doesnotexist", "task"))

    def test_pop_from_nonexistent_buffer(self):
        self.assertIsNone(self.buf.pop("atb-doesnotexist"))


if __name__ == "__main__":
    unittest.main()
