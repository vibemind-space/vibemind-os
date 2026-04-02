"""Tests for PipelineStepSanitizer service."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_step_sanitizer import PipelineStepSanitizer


def test_sanitize_returns_id_with_prefix():
    svc = PipelineStepSanitizer()
    rid = svc.sanitize("p1", "step_a")
    assert isinstance(rid, str), f"Expected str, got {type(rid)}"
    assert rid.startswith("psst-"), f"Expected psst- prefix, got {rid}"
    print("  test_sanitize_returns_id_with_prefix PASSED")


def test_sanitize_stores_fields():
    svc = PipelineStepSanitizer()
    rid = svc.sanitize("p1", "step_a", mode="lenient", metadata={"key": "val"})
    entry = svc.get_sanitization(rid)
    assert entry is not None
    assert entry["record_id"] == rid
    assert entry["pipeline_id"] == "p1"
    assert entry["step_name"] == "step_a"
    assert entry["mode"] == "lenient"
    assert entry["metadata"] == {"key": "val"}
    assert "created_at" in entry
    assert "updated_at" in entry
    print("  test_sanitize_stores_fields PASSED")


def test_sanitize_default_mode_strict():
    svc = PipelineStepSanitizer()
    rid = svc.sanitize("p1", "step_a")
    entry = svc.get_sanitization(rid)
    assert entry["mode"] == "strict"
    print("  test_sanitize_default_mode_strict PASSED")


def test_sanitize_metadata_deepcopy():
    svc = PipelineStepSanitizer()
    meta = {"nested": {"a": 1}}
    rid = svc.sanitize("p1", "step_a", metadata=meta)
    meta["nested"]["a"] = 999
    entry = svc.get_sanitization(rid)
    assert entry["metadata"]["nested"]["a"] == 1
    print("  test_sanitize_metadata_deepcopy PASSED")


def test_sanitize_empty_pipeline_id_returns_empty():
    svc = PipelineStepSanitizer()
    result = svc.sanitize("", "step_a")
    assert result == ""
    print("  test_sanitize_empty_pipeline_id_returns_empty PASSED")


def test_sanitize_empty_step_name_returns_empty():
    svc = PipelineStepSanitizer()
    result = svc.sanitize("p1", "")
    assert result == ""
    print("  test_sanitize_empty_step_name_returns_empty PASSED")


def test_sanitize_both_empty_returns_empty():
    svc = PipelineStepSanitizer()
    result = svc.sanitize("", "")
    assert result == ""
    print("  test_sanitize_both_empty_returns_empty PASSED")


def test_get_sanitization_found():
    svc = PipelineStepSanitizer()
    rid = svc.sanitize("p1", "step_a")
    entry = svc.get_sanitization(rid)
    assert entry is not None
    assert entry["record_id"] == rid
    print("  test_get_sanitization_found PASSED")


def test_get_sanitization_not_found():
    svc = PipelineStepSanitizer()
    result = svc.get_sanitization("nonexistent")
    assert result is None
    print("  test_get_sanitization_not_found PASSED")


def test_get_sanitization_returns_copy():
    svc = PipelineStepSanitizer()
    rid = svc.sanitize("p1", "step_a")
    entry = svc.get_sanitization(rid)
    entry["mode"] = "modified"
    original = svc.get_sanitization(rid)
    assert original["mode"] == "strict"
    print("  test_get_sanitization_returns_copy PASSED")


def test_get_sanitizations_all():
    svc = PipelineStepSanitizer()
    svc.sanitize("p1", "step_a")
    svc.sanitize("p2", "step_b")
    svc.sanitize("p1", "step_c")
    result = svc.get_sanitizations()
    assert len(result) == 3
    print("  test_get_sanitizations_all PASSED")


def test_get_sanitizations_filter_by_pipeline():
    svc = PipelineStepSanitizer()
    svc.sanitize("p1", "step_a")
    svc.sanitize("p2", "step_b")
    svc.sanitize("p1", "step_c")
    result = svc.get_sanitizations(pipeline_id="p1")
    assert len(result) == 2
    for r in result:
        assert r["pipeline_id"] == "p1"
    print("  test_get_sanitizations_filter_by_pipeline PASSED")


def test_get_sanitizations_newest_first():
    svc = PipelineStepSanitizer()
    rid1 = svc.sanitize("p1", "step_a")
    rid2 = svc.sanitize("p1", "step_b")
    rid3 = svc.sanitize("p1", "step_c")
    result = svc.get_sanitizations()
    assert len(result) == 3
    assert result[0]["record_id"] == rid3
    assert result[2]["record_id"] == rid1
    print("  test_get_sanitizations_newest_first PASSED")


def test_get_sanitizations_limit():
    svc = PipelineStepSanitizer()
    for i in range(10):
        svc.sanitize("p1", f"step_{i}")
    result = svc.get_sanitizations(limit=3)
    assert len(result) == 3
    print("  test_get_sanitizations_limit PASSED")


def test_get_sanitization_count_all():
    svc = PipelineStepSanitizer()
    svc.sanitize("p1", "step_a")
    svc.sanitize("p2", "step_b")
    assert svc.get_sanitization_count() == 2
    print("  test_get_sanitization_count_all PASSED")


def test_get_sanitization_count_by_pipeline():
    svc = PipelineStepSanitizer()
    svc.sanitize("p1", "step_a")
    svc.sanitize("p2", "step_b")
    svc.sanitize("p1", "step_c")
    assert svc.get_sanitization_count(pipeline_id="p1") == 2
    assert svc.get_sanitization_count(pipeline_id="p2") == 1
    assert svc.get_sanitization_count(pipeline_id="p3") == 0
    print("  test_get_sanitization_count_by_pipeline PASSED")


def test_get_stats_empty():
    svc = PipelineStepSanitizer()
    stats = svc.get_stats()
    assert stats["total_sanitizations"] == 0
    assert stats["unique_pipelines"] == 0
    print("  test_get_stats_empty PASSED")


def test_get_stats_populated():
    svc = PipelineStepSanitizer()
    svc.sanitize("p1", "step_a")
    svc.sanitize("p2", "step_b")
    svc.sanitize("p1", "step_c")
    stats = svc.get_stats()
    assert stats["total_sanitizations"] == 3
    assert stats["unique_pipelines"] == 2
    print("  test_get_stats_populated PASSED")


def test_on_change_property():
    svc = PipelineStepSanitizer()
    assert svc.on_change is None
    events = []
    svc.on_change = lambda action, data: events.append((action, data))
    svc.sanitize("p1", "step_a")
    assert len(events) == 1
    assert events[0][0] == "sanitize"
    print("  test_on_change_property PASSED")


def test_on_change_set_none():
    svc = PipelineStepSanitizer()
    svc.on_change = lambda a, d: None
    assert svc.on_change is not None
    svc.on_change = None
    assert svc.on_change is None
    print("  test_on_change_set_none PASSED")


def test_remove_callback():
    svc = PipelineStepSanitizer()
    svc.on_change = lambda a, d: None
    assert svc.remove_callback("__on_change__") is True
    assert svc.on_change is None
    print("  test_remove_callback PASSED")


def test_remove_callback_not_found():
    svc = PipelineStepSanitizer()
    assert svc.remove_callback("nonexistent") is False
    print("  test_remove_callback_not_found PASSED")


def test_fire_silent_on_error():
    svc = PipelineStepSanitizer()
    svc.on_change = lambda a, d: (_ for _ in ()).throw(RuntimeError("boom"))
    rid = svc.sanitize("p1", "step_a")
    assert rid.startswith("psst-")
    print("  test_fire_silent_on_error PASSED")


def test_prune_evicts_oldest():
    svc = PipelineStepSanitizer()
    svc.MAX_ENTRIES = 5
    for i in range(8):
        svc.sanitize("p1", f"step_{i}")
    assert svc.get_sanitization_count() == 5
    # The newest 5 should remain
    results = svc.get_sanitizations()
    step_names = [r["step_name"] for r in results]
    assert "step_7" in step_names
    assert "step_6" in step_names
    assert "step_5" in step_names
    print("  test_prune_evicts_oldest PASSED")


def test_reset():
    svc = PipelineStepSanitizer()
    svc.sanitize("p1", "step_a")
    svc.sanitize("p2", "step_b")
    svc.on_change = lambda a, d: None
    svc.reset()
    assert svc.get_sanitization_count() == 0
    assert svc.get_stats()["total_sanitizations"] == 0
    assert svc.on_change is None
    print("  test_reset PASSED")


def test_unique_ids():
    svc = PipelineStepSanitizer()
    ids = set()
    for i in range(100):
        rid = svc.sanitize("p1", f"step_{i}")
        ids.add(rid)
    assert len(ids) == 100
    print("  test_unique_ids PASSED")


if __name__ == "__main__":
    print("Running PipelineStepSanitizer tests...")
    test_sanitize_returns_id_with_prefix()
    test_sanitize_stores_fields()
    test_sanitize_default_mode_strict()
    test_sanitize_metadata_deepcopy()
    test_sanitize_empty_pipeline_id_returns_empty()
    test_sanitize_empty_step_name_returns_empty()
    test_sanitize_both_empty_returns_empty()
    test_get_sanitization_found()
    test_get_sanitization_not_found()
    test_get_sanitization_returns_copy()
    test_get_sanitizations_all()
    test_get_sanitizations_filter_by_pipeline()
    test_get_sanitizations_newest_first()
    test_get_sanitizations_limit()
    test_get_sanitization_count_all()
    test_get_sanitization_count_by_pipeline()
    test_get_stats_empty()
    test_get_stats_populated()
    test_on_change_property()
    test_on_change_set_none()
    test_remove_callback()
    test_remove_callback_not_found()
    test_fire_silent_on_error()
    test_prune_evicts_oldest()
    test_reset()
    test_unique_ids()
    print("All PipelineStepSanitizer tests passed!")
