"""Test pipeline output validator -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_output_validator import PipelineOutputValidator


def test_register_stage():
    ov = PipelineOutputValidator()
    sid = ov.register_stage("parse", tags=["core"])
    assert sid.startswith("ovs-")
    s = ov.get_stage("parse")
    assert s["name"] == "parse"
    assert s["rule_count"] == 0
    assert ov.register_stage("parse") == ""  # dup
    print("OK: register stage")


def test_add_rule():
    ov = PipelineOutputValidator()
    ov.register_stage("parse")
    rid = ov.add_rule("parse", "has_name", rule_type="required_field", config={"field": "name"})
    assert rid.startswith("ovr-")
    assert ov.add_rule("parse", "has_name") == ""  # dup
    s = ov.get_stage("parse")
    assert s["rule_count"] == 1
    print("OK: add rule")


def test_remove_rule():
    ov = PipelineOutputValidator()
    ov.register_stage("parse")
    ov.add_rule("parse", "r1")
    assert ov.remove_rule("parse", "r1") is True
    assert ov.remove_rule("parse", "r1") is False
    print("OK: remove rule")


def test_validate_required_field():
    ov = PipelineOutputValidator()
    ov.register_stage("parse")
    ov.add_rule("parse", "has_name", rule_type="required_field", config={"field": "name"})
    ov.add_rule("parse", "has_age", rule_type="required_field", config={"field": "age"})
    result = ov.validate("parse", {"name": "Alice", "age": 30})
    assert result["valid"] is True
    assert len(result["errors"]) == 0
    result2 = ov.validate("parse", {"name": "Alice"})
    assert result2["valid"] is False
    assert len(result2["errors"]) == 1
    print("OK: validate required field")


def test_validate_type_check():
    ov = PipelineOutputValidator()
    ov.register_stage("parse")
    ov.add_rule("parse", "name_str", rule_type="type_check", config={"field": "name", "expected_type": "str"})
    ov.add_rule("parse", "age_int", rule_type="type_check", config={"field": "age", "expected_type": "int"})
    result = ov.validate("parse", {"name": "Alice", "age": 30})
    assert result["valid"] is True
    result2 = ov.validate("parse", {"name": "Alice", "age": "thirty"})
    assert result2["valid"] is False
    print("OK: validate type check")


def test_validate_range_check():
    ov = PipelineOutputValidator()
    ov.register_stage("parse")
    ov.add_rule("parse", "score_range", rule_type="range_check", config={"field": "score", "min": 0, "max": 100})
    result = ov.validate("parse", {"score": 50})
    assert result["valid"] is True
    result2 = ov.validate("parse", {"score": 150})
    assert result2["valid"] is False
    print("OK: validate range check")


def test_validate_regex():
    ov = PipelineOutputValidator()
    ov.register_stage("parse")
    ov.add_rule("parse", "email_format", rule_type="regex", config={"field": "email", "pattern": r"^[\w.]+@[\w.]+$"})
    result = ov.validate("parse", {"email": "test@example.com"})
    assert result["valid"] is True
    result2 = ov.validate("parse", {"email": "not-an-email"})
    assert result2["valid"] is False
    print("OK: validate regex")


def test_validate_batch():
    ov = PipelineOutputValidator()
    ov.register_stage("parse")
    ov.add_rule("parse", "has_id", rule_type="required_field", config={"field": "id"})
    outputs = [
        {"id": 1, "name": "A"},
        {"name": "B"},  # missing id
        {"id": 3, "name": "C"},
    ]
    result = ov.validate_batch("parse", outputs)
    assert result["total"] == 3
    assert result["valid_count"] == 2
    assert result["invalid_count"] == 1
    print("OK: validate batch")


def test_validation_summary():
    ov = PipelineOutputValidator()
    ov.register_stage("s1")
    ov.register_stage("s2")
    ov.add_rule("s1", "r1", rule_type="required_field", config={"field": "x"})
    ov.add_rule("s2", "r2", rule_type="required_field", config={"field": "y"})
    ov.validate("s1", {"x": 1})  # pass
    ov.validate("s1", {})  # fail
    ov.validate("s2", {"y": 2})  # pass
    summary = ov.get_validation_summary()
    assert summary["total_validations"] == 3
    assert summary["total_passes"] == 2
    assert summary["total_failures"] == 1
    print("OK: validation summary")


def test_list_stages():
    ov = PipelineOutputValidator()
    ov.register_stage("s1", tags=["core"])
    ov.register_stage("s2")
    assert len(ov.list_stages()) == 2
    assert len(ov.list_stages(tag="core")) == 1
    print("OK: list stages")


def test_list_rules():
    ov = PipelineOutputValidator()
    ov.register_stage("parse")
    ov.add_rule("parse", "r1")
    ov.add_rule("parse", "r2")
    assert len(ov.list_rules("parse")) == 2
    print("OK: list rules")


def test_remove_stage():
    ov = PipelineOutputValidator()
    ov.register_stage("parse")
    assert ov.remove_stage("parse") is True
    assert ov.remove_stage("parse") is False
    print("OK: remove stage")


def test_history():
    ov = PipelineOutputValidator()
    ov.register_stage("parse")
    ov.add_rule("parse", "r1", rule_type="required_field", config={"field": "x"})
    ov.validate("parse", {"x": 1})
    hist = ov.get_history()
    assert len(hist) >= 1
    print("OK: history")


def test_callbacks():
    ov = PipelineOutputValidator()
    fired = []
    ov.on_change("mon", lambda a, d: fired.append(a))
    ov.register_stage("parse")
    assert "stage_registered" in fired
    assert ov.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    ov = PipelineOutputValidator()
    ov.register_stage("parse")
    stats = ov.get_stats()
    assert stats["total_stages_created"] >= 1
    print("OK: stats")


def test_reset():
    ov = PipelineOutputValidator()
    ov.register_stage("parse")
    ov.reset()
    assert ov.list_stages() == []
    print("OK: reset")


def main():
    print("=== Pipeline Output Validator Tests ===\n")
    test_register_stage()
    test_add_rule()
    test_remove_rule()
    test_validate_required_field()
    test_validate_type_check()
    test_validate_range_check()
    test_validate_regex()
    test_validate_batch()
    test_validation_summary()
    test_list_stages()
    test_list_rules()
    test_remove_stage()
    test_history()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 16 TESTS PASSED ===")


if __name__ == "__main__":
    main()
