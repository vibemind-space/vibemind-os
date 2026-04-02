"""Test pipeline execution log -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_execution_log import PipelineExecutionLog


def test_log_entry():
    log = PipelineExecutionLog()
    eid = log.log_entry("pipe-1", "extract", "start", "Starting extraction")
    assert len(eid) > 0
    assert eid.startswith("pel-")
    print("OK: log entry")


def test_get_entries():
    log = PipelineExecutionLog()
    log.log_entry("pipe-1", "extract", "start", "msg1")
    log.log_entry("pipe-1", "transform", "complete", "msg2")
    entries = log.get_entries("pipe-1")
    assert len(entries) == 2
    print("OK: get entries")


def test_get_entries_filtered():
    log = PipelineExecutionLog()
    log.log_entry("pipe-1", "extract", "start", "msg1")
    log.log_entry("pipe-1", "transform", "complete", "msg2")
    log.log_entry("pipe-1", "extract", "complete", "msg3")
    log.log_entry("pipe-1", "load", "error", "msg4")

    # filter by step_name
    by_step = log.get_entries("pipe-1", step_name="extract")
    assert len(by_step) == 2

    # filter by event_type
    by_type = log.get_entries("pipe-1", event_type="complete")
    assert len(by_type) == 2

    # filter by both
    by_both = log.get_entries("pipe-1", step_name="extract", event_type="complete")
    assert len(by_both) == 1
    assert by_both[0]["step_name"] == "extract"
    assert by_both[0]["event_type"] == "complete"
    print("OK: get entries filtered")


def test_get_latest_entry():
    log = PipelineExecutionLog()
    log.log_entry("pipe-1", "extract", "start", "first")
    log.log_entry("pipe-1", "transform", "complete", "second")
    latest = log.get_latest_entry("pipe-1")
    assert latest is not None
    assert latest["message"] == "second"
    assert log.get_latest_entry("nonexistent") is None
    print("OK: get latest entry")


def test_get_entry_count():
    log = PipelineExecutionLog()
    log.log_entry("pipe-1", "extract", "start", "msg")
    log.log_entry("pipe-2", "load", "complete", "msg")
    assert log.get_entry_count() == 2
    assert log.get_entry_count("pipe-1") == 1
    print("OK: get entry count")


def test_clear_entries():
    log = PipelineExecutionLog()
    log.log_entry("pipe-1", "extract", "start", "msg1")
    log.log_entry("pipe-1", "transform", "complete", "msg2")
    cleared = log.clear_entries("pipe-1")
    assert cleared == 2
    assert log.get_entry_count("pipe-1") == 0
    print("OK: clear entries")


def test_list_pipelines():
    log = PipelineExecutionLog()
    log.log_entry("pipe-1", "extract", "start", "msg")
    log.log_entry("pipe-2", "load", "complete", "msg")
    pipelines = log.list_pipelines()
    assert "pipe-1" in pipelines
    assert "pipe-2" in pipelines
    print("OK: list pipelines")


def test_callbacks():
    log = PipelineExecutionLog()
    fired = []
    log.on_change("mon", lambda a, d: fired.append(a))
    log.log_entry("pipe-1", "extract", "start", "msg")
    assert len(fired) >= 1
    assert log.remove_callback("mon") is True
    assert log.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    log = PipelineExecutionLog()
    log.log_entry("pipe-1", "extract", "start", "msg")
    stats = log.get_stats()
    assert stats["total_logged"] == 1
    assert stats["current_entries"] == 1
    assert stats["unique_pipelines"] == 1
    assert stats["max_entries"] == 10000
    print("OK: stats")


def test_reset():
    log = PipelineExecutionLog()
    log.log_entry("pipe-1", "extract", "start", "msg")
    log.on_change("mon", lambda a, d: None)
    log.reset()
    assert log.get_entry_count() == 0
    assert log.list_pipelines() == []
    stats = log.get_stats()
    assert stats["total_logged"] == 0
    print("OK: reset")


def main():
    tests = [
        test_log_entry,
        test_get_entries,
        test_get_entries_filtered,
        test_get_latest_entry,
        test_get_entry_count,
        test_clear_entries,
        test_list_pipelines,
        test_callbacks,
        test_stats,
        test_reset,
    ]
    for t in tests:
        t()
    print(f"=== ALL {len(tests)} TESTS PASSED ===")


if __name__ == "__main__":
    main()
