"""Tests for PipelineDataSchema."""

import sys
import unittest

sys.path.insert(0, ".")
from src.services.pipeline_data_schema import PipelineDataSchema, PipelineDataSchemaState


class TestPipelineDataSchema(unittest.TestCase):

    def setUp(self):
        self.schema = PipelineDataSchema()

    def test_define_schema_returns_id(self):
        fields = {"name": {"type": "str", "required": True}}
        sid = self.schema.define_schema("pipe-1", fields)
        self.assertTrue(sid.startswith("pdsc-"))
        self.assertEqual(len(sid), 5 + 16)  # "pdsc-" + 16 hex chars

    def test_get_schema(self):
        fields = {"age": {"type": "int", "required": True}}
        self.schema.define_schema("pipe-2", fields)
        result = self.schema.get_schema("pipe-2")
        self.assertIsNotNone(result)
        self.assertEqual(result["pipeline_id"], "pipe-2")
        self.assertEqual(result["fields"]["age"]["type"], "int")

    def test_get_schema_not_found(self):
        result = self.schema.get_schema("nonexistent")
        self.assertIsNone(result)

    def test_validate_record_valid(self):
        fields = {
            "name": {"type": "str", "required": True},
            "count": {"type": "int", "required": False},
        }
        self.schema.define_schema("pipe-3", fields)
        result = self.schema.validate_record("pipe-3", {"name": "hello", "count": 5})
        self.assertTrue(result["valid"])
        self.assertEqual(result["errors"], [])

    def test_validate_record_missing_required(self):
        fields = {"name": {"type": "str", "required": True}}
        self.schema.define_schema("pipe-4", fields)
        result = self.schema.validate_record("pipe-4", {})
        self.assertFalse(result["valid"])
        self.assertTrue(any("Missing required" in e for e in result["errors"]))

    def test_validate_record_wrong_type(self):
        fields = {"count": {"type": "int", "required": True}}
        self.schema.define_schema("pipe-5", fields)
        result = self.schema.validate_record("pipe-5", {"count": "not_an_int"})
        self.assertFalse(result["valid"])
        self.assertTrue(any("expected type" in e for e in result["errors"]))

    def test_validate_record_no_schema(self):
        result = self.schema.validate_record("missing-pipe", {"x": 1})
        self.assertFalse(result["valid"])
        self.assertTrue(any("No schema found" in e for e in result["errors"]))

    def test_remove_schema(self):
        sid = self.schema.define_schema("pipe-6", {"x": {"type": "str", "required": False}})
        self.assertTrue(self.schema.remove_schema(sid))
        self.assertIsNone(self.schema.get_schema("pipe-6"))
        self.assertFalse(self.schema.remove_schema(sid))

    def test_infer_schema(self):
        records = [
            {"name": "Alice", "score": 95, "active": True},
            {"name": "Bob", "score": 88, "active": False},
        ]
        sid = self.schema.infer_schema("pipe-7", records)
        self.assertTrue(sid.startswith("pdsc-"))
        schema = self.schema.get_schema("pipe-7")
        self.assertIsNotNone(schema)
        self.assertEqual(schema["fields"]["name"]["type"], "str")
        self.assertEqual(schema["fields"]["score"]["type"], "int")
        self.assertEqual(schema["fields"]["active"]["type"], "bool")
        self.assertTrue(schema["fields"]["name"]["required"])

    def test_list_pipelines_and_count(self):
        self.schema.define_schema("p-a", {"x": {"type": "str", "required": False}})
        self.schema.define_schema("p-b", {"y": {"type": "int", "required": True}})
        pipelines = self.schema.list_pipelines()
        self.assertIn("p-a", pipelines)
        self.assertIn("p-b", pipelines)
        self.assertEqual(self.schema.get_schema_count(), 2)

    def test_callbacks(self):
        events = []
        self.schema.on_change("test_cb", lambda evt, data: events.append((evt, data)))
        self.schema.define_schema("pipe-cb", {"z": {"type": "float", "required": False}})
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "schema_defined")
        self.assertTrue(self.schema.remove_callback("test_cb"))
        self.assertFalse(self.schema.remove_callback("test_cb"))

    def test_get_stats_and_reset(self):
        self.schema.define_schema("pipe-s", {"a": {"type": "str", "required": True}})
        stats = self.schema.get_stats()
        self.assertEqual(stats["total_schemas"], 1)
        self.assertGreaterEqual(stats["seq"], 1)
        self.schema.reset()
        self.assertEqual(self.schema.get_schema_count(), 0)
        self.assertEqual(self.schema.list_pipelines(), [])

    def test_prune_max_entries(self):
        self.schema.MAX_ENTRIES = 5
        for i in range(8):
            self.schema.define_schema(f"prune-{i}", {"x": {"type": "str", "required": False}})
        self.assertLessEqual(self.schema.get_schema_count(), 5)

    def test_validate_with_default(self):
        fields = {"name": {"type": "str", "required": True, "default": "unknown"}}
        self.schema.define_schema("pipe-def", fields)
        result = self.schema.validate_record("pipe-def", {})
        self.assertTrue(result["valid"])

    def test_state_dataclass(self):
        state = PipelineDataSchemaState()
        self.assertEqual(state.entries, {})
        self.assertEqual(state._seq, 0)


if __name__ == "__main__":
    unittest.main()
