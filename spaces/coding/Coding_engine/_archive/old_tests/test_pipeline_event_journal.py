"""Test pipeline event journal -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_event_journal import PipelineEventJournal


def test_record_event():
    ej = PipelineEventJournal()
    eid = ej.record_event("pipeline-1", "started", data={"workers": 4})
    assert len(eid) > 0
    assert eid.startswith("pej-")
    print("OK: record event")


def test_get_event():
    ej = PipelineEventJournal()
    eid = ej.record_event("pipeline-1", "started", severity="info")
    event = ej.get_event(eid)
    assert event is not None
    assert event["pipeline_id"] == "pipeline-1"
    assert event["event_type"] == "started"
    assert event["severity"] == "info"
    assert ej.get_event("nonexistent") is None
    print("OK: get event")


def test_get_pipeline_events():
    ej = PipelineEventJournal()
    ej.record_event("pipeline-1", "started")
    ej.record_event("pipeline-1", "completed")
    ej.record_event("pipeline-2", "started")
    events = ej.get_pipeline_events("pipeline-1")
    assert len(events) == 2
    print("OK: get pipeline events")


def test_filter_by_type():
    ej = PipelineEventJournal()
    ej.record_event("pipeline-1", "started")
    ej.record_event("pipeline-1", "error", severity="error")
    ej.record_event("pipeline-1", "started")
    events = ej.get_pipeline_events("pipeline-1", event_type="started")
    assert len(events) == 2
    print("OK: filter by type")


def test_filter_by_severity():
    ej = PipelineEventJournal()
    ej.record_event("pipeline-1", "e1", severity="info")
    ej.record_event("pipeline-1", "e2", severity="error")
    ej.record_event("pipeline-1", "e3", severity="error")
    events = ej.get_pipeline_events("pipeline-1", severity="error")
    assert len(events) == 2
    print("OK: filter by severity")


def test_get_recent_events():
    ej = PipelineEventJournal()
    ej.record_event("pipeline-1", "e1")
    ej.record_event("pipeline-2", "e2")
    ej.record_event("pipeline-1", "e3")
    recent = ej.get_recent_events(limit=2)
    assert len(recent) == 2
    print("OK: get recent events")


def test_event_count_by_type():
    ej = PipelineEventJournal()
    ej.record_event("pipeline-1", "started")
    ej.record_event("pipeline-1", "started")
    ej.record_event("pipeline-1", "completed")
    counts = ej.get_event_count_by_type("pipeline-1")
    assert counts["started"] == 2
    assert counts["completed"] == 1
    print("OK: event count by type")


def test_event_count_by_severity():
    ej = PipelineEventJournal()
    ej.record_event("pipeline-1", "e1", severity="info")
    ej.record_event("pipeline-1", "e2", severity="error")
    ej.record_event("pipeline-1", "e3", severity="info")
    counts = ej.get_event_count_by_severity("pipeline-1")
    assert counts["info"] == 2
    assert counts["error"] == 1
    print("OK: event count by severity")


def test_clear_pipeline():
    ej = PipelineEventJournal()
    ej.record_event("pipeline-1", "e1")
    ej.record_event("pipeline-1", "e2")
    ej.record_event("pipeline-2", "e3")
    removed = ej.clear_pipeline("pipeline-1")
    assert removed == 2
    assert ej.get_event_count() == 1
    print("OK: clear pipeline")


def test_list_pipelines():
    ej = PipelineEventJournal()
    ej.record_event("pipeline-1", "e1")
    ej.record_event("pipeline-2", "e2")
    pipelines = ej.list_pipelines()
    assert "pipeline-1" in pipelines
    assert "pipeline-2" in pipelines
    print("OK: list pipelines")


def test_callbacks():
    ej = PipelineEventJournal()
    fired = []
    ej.on_change("mon", lambda a, d: fired.append(a))
    ej.record_event("pipeline-1", "e1")
    assert len(fired) >= 1
    assert ej.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    ej = PipelineEventJournal()
    ej.record_event("pipeline-1", "e1")
    stats = ej.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    ej = PipelineEventJournal()
    ej.record_event("pipeline-1", "e1")
    ej.reset()
    assert ej.get_event_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Event Journal Tests ===\n")
    test_record_event()
    test_get_event()
    test_get_pipeline_events()
    test_filter_by_type()
    test_filter_by_severity()
    test_get_recent_events()
    test_event_count_by_type()
    test_event_count_by_severity()
    test_clear_pipeline()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 13 TESTS PASSED ===")


if __name__ == "__main__":
    main()
