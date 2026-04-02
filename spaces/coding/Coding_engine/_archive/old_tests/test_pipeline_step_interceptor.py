"""Tests for PipelineStepInterceptor service."""

import sys
import unittest

sys.path.insert(0, ".")
from src.services.pipeline_step_interceptor import PipelineStepInterceptor


class TestPipelineStepInterceptor(unittest.TestCase):

    def setUp(self):
        self.interceptor = PipelineStepInterceptor()

    def test_register_interceptor_returns_id(self):
        iid = self.interceptor.register_interceptor("pipe1", "step1")
        self.assertTrue(iid.startswith("psi-"))
        self.assertEqual(len(iid), 4 + 16)  # "psi-" + 16 hex chars

    def test_register_interceptor_default_type(self):
        iid = self.interceptor.register_interceptor("pipe1", "step1")
        interceptors = self.interceptor.get_interceptors("pipe1", "step1", "before")
        self.assertEqual(len(interceptors), 1)
        self.assertEqual(interceptors[0]["intercept_type"], "before")

    def test_register_interceptor_invalid_type(self):
        with self.assertRaises(ValueError):
            self.interceptor.register_interceptor("pipe1", "step1", intercept_type="invalid")

    def test_remove_interceptor(self):
        iid = self.interceptor.register_interceptor("pipe1", "step1")
        self.assertTrue(self.interceptor.remove_interceptor(iid))
        self.assertFalse(self.interceptor.remove_interceptor(iid))
        self.assertEqual(self.interceptor.get_interceptor_count(), 0)

    def test_execute_interceptors_no_fn(self):
        self.interceptor.register_interceptor("pipe1", "step1", "before")
        ctx = {"value": 42}
        result = self.interceptor.execute_interceptors("pipe1", "step1", "before", ctx)
        self.assertEqual(result, {"value": 42})

    def test_execute_interceptors_with_fn(self):
        def double_value(ctx):
            return {"value": ctx["value"] * 2}

        self.interceptor.register_interceptor("pipe1", "step1", "after", interceptor_fn=double_value)
        result = self.interceptor.execute_interceptors("pipe1", "step1", "after", {"value": 5})
        self.assertEqual(result["value"], 10)

    def test_execute_interceptors_chaining(self):
        def add_one(ctx):
            return {"value": ctx["value"] + 1}

        def add_ten(ctx):
            return {"value": ctx["value"] + 10}

        self.interceptor.register_interceptor("pipe1", "step1", "before", interceptor_fn=add_one)
        self.interceptor.register_interceptor("pipe1", "step1", "before", interceptor_fn=add_ten)
        result = self.interceptor.execute_interceptors("pipe1", "step1", "before", {"value": 0})
        self.assertEqual(result["value"], 11)

    def test_execute_interceptors_none_context(self):
        result = self.interceptor.execute_interceptors("pipe1", "step1", "before")
        self.assertEqual(result, {})

    def test_get_interceptors_filtering(self):
        self.interceptor.register_interceptor("pipe1", "step1", "before")
        self.interceptor.register_interceptor("pipe1", "step1", "after")
        self.interceptor.register_interceptor("pipe1", "step2", "before")
        self.interceptor.register_interceptor("pipe2", "step1", "before")

        self.assertEqual(len(self.interceptor.get_interceptors("pipe1")), 3)
        self.assertEqual(len(self.interceptor.get_interceptors("pipe1", "step1")), 2)
        self.assertEqual(len(self.interceptor.get_interceptors("pipe1", "step1", "before")), 1)
        self.assertEqual(len(self.interceptor.get_interceptors("pipe2")), 1)

    def test_get_interceptor_count(self):
        self.interceptor.register_interceptor("pipe1", "step1")
        self.interceptor.register_interceptor("pipe1", "step2")
        self.interceptor.register_interceptor("pipe2", "step1")
        self.assertEqual(self.interceptor.get_interceptor_count(), 3)
        self.assertEqual(self.interceptor.get_interceptor_count("pipe1"), 2)
        self.assertEqual(self.interceptor.get_interceptor_count("pipe2"), 1)

    def test_list_pipelines(self):
        self.interceptor.register_interceptor("beta", "step1")
        self.interceptor.register_interceptor("alpha", "step1")
        self.interceptor.register_interceptor("beta", "step2")
        pipelines = self.interceptor.list_pipelines()
        self.assertEqual(pipelines, ["alpha", "beta"])

    def test_get_stats(self):
        self.interceptor.register_interceptor("pipe1", "s1", "before")
        self.interceptor.register_interceptor("pipe1", "s2", "after")
        self.interceptor.register_interceptor("pipe2", "s1", "around")
        stats = self.interceptor.get_stats()
        self.assertEqual(stats["total_interceptors"], 3)
        self.assertEqual(stats["by_type"]["before"], 1)
        self.assertEqual(stats["by_type"]["after"], 1)
        self.assertEqual(stats["by_type"]["around"], 1)
        self.assertEqual(stats["by_pipeline"]["pipe1"], 2)
        self.assertEqual(stats["by_pipeline"]["pipe2"], 1)

    def test_reset(self):
        self.interceptor.register_interceptor("pipe1", "step1")
        self.interceptor.on_change("cb1", lambda a, d: None)
        self.interceptor.reset()
        self.assertEqual(self.interceptor.get_interceptor_count(), 0)
        self.assertEqual(len(self.interceptor._callbacks), 0)
        self.assertEqual(self.interceptor._state._seq, 0)

    def test_callbacks(self):
        events = []
        self.interceptor.on_change("tracker", lambda action, detail: events.append((action, detail)))
        self.interceptor.register_interceptor("pipe1", "step1")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "register")
        self.assertTrue(self.interceptor.remove_callback("tracker"))
        self.assertFalse(self.interceptor.remove_callback("tracker"))

    def test_execute_interceptor_fn_exception_handled(self):
        def bad_fn(ctx):
            raise RuntimeError("boom")

        self.interceptor.register_interceptor("pipe1", "step1", "before", interceptor_fn=bad_fn)
        result = self.interceptor.execute_interceptors("pipe1", "step1", "before", {"ok": True})
        self.assertEqual(result, {"ok": True})

    def test_pruning_at_max_entries(self):
        self.interceptor.MAX_ENTRIES = 5
        for i in range(7):
            self.interceptor.register_interceptor(f"pipe{i}", f"step{i}")
        self.assertLessEqual(self.interceptor.get_interceptor_count(), 5)

    def test_unique_ids(self):
        ids = set()
        for i in range(20):
            iid = self.interceptor.register_interceptor("pipe1", "step1", label=f"label{i}")
            ids.add(iid)
        self.assertEqual(len(ids), 20)


if __name__ == "__main__":
    unittest.main()
