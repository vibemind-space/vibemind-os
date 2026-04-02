"""Tests for AgentWorkflowTester service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_workflow_tester import AgentWorkflowTester

class TestIdGeneration:
    def test_prefix(self):
        assert AgentWorkflowTester().test_workflow("a1","wf1").startswith("awts-")
    def test_unique(self):
        s = AgentWorkflowTester()
        assert len({s.test_workflow("a1", f"wf{i}") for i in range(20)}) == 20

class TestBasic:
    def test_returns_id(self):
        assert len(AgentWorkflowTester().test_workflow("a1","wf1")) > 0
    def test_stores_fields(self):
        s = AgentWorkflowTester(); rid=s.test_workflow("a1","wf1",test_suite="smoke")
        e = s.get_test(rid)
        assert e["agent_id"]=="a1" and e["workflow_name"]=="wf1" and e["test_suite"]=="smoke"
    def test_default_suite(self):
        s = AgentWorkflowTester(); rid=s.test_workflow("a1","wf1")
        assert s.get_test(rid)["test_suite"] == "default"
    def test_metadata(self):
        s = AgentWorkflowTester(); rid=s.test_workflow("a1","wf1",metadata={"x":1})
        assert s.get_test(rid)["metadata"]["x"] == 1
    def test_metadata_deepcopy(self):
        s = AgentWorkflowTester(); m={"a":[1]}; rid=s.test_workflow("a1","wf1",metadata=m); m["a"].append(2)
        assert s.get_test(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = AgentWorkflowTester(); b=time.time(); rid=s.test_workflow("a1","wf1")
        assert s.get_test(rid)["created_at"] >= b
    def test_empty_agent(self):
        assert AgentWorkflowTester().test_workflow("","wf1") == ""
    def test_empty_workflow(self):
        assert AgentWorkflowTester().test_workflow("a1","") == ""

class TestGet:
    def test_found(self):
        s = AgentWorkflowTester(); rid=s.test_workflow("a1","wf1"); assert s.get_test(rid) is not None
    def test_not_found(self):
        assert AgentWorkflowTester().get_test("xxx") is None
    def test_copy(self):
        s = AgentWorkflowTester(); rid=s.test_workflow("a1","wf1")
        assert s.get_test(rid) is not s.get_test(rid)

class TestList:
    def test_all(self):
        s = AgentWorkflowTester(); s.test_workflow("a1","wf1"); s.test_workflow("a2","wf2")
        assert len(s.get_tests()) == 2
    def test_filter(self):
        s = AgentWorkflowTester(); s.test_workflow("a1","wf1"); s.test_workflow("a2","wf2")
        assert len(s.get_tests(agent_id="a1")) == 1
    def test_newest_first(self):
        s = AgentWorkflowTester(); s.test_workflow("a1","wf1"); s.test_workflow("a1","wf2")
        assert s.get_tests(agent_id="a1")[0]["workflow_name"] == "wf2"
    def test_limit(self):
        s = AgentWorkflowTester()
        for i in range(10): s.test_workflow("a1", f"wf{i}")
        assert len(s.get_tests(limit=3)) == 3

class TestCount:
    def test_total(self):
        s = AgentWorkflowTester(); s.test_workflow("a1","wf1"); s.test_workflow("a2","wf2")
        assert s.get_test_count() == 2
    def test_filtered(self):
        s = AgentWorkflowTester(); s.test_workflow("a1","wf1"); s.test_workflow("a2","wf2")
        assert s.get_test_count(agent_id="a1") == 1
    def test_empty(self):
        assert AgentWorkflowTester().get_test_count() == 0

class TestStats:
    def test_empty(self):
        assert AgentWorkflowTester().get_stats()["total_tests"] == 0
    def test_data(self):
        s = AgentWorkflowTester(); s.test_workflow("a1","wf1"); s.test_workflow("a2","wf2")
        assert s.get_stats()["total_tests"] == 2 and s.get_stats()["unique_agents"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = AgentWorkflowTester(); e=[]; s.on_change=lambda a,d: e.append(a); s.test_workflow("a1","wf1")
        assert len(e) >= 1
    def test_remove_true(self):
        s = AgentWorkflowTester(); s._state.callbacks["cb1"]=lambda a,d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        assert AgentWorkflowTester().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = AgentWorkflowTester(); s.MAX_ENTRIES=5
        for i in range(8): s.test_workflow("a1", f"wf{i}")
        assert s.get_test_count() < 8

class TestReset:
    def test_clears(self):
        s = AgentWorkflowTester(); s.test_workflow("a1","wf1"); s.reset(); assert s.get_test_count() == 0
    def test_callbacks(self):
        s = AgentWorkflowTester(); s.on_change=lambda a,d: None; s.reset(); assert s.on_change is None
    def test_seq(self):
        s = AgentWorkflowTester(); s.test_workflow("a1","wf1"); s.reset(); assert s._state._seq == 0
