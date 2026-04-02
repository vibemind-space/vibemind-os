"""Test pipeline input validator -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_input_validator import PipelineInputValidator


def test_add_rule():
    iv = PipelineInputValidator()
    rid = iv.add_rule("pipeline-1", "name", rule_type="required")
    assert len(rid) > 0
    assert rid.startswith("piv-")
    print("OK: add rule")


def test_validate_required():
    iv = PipelineInputValidator()
    iv.add_rule("pipeline-1", "name", rule_type="required")
    result = iv.validate("pipeline-1", {"name": "test"})
    assert result["valid"] is True
    result2 = iv.validate("pipeline-1", {})
    assert result2["valid"] is False
    assert len(result2["errors"]) > 0
    print("OK: validate required")


def test_validate_min():
    iv = PipelineInputValidator()
    iv.add_rule("pipeline-1", "count", rule_type="min", value=5)
    result = iv.validate("pipeline-1", {"count": 10})
    assert result["valid"] is True
    result2 = iv.validate("pipeline-1", {"count": 3})
    assert result2["valid"] is False
    print("OK: validate min")


def test_validate_max():
    iv = PipelineInputValidator()
    iv.add_rule("pipeline-1", "count", rule_type="max", value=100)
    result = iv.validate("pipeline-1", {"count": 50})
    assert result["valid"] is True
    result2 = iv.validate("pipeline-1", {"count": 150})
    assert result2["valid"] is False
    print("OK: validate max")


def test_get_rules():
    iv = PipelineInputValidator()
    iv.add_rule("pipeline-1", "name", rule_type="required")
    iv.add_rule("pipeline-1", "count", rule_type="min", value=1)
    rules = iv.get_rules("pipeline-1")
    assert len(rules) == 2
    print("OK: get rules")


def test_remove_rule():
    iv = PipelineInputValidator()
    rid = iv.add_rule("pipeline-1", "name", rule_type="required")
    assert iv.remove_rule(rid) is True
    assert iv.remove_rule("nonexistent") is False
    print("OK: remove rule")


def test_list_pipelines():
    iv = PipelineInputValidator()
    iv.add_rule("pipeline-1", "name", rule_type="required")
    iv.add_rule("pipeline-2", "count", rule_type="min", value=0)
    pipelines = iv.list_pipelines()
    assert "pipeline-1" in pipelines
    assert "pipeline-2" in pipelines
    print("OK: list pipelines")


def test_callbacks():
    iv = PipelineInputValidator()
    fired = []
    iv.on_change("mon", lambda a, d: fired.append(a))
    iv.add_rule("pipeline-1", "name")
    assert len(fired) >= 1
    assert iv.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    iv = PipelineInputValidator()
    iv.add_rule("pipeline-1", "name")
    stats = iv.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    iv = PipelineInputValidator()
    iv.add_rule("pipeline-1", "name")
    iv.reset()
    assert iv.get_rule_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Input Validator Tests ===\n")
    test_add_rule()
    test_validate_required()
    test_validate_min()
    test_validate_max()
    test_get_rules()
    test_remove_rule()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")


if __name__ == "__main__":
    main()
