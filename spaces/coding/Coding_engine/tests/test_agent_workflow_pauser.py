"""Tests for AgentWorkflowPauser service."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.agent_workflow_pauser import AgentWorkflowPauser


class TestPause(unittest.TestCase):
    """Tests for the pause() method."""

    def test_pause_returns_id(self):
        p = AgentWorkflowPauser()
        rid = p.pause("agent-1", "deploy-pipeline", reason="manual hold")
        self.assertTrue(rid.startswith("awpa-"))
        self.assertGreater(len(rid), len("awpa-"))

    def test_pause_unique_ids(self):
        p = AgentWorkflowPauser()
        id1 = p.pause("a1", "wf1")
        id2 = p.pause("a1", "wf1")
        self.assertNotEqual(id1, id2)

    def test_pause_stores_entry(self):
        p = AgentWorkflowPauser()
        rid = p.pause("a1", "wf1", reason="testing", metadata={"key": "val"})
        entry = p.get_pause(rid)
        self.assertIsInstance(entry, dict)
        self.assertEqual(entry["record_id"], rid)
        self.assertEqual(entry["agent_id"], "a1")
        self.assertEqual(entry["workflow_name"], "wf1")
        self.assertEqual(entry["reason"], "testing")
        self.assertEqual(entry["metadata"], {"key": "val"})
        self.assertEqual(entry["status"], "paused")
        self.assertIsNone(entry["resumed_at"])

    def test_pause_default_args(self):
        p = AgentWorkflowPauser()
        rid = p.pause("a1", "wf1")
        entry = p.get_pause(rid)
        self.assertEqual(entry["reason"], "")
        self.assertEqual(entry["metadata"], {})

    def test_pause_fires_callback(self):
        events = []
        p = AgentWorkflowPauser()
        p.on_change = lambda action, data: events.append(action)
        p.pause("a1", "wf1")
        self.assertIn("paused", events)


class TestResumeWorkflow(unittest.TestCase):
    """Tests for the resume_workflow() method."""

    def test_resume_success(self):
        p = AgentWorkflowPauser()
        rid = p.pause("a1", "wf1")
        result = p.resume_workflow(rid)
        self.assertTrue(result)
        entry = p.get_pause(rid)
        self.assertEqual(entry["status"], "resumed")
        self.assertIsNotNone(entry["resumed_at"])

    def test_resume_nonexistent(self):
        p = AgentWorkflowPauser()
        result = p.resume_workflow("awpa-nonexistent")
        self.assertFalse(result)

    def test_resume_already_resumed(self):
        p = AgentWorkflowPauser()
        rid = p.pause("a1", "wf1")
        p.resume_workflow(rid)
        result = p.resume_workflow(rid)
        self.assertFalse(result)

    def test_resume_fires_callback(self):
        events = []
        p = AgentWorkflowPauser()
        p.on_change = lambda action, data: events.append(action)
        rid = p.pause("a1", "wf1")
        p.resume_workflow(rid)
        self.assertIn("resumed", events)


class TestGetPause(unittest.TestCase):
    """Tests for the get_pause() method."""

    def test_get_pause_returns_copy(self):
        p = AgentWorkflowPauser()
        rid = p.pause("a1", "wf1")
        e1 = p.get_pause(rid)
        e2 = p.get_pause(rid)
        self.assertEqual(e1, e2)
        self.assertIsNot(e1, e2)

    def test_get_pause_not_found(self):
        p = AgentWorkflowPauser()
        self.assertIsNone(p.get_pause("awpa-missing"))


class TestGetPauses(unittest.TestCase):
    """Tests for the get_pauses() method."""

    def test_get_pauses_all(self):
        p = AgentWorkflowPauser()
        p.pause("a1", "wf1")
        p.pause("a2", "wf2")
        p.pause("a1", "wf3")
        results = p.get_pauses()
        self.assertEqual(len(results), 3)

    def test_get_pauses_filter_agent(self):
        p = AgentWorkflowPauser()
        p.pause("a1", "wf1")
        p.pause("a2", "wf2")
        p.pause("a1", "wf3")
        results = p.get_pauses(agent_id="a1")
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r["agent_id"] == "a1" for r in results))

    def test_get_pauses_newest_first(self):
        p = AgentWorkflowPauser()
        p.pause("a1", "wf1", reason="first")
        p.pause("a1", "wf2", reason="second")
        p.pause("a1", "wf3", reason="third")
        results = p.get_pauses(agent_id="a1")
        self.assertEqual(results[0]["reason"], "third")
        self.assertEqual(results[-1]["reason"], "first")

    def test_get_pauses_limit(self):
        p = AgentWorkflowPauser()
        for i in range(10):
            p.pause("a1", f"wf{i}")
        results = p.get_pauses(limit=3)
        self.assertEqual(len(results), 3)

    def test_get_pauses_default_limit(self):
        p = AgentWorkflowPauser()
        for i in range(60):
            p.pause("a1", f"wf{i}")
        results = p.get_pauses()
        self.assertEqual(len(results), 50)

    def test_get_pauses_empty(self):
        p = AgentWorkflowPauser()
        self.assertEqual(p.get_pauses(), [])

    def test_get_pauses_returns_copies(self):
        p = AgentWorkflowPauser()
        p.pause("a1", "wf1")
        results = p.get_pauses()
        self.assertIsInstance(results[0], dict)


class TestGetPauseCount(unittest.TestCase):
    """Tests for the get_pause_count() method."""

    def test_count_all(self):
        p = AgentWorkflowPauser()
        p.pause("a1", "wf1")
        p.pause("a2", "wf2")
        p.pause("a1", "wf3")
        self.assertEqual(p.get_pause_count(), 3)

    def test_count_filtered(self):
        p = AgentWorkflowPauser()
        p.pause("a1", "wf1")
        p.pause("a2", "wf2")
        p.pause("a1", "wf3")
        self.assertEqual(p.get_pause_count(agent_id="a1"), 2)
        self.assertEqual(p.get_pause_count(agent_id="a2"), 1)
        self.assertEqual(p.get_pause_count(agent_id="a99"), 0)


class TestGetStats(unittest.TestCase):
    """Tests for the get_stats() method."""

    def test_stats_empty(self):
        p = AgentWorkflowPauser()
        stats = p.get_stats()
        self.assertEqual(stats["total_pauses"], 0)
        self.assertEqual(stats["active_pauses"], 0)
        self.assertEqual(stats["resumed_pauses"], 0)

    def test_stats_mixed(self):
        p = AgentWorkflowPauser()
        rid1 = p.pause("a1", "wf1")
        p.pause("a1", "wf2")
        p.resume_workflow(rid1)
        stats = p.get_stats()
        self.assertEqual(stats["total_pauses"], 2)
        self.assertEqual(stats["active_pauses"], 1)
        self.assertEqual(stats["resumed_pauses"], 1)

    def test_stats_all_resumed(self):
        p = AgentWorkflowPauser()
        rid1 = p.pause("a1", "wf1")
        rid2 = p.pause("a1", "wf2")
        p.resume_workflow(rid1)
        p.resume_workflow(rid2)
        stats = p.get_stats()
        self.assertEqual(stats["active_pauses"], 0)
        self.assertEqual(stats["resumed_pauses"], 2)


class TestCallbacks(unittest.TestCase):
    """Tests for callback management."""

    def test_on_change_getter_setter(self):
        p = AgentWorkflowPauser()
        self.assertIsNone(p.on_change)
        handler = lambda a, d: None
        p.on_change = handler
        self.assertIs(p.on_change, handler)

    def test_remove_callback_exists(self):
        p = AgentWorkflowPauser()
        p._callbacks["cb1"] = lambda a, d: None
        self.assertTrue(p.remove_callback("cb1"))
        self.assertFalse(p.remove_callback("cb1"))

    def test_remove_callback_nonexistent(self):
        p = AgentWorkflowPauser()
        self.assertFalse(p.remove_callback("nope"))

    def test_callbacks_dict_fires(self):
        events = []
        p = AgentWorkflowPauser()
        p._callbacks["tracker"] = lambda action, data: events.append((action, data["record_id"]))
        rid = p.pause("a1", "wf1")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "paused")
        self.assertEqual(events[0][1], rid)

    def test_callback_exception_silenced(self):
        p = AgentWorkflowPauser()
        p._callbacks["bad"] = lambda a, d: (_ for _ in ()).throw(ValueError("boom"))
        p.on_change = lambda a, d: (_ for _ in ()).throw(RuntimeError("crash"))
        rid = p.pause("a1", "wf1")
        self.assertTrue(rid.startswith("awpa-"))


class TestReset(unittest.TestCase):
    """Tests for the reset() method."""

    def test_reset_clears_everything(self):
        p = AgentWorkflowPauser()
        p.pause("a1", "wf1")
        p._callbacks["cb1"] = lambda a, d: None
        p.on_change = lambda a, d: None
        p.reset()
        self.assertEqual(p.get_stats()["total_pauses"], 0)
        self.assertEqual(len(p._callbacks), 0)
        self.assertIsNone(p.on_change)

    def test_reset_resets_seq(self):
        p = AgentWorkflowPauser()
        p.pause("a1", "wf1")
        p.reset()
        self.assertEqual(p._state._seq, 0)


class TestPruning(unittest.TestCase):
    """Tests for pruning behavior."""

    def test_prune_removes_oldest_quarter(self):
        p = AgentWorkflowPauser()
        p.MAX_ENTRIES = 8
        for i in range(10):
            p.pause("a1", f"wf{i}", reason=f"r{i}")
        # After exceeding 8, oldest quarter should be pruned
        self.assertLessEqual(len(p._state.entries), 9)

    def test_prune_keeps_newest(self):
        p = AgentWorkflowPauser()
        p.MAX_ENTRIES = 4
        for i in range(6):
            p.pause("a1", f"wf{i}", reason=f"r{i}")
        # The newest entries should survive
        results = p.get_pauses()
        reasons = [r["reason"] for r in results]
        self.assertIn("r5", reasons)


class TestPrefixAndMaxEntries(unittest.TestCase):
    """Tests for class-level constants."""

    def test_prefix(self):
        self.assertEqual(AgentWorkflowPauser.PREFIX, "awpa-")

    def test_max_entries(self):
        self.assertEqual(AgentWorkflowPauser.MAX_ENTRIES, 10000)


if __name__ == "__main__":
    unittest.main()
