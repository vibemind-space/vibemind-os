"""Tests for AgentTaskCompleter service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_completer import AgentTaskCompleter

class TestId:
    def test_prefix(self):
        assert AgentTaskCompleter().complete("t1", "a1").startswith("atcm-")
    def test_unique(self):
        s = AgentTaskCompleter()
        assert len({s.complete(f"t{i}", "a1") for i in range(20)}) == 20

class TestBasic:
    def test_returns_id(self):
        assert len(AgentTaskCompleter().complete("t1", "a1")) > 0
    def test_fields(self):
        s = AgentTaskCompleter()
        e = s.get_completion(s.complete("t1", "a1", result="ok"))
        assert e["task_id"] == "t1" and e["agent_id"] == "a1" and e["result"] == "ok"
    def test_deepcopy(self):
        s = AgentTaskCompleter(); m = {"a": [1]}
        rid = s.complete("t1", "a1", metadata=m); m["a"].append(2)
        assert s.get_completion(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = AgentTaskCompleter(); b = time.time()
        assert s.get_completion(s.complete("t1", "a1"))["created_at"] >= b
    def test_empty_task(self):
        assert AgentTaskCompleter().complete("", "a1") == ""
    def test_empty_agent(self):
        assert AgentTaskCompleter().complete("t1", "") == ""

class TestGet:
    def test_found(self):
        s = AgentTaskCompleter(); assert s.get_completion(s.complete("t1", "a1")) is not None
    def test_not_found(self):
        assert AgentTaskCompleter().get_completion("xxx") is None
    def test_copy(self):
        s = AgentTaskCompleter(); rid = s.complete("t1", "a1")
        assert s.get_completion(rid) is not s.get_completion(rid)

class TestList:
    def test_all(self):
        s = AgentTaskCompleter(); s.complete("t1", "a1"); s.complete("t2", "a2")
        assert len(s.get_completions()) == 2
    def test_filter(self):
        s = AgentTaskCompleter(); s.complete("t1", "a1"); s.complete("t2", "a2")
        assert len(s.get_completions(agent_id="a1")) == 1
    def test_newest(self):
        s = AgentTaskCompleter(); s.complete("t1", "a1"); s.complete("t2", "a1")
        assert s.get_completions(agent_id="a1")[0]["task_id"] == "t2"
    def test_limit(self):
        s = AgentTaskCompleter()
        for i in range(10): s.complete(f"t{i}", "a1")
        assert len(s.get_completions(limit=3)) == 3

class TestCount:
    def test_total(self):
        s = AgentTaskCompleter(); s.complete("t1", "a1"); s.complete("t2", "a2")
        assert s.get_completion_count() == 2
    def test_filtered(self):
        s = AgentTaskCompleter(); s.complete("t1", "a1"); s.complete("t2", "a2")
        assert s.get_completion_count(agent_id="a1") == 1
    def test_empty(self):
        assert AgentTaskCompleter().get_completion_count() == 0

class TestStats:
    def test_empty(self):
        assert AgentTaskCompleter().get_stats()["total_completions"] == 0
    def test_data(self):
        s = AgentTaskCompleter(); s.complete("t1", "a1"); s.complete("t2", "a2")
        assert s.get_stats()["total_completions"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = AgentTaskCompleter(); evts = []
        s.on_change = lambda a, d: evts.append(a); s.complete("t1", "a1")
        assert len(evts) >= 1
    def test_remove_true(self):
        s = AgentTaskCompleter(); s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        assert AgentTaskCompleter().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = AgentTaskCompleter(); s.MAX_ENTRIES = 5
        for i in range(8): s.complete(f"t{i}", "a1")
        assert s.get_completion_count() < 8

class TestReset:
    def test_clears(self):
        s = AgentTaskCompleter(); s.complete("t1", "a1"); s.reset()
        assert s.get_completion_count() == 0
    def test_callbacks(self):
        s = AgentTaskCompleter(); s.on_change = lambda a, d: None; s.reset()
        assert s.on_change is None
    def test_seq(self):
        s = AgentTaskCompleter(); s.complete("t1", "a1"); s.reset()
        assert s._state._seq == 0
