"""Tests for PipelineStepDependency service."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_step_dependency import PipelineStepDependency


def test_add_dependency():
    svc = PipelineStepDependency()
    dep_id = svc.add_dependency("p1", "build", "compile")
    assert dep_id.startswith("psd-")
    assert len(dep_id) > 4
    assert svc.get_dep_count() == 1


def test_remove_dependency():
    svc = PipelineStepDependency()
    dep_id = svc.add_dependency("p1", "build", "compile")
    assert svc.remove_dependency(dep_id) is True
    assert svc.remove_dependency(dep_id) is False
    assert svc.get_dep_count() == 0


def test_get_dependencies():
    svc = PipelineStepDependency()
    svc.add_dependency("p1", "deploy", "build")
    svc.add_dependency("p1", "deploy", "test")
    svc.add_dependency("p2", "deploy", "lint")
    deps = svc.get_dependencies("p1", "deploy")
    assert sorted(deps) == ["build", "test"]
    assert svc.get_dependencies("p2", "deploy") == ["lint"]
    assert svc.get_dependencies("p1", "build") == []


def test_get_dependents():
    svc = PipelineStepDependency()
    svc.add_dependency("p1", "build", "compile")
    svc.add_dependency("p1", "test", "compile")
    dependents = svc.get_dependents("p1", "compile")
    assert sorted(dependents) == ["build", "test"]
    assert svc.get_dependents("p1", "build") == []


def test_is_ready():
    svc = PipelineStepDependency()
    svc.add_dependency("p1", "deploy", "build")
    svc.add_dependency("p1", "deploy", "test")
    assert svc.is_ready("p1", "deploy", set()) is False
    assert svc.is_ready("p1", "deploy", {"build"}) is False
    assert svc.is_ready("p1", "deploy", {"build", "test"}) is True
    # Step with no deps is always ready
    assert svc.is_ready("p1", "build", set()) is True


def test_get_execution_order():
    svc = PipelineStepDependency()
    svc.add_dependency("p1", "build", "compile")
    svc.add_dependency("p1", "test", "build")
    svc.add_dependency("p1", "deploy", "test")
    order = svc.get_execution_order("p1")
    assert order == ["compile", "build", "test", "deploy"]
    # Unknown pipeline returns empty
    assert svc.get_execution_order("unknown") == []


def test_cycle_detection():
    svc = PipelineStepDependency()
    svc.add_dependency("p1", "a", "b")
    svc.add_dependency("p1", "b", "c")
    svc.add_dependency("p1", "c", "a")
    order = svc.get_execution_order("p1")
    assert order == []


def test_get_dep_count():
    svc = PipelineStepDependency()
    assert svc.get_dep_count() == 0
    svc.add_dependency("p1", "build", "compile")
    svc.add_dependency("p2", "test", "lint")
    assert svc.get_dep_count() == 2
    assert svc.get_dep_count("p1") == 1
    assert svc.get_dep_count("p2") == 1
    assert svc.get_dep_count("p3") == 0


def test_list_pipelines():
    svc = PipelineStepDependency()
    assert svc.list_pipelines() == []
    svc.add_dependency("p1", "build", "compile")
    svc.add_dependency("p2", "test", "lint")
    svc.add_dependency("p1", "deploy", "build")
    pipelines = svc.list_pipelines()
    assert sorted(pipelines) == ["p1", "p2"]


def test_callbacks():
    events = []

    def tracker(action, detail):
        events.append((action, detail))

    svc = PipelineStepDependency()
    svc.on_change("tracker", tracker)
    dep_id = svc.add_dependency("p1", "build", "compile")
    assert len(events) == 1
    assert events[0][0] == "dependency_added"
    assert events[0][1]["dep_id"] == dep_id

    svc.remove_dependency(dep_id)
    assert len(events) == 2
    assert events[1][0] == "dependency_removed"

    assert svc.remove_callback("tracker") is True
    assert svc.remove_callback("tracker") is False
    svc.add_dependency("p1", "x", "y")
    assert len(events) == 2  # no new events after callback removed


def test_stats():
    svc = PipelineStepDependency()
    svc.on_change("cb1", lambda a, d: None)
    svc.add_dependency("p1", "build", "compile")
    svc.add_dependency("p2", "test", "lint")
    stats = svc.get_stats()
    assert stats["total_dependencies"] == 2
    assert stats["max_entries"] == 10000
    assert stats["pipelines"] == 2
    assert stats["registered_callbacks"] == 1


def test_reset():
    svc = PipelineStepDependency()
    svc.on_change("cb", lambda a, d: None)
    svc.add_dependency("p1", "build", "compile")
    svc.add_dependency("p2", "test", "lint")
    svc.reset()
    assert svc.get_dep_count() == 0
    assert svc.list_pipelines() == []
    assert svc.get_stats()["registered_callbacks"] == 0


if __name__ == "__main__":
    test_add_dependency()
    test_remove_dependency()
    test_get_dependencies()
    test_get_dependents()
    test_is_ready()
    test_get_execution_order()
    test_cycle_detection()
    test_get_dep_count()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("=== ALL 12 TESTS PASSED ===")
