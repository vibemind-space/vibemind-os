"""Test pipeline notification hub."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_notification_hub import PipelineNotificationHub


def test_subscribe():
    """Subscribe and retrieve subscriber."""
    hub = PipelineNotificationHub()
    received = []
    sid = hub.subscribe("monitor", lambda s, t, m, sv, d: received.append(m), tags=["core"])
    assert sid.startswith("sub-")

    sub = hub.get_subscriber(sid)
    assert sub is not None
    assert sub["name"] == "monitor"

    assert hub.unsubscribe(sid) is True
    assert hub.unsubscribe(sid) is False
    print("OK: subscribe")


def test_invalid_subscribe():
    """Invalid subscribe rejected."""
    hub = PipelineNotificationHub()
    assert hub.subscribe("", lambda s, t, m, sv, d: None) == ""
    assert hub.subscribe("name", None) == ""
    print("OK: invalid subscribe")


def test_duplicate():
    """Duplicate name rejected."""
    hub = PipelineNotificationHub()
    hub.subscribe("mon", lambda s, t, m, sv, d: None)
    assert hub.subscribe("mon", lambda s, t, m, sv, d: None) == ""
    print("OK: duplicate")


def test_max_subscribers():
    """Max subscribers enforced."""
    hub = PipelineNotificationHub(max_subscribers=2)
    hub.subscribe("a", lambda s, t, m, sv, d: None)
    hub.subscribe("b", lambda s, t, m, sv, d: None)
    assert hub.subscribe("c", lambda s, t, m, sv, d: None) == ""
    print("OK: max subscribers")


def test_get_by_name():
    """Get subscriber by name."""
    hub = PipelineNotificationHub()
    hub.subscribe("monitor", lambda s, t, m, sv, d: None)

    sub = hub.get_by_name("monitor")
    assert sub is not None
    assert hub.get_by_name("nonexistent") is None
    print("OK: get by name")


def test_unsubscribe_by_name():
    """Unsubscribe by name."""
    hub = PipelineNotificationHub()
    hub.subscribe("monitor", lambda s, t, m, sv, d: None)

    assert hub.unsubscribe_by_name("monitor") is True
    assert hub.unsubscribe_by_name("monitor") is False
    print("OK: unsubscribe by name")


def test_notify_basic():
    """Basic notification delivery."""
    hub = PipelineNotificationHub()
    received = []
    hub.subscribe("mon", lambda s, t, m, sv, d: received.append(m))

    nid = hub.notify("engine", "build", "Build started")
    assert nid.startswith("ntf-")
    assert "Build started" in received
    print("OK: notify basic")


def test_notify_topic_filter():
    """Only matching topic subscribers receive."""
    hub = PipelineNotificationHub()
    r1, r2 = [], []
    hub.subscribe("build_mon", lambda s, t, m, sv, d: r1.append(m), topics=["build"])
    hub.subscribe("test_mon", lambda s, t, m, sv, d: r2.append(m), topics=["test"])

    hub.notify("engine", "build", "Build done")
    assert len(r1) == 1
    assert len(r2) == 0
    print("OK: notify topic filter")


def test_notify_no_topic_gets_all():
    """Subscribers with no topic filter get all notifications."""
    hub = PipelineNotificationHub()
    received = []
    hub.subscribe("all_mon", lambda s, t, m, sv, d: received.append(m))

    hub.notify("engine", "build", "msg1")
    hub.notify("engine", "test", "msg2")
    assert len(received) == 2
    print("OK: notify no topic gets all")


def test_severity_filter():
    """Subscriber min_severity filters low severity."""
    hub = PipelineNotificationHub()
    received = []
    hub.subscribe("error_mon", lambda s, t, m, sv, d: received.append(m), min_severity="error")

    hub.notify("engine", "", "info msg", severity="info")
    assert len(received) == 0

    hub.notify("engine", "", "error msg", severity="error")
    assert len(received) == 1
    print("OK: severity filter")


def test_notify_data():
    """Notification data passed to handler."""
    hub = PipelineNotificationHub()
    received_data = []
    hub.subscribe("mon", lambda s, t, m, sv, d: received_data.append(d))

    hub.notify("engine", "build", "done", data={"status": "ok"})
    assert received_data[0]["status"] == "ok"
    print("OK: notify data")


def test_handler_exception():
    """Handler exception doesn't break delivery."""
    hub = PipelineNotificationHub()
    received = []

    def bad_handler(s, t, m, sv, d):
        raise RuntimeError("fail")

    hub.subscribe("bad", bad_handler)
    hub.subscribe("good", lambda s, t, m, sv, d: received.append(m))

    hub.notify("engine", "", "test msg")
    assert len(received) == 1
    print("OK: handler exception")


