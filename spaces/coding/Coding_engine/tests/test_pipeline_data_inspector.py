"""Tests for PipelineDataInspector service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_data_inspector import PipelineDataInspector


def test_inspect_returns_id():
    insp = PipelineDataInspector()
    rid = insp.inspect({"key": "value"})
    assert isinstance(rid, str)
    assert rid.startswith("pdin-")


def test_inspect_with_label():
    insp = PipelineDataInspector()
    rid = insp.inspect({"a": 1}, label="my_label")
    record = insp.get_inspection(rid)
    assert record is not None
    assert record["label"] == "my_label"


def test_get_inspection_found():
    insp = PipelineDataInspector()
    rid = insp.inspect({"x": 10})
    record = insp.get_inspection(rid)
    assert record is not None
    assert record["inspection_id"] == rid
    assert "structure" in record
    assert "data" in record
    assert "created_at" in record


def test_get_inspection_not_found():
    insp = PipelineDataInspector()
    assert insp.get_inspection("pdin-nonexistent") is None


def test_get_inspection_returns_deepcopy():
    insp = PipelineDataInspector()
    rid = insp.inspect({"nested": {"inner": [1, 2, 3]}})
    record = insp.get_inspection(rid)
    record["data"]["nested"]["inner"].append(999)
    original = insp.get_inspection(rid)
    assert 999 not in original["data"]["nested"]["inner"]


def test_get_inspections_default():
    insp = PipelineDataInspector()
    insp.inspect({"a": 1})
    insp.inspect({"b": 2})
    results = insp.get_inspections()
    assert len(results) == 2


def test_get_inspections_newest_first():
    insp = PipelineDataInspector()
    id1 = insp.inspect({"first": True})
    id2 = insp.inspect({"second": True})
    results = insp.get_inspections()
    assert results[0]["inspection_id"] == id2
    assert results[1]["inspection_id"] == id1


def test_get_inspections_filter_by_label():
    insp = PipelineDataInspector()
    insp.inspect({"a": 1}, label="alpha")
    insp.inspect({"b": 2}, label="beta")
    insp.inspect({"c": 3}, label="alpha")
    results = insp.get_inspections(label="alpha")
    assert len(results) == 2
    assert all(r["label"] == "alpha" for r in results)


def test_get_inspections_limit():
    insp = PipelineDataInspector()
    for i in range(10):
        insp.inspect({"i": i})
    results = insp.get_inspections(limit=3)
    assert len(results) == 3


def test_get_inspection_count_all():
    insp = PipelineDataInspector()
    insp.inspect({"a": 1})
    insp.inspect({"b": 2})
    insp.inspect({"c": 3})
    assert insp.get_inspection_count() == 3


def test_get_inspection_count_by_label():
    insp = PipelineDataInspector()
    insp.inspect({"a": 1}, label="x")
    insp.inspect({"b": 2}, label="y")
    insp.inspect({"c": 3}, label="x")
    assert insp.get_inspection_count(label="x") == 2
    assert insp.get_inspection_count(label="y") == 1
    assert insp.get_inspection_count(label="z") == 0


def test_get_stats():
    insp = PipelineDataInspector()
    insp.inspect({"a": 1}, label="alpha")
    insp.inspect({"b": 2}, label="beta")
    insp.inspect({"c": 3}, label="alpha")
    stats = insp.get_stats()
    assert stats["total_inspections"] == 3
    assert stats["unique_labels"] == 2


def test_get_stats_empty():
    insp = PipelineDataInspector()
    stats = insp.get_stats()
    assert stats["total_inspections"] == 0
    assert stats["unique_labels"] == 0


def test_reset():
    insp = PipelineDataInspector()
    insp.inspect({"a": 1})
    insp.inspect({"b": 2})
    insp.reset()
    assert insp.get_inspection_count() == 0
    assert insp.get_inspections() == []


def test_reset_clears_callbacks():
    insp = PipelineDataInspector()
    insp._callbacks["my_cb"] = lambda e, d: None
    insp.on_change = lambda e, d: None
    insp.reset()
    assert insp.on_change is None
    assert len(insp._callbacks) == 0


def test_on_change_callback():
    events = []
    insp = PipelineDataInspector()
    insp.on_change = lambda e, d: events.append((e, d))
    insp.inspect({"key": "val"})
    assert len(events) == 1
    assert events[0][0] == "inspect"


def test_on_change_property():
    insp = PipelineDataInspector()
    assert insp.on_change is None
    cb = lambda e, d: None
    insp.on_change = cb
    assert insp.on_change is cb


def test_remove_callback():
    insp = PipelineDataInspector()
    insp._callbacks["cb1"] = lambda e, d: None
    assert insp.remove_callback("cb1") is True
    assert insp.remove_callback("cb1") is False


def test_remove_callback_nonexistent():
    insp = PipelineDataInspector()
    assert insp.remove_callback("nope") is False


def test_fire_silent_exceptions():
    insp = PipelineDataInspector()
    insp.on_change = lambda e, d: (_ for _ in ()).throw(RuntimeError("boom"))
    insp._callbacks["bad"] = lambda e, d: (_ for _ in ()).throw(ValueError("oops"))
    # Should not raise
    insp.inspect({"safe": True})
    assert insp.get_inspection_count() == 1


def test_structure_analysis_flat_dict():
    insp = PipelineDataInspector()
    rid = insp.inspect({"name": "alice", "age": 30})
    record = insp.get_inspection(rid)
    struct = record["structure"]
    assert struct["type"] == "dict"
    assert set(struct["keys"]) == {"name", "age"}
    assert struct["key_count"] == 2


def test_structure_analysis_nested_dict():
    insp = PipelineDataInspector()
    rid = insp.inspect({"outer": {"inner": {"deep": 1}}})
    record = insp.get_inspection(rid)
    struct = record["structure"]
    assert struct["max_depth"] >= 2


def test_structure_analysis_list_values():
    insp = PipelineDataInspector()
    rid = insp.inspect({"items": [1, 2, 3]})
    record = insp.get_inspection(rid)
    items_struct = record["structure"]["children"]["items"]
    assert items_struct["type"] == "list"
    assert items_struct["length"] == 3


def test_inspect_stores_deepcopy_of_data():
    data = {"mutable": [1, 2, 3]}
    insp = PipelineDataInspector()
    rid = insp.inspect(data)
    data["mutable"].append(999)
    record = insp.get_inspection(rid)
    assert 999 not in record["data"]["mutable"]


def test_generate_id_uniqueness():
    insp = PipelineDataInspector()
    ids = set()
    for i in range(100):
        rid = insp.inspect({"i": i}, label=f"l{i}")
        ids.add(rid)
    assert len(ids) == 100


def test_inspect_empty_dict():
    insp = PipelineDataInspector()
    rid = insp.inspect({})
    record = insp.get_inspection(rid)
    assert record is not None
    assert record["structure"]["type"] == "dict"
    assert record["structure"]["key_count"] == 0


def test_get_inspections_returns_deepcopy():
    insp = PipelineDataInspector()
    insp.inspect({"val": [10, 20]})
    results = insp.get_inspections()
    results[0]["data"]["val"].append(99)
    fresh = insp.get_inspections()
    assert 99 not in fresh[0]["data"]["val"]


if __name__ == "__main__":
    tests = [
        test_inspect_returns_id,
        test_inspect_with_label,
        test_get_inspection_found,
        test_get_inspection_not_found,
        test_get_inspection_returns_deepcopy,
        test_get_inspections_default,
        test_get_inspections_newest_first,
        test_get_inspections_filter_by_label,
        test_get_inspections_limit,
        test_get_inspection_count_all,
        test_get_inspection_count_by_label,
        test_get_stats,
        test_get_stats_empty,
        test_reset,
        test_reset_clears_callbacks,
        test_on_change_callback,
        test_on_change_property,
        test_remove_callback,
        test_remove_callback_nonexistent,
        test_fire_silent_exceptions,
        test_structure_analysis_flat_dict,
        test_structure_analysis_nested_dict,
        test_structure_analysis_list_values,
        test_inspect_stores_deepcopy_of_data,
        test_generate_id_uniqueness,
        test_inspect_empty_dict,
        test_get_inspections_returns_deepcopy,
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
