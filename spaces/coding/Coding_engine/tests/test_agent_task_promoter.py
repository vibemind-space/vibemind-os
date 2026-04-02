"""Tests for AgentTaskPromoter service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_promoter import AgentTaskPromoter

class TestIdGeneration:
    def test_prefix(self):
        p = AgentTaskPromoter()
        assert p.promote("t1", "a1").startswith("atpm-")
    def test_unique(self):
        p = AgentTaskPromoter()
        ids = {p.promote(f"t{i}", "a1") for i in range(20)}
        assert len(ids) == 20

class TestPromoteBasic:
    def test_returns_id(self):
        assert len(AgentTaskPromoter().promote("t1", "a1")) > 0
    def test_stores_fields(self):
        p = AgentTaskPromoter()
        rid = p.promote("t1", "a1", new_priority=5, reason="urgent")
        e = p.get_promotion(rid)
        assert e["task_id"] == "t1"
        assert e["agent_id"] == "a1"
        assert e["new_priority"] == 5
    def test_with_metadata(self):
        p = AgentTaskPromoter()
        rid = p.promote("t1", "a1", metadata={"x": 1})
        assert p.get_promotion(rid)["metadata"]["x"] == 1

class TestPromoteValidation:
    def test_empty_task_id(self):
        assert AgentTaskPromoter().promote("", "a1") == ""
    def test_empty_agent_id(self):
        assert AgentTaskPromoter().promote("t1", "") == ""

class TestGetPromotion:
    def test_found(self):
        p = AgentTaskPromoter()
        rid = p.promote("t1", "a1")
        assert p.get_promotion(rid) is not None
    def test_not_found(self):
        assert AgentTaskPromoter().get_promotion("xxx") is None
    def test_returns_copy(self):
        p = AgentTaskPromoter()
        rid = p.promote("t1", "a1")
        assert p.get_promotion(rid) is not p.get_promotion(rid)

class TestGetPromotions:
    def test_all(self):
        p = AgentTaskPromoter()
        p.promote("t1", "a1"); p.promote("t2", "a2")
        assert len(p.get_promotions()) == 2
    def test_filter(self):
        p = AgentTaskPromoter()
        p.promote("t1", "a1"); p.promote("t2", "a2")
        assert len(p.get_promotions(agent_id="a1")) == 1
    def test_newest_first(self):
        p = AgentTaskPromoter()
        p.promote("t1", "a1"); p.promote("t2", "a1")
        assert p.get_promotions(agent_id="a1")[0]["task_id"] == "t2"
    def test_limit(self):
        p = AgentTaskPromoter()
        for i in range(10): p.promote(f"t{i}", "a1")
        assert len(p.get_promotions(limit=3)) == 3

class TestGetPromotionCount:
    def test_total(self):
        p = AgentTaskPromoter()
        p.promote("t1", "a1"); p.promote("t2", "a2")
        assert p.get_promotion_count() == 2
    def test_filtered(self):
        p = AgentTaskPromoter()
        p.promote("t1", "a1"); p.promote("t2", "a2")
        assert p.get_promotion_count(agent_id="a1") == 1

class TestGetStats:
    def test_empty(self):
        assert AgentTaskPromoter().get_stats()["total_promotions"] == 0
    def test_with_data(self):
        p = AgentTaskPromoter()
        p.promote("t1", "a1"); p.promote("t2", "a2")
        st = p.get_stats()
        assert st["total_promotions"] == 2
        assert st["unique_agents"] == 2

class TestCallbacks:
    def test_on_change(self):
        p = AgentTaskPromoter()
        evts = []
        p.on_change = lambda a, d: evts.append(a)
        p.promote("t1", "a1")
        assert len(evts) >= 1
    def test_remove_callback_true(self):
        p = AgentTaskPromoter()
        p._state.callbacks["cb1"] = lambda a, d: None
        assert p.remove_callback("cb1") is True
    def test_remove_callback_false(self):
        assert AgentTaskPromoter().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        p = AgentTaskPromoter()
        p.MAX_ENTRIES = 5
        for i in range(8): p.promote(f"t{i}", "a1")
        assert p.get_promotion_count() < 8
    def test_prune_keeps_newest(self):
        p = AgentTaskPromoter()
        p.MAX_ENTRIES = 3
        for i in range(6): p.promote(f"t{i}", "a1")
        remaining = p.get_promotions()
        # newest entries should survive
        task_ids = {e["task_id"] for e in remaining}
        assert "t5" in task_ids

class TestReset:
    def test_clears(self):
        p = AgentTaskPromoter()
        p.promote("t1", "a1"); p.reset()
        assert p.get_promotion_count() == 0
    def test_resets_seq(self):
        p = AgentTaskPromoter()
        p.promote("t1", "a1"); p.reset()
        assert p._state._seq == 0
    def test_stats_after_reset(self):
        p = AgentTaskPromoter()
        p.promote("t1", "a1"); p.reset()
        assert p.get_stats() == {"total_promotions": 0, "unique_agents": 0}

class TestPromoteValidationExtra:
    def test_both_empty(self):
        assert AgentTaskPromoter().promote("", "") == ""
    def test_none_metadata_becomes_empty(self):
        p = AgentTaskPromoter()
        rid = p.promote("t1", "a1", metadata=None)
        assert p.get_promotion(rid)["metadata"] == {}
    def test_created_at_present(self):
        p = AgentTaskPromoter()
        rid = p.promote("t1", "a1")
        assert "created_at" in p.get_promotion(rid)
    def test_default_reason_empty(self):
        p = AgentTaskPromoter()
        rid = p.promote("t1", "a1")
        assert p.get_promotion(rid)["reason"] == ""
    def test_max_entries_constant(self):
        assert AgentTaskPromoter.MAX_ENTRIES == 10000
    def test_on_change_initially_none(self):
        assert AgentTaskPromoter().on_change is None
    def test_callback_error_does_not_propagate(self):
        p = AgentTaskPromoter()
        p.on_change = lambda a, d: (_ for _ in ()).throw(ValueError)
        pid = p.promote("t1", "a1")
        assert pid.startswith("atpm-")
