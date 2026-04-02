"""Tests for AgentWorkflowGraph service."""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_workflow_graph import AgentWorkflowGraph


class TestCreateGraph:
    """Graph creation tests."""

    def test_create_graph_returns_id(self):
        svc = AgentWorkflowGraph()
        gid = svc.create_graph("wf1")
        assert gid.startswith("awgr-")
        assert len(gid) > 5

    def test_create_graph_with_label(self):
        svc = AgentWorkflowGraph()
        gid = svc.create_graph("wf1", label="main flow")
        graph = svc.get_graph(gid)
        assert graph["label"] == "main flow"

    def test_create_graph_empty_workflow_id_returns_empty(self):
        svc = AgentWorkflowGraph()
        assert svc.create_graph("") == ""

    def test_create_graph_stores_workflow_id(self):
        svc = AgentWorkflowGraph()
        gid = svc.create_graph("wf1")
        graph = svc.get_graph(gid)
        assert graph["workflow_id"] == "wf1"


class TestAddNode:
    """Node addition tests."""

    def test_add_node_success(self):
        svc = AgentWorkflowGraph()
        gid = svc.create_graph("wf1")
        assert svc.add_node(gid, "start") is True

    def test_add_node_invalid_graph(self):
        svc = AgentWorkflowGraph()
        assert svc.add_node("awgr-nonexistent", "start") is False

    def test_add_node_empty_name(self):
        svc = AgentWorkflowGraph()
        gid = svc.create_graph("wf1")
        assert svc.add_node(gid, "") is False

    def test_add_node_duplicate_rejected(self):
        svc = AgentWorkflowGraph()
        gid = svc.create_graph("wf1")
        svc.add_node(gid, "start")
        assert svc.add_node(gid, "start") is False

    def test_add_node_with_metadata(self):
        svc = AgentWorkflowGraph()
        gid = svc.create_graph("wf1")
        svc.add_node(gid, "step1", metadata={"type": "transform"})
        graph = svc.get_graph(gid)
        assert graph["nodes"]["step1"]["metadata"] == {"type": "transform"}

    def test_add_node_metadata_deep_copied(self):
        svc = AgentWorkflowGraph()
        gid = svc.create_graph("wf1")
        meta = {"nested": {"x": 1}}
        svc.add_node(gid, "step1", metadata=meta)
        meta["nested"]["x"] = 999
        graph = svc.get_graph(gid)
        assert graph["nodes"]["step1"]["metadata"]["nested"]["x"] == 1


class TestAddEdge:
    """Edge addition tests."""

    def test_add_edge_success(self):
        svc = AgentWorkflowGraph()
        gid = svc.create_graph("wf1")
        svc.add_node(gid, "a")
        svc.add_node(gid, "b")
        assert svc.add_edge(gid, "a", "b") is True

    def test_add_edge_invalid_graph(self):
        svc = AgentWorkflowGraph()
        assert svc.add_edge("awgr-nonexistent", "a", "b") is False

    def test_add_edge_missing_from_node(self):
        svc = AgentWorkflowGraph()
        gid = svc.create_graph("wf1")
        svc.add_node(gid, "b")
        assert svc.add_edge(gid, "a", "b") is False

    def test_add_edge_missing_to_node(self):
        svc = AgentWorkflowGraph()
        gid = svc.create_graph("wf1")
        svc.add_node(gid, "a")
        assert svc.add_edge(gid, "a", "b") is False

    def test_add_edge_duplicate_rejected(self):
        svc = AgentWorkflowGraph()
        gid = svc.create_graph("wf1")
        svc.add_node(gid, "a")
        svc.add_node(gid, "b")
        svc.add_edge(gid, "a", "b")
        assert svc.add_edge(gid, "a", "b") is False


class TestGetGraph:
    """Graph retrieval tests."""

    def test_get_graph_existing(self):
        svc = AgentWorkflowGraph()
        gid = svc.create_graph("wf1", label="test")
        graph = svc.get_graph(gid)
        assert graph is not None
        assert graph["graph_id"] == gid
        assert graph["workflow_id"] == "wf1"
        assert graph["label"] == "test"
        assert isinstance(graph["nodes"], dict)
        assert isinstance(graph["edges"], list)

    def test_get_graph_nonexistent(self):
        svc = AgentWorkflowGraph()
        assert svc.get_graph("awgr-nonexistent") is None

    def test_get_graph_returns_dict(self):
        svc = AgentWorkflowGraph()
        gid = svc.create_graph("wf1")
        assert isinstance(svc.get_graph(gid), dict)


