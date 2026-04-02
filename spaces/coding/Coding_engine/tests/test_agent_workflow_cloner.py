"""Tests for AgentWorkflowCloner service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_workflow_cloner import AgentWorkflowCloner


class TestCloneBasic:
    """Basic clone and retrieval."""

    def test_clone_returns_id(self):
        svc = AgentWorkflowCloner()
        cid = svc.clone_workflow("a1", "src_wf", "tgt_wf")
        assert cid.startswith("awcl-")
        assert len(cid) > 5

    def test_get_clone_existing(self):
        svc = AgentWorkflowCloner()
        cid = svc.clone_workflow("a1", "src_wf", "tgt_wf")
        entry = svc.get_clone(cid)
        assert entry is not None
        assert entry["agent_id"] == "a1"
        assert entry["source_workflow"] == "src_wf"
        assert entry["target_workflow"] == "tgt_wf"

    def test_get_clone_nonexistent(self):
        svc = AgentWorkflowCloner()
        assert svc.get_clone("awcl-nonexistent") is None

    def test_clone_has_created_at(self):
        svc = AgentWorkflowCloner()
        cid = svc.clone_workflow("a1", "src_wf", "tgt_wf")
        entry = svc.get_clone(cid)
        assert "created_at" in entry
        assert isinstance(entry["created_at"], float)

    def test_clone_has_seq(self):
        svc = AgentWorkflowCloner()
        cid = svc.clone_workflow("a1", "src_wf", "tgt_wf")
        entry = svc.get_clone(cid)
        assert "_seq" in entry

    def test_clone_returns_copy(self):
        svc = AgentWorkflowCloner()
        cid = svc.clone_workflow("a1", "src_wf", "tgt_wf")
        entry = svc.get_clone(cid)
        entry["agent_id"] = "mutated"
        assert svc.get_clone(cid)["agent_id"] == "a1"


class TestMetadata:
    """Metadata handling."""

    def test_metadata_stored(self):
        svc = AgentWorkflowCloner()
        cid = svc.clone_workflow("a1", "src_wf", "tgt_wf", metadata={"key": "val"})
        entry = svc.get_clone(cid)
        assert entry["metadata"] == {"key": "val"}

    def test_metadata_deep_copied(self):
        meta = {"nested": {"x": 1}}
        svc = AgentWorkflowCloner()
        cid = svc.clone_workflow("a1", "src_wf", "tgt_wf", metadata=meta)
        meta["nested"]["x"] = 999
        entry = svc.get_clone(cid)
        assert entry["metadata"]["nested"]["x"] == 1

    def test_metadata_default_empty(self):
        svc = AgentWorkflowCloner()
        cid = svc.clone_workflow("a1", "src_wf", "tgt_wf")
        entry = svc.get_clone(cid)
        assert entry["metadata"] == {}


class TestGetClones:
    """Querying multiple clones."""

    def test_get_all(self):
        svc = AgentWorkflowCloner()
        svc.clone_workflow("a1", "src1", "tgt1")
        svc.clone_workflow("a2", "src2", "tgt2")
        results = svc.get_clones()
        assert len(results) == 2

    def test_filter_by_agent(self):
        svc = AgentWorkflowCloner()
        svc.clone_workflow("a1", "src1", "tgt1")
        svc.clone_workflow("a2", "src2", "tgt2")
        svc.clone_workflow("a1", "src3", "tgt3")
        results = svc.get_clones(agent_id="a1")
        assert len(results) == 2
        assert all(r["agent_id"] == "a1" for r in results)

    def test_newest_first(self):
        svc = AgentWorkflowCloner()
        id1 = svc.clone_workflow("a1", "src1", "tgt1")
        id2 = svc.clone_workflow("a1", "src2", "tgt2")
        results = svc.get_clones()
        assert results[0]["clone_id"] == id2
        assert results[1]["clone_id"] == id1

    def test_respects_limit(self):
        svc = AgentWorkflowCloner()
        for i in range(10):
            svc.clone_workflow("a1", f"src{i}", f"tgt{i}")
        results = svc.get_clones(limit=3)
        assert len(results) == 3

    def test_empty(self):
        svc = AgentWorkflowCloner()
        results = svc.get_clones()
        assert results == []

    def test_returns_copies(self):
        svc = AgentWorkflowCloner()
        cid = svc.clone_workflow("a1", "src1", "tgt1")
        results = svc.get_clones()
        results[0]["agent_id"] = "mutated"
        entry = svc.get_clone(cid)
        assert entry["agent_id"] == "a1"


class TestGetCloneCount:
    """Counting clones."""

    def test_count_all(self):
        svc = AgentWorkflowCloner()
        svc.clone_workflow("a1", "src1", "tgt1")
        svc.clone_workflow("a2", "src2", "tgt2")
        assert svc.get_clone_count() == 2

    def test_count_by_agent(self):
        svc = AgentWorkflowCloner()
        svc.clone_workflow("a1", "src1", "tgt1")
        svc.clone_workflow("a2", "src2", "tgt2")
        svc.clone_workflow("a1", "src3", "tgt3")
        assert svc.get_clone_count(agent_id="a1") == 2
        assert svc.get_clone_count(agent_id="a2") == 1

    def test_count_empty(self):
        svc = AgentWorkflowCloner()
        assert svc.get_clone_count() == 0


class TestGetStats:
    """Statistics."""

    def test_stats_empty(self):
        svc = AgentWorkflowCloner()
        stats = svc.get_stats()
        assert stats["total_clones"] == 0
        assert stats["unique_agents"] == 0

    def test_stats_populated(self):
        svc = AgentWorkflowCloner()
        svc.clone_workflow("a1", "src1", "tgt1")
        svc.clone_workflow("a2", "src2", "tgt2")
        svc.clone_workflow("a1", "src3", "tgt3")
        stats = svc.get_stats()
        assert stats["total_clones"] == 3
        assert stats["unique_agents"] == 2

    def test_stats_returns_dict(self):
        svc = AgentWorkflowCloner()
        stats = svc.get_stats()
        assert isinstance(stats, dict)


class TestReset:
    """Reset clears all state."""

    def test_reset_clears_entries(self):
        svc = AgentWorkflowCloner()
        svc.clone_workflow("a1", "src1", "tgt1")
        svc.reset()
        assert svc.get_clone_count() == 0
        assert svc.get_stats()["total_clones"] == 0

    def test_reset_clears_callbacks(self):
        svc = AgentWorkflowCloner()
        svc._state.callbacks["cb1"] = lambda a, d: None
        svc.on_change = lambda a, d: None
        svc.reset()
        assert svc.on_change is None
        assert len(svc._state.callbacks) == 0

    def test_reset_allows_new_clones(self):
        svc = AgentWorkflowCloner()
        svc.clone_workflow("a1", "src1", "tgt1")
        svc.reset()
        cid = svc.clone_workflow("a2", "src2", "tgt2")
        assert cid.startswith("awcl-")
        assert svc.get_clone_count() == 1


class TestCallbacks:
    """Callback and on_change behaviour."""

    def test_on_change_fires_on_clone(self):
        events = []
        svc = AgentWorkflowCloner()
        svc.on_change = lambda action, data: events.append((action, data))
        svc.clone_workflow("a1", "src1", "tgt1")
        assert len(events) == 1
        assert events[0][0] == "cloned"

    def test_on_change_getter(self):
        svc = AgentWorkflowCloner()
        assert svc.on_change is None
        fn = lambda a, d: None
        svc.on_change = fn
        assert svc.on_change is fn

    def test_on_change_set_none(self):
        svc = AgentWorkflowCloner()
        svc.on_change = lambda a, d: None
        assert svc.on_change is not None
        svc.on_change = None
        assert svc.on_change is None

    def test_remove_callback(self):
        svc = AgentWorkflowCloner()
        svc._state.callbacks["cb1"] = lambda a, d: None
        assert svc.remove_callback("cb1") is True
        assert svc.remove_callback("cb1") is False

    def test_remove_callback_nonexistent(self):
        svc = AgentWorkflowCloner()
        assert svc.remove_callback("nope") is False

    def test_callback_exception_silenced(self):
        svc = AgentWorkflowCloner()
        svc.on_change = lambda a, d: (_ for _ in ()).throw(RuntimeError("boom"))
        cid = svc.clone_workflow("a1", "src1", "tgt1")
        assert cid.startswith("awcl-")

    def test_named_callbacks_fire(self):
        events = []
        svc = AgentWorkflowCloner()
        svc._state.callbacks["my_cb"] = lambda action, data: events.append(action)
        svc.clone_workflow("a1", "src1", "tgt1")
        assert "cloned" in events

    def test_named_callback_exception_silenced(self):
        svc = AgentWorkflowCloner()
        svc._state.callbacks["bad"] = lambda a, d: (_ for _ in ()).throw(ValueError("x"))
        cid = svc.clone_workflow("a1", "src1", "tgt1")
        assert cid.startswith("awcl-")


class TestPruning:
    """Pruning when MAX_ENTRIES is exceeded."""

    def test_prune_evicts_oldest_quarter(self):
        svc = AgentWorkflowCloner()
        svc.MAX_ENTRIES = 8
        ids = []
        for i in range(9):
            ids.append(svc.clone_workflow("a1", f"src{i}", f"tgt{i}"))
        assert svc.get_clone(ids[0]) is None
        assert svc.get_clone(ids[1]) is None
        assert svc.get_clone_count() <= 8

    def test_prune_keeps_newest(self):
        svc = AgentWorkflowCloner()
        svc.MAX_ENTRIES = 4
        ids = []
        for i in range(5):
            ids.append(svc.clone_workflow("a1", f"src{i}", f"tgt{i}"))
        assert svc.get_clone(ids[-1]) is not None


class TestUniqueIds:
    """IDs are unique."""

    def test_unique_ids(self):
        svc = AgentWorkflowCloner()
        ids = set()
        for i in range(50):
            ids.add(svc.clone_workflow("a1", f"src{i}", f"tgt{i}"))
        assert len(ids) == 50

    def test_id_prefix(self):
        svc = AgentWorkflowCloner()
        cid = svc.clone_workflow("a1", "src1", "tgt1")
        assert cid.startswith("awcl-")
