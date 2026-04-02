"""Test pipeline event replay."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_event_replay import PipelineEventReplay


def test_start_recording():
    """Start and stop recording."""
    er = PipelineEventReplay()
    rid = er.start_recording("test-session", tags=["debug"])
    assert rid.startswith("rec-")
    assert er.is_recording() is True
    assert er.get_active_recording() == rid

    rec = er.get_recording(rid)
    assert rec is not None
    assert rec["name"] == "test-session"
    assert rec["status"] == "recording"
    assert "debug" in rec["tags"]

    stopped = er.stop_recording()
    assert stopped == rid
    assert er.is_recording() is False
    assert er.get_recording(rid)["status"] == "stopped"
    print("OK: start recording")


def test_no_double_recording():
    """Can't start recording while already recording."""
    er = PipelineEventReplay()
    er.start_recording("a")
    assert er.start_recording("b") == ""
    er.stop_recording()
    assert er.start_recording("b") != ""
    print("OK: no double recording")


def test_stop_no_recording():
    """Stopping without active recording returns empty."""
    er = PipelineEventReplay()
    assert er.stop_recording() == ""
    print("OK: stop no recording")


def test_record_event():
    """Record events during session."""
    er = PipelineEventReplay()
    rid = er.start_recording("test")

    eid1 = er.record_event("task_started", "agent-1", {"task": "build"})
    eid2 = er.record_event("task_completed", "agent-1", {"task": "build"})
    assert eid1.startswith("evt-")

    e = er.get_event(eid1)
    assert e is not None
    assert e["event_type"] == "task_started"
    assert e["source"] == "agent-1"
    assert e["data"]["task"] == "build"
    assert e["sequence"] == 1

    rec = er.get_recording(rid)
    assert rec["event_count"] == 2
    er.stop_recording()
    print("OK: record event")


def test_record_no_session():
    """Can't record without active session."""
    er = PipelineEventReplay()
    assert er.record_event("x", "y") == ""
    print("OK: record no session")


def test_get_events():
    """Get events from recording."""
    er = PipelineEventReplay()
    rid = er.start_recording("test")
    er.record_event("start", "a", {"x": 1})
    er.record_event("complete", "a", {"x": 2})
    er.record_event("start", "b", {"x": 3})
    er.stop_recording()

    all_e = er.get_events(rid)
    assert len(all_e) == 3

    starts = er.get_events(rid, event_type="start")
    assert len(starts) == 2

    from_b = er.get_events(rid, source="b")
    assert len(from_b) == 1
    print("OK: get events")


def test_get_event_types():
    """Get event type counts."""
    er = PipelineEventReplay()
    rid = er.start_recording("test")
    er.record_event("start", "a")
    er.record_event("start", "b")
    er.record_event("complete", "a")
    er.stop_recording()

    types = er.get_event_types(rid)
    assert types["start"] == 2
    assert types["complete"] == 1
    print("OK: get event types")


def test_remove_recording():
    """Remove recording and its events."""
    er = PipelineEventReplay()
    rid = er.start_recording("test")
    eid = er.record_event("x", "y")
    er.stop_recording()

    assert er.remove_recording(rid) is True
    assert er.get_recording(rid) is None
    assert er.get_event(eid) is None
    assert er.remove_recording(rid) is False
    print("OK: remove recording")


def test_cant_remove_active():
    """Can't remove active recording."""
    er = PipelineEventReplay()
    rid = er.start_recording("test")
    assert er.remove_recording(rid) is False
    print("OK: cant remove active")


def test_list_recordings():
    """List recordings with filters."""
    er = PipelineEventReplay()
    r1 = er.start_recording("a", tags=["debug"])
    er.stop_recording()
    r2 = er.start_recording("b", tags=["test"])
    er.stop_recording()

    all_r = er.list_recordings()
    assert len(all_r) == 2

    tagged = er.list_recordings(tag="debug")
    assert len(tagged) == 1

    stopped = er.list_recordings(status="stopped")
    assert len(stopped) == 2
    print("OK: list recordings")


def test_replay():
    """Replay a recording."""
    er = PipelineEventReplay()
    rid = er.start_recording("test")
    er.record_event("task_start", "a", {"id": 1})
    er.record_event("task_end", "a", {"id": 1})
    er.stop_recording()

    replayed = []
    er.register_handler("task_start", lambda t, s, d: replayed.append(("start", d)))
    er.register_handler("task_end", lambda t, s, d: replayed.append(("end", d)))

    result = er.replay(rid)
    assert result["success"] is True
    assert result["total_events"] == 2
    assert result["replayed"] == 2
    assert result["errors"] == 0
    assert len(replayed) == 2

    rec = er.get_recording(rid)
    assert rec["replay_count"] == 1
    print("OK: replay")


