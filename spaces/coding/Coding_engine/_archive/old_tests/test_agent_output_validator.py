"""Test agent output validator."""
import sys
sys.path.insert(0, ".")

from src.services.agent_output_validator import AgentOutputValidator


def test_add_rule():
    """Add and retrieve rule."""
    v = AgentOutputValidator()
    rid = v.add_rule("check_json", "json_output", required_fields=["status", "data"], tags=["core"])
    assert rid.startswith("vrl-")

    r = v.get_rule(rid)
    assert r is not None
    assert r["name"] == "check_json"
    assert r["output_type"] == "json_output"
    assert r["required_fields"] == ["status", "data"]
    assert r["total_checked"] == 0

    assert v.remove_rule(rid) is True
    assert v.remove_rule(rid) is False
    print("OK: add rule")


def test_invalid_add():
    """Invalid add rejected."""
    v = AgentOutputValidator()
    assert v.add_rule("", "type") == ""
    assert v.add_rule("name", "") == ""
    print("OK: invalid add")


def test_duplicate():
    """Duplicate name rejected."""
    v = AgentOutputValidator()
    v.add_rule("r1", "type")
    assert v.add_rule("r1", "type") == ""
    print("OK: duplicate")


def test_max_rules():
    """Max rules enforced."""
    v = AgentOutputValidator(max_rules=2)
    v.add_rule("a", "type")
    v.add_rule("b", "type")
    assert v.add_rule("c", "type") == ""
    print("OK: max rules")


def test_get_rule_by_name():
    """Get rule by name."""
    v = AgentOutputValidator()
    v.add_rule("check_json", "json_output")

    r = v.get_rule_by_name("check_json")
    assert r is not None
    assert r["name"] == "check_json"
    assert v.get_rule_by_name("nonexistent") is None
    print("OK: get rule by name")


def test_validate_required_fields():
    """Validate required fields."""
    v = AgentOutputValidator()
    v.add_rule("check_json", "json_output", required_fields=["status", "data"])

    result = v.validate("worker1", "json_output", {"status": "ok", "data": [1, 2]})
    assert result["passed"] is True
    assert result["rules_checked"] == 1
    assert result["rules_passed"] == 1
    assert result["errors"] == []

    result = v.validate("worker1", "json_output", {"status": "ok"})
    assert result["passed"] is False
    assert "missing field: data" in result["errors"]
    print("OK: validate required fields")


def test_validate_custom_fn_bool():
    """Validate with bool-returning validator."""
    v = AgentOutputValidator()
    v.add_rule("positive", "number", validator_fn=lambda x: x > 0)

    result = v.validate("w1", "number", 5)
    assert result["passed"] is True

    result = v.validate("w1", "number", -1)
    assert result["passed"] is False
    print("OK: validate custom fn bool")


def test_validate_custom_fn_str():
    """Validate with string-returning validator."""
    v = AgentOutputValidator()
    v.add_rule("length_check", "text", validator_fn=lambda x: "" if len(x) < 100 else "too long")

    result = v.validate("w1", "text", "short")
    assert result["passed"] is True

    result = v.validate("w1", "text", "x" * 200)
    assert result["passed"] is False
    assert "too long" in result["errors"]
    print("OK: validate custom fn str")


def test_validate_custom_fn_list():
    """Validate with list-returning validator."""
    def multi_check(output):
        errors = []
        if not output.get("name"):
            errors.append("missing name")
        if not output.get("age"):
            errors.append("missing age")
        return errors

    v = AgentOutputValidator()
    v.add_rule("person_check", "person", validator_fn=multi_check)

    result = v.validate("w1", "person", {"name": "Alice", "age": 30})
    assert result["passed"] is True

    result = v.validate("w1", "person", {})
    assert result["passed"] is False
    assert len(result["errors"]) == 2
    print("OK: validate custom fn list")


def test_validate_fn_exception():
    """Validate handles validator exception."""
    def bad_fn(x):
        raise ValueError("boom")

    v = AgentOutputValidator()
    v.add_rule("bad", "type", validator_fn=bad_fn)

    result = v.validate("w1", "type", "data")
    assert result["passed"] is False
    assert any("validator error" in e for e in result["errors"])
    print("OK: validate fn exception")


def test_validate_no_matching_rules():
    """Validate with no matching rules passes."""
    v = AgentOutputValidator()
    v.add_rule("r1", "type_a")

    result = v.validate("w1", "type_b", "data")
    assert result["passed"] is True
    assert result["rules_checked"] == 0
    print("OK: validate no matching rules")


