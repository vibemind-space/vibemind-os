"""Tests for AgentTaskEstimator service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_estimator import AgentTaskEstimator


class TestEstimateBasic:
    """Basic estimate and retrieval."""

    def test_estimate_returns_id(self):
        svc = AgentTaskEstimator()
        eid = svc.estimate("t1", "a1")
        assert eid.startswith("ates-")
        assert len(eid) > 5

    def test_estimate_empty_task_id_returns_empty(self):
        svc = AgentTaskEstimator()
        assert svc.estimate("", "a1") == ""

    def test_estimate_empty_agent_id_returns_empty(self):
        svc = AgentTaskEstimator()
        assert svc.estimate("t1", "") == ""

    def test_get_estimate_existing(self):
        svc = AgentTaskEstimator()
        eid = svc.estimate("t1", "a1", effort=3.0, unit="hours", confidence=0.8)
        entry = svc.get_estimate(eid)
        assert entry is not None
        assert entry["task_id"] == "t1"
        assert entry["agent_id"] == "a1"
        assert entry["effort"] == 3.0
        assert entry["unit"] == "hours"
        assert entry["confidence"] == 0.8

    def test_get_estimate_nonexistent(self):
        svc = AgentTaskEstimator()
        assert svc.get_estimate("ates-nonexistent") is None

    def test_default_values(self):
        svc = AgentTaskEstimator()
        eid = svc.estimate("t1", "a1")
        entry = svc.get_estimate(eid)
        assert entry["effort"] == 1.0
        assert entry["unit"] == "hours"
        assert entry["confidence"] == 0.5


class TestMetadata:
    """Metadata behaviour."""

    def test_metadata_stored(self):
        svc = AgentTaskEstimator()
        eid = svc.estimate("t1", "a1", metadata={"key": "val"})
        entry = svc.get_estimate(eid)
        assert entry["metadata"] == {"key": "val"}

    def test_metadata_deep_copied(self):
        meta = {"nested": {"x": 1}}
        svc = AgentTaskEstimator()
        eid = svc.estimate("t1", "a1", metadata=meta)
        meta["nested"]["x"] = 999
        entry = svc.get_estimate(eid)
        assert entry["metadata"]["nested"]["x"] == 1

    def test_metadata_default_empty(self):
        svc = AgentTaskEstimator()
        eid = svc.estimate("t1", "a1")
        entry = svc.get_estimate(eid)
        assert entry["metadata"] == {}


class TestGetEstimates:
    """Querying multiple estimates."""

    def test_get_estimates_all(self):
        svc = AgentTaskEstimator()
        svc.estimate("t1", "a1")
        svc.estimate("t2", "a2")
        results = svc.get_estimates()
        assert len(results) == 2

    def test_get_estimates_filter_by_agent(self):
        svc = AgentTaskEstimator()
        svc.estimate("t1", "a1")
        svc.estimate("t2", "a2")
        svc.estimate("t3", "a1")
        results = svc.get_estimates(agent_id="a1")
        assert len(results) == 2
        assert all(r["agent_id"] == "a1" for r in results)

    def test_get_estimates_filter_by_task(self):
        svc = AgentTaskEstimator()
        svc.estimate("t1", "a1")
        svc.estimate("t1", "a2")
        svc.estimate("t2", "a1")
        results = svc.get_estimates(task_id="t1")
        assert len(results) == 2
        assert all(r["task_id"] == "t1" for r in results)

    def test_get_estimates_newest_first(self):
        svc = AgentTaskEstimator()
        id1 = svc.estimate("t1", "a1")
        id2 = svc.estimate("t2", "a2")
        results = svc.get_estimates()
        assert results[0]["estimate_id"] == id2
        assert results[1]["estimate_id"] == id1

    def test_get_estimates_respects_limit(self):
        svc = AgentTaskEstimator()
        for i in range(10):
            svc.estimate(f"t{i}", "a1")
        results = svc.get_estimates(limit=3)
        assert len(results) == 3


class TestUpdateEstimate:
    """Updating existing estimates."""

    def test_update_effort(self):
        svc = AgentTaskEstimator()
        eid = svc.estimate("t1", "a1", effort=1.0)
        assert svc.update_estimate(eid, effort=5.0) is True
        entry = svc.get_estimate(eid)
        assert entry["effort"] == 5.0

    def test_update_confidence(self):
        svc = AgentTaskEstimator()
        eid = svc.estimate("t1", "a1", confidence=0.5)
        assert svc.update_estimate(eid, confidence=0.9) is True
        entry = svc.get_estimate(eid)
        assert entry["confidence"] == 0.9

    def test_update_both(self):
        svc = AgentTaskEstimator()
        eid = svc.estimate("t1", "a1", effort=1.0, confidence=0.5)
        assert svc.update_estimate(eid, effort=8.0, confidence=0.95) is True
        entry = svc.get_estimate(eid)
        assert entry["effort"] == 8.0
        assert entry["confidence"] == 0.95

    def test_update_nonexistent(self):
        svc = AgentTaskEstimator()
        assert svc.update_estimate("ates-nope", effort=2.0) is False


class TestGetEstimateCount:
    """Counting estimates."""

    def test_count_all(self):
        svc = AgentTaskEstimator()
        svc.estimate("t1", "a1")
        svc.estimate("t2", "a2")
        assert svc.get_estimate_count() == 2

    def test_count_by_agent(self):
        svc = AgentTaskEstimator()
        svc.estimate("t1", "a1")
        svc.estimate("t2", "a2")
        svc.estimate("t3", "a1")
        assert svc.get_estimate_count(agent_id="a1") == 2
        assert svc.get_estimate_count(agent_id="a2") == 1

    def test_count_empty(self):
        svc = AgentTaskEstimator()
        assert svc.get_estimate_count() == 0


class TestGetStats:
    """Statistics."""

    def test_stats_empty(self):
        svc = AgentTaskEstimator()
        stats = svc.get_stats()
        assert stats["total_estimates"] == 0
        assert stats["avg_effort"] == 0.0
        assert stats["avg_confidence"] == 0.0
        assert stats["unique_agents"] == 0

    def test_stats_populated(self):
        svc = AgentTaskEstimator()
        svc.estimate("t1", "a1", effort=2.0, confidence=0.6)
        svc.estimate("t2", "a2", effort=4.0, confidence=0.8)
        stats = svc.get_stats()
        assert stats["total_estimates"] == 2
        assert stats["avg_effort"] == 3.0
        assert stats["avg_confidence"] == 0.7
        assert stats["unique_agents"] == 2

    def test_stats_unique_agents(self):
        svc = AgentTaskEstimator()
        svc.estimate("t1", "a1")
        svc.estimate("t2", "a1")
        svc.estimate("t3", "a2")
        stats = svc.get_stats()
        assert stats["unique_agents"] == 2


class TestReset:
    """Reset clears all state."""

    def test_reset_clears_entries(self):
        svc = AgentTaskEstimator()
        svc.estimate("t1", "a1")
        svc.reset()
        assert svc.get_estimate_count() == 0
        assert svc.get_stats()["total_estimates"] == 0

    def test_reset_clears_callbacks(self):
        svc = AgentTaskEstimator()
        svc.on_change = lambda a, d: None
        svc._callbacks["cb1"] = lambda a, d: None
        svc.reset()
        assert svc.on_change is None
        assert len(svc._callbacks) == 0


class TestCallbacks:
    """Callback and on_change behaviour."""

    def test_on_change_fires_on_estimate(self):
        events = []
        svc = AgentTaskEstimator()
        svc.on_change = lambda action, data: events.append((action, data))
        svc.estimate("t1", "a1")
        assert len(events) == 1
        assert events[0][0] == "estimated"

    def test_on_change_fires_on_update(self):
        events = []
        svc = AgentTaskEstimator()
        eid = svc.estimate("t1", "a1")
        svc.on_change = lambda action, data: events.append((action, data))
        svc.update_estimate(eid, effort=5.0)
        assert len(events) == 1
        assert events[0][0] == "estimate_updated"

    def test_on_change_getter(self):
        svc = AgentTaskEstimator()
        assert svc.on_change is None
        fn = lambda a, d: None
        svc.on_change = fn
        assert svc.on_change is fn

    def test_remove_callback(self):
        svc = AgentTaskEstimator()
        svc._callbacks["cb1"] = lambda a, d: None
        assert svc.remove_callback("cb1") is True
        assert svc.remove_callback("cb1") is False

    def test_callback_exception_silenced(self):
        svc = AgentTaskEstimator()
        svc.on_change = lambda a, d: (_ for _ in ()).throw(RuntimeError("boom"))
        eid = svc.estimate("t1", "a1")
        assert eid.startswith("ates-")

    def test_named_callbacks_fire(self):
        events = []
        svc = AgentTaskEstimator()
        svc._callbacks["my_cb"] = lambda action, data: events.append(action)
        svc.estimate("t1", "a1")
        assert "estimated" in events


class TestPruning:
    """Pruning when MAX_ENTRIES is exceeded."""

    def test_prune_evicts_oldest(self):
        svc = AgentTaskEstimator()
        svc.MAX_ENTRIES = 5
        ids = []
        for i in range(6):
            ids.append(svc.estimate(f"t{i}", "a1"))
        assert svc.get_estimate(ids[0]) is None
        assert svc.get_estimate_count() <= 5


class TestUniqueIds:
    """IDs are unique."""

    def test_unique_ids(self):
        svc = AgentTaskEstimator()
        ids = set()
        for i in range(50):
            ids.add(svc.estimate(f"t{i}", "a1"))
        assert len(ids) == 50


class TestReturnTypes:
    """All public methods return dicts or expected types."""

    def test_estimate_returns_dict_via_get(self):
        svc = AgentTaskEstimator()
        eid = svc.estimate("t1", "a1")
        result = svc.get_estimate(eid)
        assert isinstance(result, dict)

    def test_get_estimates_returns_list_of_dicts(self):
        svc = AgentTaskEstimator()
        svc.estimate("t1", "a1")
        results = svc.get_estimates()
        assert isinstance(results, list)
        assert all(isinstance(r, dict) for r in results)

    def test_get_stats_returns_dict(self):
        svc = AgentTaskEstimator()
        assert isinstance(svc.get_stats(), dict)
