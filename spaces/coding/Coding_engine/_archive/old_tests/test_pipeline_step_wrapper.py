"""Tests for PipelineStepWrapper service."""

import sys
import unittest
import time

sys.path.insert(0, ".")
from src.services.pipeline_step_wrapper import PipelineStepWrapper, PipelineStepWrapperState


class TestPipelineStepWrapper(unittest.TestCase):

    def setUp(self):
        self.wrapper = PipelineStepWrapper()

    def test_register_wrapper_returns_id(self):
        wid = self.wrapper.register_wrapper("pipe1", "step1")
        self.assertTrue(wid.startswith("psw-"))
        self.assertEqual(len(wid), 4 + 16)  # prefix + hash

    def test_register_wrapper_default_type(self):
        wid = self.wrapper.register_wrapper("pipe1", "step1")
        entry = self.wrapper.get_wrapper(wid)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["wrapper_type"], "timing")
        self.assertEqual(entry["pipeline_id"], "pipe1")
        self.assertEqual(entry["step_name"], "step1")

    def test_register_wrapper_custom_type(self):
        wid = self.wrapper.register_wrapper("pipe1", "step1", wrapper_type="logging")
        entry = self.wrapper.get_wrapper(wid)
        self.assertEqual(entry["wrapper_type"], "logging")

    def test_get_wrapper_not_found(self):
        result = self.wrapper.get_wrapper("psw-nonexistent")
        self.assertIsNone(result)

    def test_wrap_execution_timing(self):
        self.wrapper.register_wrapper("pipe1", "step1", "timing")
        result = self.wrapper.wrap_execution("pipe1", "step1", lambda x: x * 2, 5)
        self.assertEqual(result["result"], 10)
        self.assertGreaterEqual(result["duration_ms"], 0)
        self.assertEqual(result["wrapper_type"], "timing")
        self.assertIsNone(result["error"])

    def test_wrap_execution_error_handler(self):
        self.wrapper.register_wrapper("pipe1", "step1", "error_handler")

        def failing_fn():
            raise ValueError("test error")

        result = self.wrapper.wrap_execution("pipe1", "step1", failing_fn)
        self.assertIsNone(result["result"])
        self.assertEqual(result["error"], "test error")
        self.assertEqual(result["wrapper_type"], "error_handler")

    def test_wrap_execution_raises_without_error_handler(self):
        self.wrapper.register_wrapper("pipe1", "step1", "timing")

        def failing_fn():
            raise ValueError("boom")

        with self.assertRaises(ValueError):
            self.wrapper.wrap_execution("pipe1", "step1", failing_fn)

    def test_get_wrappers_by_pipeline(self):
        self.wrapper.register_wrapper("pipe1", "step1")
        self.wrapper.register_wrapper("pipe1", "step2")
        self.wrapper.register_wrapper("pipe2", "step1")
        results = self.wrapper.get_wrappers("pipe1")
        self.assertEqual(len(results), 2)

    def test_get_wrappers_by_pipeline_and_step(self):
        self.wrapper.register_wrapper("pipe1", "step1")
        self.wrapper.register_wrapper("pipe1", "step2")
        results = self.wrapper.get_wrappers("pipe1", "step1")
        self.assertEqual(len(results), 1)

    def test_remove_wrapper(self):
        wid = self.wrapper.register_wrapper("pipe1", "step1")
        self.assertTrue(self.wrapper.remove_wrapper(wid))
        self.assertIsNone(self.wrapper.get_wrapper(wid))
        self.assertFalse(self.wrapper.remove_wrapper(wid))

    def test_get_execution_history(self):
        self.wrapper.register_wrapper("pipe1", "step1")
        self.wrapper.register_wrapper("pipe1", "step2")
        self.wrapper.wrap_execution("pipe1", "step1", lambda: "a")
        self.wrapper.wrap_execution("pipe1", "step2", lambda: "b")
        self.wrapper.wrap_execution("pipe1", "step1", lambda: "c")
        history = self.wrapper.get_execution_history("pipe1", "step1")
        self.assertEqual(len(history), 2)
        # Most recent first
        self.assertEqual(history[0]["result"], "c")

    def test_get_execution_history_limit(self):
        self.wrapper.register_wrapper("pipe1", "step1")
        for i in range(5):
            self.wrapper.wrap_execution("pipe1", "step1", lambda: i)
        history = self.wrapper.get_execution_history("pipe1", limit=3)
        self.assertEqual(len(history), 3)

    def test_get_wrapper_count(self):
        self.wrapper.register_wrapper("pipe1", "step1")
        self.wrapper.register_wrapper("pipe1", "step2")
        self.wrapper.register_wrapper("pipe2", "step1")
        self.assertEqual(self.wrapper.get_wrapper_count(), 3)
        self.assertEqual(self.wrapper.get_wrapper_count("pipe1"), 2)
        self.assertEqual(self.wrapper.get_wrapper_count("pipe2"), 1)

    def test_list_pipelines(self):
        self.wrapper.register_wrapper("pipe1", "step1")
        self.wrapper.register_wrapper("pipe2", "step1")
        self.wrapper.register_wrapper("pipe1", "step2")
        pipelines = self.wrapper.list_pipelines()
        self.assertEqual(pipelines, ["pipe1", "pipe2"])

    def test_get_stats(self):
        self.wrapper.register_wrapper("pipe1", "step1")
        self.wrapper.wrap_execution("pipe1", "step1", lambda: 42)
        stats = self.wrapper.get_stats()
        self.assertEqual(stats["total_wrappers"], 1)
        self.assertEqual(stats["total_executions"], 1)
        self.assertEqual(stats["pipelines"], 1)

    def test_reset(self):
        self.wrapper.register_wrapper("pipe1", "step1")
        self.wrapper.wrap_execution("pipe1", "step1", lambda: 42)
        self.wrapper.reset()
        self.assertEqual(self.wrapper.get_wrapper_count(), 0)
        self.assertEqual(len(self.wrapper.get_execution_history("pipe1")), 0)
        stats = self.wrapper.get_stats()
        self.assertEqual(stats["total_wrappers"], 0)

    def test_callbacks(self):
        events = []
        self.wrapper.on_change("cb1", lambda evt, data: events.append(evt))
        self.wrapper.register_wrapper("pipe1", "step1")
        self.assertIn("wrapper_registered", events)
        self.assertTrue(self.wrapper.remove_callback("cb1"))
        self.assertFalse(self.wrapper.remove_callback("cb1"))

    def test_unique_ids(self):
        ids = set()
        for i in range(50):
            wid = self.wrapper.register_wrapper("pipe1", f"step{i}")
            ids.add(wid)
        self.assertEqual(len(ids), 50)

    def test_prune_at_max(self):
        for i in range(10050):
            self.wrapper.register_wrapper(f"pipe{i}", "step1")
        self.assertLessEqual(self.wrapper.get_wrapper_count(), 10000)

    def test_wrap_execution_logging_type(self):
        self.wrapper.register_wrapper("pipe1", "step1", "logging")
        result = self.wrapper.wrap_execution("pipe1", "step1", lambda x: x + 1, 10)
        self.assertEqual(result["result"], 11)
        self.assertEqual(result["wrapper_type"], "logging")

    def test_state_dataclass(self):
        state = PipelineStepWrapperState()
        self.assertEqual(state.entries, {})
        self.assertEqual(state._seq, 0)


if __name__ == "__main__":
    unittest.main()
