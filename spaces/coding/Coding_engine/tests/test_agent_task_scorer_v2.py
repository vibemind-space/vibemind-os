from __future__ import annotations

import copy
import unittest

from src.services.agent_task_scorer_v2 import AgentTaskScorerV2


class TestBasic(unittest.TestCase):
    def setUp(self) -> None:
        self.scorer = AgentTaskScorerV2()

    def test_prefix(self) -> None:
        rid = self.scorer.score_v2("t1", "a1")
        self.assertTrue(rid.startswith("atsv-"))

    def test_fields_present(self) -> None:
        rid = self.scorer.score_v2("t1", "a1", score=3.5, metadata={"k": "v"})
        entry = self.scorer.get_score(rid)
        self.assertIsNotNone(entry)
        for key in ("record_id", "task_id", "agent_id", "score", "metadata", "created_at", "_seq"):
            self.assertIn(key, entry)
        self.assertEqual(entry["task_id"], "t1")
        self.assertEqual(entry["agent_id"], "a1")
        self.assertEqual(entry["score"], 3.5)
        self.assertEqual(entry["metadata"], {"k": "v"})

    def test_default_score_zero(self) -> None:
        rid = self.scorer.score_v2("t1", "a1")
        entry = self.scorer.get_score(rid)
        self.assertEqual(entry["score"], 0.0)

    def test_deepcopy_returned(self) -> None:
        rid = self.scorer.score_v2("t1", "a1", metadata={"x": 1})
        e1 = self.scorer.get_score(rid)
        e2 = self.scorer.get_score(rid)
        e1["metadata"]["x"] = 999
        self.assertEqual(e2["metadata"]["x"], 1)

    def test_empty_task_id_returns_empty(self) -> None:
        result = self.scorer.score_v2("", "a1")
        self.assertEqual(result, "")

    def test_empty_agent_id_returns_empty(self) -> None:
        result = self.scorer.score_v2("t1", "")
        self.assertEqual(result, "")


class TestGet(unittest.TestCase):
    def setUp(self) -> None:
        self.scorer = AgentTaskScorerV2()

    def test_found(self) -> None:
        rid = self.scorer.score_v2("t1", "a1")
        entry = self.scorer.get_score(rid)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["record_id"], rid)

    def test_not_found_returns_none(self) -> None:
        self.assertIsNone(self.scorer.get_score("nonexistent"))

    def test_get_returns_copy(self) -> None:
        rid = self.scorer.score_v2("t1", "a1")
        e = self.scorer.get_score(rid)
        e["score"] = 999
        original = self.scorer.get_score(rid)
        self.assertNotEqual(original["score"], 999)


class TestList(unittest.TestCase):
    def setUp(self) -> None:
        self.scorer = AgentTaskScorerV2()

    def test_all_scores(self) -> None:
        self.scorer.score_v2("t1", "a1")
        self.scorer.score_v2("t2", "a2")
        self.scorer.score_v2("t3", "a1")
        results = self.scorer.get_scores()
        self.assertEqual(len(results), 3)

    def test_filter_by_agent(self) -> None:
        self.scorer.score_v2("t1", "a1")
        self.scorer.score_v2("t2", "a2")
        self.scorer.score_v2("t3", "a1")
        results = self.scorer.get_scores(agent_id="a1")
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertEqual(r["agent_id"], "a1")

    def test_newest_first(self) -> None:
        self.scorer.score_v2("t1", "a1")
        self.scorer.score_v2("t2", "a1")
        rid3 = self.scorer.score_v2("t3", "a1")
        results = self.scorer.get_scores()
        self.assertEqual(results[0]["record_id"], rid3)


class TestCount(unittest.TestCase):
    def setUp(self) -> None:
        self.scorer = AgentTaskScorerV2()

    def test_total_count(self) -> None:
        self.scorer.score_v2("t1", "a1")
        self.scorer.score_v2("t2", "a2")
        self.assertEqual(self.scorer.get_score_count(), 2)

    def test_filtered_count(self) -> None:
        self.scorer.score_v2("t1", "a1")
        self.scorer.score_v2("t2", "a2")
        self.scorer.score_v2("t3", "a1")
        self.assertEqual(self.scorer.get_score_count(agent_id="a1"), 2)


class TestStats(unittest.TestCase):
    def test_stats(self) -> None:
        scorer = AgentTaskScorerV2()
        scorer.score_v2("t1", "a1")
        scorer.score_v2("t2", "a2")
        scorer.score_v2("t3", "a1")
        stats = scorer.get_stats()
        self.assertEqual(stats["total_scores"], 3)
        self.assertEqual(stats["unique_agents"], 2)


class TestCallbacks(unittest.TestCase):
    def test_callback_fires(self) -> None:
        on_change_fired = []
        cb_fired = []
        scorer = AgentTaskScorerV2(_on_change=lambda action, data: on_change_fired.append((action, data)))
        scorer.register_callback("cb1", lambda action, data: cb_fired.append((action, data)))
        scorer.score_v2("t1", "a1")
        self.assertEqual(len(on_change_fired), 1)
        self.assertEqual(on_change_fired[0][0], "score_added")
        self.assertIn("action", on_change_fired[0][1])
        self.assertEqual(len(cb_fired), 1)

    def test_remove_callback_true(self) -> None:
        scorer = AgentTaskScorerV2()
        scorer.register_callback("cb1", lambda a, d: None)
        self.assertTrue(scorer.remove_callback("cb1"))

    def test_remove_callback_false(self) -> None:
        scorer = AgentTaskScorerV2()
        self.assertFalse(scorer.remove_callback("nope"))


class TestPrune(unittest.TestCase):
    def test_prune_keeps_max(self) -> None:
        scorer = AgentTaskScorerV2()
        scorer.MAX_ENTRIES = 5
        for i in range(7):
            scorer.score_v2(f"t{i}", "a1")
        self.assertEqual(len(scorer._state.entries), 5)


class TestReset(unittest.TestCase):
    def test_clears_entries(self) -> None:
        scorer = AgentTaskScorerV2()
        scorer.score_v2("t1", "a1")
        scorer.reset()
        self.assertEqual(len(scorer._state.entries), 0)

    def test_on_change_none_after_reset(self) -> None:
        scorer = AgentTaskScorerV2(_on_change=lambda a, d: None)
        scorer.reset()
        self.assertIsNone(scorer._on_change)

    def test_seq_zero_after_reset(self) -> None:
        scorer = AgentTaskScorerV2()
        scorer.score_v2("t1", "a1")
        scorer.reset()
        self.assertEqual(scorer._state._seq, 0)


if __name__ == "__main__":
    unittest.main()
