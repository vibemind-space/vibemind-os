import sys
import unittest

sys.path.insert(0, ".")

from src.services.agent_connection_manager import AgentConnectionManager


class TestAgentConnectionManager(unittest.TestCase):

    def setUp(self):
        self.mgr = AgentConnectionManager()

    def test_connect_returns_id_with_prefix(self):
        cid = self.mgr.connect("agent-a", "agent-b")
        self.assertTrue(cid.startswith("acm-"))
        self.assertEqual(len(cid), 4 + 16)  # prefix + 16 hex chars

    def test_disconnect_existing(self):
        cid = self.mgr.connect("a", "b")
        self.assertTrue(self.mgr.disconnect(cid))

    def test_disconnect_nonexistent(self):
        self.assertFalse(self.mgr.disconnect("acm-doesnotexist"))

    def test_is_connected(self):
        self.mgr.connect("x", "y")
        self.assertTrue(self.mgr.is_connected("x", "y"))
        self.assertFalse(self.mgr.is_connected("y", "x"))

    def test_get_connections_directions(self):
        self.mgr.connect("a", "b")
        self.mgr.connect("c", "a")
        out = self.mgr.get_connections("a", direction="outgoing")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["to_agent"], "b")
        inc = self.mgr.get_connections("a", direction="incoming")
        self.assertEqual(len(inc), 1)
        self.assertEqual(inc[0]["from_agent"], "c")
        both = self.mgr.get_connections("a", direction="both")
        self.assertEqual(len(both), 2)

    def test_get_peers(self):
        self.mgr.connect("a", "b")
        self.mgr.connect("c", "a")
        peers = self.mgr.get_peers("a")
        self.assertCountEqual(peers, ["b", "c"])

    def test_get_connection(self):
        cid = self.mgr.connect("a", "b", connection_type="rpc")
        conn = self.mgr.get_connection(cid)
        self.assertIsNotNone(conn)
        self.assertEqual(conn["connection_type"], "rpc")
        self.assertIsNone(self.mgr.get_connection("acm-nope"))

    def test_get_connection_count(self):
        self.mgr.connect("a", "b")
        self.mgr.connect("a", "c")
        self.mgr.connect("d", "e")
        self.assertEqual(self.mgr.get_connection_count(), 3)
        self.assertEqual(self.mgr.get_connection_count("a"), 2)
        self.assertEqual(self.mgr.get_connection_count("d"), 1)
        self.assertEqual(self.mgr.get_connection_count("z"), 0)

    def test_list_agents(self):
        self.mgr.connect("a", "b")
        self.mgr.connect("c", "d")
        agents = self.mgr.list_agents()
        self.assertCountEqual(agents, ["a", "b", "c", "d"])

    def test_get_stats(self):
        self.mgr.connect("a", "b")
        stats = self.mgr.get_stats()
        self.assertEqual(stats["total_connections"], 1)
        self.assertEqual(stats["total_agents"], 2)
        self.assertGreaterEqual(stats["seq"], 1)

    def test_reset(self):
        self.mgr.connect("a", "b")
        self.mgr.on_change(lambda e, d: None)
        self.mgr.reset()
        self.assertEqual(self.mgr.get_connection_count(), 0)
        self.assertEqual(len(self.mgr._callbacks), 0)

    def test_callbacks_fire_and_remove(self):
        events = []
        cb_id = self.mgr.on_change(lambda e, d: events.append((e, d["id"])))
        cid = self.mgr.connect("a", "b")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "connect")
        self.mgr.disconnect(cid)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[1][0], "disconnect")
        self.assertTrue(self.mgr.remove_callback(cb_id))
        self.assertFalse(self.mgr.remove_callback(cb_id))

    def test_prune_at_max(self):
        self.mgr.MAX_ENTRIES = 10
        for i in range(15):
            self.mgr.connect(f"a{i}", f"b{i}")
        self.assertLessEqual(len(self.mgr._state.entries), 10)

    def test_unique_ids(self):
        ids = set()
        for i in range(50):
            ids.add(self.mgr.connect("a", "b"))
        self.assertEqual(len(ids), 50)


if __name__ == "__main__":
    unittest.main()
