"""Tests for AgentWorkflowScope service."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.agent_workflow_scope import AgentWorkflowScope


def test_create_scope_returns_id():
    svc = AgentWorkflowScope()
    sid = svc.create_scope("a1", "wf1")
    assert sid.startswith("awsc-")
    assert len(sid) > len("awsc-")


def test_create_scope_unique_ids():
    svc = AgentWorkflowScope()
    id1 = svc.create_scope("a1", "wf1")
    id2 = svc.create_scope("a1", "wf1")
    assert id1 != id2


def test_get_scope_by_id():
    svc = AgentWorkflowScope()
    sid = svc.create_scope("a1", "wf1", parent_scope_id="parent-1", variables={"x": 1})
    entry = svc.get_scope(sid)
    assert entry is not None
    assert entry["scope_id"] == sid
    assert entry["agent_id"] == "a1"
    assert entry["workflow_name"] == "wf1"
    assert entry["parent_scope_id"] == "parent-1"
    assert entry["variables"] == {"x": 1}


def test_get_scope_not_found():
    svc = AgentWorkflowScope()
    assert svc.get_scope("awsc-nonexistent") is None


def test_get_scope_returns_dict():
    svc = AgentWorkflowScope()
    sid = svc.create_scope("a1", "wf1")
    result = svc.get_scope(sid)
    assert isinstance(result, dict)


def test_create_scope_default_variables():
    svc = AgentWorkflowScope()
    sid = svc.create_scope("a1", "wf1")
    entry = svc.get_scope(sid)
    assert entry["variables"] == {}


def test_create_scope_default_parent():
    svc = AgentWorkflowScope()
    sid = svc.create_scope("a1", "wf1")
    entry = svc.get_scope(sid)
    assert entry["parent_scope_id"] == ""


def test_set_variable():
    svc = AgentWorkflowScope()
    sid = svc.create_scope("a1", "wf1")
    result = svc.set_variable(sid, "key1", "value1")
    assert result is True
    entry = svc.get_scope(sid)
    assert entry["variables"]["key1"] == "value1"


def test_set_variable_not_found():
    svc = AgentWorkflowScope()
    assert svc.set_variable("awsc-missing", "k", "v") is False


def test_get_variable():
    svc = AgentWorkflowScope()
    sid = svc.create_scope("a1", "wf1", variables={"foo": 42})
    assert svc.get_variable(sid, "foo") == 42


def test_get_variable_not_found_key():
    svc = AgentWorkflowScope()
    sid = svc.create_scope("a1", "wf1")
    assert svc.get_variable(sid, "missing") is None


def test_get_variable_not_found_scope():
    svc = AgentWorkflowScope()
    assert svc.get_variable("awsc-missing", "k") is None


def test_get_scopes_for_agent():
    svc = AgentWorkflowScope()
    svc.create_scope("a1", "wf1")
    svc.create_scope("a1", "wf2")
    svc.create_scope("a2", "wf1")
    results = svc.get_scopes(agent_id="a1")
    assert len(results) == 2
    assert all(r["agent_id"] == "a1" for r in results)


def test_get_scopes_all():
    svc = AgentWorkflowScope()
    svc.create_scope("a1", "wf1")
    svc.create_scope("a2", "wf2")
    results = svc.get_scopes()
    assert len(results) == 2


def test_get_scopes_newest_first():
    svc = AgentWorkflowScope()
    svc.create_scope("a1", "wf1", variables={"order": 1})
    svc.create_scope("a1", "wf1", variables={"order": 2})
    svc.create_scope("a1", "wf1", variables={"order": 3})
    results = svc.get_scopes(agent_id="a1")
    assert results[0]["variables"]["order"] == 3
    assert results[-1]["variables"]["order"] == 1


def test_get_scopes_limit():
    svc = AgentWorkflowScope()
    for i in range(10):
        svc.create_scope("a1", f"wf{i}")
    results = svc.get_scopes(agent_id="a1", limit=3)
    assert len(results) == 3


def test_get_scopes_default_limit():
    svc = AgentWorkflowScope()
    for i in range(60):
        svc.create_scope("a1", f"wf{i}")
    results = svc.get_scopes(agent_id="a1")
    assert len(results) == 50


def test_get_scopes_empty():
    svc = AgentWorkflowScope()
    results = svc.get_scopes(agent_id="a1")
    assert results == []


def test_get_scope_count():
    svc = AgentWorkflowScope()
    svc.create_scope("a1", "wf1")
    svc.create_scope("a1", "wf2")
    svc.create_scope("a2", "wf1")
    assert svc.get_scope_count() == 3
    assert svc.get_scope_count(agent_id="a1") == 2
    assert svc.get_scope_count(agent_id="a2") == 1
    assert svc.get_scope_count(agent_id="a3") == 0


def test_get_stats():
    svc = AgentWorkflowScope()
    svc.create_scope("a1", "wf1", variables={"x": 1, "y": 2})
    svc.create_scope("a2", "wf2", variables={"z": 3})
    svc.create_scope("a1", "wf3")
    stats = svc.get_stats()
    assert stats["total_scopes"] == 3
    assert stats["unique_agents"] == 2
    assert stats["total_variables"] == 3


def test_get_stats_empty():
    svc = AgentWorkflowScope()
    stats = svc.get_stats()
    assert stats["total_scopes"] == 0
    assert stats["unique_agents"] == 0
    assert stats["total_variables"] == 0


def test_reset():
    svc = AgentWorkflowScope()
    svc.create_scope("a1", "wf1")
    svc._callbacks["cb1"] = lambda a, d: None
    svc.on_change = lambda a, d: None
    svc.reset()
    assert svc.get_stats()["total_scopes"] == 0
    assert len(svc._callbacks) == 0
    assert svc.on_change is None


def test_on_change_callback_create():
    events = []
    svc = AgentWorkflowScope()
    svc.on_change = lambda action, data: events.append(action)
    svc.create_scope("a1", "wf1")
    assert "scope_created" in events


def test_on_change_callback_set_variable():
    events = []
    svc = AgentWorkflowScope()
    svc.on_change = lambda action, data: events.append(action)
    sid = svc.create_scope("a1", "wf1")
    svc.set_variable(sid, "k", "v")
    assert "variable_set" in events


def test_on_change_getter_setter():
    svc = AgentWorkflowScope()
    assert svc.on_change is None
    handler = lambda a, d: None
    svc.on_change = handler
    assert svc.on_change is handler


def test_remove_callback():
    svc = AgentWorkflowScope()
    svc._callbacks["cb1"] = lambda a, d: None
    assert svc.remove_callback("cb1") is True
    assert svc.remove_callback("cb1") is False


def test_remove_callback_nonexistent():
    svc = AgentWorkflowScope()
    assert svc.remove_callback("nope") is False


def test_callbacks_dict_fires():
    events = []
    svc = AgentWorkflowScope()
    svc._callbacks["tracker"] = lambda action, data: events.append((action, data["scope_id"]))
    sid = svc.create_scope("a1", "wf1")
    assert len(events) == 1
    assert events[0][0] == "scope_created"
    assert events[0][1] == sid


def test_callback_exception_silenced():
    svc = AgentWorkflowScope()
    svc._callbacks["bad"] = lambda a, d: (_ for _ in ()).throw(ValueError("boom"))
    svc.on_change = lambda a, d: (_ for _ in ()).throw(RuntimeError("crash"))
    # Should not raise
    sid = svc.create_scope("a1", "wf1")
    assert sid.startswith("awsc-")


def test_pruning():
    svc = AgentWorkflowScope()
    svc.MAX_ENTRIES = 5
    for i in range(7):
        svc.create_scope("a1", f"wf{i}")
    assert len(svc._state.entries) <= 6
    stats = svc.get_stats()
    assert stats["total_scopes"] <= 6


def test_prefix_and_max_entries():
    assert AgentWorkflowScope.PREFIX == "awsc-"
    assert AgentWorkflowScope.MAX_ENTRIES == 10000


def test_create_scope_variables_isolated():
    svc = AgentWorkflowScope()
    original = {"nested": 1}
    sid = svc.create_scope("a1", "wf1", variables=original)
    original["nested"] = 999
    entry = svc.get_scope(sid)
    assert entry["variables"]["nested"] == 1


if __name__ == "__main__":
    tests = [
        test_create_scope_returns_id,
        test_create_scope_unique_ids,
        test_get_scope_by_id,
        test_get_scope_not_found,
        test_get_scope_returns_dict,
        test_create_scope_default_variables,
        test_create_scope_default_parent,
        test_set_variable,
        test_set_variable_not_found,
        test_get_variable,
        test_get_variable_not_found_key,
        test_get_variable_not_found_scope,
        test_get_scopes_for_agent,
        test_get_scopes_all,
        test_get_scopes_newest_first,
        test_get_scopes_limit,
        test_get_scopes_default_limit,
        test_get_scopes_empty,
        test_get_scope_count,
        test_get_stats,
        test_get_stats_empty,
        test_reset,
        test_on_change_callback_create,
        test_on_change_callback_set_variable,
        test_on_change_getter_setter,
        test_remove_callback,
        test_remove_callback_nonexistent,
        test_callbacks_dict_fires,
        test_callback_exception_silenced,
        test_pruning,
        test_prefix_and_max_entries,
        test_create_scope_variables_isolated,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
    print(f"{passed}/{len(tests)} tests passed")
