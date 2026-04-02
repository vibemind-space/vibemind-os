"""Tests for AgentTaskClassifier service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_classifier import AgentTaskClassifier


class TestClassifyBasic:
    """Basic classify and retrieval."""

    def test_classify_returns_id(self):
        svc = AgentTaskClassifier()
        cid = svc.classify("t1")
        assert cid.startswith("atcl-")
        assert len(cid) > 5

    def test_classify_empty_task_id_returns_empty(self):
        svc = AgentTaskClassifier()
        assert svc.classify("") == ""

    def test_get_classification_existing(self):
        svc = AgentTaskClassifier()
        cid = svc.classify("t1", task_type="build", priority="high")
        entry = svc.get_classification(cid)
        assert entry is not None
        assert entry["task_id"] == "t1"
        assert entry["task_type"] == "build"
        assert entry["priority"] == "high"

    def test_get_classification_nonexistent(self):
        svc = AgentTaskClassifier()
        assert svc.get_classification("atcl-nonexistent") is None

    def test_default_type_and_priority(self):
        svc = AgentTaskClassifier()
        cid = svc.classify("t1")
        entry = svc.get_classification(cid)
        assert entry["task_type"] == "general"
        assert entry["priority"] == "normal"


class TestTagsAndMetadata:
    """Tags and metadata behaviour."""

    def test_tags_stored(self):
        svc = AgentTaskClassifier()
        cid = svc.classify("t1", tags=["ui", "backend"])
        entry = svc.get_classification(cid)
        assert entry["tags"] == ["ui", "backend"]

    def test_tags_default_empty(self):
        svc = AgentTaskClassifier()
        cid = svc.classify("t1")
        entry = svc.get_classification(cid)
        assert entry["tags"] == []

    def test_metadata_stored(self):
        svc = AgentTaskClassifier()
        cid = svc.classify("t1", metadata={"key": "val"})
        entry = svc.get_classification(cid)
        assert entry["metadata"] == {"key": "val"}

    def test_metadata_deep_copied(self):
        meta = {"nested": {"x": 1}}
        svc = AgentTaskClassifier()
        cid = svc.classify("t1", metadata=meta)
        meta["nested"]["x"] = 999
        entry = svc.get_classification(cid)
        assert entry["metadata"]["nested"]["x"] == 1

    def test_metadata_default_empty(self):
        svc = AgentTaskClassifier()
        cid = svc.classify("t1")
        entry = svc.get_classification(cid)
        assert entry["metadata"] == {}


class TestGetClassifications:
    """Querying multiple classifications."""

    def test_get_classifications_all(self):
        svc = AgentTaskClassifier()
        svc.classify("t1", task_type="build")
        svc.classify("t2", task_type="test")
        results = svc.get_classifications()
        assert len(results) == 2

    def test_get_classifications_filter_by_type(self):
        svc = AgentTaskClassifier()
        svc.classify("t1", task_type="build")
        svc.classify("t2", task_type="test")
        svc.classify("t3", task_type="build")
        results = svc.get_classifications(task_type="build")
        assert len(results) == 2
        assert all(r["task_type"] == "build" for r in results)

    def test_get_classifications_filter_by_priority(self):
        svc = AgentTaskClassifier()
        svc.classify("t1", priority="high")
        svc.classify("t2", priority="low")
        svc.classify("t3", priority="high")
        results = svc.get_classifications(priority="high")
        assert len(results) == 2

    def test_get_classifications_newest_first(self):
        svc = AgentTaskClassifier()
        id1 = svc.classify("t1")
        id2 = svc.classify("t2")
        results = svc.get_classifications()
        assert results[0]["classification_id"] == id2
        assert results[1]["classification_id"] == id1

    def test_get_classifications_respects_limit(self):
        svc = AgentTaskClassifier()
        for i in range(10):
            svc.classify(f"t{i}")
        results = svc.get_classifications(limit=3)
        assert len(results) == 3


class TestReclassify:
    """Reclassifying existing entries."""

    def test_reclassify_type(self):
        svc = AgentTaskClassifier()
        cid = svc.classify("t1", task_type="general")
        assert svc.reclassify(cid, task_type="build") is True
        entry = svc.get_classification(cid)
        assert entry["task_type"] == "build"

    def test_reclassify_priority(self):
        svc = AgentTaskClassifier()
        cid = svc.classify("t1", priority="normal")
        assert svc.reclassify(cid, priority="critical") is True
        entry = svc.get_classification(cid)
        assert entry["priority"] == "critical"

    def test_reclassify_nonexistent(self):
        svc = AgentTaskClassifier()
        assert svc.reclassify("atcl-nope", task_type="build") is False


class TestGetClassificationCount:
    """Counting classifications."""

    def test_count_all(self):
        svc = AgentTaskClassifier()
        svc.classify("t1")
        svc.classify("t2")
        assert svc.get_classification_count() == 2

    def test_count_by_type(self):
        svc = AgentTaskClassifier()
        svc.classify("t1", task_type="build")
        svc.classify("t2", task_type="test")
        svc.classify("t3", task_type="build")
        assert svc.get_classification_count(task_type="build") == 2
        assert svc.get_classification_count(task_type="test") == 1

    def test_count_by_priority(self):
        svc = AgentTaskClassifier()
        svc.classify("t1", priority="high")
        svc.classify("t2", priority="low")
        assert svc.get_classification_count(priority="high") == 1

    def test_count_empty(self):
        svc = AgentTaskClassifier()
        assert svc.get_classification_count() == 0


class TestGetStats:
    """Statistics."""

    def test_stats_empty(self):
        svc = AgentTaskClassifier()
        stats = svc.get_stats()
        assert stats["total_classifications"] == 0
        assert stats["by_type"] == {}
        assert stats["by_priority"] == {}

    def test_stats_populated(self):
        svc = AgentTaskClassifier()
        svc.classify("t1", task_type="build", priority="high")
        svc.classify("t2", task_type="test", priority="low")
        svc.classify("t3", task_type="build", priority="high")
        stats = svc.get_stats()
        assert stats["total_classifications"] == 3
        assert stats["by_type"] == {"build": 2, "test": 1}
        assert stats["by_priority"] == {"high": 2, "low": 1}


class TestReset:
    """Reset clears all state."""

    def test_reset_clears_entries(self):
        svc = AgentTaskClassifier()
        svc.classify("t1")
        svc.reset()
        assert svc.get_classification_count() == 0
        assert svc.get_stats()["total_classifications"] == 0


class TestCallbacks:
    """Callback and on_change behaviour."""

    def test_on_change_fires_on_classify(self):
        events = []
        svc = AgentTaskClassifier()
        svc.on_change = lambda action, data: events.append((action, data))
        svc.classify("t1")
        assert len(events) == 1
        assert events[0][0] == "classified"

    def test_on_change_fires_on_reclassify(self):
        events = []
        svc = AgentTaskClassifier()
        cid = svc.classify("t1")
        svc.on_change = lambda action, data: events.append((action, data))
        svc.reclassify(cid, task_type="build")
        assert len(events) == 1
        assert events[0][0] == "reclassified"

    def test_on_change_getter(self):
        svc = AgentTaskClassifier()
        assert svc.on_change is None
        fn = lambda a, d: None
        svc.on_change = fn
        assert svc.on_change is fn

    def test_remove_callback(self):
        svc = AgentTaskClassifier()
        svc._callbacks["cb1"] = lambda a, d: None
        assert svc.remove_callback("cb1") is True
        assert svc.remove_callback("cb1") is False

    def test_callback_exception_silenced(self):
        svc = AgentTaskClassifier()
        svc.on_change = lambda a, d: (_ for _ in ()).throw(RuntimeError("boom"))
        cid = svc.classify("t1")
        assert cid.startswith("atcl-")

    def test_named_callbacks_fire(self):
        events = []
        svc = AgentTaskClassifier()
        svc._callbacks["my_cb"] = lambda action, data: events.append(action)
        svc.classify("t1")
        assert "classified" in events


class TestPruning:
    """Pruning when MAX_ENTRIES is exceeded."""

    def test_prune_evicts_oldest(self):
        svc = AgentTaskClassifier()
        svc.MAX_ENTRIES = 5
        ids = []
        for i in range(6):
            ids.append(svc.classify(f"t{i}"))
        assert svc.get_classification(ids[0]) is None
        assert svc.get_classification_count() <= 5


class TestUniqueIds:
    """IDs are unique."""

    def test_unique_ids(self):
        svc = AgentTaskClassifier()
        ids = set()
        for i in range(50):
            ids.add(svc.classify(f"t{i}"))
        assert len(ids) == 50
