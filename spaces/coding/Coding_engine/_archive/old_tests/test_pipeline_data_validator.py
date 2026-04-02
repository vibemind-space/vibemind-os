"""Test pipeline data validator."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_data_validator import PipelineDataValidator


def test_create_schema():
    """Create and remove schema."""
    dv = PipelineDataValidator()
    sid = dv.create_schema("user_data", fields={
        "name": {"type": "string", "required": True},
        "age": {"type": "int", "required": True},
    }, tags=["user"])
    assert sid.startswith("schema-")

    s = dv.get_schema(sid)
    assert s is not None
    assert s["name"] == "user_data"
    assert s["status"] == "active"
    assert "user" in s["tags"]

    assert dv.remove_schema(sid) is True
    assert dv.remove_schema(sid) is False
    print("OK: create schema")


def test_invalid_schema():
    """Invalid schema rejected."""
    dv = PipelineDataValidator()
    assert dv.create_schema("") == ""
    print("OK: invalid schema")


def test_max_schemas():
    """Max schemas enforced."""
    dv = PipelineDataValidator(max_schemas=2)
    dv.create_schema("a")
    dv.create_schema("b")
    assert dv.create_schema("c") == ""
    print("OK: max schemas")


def test_disable_enable_schema():
    """Disable and enable schema."""
    dv = PipelineDataValidator()
    sid = dv.create_schema("test")

    assert dv.disable_schema(sid) is True
    assert dv.get_schema(sid)["status"] == "disabled"
    assert dv.disable_schema(sid) is False

    assert dv.enable_schema(sid) is True
    assert dv.get_schema(sid)["status"] == "active"
    assert dv.enable_schema(sid) is False
    print("OK: disable enable schema")


def test_update_fields():
    """Update schema fields."""
    dv = PipelineDataValidator()
    sid = dv.create_schema("test", fields={"a": {"type": "string"}})

    assert dv.update_fields(sid, {"b": {"type": "int"}}) is True
    s = dv.get_schema(sid)
    assert "a" in s["fields"]
    assert "b" in s["fields"]

    assert dv.update_fields("nonexistent", {}) is False
    print("OK: update fields")


def test_add_rule():
    """Add and remove rule."""
    dv = PipelineDataValidator()
    sid = dv.create_schema("test")
    rid = dv.add_rule(sid, "age_min", "age", "min", params={"value": 0})
    assert rid.startswith("vrule-")

    r = dv.get_rule(rid)
    assert r is not None
    assert r["name"] == "age_min"
    assert r["rule_type"] == "min"

    assert dv.remove_rule(rid) is True
    assert dv.remove_rule(rid) is False
    print("OK: add rule")


def test_invalid_rule():
    """Invalid rule rejected."""
    dv = PipelineDataValidator()
    sid = dv.create_schema("test")
    assert dv.add_rule("nonexistent", "r", "f", "min") == ""
    assert dv.add_rule(sid, "", "f", "min") == ""
    assert dv.add_rule(sid, "r", "", "min") == ""
    assert dv.add_rule(sid, "r", "f", "invalid_type") == ""
    print("OK: invalid rule")


def test_enable_disable_rule():
    """Enable and disable rule."""
    dv = PipelineDataValidator()
    sid = dv.create_schema("test")
    rid = dv.add_rule(sid, "r", "f", "not_empty")

    assert dv.disable_rule(rid) is True
    assert dv.get_rule(rid)["enabled"] is False
    assert dv.disable_rule(rid) is False

    assert dv.enable_rule(rid) is True
    assert dv.get_rule(rid)["enabled"] is True
    assert dv.enable_rule(rid) is False
    print("OK: enable disable rule")


def test_check_valid_data():
    """Valid data passes."""
    dv = PipelineDataValidator()
    sid = dv.create_schema("user", fields={
        "name": {"type": "string", "required": True},
        "age": {"type": "int", "required": True},
    })

    result = dv.check_data(sid, {"name": "Alice", "age": 30})
    assert result is not None
    assert result["passed"] is True
    assert len(result["errors"]) == 0
    print("OK: check valid data")


def test_check_missing_required():
    """Missing required field fails."""
    dv = PipelineDataValidator()
    sid = dv.create_schema("user", fields={
        "name": {"type": "string", "required": True},
        "email": {"type": "string", "required": True},
    })

    result = dv.check_data(sid, {"name": "Alice"})
    assert result["passed"] is False
    assert any("email" in e for e in result["errors"])
    print("OK: check missing required")


def test_check_type_mismatch():
    """Type mismatch fails."""
    dv = PipelineDataValidator()
    sid = dv.create_schema("data", fields={
        "count": {"type": "int"},
    })

    result = dv.check_data(sid, {"count": "not_an_int"})
    assert result["passed"] is False
    assert any("type" in e.lower() or "mismatch" in e.lower() for e in result["errors"])
    print("OK: check type mismatch")


def test_check_min_rule():
    """Min rule validation."""
    dv = PipelineDataValidator()
    sid = dv.create_schema("test")
    dv.add_rule(sid, "age_min", "age", "min", params={"value": 18})

    result = dv.check_data(sid, {"age": 10})
    assert result["passed"] is False

    result2 = dv.check_data(sid, {"age": 25})
    assert result2["passed"] is True
    print("OK: check min rule")


def test_check_max_rule():
    """Max rule validation."""
    dv = PipelineDataValidator()
    sid = dv.create_schema("test")
    dv.add_rule(sid, "score_max", "score", "max", params={"value": 100})

    result = dv.check_data(sid, {"score": 150})
    assert result["passed"] is False

    result2 = dv.check_data(sid, {"score": 80})
    assert result2["passed"] is True
    print("OK: check max rule")


def test_check_pattern_rule():
    """Pattern rule validation."""
    dv = PipelineDataValidator()
    sid = dv.create_schema("test")
    dv.add_rule(sid, "email_format", "email", "pattern",
                params={"value": r"^[\w.]+@[\w.]+$"})

    result = dv.check_data(sid, {"email": "bad-email"})
    assert result["passed"] is False

    result2 = dv.check_data(sid, {"email": "user@example.com"})
    assert result2["passed"] is True
    print("OK: check pattern rule")


def test_check_in_list_rule():
    """In-list rule validation."""
    dv = PipelineDataValidator()
    sid = dv.create_schema("test")
    dv.add_rule(sid, "status_check", "status", "in_list",
                params={"values": ["active", "inactive", "pending"]})

    result = dv.check_data(sid, {"status": "deleted"})
    assert result["passed"] is False

    result2 = dv.check_data(sid, {"status": "active"})
    assert result2["passed"] is True
    print("OK: check in list rule")


def test_check_not_empty_rule():
    """Not-empty rule validation."""
    dv = PipelineDataValidator()
    sid = dv.create_schema("test")
    dv.add_rule(sid, "name_required", "name", "not_empty")

    result = dv.check_data(sid, {"name": ""})
    assert result["passed"] is False

    result2 = dv.check_data(sid, {"name": "Alice"})
    assert result2["passed"] is True
    print("OK: check not empty rule")


def test_check_length_rules():
    """Min/max length rules."""
    dv = PipelineDataValidator()
    sid = dv.create_schema("test")
    dv.add_rule(sid, "pw_min", "password", "min_length", params={"value": 8})
    dv.add_rule(sid, "pw_max", "password", "max_length", params={"value": 64})

    result = dv.check_data(sid, {"password": "short"})
    assert result["passed"] is False

    result2 = dv.check_data(sid, {"password": "validpassword123"})
    assert result2["passed"] is True
    print("OK: check length rules")


def test_disabled_schema_skipped():
    """Disabled schema returns None."""
    dv = PipelineDataValidator()
    sid = dv.create_schema("test")
    dv.disable_schema(sid)

    result = dv.check_data(sid, {"x": 1})
    assert result is None
    print("OK: disabled schema skipped")


def test_disabled_rule_skipped():
    """Disabled rules are skipped during validation."""
    dv = PipelineDataValidator()
    sid = dv.create_schema("test")
    rid = dv.add_rule(sid, "age_min", "age", "min", params={"value": 100})
    dv.disable_rule(rid)

    result = dv.check_data(sid, {"age": 5})
    assert result["passed"] is True  # Rule is disabled, so no check
    print("OK: disabled rule skipped")


def test_get_result():
    """Get validation result."""
    dv = PipelineDataValidator()
    sid = dv.create_schema("test")
    result = dv.check_data(sid, {"x": 1}, data_source="api")
    rid = result["result_id"]

    r = dv.get_result(rid)
    assert r is not None
    assert r["data_source"] == "api"
    assert r["passed"] is True
    print("OK: get result")


def test_schema_results():
    """Get results for a schema."""
    dv = PipelineDataValidator()
    sid = dv.create_schema("test", fields={"x": {"type": "int", "required": True}})

    dv.check_data(sid, {"x": 1})
    dv.check_data(sid, {})  # Missing required

    all_r = dv.get_schema_results(sid)
    assert len(all_r) == 2

    failed = dv.get_schema_results(sid, passed=False)
    assert len(failed) == 1
    print("OK: schema results")


def test_pass_rate():
    """Get pass rate."""
    dv = PipelineDataValidator()
    sid = dv.create_schema("test", fields={"x": {"type": "int", "required": True}})

    dv.check_data(sid, {"x": 1})
    dv.check_data(sid, {"x": 2})
    dv.check_data(sid, {})  # Fail

    rate = dv.get_pass_rate(sid)
    assert abs(rate - 0.6667) < 0.01
    print("OK: pass rate")


def test_most_failing_rules():
    """Get most failing rules."""
    dv = PipelineDataValidator()
    sid = dv.create_schema("test")
    dv.add_rule(sid, "age_min", "age", "min", params={"value": 18})

    dv.check_data(sid, {"age": 5})
    dv.check_data(sid, {"age": 10})
    dv.check_data(sid, {"age": 25})

    failing = dv.get_most_failing_rules()
    assert len(failing) == 1
    assert failing[0]["times_failed"] == 2
    print("OK: most failing rules")


def test_list_schemas():
    """List schemas with filters."""
    dv = PipelineDataValidator()
    dv.create_schema("a", tags=["api"])
    s2 = dv.create_schema("b")
    dv.disable_schema(s2)

    all_s = dv.list_schemas()
    assert len(all_s) == 2

    active = dv.list_schemas(status="active")
    assert len(active) == 1

    by_tag = dv.list_schemas(tag="api")
    assert len(by_tag) == 1
    print("OK: list schemas")


def test_schema_rules():
    """Get rules for a schema."""
    dv = PipelineDataValidator()
    sid = dv.create_schema("test")
    dv.add_rule(sid, "r1", "a", "not_empty")
    dv.add_rule(sid, "r2", "b", "min", params={"value": 0})

    rules = dv.get_schema_rules(sid)
    assert len(rules) == 2
    print("OK: schema rules")


def test_validation_failed_callback():
    """Callback fires on validation failure."""
    dv = PipelineDataValidator()
    fired = []
    dv.on_change("mon", lambda a, d: fired.append(a))

    sid = dv.create_schema("test", fields={"x": {"type": "int", "required": True}})
    dv.check_data(sid, {})  # Fail

    assert "validation_failed" in fired
    print("OK: validation failed callback")


def test_callbacks():
    """Callback registration."""
    dv = PipelineDataValidator()
    assert dv.on_change("mon", lambda a, d: None) is True
    assert dv.on_change("mon", lambda a, d: None) is False
    assert dv.remove_callback("mon") is True
    assert dv.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    dv = PipelineDataValidator()
    sid = dv.create_schema("test", fields={"x": {"type": "int", "required": True}})
    dv.add_rule(sid, "r", "x", "min", params={"value": 0})

    dv.check_data(sid, {"x": 5})
    dv.check_data(sid, {})

    stats = dv.get_stats()
    assert stats["total_schemas_created"] == 1
    assert stats["total_validations"] == 2
    assert stats["total_passed"] == 1
    assert stats["total_failed"] == 1
    assert stats["total_rules_created"] == 1
    assert stats["current_schemas"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    dv = PipelineDataValidator()
    dv.create_schema("test")

    dv.reset()
    assert dv.list_schemas() == []
    stats = dv.get_stats()
    assert stats["current_schemas"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Data Validator Tests ===\n")
    test_create_schema()
    test_invalid_schema()
    test_max_schemas()
    test_disable_enable_schema()
    test_update_fields()
    test_add_rule()
    test_invalid_rule()
    test_enable_disable_rule()
    test_check_valid_data()
    test_check_missing_required()
    test_check_type_mismatch()
    test_check_min_rule()
    test_check_max_rule()
    test_check_pattern_rule()
    test_check_in_list_rule()
    test_check_not_empty_rule()
    test_check_length_rules()
    test_disabled_schema_skipped()
    test_disabled_rule_skipped()
    test_get_result()
    test_schema_results()
    test_pass_rate()
    test_most_failing_rules()
    test_list_schemas()
    test_schema_rules()
    test_validation_failed_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 29 TESTS PASSED ===")


if __name__ == "__main__":
    main()
