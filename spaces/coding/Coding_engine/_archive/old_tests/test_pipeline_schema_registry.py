"""Test pipeline schema registry -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_schema_registry import PipelineSchemaRegistry


def test_register_schema():
    sr = PipelineSchemaRegistry()
    sid = sr.register_schema("user", {
        "name": {"type": "str", "required": True},
        "age": {"type": "int", "required": True},
        "email": {"type": "str", "required": False},
    }, version="1.0", tags=["core"])
    assert len(sid) > 0
    s = sr.get_schema(sid)
    assert s is not None
    assert s["name"] == "user"
    assert sr.register_schema("user", {}) == ""  # dup
    print("OK: register schema")


def test_validate_valid():
    sr = PipelineSchemaRegistry()
    sr.register_schema("user", {
        "name": {"type": "str", "required": True},
        "age": {"type": "int", "required": True},
    })
    result = sr.validate("user", {"name": "Alice", "age": 30})
    assert result["valid"] is True
    assert len(result["errors"]) == 0
    print("OK: validate valid")


def test_validate_missing_required():
    sr = PipelineSchemaRegistry()
    sr.register_schema("user", {
        "name": {"type": "str", "required": True},
        "age": {"type": "int", "required": True},
    })
    result = sr.validate("user", {"name": "Alice"})
    assert result["valid"] is False
    assert len(result["errors"]) >= 1
    print("OK: validate missing required")


def test_validate_wrong_type():
    sr = PipelineSchemaRegistry()
    sr.register_schema("user", {
        "name": {"type": "str", "required": True},
        "age": {"type": "int", "required": True},
    })
    result = sr.validate("user", {"name": "Alice", "age": "thirty"})
    assert result["valid"] is False
    assert len(result["errors"]) >= 1
    print("OK: validate wrong type")


def test_update_schema():
    sr = PipelineSchemaRegistry()
    sid = sr.register_schema("user", {"name": {"type": "str", "required": True}})
    assert sr.update_schema(sid, schema_def={
        "name": {"type": "str", "required": True},
        "role": {"type": "str", "required": False},
    }, version="2.0") is True
    print("OK: update schema")


def test_list_schemas():
    sr = PipelineSchemaRegistry()
    sr.register_schema("s1", {}, tags=["core"])
    sr.register_schema("s2", {})
    assert len(sr.list_schemas()) == 2
    assert len(sr.list_schemas(tag="core")) == 1
    print("OK: list schemas")


def test_remove_schema():
    sr = PipelineSchemaRegistry()
    sid = sr.register_schema("temp", {})
    assert sr.remove_schema(sid) is True
    assert sr.remove_schema(sid) is False
    print("OK: remove schema")


def test_callbacks():
    sr = PipelineSchemaRegistry()
    fired = []
    sr.on_change("mon", lambda a, d: fired.append(a))
    sr.register_schema("s1", {})
    assert len(fired) >= 1
    assert sr.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    sr = PipelineSchemaRegistry()
    sr.register_schema("s1", {})
    stats = sr.get_stats()
    assert stats.get("total_schemas_created", stats.get("total_registered", 0)) >= 1
    print("OK: stats")


def test_reset():
    sr = PipelineSchemaRegistry()
    sr.register_schema("s1", {})
    sr.reset()
    assert sr.list_schemas() == []
    print("OK: reset")


def main():
    print("=== Pipeline Schema Registry Tests ===\n")
    test_register_schema()
    test_validate_valid()
    test_validate_missing_required()
    test_validate_wrong_type()
    test_update_schema()
    test_list_schemas()
    test_remove_schema()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")


if __name__ == "__main__":
    main()
