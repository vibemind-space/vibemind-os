"""Tests for PipelineStepFallback service."""

import sys
import unittest

sys.path.insert(0, ".")
from src.services.pipeline_step_fallback import PipelineStepFallback


class TestPipelineStepFallback(unittest.TestCase):
    def setUp(self):
        self.svc = PipelineStepFallback()

    def test_register_fallback(self):
        fid = self.svc.register_fallback("pipe1", "step1")
        self.assertTrue(fid.startswith("psf-"))
        self.assertEqual(len(fid), 4 + 16)

    def test_register_multiple_fallbacks(self):
        fid1 = self.svc.register_fallback("pipe1", "step1")
        fid2 = self.svc.register_fallback("pipe1", "step2")
        self.assertNotEqual(fid1, fid2)
        self.assertEqual(self.svc.get_fallback_count(), 2)

    def test_get_fallback(self):
        fid = self.svc.register_fallback("pipe1", "step1", fallback_type="skip")
        entry = self.svc.get_fallback(fid)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["pipeline_id"], "pipe1")
        self.assertEqual(entry["step_name"], "step1")
        self.assertEqual(entry["fallback_type"], "skip")

    def test_get_fallback_not_found(self):
        self.assertIsNone(self.svc.get_fallback("psf-nonexistent"))

    def test_execute_skip(self):
        self.svc.register_fallback("pipe1", "step1", fallback_type="skip")
        result = self.svc.execute_fallback("pipe1", "step1", error=Exception("fail"))
        self.assertEqual(result["fallback_type"], "skip")
        self.assertIsNone(result["result"])
        self.assertEqual(result["attempts"], 1)

    def test_execute_default_value(self):
        self.svc.register_fallback("pipe1", "step1", fallback_type="default_value")
        self.svc.set_default_value("pipe1", "step1", {"status": "ok"})
        result = self.svc.execute_fallback("pipe1", "step1", error=Exception("fail"))
        self.assertEqual(result["fallback_type"], "default_value")
        self.assertEqual(result["result"], {"status": "ok"})
        self.assertEqual(result["attempts"], 1)

    def test_execute_custom(self):
        custom_fn = lambda error, context: f"handled: {error}"
        self.svc.register_fallback("pipe1", "step1", fallback_fn=custom_fn, fallback_type="custom")
        result = self.svc.execute_fallback("pipe1", "step1", error="some_error", context={"key": "val"})
        self.assertEqual(result["fallback_type"], "custom")
        self.assertEqual(result["result"], "handled: some_error")

    def test_execute_retry(self):
        call_count = {"n": 0}

        def retry_fn(error, context):
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise RuntimeError("not yet")
            return "success"

        self.svc.register_fallback("pipe1", "step1", fallback_fn=retry_fn, fallback_type="retry", max_attempts=3)
        result = self.svc.execute_fallback("pipe1", "step1", error="err")
        self.assertEqual(result["result"], "success")
        self.assertEqual(result["attempts"], 3)

    def test_set_default_value(self):
        self.svc.register_fallback("pipe1", "step1", fallback_type="default_value")
        self.assertTrue(self.svc.set_default_value("pipe1", "step1", 42))
        self.assertFalse(self.svc.set_default_value("pipe1", "nonexistent", 42))

    def test_remove_fallback(self):
        fid = self.svc.register_fallback("pipe1", "step1")
        self.assertTrue(self.svc.remove_fallback(fid))
        self.assertFalse(self.svc.remove_fallback(fid))
        self.assertIsNone(self.svc.get_fallback(fid))

    def test_get_fallbacks_filter(self):
        self.svc.register_fallback("pipe1", "step1")
        self.svc.register_fallback("pipe1", "step2")
        self.svc.register_fallback("pipe2", "step1")
        all_pipe1 = self.svc.get_fallbacks("pipe1")
        self.assertEqual(len(all_pipe1), 2)
        filtered = self.svc.get_fallbacks("pipe1", step_name="step1")
        self.assertEqual(len(filtered), 1)

    def test_get_fallback_count(self):
        self.svc.register_fallback("pipe1", "step1")
        self.svc.register_fallback("pipe2", "step1")
        self.assertEqual(self.svc.get_fallback_count(), 2)
        self.assertEqual(self.svc.get_fallback_count("pipe1"), 1)

    def test_list_pipelines(self):
        self.svc.register_fallback("pipe1", "step1")
        self.svc.register_fallback("pipe2", "step1")
        pipelines = self.svc.list_pipelines()
        self.assertIn("pipe1", pipelines)
        self.assertIn("pipe2", pipelines)
        self.assertEqual(len(pipelines), 2)

    def test_callbacks(self):
        events = []
        self.svc.on_change("test_cb", lambda action, detail: events.append((action, detail)))
        self.svc.register_fallback("pipe1", "step1")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "register_fallback")
        self.assertTrue(self.svc.remove_callback("test_cb"))
        self.assertFalse(self.svc.remove_callback("test_cb"))

    def test_stats(self):
        self.svc.register_fallback("pipe1", "step1", fallback_type="skip")
        self.svc.register_fallback("pipe1", "step2", fallback_type="retry")
        stats = self.svc.get_stats()
        self.assertEqual(stats["total_fallbacks"], 2)
        self.assertEqual(stats["pipeline_count"], 1)
        self.assertIn("skip", stats["type_counts"])
        self.assertIn("retry", stats["type_counts"])

    def test_reset(self):
        self.svc.register_fallback("pipe1", "step1")
        self.svc.reset()
        self.assertEqual(self.svc.get_fallback_count(), 0)
        self.assertEqual(self.svc.get_stats()["total_fallbacks"], 0)

    def test_execute_no_fallback_registered(self):
        result = self.svc.execute_fallback("pipe1", "step1", error="err")
        self.assertIsNone(result["fallback_id"])
        self.assertEqual(result["attempts"], 0)


if __name__ == "__main__":
    unittest.main()
