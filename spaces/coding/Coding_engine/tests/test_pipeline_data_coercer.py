"""Tests for PipelineDataCoercer service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_data_coercer import PipelineDataCoercer


def test_register_coercion():
    c = PipelineDataCoercer()
    cid = c.register_coercion("to_int", "age", "int")
    assert cid.startswith("pdco-")
    assert c.get_coercion_count() == 1


def test_register_coercion_invalid_type():
    c = PipelineDataCoercer()
    try:
        c.register_coercion("bad", "field", "list")
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


def test_coerce_str_to_int():
    c = PipelineDataCoercer()
    cid = c.register_coercion("to_int", "age", "int")
    result = c.coerce(cid, {"age": "42", "name": "Alice"})
    assert result["age"] == 42
    assert result["name"] == "Alice"


def test_coerce_str_to_float():
    c = PipelineDataCoercer()
    cid = c.register_coercion("to_float", "score", "float")
    result = c.coerce(cid, {"score": "3.14"})
    assert abs(result["score"] - 3.14) < 0.001


def test_coerce_int_to_str():
    c = PipelineDataCoercer()
    cid = c.register_coercion("to_str", "code", "str")
    result = c.coerce(cid, {"code": 123})
    assert result["code"] == "123"


def test_coerce_str_to_bool_true():
    c = PipelineDataCoercer()
    cid = c.register_coercion("to_bool", "active", "bool")
    result = c.coerce(cid, {"active": "true"})
    assert result["active"] is True


def test_coerce_str_to_bool_false():
    c = PipelineDataCoercer()
    cid = c.register_coercion("to_bool", "active", "bool")
    result = c.coerce(cid, {"active": "false"})
    assert result["active"] is False


def test_coerce_with_default_on_failure():
    c = PipelineDataCoercer()
    cid = c.register_coercion("to_int", "age", "int", default_value=-1)
    result = c.coerce(cid, {"age": "not_a_number"})
    assert result["age"] == -1


def test_coerce_missing_field():
    c = PipelineDataCoercer()
    cid = c.register_coercion("to_int", "age", "int")
    record = {"name": "Bob"}
    result = c.coerce(cid, record)
    assert "age" not in result
    assert result["name"] == "Bob"


def test_coerce_missing_coercion_id():
    c = PipelineDataCoercer()
    record = {"age": "42"}
    result = c.coerce("pdco-nonexistent", record)
    assert result == {"age": "42"}


def test_coerce_batch():
    c = PipelineDataCoercer()
    cid = c.register_coercion("to_int", "val", "int")
    records = [{"val": "1"}, {"val": "2"}, {"val": "3"}]
    results = c.coerce_batch(cid, records)
    assert len(results) == 3
    assert results[0]["val"] == 1
    assert results[1]["val"] == 2
    assert results[2]["val"] == 3


def test_coerce_all():
    c = PipelineDataCoercer()
    cid1 = c.register_coercion("to_int", "age", "int")
    cid2 = c.register_coercion("to_float", "score", "float")
    record = {"age": "25", "score": "99.5"}
    result = c.coerce_all(record, [cid1, cid2])
    assert result["age"] == 25
    assert abs(result["score"] - 99.5) < 0.001


def test_get_coercion():
    c = PipelineDataCoercer()
    cid = c.register_coercion("test_rule", "x", "str", default_value="N/A")
    entry = c.get_coercion(cid)
    assert entry["name"] == "test_rule"
    assert entry["field"] == "x"
    assert entry["target_type"] == "str"
    assert entry["default_value"] == "N/A"
    assert entry["usage_count"] == 0
    assert "created_at" in entry


def test_get_coercion_not_found():
    c = PipelineDataCoercer()
    assert c.get_coercion("pdco-nonexistent") == {}


def test_get_coercions():
    c = PipelineDataCoercer()
    c.register_coercion("a", "f1", "int")
    c.register_coercion("b", "f2", "float")
    coercions = c.get_coercions()
    assert len(coercions) == 2


def test_remove_coercion():
    c = PipelineDataCoercer()
    cid = c.register_coercion("removable", "x", "int")
    assert c.remove_coercion(cid) is True
    assert c.get_coercion_count() == 0
    assert c.remove_coercion(cid) is False


def test_get_stats():
    c = PipelineDataCoercer()
    cid1 = c.register_coercion("s1", "a", "int")
    cid2 = c.register_coercion("s2", "b", "float")
    c.coerce(cid1, {"a": "1"})
    c.coerce(cid1, {"a": "2"})
    c.coerce(cid2, {"b": "3.0"})
    stats = c.get_stats()
    assert stats["total_coercions"] == 2
    assert stats["total_operations"] == 3


def test_reset():
    c = PipelineDataCoercer()
    c.register_coercion("r1", "f", "int")
    c.reset()
    assert c.get_coercion_count() == 0
    assert c.get_coercions() == []


def test_on_change_callback():
    events = []
    c = PipelineDataCoercer()
    c.on_change = lambda e, d: events.append(e)
    c.register_coercion("cb", "f", "int")
    assert "register" in events


def test_remove_callback():
    c = PipelineDataCoercer()
    c._callbacks["my_cb"] = lambda e, d: None
    assert c.remove_callback("my_cb") is True
    assert c.remove_callback("my_cb") is False


def test_generate_id_uniqueness():
    c = PipelineDataCoercer()
    ids = set()
    for i in range(100):
        cid = c.register_coercion(f"u{i}", "field", "int")
        ids.add(cid)
    assert len(ids) == 100


def test_usage_count_increments():
    c = PipelineDataCoercer()
    cid = c.register_coercion("counter", "x", "int")
    c.coerce(cid, {"x": "1"})
    c.coerce(cid, {"x": "2"})
    c.coerce(cid, {"x": "3"})
    assert c.get_coercion(cid)["usage_count"] == 3


if __name__ == "__main__":
    tests = [
        test_register_coercion,
        test_register_coercion_invalid_type,
        test_coerce_str_to_int,
        test_coerce_str_to_float,
        test_coerce_int_to_str,
        test_coerce_str_to_bool_true,
        test_coerce_str_to_bool_false,
        test_coerce_with_default_on_failure,
        test_coerce_missing_field,
        test_coerce_missing_coercion_id,
        test_coerce_batch,
        test_coerce_all,
        test_get_coercion,
        test_get_coercion_not_found,
        test_get_coercions,
        test_remove_coercion,
        test_get_stats,
        test_reset,
        test_on_change_callback,
        test_remove_callback,
        test_generate_id_uniqueness,
        test_usage_count_increments,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"FAIL: {t.__name__}: {e}")
    print(f"{passed}/{passed + failed} tests passed")
