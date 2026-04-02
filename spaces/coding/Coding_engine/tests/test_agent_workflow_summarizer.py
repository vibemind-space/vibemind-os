"""Tests for AgentWorkflowSummarizer service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_workflow_summarizer import AgentWorkflowSummarizer

class TestIdGeneration:
    def test_prefix(self):
        s = AgentWorkflowSummarizer()
        assert s.summarize("a1", "wf1", "done").startswith("awsm-")
    def test_unique(self):
        s = AgentWorkflowSummarizer()
        ids = {s.summarize("a1", f"wf{i}", "text") for i in range(20)}
        assert len(ids) == 20

class TestSummarizeBasic:
    def test_returns_id(self):
        s = AgentWorkflowSummarizer()
        assert len(s.summarize("a1", "wf1", "all good")) > 0
    def test_stores_fields(self):
        s = AgentWorkflowSummarizer()
        rid = s.summarize("a1", "wf1", "completed ok")
        e = s.get_summary(rid)
        assert e["agent_id"] == "a1"
        assert e["workflow_name"] == "wf1"
        assert e["summary_text"] == "completed ok"
    def test_with_metadata(self):
        s = AgentWorkflowSummarizer()
        rid = s.summarize("a1", "wf1", "ok", metadata={"x": 1})
        assert s.get_summary(rid)["metadata"]["x"] == 1
    def test_created_at(self):
        s = AgentWorkflowSummarizer()
        before = time.time()
        rid = s.summarize("a1", "wf1", "ok")
        assert s.get_summary(rid)["created_at"] >= before

class TestGetSummary:
    def test_found(self):
        s = AgentWorkflowSummarizer()
        rid = s.summarize("a1", "wf1", "ok")
        assert s.get_summary(rid) is not None
    def test_not_found(self):
        assert AgentWorkflowSummarizer().get_summary("xxx") is None
    def test_returns_copy(self):
        s = AgentWorkflowSummarizer()
        rid = s.summarize("a1", "wf1", "ok")
        assert s.get_summary(rid) is not s.get_summary(rid)

class TestGetSummaries:
    def test_all(self):
        s = AgentWorkflowSummarizer()
        s.summarize("a1", "wf1", "ok"); s.summarize("a2", "wf2", "ok")
        assert len(s.get_summaries()) == 2
    def test_filter(self):
        s = AgentWorkflowSummarizer()
        s.summarize("a1", "wf1", "ok"); s.summarize("a2", "wf2", "ok")
        assert len(s.get_summaries(agent_id="a1")) == 1
    def test_newest_first(self):
        s = AgentWorkflowSummarizer()
        s.summarize("a1", "wf1", "first"); s.summarize("a1", "wf2", "second")
        assert s.get_summaries(agent_id="a1")[0]["workflow_name"] == "wf2"
    def test_limit(self):
        s = AgentWorkflowSummarizer()
        for i in range(10): s.summarize("a1", f"wf{i}", "ok")
        assert len(s.get_summaries(limit=3)) == 3

class TestGetSummaryCount:
    def test_total(self):
        s = AgentWorkflowSummarizer()
        s.summarize("a1", "wf1", "ok"); s.summarize("a2", "wf2", "ok")
        assert s.get_summary_count() == 2
    def test_filtered(self):
        s = AgentWorkflowSummarizer()
        s.summarize("a1", "wf1", "ok"); s.summarize("a2", "wf2", "ok")
        assert s.get_summary_count(agent_id="a1") == 1
    def test_empty(self):
        assert AgentWorkflowSummarizer().get_summary_count() == 0

class TestGetStats:
    def test_empty(self):
        assert AgentWorkflowSummarizer().get_stats()["total_summaries"] == 0
    def test_with_data(self):
        s = AgentWorkflowSummarizer()
        s.summarize("a1", "wf1", "ok"); s.summarize("a2", "wf2", "ok")
        st = s.get_stats()
        assert st["total_summaries"] == 2
        assert st["unique_agents"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = AgentWorkflowSummarizer()
        evts = []
        s.on_change = lambda a, d: evts.append(a)
        s.summarize("a1", "wf1", "ok")
        assert len(evts) >= 1
    def test_remove_callback_true(self):
        s = AgentWorkflowSummarizer()
        s._callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_callback_false(self):
        assert AgentWorkflowSummarizer().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = AgentWorkflowSummarizer()
        s.MAX_ENTRIES = 5
        for i in range(8): s.summarize("a1", f"wf{i}", "ok")
        assert s.get_summary_count() < 8

class TestReset:
    def test_clears(self):
        s = AgentWorkflowSummarizer()
        s.summarize("a1", "wf1", "ok"); s.reset()
        assert s.get_summary_count() == 0
    def test_clears_callbacks(self):
        s = AgentWorkflowSummarizer()
        s.on_change = lambda a, d: None
        s.reset()
        assert s.on_change is None
    def test_resets_seq(self):
        s = AgentWorkflowSummarizer()
        s.summarize("a1", "wf1", "ok"); s.reset()
        assert s._state._seq == 0
