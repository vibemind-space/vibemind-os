"""Test task dependency resolver."""
import sys
sys.path.insert(0, ".")

from src.services.task_dependency_resolver import TaskDependencyResolver


def test_add_task():
    """Add and remove tasks."""
    r = TaskDependencyResolver()
    tid = r.add_task("Build", category="build", priority=80)
    assert tid.startswith("td-")

    task = r.get_task(tid)
    assert task is not None
    assert task["name"] == "Build"
    assert task["status"] == "ready"  # No deps = ready
    assert task["priority"] == 80

    assert r.remove_task(tid) is True
    assert r.remove_task(tid) is False
    assert r.get_task(tid) is None
    print("OK: add task")


def test_dependencies():
    """Tasks with deps start pending."""
    r = TaskDependencyResolver()
    t1 = r.add_task("Compile")
    t2 = r.add_task("Link", dependencies=[t1])

    task2 = r.get_task(t2)
    assert task2["status"] == "pending"
    assert task2["dependency_count"] == 1

    # t1 has a dependent
    task1 = r.get_task(t1)
    assert task1["dependent_count"] == 1
    print("OK: dependencies")


def test_complete_cascades():
    """Completing a dep makes downstream ready."""
    r = TaskDependencyResolver()
    t1 = r.add_task("Compile")
    t2 = r.add_task("Link", dependencies=[t1])
    t3 = r.add_task("Package", dependencies=[t2])

    assert r.get_task(t2)["status"] == "pending"
    assert r.get_task(t3)["status"] == "pending"

    r.complete_task(t1)
    assert r.get_task(t2)["status"] == "ready"
    assert r.get_task(t3)["status"] == "pending"  # Still waiting on t2

    r.complete_task(t2)
    assert r.get_task(t3)["status"] == "ready"
    print("OK: complete cascades")


def test_fail_task():
    """Fail a task."""
    r = TaskDependencyResolver()
    t1 = r.add_task("Build")
    r.start_task(t1)
    assert r.fail_task(t1) is True
    assert r.get_task(t1)["status"] == "failed"

    assert r.fail_task(t1) is False  # Already failed
    assert r.fail_task("fake") is False
    print("OK: fail task")


def test_skip_task():
    """Skip acts like complete for deps."""
    r = TaskDependencyResolver()
    t1 = r.add_task("Optional")
    t2 = r.add_task("Next", dependencies=[t1])

    r.skip_task(t1)
    assert r.get_task(t1)["status"] == "skipped"
    assert r.get_task(t2)["status"] == "ready"
    print("OK: skip task")


def test_start_task():
    """Start a ready task."""
    r = TaskDependencyResolver()
    t1 = r.add_task("Build")
    assert r.start_task(t1) is True
    assert r.get_task(t1)["status"] == "running"

    # Can't start again
    assert r.start_task(t1) is False
    print("OK: start task")


def test_reset_task():
    """Reset failed task back to ready/pending."""
    r = TaskDependencyResolver()
    t1 = r.add_task("Build")
    r.start_task(t1)
    r.fail_task(t1)

    assert r.reset_task(t1) is True
    assert r.get_task(t1)["status"] == "ready"

    assert r.reset_task(t1) is False  # Now it's ready, not failed
    print("OK: reset task")


def test_add_remove_dependency():
    """Dynamically add/remove dependencies."""
    r = TaskDependencyResolver()
    t1 = r.add_task("A")
    t2 = r.add_task("B")

    assert r.add_dependency(t2, t1) is True
    assert r.get_task(t2)["status"] == "pending"

    # Remove dep
    assert r.remove_dependency(t2, t1) is True
    assert r.get_task(t2)["status"] == "ready"

    assert r.remove_dependency(t2, t1) is False  # Already removed
    print("OK: add remove dependency")


def test_cycle_detection():
    """Cycles are prevented."""
    r = TaskDependencyResolver()
    t1 = r.add_task("A")
    t2 = r.add_task("B", dependencies=[t1])

    # t1 -> t2, adding t2 -> t1 would create cycle
    assert r.add_dependency(t1, t2) is False
    assert r.has_cycle() is False
    print("OK: cycle detection")


def test_invalid_dependency():
    """Can't add dependency on nonexistent task."""
    r = TaskDependencyResolver()
    tid = r.add_task("A")
    assert r.add_task("B", dependencies=["fake"]) == ""
    print("OK: invalid dependency")


def test_get_all_deps():
    """Transitive dependencies."""
    r = TaskDependencyResolver()
    t1 = r.add_task("A")
    t2 = r.add_task("B", dependencies=[t1])
    t3 = r.add_task("C", dependencies=[t2])

    all_deps = r.get_all_dependencies(t3)
    assert t1 in all_deps
    assert t2 in all_deps
    assert len(all_deps) == 2

    all_deps_t = r.get_all_dependents(t1)
    assert t2 in all_deps_t
    assert t3 in all_deps_t
    print("OK: get all deps")


