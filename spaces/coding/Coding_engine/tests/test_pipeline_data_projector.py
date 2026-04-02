"""Tests for PipelineDataProjector service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_data_projector import PipelineDataProjector


def test_register_projection():
    proj = PipelineDataProjector()
    pid = proj.register_projection("basic", ["name", "age"])
    assert pid.startswith("pdpr-")
    assert proj.get_projection_count() == 1


def test_project_basic():
    proj = PipelineDataProjector()
    pid = proj.register_projection("select_fields", ["name", "age"])
    result = proj.project(pid, {"name": "Alice", "age": 30, "email": "a@b.com"})
    assert result == {"name": "Alice", "age": 30}


def test_project_with_rename():
    proj = PipelineDataProjector()
    pid = proj.register_projection("renamed", ["name", "age"], rename={"name": "full_name"})
    result = proj.project(pid, {"name": "Bob", "age": 25, "city": "NYC"})
    assert result == {"full_name": "Bob", "age": 25}


def test_project_missing_fields():
    proj = PipelineDataProjector()
    pid = proj.register_projection("sparse", ["name", "phone"])
    result = proj.project(pid, {"name": "Carol"})
    assert result == {"name": "Carol"}
    assert "phone" not in result


def test_project_not_found():
    proj = PipelineDataProjector()
    result = proj.project("pdpr-nonexistent", {"a": 1})
    assert result == {}


def test_project_batch():
    proj = PipelineDataProjector()
    pid = proj.register_projection("batch", ["x", "y"])
    records = [{"x": 1, "y": 2, "z": 3}, {"x": 4, "y": 5, "z": 6}]
    results = proj.project_batch(pid, records)
    assert len(results) == 2
    assert results[0] == {"x": 1, "y": 2}
    assert results[1] == {"x": 4, "y": 5}


def test_project_increments_usage_count():
    proj = PipelineDataProjector()
    pid = proj.register_projection("counter", ["a"])
    proj.project(pid, {"a": 1})
    proj.project(pid, {"a": 2})
    proj.project(pid, {"a": 3})
    entry = proj.get_projection(pid)
    assert entry["usage_count"] == 3


def test_get_projection():
    proj = PipelineDataProjector()
    pid = proj.register_projection("detail", ["f1", "f2"], rename={"f1": "field_one"})
    entry = proj.get_projection(pid)
    assert entry["name"] == "detail"
    assert entry["fields"] == ["f1", "f2"]
    assert entry["rename"] == {"f1": "field_one"}
    assert entry["usage_count"] == 0
    assert "created_at" in entry


def test_get_projection_not_found():
    proj = PipelineDataProjector()
    assert proj.get_projection("pdpr-missing") == {}


def test_get_projections():
    proj = PipelineDataProjector()
    proj.register_projection("a", ["x"])
    proj.register_projection("b", ["y"])
    all_projs = proj.get_projections()
    assert len(all_projs) == 2
    names = {p["name"] for p in all_projs}
    assert names == {"a", "b"}


def test_remove_projection():
    proj = PipelineDataProjector()
    pid = proj.register_projection("removable", ["x"])
    assert proj.remove_projection(pid) is True
    assert proj.get_projection_count() == 0
    assert proj.remove_projection(pid) is False


def test_get_stats():
    proj = PipelineDataProjector()
    p1 = proj.register_projection("s1", ["a"])
    p2 = proj.register_projection("s2", ["b"])
    proj.project(p1, {"a": 1})
    proj.project(p1, {"a": 2})
    proj.project(p2, {"b": 3})
    stats = proj.get_stats()
    assert stats["total_projections"] == 2
    assert stats["total_operations"] == 3


def test_reset():
    proj = PipelineDataProjector()
    proj.register_projection("r1", ["x"])
    proj.register_projection("r2", ["y"])
    proj.reset()
    assert proj.get_projection_count() == 0
    assert proj.get_projections() == []


def test_on_change_callback():
    events = []
    proj = PipelineDataProjector()
    proj.on_change = lambda e, d: events.append(e)
    proj.register_projection("cb", ["a"])
    assert "register" in events


def test_remove_callback():
    proj = PipelineDataProjector()
    proj._callbacks["my_cb"] = lambda e, d: None
    assert proj.remove_callback("my_cb") is True
    assert proj.remove_callback("my_cb") is False


def test_generate_id_uniqueness():
    proj = PipelineDataProjector()
    ids = set()
    for i in range(100):
        pid = proj.register_projection(f"u{i}", ["field"])
        ids.add(pid)
    assert len(ids) == 100


if __name__ == "__main__":
    tests = [
        test_register_projection,
        test_project_basic,
        test_project_with_rename,
        test_project_missing_fields,
        test_project_not_found,
        test_project_batch,
        test_project_increments_usage_count,
        test_get_projection,
        test_get_projection_not_found,
        test_get_projections,
        test_remove_projection,
        test_get_stats,
        test_reset,
        test_on_change_callback,
        test_remove_callback,
        test_generate_id_uniqueness,
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
