from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "services"))

from agent_workflow_renamer import AgentWorkflowRenamer


class TestBasic(unittest.TestCase):
    def setUp(self) -> None:
        self.svc = AgentWorkflowRenamer()

    def test_prefix(self) -> None:
        rid = self.svc.rename("a1", "wf1")
        self.assertTrue(rid.startswith("awrn-"))

    def test_fields_present(self) -> None:
        rid = self.svc.rename("a1", "wf1", new_name="new_wf1", metadata={"k": "v"})
        entry = self.svc.get_rename(rid)
        self.assertIsNotNone(entry)
        for key in ("record_id", "agent_id", "workflow_name", "new_name", "metadata", "created_at", "updated_at", "_seq"):
            self.assertIn(key, entry)
        self.assertEqual(entry["agent_id"], "a1")
        self.assertEqual(entry["workflow_name"], "wf1")
        self.assertEqual(entry["new_name"], "new_wf1")
        self.assertEqual(entry["metadata"], {"k": "v"})

    def test_default_new_name_empty(self) -> None:
        rid = self.svc.rename("a1", "wf1")
        entry = self.svc.get_rename(rid)
        self.assertEqual(entry["new_name"], "")

    def test_metadata_deepcopy(self) -> None:
        meta = {"nested": [1, 2, 3]}
        rid = self.svc.rename("a1", "wf1", metadata=meta)
        meta["nested"].append(4)
        entry = self.svc.get_rename(rid)
        self.assertEqual(entry["metadata"]["nested"], [1, 2, 3])

    def test_empty_agent_id_returns_empty(self) -> None:
        result = self.svc.rename("", "wf1")
        self.assertEqual(result, "")

    def test_empty_workflow_name_returns_empty(self) -> None:
        result = self.svc.rename("a1", "")
        self.assertEqual(result, "")

    def test_both_empty_returns_empty(self) -> None:
        result = self.svc.rename("", "")
        self.assertEqual(result, "")


class TestGet(unittest.TestCase):
    def setUp(self) -> None:
        self.svc = AgentWorkflowRenamer()

    def test_get_existing(self) -> None:
        rid = self.svc.rename("a1", "wf1")
        entry = self.svc.get_rename(rid)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["record_id"], rid)

    def test_get_nonexistent(self) -> None:
        self.assertIsNone(self.svc.get_rename("awrn-nonexistent"))

    def test_get_returns_copy(self) -> None:
        rid = self.svc.rename("a1", "wf1")
        e1 = self.svc.get_rename(rid)
        e1["agent_id"] = "modified"
        e2 = self.svc.get_rename(rid)
        self.assertEqual(e2["agent_id"], "a1")


class TestList(unittest.TestCase):
    def setUp(self) -> None:
        self.svc = AgentWorkflowRenamer()

    def test_list_all(self) -> None:
        self.svc.rename("a1", "wf1")
        self.svc.rename("a2", "wf2")
        results = self.svc.get_renames()
        self.assertEqual(len(results), 2)

    def test_list_by_agent(self) -> None:
        self.svc.rename("a1", "wf1")
        self.svc.rename("a1", "wf2")
        self.svc.rename("a2", "wf3")
        results = self.svc.get_renames(agent_id="a1")
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r["agent_id"] == "a1" for r in results))

    def test_list_newest_first(self) -> None:
        r1 = self.svc.rename("a1", "wf1")
        r2 = self.svc.rename("a1", "wf2")
        results = self.svc.get_renames(agent_id="a1")
        self.assertEqual(results[0]["record_id"], r2)
        self.assertEqual(results[1]["record_id"], r1)

    def test_list_limit(self) -> None:
        for i in range(10):
            self.svc.rename("a1", f"wf{i}")
        results = self.svc.get_renames(limit=3)
        self.assertEqual(len(results), 3)


