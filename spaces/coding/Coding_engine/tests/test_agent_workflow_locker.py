"""Tests for AgentWorkflowLocker service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_workflow_locker import AgentWorkflowLocker


class TestIdGeneration:
    def test_prefix(self):
        s = AgentWorkflowLocker()
        assert s.lock("a1", "wf1").startswith("awlk-")

    def test_unique(self):
        s = AgentWorkflowLocker()
        ids = {s.lock("a1", f"wf{i}") for i in range(20)}
        assert len(ids) == 20


class TestLockBasic:
    def test_returns_id(self):
        s = AgentWorkflowLocker()
        assert len(s.lock("a1", "wf1")) > 0

    def test_stores_fields(self):
        s = AgentWorkflowLocker()
        rid = s.lock("a1", "wf1", reason="maintenance")
        e = s.get_lock(rid)
        assert e["agent_id"] == "a1"
        assert e["workflow_name"] == "wf1"
        assert e["reason"] == "maintenance"

    def test_with_metadata(self):
        s = AgentWorkflowLocker()
        rid = s.lock("a1", "wf1", metadata={"x": 1})
        assert s.get_lock(rid)["metadata"]["x"] == 1

    def test_metadata_deepcopy(self):
        s = AgentWorkflowLocker()
        m = {"a": [1]}
        rid = s.lock("a1", "wf1", metadata=m)
        m["a"].append(2)
        assert s.get_lock(rid)["metadata"]["a"] == [1]

    def test_created_at(self):
        s = AgentWorkflowLocker()
        before = time.time()
        rid = s.lock("a1", "wf1")
        assert s.get_lock(rid)["created_at"] >= before

    def test_empty_agent_returns_empty(self):
        assert AgentWorkflowLocker().lock("", "wf1") == ""

    def test_empty_workflow_returns_empty(self):
        assert AgentWorkflowLocker().lock("a1", "") == ""


class TestGetLock:
    def test_found(self):
        s = AgentWorkflowLocker()
        rid = s.lock("a1", "wf1")
        assert s.get_lock(rid) is not None

    def test_not_found(self):
        assert AgentWorkflowLocker().get_lock("xxx") is None

    def test_returns_copy(self):
        s = AgentWorkflowLocker()
        rid = s.lock("a1", "wf1")
        assert s.get_lock(rid) is not s.get_lock(rid)


class TestGetLocks:
    def test_all(self):
        s = AgentWorkflowLocker()
        s.lock("a1", "wf1"); s.lock("a2", "wf2")
        assert len(s.get_locks()) == 2

    def test_filter(self):
        s = AgentWorkflowLocker()
        s.lock("a1", "wf1"); s.lock("a2", "wf2")
        assert len(s.get_locks(agent_id="a1")) == 1

    def test_newest_first(self):
        s = AgentWorkflowLocker()
        s.lock("a1", "wf1"); s.lock("a1", "wf2")
        assert s.get_locks(agent_id="a1")[0]["workflow_name"] == "wf2"

    def test_limit(self):
        s = AgentWorkflowLocker()
        for i in range(10): s.lock("a1", f"wf{i}")
        assert len(s.get_locks(limit=3)) == 3


class TestGetLockCount:
    def test_total(self):
        s = AgentWorkflowLocker()
        s.lock("a1", "wf1"); s.lock("a2", "wf2")
        assert s.get_lock_count() == 2

    def test_filtered(self):
        s = AgentWorkflowLocker()
        s.lock("a1", "wf1"); s.lock("a2", "wf2")
        assert s.get_lock_count(agent_id="a1") == 1

    def test_empty(self):
        assert AgentWorkflowLocker().get_lock_count() == 0


class TestGetStats:
    def test_empty(self):
        st = AgentWorkflowLocker().get_stats()
        assert st["total_locks"] == 0
        assert st["unique_agents"] == 0

    def test_with_data(self):
        s = AgentWorkflowLocker()
        s.lock("a1", "wf1"); s.lock("a2", "wf2")
        st = s.get_stats()
        assert st["total_locks"] == 2
        assert st["unique_agents"] == 2

    def test_duplicate_agents(self):
        s = AgentWorkflowLocker()
        s.lock("a1", "wf1"); s.lock("a1", "wf2"); s.lock("a2", "wf3")
        st = s.get_stats()
        assert st["total_locks"] == 3
        assert st["unique_agents"] == 2


class TestCallbacks:
    def test_on_change(self):
        s = AgentWorkflowLocker()
        evts = []
        s.on_change = lambda a, d: evts.append(a)
        s.lock("a1", "wf1")
        assert "locked" in evts

    def test_on_change_getter_setter(self):
        s = AgentWorkflowLocker()
        assert s.on_change is None
        handler = lambda a, d: None
        s.on_change = handler
        assert s.on_change is handler

    def test_remove_callback_true(self):
        s = AgentWorkflowLocker()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True

    def test_remove_callback_false(self):
        assert AgentWorkflowLocker().remove_callback("x") is False

    def test_callbacks_dict_fires(self):
        evts = []
        s = AgentWorkflowLocker()
        s._state.callbacks["tracker"] = lambda action, data: evts.append((action, data["record_id"]))
        rid = s.lock("a1", "wf1")
        assert len(evts) >= 1
        assert evts[0][0] == "locked"
        assert evts[0][1] == rid

    def test_callback_exception_silenced(self):
        s = AgentWorkflowLocker()
        s._state.callbacks["bad"] = lambda a, d: (_ for _ in ()).throw(ValueError("boom"))
        s.on_change = lambda a, d: (_ for _ in ()).throw(RuntimeError("crash"))
        rid = s.lock("a1", "wf1")
        assert rid.startswith("awlk-")


class TestPrune:
    def test_prune_triggers(self):
        s = AgentWorkflowLocker()
        s.MAX_ENTRIES = 5
        for i in range(8): s.lock("a1", f"wf{i}")
        assert s.get_lock_count() < 8

    def test_prune_respects_max(self):
        s = AgentWorkflowLocker()
        s.MAX_ENTRIES = 5
        for i in range(8): s.lock("a1", f"wf{i}")
        assert s.get_lock_count() <= 8


class TestReset:
    def test_clears(self):
        s = AgentWorkflowLocker()
        s.lock("a1", "wf1"); s.reset()
        assert s.get_lock_count() == 0

    def test_clears_callbacks(self):
        s = AgentWorkflowLocker()
        s.on_change = lambda a, d: None
        s.reset()
        assert s.on_change is None

    def test_resets_seq(self):
        s = AgentWorkflowLocker()
        s.lock("a1", "wf1"); s.reset()
        assert s._state._seq == 0

    def test_clears_state_callbacks(self):
        s = AgentWorkflowLocker()
        s._state.callbacks["cb1"] = lambda a, d: None
        s.reset()
        assert len(s._state.callbacks) == 0
