from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "services"))

from pipeline_data_compiler import PipelineDataCompiler


class TestBasic(unittest.TestCase):
    def setUp(self) -> None:
        self.compiler = PipelineDataCompiler()

    def test_prefix(self) -> None:
        rid = self.compiler.compile("p1", "k1")
        self.assertTrue(rid.startswith("pdcp-"))

    def test_fields_present(self) -> None:
        rid = self.compiler.compile("p1", "k1")
        rec = self.compiler.get_compilation(rid)
        self.assertIsNotNone(rec)
        for f in ("record_id", "pipeline_id", "data_key", "target", "metadata", "created_at", "updated_at", "_seq"):
            self.assertIn(f, rec)

    def test_default_target_is_binary(self) -> None:
        rid = self.compiler.compile("p1", "k1")
        rec = self.compiler.get_compilation(rid)
        self.assertEqual(rec["target"], "binary")

    def test_custom_target(self) -> None:
        rid = self.compiler.compile("p1", "k1", target="text")
        rec = self.compiler.get_compilation(rid)
        self.assertEqual(rec["target"], "text")

    def test_metadata_deepcopy(self) -> None:
        meta = {"nested": [1, 2, 3]}
        rid = self.compiler.compile("p1", "k1", metadata=meta)
        meta["nested"].append(999)
        rec = self.compiler.get_compilation(rid)
        self.assertNotIn(999, rec["metadata"]["nested"])

    def test_empty_pipeline_id_returns_empty(self) -> None:
        self.assertEqual(self.compiler.compile("", "k1"), "")

    def test_empty_data_key_returns_empty(self) -> None:
        self.assertEqual(self.compiler.compile("p1", ""), "")

    def test_both_empty_returns_empty(self) -> None:
        self.assertEqual(self.compiler.compile("", ""), "")


class TestGet(unittest.TestCase):
    def setUp(self) -> None:
        self.compiler = PipelineDataCompiler()

    def test_get_existing(self) -> None:
        rid = self.compiler.compile("p1", "k1")
        rec = self.compiler.get_compilation(rid)
        self.assertIsNotNone(rec)
        self.assertEqual(rec["record_id"], rid)

    def test_get_missing_returns_none(self) -> None:
        self.assertIsNone(self.compiler.get_compilation("nonexistent"))

    def test_get_returns_copy(self) -> None:
        rid = self.compiler.compile("p1", "k1")
        rec1 = self.compiler.get_compilation(rid)
        rec1["pipeline_id"] = "MODIFIED"
        rec2 = self.compiler.get_compilation(rid)
        self.assertEqual(rec2["pipeline_id"], "p1")


class TestList(unittest.TestCase):
    def setUp(self) -> None:
        self.compiler = PipelineDataCompiler()

    def test_get_all(self) -> None:
        self.compiler.compile("p1", "k1")
        self.compiler.compile("p2", "k2")
        results = self.compiler.get_compilations()
        self.assertEqual(len(results), 2)

    def test_filter_by_pipeline_id(self) -> None:
        self.compiler.compile("p1", "k1")
        self.compiler.compile("p1", "k2")
        self.compiler.compile("p2", "k3")
        results = self.compiler.get_compilations(pipeline_id="p1")
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertEqual(r["pipeline_id"], "p1")

    def test_newest_first(self) -> None:
        r1 = self.compiler.compile("p1", "k1")
        r2 = self.compiler.compile("p1", "k2")
        results = self.compiler.get_compilations()
        self.assertEqual(results[0]["record_id"], r2)
        self.assertEqual(results[1]["record_id"], r1)

    def test_limit(self) -> None:
        for i in range(10):
            self.compiler.compile("p1", f"k{i}")
        results = self.compiler.get_compilations(limit=3)
        self.assertEqual(len(results), 3)


