import sys
import unittest

sys.path.insert(0, ".")
from src.services.pipeline_data_flattener import PipelineDataFlattener


class TestPipelineDataFlattener(unittest.TestCase):
    def setUp(self):
        self.flattener = PipelineDataFlattener()

    def test_configure_returns_id(self):
        config_id = self.flattener.configure("pipe1")
        self.assertTrue(config_id.startswith("pdf2-"))
        self.assertEqual(len(config_id), 5 + 16)

    def test_configure_custom_separator_and_depth(self):
        config_id = self.flattener.configure("pipe2", separator="/", max_depth=5)
        config = self.flattener.get_config("pipe2")
        self.assertIsNotNone(config)
        self.assertEqual(config["separator"], "/")
        self.assertEqual(config["max_depth"], 5)

    def test_flatten_nested_dict(self):
        self.flattener.configure("p1")
        result = self.flattener.flatten("p1", {"a": {"b": 1, "c": {"d": 2}}})
        self.assertEqual(result["a.b"], 1)
        self.assertEqual(result["a.c.d"], 2)

    def test_flatten_with_lists(self):
        self.flattener.configure("p2")
        result = self.flattener.flatten("p2", {"items": [10, 20, 30]})
        self.assertEqual(result["items.0"], 10)
        self.assertEqual(result["items.1"], 20)
        self.assertEqual(result["items.2"], 30)

    def test_flatten_custom_separator(self):
        self.flattener.configure("p3", separator="/")
        result = self.flattener.flatten("p3", {"a": {"b": 1}})
        self.assertEqual(result["a/b"], 1)

    def test_unflatten(self):
        self.flattener.configure("p4")
        flat = {"a.b": 1, "a.c": 2, "d": 3}
        result = self.flattener.unflatten("p4", flat)
        self.assertEqual(result["a"]["b"], 1)
        self.assertEqual(result["a"]["c"], 2)
        self.assertEqual(result["d"], 3)

    def test_flatten_unflatten_roundtrip(self):
        self.flattener.configure("p5")
        original = {"x": {"y": {"z": 42}}, "a": 1}
        flat = self.flattener.flatten("p5", original)
        restored = self.flattener.unflatten("p5", flat)
        self.assertEqual(restored, original)

    def test_callbacks_fire(self):
        events = []
        self.flattener.on_change("test_cb", lambda action, detail: events.append(action))
        self.flattener.configure("p6")
        self.assertIn("configure", events)

    def test_remove_callback(self):
        self.flattener.on_change("cb1", lambda a, d: None)
        self.assertTrue(self.flattener.remove_callback("cb1"))
        self.assertFalse(self.flattener.remove_callback("cb1"))

    def test_get_stats(self):
        self.flattener.configure("s1")
        self.flattener.configure("s2")
        stats = self.flattener.get_stats()
        self.assertEqual(stats["config_count"], 2)
        self.assertEqual(stats["total_entries"], 2)
        self.assertGreaterEqual(stats["seq"], 2)

    def test_reset(self):
        self.flattener.configure("r1")
        self.flattener.reset()
        stats = self.flattener.get_stats()
        self.assertEqual(stats["total_entries"], 0)
        self.assertIsNone(self.flattener.get_config("r1"))

    def test_remove_config(self):
        config_id = self.flattener.configure("rem1")
        self.assertTrue(self.flattener.remove_config(config_id))
        self.assertFalse(self.flattener.remove_config(config_id))
        self.assertIsNone(self.flattener.get_config("rem1"))

    def test_get_config_count(self):
        self.flattener.configure("gc1")
        self.flattener.configure("gc2")
        self.flattener.configure("gc2", separator="/")
        self.assertEqual(self.flattener.get_config_count(), 3)
        self.assertEqual(self.flattener.get_config_count("gc2"), 2)
        self.assertEqual(self.flattener.get_config_count("gc1"), 1)

    def test_list_pipelines(self):
        self.flattener.configure("lp1")
        self.flattener.configure("lp2")
        pipelines = self.flattener.list_pipelines()
        self.assertIn("lp1", pipelines)
        self.assertIn("lp2", pipelines)

    def test_flatten_no_config_raises(self):
        with self.assertRaises(ValueError):
            self.flattener.flatten("nonexistent", {"a": 1})

    def test_get_config_nonexistent(self):
        self.assertIsNone(self.flattener.get_config("nope"))


if __name__ == "__main__":
    unittest.main()
