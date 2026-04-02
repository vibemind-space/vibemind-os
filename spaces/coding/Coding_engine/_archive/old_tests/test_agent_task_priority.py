"""Tests for AgentTaskPriority."""

import sys
import unittest

sys.path.insert(0, ".")
from src.services.agent_task_priority import AgentTaskPriority, AgentTaskPriorityState


class TestAgentTaskPriority(unittest.TestCase):

    def setUp(self):
        self.atp = AgentTaskPriority()

    # 1. add_task returns id with correct prefix
    def test_add_task_returns_id(self):
        tid = self.atp.add_task("agent1", "build")
        self.assertTrue(tid.startswith("atp-"))
        self.assertEqual(len(tid), 4 + 16)  # prefix + 16 hex chars

    # 2. get_task retrieves added task
    def test_get_task(self):
        tid = self.atp.add_task("agent1", "deploy", priority=5, metadata={"env": "prod"})
        task = self.atp.get_task(tid)
        self.assertIsNotNone(task)
        self.assertEqual(task["task_name"], "deploy")
        self.assertEqual(task["priority"], 5)
        self.assertEqual(task["status"], "pending")
        self.assertEqual(task["metadata"], {"env": "prod"})

    # 3. get_task returns None for unknown id
    def test_get_task_unknown(self):
        self.assertIsNone(self.atp.get_task("atp-nonexistent00000"))

    # 4. get_next returns highest priority task and marks in_progress
    def test_get_next_priority_order(self):
        self.atp.add_task("a1", "low", priority=1)
        self.atp.add_task("a1", "high", priority=10)
        self.atp.add_task("a1", "mid", priority=5)
        task = self.atp.get_next("a1")
        self.assertIsNotNone(task)
        self.assertEqual(task["task_name"], "high")
        self.assertEqual(task["status"], "in_progress")

    # 5. get_next returns None when no pending tasks
    def test_get_next_empty(self):
        self.assertIsNone(self.atp.get_next("no_agent"))

    # 6. complete_task
    def test_complete_task(self):
        tid = self.atp.add_task("a1", "job")
        self.atp.get_next("a1")  # move to in_progress
        result = self.atp.complete_task(tid)
        self.assertTrue(result)
        task = self.atp.get_task(tid)
        self.assertEqual(task["status"], "completed")
        self.assertIsNotNone(task["completed_at"])

    # 7. complete_task returns False for unknown / already completed
    def test_complete_task_invalid(self):
        self.assertFalse(self.atp.complete_task("atp-doesnotexist00"))
        tid = self.atp.add_task("a1", "x")
        self.atp.complete_task(tid)
        self.assertFalse(self.atp.complete_task(tid))

    # 8. reprioritize
    def test_reprioritize(self):
        tid = self.atp.add_task("a1", "task", priority=3)
        result = self.atp.reprioritize(tid, 99)
        self.assertTrue(result)
        self.assertEqual(self.atp.get_task(tid)["priority"], 99)
        self.assertFalse(self.atp.reprioritize("atp-bad", 1))

    # 9. get_tasks with status filter
    def test_get_tasks_filter(self):
        self.atp.add_task("a1", "t1")
        self.atp.add_task("a1", "t2")
        self.atp.add_task("a2", "t3")
        self.atp.get_next("a1")  # one becomes in_progress
        pending = self.atp.get_tasks("a1", status="pending")
        self.assertEqual(len(pending), 1)
        all_a1 = self.atp.get_tasks("a1")
        self.assertEqual(len(all_a1), 2)

    # 10. get_task_count
    def test_get_task_count(self):
        self.atp.add_task("a1", "t1")
        self.atp.add_task("a1", "t2")
        self.atp.add_task("a2", "t3")
        self.assertEqual(self.atp.get_task_count(), 3)
        self.assertEqual(self.atp.get_task_count(agent_id="a1"), 2)
        self.assertEqual(self.atp.get_task_count(status="pending"), 3)

    # 11. list_agents
    def test_list_agents(self):
        self.atp.add_task("beta", "x")
        self.atp.add_task("alpha", "y")
        self.atp.add_task("beta", "z")
        self.assertEqual(self.atp.list_agents(), ["alpha", "beta"])

    # 12. callbacks fire on events
    def test_callbacks(self):
        events = []
        self.atp.on_change("spy", lambda evt, data: events.append(evt))
        self.atp.add_task("a1", "t1")
        self.assertIn("task_added", events)
        self.assertTrue(self.atp.remove_callback("spy"))
        self.assertFalse(self.atp.remove_callback("spy"))

    # 13. get_stats and reset
    def test_stats_and_reset(self):
        self.atp.add_task("a1", "t1")
        self.atp.add_task("a2", "t2")
        stats = self.atp.get_stats()
        self.assertEqual(stats["total_tasks"], 2)
        self.assertEqual(stats["agents"], 2)
        self.atp.reset()
        self.assertEqual(self.atp.get_task_count(), 0)
        self.assertEqual(self.atp.get_stats()["total_tasks"], 0)

    # 14. unique IDs via seq increment
    def test_unique_ids(self):
        ids = {self.atp.add_task("a", "t") for _ in range(50)}
        self.assertEqual(len(ids), 50)

    # 15. prune beyond MAX_ENTRIES
    def test_prune(self):
        from src.services.agent_task_priority import MAX_ENTRIES
        # Add tasks beyond limit — mark most as completed so pruning works
        for i in range(MAX_ENTRIES + 50):
            tid = self.atp.add_task("a1", f"task{i}")
            self.atp.complete_task(tid)
        self.assertLessEqual(len(self.atp._state.entries), MAX_ENTRIES)

    # 16. dataclass state
    def test_state_dataclass(self):
        import dataclasses
        self.assertTrue(dataclasses.is_dataclass(AgentTaskPriorityState))
        state = AgentTaskPriorityState()
        self.assertIsInstance(state.entries, dict)
        self.assertEqual(state._seq, 0)


if __name__ == "__main__":
    unittest.main()
