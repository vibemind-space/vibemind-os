"""Tests for AgentWorkflowValidator."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.agent_workflow_validator import AgentWorkflowValidator


def test_register_rule_returns_id():
    v = AgentWorkflowValidator()
    rid = v.register_rule("name_required", "name")
    assert rid.startswith("awv-")
    assert len(rid) == 4 + 16


def test_register_rule_increments_count():
    v = AgentWorkflowValidator()
    v.register_rule("r1", "f1")
    v.register_rule("r2", "f2")
    assert v.get_rule_count() == 2


def test_get_rule():
    v = AgentWorkflowValidator()
    rid = v.register_rule("check_name", "name", "required")
    rule = v.get_rule(rid)
    assert rule["rule_name"] == "check_name"
    assert rule["field"] == "name"
    assert rule["check_type"] == "required"


def test_get_rule_not_found():
    v = AgentWorkflowValidator()
    assert v.get_rule("awv-nonexistent") == {}


def test_get_rules():
    v = AgentWorkflowValidator()
    v.register_rule("r1", "f1")
    v.register_rule("r2", "f2")
    rules = v.get_rules()
    assert len(rules) == 2


def test_remove_rule():
    v = AgentWorkflowValidator()
    rid = v.register_rule("r1", "f1")
    assert v.remove_rule(rid) is True
    assert v.get_rule_count() == 0


def test_remove_rule_not_found():
    v = AgentWorkflowValidator()
    assert v.remove_rule("awv-nope") is False


def test_validate_required_pass():
    v = AgentWorkflowValidator()
    v.register_rule("name_req", "name", "required")
    result = v.validate({"name": "my_workflow"})
    assert result["valid"] is True
    assert result["errors"] == []
    assert result["rules_checked"] == 1
    assert result["rules_passed"] == 1


def test_validate_required_fail():
    v = AgentWorkflowValidator()
    v.register_rule("name_req", "name", "required")
    result = v.validate({"other": 1})
    assert result["valid"] is False
    assert len(result["errors"]) == 1
    assert "missing" in result["errors"][0]


def test_validate_type_pass():
    v = AgentWorkflowValidator()
    v.register_rule("name_str", "name", "type", "str")
    result = v.validate({"name": "hello"})
    assert result["valid"] is True
    assert result["rules_passed"] == 1


def test_validate_type_fail():
    v = AgentWorkflowValidator()
    v.register_rule("name_str", "name", "type", "str")
    result = v.validate({"name": 123})
    assert result["valid"] is False
    assert "expected type" in result["errors"][0]


def test_validate_type_missing_field():
    v = AgentWorkflowValidator()
    v.register_rule("name_str", "name", "type", "str")
    result = v.validate({})
    assert result["valid"] is False
    assert "missing" in result["errors"][0]


def test_validate_value_pass():
    v = AgentWorkflowValidator()
    v.register_rule("status_active", "status", "value", "active")
    result = v.validate({"status": "active"})
    assert result["valid"] is True


def test_validate_value_fail():
    v = AgentWorkflowValidator()
    v.register_rule("status_active", "status", "value", "active")
    result = v.validate({"status": "inactive"})
    assert result["valid"] is False
    assert "expected" in result["errors"][0]


def test_validate_value_missing_field():
    v = AgentWorkflowValidator()
    v.register_rule("status_active", "status", "value", "active")
    result = v.validate({})
    assert result["valid"] is False


def test_validate_subset_of_rules():
    v = AgentWorkflowValidator()
    r1 = v.register_rule("r1", "name", "required")
    r2 = v.register_rule("r2", "age", "required")
    result = v.validate({"name": "x"}, rule_ids=[r1])
    assert result["valid"] is True
    assert result["rules_checked"] == 1


def test_validation_count():
    v = AgentWorkflowValidator()
    v.register_rule("r1", "f1")
    v.validate({"f1": 1})
    v.validate({"f1": 2})
    v.validate({})
    assert v.get_validation_count() == 3


def test_get_stats():
    v = AgentWorkflowValidator()
    v.register_rule("r1", "f1", "required")
    v.validate({})
    v.validate({"f1": 1})
    stats = v.get_stats()
    assert stats["total_rules"] == 1
    assert stats["total_validations"] == 2
    assert stats["total_errors"] == 1


def test_reset():
    v = AgentWorkflowValidator()
    v.register_rule("r1", "f1")
    v.validate({})
    v.reset()
    assert v.get_rule_count() == 0
    assert v.get_validation_count() == 0
    assert v.get_stats()["total_errors"] == 0


def test_on_change_callback():
    events = []
    v = AgentWorkflowValidator()
    v.on_change = lambda event, data: events.append(event)
    v.register_rule("r1", "f1")
    v.validate({"f1": 1})
    assert "rule_registered" in events
    assert "validation_complete" in events


def test_remove_callback():
    v = AgentWorkflowValidator()
    v._callbacks["my_cb"] = lambda e, d: None
    assert v.remove_callback("my_cb") is True
    assert v.remove_callback("my_cb") is False


def test_callback_exception_handled():
    v = AgentWorkflowValidator()
    v.on_change = lambda e, d: (_ for _ in ()).throw(ValueError("boom"))
    # Should not raise
    v.register_rule("r1", "f1")


def test_unique_ids():
    v = AgentWorkflowValidator()
    ids = set()
    for i in range(50):
        ids.add(v.register_rule(f"rule_{i}", f"field_{i}"))
    assert len(ids) == 50


def test_multiple_rules_mixed_results():
    v = AgentWorkflowValidator()
    v.register_rule("name_req", "name", "required")
    v.register_rule("name_type", "name", "type", "str")
    v.register_rule("version_val", "version", "value", 2)
    result = v.validate({"name": "wf", "version": 2})
    assert result["valid"] is True
    assert result["rules_passed"] == 3

    result2 = v.validate({"name": 123, "version": 1})
    assert result2["valid"] is False
    assert result2["rules_passed"] == 1  # name required passes
    assert len(result2["errors"]) == 2  # name type + version value


if __name__ == "__main__":
    tests = [
        test_register_rule_returns_id,
        test_register_rule_increments_count,
        test_get_rule,
        test_get_rule_not_found,
        test_get_rules,
        test_remove_rule,
        test_remove_rule_not_found,
        test_validate_required_pass,
        test_validate_required_fail,
        test_validate_type_pass,
        test_validate_type_fail,
        test_validate_type_missing_field,
        test_validate_value_pass,
        test_validate_value_fail,
        test_validate_value_missing_field,
        test_validate_subset_of_rules,
        test_validation_count,
        test_get_stats,
        test_reset,
        test_on_change_callback,
        test_remove_callback,
        test_callback_exception_handled,
        test_unique_ids,
        test_multiple_rules_mixed_results,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as exc:
            print(f"FAIL {t.__name__}: {exc}")
    print(f"{passed}/{len(tests)} tests passed")
