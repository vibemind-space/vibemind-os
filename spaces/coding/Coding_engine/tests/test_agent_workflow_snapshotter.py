"""Tests for AgentWorkflowSnapshotter service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_workflow_snapshotter import AgentWorkflowSnapshotter

class TestIdGeneration:
    def test_prefix(self):
        s = AgentWorkflowSnapshotter()
        assert s.snapshot("a1", "wf1").startswith("awsn-")
    def test_unique(self):
        s = AgentWorkflowSnapshotter()
        ids = {s.snapshot("a1", f"wf{i}") for i in range(20)}
        assert len(ids) == 20

class TestSnapshotBasic:
    def test_returns_id(self):
        s = AgentWorkflowSnapshotter()
        assert len(s.snapshot("a1", "wf1")) > 0
    def test_stores_fields(self):
        s = AgentWorkflowSnapshotter()
        rid = s.snapshot("a1", "wf1", label="v1")
        e = s.get_snapshot(rid)
        assert e["agent_id"] == "a1"
        assert e["workflow_name"] == "wf1"
        assert e["label"] == "v1"
    def test_with_metadata(self):
        s = AgentWorkflowSnapshotter()
        rid = s.snapshot("a1", "wf1", metadata={"x": 1})
        assert s.get_snapshot(rid)["metadata"]["x"] == 1
    def test_metadata_deepcopy(self):
        s = AgentWorkflowSnapshotter()
        m = {"a": [1]}
        rid = s.snapshot("a1", "wf1", metadata=m)
        m["a"].append(2)
        assert s.get_snapshot(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = AgentWorkflowSnapshotter()
        before = time.time()
        rid = s.snapshot("a1", "wf1")
        assert s.get_snapshot(rid)["created_at"] >= before
    def test_empty_agent_returns_empty(self):
        assert AgentWorkflowSnapshotter().snapshot("", "wf1") == ""
    def test_empty_workflow_returns_empty(self):
        assert AgentWorkflowSnapshotter().snapshot("a1", "") == ""

class TestGetSnapshot:
    def test_found(self):
        s = AgentWorkflowSnapshotter()
        rid = s.snapshot("a1", "wf1")
        assert s.get_snapshot(rid) is not None
    def test_not_found(self):
        assert AgentWorkflowSnapshotter().get_snapshot("xxx") is None
    def test_returns_copy(self):
        s = AgentWorkflowSnapshotter()
        rid = s.snapshot("a1", "wf1")
        assert s.get_snapshot(rid) is not s.get_snapshot(rid)

class TestGetSnapshots:
    def test_all(self):
        s = AgentWorkflowSnapshotter()
        s.snapshot("a1", "wf1"); s.snapshot("a2", "wf2")
        assert len(s.get_snapshots()) == 2
    def test_filter(self):
        s = AgentWorkflowSnapshotter()
        s.snapshot("a1", "wf1"); s.snapshot("a2", "wf2")
        assert len(s.get_snapshots(agent_id="a1")) == 1
    def test_newest_first(self):
        s = AgentWorkflowSnapshotter()
        s.snapshot("a1", "wf1"); s.snapshot("a1", "wf2")
        assert s.get_snapshots(agent_id="a1")[0]["workflow_name"] == "wf2"
    def test_limit(self):
        s = AgentWorkflowSnapshotter()
        for i in range(10): s.snapshot("a1", f"wf{i}")
        assert len(s.get_snapshots(limit=3)) == 3

class TestGetSnapshotCount:
    def test_total(self):
        s = AgentWorkflowSnapshotter()
        s.snapshot("a1", "wf1"); s.snapshot("a2", "wf2")
        assert s.get_snapshot_count() == 2
    def test_filtered(self):
        s = AgentWorkflowSnapshotter()
        s.snapshot("a1", "wf1"); s.snapshot("a2", "wf2")
        assert s.get_snapshot_count(agent_id="a1") == 1
    def test_empty(self):
        assert AgentWorkflowSnapshotter().get_snapshot_count() == 0

class TestGetStats:
    def test_empty(self):
        assert AgentWorkflowSnapshotter().get_stats()["total_snapshots"] == 0
    def test_with_data(self):
        s = AgentWorkflowSnapshotter()
        s.snapshot("a1", "wf1"); s.snapshot("a2", "wf2")
        st = s.get_stats()
        assert st["total_snapshots"] == 2
        assert st["unique_agents"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = AgentWorkflowSnapshotter()
        evts = []
        s.on_change = lambda a, d: evts.append(a)
        s.snapshot("a1", "wf1")
        assert len(evts) >= 1
    def test_remove_callback_true(self):
        s = AgentWorkflowSnapshotter()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_callback_false(self):
        assert AgentWorkflowSnapshotter().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = AgentWorkflowSnapshotter()
        s.MAX_ENTRIES = 5
        for i in range(8): s.snapshot("a1", f"wf{i}")
        assert s.get_snapshot_count() < 8

class TestReset:
    def test_clears(self):
        s = AgentWorkflowSnapshotter()
        s.snapshot("a1", "wf1"); s.reset()
        assert s.get_snapshot_count() == 0
    def test_clears_callbacks(self):
        s = AgentWorkflowSnapshotter()
        s.on_change = lambda a, d: None
        s.reset()
        assert s.on_change is None
    def test_resets_seq(self):
        s = AgentWorkflowSnapshotter()
        s.snapshot("a1", "wf1"); s.reset()
        assert s._state._seq == 0
