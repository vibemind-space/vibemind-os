"""Tests for PipelineStepEmitter."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_step_emitter import PipelineStepEmitter


def test_emit_returns_id():
    e = PipelineStepEmitter()
    eid = e.emit("pipe1", "step_a", "started")
    assert eid.startswith("pse2-")
    assert len(eid) == 5 + 16


def test_emit_stores_event():
    e = PipelineStepEmitter()
    eid = e.emit("pipe1", "step_a", "completed", {"duration": 1.5})
    event = e.get_event(eid)
    assert event is not None
    assert event["pipeline_id"] == "pipe1"
    assert event["step_name"] == "step_a"
    assert event["event_type"] == "completed"
    assert event["data"] == {"duration": 1.5}
    assert "created_at" in event


def test_emit_default_data():
    e = PipelineStepEmitter()
    eid = e.emit("pipe1", "step_b", "started")
    event = e.get_event(eid)
    assert event["data"] == {}


def test_get_event_not_found():
    e = PipelineStepEmitter()
    assert e.get_event("pse2-nonexistent00000") is None


def test_get_events_by_pipeline():
    e = PipelineStepEmitter()
    e.emit("pipe1", "s1", "started")
    e.emit("pipe1", "s2", "completed")
    e.emit("pipe2", "s1", "started")
    events = e.get_events("pipe1")
    assert len(events) == 2
    assert all(ev["pipeline_id"] == "pipe1" for ev in events)


def test_get_events_by_step_name():
    e = PipelineStepEmitter()
    e.emit("pipe1", "build", "started")
    e.emit("pipe1", "test", "started")
    e.emit("pipe1", "build", "completed")
    events = e.get_events("pipe1", step_name="build")
    assert len(events) == 2
    assert all(ev["step_name"] == "build" for ev in events)


def test_get_events_by_event_type():
    e = PipelineStepEmitter()
    e.emit("pipe1", "s1", "started")
    e.emit("pipe1", "s1", "completed")
    e.emit("pipe1", "s2", "failed")
    events = e.get_events("pipe1", event_type="failed")
    assert len(events) == 1
    assert events[0]["event_type"] == "failed"


def test_get_events_newest_first():
    e = PipelineStepEmitter()
    id1 = e.emit("pipe1", "s1", "started")
    id2 = e.emit("pipe1", "s1", "completed")
    events = e.get_events("pipe1")
    assert events[0]["event_id"] == id2
    assert events[1]["event_id"] == id1


def test_get_events_limit():
    e = PipelineStepEmitter()
    for i in range(10):
        e.emit("pipe1", f"s{i}", "started")
    events = e.get_events("pipe1", limit=3)
    assert len(events) == 3


def test_get_events_combined_filters():
    e = PipelineStepEmitter()
    e.emit("pipe1", "build", "started")
    e.emit("pipe1", "build", "completed")
    e.emit("pipe1", "test", "started")
    e.emit("pipe1", "test", "failed")
    events = e.get_events("pipe1", step_name="test", event_type="failed")
    assert len(events) == 1
    assert events[0]["step_name"] == "test"
    assert events[0]["event_type"] == "failed"


def test_get_event_count_all():
    e = PipelineStepEmitter()
    e.emit("pipe1", "s1", "started")
    e.emit("pipe2", "s1", "started")
    e.emit("pipe1", "s2", "completed")
    assert e.get_event_count() == 3


def test_get_event_count_by_pipeline():
    e = PipelineStepEmitter()
    e.emit("pipe1", "s1", "started")
    e.emit("pipe2", "s1", "started")
    e.emit("pipe1", "s2", "completed")
    assert e.get_event_count(pipeline_id="pipe1") == 2


def test_get_event_count_by_event_type():
    e = PipelineStepEmitter()
    e.emit("pipe1", "s1", "started")
    e.emit("pipe1", "s1", "completed")
    e.emit("pipe2", "s1", "started")
    assert e.get_event_count(event_type="started") == 2


def test_get_event_count_combined():
    e = PipelineStepEmitter()
    e.emit("pipe1", "s1", "started")
    e.emit("pipe1", "s1", "failed")
    e.emit("pipe2", "s1", "failed")
    assert e.get_event_count(pipeline_id="pipe1", event_type="failed") == 1


def test_get_stats():
    e = PipelineStepEmitter()
    e.emit("pipe1", "s1", "started")
    e.emit("pipe1", "s1", "completed")
    e.emit("pipe2", "s2", "failed")
    e.emit("pipe3", "s3", "skipped")
    stats = e.get_stats()
    assert stats["total_events"] == 4
    assert stats["unique_pipelines"] == 3
    assert stats["events_by_type"]["started"] == 1
    assert stats["events_by_type"]["completed"] == 1
    assert stats["events_by_type"]["failed"] == 1
    assert stats["events_by_type"]["skipped"] == 1


def test_get_stats_empty():
    e = PipelineStepEmitter()
    stats = e.get_stats()
    assert stats["total_events"] == 0
    assert stats["unique_pipelines"] == 0
    assert stats["events_by_type"] == {}


def test_reset():
    e = PipelineStepEmitter()
    e.emit("pipe1", "s1", "started")
    e.emit("pipe1", "s2", "completed")
    e._callbacks["cb1"] = lambda a, d: None
    e.on_change = lambda a, d: None
    e.reset()
    assert e.get_event_count() == 0
    assert e.get_stats()["total_events"] == 0
    assert e.on_change is None
    assert len(e._callbacks) == 0


def test_on_change_property():
    e = PipelineStepEmitter()
    fired = []
    e.on_change = lambda action, data: fired.append(action)
    e.emit("pipe1", "s1", "started")
    assert len(fired) == 1
    assert fired[0] == "event_emitted"


def test_on_change_getter():
    e = PipelineStepEmitter()
    assert e.on_change is None
    cb = lambda a, d: None
    e.on_change = cb
    assert e.on_change is cb


def test_callbacks_fire_on_emit():
    e = PipelineStepEmitter()
    fired = []
    e._callbacks["my_cb"] = lambda action, data: fired.append((action, data["pipeline_id"]))
    e.emit("pipe1", "s1", "started")
    assert len(fired) == 1
    assert fired[0] == ("event_emitted", "pipe1")


def test_remove_callback():
    e = PipelineStepEmitter()
    e._callbacks["my_cb"] = lambda a, d: None
    assert e.remove_callback("my_cb") is True
    assert e.remove_callback("my_cb") is False


def test_remove_callback_not_found():
    e = PipelineStepEmitter()
    assert e.remove_callback("nonexistent") is False


def test_callback_exception_handled():
    e = PipelineStepEmitter()

    def bad_cb(action, data):
        raise ValueError("boom")

    e._callbacks["bad"] = bad_cb
    eid = e.emit("pipe1", "s1", "started")
    assert eid.startswith("pse2-")


def test_on_change_exception_handled():
    e = PipelineStepEmitter()
    e.on_change = lambda a, d: (_ for _ in ()).throw(RuntimeError("crash"))
    eid = e.emit("pipe1", "s1", "started")
    assert eid.startswith("pse2-")


def test_unique_ids():
    e = PipelineStepEmitter()
    ids = set()
    for i in range(50):
        ids.add(e.emit("pipe1", f"step_{i}", "started"))
    assert len(ids) == 50


def test_pruning():
    e = PipelineStepEmitter()
    e.MAX_ENTRIES = 5
    emitted_ids = []
    for i in range(8):
        emitted_ids.append(e.emit("pipe1", f"step_{i}", "started"))
    assert e.get_event_count() == 5
    # oldest entries should have been pruned
    assert e.get_event(emitted_ids[0]) is None
    assert e.get_event(emitted_ids[1]) is None
    assert e.get_event(emitted_ids[2]) is None
    # newest should still exist
    assert e.get_event(emitted_ids[-1]) is not None


def test_get_events_empty_pipeline():
    e = PipelineStepEmitter()
    e.emit("pipe1", "s1", "started")
    events = e.get_events("pipe_nonexistent")
    assert events == []


if __name__ == "__main__":
    tests = [
        test_emit_returns_id,
        test_emit_stores_event,
        test_emit_default_data,
        test_get_event_not_found,
        test_get_events_by_pipeline,
        test_get_events_by_step_name,
        test_get_events_by_event_type,
        test_get_events_newest_first,
        test_get_events_limit,
        test_get_events_combined_filters,
        test_get_event_count_all,
        test_get_event_count_by_pipeline,
        test_get_event_count_by_event_type,
        test_get_event_count_combined,
        test_get_stats,
        test_get_stats_empty,
        test_reset,
        test_on_change_property,
        test_on_change_getter,
        test_callbacks_fire_on_emit,
        test_remove_callback,
        test_remove_callback_not_found,
        test_callback_exception_handled,
        test_on_change_exception_handled,
        test_unique_ids,
        test_pruning,
        test_get_events_empty_pipeline,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
    print(f"{passed}/{len(tests)} tests passed")
