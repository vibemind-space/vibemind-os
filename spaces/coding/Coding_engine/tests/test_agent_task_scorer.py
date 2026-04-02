"""Tests for AgentTaskScorer service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_scorer import AgentTaskScorer


class TestScoreBasic:
    """Basic score creation and retrieval."""

    def test_score_returns_id(self):
        svc = AgentTaskScorer()
        sid = svc.score("t1", "a1", score=0.8)
        assert sid.startswith("atsc-")
        assert len(sid) > 5

    def test_score_empty_task_id_returns_empty(self):
        svc = AgentTaskScorer()
        assert svc.score("", "a1") == ""

    def test_score_empty_agent_id_returns_empty(self):
        svc = AgentTaskScorer()
        assert svc.score("t1", "") == ""

    def test_get_score_existing(self):
        svc = AgentTaskScorer()
        sid = svc.score("t1", "a1", score=0.9, criteria="accuracy", notes="good")
        entry = svc.get_score(sid)
        assert entry is not None
        assert entry["task_id"] == "t1"
        assert entry["agent_id"] == "a1"
        assert entry["score"] == 0.9
        assert entry["criteria"] == "accuracy"
        assert entry["notes"] == "good"

    def test_get_score_nonexistent(self):
        svc = AgentTaskScorer()
        assert svc.get_score("atsc-nonexistent") is None

    def test_default_criteria_is_overall(self):
        svc = AgentTaskScorer()
        sid = svc.score("t1", "a1")
        entry = svc.get_score(sid)
        assert entry["criteria"] == "overall"

    def test_default_score_is_zero(self):
        svc = AgentTaskScorer()
        sid = svc.score("t1", "a1")
        entry = svc.get_score(sid)
        assert entry["score"] == 0.0


class TestScoreClamping:
    """Score values are clamped to 0.0-1.0."""

    def test_score_clamped_above_one(self):
        svc = AgentTaskScorer()
        sid = svc.score("t1", "a1", score=5.0)
        entry = svc.get_score(sid)
        assert entry["score"] == 1.0

    def test_score_clamped_below_zero(self):
        svc = AgentTaskScorer()
        sid = svc.score("t1", "a1", score=-2.0)
        entry = svc.get_score(sid)
        assert entry["score"] == 0.0


class TestMetadata:
    """Metadata deep-copy behaviour."""

    def test_metadata_stored(self):
        svc = AgentTaskScorer()
        sid = svc.score("t1", "a1", metadata={"key": "val"})
        entry = svc.get_score(sid)
        assert entry["metadata"] == {"key": "val"}

    def test_metadata_deep_copied(self):
        meta = {"nested": {"x": 1}}
        svc = AgentTaskScorer()
        sid = svc.score("t1", "a1", metadata=meta)
        meta["nested"]["x"] = 999
        entry = svc.get_score(sid)
        assert entry["metadata"]["nested"]["x"] == 1

    def test_metadata_default_empty(self):
        svc = AgentTaskScorer()
        sid = svc.score("t1", "a1")
        entry = svc.get_score(sid)
        assert entry["metadata"] == {}


class TestGetScores:
    """Querying multiple scores."""

    def test_get_scores_all(self):
        svc = AgentTaskScorer()
        svc.score("t1", "a1", score=0.5)
        svc.score("t2", "a2", score=0.7)
        results = svc.get_scores()
        assert len(results) == 2

    def test_get_scores_filter_by_agent(self):
        svc = AgentTaskScorer()
        svc.score("t1", "a1", score=0.5)
        svc.score("t2", "a2", score=0.7)
        svc.score("t3", "a1", score=0.9)
        results = svc.get_scores(agent_id="a1")
        assert len(results) == 2
        assert all(r["agent_id"] == "a1" for r in results)

    def test_get_scores_filter_by_task(self):
        svc = AgentTaskScorer()
        svc.score("t1", "a1", score=0.5)
        svc.score("t1", "a2", score=0.7)
        svc.score("t2", "a1", score=0.9)
        results = svc.get_scores(task_id="t1")
        assert len(results) == 2

    def test_get_scores_filter_by_criteria(self):
        svc = AgentTaskScorer()
        svc.score("t1", "a1", score=0.5, criteria="accuracy")
        svc.score("t2", "a1", score=0.7, criteria="speed")
        svc.score("t3", "a1", score=0.9, criteria="accuracy")
        results = svc.get_scores(criteria="accuracy")
        assert len(results) == 2
        assert all(r["criteria"] == "accuracy" for r in results)

    def test_get_scores_newest_first(self):
        svc = AgentTaskScorer()
        id1 = svc.score("t1", "a1", score=0.5)
        id2 = svc.score("t2", "a1", score=0.7)
        results = svc.get_scores()
        assert results[0]["score_id"] == id2
        assert results[1]["score_id"] == id1

    def test_get_scores_respects_limit(self):
        svc = AgentTaskScorer()
        for i in range(10):
            svc.score(f"t{i}", "a1", score=0.5)
        results = svc.get_scores(limit=3)
        assert len(results) == 3


class TestUpdateScore:
    """Updating existing scores."""

    def test_update_score_value(self):
        svc = AgentTaskScorer()
        sid = svc.score("t1", "a1", score=0.5)
        assert svc.update_score(sid, score=0.9) is True
        entry = svc.get_score(sid)
        assert entry["score"] == 0.9

    def test_update_notes(self):
        svc = AgentTaskScorer()
        sid = svc.score("t1", "a1")
        svc.update_score(sid, notes="improved")
        entry = svc.get_score(sid)
        assert entry["notes"] == "improved"

    def test_update_nonexistent_returns_false(self):
        svc = AgentTaskScorer()
        assert svc.update_score("atsc-nope", score=0.5) is False

    def test_update_changes_updated_at(self):
        svc = AgentTaskScorer()
        sid = svc.score("t1", "a1", score=0.5)
        before = svc.get_score(sid)["updated_at"]
        svc.update_score(sid, score=0.8)
        after = svc.get_score(sid)["updated_at"]
        assert after >= before

    def test_update_score_clamped(self):
        svc = AgentTaskScorer()
        sid = svc.score("t1", "a1", score=0.5)
        svc.update_score(sid, score=2.0)
        entry = svc.get_score(sid)
        assert entry["score"] == 1.0


class TestGetScoreCount:
    """Counting scores."""

    def test_count_all(self):
        svc = AgentTaskScorer()
        svc.score("t1", "a1", score=0.5)
        svc.score("t2", "a2", score=0.7)
        assert svc.get_score_count() == 2

    def test_count_by_agent(self):
        svc = AgentTaskScorer()
        svc.score("t1", "a1", score=0.5)
        svc.score("t2", "a2", score=0.7)
        svc.score("t3", "a1", score=0.9)
        assert svc.get_score_count(agent_id="a1") == 2
        assert svc.get_score_count(agent_id="a2") == 1

    def test_count_by_criteria(self):
        svc = AgentTaskScorer()
        svc.score("t1", "a1", score=0.5, criteria="accuracy")
        svc.score("t2", "a1", score=0.7, criteria="speed")
        assert svc.get_score_count(criteria="accuracy") == 1
        assert svc.get_score_count(criteria="speed") == 1

    def test_count_empty(self):
        svc = AgentTaskScorer()
        assert svc.get_score_count() == 0


class TestGetStats:
    """Statistics."""

    def test_stats_empty(self):
        svc = AgentTaskScorer()
        stats = svc.get_stats()
        assert stats["total_scores"] == 0
        assert stats["by_criteria"] == {}
        assert stats["avg_score"] == 0.0
        assert stats["unique_agents"] == 0

    def test_stats_populated(self):
        svc = AgentTaskScorer()
        svc.score("t1", "a1", score=0.5, criteria="accuracy")
        svc.score("t2", "a2", score=1.0, criteria="speed")
        svc.score("t3", "a1", score=0.25, criteria="accuracy")
        stats = svc.get_stats()
        assert stats["total_scores"] == 3
        assert stats["unique_agents"] == 2
        assert stats["by_criteria"]["accuracy"] == 2
        assert stats["by_criteria"]["speed"] == 1
        assert abs(stats["avg_score"] - 0.5833333333) < 0.01


class TestReset:
    """Reset clears all state."""

    def test_reset_clears_entries(self):
        svc = AgentTaskScorer()
        svc.score("t1", "a1", score=0.5)
        svc.reset()
        assert svc.get_score_count() == 0
        assert svc.get_stats()["total_scores"] == 0

    def test_reset_clears_on_change(self):
        svc = AgentTaskScorer()
        svc.on_change = lambda a, d: None
        svc.reset()
        assert svc.on_change is None


class TestCallbacks:
    """Callback and on_change behaviour."""

    def test_on_change_fires_on_score(self):
        events = []
        svc = AgentTaskScorer()
        svc.on_change = lambda action, data: events.append((action, data))
        svc.score("t1", "a1", score=0.5)
        assert len(events) == 1
        assert events[0][0] == "score_created"

    def test_on_change_fires_on_update(self):
        events = []
        svc = AgentTaskScorer()
        sid = svc.score("t1", "a1", score=0.5)
        svc.on_change = lambda action, data: events.append((action, data))
        svc.update_score(sid, score=0.8)
        assert len(events) == 1
        assert events[0][0] == "score_updated"

    def test_on_change_getter(self):
        svc = AgentTaskScorer()
        assert svc.on_change is None
        fn = lambda a, d: None
        svc.on_change = fn
        assert svc.on_change is fn

    def test_remove_callback(self):
        svc = AgentTaskScorer()
        svc._callbacks["cb1"] = lambda a, d: None
        assert svc.remove_callback("cb1") is True
        assert svc.remove_callback("cb1") is False

    def test_callback_exception_silenced(self):
        svc = AgentTaskScorer()
        svc.on_change = lambda a, d: (_ for _ in ()).throw(RuntimeError("boom"))
        sid = svc.score("t1", "a1", score=0.5)
        assert sid.startswith("atsc-")

    def test_named_callbacks_fire(self):
        events = []
        svc = AgentTaskScorer()
        svc._callbacks["my_cb"] = lambda action, data: events.append(action)
        svc.score("t1", "a1", score=0.5)
        assert "score_created" in events


class TestPruning:
    """Pruning when MAX_ENTRIES is exceeded."""

    def test_prune_evicts_oldest(self):
        svc = AgentTaskScorer()
        svc.MAX_ENTRIES = 5
        ids = []
        for i in range(6):
            ids.append(svc.score(f"t{i}", "a1", score=0.5))
        assert svc.get_score(ids[0]) is None
        assert svc.get_score_count() <= 5


class TestUniqueIds:
    """IDs are unique."""

    def test_unique_ids(self):
        svc = AgentTaskScorer()
        ids = set()
        for i in range(50):
            ids.add(svc.score(f"t{i}", "a1", score=0.5))
        assert len(ids) == 50


class TestReturnTypes:
    """All public methods return expected types."""

    def test_score_returns_dict_via_get(self):
        svc = AgentTaskScorer()
        sid = svc.score("t1", "a1", score=0.5)
        assert isinstance(svc.get_score(sid), dict)

    def test_get_scores_returns_list_of_dicts(self):
        svc = AgentTaskScorer()
        svc.score("t1", "a1", score=0.5)
        results = svc.get_scores()
        assert isinstance(results, list)
        assert all(isinstance(r, dict) for r in results)

    def test_get_stats_returns_dict(self):
        svc = AgentTaskScorer()
        assert isinstance(svc.get_stats(), dict)
