"""Tests for AgentWorkflowCoordinator."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.agent_workflow_coordinator import AgentWorkflowCoordinator


def test_coordinate_returns_id():
    c = AgentWorkflowCoordinator()
    rid = c.coordinate("agent1", "build")
    assert isinstance(rid, str)
    assert len(rid) > 0


def test_coordinate_id_has_prefix():
    c = AgentWorkflowCoordinator()
    rid = c.coordinate("agent1", "build")
    assert rid.startswith("awco-")


def test_coordinate_id_length():
    c = AgentWorkflowCoordinator()
    rid = c.coordinate("agent1", "build")
    assert len(rid) == 5 + 12


def test_coordinate_unique_ids():
    c = AgentWorkflowCoordinator()
    ids = [c.coordinate("agent1", "build") for _ in range(20)]
    assert len(set(ids)) == 20


def test_coordinate_basic_fields():
    c = AgentWorkflowCoordinator()
    rid = c.coordinate("agent1", "deploy")
    entry = c.get_coordination(rid)
    assert entry["agent_id"] == "agent1"
    assert entry["workflow_name"] == "deploy"
    assert entry["strategy"] == "sequential"
    assert entry["participants"] == []
    assert entry["metadata"] == {}
    assert "created_at" in entry


def test_coordinate_with_participants():
    c = AgentWorkflowCoordinator()
    rid = c.coordinate("agent1", "build", participants=["a", "b", "c"])
    entry = c.get_coordination(rid)
    assert entry["participants"] == ["a", "b", "c"]


def test_coordinate_with_strategy():
    c = AgentWorkflowCoordinator()
    rid = c.coordinate("agent1", "build", strategy="parallel")
    entry = c.get_coordination(rid)
    assert entry["strategy"] == "parallel"


def test_coordinate_with_metadata():
    c = AgentWorkflowCoordinator()
    rid = c.coordinate("agent1", "build", metadata={"env": "prod"})
    entry = c.get_coordination(rid)
    assert entry["metadata"] == {"env": "prod"}


def test_get_coordination_found():
    c = AgentWorkflowCoordinator()
    rid = c.coordinate("agent1", "build")
    result = c.get_coordination(rid)
    assert result is not None
    assert result["record_id"] == rid


def test_get_coordination_not_found():
    c = AgentWorkflowCoordinator()
    result = c.get_coordination("awco-nonexistent")
    assert result is None


def test_get_coordination_returns_copy():
    c = AgentWorkflowCoordinator()
    rid = c.coordinate("agent1", "build")
    r1 = c.get_coordination(rid)
    r2 = c.get_coordination(rid)
    assert r1 is not r2
    assert r1 == r2


def test_get_coordinations_all():
    c = AgentWorkflowCoordinator()
    c.coordinate("agent1", "build")
    c.coordinate("agent2", "test")
    c.coordinate("agent1", "deploy")
    results = c.get_coordinations()
    assert len(results) == 3


def test_get_coordinations_filter_by_agent():
    c = AgentWorkflowCoordinator()
    c.coordinate("agent1", "build")
    c.coordinate("agent2", "test")
    c.coordinate("agent1", "deploy")
    results = c.get_coordinations(agent_id="agent1")
    assert len(results) == 2
    for r in results:
        assert r["agent_id"] == "agent1"


def test_get_coordinations_newest_first():
    c = AgentWorkflowCoordinator()
    r1 = c.coordinate("agent1", "first")
    r2 = c.coordinate("agent1", "second")
    r3 = c.coordinate("agent1", "third")
    results = c.get_coordinations()
    assert results[0]["record_id"] == r3
    assert results[1]["record_id"] == r2
    assert results[2]["record_id"] == r1


def test_get_coordinations_limit():
    c = AgentWorkflowCoordinator()
    for i in range(10):
        c.coordinate("agent1", f"wf{i}")
    results = c.get_coordinations(limit=3)
    assert len(results) == 3


def test_get_coordinations_returns_copies():
    c = AgentWorkflowCoordinator()
    c.coordinate("agent1", "build")
    results = c.get_coordinations()
    assert len(results) == 1
    results[0]["agent_id"] = "modified"
    original = c.get_coordinations()
    assert original[0]["agent_id"] == "agent1"


def test_get_coordination_count_all():
    c = AgentWorkflowCoordinator()
    assert c.get_coordination_count() == 0
    c.coordinate("agent1", "build")
    c.coordinate("agent2", "test")
    assert c.get_coordination_count() == 2


def test_get_coordination_count_filtered():
    c = AgentWorkflowCoordinator()
    c.coordinate("agent1", "build")
    c.coordinate("agent2", "test")
    c.coordinate("agent1", "deploy")
    assert c.get_coordination_count(agent_id="agent1") == 2
    assert c.get_coordination_count(agent_id="agent2") == 1
    assert c.get_coordination_count(agent_id="agent3") == 0


def test_get_stats_empty():
    c = AgentWorkflowCoordinator()
    stats = c.get_stats()
    assert stats["total_coordinations"] == 0
    assert stats["unique_agents"] == 0


def test_get_stats_with_data():
    c = AgentWorkflowCoordinator()
    c.coordinate("agent1", "build")
    c.coordinate("agent2", "test")
    c.coordinate("agent1", "deploy")
    stats = c.get_stats()
    assert stats["total_coordinations"] == 3
    assert stats["unique_agents"] == 2


def test_on_change_callback():
    c = AgentWorkflowCoordinator()
    calls = []
    c.on_change = lambda action, data: calls.append((action, data))
    c.coordinate("agent1", "build")
    assert len(calls) == 1
    assert calls[0][0] == "coordinate"


def test_on_change_getter():
    c = AgentWorkflowCoordinator()
    assert c.on_change is None
    cb = lambda a, d: None
    c.on_change = cb
    assert c.on_change is cb


def test_on_change_set_none():
    c = AgentWorkflowCoordinator()
    c.on_change = lambda a, d: None
    assert c.on_change is not None
    c.on_change = None
    assert c.on_change is None


def test_remove_callback_found():
    c = AgentWorkflowCoordinator()
    c._state.callbacks["my_cb"] = lambda a, d: None
    assert c.remove_callback("my_cb") is True
    assert "my_cb" not in c._state.callbacks


def test_remove_callback_not_found():
    c = AgentWorkflowCoordinator()
    assert c.remove_callback("nonexistent") is False


def test_fire_catches_exceptions():
    c = AgentWorkflowCoordinator()

    def bad_cb(action, data):
        raise RuntimeError("boom")

    c._state.callbacks["bad"] = bad_cb
    # Should not raise
    c.coordinate("agent1", "build")


def test_prune_at_max_entries():
    c = AgentWorkflowCoordinator()
    c.MAX_ENTRIES = 5
    for i in range(8):
        c.coordinate(f"agent{i}", f"wf{i}")
    assert len(c._state.entries) == 5


def test_prune_keeps_newest():
    c = AgentWorkflowCoordinator()
    c.MAX_ENTRIES = 3
    ids = []
    for i in range(6):
        ids.append(c.coordinate("agent1", f"wf{i}"))
    # The newest 3 should remain
    for rid in ids[-3:]:
        assert c.get_coordination(rid) is not None


def test_reset_clears_entries():
    c = AgentWorkflowCoordinator()
    c.coordinate("agent1", "build")
    c.coordinate("agent2", "test")
    assert c.get_coordination_count() == 2
    c.reset()
    assert c.get_coordination_count() == 0


def test_reset_clears_callbacks():
    c = AgentWorkflowCoordinator()
    c.on_change = lambda a, d: None
    c._state.callbacks["extra"] = lambda a, d: None
    c.reset()
    assert c.on_change is None
    assert len(c._state.callbacks) == 0


def test_reset_resets_seq():
    c = AgentWorkflowCoordinator()
    c.coordinate("agent1", "build")
    assert c._state._seq > 0
    c.reset()
    assert c._state._seq == 0
