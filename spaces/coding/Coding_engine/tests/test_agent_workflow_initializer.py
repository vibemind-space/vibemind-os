"""Tests for AgentWorkflowInitializer service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_workflow_initializer import AgentWorkflowInitializer

class TestIdGeneration:
    def test_prefix(self):
        s = AgentWorkflowInitializer()
        assert s.initialize("a1", "wf1").startswith("awin-")
    def test_unique(self):
        s = AgentWorkflowInitializer()
        ids = {s.initialize("a1", f"wf{i}") for i in range(20)}
        assert len(ids) == 20

class TestInitializeBasic:
    def test_returns_id(self):
        s = AgentWorkflowInitializer()
        assert len(s.initialize("a1", "wf1")) > 0
    def test_stores_fields(self):
        s = AgentWorkflowInitializer()
        rid = s.initialize("a1", "wf1", config="cfg1")
        e = s.get_initialization(rid)
        assert e["agent_id"] == "a1"
        assert e["workflow_name"] == "wf1"
        assert e["config"] == "cfg1"
    def test_with_metadata(self):
        s = AgentWorkflowInitializer()
        rid = s.initialize("a1", "wf1", metadata={"x": 1})
        assert s.get_initialization(rid)["metadata"]["x"] == 1
    def test_metadata_deepcopy(self):
        s = AgentWorkflowInitializer()
        m = {"a": [1]}
        rid = s.initialize("a1", "wf1", metadata=m)
        m["a"].append(2)
        assert s.get_initialization(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = AgentWorkflowInitializer()
        before = time.time()
        rid = s.initialize("a1", "wf1")
        assert s.get_initialization(rid)["created_at"] >= before
    def test_empty_agent_returns_empty(self):
        assert AgentWorkflowInitializer().initialize("", "wf1") == ""
    def test_empty_workflow_returns_empty(self):
        assert AgentWorkflowInitializer().initialize("a1", "") == ""

class TestGetInitialization:
    def test_found(self):
        s = AgentWorkflowInitializer()
        rid = s.initialize("a1", "wf1")
        assert s.get_initialization(rid) is not None
    def test_not_found(self):
        assert AgentWorkflowInitializer().get_initialization("xxx") is None
    def test_returns_copy(self):
        s = AgentWorkflowInitializer()
        rid = s.initialize("a1", "wf1")
        assert s.get_initialization(rid) is not s.get_initialization(rid)

class TestGetInitializations:
    def test_all(self):
        s = AgentWorkflowInitializer()
        s.initialize("a1", "wf1"); s.initialize("a2", "wf2")
        assert len(s.get_initializations()) == 2
    def test_filter(self):
        s = AgentWorkflowInitializer()
        s.initialize("a1", "wf1"); s.initialize("a2", "wf2")
        assert len(s.get_initializations(agent_id="a1")) == 1
    def test_newest_first(self):
        s = AgentWorkflowInitializer()
        s.initialize("a1", "wf1"); s.initialize("a1", "wf2")
        assert s.get_initializations(agent_id="a1")[0]["workflow_name"] == "wf2"
    def test_limit(self):
        s = AgentWorkflowInitializer()
        for i in range(10): s.initialize("a1", f"wf{i}")
        assert len(s.get_initializations(limit=3)) == 3

class TestGetInitializationCount:
    def test_total(self):
        s = AgentWorkflowInitializer()
        s.initialize("a1", "wf1"); s.initialize("a2", "wf2")
        assert s.get_initialization_count() == 2
    def test_filtered(self):
        s = AgentWorkflowInitializer()
        s.initialize("a1", "wf1"); s.initialize("a2", "wf2")
        assert s.get_initialization_count(agent_id="a1") == 1
    def test_empty(self):
        assert AgentWorkflowInitializer().get_initialization_count() == 0

class TestGetStats:
    def test_empty(self):
        assert AgentWorkflowInitializer().get_stats()["total_initializations"] == 0
    def test_with_data(self):
        s = AgentWorkflowInitializer()
        s.initialize("a1", "wf1"); s.initialize("a2", "wf2")
        st = s.get_stats()
        assert st["total_initializations"] == 2
        assert st["unique_agents"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = AgentWorkflowInitializer()
        evts = []
        s.on_change = lambda a, d: evts.append(a)
        s.initialize("a1", "wf1")
        assert len(evts) >= 1
    def test_remove_callback_true(self):
        s = AgentWorkflowInitializer()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_callback_false(self):
        assert AgentWorkflowInitializer().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = AgentWorkflowInitializer()
        s.MAX_ENTRIES = 5
        for i in range(8): s.initialize("a1", f"wf{i}")
        assert s.get_initialization_count() < 8

class TestReset:
    def test_clears(self):
        s = AgentWorkflowInitializer()
        s.initialize("a1", "wf1"); s.reset()
        assert s.get_initialization_count() == 0
    def test_clears_callbacks(self):
        s = AgentWorkflowInitializer()
        s.on_change = lambda a, d: None
        s.reset()
        assert s.on_change is None
    def test_resets_seq(self):
        s = AgentWorkflowInitializer()
        s.initialize("a1", "wf1"); s.reset()
        assert s._state._seq == 0
