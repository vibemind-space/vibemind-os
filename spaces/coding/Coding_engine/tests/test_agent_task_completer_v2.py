"""Tests for AgentTaskCompleterV2 service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_completer_v2 import AgentTaskCompleterV2

class TestId:
    def test_prefix(self):
        assert AgentTaskCompleterV2().complete_v2("t1", "a1").startswith("atcv-")
    def test_unique(self):
        s = AgentTaskCompleterV2()
        assert len({s.complete_v2(f"t{i}", "a1") for i in range(20)}) == 20

class TestBasic:
    def test_returns_id(self):
        assert len(AgentTaskCompleterV2().complete_v2("t1", "a1")) > 0
    def test_fields(self):
        s = AgentTaskCompleterV2()
        e = s.get_completion(s.complete_v2("t1", "a1", status="ok"))
        assert e["task_id"] == "t1" and e["agent_id"] == "a1" and e["status"] == "ok"
    def test_default_status(self):
        s = AgentTaskCompleterV2()
        e = s.get_completion(s.complete_v2("t1", "a1"))
        assert e["status"] == "done"
    def test_deepcopy(self):
        s = AgentTaskCompleterV2(); m = {"a": [1]}
        rid = s.complete_v2("t1", "a1", metadata=m); m["a"].append(2)
        assert s.get_completion(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = AgentTaskCompleterV2(); b = time.time()
        assert s.get_completion(s.complete_v2("t1", "a1"))["created_at"] >= b
    def test_empty_task(self):
        assert AgentTaskCompleterV2().complete_v2("", "a1") == ""
    def test_empty_agent(self):
        assert AgentTaskCompleterV2().complete_v2("t1", "") == ""

class TestGet:
    def test_found(self):
        s = AgentTaskCompleterV2(); assert s.get_completion(s.complete_v2("t1", "a1")) is not None
    def test_not_found(self):
        assert AgentTaskCompleterV2().get_completion("xxx") is None
    def test_copy(self):
        s = AgentTaskCompleterV2(); rid = s.complete_v2("t1", "a1")
        assert s.get_completion(rid) is not s.get_completion(rid)

class TestList:
    def test_all(self):
        s = AgentTaskCompleterV2(); s.complete_v2("t1", "a1"); s.complete_v2("t2", "a2")
        assert len(s.get_completions()) == 2
    def test_filter(self):
        s = AgentTaskCompleterV2(); s.complete_v2("t1", "a1"); s.complete_v2("t2", "a2")
        assert len(s.get_completions(agent_id="a1")) == 1
    def test_newest(self):
        s = AgentTaskCompleterV2(); s.complete_v2("t1", "a1"); s.complete_v2("t2", "a1")
        assert s.get_completions(agent_id="a1")[0]["task_id"] == "t2"
    def test_limit(self):
        s = AgentTaskCompleterV2()
        for i in range(10): s.complete_v2(f"t{i}", "a1")
        assert len(s.get_completions(limit=3)) == 3

class TestCount:
    def test_total(self):
        s = AgentTaskCompleterV2(); s.complete_v2("t1", "a1"); s.complete_v2("t2", "a2")
        assert s.get_completion_count() == 2
    def test_filtered(self):
        s = AgentTaskCompleterV2(); s.complete_v2("t1", "a1"); s.complete_v2("t2", "a2")
        assert s.get_completion_count(agent_id="a1") == 1
    def test_empty(self):
        assert AgentTaskCompleterV2().get_completion_count() == 0

class TestStats:
    def test_empty(self):
        assert AgentTaskCompleterV2().get_stats()["total_completions"] == 0
    def test_data(self):
        s = AgentTaskCompleterV2(); s.complete_v2("t1", "a1"); s.complete_v2("t2", "a2")
        assert s.get_stats()["total_completions"] == 2
    def test_unique_agents(self):
        s = AgentTaskCompleterV2(); s.complete_v2("t1", "a1"); s.complete_v2("t2", "a2")
        assert s.get_stats()["unique_agents"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = AgentTaskCompleterV2(); evts = []
        s.on_change = lambda a, d: evts.append(a); s.complete_v2("t1", "a1")
        assert len(evts) >= 1
    def test_remove_true(self):
        s = AgentTaskCompleterV2(); s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        assert AgentTaskCompleterV2().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = AgentTaskCompleterV2(); s.MAX_ENTRIES = 5
        for i in range(8): s.complete_v2(f"t{i}", "a1")
        assert s.get_completion_count() < 8

class TestReset:
    def test_clears(self):
        s = AgentTaskCompleterV2(); s.complete_v2("t1", "a1"); s.reset()
        assert s.get_completion_count() == 0
    def test_callbacks(self):
        s = AgentTaskCompleterV2(); s.on_change = lambda a, d: None; s.reset()
        assert s.on_change is None
    def test_seq(self):
        s = AgentTaskCompleterV2(); s.complete_v2("t1", "a1"); s.reset()
        assert s._state._seq == 0
