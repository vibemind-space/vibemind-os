"""Test pipeline task dependency resolver."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_task_dependency_resolver import PipelineTaskDependencyResolver


def test_create_graph():
    """Create and remove graph."""
    dr = PipelineTaskDependencyResolver()
    gid = dr.create_graph("build_pipeline", tags=["ci"])
    assert gid.startswith("graph-")

    g = dr.get_graph(gid)
    assert g is not None
    assert g["name"] == "build_pipeline"
    assert g["status"] == "building"
    assert "ci" in g["tags"]

    assert dr.remove_graph(gid) is True
    assert dr.remove_graph(gid) is False
    print("OK: create graph")


def test_invalid_graph():
    """Invalid graph rejected."""
    dr = PipelineTaskDependencyResolver()
    assert dr.create_graph("") == ""
    print("OK: invalid graph")


def test_max_graphs():
    """Max graphs enforced."""
    dr = PipelineTaskDependencyResolver(max_graphs=2)
    dr.create_graph("a")
    dr.create_graph("b")
    assert dr.create_graph("c") == ""
    print("OK: max graphs")


def test_add_task():
    """Add and remove tasks."""
    dr = PipelineTaskDependencyResolver()
    gid = dr.create_graph("test")
    tid = dr.add_task(gid, "compile", priority=5, tags=["build"])
    assert tid.startswith("task-")

    t = dr.get_task(gid, tid)
    assert t is not None
    assert t["name"] == "compile"
    assert t["priority"] == 5
    assert t["status"] == "pending"
    assert "build" in t["tags"]

    assert dr.remove_task(gid, tid) is True
    assert dr.remove_task(gid, tid) is False
    print("OK: add task")


def test_invalid_task():
    """Invalid task rejected."""
    dr = PipelineTaskDependencyResolver()
    gid = dr.create_graph("test")
    assert dr.add_task(gid, "") == ""
    assert dr.add_task("nonexistent", "x") == ""
    print("OK: invalid task")


def test_max_tasks():
    """Max tasks per graph enforced."""
    dr = PipelineTaskDependencyResolver(max_tasks_per_graph=2)
    gid = dr.create_graph("test")
    dr.add_task(gid, "a")
    dr.add_task(gid, "b")
    assert dr.add_task(gid, "c") == ""
    print("OK: max tasks")


def test_resolve_order():
    """Resolve topological order."""
    dr = PipelineTaskDependencyResolver()
    gid = dr.create_graph("pipeline")
    t1 = dr.add_task(gid, "fetch")
    t2 = dr.add_task(gid, "parse", dependencies=[t1])
    t3 = dr.add_task(gid, "transform", dependencies=[t2])

    order = dr.resolve_order(gid)
    assert len(order) == 3
    assert order.index(t1) < order.index(t2)
    assert order.index(t2) < order.index(t3)
    print("OK: resolve order")


def test_resolve_with_priority():
    """Priority affects ordering of independent tasks."""
    dr = PipelineTaskDependencyResolver()
    gid = dr.create_graph("test")
    t1 = dr.add_task(gid, "low", priority=1)
    t2 = dr.add_task(gid, "high", priority=10)
    t3 = dr.add_task(gid, "mid", priority=5)

    order = dr.resolve_order(gid)
    assert order[0] == t2  # Highest priority first
    print("OK: resolve with priority")


def test_cycle_detection():
    """Detect dependency cycles."""
    dr = PipelineTaskDependencyResolver()
    gid = dr.create_graph("cyclic")
    t1 = dr.add_task(gid, "a")
    t2 = dr.add_task(gid, "b", dependencies=[t1])
    t3 = dr.add_task(gid, "c", dependencies=[t2])
    # Add cycle: a depends on c
    dr._graphs[gid].tasks[t1].dependencies.append(t3)

    assert dr.has_cycle(gid) is True
    assert dr.resolve_order(gid) == []
    print("OK: cycle detection")


def test_no_cycle():
    """No false cycle detection."""
    dr = PipelineTaskDependencyResolver()
    gid = dr.create_graph("acyclic")
    t1 = dr.add_task(gid, "a")
    t2 = dr.add_task(gid, "b", dependencies=[t1])
    t3 = dr.add_task(gid, "c", dependencies=[t1])

    assert dr.has_cycle(gid) is False
    print("OK: no cycle")


def test_validate_graph():
    """Validate graph catches issues."""
    dr = PipelineTaskDependencyResolver()
    gid = dr.create_graph("test")
    t1 = dr.add_task(gid, "a")
    dr.add_task(gid, "b", dependencies=["nonexistent-task"])

    result = dr.validate_graph(gid)
    assert result["valid"] is False
    assert len(result["errors"]) > 0
    print("OK: validate graph")


def test_validate_clean():
    """Clean graph validates."""
    dr = PipelineTaskDependencyResolver()
    gid = dr.create_graph("test")
    t1 = dr.add_task(gid, "a")
    dr.add_task(gid, "b", dependencies=[t1])

    result = dr.validate_graph(gid)
    assert result["valid"] is True
    print("OK: validate clean")


def test_parallel_groups():
    """Get parallel execution groups."""
    dr = PipelineTaskDependencyResolver()
    gid = dr.create_graph("test")
    t1 = dr.add_task(gid, "a")
    t2 = dr.add_task(gid, "b")
    t3 = dr.add_task(gid, "c", dependencies=[t1, t2])
    t4 = dr.add_task(gid, "d", dependencies=[t3])

    groups = dr.get_parallel_groups(gid)
    assert len(groups) == 3
    assert set(groups[0]) == {t1, t2}  # a and b can run in parallel
    assert groups[1] == [t3]
    assert groups[2] == [t4]
    print("OK: parallel groups")


def test_start_graph():
    """Start graph execution."""
    dr = PipelineTaskDependencyResolver()
    gid = dr.create_graph("test")
    t1 = dr.add_task(gid, "a")
    t2 = dr.add_task(gid, "b", dependencies=[t1])

    assert dr.start_graph(gid) is True
    g = dr.get_graph(gid)
    assert g["status"] == "running"

    # t1 should be ready, t2 pending
    assert dr.get_task(gid, t1)["status"] == "ready"
    assert dr.get_task(gid, t2)["status"] == "pending"

    # Can't start again
    assert dr.start_graph(gid) is False
    print("OK: start graph")


def test_task_execution_flow():
    """Full task execution flow."""
    dr = PipelineTaskDependencyResolver()
    gid = dr.create_graph("test")
    t1 = dr.add_task(gid, "build")
    t2 = dr.add_task(gid, "test", dependencies=[t1])

    dr.start_graph(gid)

    # Start and complete t1
    assert dr.start_task(gid, t1) is True
    assert dr.get_task(gid, t1)["status"] == "running"

    assert dr.complete_task(gid, t1, result="built ok") is True
    assert dr.get_task(gid, t1)["status"] == "completed"

    # t2 should now be ready
    assert dr.get_task(gid, t2)["status"] == "ready"

    # Complete t2
    dr.start_task(gid, t2)
    dr.complete_task(gid, t2)

    # Graph should be completed
    assert dr.get_graph(gid)["status"] == "completed"
    print("OK: task execution flow")


def test_fail_task():
    """Failing a task fails the graph."""
    dr = PipelineTaskDependencyResolver()
    gid = dr.create_graph("test")
    t1 = dr.add_task(gid, "risky")
    dr.start_graph(gid)
    dr.start_task(gid, t1)

    assert dr.fail_task(gid, t1, reason="segfault") is True
    assert dr.get_task(gid, t1)["status"] == "failed"
    assert dr.get_graph(gid)["status"] == "failed"
    print("OK: fail task")


def test_skip_task():
    """Skip a task and unblock dependents."""
    dr = PipelineTaskDependencyResolver()
    gid = dr.create_graph("test")
    t1 = dr.add_task(gid, "optional")
    t2 = dr.add_task(gid, "next", dependencies=[t1])
    dr.start_graph(gid)

    assert dr.skip_task(gid, t1) is True
    assert dr.get_task(gid, t1)["status"] == "skipped"
    assert dr.get_task(gid, t2)["status"] == "ready"
    print("OK: skip task")


def test_get_ready_tasks():
    """Get ready tasks sorted by priority."""
    dr = PipelineTaskDependencyResolver()
    gid = dr.create_graph("test")
    t1 = dr.add_task(gid, "low", priority=1)
    t2 = dr.add_task(gid, "high", priority=10)
    dr.start_graph(gid)

    ready = dr.get_ready_tasks(gid)
    assert len(ready) == 2
    assert ready[0]["task_id"] == t2  # Higher priority first
    print("OK: get ready tasks")


def test_graph_progress():
    """Get graph progress."""
    dr = PipelineTaskDependencyResolver()
    gid = dr.create_graph("test")
    t1 = dr.add_task(gid, "a")
    t2 = dr.add_task(gid, "b")
    dr.start_graph(gid)

    dr.start_task(gid, t1)
    dr.complete_task(gid, t1)

    prog = dr.get_graph_progress(gid)
    assert prog["total"] == 2
    assert prog["completed"] == 1
    assert prog["ready"] == 1
    assert prog["percent"] == 50.0
    print("OK: graph progress")


def test_task_dependents():
    """Get task dependents."""
    dr = PipelineTaskDependencyResolver()
    gid = dr.create_graph("test")
    t1 = dr.add_task(gid, "a")
    t2 = dr.add_task(gid, "b", dependencies=[t1])
    t3 = dr.add_task(gid, "c", dependencies=[t1])

    deps = dr.get_task_dependents(gid, t1)
    assert set(deps) == {t2, t3}
    print("OK: task dependents")


def test_critical_path():
    """Get critical path."""
    dr = PipelineTaskDependencyResolver()
    gid = dr.create_graph("test")
    t1 = dr.add_task(gid, "a")
    t2 = dr.add_task(gid, "b", dependencies=[t1])
    t3 = dr.add_task(gid, "c", dependencies=[t2])
    t4 = dr.add_task(gid, "d", dependencies=[t1])  # Shorter path

    path = dr.get_critical_path(gid)
    assert path == [t1, t2, t3]  # Longest chain
    print("OK: critical path")


def test_list_graphs():
    """List graphs with filters."""
    dr = PipelineTaskDependencyResolver()
    g1 = dr.create_graph("a", tags=["ci"])
    g2 = dr.create_graph("b")
    dr.add_task(g1, "x")
    dr.start_graph(g1)

    all_g = dr.list_graphs()
    assert len(all_g) == 2

    by_status = dr.list_graphs(status="running")
    assert len(by_status) == 1

    by_tag = dr.list_graphs(tag="ci")
    assert len(by_tag) == 1
    print("OK: list graphs")


def test_graph_created_callback():
    """Callback fires on graph creation."""
    dr = PipelineTaskDependencyResolver()
    fired = []
    dr.on_change("mon", lambda a, d: fired.append(a))

    dr.create_graph("test")
    assert "graph_created" in fired
    print("OK: graph created callback")


def test_graph_completed_callback():
    """Callback fires on graph completion."""
    dr = PipelineTaskDependencyResolver()
    fired = []
    dr.on_change("mon", lambda a, d: fired.append(a))

    gid = dr.create_graph("test")
    t1 = dr.add_task(gid, "only")
    dr.start_graph(gid)
    dr.start_task(gid, t1)
    dr.complete_task(gid, t1)
    assert "graph_completed" in fired
    print("OK: graph completed callback")


def test_callbacks():
    """Callback registration."""
    dr = PipelineTaskDependencyResolver()
    assert dr.on_change("mon", lambda a, d: None) is True
    assert dr.on_change("mon", lambda a, d: None) is False
    assert dr.remove_callback("mon") is True
    assert dr.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    dr = PipelineTaskDependencyResolver()
    gid = dr.create_graph("test")
    t1 = dr.add_task(gid, "a")
    t2 = dr.add_task(gid, "b")
    dr.start_graph(gid)
    dr.start_task(gid, t1)
    dr.complete_task(gid, t1)
    dr.start_task(gid, t2)
    dr.fail_task(gid, t2)

    stats = dr.get_stats()
    assert stats["total_graphs_created"] == 1
    assert stats["total_tasks_added"] == 2
    assert stats["total_tasks_completed"] == 1
    assert stats["total_tasks_failed"] == 1
    assert stats["current_graphs"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    dr = PipelineTaskDependencyResolver()
    dr.create_graph("test")

    dr.reset()
    assert dr.list_graphs() == []
    stats = dr.get_stats()
    assert stats["current_graphs"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Task Dependency Resolver Tests ===\n")
    test_create_graph()
    test_invalid_graph()
    test_max_graphs()
    test_add_task()
    test_invalid_task()
    test_max_tasks()
    test_resolve_order()
    test_resolve_with_priority()
    test_cycle_detection()
    test_no_cycle()
    test_validate_graph()
    test_validate_clean()
    test_parallel_groups()
    test_start_graph()
    test_task_execution_flow()
    test_fail_task()
    test_skip_task()
    test_get_ready_tasks()
    test_graph_progress()
    test_task_dependents()
    test_critical_path()
    test_list_graphs()
    test_graph_created_callback()
    test_graph_completed_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 27 TESTS PASSED ===")


if __name__ == "__main__":
    main()
