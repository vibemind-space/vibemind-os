from __future__ import annotations

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "services"))

from agent_workflow_rotator import AgentWorkflowRotator


class TestAgentWorkflowRotator(unittest.TestCase):
    def setUp(self) -> None:
        self.rotator = AgentWorkflowRotator()

    # ------------------------------------------------------------------
    # ID / prefix
    # ------------------------------------------------------------------

    def test_prefix(self) -> None:
        rid = self.rotator.rotate("a1", "wf1")
        self.assertTrue(rid.startswith("awrt-"))

    # ------------------------------------------------------------------
    # Fields
    # ------------------------------------------------------------------

    def test_fields(self) -> None:
        rid = self.rotator.rotate("a1", "wf1", direction="backward", metadata={"k": "v"})
        rec = self.rotator.get_rotation(rid)
        self.assertIsNotNone(rec)
        self.assertEqual(rec["record_id"], rid)
        self.assertEqual(rec["agent_id"], "a1")
        self.assertEqual(rec["workflow_name"], "wf1")
        self.assertEqual(rec["direction"], "backward")
        self.assertEqual(rec["metadata"], {"k": "v"})
        self.assertIn("created_at", rec)
        self.assertIn("_seq", rec)

    # ------------------------------------------------------------------
    # Default direction
    # ------------------------------------------------------------------

    def test_default_direction(self) -> None:
        rid = self.rotator.rotate("a1", "wf1")
        rec = self.rotator.get_rotation(rid)
        self.assertEqual(rec["direction"], "forward")

    # ------------------------------------------------------------------
    # Deepcopy of metadata
    # ------------------------------------------------------------------

    def test_metadata_deepcopy(self) -> None:
        meta = {"nested": [1, 2, 3]}
        rid = self.rotator.rotate("a1", "wf1", metadata=meta)
        meta["nested"].append(999)
        rec = self.rotator.get_rotation(rid)
        self.assertNotIn(999, rec["metadata"]["nested"])

    # ------------------------------------------------------------------
    # Empty agent_id / workflow_name returns ""
    # ------------------------------------------------------------------

    def test_empty_agent_id_returns_empty(self) -> None:
        self.assertEqual(self.rotator.rotate("", "wf1"), "")

    def test_empty_workflow_returns_empty(self) -> None:
        self.assertEqual(self.rotator.rotate("a1", ""), "")

    # ------------------------------------------------------------------
    # get_rotation found / not found / copy
    # ------------------------------------------------------------------

    def test_get_rotation_found(self) -> None:
        rid = self.rotator.rotate("a1", "wf1")
        self.assertIsNotNone(self.rotator.get_rotation(rid))

    def test_get_rotation_not_found(self) -> None:
        self.assertIsNone(self.rotator.get_rotation("nonexistent"))

    def test_get_rotation_returns_copy(self) -> None:
        rid = self.rotator.rotate("a1", "wf1", metadata={"x": 1})
        r1 = self.rotator.get_rotation(rid)
        r2 = self.rotator.get_rotation(rid)
        self.assertEqual(r1, r2)
        r1["metadata"]["x"] = 999
        r3 = self.rotator.get_rotation(rid)
        self.assertEqual(r3["metadata"]["x"], 1)

    # ------------------------------------------------------------------
    # get_rotations (list)
    # ------------------------------------------------------------------

    def test_get_rotations_list(self) -> None:
        self.rotator.rotate("a1", "wf1")
        self.rotator.rotate("a1", "wf2")
        self.rotator.rotate("a2", "wf3")
        all_rots = self.rotator.get_rotations()
        self.assertEqual(len(all_rots), 3)
        # sorted descending by _seq
        seqs = [r["_seq"] for r in all_rots]
        self.assertEqual(seqs, sorted(seqs, reverse=True))

    def test_get_rotations_filtered(self) -> None:
        self.rotator.rotate("a1", "wf1")
        self.rotator.rotate("a2", "wf2")
        result = self.rotator.get_rotations(agent_id="a1")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["agent_id"], "a1")

    def test_get_rotations_limit(self) -> None:
        for i in range(10):
            self.rotator.rotate("a1", f"wf{i}")
        result = self.rotator.get_rotations(limit=3)
        self.assertEqual(len(result), 3)

    # ------------------------------------------------------------------
    # get_rotation_count
    # ------------------------------------------------------------------

    def test_count_all(self) -> None:
        self.rotator.rotate("a1", "wf1")
        self.rotator.rotate("a2", "wf2")
        self.assertEqual(self.rotator.get_rotation_count(), 2)

    def test_count_filtered(self) -> None:
        self.rotator.rotate("a1", "wf1")
        self.rotator.rotate("a1", "wf2")
        self.rotator.rotate("a2", "wf3")
        self.assertEqual(self.rotator.get_rotation_count(agent_id="a1"), 2)

    # ------------------------------------------------------------------
    # get_stats
    # ------------------------------------------------------------------

    def test_stats(self) -> None:
        self.rotator.rotate("a1", "wf1")
        self.rotator.rotate("a2", "wf2")
        self.rotator.rotate("a1", "wf3")
        stats = self.rotator.get_stats()
        self.assertEqual(stats["total_rotations"], 3)
        self.assertEqual(stats["unique_agents"], 2)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def test_on_change_callback(self) -> None:
        events = []
        self.rotator.on_change = lambda evt, data: events.append((evt, data))
        self.rotator.rotate("a1", "wf1")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "rotate")

    def test_named_callback(self) -> None:
        events = []
        self.rotator._state.callbacks["cb1"] = lambda evt, data: events.append(evt)
        self.rotator.rotate("a1", "wf1")
        self.assertEqual(events, ["rotate"])

    def test_remove_callback(self) -> None:
        self.rotator._state.callbacks["cb1"] = lambda e, d: None
        self.assertTrue(self.rotator.remove_callback("cb1"))
        self.assertFalse(self.rotator.remove_callback("cb1"))

    # ------------------------------------------------------------------
    # Prune
    # ------------------------------------------------------------------

    def test_prune(self) -> None:
        self.rotator.MAX_ENTRIES = 5
        for i in range(8):
            self.rotator.rotate(f"a{i}", f"wf{i}")
        # Prune fires whenever count > MAX_ENTRIES, removing oldest quarter each time
        self.assertLessEqual(len(self.rotator._state.entries), 8)
        self.assertGreater(len(self.rotator._state.entries), 0)
        # Verify the newest entries survived
        remaining_agents = {e["agent_id"] for e in self.rotator._state.entries.values()}
        self.assertIn("a7", remaining_agents)

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def test_reset(self) -> None:
        self.rotator.rotate("a1", "wf1")
        self.rotator.on_change = lambda e, d: None
        self.rotator.reset()
        self.assertEqual(self.rotator.get_rotation_count(), 0)
        self.assertIsNone(self.rotator.on_change)


if __name__ == "__main__":
    unittest.main()
