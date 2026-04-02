"""Tests for AgentWorkflowReplayer."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.agent_workflow_replayer import AgentWorkflowReplayer


class TestAgentWorkflowReplayerRecord(unittest.TestCase):
    """Tests for the record method."""

    def setUp(self):
        self.svc = AgentWorkflowReplayer()

    def test_record_returns_id_with_prefix(self):
        rid = self.svc.record("a1", "wf1", [{"step": 1}])
        self.assertTrue(rid.startswith("awrp-"))
        self.assertGreater(len(rid), len("awrp-"))

    def test_record_stores_agent_id(self):
        rid = self.svc.record("agent-42", "wf1", [])
        replay = self.svc.get_replay(rid)
        self.assertEqual(replay["agent_id"], "agent-42")

    def test_record_stores_workflow_name(self):
        rid = self.svc.record("a1", "deploy-pipeline", [])
        replay = self.svc.get_replay(rid)
        self.assertEqual(replay["workflow_name"], "deploy-pipeline")

    def test_record_stores_steps_data(self):
        steps = [{"action": "start"}, {"action": "finish"}]
        rid = self.svc.record("a1", "wf1", steps)
        replay = self.svc.get_replay(rid)
        self.assertEqual(replay["steps_data"], steps)

    def test_record_deep_copies_steps_data(self):
        steps = [{"nested": {"val": 1}}]
        rid = self.svc.record("a1", "wf1", steps)
        steps[0]["nested"]["val"] = 999
        replay = self.svc.get_replay(rid)
        self.assertEqual(replay["steps_data"][0]["nested"]["val"], 1)

    def test_record_with_metadata(self):
        meta = {"version": "2.0", "env": "prod"}
        rid = self.svc.record("a1", "wf1", [], metadata=meta)
        replay = self.svc.get_replay(rid)
        self.assertEqual(replay["metadata"]["version"], "2.0")
        self.assertEqual(replay["metadata"]["env"], "prod")

    def test_record_metadata_defaults_to_empty_dict(self):
        rid = self.svc.record("a1", "wf1", [])
        replay = self.svc.get_replay(rid)
        self.assertEqual(replay["metadata"], {})

    def test_record_deep_copies_metadata(self):
        meta = {"key": [1, 2, 3]}
        rid = self.svc.record("a1", "wf1", [], metadata=meta)
        meta["key"].append(4)
        replay = self.svc.get_replay(rid)
        self.assertEqual(replay["metadata"]["key"], [1, 2, 3])

    def test_record_sets_created_at(self):
        rid = self.svc.record("a1", "wf1", [])
        replay = self.svc.get_replay(rid)
        self.assertIn("created_at", replay)
        self.assertGreater(replay["created_at"], 0)

    def test_record_unique_ids(self):
        ids = set()
        for i in range(100):
            ids.add(self.svc.record("a1", "wf1", [{"i": i}]))
        self.assertEqual(len(ids), 100)


class TestAgentWorkflowReplayerGetReplay(unittest.TestCase):
    """Tests for the get_replay method."""

    def setUp(self):
        self.svc = AgentWorkflowReplayer()

    def test_get_replay_returns_none_for_missing(self):
        self.assertIsNone(self.svc.get_replay("awrp-nonexistent"))

    def test_get_replay_returns_dict_copy(self):
        rid = self.svc.record("a1", "wf1", [{"x": 1}])
        r1 = self.svc.get_replay(rid)
        r2 = self.svc.get_replay(rid)
        self.assertEqual(r1, r2)
        self.assertIsNot(r1, r2)

    def test_get_replay_contains_all_fields(self):
        rid = self.svc.record("a1", "wf1", [{"step": 1}], metadata={"k": "v"})
        replay = self.svc.get_replay(rid)
        self.assertIn("replay_id", replay)
        self.assertIn("agent_id", replay)
        self.assertIn("workflow_name", replay)
        self.assertIn("steps_data", replay)
        self.assertIn("metadata", replay)
        self.assertIn("created_at", replay)
        self.assertIn("seq", replay)


class TestAgentWorkflowReplayerGetReplays(unittest.TestCase):
    """Tests for the get_replays method."""

    def setUp(self):
        self.svc = AgentWorkflowReplayer()

    def test_get_replays_empty(self):
        self.assertEqual(self.svc.get_replays(), [])

    def test_get_replays_newest_first(self):
        r1 = self.svc.record("a1", "wf1", [{"step": 1}])
        r2 = self.svc.record("a1", "wf1", [{"step": 2}])
        r3 = self.svc.record("a1", "wf2", [{"step": 3}])
        results = self.svc.get_replays()
        self.assertEqual(results[0]["replay_id"], r3)
        self.assertEqual(results[1]["replay_id"], r2)
        self.assertEqual(results[2]["replay_id"], r1)

    def test_get_replays_filter_by_agent_id(self):
        self.svc.record("a1", "wf1", [])
        self.svc.record("a2", "wf1", [])
        self.svc.record("a1", "wf2", [])
        results = self.svc.get_replays(agent_id="a1")
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertEqual(r["agent_id"], "a1")

    def test_get_replays_filter_by_workflow_name(self):
        self.svc.record("a1", "wf1", [])
        self.svc.record("a1", "wf2", [])
        self.svc.record("a2", "wf1", [])
        results = self.svc.get_replays(workflow_name="wf1")
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertEqual(r["workflow_name"], "wf1")

    def test_get_replays_filter_by_both(self):
        self.svc.record("a1", "wf1", [])
        self.svc.record("a1", "wf2", [])
        self.svc.record("a2", "wf1", [])
        results = self.svc.get_replays(agent_id="a1", workflow_name="wf1")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["agent_id"], "a1")
        self.assertEqual(results[0]["workflow_name"], "wf1")

    def test_get_replays_limit(self):
        for i in range(10):
            self.svc.record("a1", "wf1", [{"i": i}])
        results = self.svc.get_replays(limit=3)
        self.assertEqual(len(results), 3)

    def test_get_replays_no_match(self):
        self.svc.record("a1", "wf1", [])
        results = self.svc.get_replays(agent_id="nonexistent")
        self.assertEqual(results, [])

    def test_get_replays_returns_copies(self):
        self.svc.record("a1", "wf1", [{"x": 1}])
        r1 = self.svc.get_replays()
        r2 = self.svc.get_replays()
        self.assertIsNot(r1[0], r2[0])


class TestAgentWorkflowReplayerCount(unittest.TestCase):
    """Tests for the get_replay_count method."""

    def setUp(self):
        self.svc = AgentWorkflowReplayer()

    def test_count_empty(self):
        self.assertEqual(self.svc.get_replay_count(), 0)

    def test_count_all(self):
        self.svc.record("a1", "wf1", [])
        self.svc.record("a2", "wf1", [])
        self.assertEqual(self.svc.get_replay_count(), 2)

    def test_count_by_agent(self):
        self.svc.record("a1", "wf1", [])
        self.svc.record("a2", "wf1", [])
        self.svc.record("a1", "wf2", [])
        self.assertEqual(self.svc.get_replay_count("a1"), 2)
        self.assertEqual(self.svc.get_replay_count("a2"), 1)
        self.assertEqual(self.svc.get_replay_count("a3"), 0)


class TestAgentWorkflowReplayerCallbacks(unittest.TestCase):
    """Tests for callbacks and on_change."""

    def setUp(self):
        self.svc = AgentWorkflowReplayer()

    def test_on_change_property_get_set(self):
        self.assertIsNone(self.svc.on_change)
        cb = lambda a, d: None
        self.svc.on_change = cb
        self.assertIs(self.svc.on_change, cb)

    def test_on_change_fires_on_record(self):
        events = []
        self.svc.on_change = lambda action, data: events.append((action, data))
        self.svc.record("a1", "wf1", [])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "replay_recorded")

    def test_on_change_set_to_none_stops_firing(self):
        events = []
        self.svc.on_change = lambda action, data: events.append(action)
        self.svc.record("a1", "wf1", [])
        self.svc.on_change = None
        self.svc.record("a1", "wf1", [])
        self.assertEqual(len(events), 1)

    def test_remove_callback_returns_false_for_missing(self):
        self.assertFalse(self.svc.remove_callback("nonexistent"))

    def test_remove_callback_returns_true_and_removes(self):
        self.svc._callbacks["cb1"] = lambda a, d: None
        self.assertTrue(self.svc.remove_callback("cb1"))
        self.assertNotIn("cb1", self.svc._callbacks)

    def test_callback_exception_is_swallowed(self):
        def bad_cb(action, data):
            raise RuntimeError("boom")

        self.svc._callbacks["bad"] = bad_cb
        # Should not raise
        rid = self.svc.record("a1", "wf1", [])
        self.assertIsNotNone(self.svc.get_replay(rid))

    def test_on_change_exception_is_swallowed(self):
        self.svc.on_change = lambda a, d: (_ for _ in ()).throw(ValueError("oops"))
        rid = self.svc.record("a1", "wf1", [])
        self.assertIsNotNone(self.svc.get_replay(rid))


class TestAgentWorkflowReplayerPrune(unittest.TestCase):
    """Tests for pruning behavior."""

    def test_prune_removes_oldest_quarter(self):
        svc = AgentWorkflowReplayer()
        svc.MAX_ENTRIES = 4
        # Record 5 entries: no pruning yet (prune checks before adding)
        for i in range(5):
            svc.record("a1", "wf1", [{"i": i}])
        self.assertEqual(svc.get_replay_count(), 5)
        # 6th record: prune fires (5 > 4), removes floor(5/4)=1, then adds
        svc.record("a1", "wf1", [{"i": 5}])
        self.assertEqual(svc.get_replay_count(), 5)

    def test_prune_keeps_newest_entries(self):
        svc = AgentWorkflowReplayer()
        svc.MAX_ENTRIES = 4
        ids = []
        for i in range(5):
            ids.append(svc.record("a1", "wf1", [{"i": i}]))
        # The last recorded entry should still exist
        self.assertIsNotNone(svc.get_replay(ids[-1]))


class TestAgentWorkflowReplayerStats(unittest.TestCase):
    """Tests for get_stats."""

    def setUp(self):
        self.svc = AgentWorkflowReplayer()

    def test_stats_empty(self):
        stats = self.svc.get_stats()
        self.assertEqual(stats["total_replays"], 0)
        self.assertEqual(stats["unique_agents"], 0)
        self.assertEqual(stats["unique_workflows"], 0)

    def test_stats_populated(self):
        self.svc.record("a1", "wf1", [])
        self.svc.record("a1", "wf2", [])
        self.svc.record("a2", "wf1", [])
        stats = self.svc.get_stats()
        self.assertEqual(stats["total_replays"], 3)
        self.assertEqual(stats["unique_agents"], 2)
        self.assertEqual(stats["unique_workflows"], 2)


class TestAgentWorkflowReplayerReset(unittest.TestCase):
    """Tests for reset."""

    def test_reset_clears_entries(self):
        svc = AgentWorkflowReplayer()
        svc.record("a1", "wf1", [])
        svc.record("a2", "wf2", [])
        svc.reset()
        self.assertEqual(svc.get_replay_count(), 0)
        self.assertEqual(svc.get_stats()["total_replays"], 0)

    def test_reset_clears_callbacks(self):
        svc = AgentWorkflowReplayer()
        svc._callbacks["cb1"] = lambda a, d: None
        svc.on_change = lambda a, d: None
        svc.reset()
        self.assertEqual(len(svc._callbacks), 0)
        self.assertIsNone(svc.on_change)

    def test_reset_resets_seq(self):
        svc = AgentWorkflowReplayer()
        svc.record("a1", "wf1", [])
        svc.reset()
        self.assertEqual(svc._state._seq, 0)


if __name__ == "__main__":
    unittest.main()
