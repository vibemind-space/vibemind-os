"""Tests for PipelineStepTracker service."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_step_tracker import PipelineStepTracker


def test_start_tracking_returns_id():
    svc = PipelineStepTracker()
    tid = svc.start_tracking("p1", "step_a")
    assert isinstance(tid, str), f"Expected str, got {type(tid)}"
    assert tid.startswith("pstr-"), f"Expected pstr- prefix, got {tid}"
    print("  test_start_tracking_returns_id PASSED")


def test_start_tracking_stores_fields():
    svc = PipelineStepTracker()
    tid = svc.start_tracking("p1", "step_a", total_items=100)
    entry = svc.get_tracker(tid)
    assert entry is not None
    assert entry["pipeline_id"] == "p1"
    assert entry["step_name"] == "step_a"
    assert entry["total_items"] == 100
    assert entry["completed_items"] == 0
    assert entry["status"] == "in_progress"
    assert "created_at" in entry
    assert "updated_at" in entry
    print("  test_start_tracking_stores_fields PASSED")


def test_start_tracking_default_total_items():
    svc = PipelineStepTracker()
    tid = svc.start_tracking("p1", "step_a")
    entry = svc.get_tracker(tid)
    assert entry["total_items"] == 0
    print("  test_start_tracking_default_total_items PASSED")


def test_get_tracker_not_found():
    svc = PipelineStepTracker()
    result = svc.get_tracker("nonexistent")
    assert result is None
    print("  test_get_tracker_not_found PASSED")


def test_update_progress_completed_items():
    svc = PipelineStepTracker()
    tid = svc.start_tracking("p1", "step_a", total_items=50)
    ok = svc.update_progress(tid, completed_items=25)
    assert ok is True
    entry = svc.get_tracker(tid)
    assert entry["completed_items"] == 25
    print("  test_update_progress_completed_items PASSED")


def test_update_progress_status():
    svc = PipelineStepTracker()
    tid = svc.start_tracking("p1", "step_a")
    ok = svc.update_progress(tid, status="paused")
    assert ok is True
    entry = svc.get_tracker(tid)
    assert entry["status"] == "paused"
    print("  test_update_progress_status PASSED")


def test_update_progress_not_found():
    svc = PipelineStepTracker()
    ok = svc.update_progress("nonexistent", completed_items=5)
    assert ok is False
    print("  test_update_progress_not_found PASSED")


def test_complete_tracking():
    svc = PipelineStepTracker()
    tid = svc.start_tracking("p1", "step_a")
    ok = svc.complete_tracking(tid)
    assert ok is True
    entry = svc.get_tracker(tid)
    assert entry["status"] == "completed"
    print("  test_complete_tracking PASSED")


def test_complete_tracking_custom_status():
    svc = PipelineStepTracker()
    tid = svc.start_tracking("p1", "step_a")
    ok = svc.complete_tracking(tid, status="failed")
    assert ok is True
    entry = svc.get_tracker(tid)
    assert entry["status"] == "failed"
    print("  test_complete_tracking_custom_status PASSED")


def test_complete_tracking_not_found():
    svc = PipelineStepTracker()
    ok = svc.complete_tracking("nonexistent")
    assert ok is False
    print("  test_complete_tracking_not_found PASSED")


def test_get_trackers_empty():
    svc = PipelineStepTracker()
    result = svc.get_trackers()
    assert result == []
    print("  test_get_trackers_empty PASSED")


def test_get_trackers_newest_first():
    svc = PipelineStepTracker()
    tid1 = svc.start_tracking("p1", "step_a")
    tid2 = svc.start_tracking("p1", "step_b")
    tid3 = svc.start_tracking("p1", "step_c")
    result = svc.get_trackers()
    assert len(result) == 3
    assert result[0]["tracker_id"] == tid3
    assert result[2]["tracker_id"] == tid1
    print("  test_get_trackers_newest_first PASSED")


def test_get_trackers_filter_by_pipeline():
    svc = PipelineStepTracker()
    svc.start_tracking("p1", "step_a")
    svc.start_tracking("p2", "step_b")
    svc.start_tracking("p1", "step_c")
    result = svc.get_trackers(pipeline_id="p1")
    assert len(result) == 2
    for r in result:
        assert r["pipeline_id"] == "p1"
    print("  test_get_trackers_filter_by_pipeline PASSED")


def test_get_trackers_limit():
    svc = PipelineStepTracker()
    for i in range(10):
        svc.start_tracking("p1", f"step_{i}")
    result = svc.get_trackers(limit=3)
    assert len(result) == 3
    print("  test_get_trackers_limit PASSED")


def test_get_tracker_count_all():
    svc = PipelineStepTracker()
    svc.start_tracking("p1", "step_a")
    svc.start_tracking("p2", "step_b")
    assert svc.get_tracker_count() == 2
    print("  test_get_tracker_count_all PASSED")


def test_get_tracker_count_by_pipeline():
    svc = PipelineStepTracker()
    svc.start_tracking("p1", "step_a")
    svc.start_tracking("p2", "step_b")
    svc.start_tracking("p1", "step_c")
    assert svc.get_tracker_count(pipeline_id="p1") == 2
    assert svc.get_tracker_count(pipeline_id="p2") == 1
    assert svc.get_tracker_count(pipeline_id="p3") == 0
    print("  test_get_tracker_count_by_pipeline PASSED")


def test_get_stats_empty():
    svc = PipelineStepTracker()
    stats = svc.get_stats()
    assert stats["total_trackers"] == 0
    assert stats["completed_count"] == 0
    assert stats["in_progress_count"] == 0
    print("  test_get_stats_empty PASSED")


def test_get_stats_mixed():
    svc = PipelineStepTracker()
    tid1 = svc.start_tracking("p1", "step_a")
    tid2 = svc.start_tracking("p1", "step_b")
    svc.start_tracking("p1", "step_c")
    svc.complete_tracking(tid1)
    svc.complete_tracking(tid2)
    stats = svc.get_stats()
    assert stats["total_trackers"] == 3
    assert stats["completed_count"] == 2
    assert stats["in_progress_count"] == 1
    print("  test_get_stats_mixed PASSED")


def test_reset():
    svc = PipelineStepTracker()
    svc.start_tracking("p1", "step_a")
    svc.start_tracking("p2", "step_b")
    svc.reset()
    assert svc.get_tracker_count() == 0
    assert svc.get_stats()["total_trackers"] == 0
    print("  test_reset PASSED")


def test_on_change_property():
    svc = PipelineStepTracker()
    assert svc.on_change is None
    events = []
    svc.on_change = lambda action, data: events.append((action, data))
    svc.start_tracking("p1", "step_a")
    assert len(events) == 1
    assert events[0][0] == "tracking_started"
    print("  test_on_change_property PASSED")


def test_on_change_set_none():
    svc = PipelineStepTracker()
    svc.on_change = lambda a, d: None
    assert svc.on_change is not None
    svc.on_change = None
    assert svc.on_change is None
    print("  test_on_change_set_none PASSED")


def test_remove_callback():
    svc = PipelineStepTracker()
    svc.on_change = lambda a, d: None
    assert svc.remove_callback("__on_change__") is True
    assert svc.on_change is None
    print("  test_remove_callback PASSED")


def test_remove_callback_not_found():
    svc = PipelineStepTracker()
    assert svc.remove_callback("nonexistent") is False
    print("  test_remove_callback_not_found PASSED")


def test_fire_silent_on_error():
    svc = PipelineStepTracker()
    svc.on_change = lambda a, d: (_ for _ in ()).throw(RuntimeError("boom"))
    # Should not raise
    tid = svc.start_tracking("p1", "step_a")
    assert tid.startswith("pstr-")
    print("  test_fire_silent_on_error PASSED")


def test_fire_events_on_update():
    svc = PipelineStepTracker()
    events = []
    svc.on_change = lambda action, data: events.append(action)
    tid = svc.start_tracking("p1", "step_a")
    svc.update_progress(tid, completed_items=5)
    svc.complete_tracking(tid)
    assert "tracking_started" in events
    assert "progress_updated" in events
    assert "tracking_completed" in events
    print("  test_fire_events_on_update PASSED")


def test_unique_ids():
    svc = PipelineStepTracker()
    ids = set()
    for i in range(100):
        tid = svc.start_tracking("p1", f"step_{i}")
        ids.add(tid)
    assert len(ids) == 100
    print("  test_unique_ids PASSED")


def test_get_tracker_returns_copy():
    svc = PipelineStepTracker()
    tid = svc.start_tracking("p1", "step_a")
    entry = svc.get_tracker(tid)
    entry["status"] = "modified"
    original = svc.get_tracker(tid)
    assert original["status"] == "in_progress"
    print("  test_get_tracker_returns_copy PASSED")


def test_get_trackers_returns_dicts():
    svc = PipelineStepTracker()
    svc.start_tracking("p1", "step_a")
    result = svc.get_trackers()
    assert len(result) == 1
    assert isinstance(result[0], dict)
    assert "tracker_id" in result[0]
    print("  test_get_trackers_returns_dicts PASSED")


if __name__ == "__main__":
    print("Running PipelineStepTracker tests...")
    test_start_tracking_returns_id()
    test_start_tracking_stores_fields()
    test_start_tracking_default_total_items()
    test_get_tracker_not_found()
    test_update_progress_completed_items()
    test_update_progress_status()
    test_update_progress_not_found()
    test_complete_tracking()
    test_complete_tracking_custom_status()
    test_complete_tracking_not_found()
    test_get_trackers_empty()
    test_get_trackers_newest_first()
    test_get_trackers_filter_by_pipeline()
    test_get_trackers_limit()
    test_get_tracker_count_all()
    test_get_tracker_count_by_pipeline()
    test_get_stats_empty()
    test_get_stats_mixed()
    test_reset()
    test_on_change_property()
    test_on_change_set_none()
    test_remove_callback()
    test_remove_callback_not_found()
    test_fire_silent_on_error()
    test_fire_events_on_update()
    test_unique_ids()
    test_get_tracker_returns_copy()
    test_get_trackers_returns_dicts()
    print("All PipelineStepTracker tests passed!")
