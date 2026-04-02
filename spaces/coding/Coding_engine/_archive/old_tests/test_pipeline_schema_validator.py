"""Test pipeline schema validator."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_schema_validator import PipelineSchemaValidator


def test_register_schema():
    """Register and retrieve schema."""
    sv = PipelineSchemaValidator()
    eid = sv.register_schema("user", fields={
        "name": {"type": "str", "required": True},
        "age": {"type": "int", "required": False},
    }, tags=["core"])
    assert eid.startswith("sch-")

    s = sv.get_schema(eid)
    assert s is not None
    assert s["name"] == "user"
    assert "name" in s["fields"]

    assert sv.remove_schema(eid) is True
    assert sv.remove_schema(eid) is False
    print("OK: register schema")


def test_invalid_register():
    """Invalid registration rejected."""
    sv = PipelineSchemaValidator()
    assert sv.register_schema("") == ""
    print("OK: invalid register")


def test_duplicate():
    """Duplicate name rejected."""
    sv = PipelineSchemaValidator()
    sv.register_schema("user")
    assert sv.register_schema("user") == ""
    print("OK: duplicate")


def test_max_schemas():
    """Max schemas enforced."""
    sv = PipelineSchemaValidator(max_schemas=2)
    sv.register_schema("a")
    sv.register_schema("b")
    assert sv.register_schema("c") == ""
    print("OK: max schemas")


def test_get_by_name():
    """Get schema by name."""
    sv = PipelineSchemaValidator()
    sv.register_schema("user")
    assert sv.get_by_name("user") is not None
    assert sv.get_by_name("nonexistent") is None
    print("OK: get by name")


def test_add_field():
    """Add field to schema."""
    sv = PipelineSchemaValidator()
    eid = sv.register_schema("user")

    assert sv.add_field(eid, "email", {"type": "str", "required": True}) is True
    assert sv.add_field(eid, "email", {"type": "str"}) is False  # duplicate
    assert sv.add_field("bad", "f", {}) is False
    print("OK: add field")


def test_remove_field():
    """Remove field from schema."""
    sv = PipelineSchemaValidator()
    eid = sv.register_schema("user", fields={
        "name": {"type": "str"}, "age": {"type": "int"},
    })

    assert sv.remove_field(eid, "age") is True
    assert sv.remove_field(eid, "age") is False
    print("OK: remove field")


def test_validate_required():
    """Validate required fields."""
    sv = PipelineSchemaValidator()
    sv.register_schema("user", fields={
        "name": {"type": "str", "required": True},
        "age": {"type": "int", "required": False},
    })

    result = sv.validate("user", {"name": "Alice"})
    assert result["passed"] is True

    result = sv.validate("user", {"age": 30})
    assert result["passed"] is False
    assert any("Missing" in e for e in result["errors"])
    print("OK: validate required")


def test_validate_types():
    """Validate field types."""
    sv = PipelineSchemaValidator()
    sv.register_schema("user", fields={
        "name": {"type": "str", "required": True},
        "age": {"type": "int", "required": True},
    })

    result = sv.validate("user", {"name": "Alice", "age": 30})
    assert result["passed"] is True

    result = sv.validate("user", {"name": "Alice", "age": "thirty"})
    assert result["passed"] is False
    assert any("expected int" in e for e in result["errors"])
    print("OK: validate types")


def test_validate_any_type():
    """Any type accepts anything."""
    sv = PipelineSchemaValidator()
    sv.register_schema("flexible", fields={
        "data": {"type": "any", "required": True},
    })

    assert sv.validate("flexible", {"data": "string"})["passed"] is True
    assert sv.validate("flexible", {"data": 42})["passed"] is True
    assert sv.validate("flexible", {"data": [1, 2]})["passed"] is True
    print("OK: validate any type")


def test_validate_custom_fn_bool():
    """Custom validator returning bool."""
    sv = PipelineSchemaValidator()
    sv.register_schema("user", fields={
        "age": {"type": "int", "required": True,
                "validator": lambda v: v >= 0},
    })

    assert sv.validate("user", {"age": 25})["passed"] is True
    assert sv.validate("user", {"age": -1})["passed"] is False
    print("OK: validate custom fn bool")


def test_validate_custom_fn_str():
    """Custom validator returning error string."""
    sv = PipelineSchemaValidator()
    sv.register_schema("user", fields={
        "name": {"type": "str", "required": True,
                 "validator": lambda v: "" if len(v) > 0 else "Name cannot be empty"},
    })

    assert sv.validate("user", {"name": "Alice"})["passed"] is True
    result = sv.validate("user", {"name": ""})
    assert result["passed"] is False
    assert any("empty" in e for e in result["errors"])
    print("OK: validate custom fn str")


def test_validate_fn_exception():
    """Custom validator exception handled."""
    sv = PipelineSchemaValidator()
    sv.register_schema("bad", fields={
        "x": {"type": "any", "required": True,
              "validator": lambda v: 1/0},
    })

    result = sv.validate("bad", {"x": 1})
    assert result["passed"] is False
    assert any("error" in e.lower() for e in result["errors"])
    print("OK: validate fn exception")


def test_validate_unknown_schema():
    """Validating against unknown schema fails."""
    sv = PipelineSchemaValidator()
    result = sv.validate("nonexistent", {"a": 1})
    assert result["passed"] is False
    print("OK: validate unknown schema")


def test_validate_field():
    """Validate single field."""
    sv = PipelineSchemaValidator()
    sv.register_schema("user", fields={
        "age": {"type": "int", "required": True},
    })

    result = sv.validate_field("user", "age", 25)
    assert result["passed"] is True

    result = sv.validate_field("user", "age", "old")
    assert result["passed"] is False

    result = sv.validate_field("user", "nonexistent", 1)
    assert result["passed"] is False
    print("OK: validate field")


def test_schema_stats_updated():
    """Schema validation stats updated."""
    sv = PipelineSchemaValidator()
    sv.register_schema("user", fields={
        "name": {"type": "str", "required": True},
    })

    sv.validate("user", {"name": "Alice"})
    sv.validate("user", {})

    s = sv.get_by_name("user")
    assert s["total_validations"] == 2
    assert s["total_passed"] == 1
    assert s["total_failed"] == 1
    print("OK: schema stats updated")


def test_list_schemas():
    """List schemas with filters."""
    sv = PipelineSchemaValidator()
    sv.register_schema("a", tags=["core"])
    sv.register_schema("b")

    all_s = sv.list_schemas()
    assert len(all_s) == 2

    by_tag = sv.list_schemas(tag="core")
    assert len(by_tag) == 1
    print("OK: list schemas")


def test_history():
    """Validation history tracking."""
    sv = PipelineSchemaValidator()
    sv.register_schema("user", fields={
        "name": {"type": "str", "required": True},
    })

    sv.validate("user", {"name": "Alice"})
    sv.validate("user", {})

    hist = sv.get_history()
    assert len(hist) == 2

    passed = sv.get_history(passed=True)
    assert len(passed) == 1

    failed = sv.get_history(passed=False)
    assert len(failed) == 1

    by_name = sv.get_history(schema_name="user")
    assert len(by_name) == 2

    limited = sv.get_history(limit=1)
    assert len(limited) == 1
    print("OK: history")


def test_callback():
    """Callback fires on events."""
    sv = PipelineSchemaValidator()
    fired = []
    sv.on_change("mon", lambda a, d: fired.append(a))

    sv.register_schema("user")
    assert "schema_registered" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    sv = PipelineSchemaValidator()
    assert sv.on_change("mon", lambda a, d: None) is True
    assert sv.on_change("mon", lambda a, d: None) is False
    assert sv.remove_callback("mon") is True
    assert sv.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    sv = PipelineSchemaValidator()
    sv.register_schema("user", fields={"name": {"type": "str", "required": True}})
    sv.validate("user", {"name": "Alice"})
    sv.validate("user", {})

    stats = sv.get_stats()
    assert stats["current_schemas"] == 1
    assert stats["total_created"] == 1
    assert stats["total_validations"] == 2
    assert stats["total_passed"] == 1
    assert stats["total_failed"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    sv = PipelineSchemaValidator()
    sv.register_schema("user")

    sv.reset()
    assert sv.list_schemas() == []
    stats = sv.get_stats()
    assert stats["current_schemas"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Schema Validator Tests ===\n")
    test_register_schema()
    test_invalid_register()
    test_duplicate()
    test_max_schemas()
    test_get_by_name()
    test_add_field()
    test_remove_field()
    test_validate_required()
    test_validate_types()
    test_validate_any_type()
    test_validate_custom_fn_bool()
    test_validate_custom_fn_str()
    test_validate_fn_exception()
    test_validate_unknown_schema()
    test_validate_field()
    test_schema_stats_updated()
    test_list_schemas()
    test_history()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 22 TESTS PASSED ===")


if __name__ == "__main__":
    main()
