"""Tests for PipelineDataObfuscator service."""

import hashlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_data_obfuscator import PipelineDataObfuscator


def test_obfuscate_mask_strategy():
    o = PipelineDataObfuscator()
    rid = o.obfuscate({"name": "Alice", "ssn": "123-45-6789"}, ["ssn"])
    assert rid.startswith("pdo-")
    rec = o.get_record(rid)
    assert rec["obfuscated_payload"]["ssn"] == "***"
    assert rec["obfuscated_payload"]["name"] == "Alice"


def test_obfuscate_hash_strategy():
    o = PipelineDataObfuscator()
    rid = o.obfuscate({"password": "secret123"}, ["password"], strategy="hash")
    rec = o.get_record(rid)
    expected = hashlib.sha256("secret123".encode()).hexdigest()
    assert rec["obfuscated_payload"]["password"] == expected


def test_obfuscate_redact_strategy():
    o = PipelineDataObfuscator()
    rid = o.obfuscate({"name": "Bob", "ssn": "999"}, ["ssn"], strategy="redact")
    rec = o.get_record(rid)
    assert "ssn" not in rec["obfuscated_payload"]
    assert rec["obfuscated_payload"]["name"] == "Bob"


def test_obfuscate_default_strategy_is_mask():
    o = PipelineDataObfuscator()
    rid = o.obfuscate({"secret": "val"}, ["secret"])
    rec = o.get_record(rid)
    assert rec["strategy"] == "mask"
    assert rec["obfuscated_payload"]["secret"] == "***"


def test_obfuscate_multiple_fields():
    o = PipelineDataObfuscator()
    rid = o.obfuscate({"a": "1", "b": "2", "c": "3"}, ["a", "b"])
    rec = o.get_record(rid)
    assert rec["obfuscated_payload"]["a"] == "***"
    assert rec["obfuscated_payload"]["b"] == "***"
    assert rec["obfuscated_payload"]["c"] == "3"


def test_obfuscate_field_not_in_payload():
    o = PipelineDataObfuscator()
    rid = o.obfuscate({"name": "Alice"}, ["ssn"])
    rec = o.get_record(rid)
    assert rec["fields"] == []
    assert rec["obfuscated_payload"] == {"name": "Alice"}


def test_obfuscate_preserves_original_via_deepcopy():
    o = PipelineDataObfuscator()
    payload = {"name": "Alice", "data": {"nested": "value"}}
    rid = o.obfuscate(payload, ["name"])
    # Original should be unmodified
    assert payload["name"] == "Alice"
    # Deobfuscated copy should be independent
    original = o.deobfuscate(rid)
    original["data"]["nested"] = "changed"
    assert payload["data"]["nested"] == "value"


def test_get_record_returns_none_for_missing():
    o = PipelineDataObfuscator()
    assert o.get_record("pdo-nonexistent") is None


def test_get_record_returns_dict():
    o = PipelineDataObfuscator()
    rid = o.obfuscate({"x": "1"}, ["x"])
    rec = o.get_record(rid)
    assert isinstance(rec, dict)
    assert "id" in rec
    assert "obfuscated_payload" in rec
    assert "fields" in rec
    assert "strategy" in rec
    assert "created_at" in rec


def test_get_records_returns_newest_first():
    o = PipelineDataObfuscator()
    # Manually set created_at to ensure distinct timestamps
    rid1 = o.obfuscate({"a": "1"}, ["a"])
    o._state.entries[rid1]["created_at"] = 1000.0
    rid2 = o.obfuscate({"b": "2"}, ["b"])
    o._state.entries[rid2]["created_at"] = 2000.0
    rid3 = o.obfuscate({"c": "3"}, ["c"])
    o._state.entries[rid3]["created_at"] = 3000.0
    records = o.get_records()
    assert len(records) == 3
    assert records[0]["id"] == rid3
    assert records[2]["id"] == rid1


def test_get_records_filter_by_pipeline_id():
    o = PipelineDataObfuscator()
    o.obfuscate({"pipeline_id": "p1", "x": "1"}, ["x"])
    o.obfuscate({"pipeline_id": "p2", "y": "2"}, ["y"])
    o.obfuscate({"pipeline_id": "p1", "z": "3"}, ["z"])
    records = o.get_records(pipeline_id="p1")
    assert len(records) == 2
    for r in records:
        assert r["pipeline_id"] == "p1"


def test_get_records_with_limit():
    o = PipelineDataObfuscator()
    for i in range(10):
        o.obfuscate({"v": str(i)}, ["v"])
    records = o.get_records(limit=3)
    assert len(records) == 3


def test_get_records_empty():
    o = PipelineDataObfuscator()
    assert o.get_records() == []


def test_deobfuscate_returns_original():
    o = PipelineDataObfuscator()
    rid = o.obfuscate({"name": "Alice", "ssn": "123"}, ["ssn"], strategy="mask")
    original = o.deobfuscate(rid)
    assert original == {"name": "Alice", "ssn": "123"}


