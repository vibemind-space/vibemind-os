"""Test pipeline dependency store -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_dependency_store import PipelineDependencyStore


def test_register_stage():
    ds = PipelineDependencyStore()
    sid = ds.register_stage("deploy", "build", tags=["ci"])
    assert len(sid) > 0
    assert ds.register_stage("deploy", "build") == ""  # dup
    print("OK: register stage")


def test_add_dependency():
    ds = PipelineDependencyStore()
    ds.register_stage("deploy", "build")
    ds.register_stage("deploy", "test")
    assert ds.add_dependency("deploy", "test", "build") is True
    deps = ds.get_dependencies("deploy", "test")
    assert "build" in deps
    print("OK: add dependency")


def test_get_dependents():
    ds = PipelineDependencyStore()
    ds.register_stage("deploy", "build")
    ds.register_stage("deploy", "test")
    ds.register_stage("deploy", "release")
    ds.add_dependency("deploy", "test", "build")
    ds.add_dependency("deploy", "release", "build")
    dependents = ds.get_dependents("deploy", "build")
    assert "test" in dependents
    assert "release" in dependents
    print("OK: get dependents")


def test_execution_order():
    ds = PipelineDependencyStore()
    ds.register_stage("deploy", "build")
    ds.register_stage("deploy", "test")
    ds.register_stage("deploy", "release")
    ds.add_dependency("deploy", "test", "build")
    ds.add_dependency("deploy", "release", "test")
    order = ds.get_execution_order("deploy")
    assert order.index("build") < order.index("test")
    assert order.index("test") < order.index("release")
    print("OK: execution order")


def test_has_cycle():
    ds = PipelineDependencyStore()
    ds.register_stage("p", "a")
    ds.register_stage("p", "b")
    ds.add_dependency("p", "b", "a")
    assert ds.has_cycle("p") is False
    # Cycle is rejected at add_dependency time (returns False)
    result = ds.add_dependency("p", "a", "b")
    assert result is False  # cycle rejected
    assert ds.has_cycle("p") is False  # no cycle exists
    print("OK: has cycle")


def test_list_stages():
    ds = PipelineDependencyStore()
    ds.register_stage("deploy", "build")
    ds.register_stage("deploy", "test")
    stages = ds.list_stages("deploy")
    assert len(stages) == 2
    print("OK: list stages")


def test_list_pipelines():
    ds = PipelineDependencyStore()
    ds.register_stage("deploy", "build")
    ds.register_stage("ci", "lint")
    pipelines = ds.list_pipelines()
    assert "deploy" in pipelines
    assert "ci" in pipelines
    print("OK: list pipelines")


def test_remove_stage():
    ds = PipelineDependencyStore()
    ds.register_stage("deploy", "build")
    assert ds.remove_stage("deploy", "build") is True
    assert ds.remove_stage("deploy", "build") is False
    print("OK: remove stage")


def test_callbacks():
    ds = PipelineDependencyStore()
    fired = []
    ds.on_change("mon", lambda a, d: fired.append(a))
    ds.register_stage("deploy", "build")
    assert len(fired) >= 1
    assert ds.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    ds = PipelineDependencyStore()
    ds.register_stage("deploy", "build")
    stats = ds.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    ds = PipelineDependencyStore()
    ds.register_stage("deploy", "build")
    ds.reset()
    assert ds.list_pipelines() == []
    print("OK: reset")


def main():
    print("=== Pipeline Dependency Store Tests ===\n")
    test_register_stage()
    test_add_dependency()
    test_get_dependents()
    test_execution_order()
    test_has_cycle()
    test_list_stages()
    test_list_pipelines()
    test_remove_stage()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
