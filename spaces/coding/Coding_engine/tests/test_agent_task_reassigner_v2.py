from __future__ import annotations

import copy
import unittest

from src.services.agent_task_reassigner_v2 import (
    AgentTaskReassignerV2,
    AgentTaskReassignerV2State,
)


class TestBasic(unittest.TestCase):
    def setUp(self) -> None:
        self.r = AgentTaskReassignerV2()

    def test_prefix(self) -> None:
        rid = self.r.reassign_v2("t1", "a1")
        self.assertTrue(rid.startswith("atrv-"))

    def test_fields_stored(self) -> None:
        rid = self.r.reassign_v2("t1", "a1", new_agent="a2", metadata={"k": "v"})
        entry = self.r.get_reassignment(rid)
        assert entry is not None
        self.assertEqual(entry["task_id"], "t1")
        self.assertEqual(entry["agent_id"], "a1")
        self.assertEqual(entry["new_agent"], "a2")
        self.assertEqual(entry["metadata"], {"k": "v"})
        self.assertIn("created_at", entry)
        self.assertIn("_seq", entry)

    def test_default_new_agent_empty(self) -> None:
        rid = self.r.reassign_v2("t1", "a1")
        entry = self.r.get_reassignment(rid)
        assert entry is not None
        self.assertEqual(entry["new_agent"], "")

    def test_metadata_deepcopy(self) -> None:
        meta = {"nested": [1, 2]}
        rid = self.r.reassign_v2("t1", "a1", metadata=meta)
        meta["nested"].append(3)
        entry = self.r.get_reassignment(rid)
        assert entry is not None
        self.assertEqual(entry["metadata"]["nested"], [1, 2])

    def test_empty_task_id_returns_empty(self) -> None:
        self.assertEqual(self.r.reassign_v2("", "a1"), "")

    def test_empty_agent_id_returns_empty(self) -> None:
        self.assertEqual(self.r.reassign_v2("t1", ""), "")


class TestGet(unittest.TestCase):
    def setUp(self) -> None:
        self.r = AgentTaskReassignerV2()

    def test_found(self) -> None:
        rid = self.r.reassign_v2("t1", "a1")
        entry = self.r.get_reassignment(rid)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["record_id"], rid)

    def test_not_found_returns_none(self) -> None:
        self.assertIsNone(self.r.get_reassignment("nope"))

    def test_returns_copy(self) -> None:
        rid = self.r.reassign_v2("t1", "a1")
        e1 = self.r.get_reassignment(rid)
        e2 = self.r.get_reassignment(rid)
        self.assertEqual(e1, e2)
        assert e1 is not None and e2 is not None
        e1["task_id"] = "modified"
        e2_check = self.r.get_reassignment(rid)
        assert e2_check is not None
        self.assertEqual(e2_check["task_id"], "t1")


class TestList(unittest.TestCase):
    def setUp(self) -> None:
        self.r = AgentTaskReassignerV2()

    def test_all(self) -> None:
        self.r.reassign_v2("t1", "a1")
        self.r.reassign_v2("t2", "a2")
        self.assertEqual(len(self.r.get_reassignments()), 2)

    def test_filter_agent_id(self) -> None:
        self.r.reassign_v2("t1", "a1")
        self.r.reassign_v2("t2", "a2")
        self.r.reassign_v2("t3", "a1")
        result = self.r.get_reassignments(agent_id="a1")
        self.assertEqual(len(result), 2)
        for e in result:
            self.assertEqual(e["agent_id"], "a1")

    def test_newest_first_by_seq(self) -> None:
        r1 = self.r.reassign_v2("t1", "a1")
        r2 = self.r.reassign_v2("t2", "a1")
        r3 = self.r.reassign_v2("t3", "a1")
        result = self.r.get_reassignments()
        self.assertEqual(result[0]["record_id"], r3)
        self.assertEqual(result[1]["record_id"], r2)
        self.assertEqual(result[2]["record_id"], r1)

    def test_limit(self) -> None:
        for i in range(10):
            self.r.reassign_v2(f"t{i}", "a1")
        result = self.r.get_reassignments(limit=3)
        self.assertEqual(len(result), 3)


