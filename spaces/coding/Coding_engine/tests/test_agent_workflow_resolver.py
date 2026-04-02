"""Tests for AgentWorkflowResolver service."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.agent_workflow_resolver import AgentWorkflowResolver


def test_add_dependency_returns_id():
    r = AgentWorkflowResolver()
    dep_id = r.add_dependency("wf1", "step_a")
    assert dep_id.startswith("awre-")
    assert len(dep_id) > len("awre-")


def test_add_dependency_unique_ids():
    r = AgentWorkflowResolver()
    id1 = r.add_dependency("wf1", "step_a")
    id2 = r.add_dependency("wf1", "step_b")
    assert id1 != id2


def test_add_dependency_returns_dict():
    r = AgentWorkflowResolver()
    dep_id = r.add_dependency("wf1", "step_a", ["step_b"])
    entry = r.get_dependency(dep_id)
    assert isinstance(entry, dict)


def test_get_dependency_by_id():
    r = AgentWorkflowResolver()
    dep_id = r.add_dependency("wf1", "step_a", ["step_b", "step_c"])
    entry = r.get_dependency(dep_id)
    assert entry is not None
    assert entry["dep_id"] == dep_id
    assert entry["workflow_id"] == "wf1"
    assert entry["step_name"] == "step_a"
    assert entry["depends_on"] == ["step_b", "step_c"]


def test_get_dependency_not_found():
    r = AgentWorkflowResolver()
    assert r.get_dependency("awre-nonexistent") is None


def test_add_dependency_no_depends_on():
    r = AgentWorkflowResolver()
    dep_id = r.add_dependency("wf1", "step_a")
    entry = r.get_dependency(dep_id)
    assert entry["depends_on"] == []


def test_resolve_order_no_dependencies():
    r = AgentWorkflowResolver()
    r.add_dependency("wf1", "step_a")
    r.add_dependency("wf1", "step_b")
    r.add_dependency("wf1", "step_c")
    order = r.resolve_order("wf1")
    assert isinstance(order, list)
    assert set(order) == {"step_a", "step_b", "step_c"}


def test_resolve_order_with_dependencies():
    r = AgentWorkflowResolver()
    r.add_dependency("wf1", "step_a")
    r.add_dependency("wf1", "step_b", ["step_a"])
    r.add_dependency("wf1", "step_c", ["step_b"])
    order = r.resolve_order("wf1")
    assert order.index("step_a") < order.index("step_b")
    assert order.index("step_b") < order.index("step_c")


def test_resolve_order_returns_list_of_strings():
    r = AgentWorkflowResolver()
    r.add_dependency("wf1", "step_a")
    order = r.resolve_order("wf1")
    assert isinstance(order, list)
    assert all(isinstance(s, str) for s in order)


def test_resolve_order_empty_workflow():
    r = AgentWorkflowResolver()
    order = r.resolve_order("wf_nonexistent")
    assert order == []


def test_resolve_order_diamond_dependency():
    r = AgentWorkflowResolver()
    r.add_dependency("wf1", "step_a")
    r.add_dependency("wf1", "step_b", ["step_a"])
    r.add_dependency("wf1", "step_c", ["step_a"])
    r.add_dependency("wf1", "step_d", ["step_b", "step_c"])
    order = r.resolve_order("wf1")
    assert order.index("step_a") < order.index("step_b")
    assert order.index("step_a") < order.index("step_c")
    assert order.index("step_b") < order.index("step_d")
    assert order.index("step_c") < order.index("step_d")


def test_resolve_order_isolates_workflows():
    r = AgentWorkflowResolver()
    r.add_dependency("wf1", "step_a")
    r.add_dependency("wf1", "step_b", ["step_a"])
    r.add_dependency("wf2", "step_x")
    order1 = r.resolve_order("wf1")
    order2 = r.resolve_order("wf2")
    assert "step_x" not in order1
    assert "step_a" not in order2


def test_get_dependencies_for_workflow():
    r = AgentWorkflowResolver()
    r.add_dependency("wf1", "step_a")
    r.add_dependency("wf1", "step_b")
    r.add_dependency("wf2", "step_x")
    results = r.get_dependencies("wf1")
    assert len(results) == 2
    assert all(d["workflow_id"] == "wf1" for d in results)


def test_get_dependencies_newest_first():
    r = AgentWorkflowResolver()
    r.add_dependency("wf1", "step_a")
    r.add_dependency("wf1", "step_b")
    r.add_dependency("wf1", "step_c")
    results = r.get_dependencies("wf1")
    assert results[0]["step_name"] == "step_c"
    assert results[-1]["step_name"] == "step_a"


def test_get_dependencies_limit():
    r = AgentWorkflowResolver()
    for i in range(10):
        r.add_dependency("wf1", f"step_{i}")
    results = r.get_dependencies("wf1", limit=3)
    assert len(results) == 3


def test_get_dependencies_default_limit():
    r = AgentWorkflowResolver()
    for i in range(60):
        r.add_dependency("wf1", f"step_{i}")
    results = r.get_dependencies("wf1")
    assert len(results) == 50


def test_get_dependency_count_all():
    r = AgentWorkflowResolver()
    r.add_dependency("wf1", "step_a")
    r.add_dependency("wf2", "step_b")
    r.add_dependency("wf1", "step_c")
    assert r.get_dependency_count() == 3


def test_get_dependency_count_by_workflow():
    r = AgentWorkflowResolver()
    r.add_dependency("wf1", "step_a")
    r.add_dependency("wf2", "step_b")
    r.add_dependency("wf1", "step_c")
    assert r.get_dependency_count("wf1") == 2
    assert r.get_dependency_count("wf2") == 1


def test_get_dependency_count_empty():
    r = AgentWorkflowResolver()
    assert r.get_dependency_count() == 0
    assert r.get_dependency_count("wf1") == 0


def test_get_stats():
    r = AgentWorkflowResolver()
    r.add_dependency("wf1", "step_a")
    r.add_dependency("wf1", "step_b", ["step_a"])
    r.add_dependency("wf2", "step_x")
    stats = r.get_stats()
    assert stats["total_dependencies"] == 3
    assert stats["unique_workflows"] == 2
    assert stats["total_steps"] == 3


def test_get_stats_empty():
    r = AgentWorkflowResolver()
    stats = r.get_stats()
    assert stats["total_dependencies"] == 0
    assert stats["unique_workflows"] == 0
    assert stats["total_steps"] == 0


def test_reset():
    r = AgentWorkflowResolver()
    r.add_dependency("wf1", "step_a")
    r._callbacks["cb1"] = lambda a, d: None
    r.on_change = lambda a, d: None
    r.reset()
    assert r.get_stats()["total_dependencies"] == 0
    assert len(r._callbacks) == 0
    assert r.on_change is None


def test_on_change_callback_add():
    events = []
    r = AgentWorkflowResolver()
    r.on_change = lambda action, data: events.append(action)
    r.add_dependency("wf1", "step_a")
    assert "dependency_added" in events


def test_on_change_callback_resolve():
    events = []
    r = AgentWorkflowResolver()
    r.on_change = lambda action, data: events.append(action)
    r.add_dependency("wf1", "step_a")
    r.resolve_order("wf1")
    assert "order_resolved" in events


def test_on_change_getter_setter():
    r = AgentWorkflowResolver()
    assert r.on_change is None
    handler = lambda a, d: None
    r.on_change = handler
    assert r.on_change is handler


def test_remove_callback():
    r = AgentWorkflowResolver()
    r._callbacks["cb1"] = lambda a, d: None
    assert r.remove_callback("cb1") is True
    assert r.remove_callback("cb1") is False


def test_remove_callback_nonexistent():
    r = AgentWorkflowResolver()
    assert r.remove_callback("nope") is False


def test_callbacks_dict_fires():
    events = []
    r = AgentWorkflowResolver()
    r._callbacks["tracker"] = lambda action, data: events.append((action, data["dep_id"]))
    dep_id = r.add_dependency("wf1", "step_a")
    assert len(events) == 1
    assert events[0][0] == "dependency_added"
    assert events[0][1] == dep_id


def test_callback_exception_silenced():
    r = AgentWorkflowResolver()
    r._callbacks["bad"] = lambda a, d: (_ for _ in ()).throw(ValueError("boom"))
    r.on_change = lambda a, d: (_ for _ in ()).throw(RuntimeError("crash"))
    dep_id = r.add_dependency("wf1", "step_a")
    assert dep_id.startswith("awre-")


def test_pruning():
    r = AgentWorkflowResolver()
    r.MAX_ENTRIES = 5
    for i in range(7):
        r.add_dependency("wf1", f"step_{i}")
    assert len(r._state.entries) <= 6
    stats = r.get_stats()
    assert stats["total_dependencies"] <= 6


def test_prefix_and_max_entries():
    assert AgentWorkflowResolver.PREFIX == "awre-"
    assert AgentWorkflowResolver.MAX_ENTRIES == 10000


if __name__ == "__main__":
    tests = [
        test_add_dependency_returns_id,
        test_add_dependency_unique_ids,
        test_add_dependency_returns_dict,
        test_get_dependency_by_id,
        test_get_dependency_not_found,
        test_add_dependency_no_depends_on,
        test_resolve_order_no_dependencies,
        test_resolve_order_with_dependencies,
        test_resolve_order_returns_list_of_strings,
        test_resolve_order_empty_workflow,
        test_resolve_order_diamond_dependency,
        test_resolve_order_isolates_workflows,
        test_get_dependencies_for_workflow,
        test_get_dependencies_newest_first,
        test_get_dependencies_limit,
        test_get_dependencies_default_limit,
        test_get_dependency_count_all,
        test_get_dependency_count_by_workflow,
        test_get_dependency_count_empty,
        test_get_stats,
        test_get_stats_empty,
        test_reset,
        test_on_change_callback_add,
        test_on_change_callback_resolve,
        test_on_change_getter_setter,
        test_remove_callback,
        test_remove_callback_nonexistent,
        test_callbacks_dict_fires,
        test_callback_exception_silenced,
        test_pruning,
        test_prefix_and_max_entries,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
    print(f"{passed}/{len(tests)} tests passed")
