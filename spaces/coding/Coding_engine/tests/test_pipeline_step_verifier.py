"""Tests for PipelineStepVerifier service."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_step_verifier import PipelineStepVerifier


def test_verify_returns_id():
    svc = PipelineStepVerifier()
    vid = svc.verify("p1", "step_a", {"x": 1}, {"x": 1})
    assert isinstance(vid, str), f"Expected str, got {type(vid)}"
    assert vid.startswith("psvr-"), f"Expected psvr- prefix, got {vid}"
    print("  test_verify_returns_id PASSED")


def test_verify_passing():
    svc = PipelineStepVerifier()
    vid = svc.verify("p1", "step_a", {"x": 1, "y": 2}, {"x": 1, "y": 2})
    entry = svc.get_verification(vid)
    assert entry is not None
    assert entry["passed"] is True
    assert entry["mismatches"] == []
    print("  test_verify_passing PASSED")


def test_verify_failing_value_mismatch():
    svc = PipelineStepVerifier()
    vid = svc.verify("p1", "step_a", {"x": 1}, {"x": 2})
    entry = svc.get_verification(vid)
    assert entry["passed"] is False
    assert len(entry["mismatches"]) == 1
    assert entry["mismatches"][0]["reason"] == "value_mismatch"
    print("  test_verify_failing_value_mismatch PASSED")


def test_verify_failing_missing_field():
    svc = PipelineStepVerifier()
    vid = svc.verify("p1", "step_a", {"x": 1, "y": 2}, {"x": 1})
    entry = svc.get_verification(vid)
    assert entry["passed"] is False
    missing = [m for m in entry["mismatches"] if m["reason"] == "missing_in_actual"]
    assert len(missing) == 1
    assert missing[0]["field"] == "y"
    print("  test_verify_failing_missing_field PASSED")


def test_verify_failing_extra_field():
    svc = PipelineStepVerifier()
    vid = svc.verify("p1", "step_a", {"x": 1}, {"x": 1, "z": 3})
    entry = svc.get_verification(vid)
    assert entry["passed"] is False
    extra = [m for m in entry["mismatches"] if m["reason"] == "extra_in_actual"]
    assert len(extra) == 1
    assert extra[0]["field"] == "z"
    print("  test_verify_failing_extra_field PASSED")


def test_verify_non_dict_match():
    svc = PipelineStepVerifier()
    vid = svc.verify("p1", "step_a", 42, 42)
    entry = svc.get_verification(vid)
    assert entry["passed"] is True
    print("  test_verify_non_dict_match PASSED")


def test_verify_non_dict_mismatch():
    svc = PipelineStepVerifier()
    vid = svc.verify("p1", "step_a", 42, 99)
    entry = svc.get_verification(vid)
    assert entry["passed"] is False
    assert entry["mismatches"][0]["reason"] == "value_mismatch"
    print("  test_verify_non_dict_mismatch PASSED")


def test_verify_stores_metadata():
    svc = PipelineStepVerifier()
    vid = svc.verify("p1", "step_a", 1, 1, metadata={"env": "test"})
    entry = svc.get_verification(vid)
    assert entry["metadata"] == {"env": "test"}
    print("  test_verify_stores_metadata PASSED")


def test_verify_default_metadata():
    svc = PipelineStepVerifier()
    vid = svc.verify("p1", "step_a", 1, 1)
    entry = svc.get_verification(vid)
    assert entry["metadata"] == {}
    print("  test_verify_default_metadata PASSED")


def test_verify_stores_all_fields():
    svc = PipelineStepVerifier()
    vid = svc.verify("p1", "step_a", {"a": 1}, {"a": 1})
    entry = svc.get_verification(vid)
    assert entry["pipeline_id"] == "p1"
    assert entry["step_name"] == "step_a"
    assert entry["expected"] == {"a": 1}
    assert entry["actual"] == {"a": 1}
    assert "created_at" in entry
    assert "_seq" in entry
    print("  test_verify_stores_all_fields PASSED")


def test_get_verification_not_found():
    svc = PipelineStepVerifier()
    result = svc.get_verification("nonexistent")
    assert result is None
    print("  test_get_verification_not_found PASSED")


def test_get_verification_returns_copy():
    svc = PipelineStepVerifier()
    vid = svc.verify("p1", "step_a", 1, 1)
    entry = svc.get_verification(vid)
    entry["passed"] = "modified"
    original = svc.get_verification(vid)
    assert original["passed"] is True
    print("  test_get_verification_returns_copy PASSED")


def test_get_verifications_empty():
    svc = PipelineStepVerifier()
    result = svc.get_verifications()
    assert result == []
    print("  test_get_verifications_empty PASSED")


def test_get_verifications_newest_first():
    svc = PipelineStepVerifier()
    vid1 = svc.verify("p1", "step_a", 1, 1)
    vid2 = svc.verify("p1", "step_b", 2, 2)
    vid3 = svc.verify("p1", "step_c", 3, 3)
    result = svc.get_verifications()
    assert len(result) == 3
    assert result[0]["verification_id"] == vid3
    assert result[2]["verification_id"] == vid1
    print("  test_get_verifications_newest_first PASSED")


def test_get_verifications_filter_by_pipeline():
    svc = PipelineStepVerifier()
    svc.verify("p1", "step_a", 1, 1)
    svc.verify("p2", "step_b", 2, 2)
    svc.verify("p1", "step_c", 3, 3)
    result = svc.get_verifications(pipeline_id="p1")
    assert len(result) == 2
    for r in result:
        assert r["pipeline_id"] == "p1"
    print("  test_get_verifications_filter_by_pipeline PASSED")


def test_get_verifications_filter_by_step_name():
    svc = PipelineStepVerifier()
    svc.verify("p1", "step_a", 1, 1)
    svc.verify("p1", "step_b", 2, 2)
    svc.verify("p2", "step_a", 3, 3)
    result = svc.get_verifications(step_name="step_a")
    assert len(result) == 2
    for r in result:
        assert r["step_name"] == "step_a"
    print("  test_get_verifications_filter_by_step_name PASSED")


def test_get_verifications_filter_by_both():
    svc = PipelineStepVerifier()
    svc.verify("p1", "step_a", 1, 1)
    svc.verify("p1", "step_b", 2, 2)
    svc.verify("p2", "step_a", 3, 3)
    result = svc.get_verifications(pipeline_id="p1", step_name="step_a")
    assert len(result) == 1
    assert result[0]["pipeline_id"] == "p1"
    assert result[0]["step_name"] == "step_a"
    print("  test_get_verifications_filter_by_both PASSED")


def test_get_verifications_limit():
    svc = PipelineStepVerifier()
    for i in range(10):
        svc.verify("p1", f"step_{i}", i, i)
    result = svc.get_verifications(limit=3)
    assert len(result) == 3
    print("  test_get_verifications_limit PASSED")


def test_get_verifications_returns_dicts():
    svc = PipelineStepVerifier()
    svc.verify("p1", "step_a", 1, 1)
    result = svc.get_verifications()
    assert len(result) == 1
    assert isinstance(result[0], dict)
    assert "verification_id" in result[0]
    print("  test_get_verifications_returns_dicts PASSED")


def test_get_verification_count_all():
    svc = PipelineStepVerifier()
    svc.verify("p1", "step_a", 1, 1)
    svc.verify("p2", "step_b", 2, 2)
    assert svc.get_verification_count() == 2
    print("  test_get_verification_count_all PASSED")


def test_get_verification_count_by_pipeline():
    svc = PipelineStepVerifier()
    svc.verify("p1", "step_a", 1, 1)
    svc.verify("p2", "step_b", 2, 2)
    svc.verify("p1", "step_c", 3, 3)
    assert svc.get_verification_count(pipeline_id="p1") == 2
    assert svc.get_verification_count(pipeline_id="p2") == 1
    assert svc.get_verification_count(pipeline_id="p3") == 0
    print("  test_get_verification_count_by_pipeline PASSED")


def test_get_stats_empty():
    svc = PipelineStepVerifier()
    stats = svc.get_stats()
    assert stats["total_verifications"] == 0
    assert stats["passed_count"] == 0
    assert stats["failed_count"] == 0
    print("  test_get_stats_empty PASSED")


def test_get_stats_mixed():
    svc = PipelineStepVerifier()
    svc.verify("p1", "step_a", 1, 1)
    svc.verify("p1", "step_b", 1, 2)
    svc.verify("p1", "step_c", 3, 3)
    stats = svc.get_stats()
    assert stats["total_verifications"] == 3
    assert stats["passed_count"] == 2
    assert stats["failed_count"] == 1
    print("  test_get_stats_mixed PASSED")


def test_reset():
    svc = PipelineStepVerifier()
    svc.verify("p1", "step_a", 1, 1)
    svc.verify("p2", "step_b", 2, 2)
    svc.on_change = lambda a, d: None
    svc._callbacks["test_cb"] = lambda a, d: None
    svc.reset()
    assert svc.get_verification_count() == 0
    assert svc.get_stats()["total_verifications"] == 0
    assert svc.on_change is None
    assert len(svc._callbacks) == 0
    print("  test_reset PASSED")


def test_on_change_property():
    svc = PipelineStepVerifier()
    assert svc.on_change is None
    events = []
    svc.on_change = lambda action, data: events.append((action, data))
    svc.verify("p1", "step_a", 1, 1)
    assert len(events) == 1
    assert events[0][0] == "verification_created"
    print("  test_on_change_property PASSED")


def test_on_change_set_none():
    svc = PipelineStepVerifier()
    svc.on_change = lambda a, d: None
    assert svc.on_change is not None
    svc.on_change = None
    assert svc.on_change is None
    print("  test_on_change_set_none PASSED")


def test_remove_callback():
    svc = PipelineStepVerifier()
    svc._callbacks["my_cb"] = lambda a, d: None
    assert svc.remove_callback("my_cb") is True
    assert "my_cb" not in svc._callbacks
    print("  test_remove_callback PASSED")


def test_remove_callback_not_found():
    svc = PipelineStepVerifier()
    assert svc.remove_callback("nonexistent") is False
    print("  test_remove_callback_not_found PASSED")


def test_fire_silent_on_error():
    svc = PipelineStepVerifier()
    svc.on_change = lambda a, d: (_ for _ in ()).throw(RuntimeError("boom"))
    # Should not raise
    vid = svc.verify("p1", "step_a", 1, 1)
    assert vid.startswith("psvr-")
    print("  test_fire_silent_on_error PASSED")


def test_fire_callback_error_silent():
    svc = PipelineStepVerifier()
    svc._callbacks["bad"] = lambda a, d: (_ for _ in ()).throw(ValueError("oops"))
    vid = svc.verify("p1", "step_a", 1, 1)
    assert vid.startswith("psvr-")
    print("  test_fire_callback_error_silent PASSED")


def test_unique_ids():
    svc = PipelineStepVerifier()
    ids = set()
    for i in range(100):
        vid = svc.verify("p1", f"step_{i}", i, i)
        ids.add(vid)
    assert len(ids) == 100
    print("  test_unique_ids PASSED")


def test_pruning_removes_oldest_quarter():
    svc = PipelineStepVerifier()
    svc.MAX_ENTRIES = 10
    # Add 11 entries: after 11th, there are 11 entries.
    # On the 12th call, _prune sees 11 > 10, removes 11 // 4 = 2 oldest, then adds 12th = 10
    for i in range(12):
        svc.verify("p1", f"step_{i}", i, i)
    count = svc.get_verification_count()
    assert count <= 11, f"Expected <= 11 entries after pruning, got {count}"
    # Verify newest entries are still present
    results = svc.get_verifications(limit=100)
    step_names = [r["step_name"] for r in results]
    assert "step_11" in step_names
    # Verify oldest were removed
    assert "step_0" not in step_names
    print("  test_pruning_removes_oldest_quarter PASSED")


def test_multiple_mismatches():
    svc = PipelineStepVerifier()
    vid = svc.verify("p1", "step_a", {"a": 1, "b": 2, "c": 3}, {"a": 1, "b": 99})
    entry = svc.get_verification(vid)
    assert entry["passed"] is False
    assert len(entry["mismatches"]) == 2
    reasons = {m["reason"] for m in entry["mismatches"]}
    assert "value_mismatch" in reasons
    assert "missing_in_actual" in reasons
    print("  test_multiple_mismatches PASSED")


if __name__ == "__main__":
    print("Running PipelineStepVerifier tests...")
    test_verify_returns_id()
    test_verify_passing()
    test_verify_failing_value_mismatch()
    test_verify_failing_missing_field()
    test_verify_failing_extra_field()
    test_verify_non_dict_match()
    test_verify_non_dict_mismatch()
    test_verify_stores_metadata()
    test_verify_default_metadata()
    test_verify_stores_all_fields()
    test_get_verification_not_found()
    test_get_verification_returns_copy()
    test_get_verifications_empty()
    test_get_verifications_newest_first()
    test_get_verifications_filter_by_pipeline()
    test_get_verifications_filter_by_step_name()
    test_get_verifications_filter_by_both()
    test_get_verifications_limit()
    test_get_verifications_returns_dicts()
    test_get_verification_count_all()
    test_get_verification_count_by_pipeline()
    test_get_stats_empty()
    test_get_stats_mixed()
    test_reset()
    test_on_change_property()
    test_on_change_set_none()
    test_remove_callback()
    test_remove_callback_not_found()
    test_fire_silent_on_error()
    test_fire_callback_error_silent()
    test_unique_ids()
    test_pruning_removes_oldest_quarter()
    test_multiple_mismatches()
    print("All PipelineStepVerifier tests passed!")
