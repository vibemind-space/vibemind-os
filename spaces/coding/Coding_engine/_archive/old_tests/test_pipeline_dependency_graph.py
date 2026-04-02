"""Test pipeline dependency graph -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_dependency_graph import PipelineDependencyGraph


def test_add_pipeline():
    dg = PipelineDependencyGraph()
    eid = dg.add_pipeline("build")
    assert len(eid) > 0
    assert eid.startswith("pdg-")
    # Duplicate returns ""
    assert dg.add_pipeline("build") == ""
    print("OK: add pipeline")


def test_add_dependency():
    dg = PipelineDependencyGraph()
    dg.add_pipeline("build")
    dg.add_pipeline("test")
    assert dg.add_dependency("test", "build") is True
    # Self-dependency
    assert dg.add_dependency("build", "build") is False
    # Nonexistent
    assert dg.add_dependency("test", "nonexistent") is False
    print("OK: add dependency")


def test_remove_dependency():
    dg = PipelineDependencyGraph()
    dg.add_pipeline("build")
    dg.add_pipeline("test")
    dg.add_dependency("test", "build")
    assert dg.remove_dependency("test", "build") is True
    assert dg.remove_dependency("test", "build") is False
    print("OK: remove dependency")


def test_get_dependencies():
    dg = PipelineDependencyGraph()
    dg.add_pipeline("build")
    dg.add_pipeline("test")
    dg.add_pipeline("deploy")
    dg.add_dependency("test", "build")
    dg.add_dependency("deploy", "test")
    deps = dg.get_dependencies("test")
    assert "build" in deps
    assert dg.get_dependencies("nonexistent") == []
    print("OK: get dependencies")


def test_get_dependents():
    dg = PipelineDependencyGraph()
    dg.add_pipeline("build")
    dg.add_pipeline("test")
    dg.add_dependency("test", "build")
    dependents = dg.get_dependents("build")
    assert "test" in dependents
    print("OK: get dependents")


def test_get_execution_order():
    dg = PipelineDependencyGraph()
    dg.add_pipeline("build")
    dg.add_pipeline("test")
    dg.add_pipeline("deploy")
    dg.add_dependency("test", "build")
    dg.add_dependency("deploy", "test")
    order = dg.get_execution_order()
    assert len(order) == 3
    assert order.index("build") < order.index("test")
    assert order.index("test") < order.index("deploy")
    print("OK: get execution order")


def test_has_cycle():
    dg = PipelineDependencyGraph()
    dg.add_pipeline("a")
    dg.add_pipeline("b")
    dg.add_dependency("b", "a")
    assert dg.has_cycle() is False
    print("OK: has cycle (no cycle)")


def test_remove_pipeline():
    dg = PipelineDependencyGraph()
    dg.add_pipeline("build")
    dg.add_pipeline("test")
    dg.add_dependency("test", "build")
    assert dg.remove_pipeline("build") is True
    assert dg.remove_pipeline("build") is False
    assert dg.get_dependencies("test") == []
    print("OK: remove pipeline")


def test_list_pipelines():
    dg = PipelineDependencyGraph()
    dg.add_pipeline("build")
    dg.add_pipeline("test")
    pipes = dg.list_pipelines()
    assert "build" in pipes
    assert "test" in pipes
    print("OK: list pipelines")


def test_get_graph_summary():
    dg = PipelineDependencyGraph()
    dg.add_pipeline("build")
    dg.add_pipeline("test")
    dg.add_dependency("test", "build")
    summary = dg.get_graph_summary()
    assert summary["pipeline_count"] == 2
    assert summary["dependency_count"] == 1
    assert summary["has_cycles"] is False
    print("OK: get graph summary")


def test_callbacks():
    dg = PipelineDependencyGraph()
    fired = []
    dg.on_change("mon", lambda a, d: fired.append(a))
    dg.add_pipeline("build")
    assert len(fired) >= 1
    assert dg.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    dg = PipelineDependencyGraph()
    dg.add_pipeline("build")
    stats = dg.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    dg = PipelineDependencyGraph()
    dg.add_pipeline("build")
    dg.reset()
    assert dg.list_pipelines() == []
    print("OK: reset")


def main():
    print("=== Pipeline Dependency Graph Tests ===\n")
    test_add_pipeline()
    test_add_dependency()
    test_remove_dependency()
    test_get_dependencies()
    test_get_dependents()
    test_get_execution_order()
    test_has_cycle()
    test_remove_pipeline()
    test_list_pipelines()
    test_get_graph_summary()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 13 TESTS PASSED ===")


if __name__ == "__main__":
    main()
