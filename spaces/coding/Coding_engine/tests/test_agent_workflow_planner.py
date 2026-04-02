"""Tests for AgentWorkflowPlanner."""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.agent_workflow_planner import AgentWorkflowPlanner


def test_init():
    p = AgentWorkflowPlanner()
    assert p._state is not None
    assert p._callbacks == {}
    assert p._on_change is None


def test_generate_id_prefix():
    p = AgentWorkflowPlanner()
    pid = p._generate_id("test")
    assert pid.startswith("awpl-")
    assert len(pid) == 5 + 16


def test_generate_id_unique():
    p = AgentWorkflowPlanner()
    id1 = p._generate_id("test")
    id2 = p._generate_id("test")
    assert id1 != id2


def test_create_plan_basic():
    p = AgentWorkflowPlanner()
    pid = p.create_plan("agent1", "deploy", ["build", "test", "release"])
    assert pid.startswith("awpl-")
    plan = p.get_plan(pid)
    assert plan["agent_id"] == "agent1"
    assert plan["workflow_name"] == "deploy"
    assert plan["steps"] == ["build", "test", "release"]
    assert plan["strategy"] == "sequential"


def test_create_plan_with_strategy():
    p = AgentWorkflowPlanner()
    pid = p.create_plan("agent1", "pipeline", ["a", "b"], strategy="parallel")
    plan = p.get_plan(pid)
    assert plan["strategy"] == "parallel"


def test_create_plan_with_metadata():
    p = AgentWorkflowPlanner()
    pid = p.create_plan("agent1", "wf1", ["step1"], metadata={"priority": "high"})
    plan = p.get_plan(pid)
    assert plan["metadata"] == {"priority": "high"}


def test_create_plan_default_metadata():
    p = AgentWorkflowPlanner()
    pid = p.create_plan("agent1", "wf1", ["step1"])
    plan = p.get_plan(pid)
    assert plan["metadata"] == {}


def test_get_plan_not_found():
    p = AgentWorkflowPlanner()
    assert p.get_plan("nonexistent") is None


def test_update_plan_steps():
    p = AgentWorkflowPlanner()
    pid = p.create_plan("agent1", "wf1", ["a", "b"])
    result = p.update_plan(pid, steps=["x", "y", "z"])
    assert result is True
    plan = p.get_plan(pid)
    assert plan["steps"] == ["x", "y", "z"]


def test_update_plan_strategy():
    p = AgentWorkflowPlanner()
    pid = p.create_plan("agent1", "wf1", ["a"], strategy="sequential")
    result = p.update_plan(pid, strategy="parallel")
    assert result is True
    plan = p.get_plan(pid)
    assert plan["strategy"] == "parallel"


def test_update_plan_not_found():
    p = AgentWorkflowPlanner()
    assert p.update_plan("nonexistent", steps=["a"]) is False


def test_update_plan_no_changes():
    p = AgentWorkflowPlanner()
    pid = p.create_plan("agent1", "wf1", ["a", "b"])
    result = p.update_plan(pid)
    assert result is True
    plan = p.get_plan(pid)
    assert plan["steps"] == ["a", "b"]


def test_get_plans_all():
    p = AgentWorkflowPlanner()
    p.create_plan("agent1", "wf1", ["a"])
    p.create_plan("agent2", "wf2", ["b"])
    results = p.get_plans()
    assert len(results) == 2


def test_get_plans_by_agent():
    p = AgentWorkflowPlanner()
    p.create_plan("agent1", "wf1", ["a"])
    p.create_plan("agent2", "wf2", ["b"])
    p.create_plan("agent1", "wf3", ["c"])
    results = p.get_plans(agent_id="agent1")
    assert len(results) == 2
    assert all(r["agent_id"] == "agent1" for r in results)


def test_get_plans_by_workflow():
    p = AgentWorkflowPlanner()
    p.create_plan("agent1", "wf1", ["a"])
    p.create_plan("agent2", "wf1", ["b"])
    p.create_plan("agent1", "wf2", ["c"])
    results = p.get_plans(workflow_name="wf1")
    assert len(results) == 2
    assert all(r["workflow_name"] == "wf1" for r in results)


def test_get_plans_newest_first():
    p = AgentWorkflowPlanner()
    p.create_plan("agent1", "wf1", ["first"])
    time.sleep(0.01)
    p.create_plan("agent1", "wf1", ["second"])
    results = p.get_plans()
    assert results[0]["steps"] == ["second"]
    assert results[1]["steps"] == ["first"]


def test_get_plans_limit():
    p = AgentWorkflowPlanner()
    for i in range(10):
        p.create_plan("agent1", "wf1", [f"step{i}"])
    results = p.get_plans(limit=3)
    assert len(results) == 3


def test_get_plan_count_all():
    p = AgentWorkflowPlanner()
    p.create_plan("agent1", "wf1", ["a"])
    p.create_plan("agent2", "wf2", ["b"])
    assert p.get_plan_count() == 2


