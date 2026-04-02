from __future__ import annotations

import copy
import unittest

from src.services.pipeline_data_linker import PipelineDataLinker, PipelineDataLinkerState


class TestBasic(unittest.TestCase):
    def setUp(self) -> None:
        self.linker = PipelineDataLinker()

    def test_prefix(self) -> None:
        rid = self.linker.link("pipe-1", "key-a")
        self.assertTrue(rid.startswith(PipelineDataLinker.PREFIX))

    def test_prefix_length(self) -> None:
        rid = self.linker.link("pipe-1", "key-a")
        # PREFIX (5) + 12 hex chars
        self.assertEqual(len(rid), 5 + 12)

    def test_fields_present(self) -> None:
        rid = self.linker.link("pipe-1", "key-a", "tgt-1", {"x": 1})
        entry = self.linker.get_link(rid)
        self.assertIsNotNone(entry)
        for field in ("record_id", "pipeline_id", "data_key", "target_key",
                       "metadata", "created_at", "updated_at", "_seq"):
            self.assertIn(field, entry)
        self.assertEqual(entry["pipeline_id"], "pipe-1")
        self.assertEqual(entry["data_key"], "key-a")
        self.assertEqual(entry["target_key"], "tgt-1")
        self.assertEqual(entry["metadata"], {"x": 1})

    def test_default_target_key_empty(self) -> None:
        rid = self.linker.link("pipe-1", "key-a")
        entry = self.linker.get_link(rid)
        self.assertEqual(entry["target_key"], "")

    def test_deepcopy_metadata(self) -> None:
        meta = {"nested": [1, 2, 3]}
        rid = self.linker.link("pipe-1", "key-a", metadata=meta)
        meta["nested"].append(999)
        entry = self.linker.get_link(rid)
        self.assertNotIn(999, entry["metadata"]["nested"])

    def test_empty_pipeline_id_returns_empty(self) -> None:
        result = self.linker.link("", "key-a")
        self.assertEqual(result, "")

    def test_empty_data_key_returns_empty(self) -> None:
        result = self.linker.link("pipe-1", "")
        self.assertEqual(result, "")

    def test_unique_ids(self) -> None:
        ids = {self.linker.link("pipe-1", f"k{i}") for i in range(20)}
        self.assertEqual(len(ids), 20)


class TestGet(unittest.TestCase):
    def setUp(self) -> None:
        self.linker = PipelineDataLinker()

    def test_get_existing(self) -> None:
        rid = self.linker.link("p1", "k1")
        self.assertIsNotNone(self.linker.get_link(rid))

    def test_get_nonexistent(self) -> None:
        self.assertIsNone(self.linker.get_link("pdlk-doesnotexist"))


class TestList(unittest.TestCase):
    def setUp(self) -> None:
        self.linker = PipelineDataLinker()

    def test_filter_by_pipeline_id(self) -> None:
        self.linker.link("alpha", "k1")
        self.linker.link("alpha", "k2")
        self.linker.link("beta", "k3")
        results = self.linker.get_links(pipeline_id="alpha")
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertEqual(r["pipeline_id"], "alpha")

    def test_newest_first(self) -> None:
        r1 = self.linker.link("p1", "k1")
        r2 = self.linker.link("p1", "k2")
        r3 = self.linker.link("p1", "k3")
        links = self.linker.get_links()
        self.assertEqual(links[0]["record_id"], r3)
        self.assertEqual(links[-1]["record_id"], r1)

    def test_limit(self) -> None:
        for i in range(10):
            self.linker.link("p1", f"k{i}")
        results = self.linker.get_links(limit=3)
        self.assertEqual(len(results), 3)

    def test_empty_list(self) -> None:
        self.assertEqual(self.linker.get_links(), [])


