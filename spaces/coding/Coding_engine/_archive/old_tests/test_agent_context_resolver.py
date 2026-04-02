"""Tests for AgentContextResolver."""

import sys
import unittest

sys.path.insert(0, ".")
from src.services.agent_context_resolver import AgentContextResolver


class TestAgentContextResolver(unittest.TestCase):

    def setUp(self):
        self.resolver = AgentContextResolver()

    def test_register_source(self):
        sid = self.resolver.register_source("agent1", "env", {"host": "localhost"})
        self.assertTrue(sid.startswith("acr-"))
        self.assertEqual(len(sid), 4 + 16)  # prefix + hash

    def test_resolve_found(self):
        self.resolver.register_source("agent1", "env", {"host": "localhost", "port": "8080"})
        self.assertEqual(self.resolver.resolve("agent1", "host"), "localhost")
        self.assertEqual(self.resolver.resolve("agent1", "port"), "8080")

    def test_resolve_not_found(self):
        self.resolver.register_source("agent1", "env", {"host": "localhost"})
        self.assertIsNone(self.resolver.resolve("agent1", "missing_key"))
        self.assertIsNone(self.resolver.resolve("agent2", "host"))

    def test_resolve_template(self):
        self.resolver.register_source("agent1", "env", {"host": "localhost", "port": "8080"})
        result = self.resolver.resolve_template("agent1", "http://{host}:{port}/api")
        self.assertEqual(result, "http://localhost:8080/api")

    def test_resolve_template_partial(self):
        self.resolver.register_source("agent1", "env", {"host": "localhost"})
        result = self.resolver.resolve_template("agent1", "{host}:{missing}")
        self.assertEqual(result, "localhost:{missing}")

    def test_get_sources(self):
        self.resolver.register_source("agent1", "env", {"a": "1"})
        self.resolver.register_source("agent1", "config", {"b": "2"})
        self.resolver.register_source("agent2", "env", {"c": "3"})
        sources = self.resolver.get_sources("agent1")
        self.assertEqual(len(sources), 2)
        names = {s["source_name"] for s in sources}
        self.assertEqual(names, {"env", "config"})

    def test_remove_source(self):
        sid = self.resolver.register_source("agent1", "env", {"host": "localhost"})
        self.assertTrue(self.resolver.remove_source(sid))
        self.assertFalse(self.resolver.remove_source(sid))
        self.assertEqual(self.resolver.get_source_count(), 0)

    def test_update_source(self):
        sid = self.resolver.register_source("agent1", "env", {"host": "localhost"})
        self.assertTrue(self.resolver.update_source(sid, {"host": "remote", "port": "9090"}))
        self.assertEqual(self.resolver.resolve("agent1", "host"), "remote")
        self.assertEqual(self.resolver.resolve("agent1", "port"), "9090")

    def test_update_source_not_found(self):
        self.assertFalse(self.resolver.update_source("acr-nonexistent", {"a": "1"}))

    def test_get_source_count(self):
        self.resolver.register_source("agent1", "env", {"a": "1"})
        self.resolver.register_source("agent1", "config", {"b": "2"})
        self.resolver.register_source("agent2", "env", {"c": "3"})
        self.assertEqual(self.resolver.get_source_count(), 3)
        self.assertEqual(self.resolver.get_source_count("agent1"), 2)
        self.assertEqual(self.resolver.get_source_count("agent2"), 1)
        self.assertEqual(self.resolver.get_source_count("agent3"), 0)

    def test_list_agents(self):
        self.resolver.register_source("agent2", "env", {"a": "1"})
        self.resolver.register_source("agent1", "config", {"b": "2"})
        agents = self.resolver.list_agents()
        self.assertEqual(agents, ["agent1", "agent2"])

    def test_get_stats(self):
        self.resolver.register_source("agent1", "env", {"a": "1"})
        stats = self.resolver.get_stats()
        self.assertEqual(stats["total_sources"], 1)
        self.assertEqual(stats["total_agents"], 1)
        self.assertGreater(stats["seq"], 0)
        self.assertGreaterEqual(stats["uptime"], 0)

    def test_on_change_and_remove_callback(self):
        events = []
        cb_id = self.resolver.on_change(lambda evt, data: events.append((evt, data)))
        self.resolver.register_source("agent1", "env", {"a": "1"})
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "register")
        self.assertTrue(self.resolver.remove_callback(cb_id))
        self.assertFalse(self.resolver.remove_callback(cb_id))

    def test_reset(self):
        self.resolver.register_source("agent1", "env", {"a": "1"})
        self.resolver.on_change(lambda e, d: None)
        self.resolver.reset()
        self.assertEqual(self.resolver.get_source_count(), 0)
        self.assertEqual(self.resolver.list_agents(), [])

    def test_prune_max_entries(self):
        resolver = AgentContextResolver()
        resolver.MAX_ENTRIES = 10
        for i in range(15):
            resolver.register_source(f"agent{i}", "src", {"k": str(i)})
        self.assertLessEqual(resolver.get_source_count(), 10)

    def test_resolve_first_match(self):
        self.resolver.register_source("agent1", "primary", {"key": "first"})
        self.resolver.register_source("agent1", "secondary", {"key": "second"})
        self.assertEqual(self.resolver.resolve("agent1", "key"), "first")


if __name__ == "__main__":
    unittest.main()
