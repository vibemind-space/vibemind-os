"""Tests for AgentDependencyResolver."""

import sys

sys.path.insert(0, ".")

from src.services.agent_dependency_resolver import AgentDependencyResolver


def test_add_dependency():
    r = AgentDependencyResolver()
    dep_id = r.add_dependency("taskA", "taskB")
    assert dep_id.startswith("adr-"), f"Expected adr- prefix, got {dep_id}"
    assert len(dep_id) > 4
    # Empty args should return empty string
    assert r.add_dependency("", "taskB") == ""
    assert r.add_dependency("taskA", "") == ""
    print("  test_add_dependency PASSED")


def test_remove_dependency():
    r = AgentDependencyResolver()
    dep_id = r.add_dependency("taskA", "taskB")
    assert r.remove_dependency(dep_id) is True
    assert r.remove_dependency(dep_id) is False  # already removed
    assert r.remove_dependency("nonexistent") is False
    print("  test_remove_dependency PASSED")


def test_get_dependencies():
    r = AgentDependencyResolver()
    r.add_dependency("taskA", "taskB")
    r.add_dependency("taskA", "taskC")
    deps = r.get_dependencies("taskA")
    assert "taskB" in deps, f"taskB not in {deps}"
    assert "taskC" in deps, f"taskC not in {deps}"
    assert r.get_dependencies("taskZ") == []
    print("  test_get_dependencies PASSED")


def test_get_dependents():
    r = AgentDependencyResolver()
    r.add_dependency("taskA", "taskX")
    r.add_dependency("taskB", "taskX")
    dependents = r.get_dependents("taskX")
    assert "taskA" in dependents, f"taskA not in {dependents}"
    assert "taskB" in dependents, f"taskB not in {dependents}"
    assert r.get_dependents("taskZ") == []
    print("  test_get_dependents PASSED")


def test_is_resolved():
    r = AgentDependencyResolver()
    r.add_dependency("taskA", "taskB")
    r.add_dependency("taskA", "taskC")
    # Not resolved – missing taskB and taskC
    assert r.is_resolved("taskA", set()) is False
    # Partially resolved
    assert r.is_resolved("taskA", {"taskB"}) is False
    # Fully resolved
    assert r.is_resolved("taskA", {"taskB", "taskC"}) is True
    # No dependencies -> resolved
    assert r.is_resolved("taskZ", set()) is True
    print("  test_is_resolved PASSED")


def test_resolve_order():
    r = AgentDependencyResolver()
    r.add_dependency("taskA", "taskB")
    r.add_dependency("taskC", "taskD")
    # With no completed tasks, only tasks with no deps are resolved
    result = r.resolve_order(["taskA", "taskB", "taskC", "taskD"])
    assert "taskB" in result  # taskB has no deps
    assert "taskD" in result  # taskD has no deps
    assert "taskA" not in result  # taskA depends on taskB
    assert "taskC" not in result  # taskC depends on taskD
    # With taskB completed
    result2 = r.resolve_order(["taskA", "taskC"], completed_tasks={"taskB"})
    assert "taskA" in result2
    assert "taskC" not in result2
    # None completed_tasks should default to empty set
    result3 = r.resolve_order(["taskB", "taskD"], completed_tasks=None)
    assert "taskB" in result3
    assert "taskD" in result3
    print("  test_resolve_order PASSED")


def test_get_dependency_count():
    r = AgentDependencyResolver()
    r.add_dependency("taskA", "taskB")
    r.add_dependency("taskA", "taskC")
    r.add_dependency("taskD", "taskE")
    # Total count
    assert r.get_dependency_count() == 3, f"Expected 3, got {r.get_dependency_count()}"
    # Per-task count
    assert r.get_dependency_count("taskA") == 2, f"Expected 2, got {r.get_dependency_count('taskA')}"
    assert r.get_dependency_count("taskD") == 1
    assert r.get_dependency_count("taskZ") == 0
    print("  test_get_dependency_count PASSED")


def test_list_tasks():
    r = AgentDependencyResolver()
    r.add_dependency("taskA", "taskB")
    r.add_dependency("taskC", "taskD")
    tasks = r.list_tasks()
    assert set(tasks) == {"taskA", "taskB", "taskC", "taskD"}, f"Got {tasks}"
    print("  test_list_tasks PASSED")


def test_callbacks():
    r = AgentDependencyResolver()
    events = []

    def my_cb(action, detail):
        events.append((action, detail))

    assert r.on_change("cb1", my_cb) is True
    assert r.on_change("cb1", my_cb) is False  # duplicate name
    dep_id = r.add_dependency("taskA", "taskB")
    assert len(events) == 1
    assert events[0][0] == "dependency_added"
    r.remove_dependency(dep_id)
    assert len(events) == 2
    assert events[1][0] == "dependency_removed"
    # remove_callback
    assert r.remove_callback("cb1") is True
    assert r.remove_callback("cb1") is False
    r.add_dependency("taskX", "taskY")
    assert len(events) == 2  # no new events after callback removed
    print("  test_callbacks PASSED")


def test_stats():
    r = AgentDependencyResolver()
    r.add_dependency("taskA", "taskB")
    r.add_dependency("taskC", "taskD")
    stats = r.get_stats()
    assert stats["dependency_count"] == 2
    assert stats["task_count"] == 4
    assert stats["seq"] >= 2
    assert "max_entries" in stats
    assert "callback_count" in stats
    print("  test_stats PASSED")


def test_reset():
    r = AgentDependencyResolver()
    r.add_dependency("taskA", "taskB")
    r.on_change("cb1", lambda a, d: None)
    r.reset()
    assert r.get_dependency_count() == 0
    assert r.list_tasks() == []
    stats = r.get_stats()
    assert stats["dependency_count"] == 0
    assert stats["callback_count"] == 0
    assert stats["seq"] == 0
    print("  test_reset PASSED")


def main():
    tests = [
        test_add_dependency,
        test_remove_dependency,
        test_get_dependencies,
        test_get_dependents,
        test_is_resolved,
        test_resolve_order,
        test_get_dependency_count,
        test_list_tasks,
        test_callbacks,
        test_stats,
        test_reset,
    ]
    for t in tests:
        t()
    print(f"=== ALL {len(tests)} TESTS PASSED ===")


if __name__ == "__main__":
    main()
