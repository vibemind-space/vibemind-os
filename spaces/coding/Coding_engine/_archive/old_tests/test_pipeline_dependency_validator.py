"""Test pipeline dependency validator -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_dependency_validator import PipelineDependencyValidator


def test_add_dependency():
    dv = PipelineDependencyValidator()
    did = dv.add_dependency("pipeline-b", "pipeline-a")
    assert len(did) > 0
    assert did.startswith("pdv-")
    print("OK: add dependency")


def test_get_dependency():
    dv = PipelineDependencyValidator()
    did = dv.add_dependency("pipeline-b", "pipeline-a")
    dep = dv.get_dependency(did)
    assert dep is not None
    assert dep["pipeline_id"] == "pipeline-b"
    assert dep["depends_on"] == "pipeline-a"
    assert dv.get_dependency("nonexistent") is None
    print("OK: get dependency")


def test_get_dependencies():
    dv = PipelineDependencyValidator()
    dv.add_dependency("pipeline-c", "pipeline-a")
    dv.add_dependency("pipeline-c", "pipeline-b")
    deps = dv.get_dependencies("pipeline-c")
    assert "pipeline-a" in deps
    assert "pipeline-b" in deps
    print("OK: get dependencies")


def test_get_dependents():
    dv = PipelineDependencyValidator()
    dv.add_dependency("pipeline-b", "pipeline-a")
    dv.add_dependency("pipeline-c", "pipeline-a")
    dependents = dv.get_dependents("pipeline-a")
    assert "pipeline-b" in dependents
    assert "pipeline-c" in dependents
    print("OK: get dependents")


def test_register_and_validate():
    dv = PipelineDependencyValidator()
    dv.register_pipeline("pipeline-a")
    dv.register_pipeline("pipeline-b")
    dv.add_dependency("pipeline-b", "pipeline-a")
    result = dv.validate("pipeline-b")
    assert result["valid"] is True
    # Add dep on unregistered pipeline
    dv.add_dependency("pipeline-b", "pipeline-x")
    result2 = dv.validate("pipeline-b")
    assert result2["valid"] is False
    assert "pipeline-x" in result2["missing"]
    print("OK: register and validate")


def test_is_registered():
    dv = PipelineDependencyValidator()
    dv.register_pipeline("pipeline-a")
    assert dv.is_registered("pipeline-a") is True
    assert dv.is_registered("pipeline-z") is False
    print("OK: is registered")


def test_remove_dependency():
    dv = PipelineDependencyValidator()
    did = dv.add_dependency("pipeline-b", "pipeline-a")
    assert dv.remove_dependency(did) is True
    assert dv.remove_dependency(did) is False
    print("OK: remove dependency")


def test_has_cycle():
    dv = PipelineDependencyValidator()
    dv.add_dependency("b", "a")
    dv.add_dependency("c", "b")
    assert dv.has_cycle() is False
    # Create cycle: a -> c -> b -> a
    dv.add_dependency("a", "c")
    assert dv.has_cycle() is True
    print("OK: has cycle")


def test_list_pipelines():
    dv = PipelineDependencyValidator()
    dv.register_pipeline("pipeline-a")
    dv.register_pipeline("pipeline-b")
    pipelines = dv.list_pipelines()
    assert "pipeline-a" in pipelines
    assert "pipeline-b" in pipelines
    print("OK: list pipelines")


def test_callbacks():
    dv = PipelineDependencyValidator()
    fired = []
    dv.on_change("mon", lambda a, d: fired.append(a))
    dv.add_dependency("pipeline-b", "pipeline-a")
    assert len(fired) >= 1
    assert dv.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    dv = PipelineDependencyValidator()
    dv.add_dependency("pipeline-b", "pipeline-a")
    stats = dv.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    dv = PipelineDependencyValidator()
    dv.add_dependency("pipeline-b", "pipeline-a")
    dv.reset()
    assert dv.get_dependency_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Dependency Validator Tests ===\n")
    test_add_dependency()
    test_get_dependency()
    test_get_dependencies()
    test_get_dependents()
    test_register_and_validate()
    test_is_registered()
    test_remove_dependency()
    test_has_cycle()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 12 TESTS PASSED ===")


if __name__ == "__main__":
    main()