def test_validate_multiple_rules():
    """Multiple rules for same output type."""
    v = AgentOutputValidator()
    v.add_rule("has_status", "json", required_fields=["status"])
    v.add_rule("has_data", "json", required_fields=["data"])

    result = v.validate("w1", "json", {"status": "ok", "data": []})
    assert result["passed"] is True
    assert result["rules_checked"] == 2

    result = v.validate("w1", "json", {"status": "ok"})
    assert result["passed"] is False
    assert result["rules_checked"] == 2
    assert result["rules_passed"] == 1
    print("OK: validate multiple rules")


def test_validate_single():
    """Validate against a single rule."""
    v = AgentOutputValidator()
    rid = v.add_rule("check", "type", required_fields=["x"])

    result = v.validate_single(rid, {"x": 1})
    assert result["passed"] is True

    result = v.validate_single(rid, {})
    assert result["passed"] is False

    result = v.validate_single("nonexistent", {})
    assert result["passed"] is False
    assert "rule not found" in result["errors"]
    print("OK: validate single")


def test_rule_stats_updated():
    """Rule stats updated after validation."""
    v = AgentOutputValidator()
    rid = v.add_rule("check", "type", required_fields=["x"])

    v.validate("w1", "type", {"x": 1})
    v.validate("w1", "type", {})

    r = v.get_rule(rid)
    assert r["total_checked"] == 2
    assert r["total_passed"] == 1
    assert r["total_failed"] == 1
    assert abs(r["pass_rate"] - 0.5) < 0.01
    print("OK: rule stats updated")


def test_history():
    """Validation history."""
    v = AgentOutputValidator()
    v.add_rule("check", "type", required_fields=["x"])

    v.validate("w1", "type", {"x": 1})
    v.validate("w2", "type", {})

    hist = v.get_history()
    assert len(hist) == 2

    by_agent = v.get_history(agent="w1")
    assert len(by_agent) == 1

    passed_only = v.get_history(passed=True)
    assert len(passed_only) == 1

    failed_only = v.get_history(passed=False)
    assert len(failed_only) == 1

    limited = v.get_history(limit=1)
    assert len(limited) == 1
    print("OK: history")


def test_list_rules():
    """List rules with filters."""
    v = AgentOutputValidator()
    v.add_rule("r1", "type_a", tags=["core"])
    v.add_rule("r2", "type_b")

    all_r = v.list_rules()
    assert len(all_r) == 2

    by_type = v.list_rules(output_type="type_a")
    assert len(by_type) == 1

    by_tag = v.list_rules(tag="core")
    assert len(by_tag) == 1
    print("OK: list rules")


def test_callback():
    """Callback fires on events."""
    v = AgentOutputValidator()
    fired = []
    v.on_change("mon", lambda a, d: fired.append(a))

    v.add_rule("check", "type", required_fields=["x"])
    assert "rule_added" in fired

    v.validate("w1", "type", {})
    assert "validation_failed" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    v = AgentOutputValidator()
    assert v.on_change("mon", lambda a, d: None) is True
    assert v.on_change("mon", lambda a, d: None) is False
    assert v.remove_callback("mon") is True
    assert v.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    v = AgentOutputValidator()
    v.add_rule("check", "type", required_fields=["x"])

    v.validate("w1", "type", {"x": 1})
    v.validate("w1", "type", {})

    stats = v.get_stats()
    assert stats["current_rules"] == 1
    assert stats["total_validations"] == 2
    assert stats["total_passes"] == 1
    assert stats["total_failures"] == 1
    assert stats["history_size"] == 2
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    v = AgentOutputValidator()
    v.add_rule("check", "type")
    v.validate("w1", "type", "data")

    v.reset()
    assert v.list_rules() == []
    stats = v.get_stats()
    assert stats["current_rules"] == 0
    assert stats["history_size"] == 0
    print("OK: reset")


def main():
    print("=== Agent Output Validator Tests ===\n")
    test_add_rule()
    test_invalid_add()
    test_duplicate()
    test_max_rules()
    test_get_rule_by_name()
    test_validate_required_fields()
    test_validate_custom_fn_bool()
    test_validate_custom_fn_str()
    test_validate_custom_fn_list()
    test_validate_fn_exception()
    test_validate_no_matching_rules()
    test_validate_multiple_rules()
    test_validate_single()
    test_rule_stats_updated()
    test_history()
    test_list_rules()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 20 TESTS PASSED ===")


if __name__ == "__main__":
    main()
