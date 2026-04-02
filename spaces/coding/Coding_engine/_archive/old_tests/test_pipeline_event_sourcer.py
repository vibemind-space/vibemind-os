"""Test pipeline event sourcer."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_event_sourcer import PipelineEventSourcer


def test_append_event():
    """Append and retrieve event."""
    es = PipelineEventSourcer()
    eid = es.append_event("order-1", "order", "order_created",
                          payload={"amount": 100}, source="api",
                          tags=["v1"])
    assert eid.startswith("evt-")

    ev = es.get_event(eid)
    assert ev is not None
    assert ev["aggregate_id"] == "order-1"
    assert ev["aggregate_type"] == "order"
    assert ev["event_type"] == "order_created"
    assert ev["payload"] == {"amount": 100}
    assert ev["version"] == 1
    print("OK: append event")


def test_invalid_event():
    """Invalid event rejected."""
    es = PipelineEventSourcer()
    assert es.append_event("", "order", "created") == ""
    assert es.append_event("a", "order", "") == ""
    print("OK: invalid event")


def test_max_events():
    """Max events enforced."""
    es = PipelineEventSourcer(max_events=2)
    es.append_event("a", "t", "e1")
    es.append_event("a", "t", "e2")
    assert es.append_event("a", "t", "e3") == ""
    print("OK: max events")


def test_versioning():
    """Events increment version per aggregate."""
    es = PipelineEventSourcer()
    es.append_event("order-1", "order", "created")
    es.append_event("order-1", "order", "paid")
    es.append_event("order-2", "order", "created")

    assert es.get_aggregate_version("order-1") == 2
    assert es.get_aggregate_version("order-2") == 1
    print("OK: versioning")


def test_get_aggregate_events():
    """Get all events for an aggregate."""
    es = PipelineEventSourcer()
    es.append_event("order-1", "order", "created")
    es.append_event("order-1", "order", "paid")
    es.append_event("order-2", "order", "created")

    events = es.get_aggregate_events("order-1")
    assert len(events) == 2
    assert events[0]["version"] == 1
    assert events[1]["version"] == 2

    # From version
    from_v1 = es.get_aggregate_events("order-1", from_version=1)
    assert len(from_v1) == 1
    assert from_v1[0]["version"] == 2
    print("OK: get aggregate events")


def test_search_events():
    """Search events."""
    es = PipelineEventSourcer()
    es.append_event("o1", "order", "created", source="api", tags=["v1"])
    es.append_event("u1", "user", "registered", source="web")

    all_e = es.search_events()
    assert len(all_e) == 2

    by_type = es.search_events(aggregate_type="order")
    assert len(by_type) == 1

    by_event = es.search_events(event_type="registered")
    assert len(by_event) == 1

    by_source = es.search_events(source="api")
    assert len(by_source) == 1

    by_tag = es.search_events(tag="v1")
    assert len(by_tag) == 1
    print("OK: search events")


def test_create_snapshot():
    """Create snapshot."""
    es = PipelineEventSourcer()
    es.append_event("order-1", "order", "created")

    sid = es.create_snapshot("order-1", {"status": "created", "amount": 100})
    assert sid.startswith("snap-")

    snap = es.get_snapshot(sid)
    assert snap is not None
    assert snap["aggregate_id"] == "order-1"
    assert snap["state"]["status"] == "created"
    assert snap["version"] == 1
    print("OK: create snapshot")


def test_snapshot_requires_events():
    """Snapshot requires existing aggregate."""
    es = PipelineEventSourcer()
    assert es.create_snapshot("nonexistent", {"x": 1}) == ""
    print("OK: snapshot requires events")


def test_latest_snapshot():
    """Get latest snapshot."""
    es = PipelineEventSourcer()
    es.append_event("o1", "order", "created")
    es.create_snapshot("o1", {"v": 1})
    es.append_event("o1", "order", "paid")
    es.create_snapshot("o1", {"v": 2})

    snap = es.get_latest_snapshot("o1")
    assert snap is not None
    assert snap["version"] == 2
    assert snap["state"]["v"] == 2
    print("OK: latest snapshot")


def test_replay_aggregate():
    """Replay aggregate from snapshot."""
    es = PipelineEventSourcer()
    es.append_event("o1", "order", "created")
    es.append_event("o1", "order", "paid")
    es.create_snapshot("o1", {"status": "paid"})
    es.append_event("o1", "order", "shipped")

    replay = es.replay_aggregate("o1")
    assert replay["aggregate_id"] == "o1"
    assert replay["snapshot"] is not None
    assert replay["snapshot"]["version"] == 2
    assert len(replay["events_since_snapshot"]) == 1
    assert replay["events_since_snapshot"][0]["event_type"] == "shipped"
    assert replay["current_version"] == 3
    print("OK: replay aggregate")


def test_replay_no_snapshot():
    """Replay without snapshot returns all events."""
    es = PipelineEventSourcer()
    es.append_event("o1", "order", "created")
    es.append_event("o1", "order", "paid")

    replay = es.replay_aggregate("o1")
    assert replay["snapshot"] is None
    assert len(replay["events_since_snapshot"]) == 2
    print("OK: replay no snapshot")


def test_create_stream():
    """Create and manage stream."""
    es = PipelineEventSourcer()
    sid = es.create_stream("order_stream", aggregate_type="order",
                            event_types=["created", "paid"])
    assert sid.startswith("str-")

    st = es.get_stream(sid)
    assert st is not None
    assert st["name"] == "order_stream"
    assert st["status"] == "active"

    assert es.remove_stream(sid) is True
    assert es.remove_stream(sid) is False
    print("OK: create stream")


def test_stream_events():
    """Stream filters events."""
    es = PipelineEventSourcer()
    es.append_event("o1", "order", "created")
    es.append_event("o1", "order", "paid")
    es.append_event("u1", "user", "registered")

    sid = es.create_stream("orders", aggregate_type="order")
    events = es.get_stream_events(sid)
    assert len(events) == 2

    sid2 = es.create_stream("paid_only", event_types=["paid"])
    events2 = es.get_stream_events(sid2)
    assert len(events2) == 1
    print("OK: stream events")


def test_pause_resume_stream():
    """Pause and resume stream."""
    es = PipelineEventSourcer()
    sid = es.create_stream("test")

    assert es.pause_stream(sid) is True
    assert es.get_stream(sid)["status"] == "paused"
    assert es.pause_stream(sid) is False

    assert es.resume_stream(sid) is True
    assert es.get_stream(sid)["status"] == "active"
    assert es.resume_stream(sid) is False
    print("OK: pause resume stream")


def test_list_streams():
    """List streams."""
    es = PipelineEventSourcer()
    es.create_stream("s1")
    es.create_stream("s2")

    streams = es.list_streams()
    assert len(streams) == 2
    print("OK: list streams")


def test_callback():
    """Callback fires on append and snapshot."""
    es = PipelineEventSourcer()
    fired = []
    es.on_change("mon", lambda a, d: fired.append(a))

    es.append_event("o1", "order", "created")
    assert "event_appended" in fired

    es.create_snapshot("o1", {"x": 1})
    assert "snapshot_created" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    es = PipelineEventSourcer()
    assert es.on_change("mon", lambda a, d: None) is True
    assert es.on_change("mon", lambda a, d: None) is False
    assert es.remove_callback("mon") is True
    assert es.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    es = PipelineEventSourcer()
    es.append_event("o1", "order", "created")
    es.create_snapshot("o1", {"x": 1})
    es.create_stream("s1")
    es.replay_aggregate("o1")

    stats = es.get_stats()
    assert stats["total_events"] == 1
    assert stats["total_snapshots"] == 1
    assert stats["total_replays"] == 1
    assert stats["current_events"] == 1
    assert stats["unique_aggregates"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    es = PipelineEventSourcer()
    es.append_event("o1", "order", "created")
    es.create_snapshot("o1", {"x": 1})
    es.create_stream("s1")

    es.reset()
    assert es.search_events() == []
    assert es.list_streams() == []
    stats = es.get_stats()
    assert stats["current_events"] == 0
    assert stats["current_snapshots"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Event Sourcer Tests ===\n")
    test_append_event()
    test_invalid_event()
    test_max_events()
    test_versioning()
    test_get_aggregate_events()
    test_search_events()
    test_create_snapshot()
    test_snapshot_requires_events()
    test_latest_snapshot()
    test_replay_aggregate()
    test_replay_no_snapshot()
    test_create_stream()
    test_stream_events()
    test_pause_resume_stream()
    test_list_streams()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 19 TESTS PASSED ===")


if __name__ == "__main__":
    main()