class TestCount(unittest.TestCase):
    def setUp(self) -> None:
        self.compiler = PipelineDataCompiler()

    def test_total_count(self) -> None:
        self.compiler.compile("p1", "k1")
        self.compiler.compile("p2", "k2")
        self.assertEqual(self.compiler.get_compilation_count(), 2)

    def test_filtered_count(self) -> None:
        self.compiler.compile("p1", "k1")
        self.compiler.compile("p1", "k2")
        self.compiler.compile("p2", "k3")
        self.assertEqual(self.compiler.get_compilation_count(pipeline_id="p1"), 2)


class TestStats(unittest.TestCase):
    def test_stats(self) -> None:
        compiler = PipelineDataCompiler()
        compiler.compile("p1", "k1")
        compiler.compile("p1", "k2")
        compiler.compile("p2", "k3")
        stats = compiler.get_stats()
        self.assertEqual(stats["total_compilations"], 3)
        self.assertEqual(stats["unique_pipelines"], 2)


class TestCallbacks(unittest.TestCase):
    def test_on_change_fires(self) -> None:
        fired = []
        compiler = PipelineDataCompiler(on_change=lambda action, data: fired.append((action, data)))
        compiler.compile("p1", "k1")
        self.assertEqual(len(fired), 1)
        self.assertEqual(fired[0][0], "compile")
        self.assertIn("record_id", fired[0][1])

    def test_on_change_property_setter(self) -> None:
        compiler = PipelineDataCompiler()
        fired = []
        compiler.on_change = lambda action, data: fired.append(action)
        compiler.compile("p1", "k1")
        self.assertEqual(fired, ["compile"])

    def test_on_change_property_getter(self) -> None:
        compiler = PipelineDataCompiler()
        self.assertIsNone(compiler.on_change)
        fn = lambda a, d: None
        compiler.on_change = fn
        self.assertIs(compiler.on_change, fn)

    def test_named_callback(self) -> None:
        compiler = PipelineDataCompiler()
        fired = []
        compiler._state.callbacks["my_cb"] = lambda action, data: fired.append(action)
        compiler.compile("p1", "k1")
        self.assertEqual(fired, ["compile"])

    def test_remove_callback_true(self) -> None:
        compiler = PipelineDataCompiler()
        compiler._state.callbacks["my_cb"] = lambda a, d: None
        self.assertTrue(compiler.remove_callback("my_cb"))
        self.assertNotIn("my_cb", compiler._state.callbacks)

    def test_remove_callback_false(self) -> None:
        compiler = PipelineDataCompiler()
        self.assertFalse(compiler.remove_callback("nonexistent"))

    def test_callback_error_does_not_propagate(self) -> None:
        def bad_cb(action, data):
            raise RuntimeError("boom")

        compiler = PipelineDataCompiler(on_change=bad_cb)
        rid = compiler.compile("p1", "k1")
        self.assertTrue(rid.startswith("pdcp-"))


class TestPrune(unittest.TestCase):
    def test_prune_removes_oldest_quarter(self) -> None:
        compiler = PipelineDataCompiler()
        compiler.MAX_ENTRIES = 5
        ids = []
        for i in range(7):
            ids.append(compiler.compile("p1", f"k{i}"))
        # After adding 6th entry prune fires: 6 entries, remove 1 (6//4=1), left 5
        # After adding 7th entry prune fires: 6 entries, remove 1 (6//4=1), left 5
        count = compiler.get_compilation_count()
        self.assertLessEqual(count, 6)
        # The newest entries should survive
        last = compiler.get_compilation(ids[-1])
        self.assertIsNotNone(last)


class TestReset(unittest.TestCase):
    def test_reset_clears_entries(self) -> None:
        compiler = PipelineDataCompiler()
        compiler.compile("p1", "k1")
        compiler.reset()
        self.assertEqual(compiler.get_compilation_count(), 0)

    def test_reset_clears_on_change(self) -> None:
        compiler = PipelineDataCompiler(on_change=lambda a, d: None)
        compiler.reset()
        self.assertIsNone(compiler.on_change)

    def test_reset_clears_seq(self) -> None:
        compiler = PipelineDataCompiler()
        compiler.compile("p1", "k1")
        compiler.reset()
        self.assertEqual(compiler._state._seq, 0)


if __name__ == "__main__":
    unittest.main()
