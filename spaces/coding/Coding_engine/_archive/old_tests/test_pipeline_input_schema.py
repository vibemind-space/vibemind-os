"""Test pipeline input schema -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_input_schema import PipelineInputSchema


def test_define_input():
    ps = PipelineInputSchema()
    iid = ps.define_input("build_stage", {
        "name": {"type": "str", "required": True},
        "count": {"type": "int", "required": True, "default": 1},
    }, description="Build stage input", tags=["core"])
    assert len(iid) > 0
    defn = ps.get_input_def("build_stage")
    assert defn is not None
    assert ps.define_input("build_stage", {}) == ""  # dup
    print("OK: define input")


def test_validate_valid():
    ps = PipelineInputSchema()
    ps.define_input("stage1", {
        "name": {"type": "str", "required": True},
        "count": {"type": "int", "required": False, "default": 0},
    })
    result = ps.validate_input("stage1", {"name": "test", "count": 5})
    assert result["valid"] is True
    assert len(result["errors"]) == 0
    print("OK: validate valid")


def test_validate_missing_required():
    ps = PipelineInputSchema()
    ps.define_input("stage1", {
        "name": {"type": "str", "required": True},
    })
    result = ps.validate_input("stage1", {})
    assert result["valid"] is False
    assert len(result["errors"]) >= 1
    print("OK: validate missing required")


def test_validate_with_defaults():
    ps = PipelineInputSchema()
    ps.define_input("stage1", {
        "name": {"type": "str", "required": True},
        "count": {"type": "int", "required": False, "default": 10},
    })
    result = ps.validate_input("stage1", {"name": "test"})
    assert result["valid"] is True
    assert result["coerced"]["count"] == 10
    print("OK: validate with defaults")


def test_coercion():
    ps = PipelineInputSchema()
    ps.define_input("stage1", {
        "count": {"type": "int", "required": True},
    })
    result = ps.validate_input("stage1", {"count": "42"})
    assert result["valid"] is True
    assert result["coerced"]["count"] == 42
    print("OK: coercion")


def test_list_inputs():
    ps = PipelineInputSchema()
    ps.define_input("s1", {}, tags=["core"])
    ps.define_input("s2", {})
    assert len(ps.list_inputs()) == 2
    assert len(ps.list_inputs(tag="core")) == 1
    print("OK: list inputs")


def test_remove_input():
    ps = PipelineInputSchema()
    ps.define_input("temp", {})
    assert ps.remove_input("temp") is True
    assert ps.remove_input("temp") is False
    print("OK: remove input")


def test_callbacks():
    ps = PipelineInputSchema()
    fired = []
    ps.on_change("mon", lambda a, d: fired.append(a))
    ps.define_input("s1", {})
    assert len(fired) >= 1
    assert ps.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    ps = PipelineInputSchema()
    ps.define_input("s1", {})
    stats = ps.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    ps = PipelineInputSchema()
    ps.define_input("s1", {})
    ps.reset()
    assert ps.list_inputs() == []
    print("OK: reset")


def main():
    print("=== Pipeline Input Schema Tests ===\n")
    test_define_input()
    test_validate_valid()
    test_validate_missing_required()
    test_validate_with_defaults()
    test_coercion()
    test_list_inputs()
    test_remove_input()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")


if __name__ == "__main__":
    main()
