"""Test pipeline config validator."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_config_validator import PipelineConfigValidator


def test_create_schema():
    """Create and remove schemas."""
    v = PipelineConfigValidator()
    sid = v.create_schema("app", {
        "name": {"type": "string", "required": True},
        "port": {"type": "int", "required": True, "min": 1, "max": 65535},
    })
    assert sid.startswith("schema-")

    s = v.get_schema(sid)
    assert s is not None
    assert s["name"] == "app"
    assert s["field_count"] == 2

    assert v.remove_schema(sid) is True
    assert v.remove_schema(sid) is False
    print("OK: create schema")


def test_invalid_schema():
    """Invalid schemas rejected."""
    v = PipelineConfigValidator()
    assert v.create_schema("x", {}) == ""  # Empty fields
    assert v.create_schema("x", {"f": {"type": "invalid"}}) == ""
    print("OK: invalid schema")


def test_add_remove_field():
    """Add and remove fields."""
    v = PipelineConfigValidator()
    sid = v.create_schema("app", {"name": {"type": "string"}})

    assert v.add_field(sid, "port", {"type": "int"}) is True
    assert v.add_field(sid, "port", {"type": "int"}) is False  # Duplicate
    assert v.add_field(sid, "bad", {"type": "invalid"}) is False
    assert v.get_schema(sid)["field_count"] == 2

    assert v.remove_field(sid, "port") is True
    assert v.remove_field(sid, "port") is False
    print("OK: add remove field")


def test_validate_pass():
    """Validation passes."""
    v = PipelineConfigValidator()
    sid = v.create_schema("app", {
        "name": {"type": "string", "required": True},
        "port": {"type": "int", "min": 1, "max": 65535},
    })

    result = v.validate(sid, {"name": "myapp", "port": 8080})
    assert result is not None
    assert result["valid"] is True
    assert result["error_count"] == 0
    print("OK: validate pass")


def test_missing_required():
    """Missing required field fails."""
    v = PipelineConfigValidator()
    sid = v.create_schema("app", {
        "name": {"type": "string", "required": True},
    })

    result = v.validate(sid, {})
    assert result["valid"] is False
    assert result["error_count"] == 1
    assert "missing" in result["errors"][0]["message"]
    print("OK: missing required")


def test_type_check():
    """Type checking works."""
    v = PipelineConfigValidator()
    sid = v.create_schema("app", {
        "port": {"type": "int"},
        "name": {"type": "string"},
    })

    result = v.validate(sid, {"port": "not_int", "name": 123})
    assert result["valid"] is False
    assert result["error_count"] == 2
    print("OK: type check")


def test_range_check_numbers():
    """Range checking for numbers."""
    v = PipelineConfigValidator()
    sid = v.create_schema("app", {
        "port": {"type": "int", "min": 1, "max": 100},
    })

    result = v.validate(sid, {"port": 0})
    assert result["valid"] is False

    result = v.validate(sid, {"port": 101})
    assert result["valid"] is False

    result = v.validate(sid, {"port": 50})
    assert result["valid"] is True
    print("OK: range check numbers")


def test_range_check_strings():
    """Range checking for string length."""
    v = PipelineConfigValidator()
    sid = v.create_schema("app", {
        "name": {"type": "string", "min": 3, "max": 10},
    })

    result = v.validate(sid, {"name": "ab"})
    assert result["valid"] is False

    result = v.validate(sid, {"name": "a" * 11})
    assert result["valid"] is False

    result = v.validate(sid, {"name": "hello"})
    assert result["valid"] is True
    print("OK: range check strings")


def test_pattern_check():
    """Regex pattern checking."""
    v = PipelineConfigValidator()
    sid = v.create_schema("app", {
        "email": {"type": "string", "pattern": r"^[\w.]+@[\w.]+$"},
    })

    result = v.validate(sid, {"email": "user@example.com"})
    assert result["valid"] is True

    result = v.validate(sid, {"email": "invalid"})
    assert result["valid"] is False
    print("OK: pattern check")


def test_choices_check():
    """Choices validation."""
    v = PipelineConfigValidator()
    sid = v.create_schema("app", {
        "env": {"type": "string", "choices": ["dev", "staging", "prod"]},
    })

    result = v.validate(sid, {"env": "dev"})
    assert result["valid"] is True

    result = v.validate(sid, {"env": "test"})
    assert result["valid"] is False
    print("OK: choices check")


def test_unknown_fields_warning():
    """Unknown fields produce warnings."""
    v = PipelineConfigValidator()
    sid = v.create_schema("app", {"name": {"type": "string"}})

    result = v.validate(sid, {"name": "x", "extra": 123})
    assert result["valid"] is True  # Still valid
    assert result["warning_count"] == 1
    print("OK: unknown fields warning")


def test_validate_batch():
    """Validate multiple configs."""
    v = PipelineConfigValidator()
    sid = v.create_schema("app", {
        "name": {"type": "string", "required": True},
    })

    results = v.validate_batch(sid, [
        {"name": "app1"},
        {},  # Missing required
        {"name": "app3"},
    ])
    assert len(results) == 3
    assert results[0]["valid"] is True
    assert results[1]["valid"] is False
    assert results[2]["valid"] is True
    print("OK: validate batch")


def test_get_defaults():
    """Get default values."""
    v = PipelineConfigValidator()
    sid = v.create_schema("app", {
        "name": {"type": "string", "required": True},
        "port": {"type": "int", "default": 8080},
        "debug": {"type": "bool", "default": False},
    })

    defaults = v.get_defaults(sid)
    assert defaults["port"] == 8080
    assert defaults["debug"] is False
    assert "name" not in defaults
    print("OK: get defaults")


def test_apply_defaults():
    """Apply defaults to config."""
    v = PipelineConfigValidator()
    sid = v.create_schema("app", {
        "name": {"type": "string"},
        "port": {"type": "int", "default": 8080},
    })

    config = v.apply_defaults(sid, {"name": "myapp"})
    assert config["name"] == "myapp"
    assert config["port"] == 8080

    # Existing values not overwritten
    config2 = v.apply_defaults(sid, {"name": "x", "port": 3000})
    assert config2["port"] == 3000
    print("OK: apply defaults")


def test_list_results():
    """List validation results."""
    v = PipelineConfigValidator()
    sid = v.create_schema("app", {
        "name": {"type": "string", "required": True},
    })

    v.validate(sid, {"name": "ok"}, config_name="good")
    v.validate(sid, {}, config_name="bad")

    all_r = v.list_results()
    assert len(all_r) == 2

    passed = v.list_results(valid=True)
    assert len(passed) == 1

    failed = v.list_results(valid=False)
    assert len(failed) == 1
    print("OK: list results")


def test_float_type():
    """Float type accepts int and float."""
    v = PipelineConfigValidator()
    sid = v.create_schema("x", {"val": {"type": "float"}})

    assert v.validate(sid, {"val": 3.14})["valid"] is True
    assert v.validate(sid, {"val": 42})["valid"] is True
    assert v.validate(sid, {"val": "nope"})["valid"] is False
    print("OK: float type")


def test_list_type():
    """List type with min/max length."""
    v = PipelineConfigValidator()
    sid = v.create_schema("x", {
        "items": {"type": "list", "min": 1, "max": 3},
    })

    assert v.validate(sid, {"items": []})["valid"] is False
    assert v.validate(sid, {"items": [1, 2]})["valid"] is True
    assert v.validate(sid, {"items": [1, 2, 3, 4]})["valid"] is False
    print("OK: list type")


def test_callbacks():
    """Validation callbacks fire."""
    v = PipelineConfigValidator()
    sid = v.create_schema("app", {
        "name": {"type": "string", "required": True},
    })

    fired = []
    assert v.on_validation("mon", lambda a, r, s: fired.append(a)) is True
    assert v.on_validation("mon", lambda a, r, s: None) is False

    v.validate(sid, {})  # Fails - should fire callback
    assert len(fired) == 1
    assert fired[0] == "validation_failed"

    v.validate(sid, {"name": "ok"})  # Passes - no callback
    assert len(fired) == 1

    assert v.remove_callback("mon") is True
    assert v.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    v = PipelineConfigValidator()
    sid = v.create_schema("app", {
        "name": {"type": "string", "required": True},
    })

    v.validate(sid, {"name": "ok"})
    v.validate(sid, {})

    stats = v.get_stats()
    assert stats["total_validations"] == 2
    assert stats["total_passed"] == 1
    assert stats["total_failed"] == 1
    assert stats["total_errors_found"] == 1
    assert stats["total_schemas"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    v = PipelineConfigValidator()
    v.create_schema("app", {"name": {"type": "string"}})

    v.reset()
    assert v.list_schemas() == []
    stats = v.get_stats()
    assert stats["total_schemas"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Config Validator Tests ===\n")
    test_create_schema()
    test_invalid_schema()
    test_add_remove_field()
    test_validate_pass()
    test_missing_required()
    test_type_check()
    test_range_check_numbers()
    test_range_check_strings()
    test_pattern_check()
    test_choices_check()
    test_unknown_fields_warning()
    test_validate_batch()
    test_get_defaults()
    test_apply_defaults()
    test_list_results()
    test_float_type()
    test_list_type()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 20 TESTS PASSED ===")


if __name__ == "__main__":
    main()