def test_replay_with_filter():
    """Replay only specific event types."""
    er = PipelineEventReplay()
    rid = er.start_recording("test")
    er.record_event("start", "a")
    er.record_event("end", "a")
    er.stop_recording()

    replayed = []
    er.register_handler("start", lambda t, s, d: replayed.append(t))

    result = er.replay(rid, event_types=["start"])
    assert result["total_events"] == 1
    assert len(replayed) == 1
    print("OK: replay with filter")


def test_replay_active_recording():
    """Can't replay active recording."""
    er = PipelineEventReplay()
    rid = er.start_recording("test")
    result = er.replay(rid)
    assert result["success"] is False
    print("OK: replay active recording")


def test_handler_management():
    """Register and unregister handlers."""
    er = PipelineEventReplay()
    assert er.register_handler("start", lambda t, s, d: None) is True
    assert er.register_handler("start", lambda t, s, d: None) is False  # Dup

    assert er.unregister_handler("start") is True
    assert er.unregister_handler("start") is False
    print("OK: handler management")


def test_replay_error_handling():
    """Replay handles handler errors."""
    er = PipelineEventReplay()
    rid = er.start_recording("test")
    er.record_event("bad", "a")
    er.record_event("good", "a")
    er.stop_recording()

    def bad_handler(t, s, d):
        raise RuntimeError("boom")

    er.register_handler("bad", bad_handler)
    er.register_handler("good", lambda t, s, d: None)

    result = er.replay(rid)
    assert result["errors"] == 1
    assert result["replayed"] == 1
    print("OK: replay error handling")


def test_search_events():
    """Search events."""
    er = PipelineEventReplay()
    rid = er.start_recording("test")
    er.record_event("pipeline_start", "engine")
    er.record_event("task_complete", "agent-1")
    er.record_event("pipeline_stop", "engine")
    er.stop_recording()

    results = er.search_events("pipeline")
    assert len(results) == 2

    results = er.search_events("agent")
    assert len(results) == 1

    results = er.search_events("pipeline", recording_id=rid)
    assert len(results) == 2
    print("OK: search events")


def test_callbacks():
    """Callbacks fire on events."""
    er = PipelineEventReplay()

    fired = []
    assert er.on_change("mon", lambda a, rid: fired.append(a)) is True
    assert er.on_change("mon", lambda a, r: None) is False

    rid = er.start_recording("test")
    assert "recording_started" in fired

    er.stop_recording()
    assert "recording_stopped" in fired

    assert er.remove_callback("mon") is True
    assert er.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    er = PipelineEventReplay()
    rid = er.start_recording("test")
    er.record_event("a", "x")
    er.record_event("b", "y")
    er.stop_recording()

    er.replay(rid)

    stats = er.get_stats()
    assert stats["total_recordings"] == 1
    assert stats["total_events_recorded"] == 2
    assert stats["total_replays"] == 1
    assert stats["stored_recordings"] == 1
    assert stats["stored_events"] == 2
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    er = PipelineEventReplay()
    er.start_recording("test")
    er.record_event("a", "x")
    er.stop_recording()

    er.reset()
    assert er.list_recordings() == []
    assert er.is_recording() is False
    stats = er.get_stats()
    assert stats["total_recordings"] == 0
    assert stats["stored_events"] == 0
    print("OK: reset")


def test_max_recordings():
    """Max recordings enforced."""
    er = PipelineEventReplay(max_recordings=2)
    er.start_recording("a")
    er.stop_recording()
    er.start_recording("b")
    er.stop_recording()
    assert er.start_recording("c") == ""
    print("OK: max recordings")


def main():
    print("=== Pipeline Event Replay Tests ===\n")
    test_start_recording()
    test_no_double_recording()
    test_stop_no_recording()
    test_record_event()
    test_record_no_session()
    test_get_events()
    test_get_event_types()
    test_remove_recording()
    test_cant_remove_active()
    test_list_recordings()
    test_replay()
    test_replay_with_filter()
    test_replay_active_recording()
    test_handler_management()
    test_replay_error_handling()
    test_search_events()
    test_callbacks()
    test_stats()
    test_reset()
    test_max_recordings()
    print("\n=== ALL 20 TESTS PASSED ===")


if __name__ == "__main__":
    main()
