"""Tests for AgentTaskRecorder service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_recorder import AgentTaskRecorder

class TestIdGeneration:
    def test_prefix(self):
        assert AgentTaskRecorder().record("t1", "a1").startswith("atrc-")
    def test_unique(self):
        s = AgentTaskRecorder()
        ids = {s.record(f"t{i}", "a1") for i in range(20)}
        assert len(ids) == 20

class TestRecordBasic:
    def test_returns_id(self):
        assert len(AgentTaskRecorder().record("t1", "a1")) > 0
    def test_stores_fields(self):
        s = AgentTaskRecorder()
        rid = s.record("t1", "a1", action="completed")
        e = s.get_record(rid)
        assert e["task_id"] == "t1"
        assert e["agent_id"] == "a1"
        assert e["action"] == "completed"
    def test_default_action(self):
        s = AgentTaskRecorder(); rid = s.record("t1", "a1")
        assert s.get_record(rid)["action"] == "started"
    def test_with_metadata(self):
        s = AgentTaskRecorder()
        rid = s.record("t1", "a1", metadata={"x": 1})
        assert s.get_record(rid)["metadata"]["x"] == 1
    def test_metadata_deepcopy(self):
        s = AgentTaskRecorder(); m = {"a": [1]}
        rid = s.record("t1", "a1", metadata=m); m["a"].append(2)
        assert s.get_record(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = AgentTaskRecorder(); before = time.time()
        rid = s.record("t1", "a1")
        assert s.get_record(rid)["created_at"] >= before
    def test_empty_task(self):
        assert AgentTaskRecorder().record("", "a1") == ""
    def test_empty_agent(self):
        assert AgentTaskRecorder().record("t1", "") == ""

class TestGetRecord:
    def test_found(self):
        s = AgentTaskRecorder(); rid = s.record("t1", "a1")
        assert s.get_record(rid) is not None
    def test_not_found(self):
        assert AgentTaskRecorder().get_record("xxx") is None
    def test_returns_copy(self):
        s = AgentTaskRecorder(); rid = s.record("t1", "a1")
        assert s.get_record(rid) is not s.get_record(rid)

class TestGetRecords:
    def test_all(self):
        s = AgentTaskRecorder(); s.record("t1","a1"); s.record("t2","a2")
        assert len(s.get_records()) == 2
    def test_filter(self):
        s = AgentTaskRecorder(); s.record("t1","a1"); s.record("t2","a2")
        assert len(s.get_records(agent_id="a1")) == 1
    def test_newest_first(self):
        s = AgentTaskRecorder(); s.record("t1","a1"); s.record("t2","a1")
        assert s.get_records(agent_id="a1")[0]["task_id"] == "t2"
    def test_limit(self):
        s = AgentTaskRecorder()
        for i in range(10): s.record(f"t{i}", "a1")
        assert len(s.get_records(limit=3)) == 3

class TestGetRecordCount:
    def test_total(self):
        s = AgentTaskRecorder(); s.record("t1","a1"); s.record("t2","a2")
        assert s.get_record_count() == 2
    def test_filtered(self):
        s = AgentTaskRecorder(); s.record("t1","a1"); s.record("t2","a2")
        assert s.get_record_count(agent_id="a1") == 1
    def test_empty(self):
        assert AgentTaskRecorder().get_record_count() == 0

class TestGetStats:
    def test_empty(self):
        assert AgentTaskRecorder().get_stats()["total_records"] == 0
    def test_with_data(self):
        s = AgentTaskRecorder(); s.record("t1","a1"); s.record("t2","a2")
        st = s.get_stats()
        assert st["total_records"] == 2
        assert st["unique_agents"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = AgentTaskRecorder(); evts = []
        s.on_change = lambda a, d: evts.append(a)
        s.record("t1", "a1"); assert len(evts) >= 1
    def test_remove_callback_true(self):
        s = AgentTaskRecorder(); s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_callback_false(self):
        assert AgentTaskRecorder().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = AgentTaskRecorder(); s.MAX_ENTRIES = 5
        for i in range(8): s.record(f"t{i}", "a1")
        assert s.get_record_count() < 8

class TestReset:
    def test_clears(self):
        s = AgentTaskRecorder(); s.record("t1","a1"); s.reset()
        assert s.get_record_count() == 0
    def test_clears_callbacks(self):
        s = AgentTaskRecorder(); s.on_change = lambda a,d: None; s.reset()
        assert s.on_change is None
    def test_resets_seq(self):
        s = AgentTaskRecorder(); s.record("t1","a1"); s.reset()
        assert s._state._seq == 0