def test_deobfuscate_returns_none_for_missing():
    o = PipelineDataObfuscator()
    assert o.deobfuscate("pdo-fake") is None


def test_deobfuscate_returns_deepcopy():
    o = PipelineDataObfuscator()
    rid = o.obfuscate({"data": [1, 2, 3]}, ["data"])
    result1 = o.deobfuscate(rid)
    result2 = o.deobfuscate(rid)
    result1["data"].append(99)
    assert result2["data"] == [1, 2, 3]


def test_get_stats():
    o = PipelineDataObfuscator()
    o.obfuscate({"a": "1", "b": "2"}, ["a", "b"], strategy="mask")
    o.obfuscate({"c": "3"}, ["c"], strategy="hash")
    stats = o.get_stats()
    assert stats["total_records"] == 2
    assert stats["strategies_used"]["mask"] == 1
    assert stats["strategies_used"]["hash"] == 1
    assert stats["fields_obfuscated"]["a"] == 1
    assert stats["fields_obfuscated"]["b"] == 1
    assert stats["fields_obfuscated"]["c"] == 1


def test_get_stats_empty():
    o = PipelineDataObfuscator()
    stats = o.get_stats()
    assert stats["total_records"] == 0
    assert stats["strategies_used"] == {}
    assert stats["fields_obfuscated"] == {}


def test_reset_clears_all():
    o = PipelineDataObfuscator()
    o.obfuscate({"x": "1"}, ["x"])
    o._callbacks["cb1"] = lambda e, d: None
    o.on_change = lambda e, d: None
    o.reset()
    assert o.get_stats()["total_records"] == 0
    assert o.get_records() == []
    assert o.on_change is None


def test_on_change_callback_fires():
    events = []
    o = PipelineDataObfuscator()
    o.on_change = lambda action, data: events.append((action, data))
    o.obfuscate({"x": "1"}, ["x"])
    assert len(events) == 1
    assert events[0][0] == "obfuscated"


def test_on_change_getter_setter():
    o = PipelineDataObfuscator()
    assert o.on_change is None
    cb = lambda e, d: None
    o.on_change = cb
    assert o.on_change is cb


def test_named_callbacks_fire():
    events = []
    o = PipelineDataObfuscator()
    o._callbacks["tracker"] = lambda action, data: events.append(action)
    o.obfuscate({"x": "1"}, ["x"])
    assert "obfuscated" in events


def test_callback_exception_silenced():
    o = PipelineDataObfuscator()
    o.on_change = lambda e, d: (_ for _ in ()).throw(ValueError("boom"))
    o._callbacks["bad"] = lambda e, d: (_ for _ in ()).throw(RuntimeError("oops"))
    # Should not raise
    rid = o.obfuscate({"x": "1"}, ["x"])
    assert rid.startswith("pdo-")


def test_remove_callback():
    o = PipelineDataObfuscator()
    o._callbacks["cb1"] = lambda e, d: None
    assert o.remove_callback("cb1") is True
    assert o.remove_callback("cb1") is False
    assert "cb1" not in o._callbacks


def test_pruning_evicts_oldest():
    o = PipelineDataObfuscator()
    o.MAX_ENTRIES = 5
    ids = []
    for i in range(7):
        rid = o.obfuscate({"v": str(i)}, ["v"])
        ids.append(rid)
    assert len(o._state.entries) == 5
    # Oldest entries should be gone
    assert ids[0] not in o._state.entries
    assert ids[1] not in o._state.entries
    # Newest should remain
    assert ids[6] in o._state.entries


def test_unique_ids():
    o = PipelineDataObfuscator()
    ids = set()
    for i in range(100):
        rid = o.obfuscate({"v": str(i)}, ["v"])
        ids.add(rid)
    assert len(ids) == 100


if __name__ == "__main__":
    tests = [
        test_obfuscate_mask_strategy,
        test_obfuscate_hash_strategy,
        test_obfuscate_redact_strategy,
        test_obfuscate_default_strategy_is_mask,
        test_obfuscate_multiple_fields,
        test_obfuscate_field_not_in_payload,
        test_obfuscate_preserves_original_via_deepcopy,
        test_get_record_returns_none_for_missing,
        test_get_record_returns_dict,
        test_get_records_returns_newest_first,
        test_get_records_filter_by_pipeline_id,
        test_get_records_with_limit,
        test_get_records_empty,
        test_deobfuscate_returns_original,
        test_deobfuscate_returns_none_for_missing,
        test_deobfuscate_returns_deepcopy,
        test_get_stats,
        test_get_stats_empty,
        test_reset_clears_all,
        test_on_change_callback_fires,
        test_on_change_getter_setter,
        test_named_callbacks_fire,
        test_callback_exception_silenced,
        test_remove_callback,
        test_pruning_evicts_oldest,
        test_unique_ids,
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