class TestCount(unittest.TestCase):
    def setUp(self) -> None:
        self.svc = AgentWorkflowRenamer()

    def test_count_all(self) -> None:
        self.svc.rename("a1", "wf1")
        self.svc.rename("a2", "wf2")
        self.assertEqual(self.svc.get_rename_count(), 2)

    def test_count_by_agent(self) -> None:
        self.svc.rename("a1", "wf1")
        self.svc.rename("a1", "wf2")
        self.svc.rename("a2", "wf3")
        self.assertEqual(self.svc.get_rename_count(agent_id="a1"), 2)
        self.assertEqual(self.svc.get_rename_count(agent_id="a2"), 1)

    def test_count_empty(self) -> None:
        self.assertEqual(self.svc.get_rename_count(), 0)


class TestStats(unittest.TestCase):
    def setUp(self) -> None:
        self.svc = AgentWorkflowRenamer()

    def test_stats_empty(self) -> None:
        stats = self.svc.get_stats()
        self.assertEqual(stats["total_renames"], 0)
        self.assertEqual(stats["unique_agents"], 0)

    def test_stats_with_data(self) -> None:
        self.svc.rename("a1", "wf1")
        self.svc.rename("a1", "wf2")
        self.svc.rename("a2", "wf3")
        stats = self.svc.get_stats()
        self.assertEqual(stats["total_renames"], 3)
        self.assertEqual(stats["unique_agents"], 2)


class TestCallbacks(unittest.TestCase):
    def setUp(self) -> None:
        self.svc = AgentWorkflowRenamer()

    def test_on_change_called(self) -> None:
        calls = []
        self.svc.on_change = lambda action, **kw: calls.append((action, kw))
        self.svc.rename("a1", "wf1")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "rename")

    def test_on_change_property(self) -> None:
        fn = lambda action, **kw: None
        self.svc.on_change = fn
        self.assertIs(self.svc.on_change, fn)

    def test_named_callback(self) -> None:
        calls = []
        self.svc._state.callbacks["cb1"] = lambda action, **kw: calls.append(action)
        self.svc.rename("a1", "wf1")
        self.assertEqual(calls, ["rename"])

    def test_remove_callback(self) -> None:
        self.svc._state.callbacks["cb1"] = lambda action, **kw: None
        self.assertTrue(self.svc.remove_callback("cb1"))
        self.assertFalse(self.svc.remove_callback("cb1"))

    def test_remove_nonexistent_callback(self) -> None:
        self.assertFalse(self.svc.remove_callback("nope"))


class TestPrune(unittest.TestCase):
    def test_prune_removes_oldest(self) -> None:
        svc = AgentWorkflowRenamer()
        svc.MAX_ENTRIES = 5
        ids = []
        for i in range(7):
            ids.append(svc.rename("a1", f"wf{i}"))
        # After adding 7 with MAX=5, prune should have removed a quarter when count exceeded 5
        # At count 6, prune removes 6//4=1 -> 5 remain. At count 6 again, prune removes 1 -> 5 remain.
        self.assertLessEqual(svc.get_rename_count(), 6)
        # The very first entry should have been pruned
        self.assertIsNone(svc.get_rename(ids[0]))


class TestReset(unittest.TestCase):
    def test_reset_clears_entries(self) -> None:
        svc = AgentWorkflowRenamer()
        svc.rename("a1", "wf1")
        svc.on_change = lambda action, **kw: None
        svc.reset()
        self.assertEqual(svc.get_rename_count(), 0)
        self.assertIsNone(svc.on_change)

    def test_reset_clears_callbacks(self) -> None:
        svc = AgentWorkflowRenamer()
        svc._state.callbacks["cb1"] = lambda action, **kw: None
        svc.reset()
        self.assertEqual(len(svc._state.callbacks), 0)

    def test_reset_resets_seq(self) -> None:
        svc = AgentWorkflowRenamer()
        svc.rename("a1", "wf1")
        svc.reset()
        self.assertEqual(svc._state._seq, 0)


if __name__ == "__main__":
    unittest.main()