def test_get_ready_tasks():
    """Get ready tasks."""
    r = TaskDependencyResolver()
    t1 = r.add_task("A", priority=80)
    t2 = r.add_task("B", priority=50)
    t3 = r.add_task("C", priority=90, dependencies=[t1])

    ready = r.get_ready_tasks()
    assert len(ready) == 2  # A and B are ready, C is pending
    assert ready[0]["name"] == "A"  # Higher priority first
    print("OK: get ready tasks")


def test_topological_sort():
    """Topological ordering."""
    r = TaskDependencyResolver()
    t1 = r.add_task("A")
    t2 = r.add_task("B", dependencies=[t1])
    t3 = r.add_task("C", dependencies=[t1])
    t4 = r.add_task("D", dependencies=[t2, t3])

    order = r.topological_sort()
    assert order is not None
    assert order.index(t1) < order.index(t2)
    assert order.index(t1) < order.index(t3)
    assert order.index(t2) < order.index(t4)
    assert order.index(t3) < order.index(t4)
    print("OK: topological sort")


def test_execution_layers():
    """Parallel execution layers."""
    r = TaskDependencyResolver()
    t1 = r.add_task("A")
    t2 = r.add_task("B")
    t3 = r.add_task("C", dependencies=[t1, t2])
    t4 = r.add_task("D", dependencies=[t3])

    layers = r.get_execution_layers()
    assert len(layers) == 3
    assert set(layers[0]) == {t1, t2}  # Layer 0: A, B in parallel
    assert layers[1] == [t3]  # Layer 1: C
    assert layers[2] == [t4]  # Layer 2: D
    print("OK: execution layers")


def test_critical_path():
    """Longest dependency chain."""
    r = TaskDependencyResolver()
    t1 = r.add_task("A")
    t2 = r.add_task("B", dependencies=[t1])
    t3 = r.add_task("C", dependencies=[t2])
    t4 = r.add_task("D")  # Independent

    path = r.get_critical_path()
    assert len(path) == 3
    assert path == [t1, t2, t3]
    print("OK: critical path")


def test_cant_remove_with_dependents():
    """Can't remove task with dependents."""
    r = TaskDependencyResolver()
    t1 = r.add_task("A")
    t2 = r.add_task("B", dependencies=[t1])

    assert r.remove_task(t1) is False  # t2 depends on it
    assert r.remove_task(t2) is True
    assert r.remove_task(t1) is True
    print("OK: cant remove with dependents")


def test_list_tasks():
    """List tasks with filters."""
    r = TaskDependencyResolver()
    t1 = r.add_task("A", category="build")
    t2 = r.add_task("B", category="test", dependencies=[t1])

    all_tasks = r.list_tasks()
    assert len(all_tasks) == 2

    ready = r.list_tasks(status="ready")
    assert len(ready) == 1

    build = r.list_tasks(category="build")
    assert len(build) == 1

    limited = r.list_tasks(limit=1)
    assert len(limited) == 1
    print("OK: list tasks")


def test_list_categories():
    """List categories."""
    r = TaskDependencyResolver()
    r.add_task("A", category="build")
    r.add_task("B", category="test")
    r.add_task("C", category="build")

    cats = r.list_categories()
    assert cats["build"] == 2
    assert cats["test"] == 1
    print("OK: list categories")


def test_pending_count():
    """Pending count."""
    r = TaskDependencyResolver()
    t1 = r.add_task("A")
    t2 = r.add_task("B")

    assert r.pending_count() == 2
    r.complete_task(t1)
    assert r.pending_count() == 1
    print("OK: pending count")


def test_stats():
    """Stats are accurate."""
    r = TaskDependencyResolver()
    t1 = r.add_task("A")
    t2 = r.add_task("B")
    r.complete_task(t1)
    r.start_task(t2)
    r.fail_task(t2)

    stats = r.get_stats()
    assert stats["total_added"] == 2
    assert stats["total_completed"] == 1
    assert stats["total_failed"] == 1
    assert stats["total_tasks"] == 2
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    r = TaskDependencyResolver()
    r.add_task("A")

    r.reset()
    assert r.list_tasks() == []
    stats = r.get_stats()
    assert stats["total_tasks"] == 0
    print("OK: reset")


def main():
    print("=== Task Dependency Resolver Tests ===\n")
    test_add_task()
    test_dependencies()
    test_complete_cascades()
    test_fail_task()
    test_skip_task()
    test_start_task()
    test_reset_task()
    test_add_remove_dependency()
    test_cycle_detection()
    test_invalid_dependency()
    test_get_all_deps()
    test_get_ready_tasks()
    test_topological_sort()
    test_execution_layers()
    test_critical_path()
    test_cant_remove_with_dependents()
    test_list_tasks()
    test_list_categories()
    test_pending_count()
    test_stats()
    test_reset()
    print("\n=== ALL 21 TESTS PASSED ===")


if __name__ == "__main__":
    main()
