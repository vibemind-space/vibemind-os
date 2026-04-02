"""Tests for AgentConfigValidator."""

import sys
import unittest

sys.path.insert(0, ".")

from src.services.agent_config_validator import AgentConfigValidator


class TestAgentConfigValidator(unittest.TestCase):
    """Tests for the AgentConfigValidator service."""

    def setUp(self):
        self.validator = AgentConfigValidator()
        self.sample_schema = {
            "name": {"type": "str", "required": True},
            "max_retries": {"type": "int", "required": True},
            "timeout": {"type": "float", "required": False, "default": 30.0},
            "enabled": {"type": "bool", "required": False, "default": True},
            "tags": {"type": "list", "required": False, "default": []},
            "metadata": {"type": "dict", "required": False, "default": {}},
        }

    def test_define_schema_returns_id_with_prefix(self):
        schema_id = self.validator.define_schema("agent-1", self.sample_schema)
        self.assertTrue(schema_id.startswith("acv-"))
        self.assertGreater(len(schema_id), 4)

    def test_get_schema_returns_defined_schema(self):
        self.validator.define_schema("agent-1", self.sample_schema)
        result = self.validator.get_schema("agent-1")
        self.assertEqual(result, self.sample_schema)

    def test_get_schema_returns_none_for_missing(self):
        result = self.validator.get_schema("nonexistent")
        self.assertIsNone(result)

    def test_validate_valid_config(self):
        self.validator.define_schema("agent-1", self.sample_schema)
        config = {"name": "bot", "max_retries": 3, "timeout": 10.0}
        result = self.validator.validate("agent-1", config)
        self.assertTrue(result["valid"])
        self.assertEqual(result["errors"], [])

    def test_validate_missing_required_field(self):
        self.validator.define_schema("agent-1", self.sample_schema)
        config = {"name": "bot"}  # missing max_retries
        result = self.validator.validate("agent-1", config)
        self.assertFalse(result["valid"])
        self.assertTrue(any("max_retries" in e for e in result["errors"]))

    def test_validate_wrong_type(self):
        self.validator.define_schema("agent-1", self.sample_schema)
        config = {"name": "bot", "max_retries": "not_an_int"}
        result = self.validator.validate("agent-1", config)
        self.assertFalse(result["valid"])
        self.assertTrue(any("type" in e for e in result["errors"]))

    def test_validate_unknown_field_warning(self):
        self.validator.define_schema("agent-1", self.sample_schema)
        config = {"name": "bot", "max_retries": 3, "unknown_field": "val"}
        result = self.validator.validate("agent-1", config)
        self.assertTrue(result["valid"])
        self.assertTrue(any("unknown_field" in w for w in result["warnings"]))

    def test_validate_no_schema_error(self):
        result = self.validator.validate("no-agent", {"key": "val"})
        self.assertFalse(result["valid"])
        self.assertTrue(any("No schema" in e for e in result["errors"]))

    def test_remove_schema(self):
        schema_id = self.validator.define_schema("agent-1", self.sample_schema)
        self.assertTrue(self.validator.remove_schema(schema_id))
        self.assertIsNone(self.validator.get_schema("agent-1"))

    def test_remove_schema_returns_false_for_missing(self):
        self.assertFalse(self.validator.remove_schema("acv-nonexistent"))

    def test_get_defaults(self):
        self.validator.define_schema("agent-1", self.sample_schema)
        defaults = self.validator.get_defaults("agent-1")
        self.assertEqual(defaults["timeout"], 30.0)
        self.assertEqual(defaults["enabled"], True)
        self.assertEqual(defaults["tags"], [])
        self.assertEqual(defaults["metadata"], {})
        self.assertNotIn("name", defaults)

    def test_get_defaults_no_schema(self):
        defaults = self.validator.get_defaults("missing")
        self.assertEqual(defaults, {})

    def test_get_schema_count(self):
        self.assertEqual(self.validator.get_schema_count(), 0)
        self.validator.define_schema("a1", {"x": {"type": "str", "required": False}})
        self.validator.define_schema("a2", {"y": {"type": "int", "required": True}})
        self.assertEqual(self.validator.get_schema_count(), 2)

    def test_list_agents(self):
        self.validator.define_schema("zz-agent", {"f": {"type": "str", "required": False}})
        self.validator.define_schema("aa-agent", {"f": {"type": "str", "required": False}})
        agents = self.validator.list_agents()
        self.assertEqual(agents, ["aa-agent", "zz-agent"])

    def test_on_change_callback_fires(self):
        events = []
        self.validator.on_change("test_cb", lambda event, **kw: events.append(event))
        self.validator.define_schema("agent-1", self.sample_schema)
        self.assertIn("schema_defined", events)

    def test_remove_callback(self):
        self.validator.on_change("cb1", lambda e, **kw: None)
        self.assertTrue(self.validator.remove_callback("cb1"))
        self.assertFalse(self.validator.remove_callback("cb1"))

    def test_get_stats(self):
        self.validator.define_schema("agent-1", self.sample_schema)
        self.validator.validate("agent-1", {"name": "x", "max_retries": 1})
        stats = self.validator.get_stats()
        self.assertEqual(stats["total_defines"], 1)
        self.assertEqual(stats["total_validations"], 1)
        self.assertEqual(stats["schema_count"], 1)
        self.assertGreater(stats["seq"], 0)

    def test_reset(self):
        self.validator.define_schema("agent-1", self.sample_schema)
        self.validator.on_change("cb", lambda e, **kw: None)
        self.validator.reset()
        self.assertEqual(self.validator.get_schema_count(), 0)
        stats = self.validator.get_stats()
        self.assertEqual(stats["total_defines"], 0)
        self.assertEqual(stats["total_validations"], 0)

    def test_unique_schema_ids(self):
        ids = set()
        for i in range(50):
            sid = self.validator.define_schema(f"agent-{i}", {"f": {"type": "str", "required": False}})
            ids.add(sid)
        self.assertEqual(len(ids), 50)

    def test_default_warning_for_optional_with_default(self):
        self.validator.define_schema("agent-1", self.sample_schema)
        config = {"name": "bot", "max_retries": 3}
        result = self.validator.validate("agent-1", config)
        self.assertTrue(result["valid"])
        # Should warn about optional fields with defaults not provided
        self.assertTrue(any("default" in w for w in result["warnings"]))


if __name__ == "__main__":
    unittest.main()
