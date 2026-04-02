"""Tests for AgentTaskInspector service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_inspector import AgentTaskInspector

class TestIdGeneration:
    def test_prefix(self):
        assert AgentTaskInspector().inspect("t1","a1").startswith("atin-")
    def test_unique(self):
        s = AgentTaskInspector()
        assert len({s.inspect(f"t{i}","a1") for i in range(20)}) == 20

class TestBasic:
    def test_returns_id(self):
        assert len(AgentTaskInspector().inspect("t1","a1")) > 0
    def test_stores_fields(self):
        s = AgentTaskInspector(); rid=s.inspect("t1","a1",findings="ok")
        e = s.get_inspection(rid)
        assert e["task_id"]=="t1" and e["agent_id"]=="a1" and e["findings"]=="ok"
    def test_default_findings(self):
        s = AgentTaskInspector(); rid=s.inspect("t1","a1")
        assert s.get_inspection(rid)["findings"] == ""
    def test_metadata(self):
        s = AgentTaskInspector(); rid=s.inspect("t1","a1",metadata={"x":1})
        assert s.get_inspection(rid)["metadata"]["x"] == 1
    def test_metadata_deepcopy(self):
        s = AgentTaskInspector(); m={"a":[1]}; rid=s.inspect("t1","a1",metadata=m); m["a"].append(2)
        assert s.get_inspection(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = AgentTaskInspector(); b=time.time(); rid=s.inspect("t1","a1")
        assert s.get_inspection(rid)["created_at"] >= b
    def test_empty_task(self):
        assert AgentTaskInspector().inspect("","a1") == ""
    def test_empty_agent(self):
        assert AgentTaskInspector().inspect("t1","") == ""

class TestGet:
    def test_found(self):
        s = AgentTaskInspector(); rid=s.inspect("t1","a1"); assert s.get_inspection(rid) is not None
    def test_not_found(self):
        assert AgentTaskInspector().get_inspection("xxx") is None
    def test_copy(self):
        s = AgentTaskInspector(); rid=s.inspect("t1","a1")
        assert s.get_inspection(rid) is not s.get_inspection(rid)

class TestList:
    def test_all(self):
        s = AgentTaskInspector(); s.inspect("t1","a1"); s.inspect("t2","a2")
        assert len(s.get_inspections()) == 2
    def test_filter(self):
        s = AgentTaskInspector(); s.inspect("t1","a1"); s.inspect("t2","a2")
        assert len(s.get_inspections(agent_id="a1")) == 1
    def test_newest_first(self):
        s = AgentTaskInspector(); s.inspect("t1","a1"); s.inspect("t2","a1")
        assert s.get_inspections(agent_id="a1")[0]["task_id"] == "t2"
    def test_limit(self):
        s = AgentTaskInspector()
        for i in range(10): s.inspect(f"t{i}","a1")
        assert len(s.get_inspections(limit=3)) == 3

class TestCount:
    def test_total(self):
        s = AgentTaskInspector(); s.inspect("t1","a1"); s.inspect("t2","a2")
        assert s.get_inspection_count() == 2
    def test_filtered(self):
        s = AgentTaskInspector(); s.inspect("t1","a1"); s.inspect("t2","a2")
        assert s.get_inspection_count(agent_id="a1") == 1
    def test_empty(self):
        assert AgentTaskInspector().get_inspection_count() == 0

class TestStats:
    def test_empty(self):
        assert AgentTaskInspector().get_stats()["total_inspections"] == 0
    def test_data(self):
        s = AgentTaskInspector(); s.inspect("t1","a1"); s.inspect("t2","a2")
        assert s.get_stats()["total_inspections"] == 2 and s.get_stats()["unique_agents"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = AgentTaskInspector(); e=[]; s.on_change=lambda a,d: e.append(a); s.inspect("t1","a1")
        assert len(e) >= 1
    def test_remove_true(self):
        s = AgentTaskInspector(); s._state.callbacks["cb1"]=lambda a,d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        assert AgentTaskInspector().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = AgentTaskInspector(); s.MAX_ENTRIES=5
        for i in range(8): s.inspect(f"t{i}","a1")
        assert s.get_inspection_count() < 8

class TestReset:
    def test_clears(self):
        s = AgentTaskInspector(); s.inspect("t1","a1"); s.reset(); assert s.get_inspection_count() == 0
    def test_callbacks(self):
        s = AgentTaskInspector(); s.on_change=lambda a,d: None; s.reset(); assert s.on_change is None
    def test_seq(self):
        s = AgentTaskInspector(); s.inspect("t1","a1"); s.reset(); assert s._state._seq == 0
