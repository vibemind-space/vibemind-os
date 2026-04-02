"""Tests for PipelineStepCounter service."""

import sys
sys.path.insert(0, ".")

from src.services.pipeline_step_counter import PipelineStepCounter


def test_increment():
    svc = PipelineStepCounter()
    result = svc.increment("p1", "step_a")
    assert result == 1, f"Expected 1, got {result}"
    result = svc.increment("p1", "step_a")
    assert result == 2, f"Expected 2, got {result}"
    result = svc.increment("p1", "step_a", count=5)
    assert result == 7, f"Expected 7, got {result}"
    result = svc.increment("p1", "step_b")
    assert result == 1, f"Expected 1, got {result}"
    print("  test_increment PASSED")


def test_get_count():
    svc = PipelineStepCounter()
    assert svc.get_count("p1", "step_a") == 0
    svc.increment("p1", "step_a", count=3)
    assert svc.get_count("p1", "step_a") == 3
    assert svc.get_count("p1", "nonexistent") == 0
    assert svc.get_count("no_pipeline", "step_a") == 0
    print("  test_get_count PASSED")


def test_get_counts():
    svc = PipelineStepCounter()
    assert svc.get_counts("p1") == {}
    svc.increment("p1", "step_a", count=2)
    svc.increment("p1", "step_b", count=5)
    counts = svc.get_counts("p1")
    assert counts == {"step_a": 2, "step_b": 5}, f"Got {counts}"
    assert svc.get_counts("nonexistent") == {}
    print("  test_get_counts PASSED")


def test_reset_counter():
    svc = PipelineStepCounter()
    assert svc.reset_counter("p1", "step_a") is False
    svc.increment("p1", "step_a", count=3)
    svc.increment("p1", "step_b", count=2)
    result = svc.reset_counter("p1", "step_a")
    assert result is True, f"Expected True, got {result}"
    assert svc.get_count("p1", "step_a") == 0
    assert svc.get_count("p1", "step_b") == 2
    result = svc.reset_counter("p1", "nonexistent")
    assert result is False, f"Expected False, got {result}"
    # Reset last step should clean up pipeline
    svc.reset_counter("p1", "step_b")
    assert svc.get_counts("p1") == {}
    print("  test_reset_counter PASSED")


def test_get_total():
    svc = PipelineStepCounter()
    assert svc.get_total() == 0
    svc.increment("p1", "step_a", count=3)
    svc.increment("p1", "step_b", count=2)
    svc.increment("p2", "step_x", count=10)
    assert svc.get_total("p1") == 5
    assert svc.get_total("p2") == 10
    assert svc.get_total() == 15
    assert svc.get_total("nonexistent") == 0
    print("  test_get_total PASSED")


def test_get_most_executed():
    svc = PipelineStepCounter()
    assert svc.get_most_executed("p1") == []
    svc.increment("p1", "step_a", count=10)
    svc.increment("p1", "step_b", count=50)
    svc.increment("p1", "step_c", count=30)
    svc.increment("p1", "step_d", count=5)
    svc.increment("p1", "step_e", count=20)
    svc.increment("p1", "step_f", count=1)
    top3 = svc.get_most_executed("p1", limit=3)
    assert len(top3) == 3, f"Expected 3, got {len(top3)}"
    assert top3[0] == ("step_b", 50), f"Got {top3[0]}"
    assert top3[1] == ("step_c", 30), f"Got {top3[1]}"
    assert top3[2] == ("step_e", 20), f"Got {top3[2]}"
    assert svc.get_most_executed("nonexistent") == []
    print("  test_get_most_executed PASSED")


def test_list_pipelines():
    svc = PipelineStepCounter()
    assert svc.list_pipelines() == []
    svc.increment("p1", "step_a")
    svc.increment("p2", "step_b")
    svc.increment("p3", "step_c")
    pipelines = svc.list_pipelines()
    assert sorted(pipelines) == ["p1", "p2", "p3"], f"Got {pipelines}"
    print("  test_list_pipelines PASSED")


def test_callbacks():
    svc = PipelineStepCounter()
    events = []
    svc.on_change("tracker", lambda action, detail: events.append((action, detail)))
    svc.increment("p1", "step_a")
    assert len(events) == 1
    assert events[0][0] == "counter_incremented"
    assert events[0][1]["pipeline_id"] == "p1"
    assert events[0][1]["step_name"] == "step_a"
    assert events[0][1]["new_total"] == 1
    svc.reset_counter("p1", "step_a")
    assert len(events) == 2
    assert events[1][0] == "counter_reset"
    result = svc.remove_callback("tracker")
    assert result is True
    result = svc.remove_callback("nonexistent")
    assert result is False
    svc.increment("p1", "step_b")
    assert len(events) == 2  # no new events after removal
    print("  test_callbacks PASSED")


def test_stats():
    svc = PipelineStepCounter()
    stats = svc.get_stats()
    assert stats["total_counters"] == 0
    assert stats["total_executions"] == 0
    assert stats["max_entries"] == 10000
    assert stats["pipelines"] == 0
    assert stats["registered_callbacks"] == 0
    svc.increment("p1", "step_a", count=5)
    svc.increment("p1", "step_b", count=3)
    svc.increment("p2", "step_x", count=10)
    svc.on_change("cb1", lambda a, d: None)
    stats = svc.get_stats()
    assert stats["total_counters"] == 3
    assert stats["total_executions"] == 18
    assert stats["pipelines"] == 2
    assert stats["registered_callbacks"] == 1
    print("  test_stats PASSED")


def test_reset():
    svc = PipelineStepCounter()
    svc.increment("p1", "step_a", count=5)
    svc.increment("p2", "step_b", count=3)
    svc.on_change("cb1", lambda a, d: None)
    svc.reset()
    assert svc.get_total() == 0
    assert svc.list_pipelines() == []
    stats = svc.get_stats()
    assert stats["total_counters"] == 0
    assert stats["registered_callbacks"] == 0
    print("  test_reset PASSED")


if __name__ == "__main__":
    test_increment()
    test_get_count()
    test_get_counts()
    test_reset_counter()
    test_get_total()
    test_get_most_executed()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")