class TestCount(unittest.TestCase):
    def setUp(self) -> None:
        self.r = AgentTaskReassignerV2()

    def test_total(self) -> None:
        self.r.reassign_v2("t1", "a1")
        self.r.reassign_v2("t2", "a2")
        self.assertEqual(self.r.get_reassignment_count(), 2)

    def test_filtered_agent_id(self) -> None:
        self.r.reassign_v2("t1", "a1")
        self.r.reassign_v2("t2", "a2")
        self.r.reassign_v2("t3", "a1")
        self.assertEqual(self.r.get_reassignment_count(agent_id="a1"), 2)
        self.assertEqual(self.r.get_reassignment_count(agent_id="a2"), 1)


class TestStats(unittest.TestCase):
    def test_stats(self) -> None:
        r = AgentTaskReassignerV2()
        r.reassign_v2("t1", "a1")
        r.reassign_v2("t2", "a2")
        r.reassign_v2("t3", "a1")
        stats = r.get_stats()
        self.assertEqual(stats["total_reassignments"], 3)
        self.assertEqual(stats["unique_agents"], 2)


class TestCallbacks(unittest.TestCase):
    def test_on_change_fires(self) -> None:
        fired: list[dict] = []
        r = AgentTaskReassignerV2(_on_change=lambda action, data: fired.append(data))
        r.reassign_v2("t1", "a1")
        self.assertEqual(len(fired), 1)
        self.assertEqual(fired[0]["action"], "reassign")

    def test_state_callback_fires(self) -> None:
        fired: list[dict] = []
        r = AgentTaskReassignerV2()
        r.register_callback(lambda action, data: fired.append(data))
        r.reassign_v2("t1", "a1")
        self.assertEqual(len(fired), 1)
        self.assertEqual(fired[0]["action"], "reassign")

    def test_remove_callback_true(self) -> None:
        r = AgentTaskReassignerV2()
        cb_id = r.register_callback(lambda a, d: None)
        self.assertTrue(r.remove_callback(cb_id))

    def test_remove_callback_false(self) -> None:
        r = AgentTaskReassignerV2()
        self.assertFalse(r.remove_callback("nonexistent"))

    def test_removed_callback_no_longer_fires(self) -> None:
        fired: list[dict] = []
        r = AgentTaskReassignerV2()
        cb_id = r.register_callback(lambda a, d: fired.append(d))
        r.remove_callback(cb_id)
        r.reassign_v2("t1", "a1")
        self.assertEqual(len(fired), 0)


class TestPrune(unittest.TestCase):
    def test_prune_oldest(self) -> None:
        r = AgentTaskReassignerV2()
        r.MAX_ENTRIES = 5
        ids = []
        for i in range(7):
            ids.append(r.reassign_v2(f"t{i}", "a1"))
        self.assertEqual(r.get_reassignment_count(), 5)
        # oldest two should be gone
        self.assertIsNone(r.get_reassignment(ids[0]))
        self.assertIsNone(r.get_reassignment(ids[1]))
        # newest should remain
        self.assertIsNotNone(r.get_reassignment(ids[6]))


class TestReset(unittest.TestCase):
    def test_clears_entries(self) -> None:
        r = AgentTaskReassignerV2()
        r.reassign_v2("t1", "a1")
        r.reset()
        self.assertEqual(r.get_reassignment_count(), 0)

    def test_on_change_none(self) -> None:
        r = AgentTaskReassignerV2(_on_change=lambda a, d: None)
        r.reset()
        self.assertIsNone(r._on_change)

    def test_seq_reset(self) -> None:
        r = AgentTaskReassignerV2()
        r.reassign_v2("t1", "a1")
        r.reset()
        self.assertEqual(r._state._seq, 0)


if __name__ == "__main__":
    unittest.main()