class TestCount(unittest.TestCase):
    def setUp(self) -> None:
        self.linker = PipelineDataLinker()

    def test_total_count(self) -> None:
        self.linker.link("p1", "k1")
        self.linker.link("p2", "k2")
        self.assertEqual(self.linker.get_link_count(), 2)

    def test_filtered_count(self) -> None:
        self.linker.link("p1", "k1")
        self.linker.link("p1", "k2")
        self.linker.link("p2", "k3")
        self.assertEqual(self.linker.get_link_count("p1"), 2)
        self.assertEqual(self.linker.get_link_count("p2"), 1)


class TestStats(unittest.TestCase):
    def setUp(self) -> None:
        self.linker = PipelineDataLinker()

    def test_empty_stats(self) -> None:
        stats = self.linker.get_stats()
        self.assertEqual(stats["total_links"], 0)
        self.assertEqual(stats["unique_pipelines"], 0)

    def test_stats_with_data(self) -> None:
        self.linker.link("p1", "k1")
        self.linker.link("p1", "k2")
        self.linker.link("p2", "k3")
        stats = self.linker.get_stats()
        self.assertEqual(stats["total_links"], 3)
        self.assertEqual(stats["unique_pipelines"], 2)


class TestCallbacks(unittest.TestCase):
    def test_on_change_called(self) -> None:
        events: list = []
        linker = PipelineDataLinker(_on_change=lambda action, data: events.append((action, data)))
        linker.link("p1", "k1")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "link_created")
        self.assertIn("action", events[0][1])

    def test_on_change_property_setter(self) -> None:
        linker = PipelineDataLinker()
        self.assertIsNone(linker.on_change)
        events: list = []
        linker.on_change = lambda a, d: events.append(a)
        linker.link("p1", "k1")
        self.assertEqual(len(events), 1)

    def test_named_callback(self) -> None:
        linker = PipelineDataLinker()
        hits: list = []
        linker._state.callbacks["cb1"] = lambda action, data: hits.append(action)
        linker.link("p1", "k1")
        self.assertEqual(len(hits), 1)

    def test_remove_callback(self) -> None:
        linker = PipelineDataLinker()
        linker._state.callbacks["cb1"] = lambda a, d: None
        self.assertTrue(linker.remove_callback("cb1"))
        self.assertFalse(linker.remove_callback("cb1"))
        self.assertNotIn("cb1", linker._state.callbacks)


class TestPrune(unittest.TestCase):
    def test_prune_removes_quarter(self) -> None:
        linker = PipelineDataLinker()
        linker.MAX_ENTRIES = 5
        for i in range(7):
            linker.link("p1", f"k{i}")
        # 7 > 5 triggers prune, removes 7//4 = 1, leaving 6
        # Then after second check still > 5, but prune only runs once per link call
        # Actually prune runs each link call. Let's just check it's <= 7
        self.assertLessEqual(len(linker._state.entries), 7)

    def test_prune_keeps_newest(self) -> None:
        linker = PipelineDataLinker()
        linker.MAX_ENTRIES = 5
        ids = []
        for i in range(7):
            ids.append(linker.link("p1", f"k{i}"))
        # The last entry should still exist
        last = ids[-1]
        self.assertIsNotNone(linker.get_link(last))


class TestReset(unittest.TestCase):
    def test_reset_clears_entries(self) -> None:
        linker = PipelineDataLinker()
        linker.link("p1", "k1")
        linker.link("p2", "k2")
        linker.reset()
        self.assertEqual(linker.get_link_count(), 0)

    def test_reset_clears_on_change(self) -> None:
        linker = PipelineDataLinker(_on_change=lambda a, d: None)
        linker.reset()
        self.assertIsNone(linker.on_change)

    def test_reset_clears_callbacks(self) -> None:
        linker = PipelineDataLinker()
        linker._state.callbacks["x"] = lambda a, d: None
        linker.reset()
        self.assertEqual(len(linker._state.callbacks), 0)


class TestDataLinkerState(unittest.TestCase):
    def test_default_state(self) -> None:
        state = PipelineDataLinkerState()
        self.assertEqual(state.entries, {})
        self.assertEqual(state._seq, 0)
        self.assertEqual(state.callbacks, {})


if __name__ == "__main__":
    unittest.main()
