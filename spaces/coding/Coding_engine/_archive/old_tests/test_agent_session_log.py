import sys
import unittest
import time

sys.path.insert(0, ".")
from src.services.agent_session_log import AgentSessionLog, AgentSessionLogState


class TestAgentSessionLog(unittest.TestCase):
    def setUp(self):
        self.log = AgentSessionLog()

    def test_start_session(self):
        sid = self.log.start_session("agent-1")
        self.assertTrue(sid.startswith("asl-"))
        session = self.log.get_session(sid)
        self.assertIsNotNone(session)
        self.assertEqual(session["agent_id"], "agent-1")
        self.assertIsNone(session["ended_at"])

    def test_start_session_with_metadata(self):
        sid = self.log.start_session("agent-1", metadata={"env": "prod"})
        session = self.log.get_session(sid)
        self.assertEqual(session["metadata"], {"env": "prod"})

    def test_end_session(self):
        sid = self.log.start_session("agent-1")
        result = self.log.end_session(sid)
        self.assertEqual(result["session_id"], sid)
        self.assertIn("duration_seconds", result)
        self.assertGreaterEqual(result["duration_seconds"], 0)
        session = self.log.get_session(sid)
        self.assertIsNotNone(session["ended_at"])

    def test_end_session_not_found(self):
        with self.assertRaises(KeyError):
            self.log.end_session("asl-nonexistent")

    def test_log_event(self):
        sid = self.log.start_session("agent-1")
        eid = self.log.log_event(sid, "step", "did something")
        self.assertTrue(eid.startswith("asl-"))
        events = self.log.get_events(sid)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_type"], "step")
        self.assertEqual(events[0]["message"], "did something")

    def test_log_event_invalid_session(self):
        with self.assertRaises(KeyError):
            self.log.log_event("asl-bad", "step")

    def test_get_sessions(self):
        s1 = self.log.start_session("agent-1")
        s2 = self.log.start_session("agent-1")
        self.log.start_session("agent-2")
        sessions = self.log.get_sessions("agent-1")
        self.assertEqual(len(sessions), 2)
        self.log.end_session(s1)
        active = self.log.get_sessions("agent-1", active_only=True)
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["session_id"], s2)

    def test_get_active_sessions(self):
        self.log.start_session("agent-1")
        s2 = self.log.start_session("agent-2")
        self.log.end_session(s2)
        all_active = self.log.get_active_sessions()
        self.assertEqual(len(all_active), 1)
        a1_active = self.log.get_active_sessions("agent-1")
        self.assertEqual(len(a1_active), 1)
        a2_active = self.log.get_active_sessions("agent-2")
        self.assertEqual(len(a2_active), 0)

    def test_get_session_count(self):
        self.log.start_session("agent-1")
        self.log.start_session("agent-1")
        self.log.start_session("agent-2")
        self.assertEqual(self.log.get_session_count(), 3)
        self.assertEqual(self.log.get_session_count("agent-1"), 2)
        self.assertEqual(self.log.get_session_count("agent-2"), 1)

    def test_list_agents(self):
        self.log.start_session("agent-b")
        self.log.start_session("agent-a")
        self.log.start_session("agent-b")
        agents = self.log.list_agents()
        self.assertEqual(agents, ["agent-a", "agent-b"])

    def test_get_stats(self):
        s1 = self.log.start_session("agent-1")
        self.log.start_session("agent-2")
        self.log.log_event(s1, "info", "hello")
        self.log.log_event(s1, "warn", "uh oh")
        self.log.end_session(s1)
        stats = self.log.get_stats()
        self.assertEqual(stats["total_sessions"], 2)
        self.assertEqual(stats["active_sessions"], 1)
        self.assertEqual(stats["total_agents"], 2)
        self.assertEqual(stats["total_events"], 2)

    def test_reset(self):
        self.log.start_session("agent-1")
        self.log.on_change(lambda e, d: None)
        self.log.reset()
        self.assertEqual(self.log.get_session_count(), 0)
        self.assertEqual(len(self.log._callbacks), 0)

    def test_callbacks(self):
        events_received = []
        cb_id = self.log.on_change(lambda e, d: events_received.append((e, d)))
        self.log.start_session("agent-1")
        self.assertEqual(len(events_received), 1)
        self.assertEqual(events_received[0][0], "session_started")
        removed = self.log.remove_callback(cb_id)
        self.assertTrue(removed)
        self.log.start_session("agent-2")
        self.assertEqual(len(events_received), 1)
        self.assertFalse(self.log.remove_callback("asl-nonexistent"))

    def test_prune(self):
        self.log.MAX_ENTRIES = 5
        for i in range(8):
            self.log.start_session(f"agent-{i}")
        self.assertLessEqual(len(self.log._state.entries), 5)

    def test_get_session_not_found(self):
        self.assertIsNone(self.log.get_session("asl-missing"))

    def test_get_events_invalid_session(self):
        self.assertEqual(self.log.get_events("asl-missing"), [])

    def test_state_dataclass(self):
        state = AgentSessionLogState()
        self.assertEqual(state.entries, {})
        self.assertEqual(state._seq, 0)


if __name__ == "__main__":
    unittest.main()
