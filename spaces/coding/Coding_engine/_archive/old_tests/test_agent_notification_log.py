"""Tests for AgentNotificationLog service."""

import sys
import unittest

sys.path.insert(0, ".")
from src.services.agent_notification_log import AgentNotificationLog


class TestAgentNotificationLog(unittest.TestCase):
    def setUp(self):
        self.log = AgentNotificationLog()

    def test_send_notification_returns_id(self):
        nid = self.log.send_notification("agent-1", "Hello", "World")
        self.assertTrue(nid.startswith("anl-"))
        self.assertEqual(len(nid), 4 + 16)  # prefix + hash

    def test_get_notification(self):
        nid = self.log.send_notification("agent-1", "Title", "Body", severity="warning")
        notif = self.log.get_notification(nid)
        self.assertIsNotNone(notif)
        self.assertEqual(notif["agent_id"], "agent-1")
        self.assertEqual(notif["title"], "Title")
        self.assertEqual(notif["message"], "Body")
        self.assertEqual(notif["severity"], "warning")
        self.assertFalse(notif["read"])

    def test_get_notification_not_found(self):
        self.assertIsNone(self.log.get_notification("anl-nonexistent"))

    def test_mark_read(self):
        nid = self.log.send_notification("agent-1", "T", "M")
        self.assertTrue(self.log.mark_read(nid))
        notif = self.log.get_notification(nid)
        self.assertTrue(notif["read"])

    def test_mark_read_not_found(self):
        self.assertFalse(self.log.mark_read("anl-nonexistent"))

    def test_get_notifications_filters(self):
        self.log.send_notification("agent-1", "A", "a", severity="info")
        self.log.send_notification("agent-1", "B", "b", severity="error")
        nid3 = self.log.send_notification("agent-2", "C", "c", severity="info")
        nid1 = self.log.send_notification("agent-1", "D", "d", severity="info")
        self.log.mark_read(nid1)

        # All for agent-1
        results = self.log.get_notifications("agent-1")
        self.assertEqual(len(results), 3)

        # Unread only for agent-1
        results = self.log.get_notifications("agent-1", unread_only=True)
        self.assertEqual(len(results), 2)

        # Severity filter
        results = self.log.get_notifications("agent-1", severity="error")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["severity"], "error")

    def test_get_unread_count(self):
        self.log.send_notification("agent-1", "A", "a")
        self.log.send_notification("agent-1", "B", "b")
        nid = self.log.send_notification("agent-1", "C", "c")
        self.assertEqual(self.log.get_unread_count("agent-1"), 3)
        self.log.mark_read(nid)
        self.assertEqual(self.log.get_unread_count("agent-1"), 2)

    def test_dismiss_notification(self):
        nid = self.log.send_notification("agent-1", "T", "M")
        self.assertTrue(self.log.dismiss_notification(nid))
        # Dismissed notifications should not appear in get_notifications
        results = self.log.get_notifications("agent-1")
        self.assertEqual(len(results), 0)
        # But still retrievable by ID
        self.assertIsNotNone(self.log.get_notification(nid))

    def test_dismiss_not_found(self):
        self.assertFalse(self.log.dismiss_notification("anl-nonexistent"))

    def test_get_notification_count(self):
        self.log.send_notification("agent-1", "A", "a")
        self.log.send_notification("agent-2", "B", "b")
        self.log.send_notification("agent-1", "C", "c")
        self.assertEqual(self.log.get_notification_count(), 3)
        self.assertEqual(self.log.get_notification_count("agent-1"), 2)
        self.assertEqual(self.log.get_notification_count("agent-2"), 1)
        self.assertEqual(self.log.get_notification_count("agent-3"), 0)

    def test_list_agents(self):
        self.log.send_notification("agent-b", "A", "a")
        self.log.send_notification("agent-a", "B", "b")
        self.log.send_notification("agent-b", "C", "c")
        agents = self.log.list_agents()
        self.assertEqual(agents, ["agent-a", "agent-b"])

    def test_get_stats(self):
        self.log.send_notification("agent-1", "A", "a", severity="info")
        nid = self.log.send_notification("agent-1", "B", "b", severity="error")
        self.log.send_notification("agent-2", "C", "c", severity="info")
        self.log.mark_read(nid)
        self.log.dismiss_notification(nid)
        stats = self.log.get_stats()
        self.assertEqual(stats["total"], 3)
        self.assertEqual(stats["read"], 1)
        self.assertEqual(stats["unread"], 2)
        self.assertEqual(stats["dismissed"], 1)
        self.assertEqual(stats["agents"], 2)
        self.assertEqual(stats["severity_counts"]["info"], 2)
        self.assertEqual(stats["severity_counts"]["error"], 1)

    def test_reset(self):
        self.log.send_notification("agent-1", "A", "a")
        self.log.on_change("cb1", lambda e, d: None)
        self.log.reset()
        self.assertEqual(self.log.get_notification_count(), 0)
        self.assertEqual(len(self.log._callbacks), 0)

    def test_callbacks(self):
        events = []
        self.log.on_change("cb1", lambda e, d: events.append(e))
        self.log.send_notification("agent-1", "T", "M")
        self.assertEqual(events, ["notification_sent"])
        self.assertTrue(self.log.remove_callback("cb1"))
        self.assertFalse(self.log.remove_callback("cb1"))

    def test_pruning(self):
        for i in range(10050):
            self.log.send_notification("agent-1", f"T{i}", f"M{i}")
        self.assertLessEqual(self.log.get_notification_count(), 10000)

    def test_unique_ids(self):
        ids = set()
        for i in range(100):
            nid = self.log.send_notification("agent-1", "Same", "Same")
            ids.add(nid)
        self.assertEqual(len(ids), 100)


if __name__ == "__main__":
    unittest.main()
