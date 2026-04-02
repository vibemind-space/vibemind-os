"""Test pipeline dependency graph."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_dep_graph import PipelineDependencyGraph


def _build_diamond(g):
    """Helper: build A → B,C → D diamond graph."""
    g.add_node("A", name="Start", duration=2.0)
    g.add_node("B", name="Build", duration=5.0)
    g.add_node("C", name="Test", duration=3.0)
    g.add_node("D", name="Deploy", duration=1.0)
    g.add_edge("B", "A")  # B depends on A
    g.add_edge("C", "A")  # C depends on A
    g.add_edge("D", "B")  # D depends on B
    g.add_edge("D", "C")  # D depends on C


def test_add_node():
    """Add nodes."""
    g = PipelineDependencyGraph()
    assert g.add_node("a", name="Task A", duration=5.0) is True
    assert g.add_node("a") is False  # Duplicate

    node = g.get_node("a")
    assert node is not None
    assert node["name"] == "Task A"
    assert node["duration"] == 5.0
    assert node["status"] == "pending"
    print("OK: add node")


def test_remove_node():
    """Remove node cleans up edges."""
    g = PipelineDependencyGraph()
    g.add_node("a")
    g.add_node("b")
    g.add_edge("b", "a")

    assert g.remove_node("a") is True
    assert g.get_node("a") is None
    assert g.get_dependencies("b") == []
    assert g.remove_node("a") is False
    print("OK: remove node")


def test_list_nodes():
    """List nodes with filters."""
    g = PipelineDependencyGraph()
    g.add_node("a", tags={"build"})
    g.add_node("b", tags={"test"})
    g.add_node("c", tags={"build"})
    g.set_status("a", "completed")

    all_nodes = g.list_nodes()
    assert len(all_nodes) == 3

    completed = g.list_nodes(status="completed")
    assert len(completed) == 1

    build = g.list_nodes(tags={"build"})
    assert len(build) == 2
    print("OK: list nodes")


def test_add_edge():
    """Add edges."""
    g = PipelineDependencyGraph()
    g.add_node("a")
    g.add_node("b")

    assert g.add_edge("b", "a") is True
    assert g.add_edge("b", "a") is False  # Duplicate
    assert g.add_edge("a", "a") is False  # Self-loop
    assert g.add_edge("b", "nonexistent") is False

    assert g.get_dependencies("b") == ["a"]
    assert g.get_dependents("a") == ["b"]
    print("OK: add edge")


def test_remove_edge():
    """Remove edges."""
    g = PipelineDependencyGraph()
    g.add_node("a")
    g.add_node("b")
    g.add_edge("b", "a")

    assert g.remove_edge("b", "a") is True
    assert g.remove_edge("b", "a") is False
    assert g.get_dependencies("b") == []
    print("OK: remove edge")


def test_topological_sort():
    """Topological ordering."""
    g = PipelineDependencyGraph()
    _build_diamond(g)

    order = g.topological_sort()
    assert order is not None
    assert len(order) == 4
    # A must come before B and C
    assert order.index("A") < order.index("B")
    assert order.index("A") < order.index("C")
    # B and C must come before D
    assert order.index("B") < order.index("D")
    assert order.index("C") < order.index("D")
    print("OK: topological sort")


def test_cycle_detection():
    """Detect cycles."""
    g = PipelineDependencyGraph()
    g.add_node("a")
    g.add_node("b")
    g.add_node("c")
    g.add_edge("b", "a")
    g.add_edge("c", "b")
    g.add_edge("a", "c")  # Creates cycle

    assert g.has_cycle() is True
    assert g.topological_sort() is None
    print("OK: cycle detection")


def test_parallel_groups():
    """Group tasks for parallel execution."""
    g = PipelineDependencyGraph()
    _build_diamond(g)

    groups = g.parallel_groups()
    assert groups is not None
    assert len(groups) == 3
    assert groups[0] == ["A"]
    assert sorted(groups[1]) == ["B", "C"]  # Can run in parallel
    assert groups[2] == ["D"]
    print("OK: parallel groups")


def test_parallel_groups_cycle():
    """Parallel groups returns None on cycle."""
    g = PipelineDependencyGraph()
    g.add_node("a")
    g.add_node("b")
    g.add_edge("a", "b")
    g.add_edge("b", "a")

    assert g.parallel_groups() is None
    print("OK: parallel groups cycle")


def test_critical_path():
    """Find critical path."""
    g = PipelineDependencyGraph()
    _build_diamond(g)

    path = g.critical_path()
    assert path is not None
    assert len(path) == 3
    # Critical path should be A → B → D (2+5+1=8) not A → C → D (2+3+1=6)
    assert path[0]["node_id"] == "A"
    assert path[1]["node_id"] == "B"
    assert path[2]["node_id"] == "D"
    assert path[2]["cumulative"] == 8.0
    print("OK: critical path")


def test_all_dependencies():
    """Get transitive dependencies."""
    g = PipelineDependencyGraph()
    _build_diamond(g)

    deps = g.get_all_dependencies("D")
    assert deps == {"A", "B", "C"}

    deps_b = g.get_all_dependencies("B")
    assert deps_b == {"A"}
    print("OK: all dependencies")


def test_all_dependents():
    """Get transitive dependents."""
    g = PipelineDependencyGraph()
    _build_diamond(g)

    dependents = g.get_all_dependents("A")
    assert dependents == {"B", "C", "D"}
    print("OK: all dependents")


def test_impact_analysis():
    """Impact analysis."""
    g = PipelineDependencyGraph()
    _build_diamond(g)

    impact = g.impact_analysis("A")
    assert impact["found"] is True
    assert impact["total_affected"] == 3
    assert sorted(impact["direct_dependents"]) == ["B", "C"]

    impact2 = g.impact_analysis("nonexistent")
    assert impact2["found"] is False
    print("OK: impact analysis")


def test_roots_and_leaves():
    """Get root and leaf nodes."""
    g = PipelineDependencyGraph()
    _build_diamond(g)

    roots = g.get_roots()
    assert roots == ["A"]

    leaves = g.get_leaves()
    assert leaves == ["D"]
    print("OK: roots and leaves")


def test_ready_nodes():
    """Get nodes ready for execution."""
    g = PipelineDependencyGraph()
    _build_diamond(g)

    ready = g.get_ready_nodes()
    assert ready == ["A"]  # Only A has no deps

    g.set_status("A", "completed")
    ready2 = g.get_ready_nodes()
    assert sorted(ready2) == ["B", "C"]  # B and C are now ready

    g.set_status("B", "completed")
    g.set_status("C", "completed")
    ready3 = g.get_ready_nodes()
    assert ready3 == ["D"]
    print("OK: ready nodes")


def test_extract_subgraph():
    """Extract subgraph."""
    g = PipelineDependencyGraph()
    _build_diamond(g)

    sub = g.extract_subgraph({"A", "B"})
    assert sub["nodes"] == ["A", "B"]
    assert ("B", "A") in sub["edges"]
    assert len(sub["edges"]) == 1  # Only B→A, not D→B
    print("OK: extract subgraph")


def test_set_status():
    """Set node status."""
    g = PipelineDependencyGraph()
    g.add_node("a")
    assert g.set_status("a", "running") is True
    assert g.get_node("a")["status"] == "running"
    assert g.set_status("nonexistent", "x") is False
    print("OK: set status")


def test_stats():
    """Stats are accurate."""
    g = PipelineDependencyGraph()
    _build_diamond(g)

    stats = g.get_stats()
    assert stats["total_nodes"] == 4
    assert stats["total_edges"] == 4
    assert stats["has_cycle"] is False
    assert stats["roots"] == 1
    assert stats["leaves"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    g = PipelineDependencyGraph()
    _build_diamond(g)

    g.reset()
    assert g.list_nodes() == []
    stats = g.get_stats()
    assert stats["total_nodes"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Dependency Graph Tests ===\n")
    test_add_node()
    test_remove_node()
    test_list_nodes()
    test_add_edge()
    test_remove_edge()
    test_topological_sort()
    test_cycle_detection()
    test_parallel_groups()
    test_parallel_groups_cycle()
    test_critical_path()
    test_all_dependencies()
    test_all_dependents()
    test_impact_analysis()
    test_roots_and_leaves()
    test_ready_nodes()
    test_extract_subgraph()
    test_set_status()
    test_stats()
    test_reset()
    print("\n=== ALL 19 TESTS PASSED ===")


if __name__ == "__main__":
    main()