class TestGetGraphs:
    """Graph listing and filtering tests."""

    def test_get_graphs_all(self):
        svc = AgentWorkflowGraph()
        svc.create_graph("wf1")
        svc.create_graph("wf2")
        assert len(svc.get_graphs()) == 2

    def test_get_graphs_filter_workflow(self):
        svc = AgentWorkflowGraph()
        svc.create_graph("wf1")
        svc.create_graph("wf2")
        svc.create_graph("wf1")
        results = svc.get_graphs(workflow_id="wf1")
        assert len(results) == 2
        assert all(r["workflow_id"] == "wf1" for r in results)

    def test_get_graphs_newest_first(self):
        svc = AgentWorkflowGraph()
        svc.create_graph("wf1", label="first")
        svc.create_graph("wf1", label="second")
        results = svc.get_graphs()
        assert results[0]["label"] == "second"
        assert results[1]["label"] == "first"

    def test_get_graphs_limit(self):
        svc = AgentWorkflowGraph()
        for i in range(10):
            svc.create_graph("wf1", label=str(i))
        results = svc.get_graphs(limit=3)
        assert len(results) == 3

    def test_get_graphs_returns_list_of_dicts(self):
        svc = AgentWorkflowGraph()
        svc.create_graph("wf1")
        results = svc.get_graphs()
        assert isinstance(results, list)
        assert isinstance(results[0], dict)


class TestGetGraphCount:
    """Graph counting tests."""

    def test_count_all(self):
        svc = AgentWorkflowGraph()
        svc.create_graph("wf1")
        svc.create_graph("wf2")
        assert svc.get_graph_count() == 2

    def test_count_by_workflow(self):
        svc = AgentWorkflowGraph()
        svc.create_graph("wf1")
        svc.create_graph("wf1")
        svc.create_graph("wf2")
        assert svc.get_graph_count(workflow_id="wf1") == 2


class TestGetStats:
    """Aggregate statistics tests."""

    def test_stats_empty(self):
        svc = AgentWorkflowGraph()
        stats = svc.get_stats()
        assert stats["total_graphs"] == 0
        assert stats["total_nodes"] == 0
        assert stats["total_edges"] == 0

    def test_stats_populated(self):
        svc = AgentWorkflowGraph()
        gid = svc.create_graph("wf1")
        svc.add_node(gid, "a")
        svc.add_node(gid, "b")
        svc.add_edge(gid, "a", "b")
        stats = svc.get_stats()
        assert stats["total_graphs"] == 1
        assert stats["total_nodes"] == 2
        assert stats["total_edges"] == 1

    def test_stats_returns_dict(self):
        svc = AgentWorkflowGraph()
        assert isinstance(svc.get_stats(), dict)


class TestReset:
    """Reset clears all state."""

    def test_reset_clears_entries(self):
        svc = AgentWorkflowGraph()
        svc.create_graph("wf1")
        svc.reset()
        assert svc.get_graph_count() == 0

    def test_reset_clears_callbacks(self):
        svc = AgentWorkflowGraph()
        svc.on_change["cb1"] = lambda e, d: None
        svc.reset()
        assert len(svc.on_change) == 0


class TestCallbacks:
    """Event firing and callback management."""

    def test_fire_on_graph_created(self):
        svc = AgentWorkflowGraph()
        events = []
        svc.on_change["cb1"] = lambda e, d: events.append((e, d))
        svc.create_graph("wf1")
        assert len(events) == 1
        assert events[0][0] == "graph_created"

    def test_fire_on_node_added(self):
        svc = AgentWorkflowGraph()
        events = []
        svc.on_change["cb1"] = lambda e, d: events.append((e, d))
        gid = svc.create_graph("wf1")
        svc.add_node(gid, "start")
        assert any(e[0] == "node_added" for e in events)

    def test_fire_on_edge_added(self):
        svc = AgentWorkflowGraph()
        events = []
        svc.on_change["cb1"] = lambda e, d: events.append((e, d))
        gid = svc.create_graph("wf1")
        svc.add_node(gid, "a")
        svc.add_node(gid, "b")
        svc.add_edge(gid, "a", "b")
        assert any(e[0] == "edge_added" for e in events)

    def test_remove_callback_existing(self):
        svc = AgentWorkflowGraph()
        svc.on_change["cb1"] = lambda e, d: None
        assert svc.remove_callback("cb1") is True
        assert "cb1" not in svc.on_change

    def test_remove_callback_nonexistent(self):
        svc = AgentWorkflowGraph()
        assert svc.remove_callback("nope") is False

    def test_fire_silent_on_error(self):
        svc = AgentWorkflowGraph()
        svc.on_change["bad"] = lambda e, d: (_ for _ in ()).throw(RuntimeError("boom"))
        gid = svc.create_graph("wf1")
        assert gid.startswith("awgr-")


class TestPrune:
    """Pruning when exceeding MAX_ENTRIES."""

    def test_prune_limits_entries(self):
        svc = AgentWorkflowGraph()
        svc.MAX_ENTRIES = 5
        for i in range(8):
            svc.create_graph("wf1", label=str(i))
        assert svc.get_graph_count() == 5
