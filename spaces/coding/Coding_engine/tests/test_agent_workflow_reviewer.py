"""Tests for AgentWorkflowReviewer service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_workflow_reviewer import AgentWorkflowReviewer

class TestIdGeneration:
    def test_prefix(self):
        assert AgentWorkflowReviewer().review("a1", "wf1").startswith("awrv-")
    def test_unique(self):
        s = AgentWorkflowReviewer()
        ids = {s.review("a1", f"wf{i}") for i in range(20)}
        assert len(ids) == 20

class TestReviewBasic:
    def test_returns_id(self):
        assert len(AgentWorkflowReviewer().review("a1", "wf1")) > 0
    def test_stores_fields(self):
        s = AgentWorkflowReviewer()
        rid = s.review("a1", "wf1", verdict="rejected")
        e = s.get_review(rid)
        assert e["agent_id"] == "a1"
        assert e["workflow_name"] == "wf1"
        assert e["verdict"] == "rejected"
    def test_default_verdict(self):
        s = AgentWorkflowReviewer(); rid = s.review("a1", "wf1")
        assert s.get_review(rid)["verdict"] == "approved"
    def test_with_metadata(self):
        s = AgentWorkflowReviewer()
        rid = s.review("a1", "wf1", metadata={"x": 1})
        assert s.get_review(rid)["metadata"]["x"] == 1
    def test_metadata_deepcopy(self):
        s = AgentWorkflowReviewer(); m = {"a": [1]}
        rid = s.review("a1", "wf1", metadata=m); m["a"].append(2)
        assert s.get_review(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = AgentWorkflowReviewer(); before = time.time()
        rid = s.review("a1", "wf1")
        assert s.get_review(rid)["created_at"] >= before
    def test_empty_agent(self):
        assert AgentWorkflowReviewer().review("", "wf1") == ""
    def test_empty_workflow(self):
        assert AgentWorkflowReviewer().review("a1", "") == ""

class TestGetReview:
    def test_found(self):
        s = AgentWorkflowReviewer(); rid = s.review("a1", "wf1")
        assert s.get_review(rid) is not None
    def test_not_found(self):
        assert AgentWorkflowReviewer().get_review("xxx") is None
    def test_returns_copy(self):
        s = AgentWorkflowReviewer(); rid = s.review("a1", "wf1")
        assert s.get_review(rid) is not s.get_review(rid)

class TestGetReviews:
    def test_all(self):
        s = AgentWorkflowReviewer(); s.review("a1","wf1"); s.review("a2","wf2")
        assert len(s.get_reviews()) == 2
    def test_filter(self):
        s = AgentWorkflowReviewer(); s.review("a1","wf1"); s.review("a2","wf2")
        assert len(s.get_reviews(agent_id="a1")) == 1
    def test_newest_first(self):
        s = AgentWorkflowReviewer(); s.review("a1","wf1"); s.review("a1","wf2")
        assert s.get_reviews(agent_id="a1")[0]["workflow_name"] == "wf2"
    def test_limit(self):
        s = AgentWorkflowReviewer()
        for i in range(10): s.review("a1", f"wf{i}")
        assert len(s.get_reviews(limit=3)) == 3

class TestGetReviewCount:
    def test_total(self):
        s = AgentWorkflowReviewer(); s.review("a1","wf1"); s.review("a2","wf2")
        assert s.get_review_count() == 2
    def test_filtered(self):
        s = AgentWorkflowReviewer(); s.review("a1","wf1"); s.review("a2","wf2")
        assert s.get_review_count(agent_id="a1") == 1
    def test_empty(self):
        assert AgentWorkflowReviewer().get_review_count() == 0

class TestGetStats:
    def test_empty(self):
        assert AgentWorkflowReviewer().get_stats()["total_reviews"] == 0
    def test_with_data(self):
        s = AgentWorkflowReviewer(); s.review("a1","wf1"); s.review("a2","wf2")
        st = s.get_stats()
        assert st["total_reviews"] == 2
        assert st["unique_agents"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = AgentWorkflowReviewer(); evts = []
        s.on_change = lambda a, d: evts.append(a)
        s.review("a1", "wf1"); assert len(evts) >= 1
    def test_remove_callback_true(self):
        s = AgentWorkflowReviewer(); s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_callback_false(self):
        assert AgentWorkflowReviewer().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = AgentWorkflowReviewer(); s.MAX_ENTRIES = 5
        for i in range(8): s.review("a1", f"wf{i}")
        assert s.get_review_count() < 8

class TestReset:
    def test_clears(self):
        s = AgentWorkflowReviewer(); s.review("a1","wf1"); s.reset()
        assert s.get_review_count() == 0
    def test_clears_callbacks(self):
        s = AgentWorkflowReviewer(); s.on_change = lambda a,d: None; s.reset()
        assert s.on_change is None
    def test_resets_seq(self):
        s = AgentWorkflowReviewer(); s.review("a1","wf1"); s.reset()
        assert s._state._seq == 0
