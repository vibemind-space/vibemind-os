"""Test pipeline event aggregator -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_event_aggregator import PipelineEventAggregator


def test_record_event():
    ea = PipelineEventAggregator()
    eid = ea.record_event("pipeline-1", "started", data={"source": "scheduler"})
    assert len(eid) > 0
    assert eid.startswith("pea-")
    print("OK: record event")


def test_get_events():
    ea = PipelineEventAggregator()
    ea.record_event("pipeline-1", "started")
    ea.record_event("pipeline-1", "step_done")
    ea.record_event("pipeline-1", "completed")
    events = ea.get_events("pipeline-1")
    assert len(events) == 3
    print("OK: get events")


def test_get_events_filtered():
    ea = PipelineEventAggregator()
    ea.record_event("pipeline-1", "started")
    ea.record_event("pipeline-1", "step_done")
    ea.record_event("pipeline-1", "step_done")
    ea.record_event("pipeline-1", "completed")
    events = ea.get_events("pipeline-1", event_type="step_done")
    assert len(events) == 2
    print("OK: get events filtered")


def test_get_event_count():
    ea = PipelineEventAggregator()
    ea.record_event("pipeline-1", "started")
    ea.record_event("pipeline-2", "started")
    assert ea.get_event_count("pipeline-1") == 1
    assert ea.get_event_count() >= 2
    print("OK: get event count")


def test_get_event_types():
    ea = PipelineEventAggregator()
    ea.record_event("pipeline-1", "started")
    ea.record_event("pipeline-1", "completed")
    types = ea.get_event_types("pipeline-1")
    assert "started" in types
    assert "completed" in types
    print("OK: get event types")


def test_get_latest_event():
    ea = PipelineEventAggregator()
    ea.record_event("pipeline-1", "started")
    ea.record_event("pipeline-1", "completed")
    latest = ea.get_latest_event("pipeline-1")
    assert latest is not None
    assert latest["event_type"] == "completed"
    print("OK: get latest event")


def test_get_summary():
    ea = PipelineEventAggregator()
    ea.record_event("pipeline-1", "started")
    ea.record_event("pipeline-1", "step_done")
    ea.record_event("pipeline-1", "step_done")
    summary = ea.get_summary("pipeline-1")
    assert summary["started"] == 1
    assert summary["step_done"] == 2
    print("OK: get summary")


def test_callbacks():
    ea = PipelineEventAggregator()
    fired = []
    ea.on_change("mon", lambda d: fired.append(d))
    ea.record_event("pipeline-1", "started")
    assert len(fired) >= 1
    assert ea.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    ea = PipelineEventAggregator()
    ea.record_event("pipeline-1", "started")
    stats = ea.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    ea = PipelineEventAggregator()
    ea.record_event("pipeline-1", "started")
    ea.reset()
    assert ea.get_total_events() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Event Aggregator Tests ===\n")
    test_record_event()
    test_get_events()
    test_get_events_filtered()
    test_get_event_count()
    test_get_event_types()
    test_get_latest_event()
    test_get_summary()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")


if __name__ == "__main__":
    main()