def test_subscriber_stats():
    """Subscriber total_received updated."""
    hub = PipelineNotificationHub()
    hub.subscribe("mon", lambda s, t, m, sv, d: None)

    hub.notify("engine", "", "msg1")
    hub.notify("engine", "", "msg2")

    sub = hub.get_by_name("mon")
    assert sub["total_received"] == 2
    print("OK: subscriber stats")


def test_list_subscribers():
    """List subscribers with filters."""
    hub = PipelineNotificationHub()
    hub.subscribe("a", lambda s, t, m, sv, d: None, topics=["build"], tags=["core"])
    hub.subscribe("b", lambda s, t, m, sv, d: None, topics=["test"])

    all_s = hub.list_subscribers()
    assert len(all_s) == 2

    by_topic = hub.list_subscribers(topic="build")
    assert len(by_topic) == 1

    by_tag = hub.list_subscribers(tag="core")
    assert len(by_tag) == 1
    print("OK: list subscribers")


def test_history():
    """Notification history tracking."""
    hub = PipelineNotificationHub()
    hub.subscribe("mon", lambda s, t, m, sv, d: None)

    hub.notify("engine", "build", "msg1")
    hub.notify("engine", "test", "msg2")

    hist = hub.get_history()
    assert len(hist) == 2

    by_source = hub.get_history(source="engine")
    assert len(by_source) == 2

    by_topic = hub.get_history(topic="build")
    assert len(by_topic) == 1

    limited = hub.get_history(limit=1)
    assert len(limited) == 1
    print("OK: history")


def test_callback():
    """Callback fires on events."""
    hub = PipelineNotificationHub()
    fired = []
    hub.on_change("mon", lambda a, d: fired.append(a))

    hub.subscribe("s1", lambda s, t, m, sv, d: None)
    assert "subscriber_added" in fired

    hub.notify("engine", "", "msg")
    assert "notification_sent" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    hub = PipelineNotificationHub()
    assert hub.on_change("mon", lambda a, d: None) is True
    assert hub.on_change("mon", lambda a, d: None) is False
    assert hub.remove_callback("mon") is True
    assert hub.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    hub = PipelineNotificationHub()
    hub.subscribe("mon", lambda s, t, m, sv, d: None)
    hub.notify("engine", "", "msg1")
    hub.notify("engine", "", "msg2")

    stats = hub.get_stats()
    assert stats["current_subscribers"] == 1
    assert stats["total_subscribers"] == 1
    assert stats["total_sent"] == 2
    assert stats["total_delivered"] == 2
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    hub = PipelineNotificationHub()
    hub.subscribe("mon", lambda s, t, m, sv, d: None)

    hub.reset()
    assert hub.list_subscribers() == []
    stats = hub.get_stats()
    assert stats["current_subscribers"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Notification Hub Tests ===\n")
    test_subscribe()
    test_invalid_subscribe()
    test_duplicate()
    test_max_subscribers()
    test_get_by_name()
    test_unsubscribe_by_name()
    test_notify_basic()
    test_notify_topic_filter()
    test_notify_no_topic_gets_all()
    test_severity_filter()
    test_notify_data()
    test_handler_exception()
    test_subscriber_stats()
    test_list_subscribers()
    test_history()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 19 TESTS PASSED ===")


if __name__ == "__main__":
    main()
