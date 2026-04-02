import sys
import unittest

sys.path.insert(0, ".")
from src.services.agent_execution_tracker_v2 import AgentExecutionTrackerV2


class TestAgentExecutionTrackerV2(unittest.TestCase):
    def setUp(self):
        self.tracker = AgentExecutionTrackerV2()

    def test_start_execution_returns_id_with_prefix(self):
        eid = self.tracker.start_execution("agent-1", "task-a")
        self.assertTrue(eid.startswith("aet2-"))

    def test_get_execution_returns_entry(self):
        eid = self.tracker.start_execution("agent-1", "task-a", phases=["init", "run"])
        entry = self.tracker.get_execution(eid)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["agent_id"], "agent-1")
        self.assertEqual(entry["task_name"], "task-a")
        self.assertEqual(entry["status"], "running")
        self.assertEqual(entry["phases"], ["init", "run"])

    def test_get_execution_not_found(self):
        self.assertIsNone(self.tracker.get_execution("aet2-nonexistent"))

    def test_advance_phase(self):
        eid = self.tracker.start_execution("agent-1", "task-a", phases=["p1", "p2", "p3"])
        result = self.tracker.advance_phase(eid)
        self.assertEqual(result["phase_name"], "p1")
        self.assertEqual(result["phase_index"], 0)
        self.assertEqual(result["total_phases"], 3)

        result2 = self.tracker.advance_phase(eid)
        self.assertEqual(result2["phase_name"], "p2")
        self.assertEqual(result2["phase_index"], 1)

    def test_advance_phase_past_end_raises(self):
        eid = self.tracker.start_execution("agent-1", "task-a", phases=["p1"])
        self.tracker.advance_phase(eid)
        with self.assertRaises(ValueError):
            self.tracker.advance_phase(eid)

    def test_advance_phase_no_phases_raises(self):
        eid = self.tracker.start_execution("agent-1", "task-a")
        with self.assertRaises(ValueError):
            self.tracker.advance_phase(eid)

    def test_complete_execution(self):
        eid = self.tracker.start_execution("agent-1", "task-a", phases=["p1", "p2"])
        self.tracker.advance_phase(eid)
        result = self.tracker.complete_execution(eid)
        self.assertEqual(result["execution_id"], eid)
        self.assertIn("duration_ms", result)
        self.assertEqual(result["phases_completed"], 1)
        entry = self.tracker.get_execution(eid)
        self.assertEqual(entry["status"], "success")

    def test_complete_execution_with_failure_status(self):
        eid = self.tracker.start_execution("agent-1", "task-a")
        result = self.tracker.complete_execution(eid, status="failed")
        entry = self.tracker.get_execution(eid)
        self.assertEqual(entry["status"], "failed")

    def test_get_current_phase(self):
        eid = self.tracker.start_execution("agent-1", "task-a", phases=["init", "run", "done"])
        self.assertIsNone(self.tracker.get_current_phase(eid))
        self.tracker.advance_phase(eid)
        self.assertEqual(self.tracker.get_current_phase(eid), "init")
        self.tracker.advance_phase(eid)
        self.assertEqual(self.tracker.get_current_phase(eid), "run")

    def test_get_executions_filters(self):
        self.tracker.start_execution("agent-1", "task-a")
        self.tracker.start_execution("agent-1", "task-b")
        eid3 = self.tracker.start_execution("agent-2", "task-c")
        self.tracker.complete_execution(eid3, status="success")

        results = self.tracker.get_executions("agent-1")
        self.assertEqual(len(results), 2)

        results_running = self.tracker.get_executions("agent-1", status="running")
        self.assertEqual(len(results_running), 2)

        results_a2 = self.tracker.get_executions("agent-2", status="success")
        self.assertEqual(len(results_a2), 1)

    def test_get_execution_count(self):
        self.tracker.start_execution("agent-1", "task-a")
        self.tracker.start_execution("agent-1", "task-b")
        self.tracker.start_execution("agent-2", "task-c")
        self.assertEqual(self.tracker.get_execution_count(), 3)
        self.assertEqual(self.tracker.get_execution_count("agent-1"), 2)
        self.assertEqual(self.tracker.get_execution_count("agent-2"), 1)
        self.assertEqual(self.tracker.get_execution_count("agent-3"), 0)

    def test_list_agents(self):
        self.tracker.start_execution("beta", "task")
        self.tracker.start_execution("alpha", "task")
        self.tracker.start_execution("beta", "task2")
        agents = self.tracker.list_agents()
        self.assertEqual(agents, ["alpha", "beta"])

    def test_on_change_and_remove_callback(self):
        events = []
        cb_id = self.tracker.on_change(lambda e, d: events.append((e, d)))
        self.tracker.start_execution("a1", "t1")
        self.assertTrue(len(events) > 0)
        self.assertEqual(events[-1][0], "execution_started")

        removed = self.tracker.remove_callback(cb_id)
        self.assertTrue(removed)
        removed2 = self.tracker.remove_callback(cb_id)
        self.assertFalse(removed2)

    def test_get_stats(self):
        self.tracker.start_execution("a1", "t1")
        eid = self.tracker.start_execution("a2", "t2")
        self.tracker.complete_execution(eid)
        stats = self.tracker.get_stats()
        self.assertEqual(stats["total_executions"], 2)
        self.assertEqual(stats["agents"], 2)
        self.assertIn("running", stats["by_status"])
        self.assertIn("success", stats["by_status"])

    def test_reset(self):
        self.tracker.start_execution("a1", "t1")
        self.tracker.on_change(lambda e, d: None)
        self.tracker.reset()
        self.assertEqual(self.tracker.get_execution_count(), 0)
        self.assertEqual(len(self.tracker._callbacks), 0)

    def test_prune_at_max(self):
        for i in range(10005):
            self.tracker.start_execution(f"agent-{i % 10}", f"task-{i}")
        self.assertLessEqual(self.tracker.get_execution_count(), 10000)


if __name__ == "__main__":
    unittest.main()