def test_get_plan_count_by_agent():
    p = AgentWorkflowPlanner()
    p.create_plan("agent1", "wf1", ["a"])
    p.create_plan("agent2", "wf2", ["b"])
    p.create_plan("agent1", "wf3", ["c"])
    assert p.get_plan_count(agent_id="agent1") == 2


def test_get_stats():
    p = AgentWorkflowPlanner()
    p.create_plan("agent1", "wf1", ["a"], strategy="sequential")
    p.create_plan("agent2", "wf2", ["b"], strategy="parallel")
    p.create_plan("agent1", "wf3", ["c"], strategy="sequential")
    stats = p.get_stats()
    assert stats["total_plans"] == 3
    assert stats["unique_agents"] == 2
    assert stats["by_strategy"]["sequential"] == 2
    assert stats["by_strategy"]["parallel"] == 1


def test_get_stats_empty():
    p = AgentWorkflowPlanner()
    stats = p.get_stats()
    assert stats["total_plans"] == 0
    assert stats["unique_agents"] == 0
    assert stats["by_strategy"] == {}


def test_reset():
    p = AgentWorkflowPlanner()
    p.create_plan("agent1", "wf1", ["a"])
    p.create_plan("agent2", "wf2", ["b"])
    p.reset()
    assert len(p._state.entries) == 0
    assert p._state._seq == 0


def test_on_change_property():
    p = AgentWorkflowPlanner()
    assert p.on_change is None
    handler = lambda action, data: None
    p.on_change = handler
    assert p.on_change is handler


def test_fire_on_change_called():
    p = AgentWorkflowPlanner()
    events = []
    p.on_change = lambda action, data: events.append((action, data))
    p.create_plan("agent1", "wf1", ["a"])
    assert len(events) == 1
    assert events[0][0] == "create_plan"


def test_fire_callback_called():
    p = AgentWorkflowPlanner()
    events = []
    p._callbacks["test_cb"] = lambda action, data: events.append((action, data))
    p.create_plan("agent1", "wf1", ["a"])
    assert len(events) == 1
    assert events[0][0] == "create_plan"


def test_fire_silent_exception():
    p = AgentWorkflowPlanner()
    p.on_change = lambda action, data: (_ for _ in ()).throw(ValueError("boom"))
    p._callbacks["bad"] = lambda action, data: (_ for _ in ()).throw(RuntimeError("fail"))
    pid = p.create_plan("agent1", "wf1", ["a"])
    assert pid.startswith("awpl-")


def test_remove_callback_success():
    p = AgentWorkflowPlanner()
    p._callbacks["cb1"] = lambda a, d: None
    assert p.remove_callback("cb1") is True
    assert "cb1" not in p._callbacks


def test_remove_callback_not_found():
    p = AgentWorkflowPlanner()
    assert p.remove_callback("nonexistent") is False


def test_prune_evicts_oldest():
    p = AgentWorkflowPlanner()
    p.MAX_ENTRIES = 5
    ids = []
    for i in range(7):
        ids.append(p.create_plan("agent1", "wf1", [f"step{i}"]))
    assert len(p._state.entries) == 5
    assert p.get_plan(ids[0]) is None
    assert p.get_plan(ids[1]) is None
    assert p.get_plan(ids[6]) is not None


def test_create_plan_returns_dict_via_get():
    p = AgentWorkflowPlanner()
    pid = p.create_plan("agent1", "wf1", ["a"])
    plan = p.get_plan(pid)
    assert isinstance(plan, dict)
    assert "plan_id" in plan
    assert "created_at" in plan


def test_get_stats_returns_dict():
    p = AgentWorkflowPlanner()
    stats = p.get_stats()
    assert isinstance(stats, dict)


def test_get_plans_combined_filters():
    p = AgentWorkflowPlanner()
    p.create_plan("agent1", "wf1", ["a"])
    p.create_plan("agent1", "wf1", ["b"])
    p.create_plan("agent1", "wf2", ["c"])
    p.create_plan("agent2", "wf1", ["d"])
    results = p.get_plans(agent_id="agent1", workflow_name="wf1")
    assert len(results) == 2


def test_fire_on_reset():
    p = AgentWorkflowPlanner()
    events = []
    p.on_change = lambda action, data: events.append((action, data))
    p.reset()
    assert len(events) == 1
    assert events[0][0] == "reset"


def test_fire_on_get_stats():
    p = AgentWorkflowPlanner()
    events = []
    p.on_change = lambda action, data: events.append((action, data))
    p.get_stats()
    assert len(events) == 1
    assert events[0][0] == "get_stats"


def test_fire_on_update_plan():
    p = AgentWorkflowPlanner()
    events = []
    p.on_change = lambda action, data: events.append((action, data))
    pid = p.create_plan("agent1", "wf1", ["a"])
    events.clear()
    p.update_plan(pid, steps=["x"])
    assert len(events) == 1
    assert events[0][0] == "update_plan"
