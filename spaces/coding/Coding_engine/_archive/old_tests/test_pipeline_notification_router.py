"""Test pipeline notification router."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_notification_router import PipelineNotificationRouter


def test_create_channel():
    """Create and retrieve channel."""
    nr = PipelineNotificationRouter()
    cid = nr.create_channel("alerts", channel_type="slack", tags=["ops"])
    assert cid.startswith("nch-")

    c = nr.get_channel(cid)
    assert c is not None
    assert c["name"] == "alerts"
    assert c["channel_type"] == "slack"
    assert c["status"] == "active"

    assert nr.remove_channel(cid) is True
    assert nr.remove_channel(cid) is False
    print("OK: create channel")


def test_invalid_channel():
    """Invalid channel rejected."""
    nr = PipelineNotificationRouter()
    assert nr.create_channel("") == ""
    assert nr.create_channel("x", channel_type="invalid") == ""
    print("OK: invalid channel")


def test_disable_enable_channel():
    """Disable and enable channel."""
    nr = PipelineNotificationRouter()
    cid = nr.create_channel("test")

    assert nr.disable_channel(cid) is True
    assert nr.get_channel(cid)["status"] == "disabled"
    assert nr.disable_channel(cid) is False

    assert nr.enable_channel(cid) is True
    assert nr.get_channel(cid)["status"] == "active"
    assert nr.enable_channel(cid) is False
    print("OK: disable enable channel")


def test_subscribe():
    """Subscribe to channel."""
    nr = PipelineNotificationRouter()
    cid = nr.create_channel("alerts")

    sid = nr.subscribe("agent_a", cid)
    assert sid.startswith("nsub-")

    # Duplicate rejected
    assert nr.subscribe("agent_a", cid) == ""

    assert nr.unsubscribe(sid) is True
    assert nr.unsubscribe(sid) is False
    print("OK: subscribe")


def test_pause_resume_subscription():
    """Pause and resume subscription."""
    nr = PipelineNotificationRouter()
    cid = nr.create_channel("alerts")
    sid = nr.subscribe("agent_a", cid)

    assert nr.pause_subscription(sid) is True
    assert nr.pause_subscription(sid) is False

    assert nr.resume_subscription(sid) is True
    assert nr.resume_subscription(sid) is False
    print("OK: pause resume subscription")


def test_send_notification():
    """Send a notification."""
    nr = PipelineNotificationRouter()
    cid = nr.create_channel("log_channel")
    nr.subscribe("agent_a", cid)

    nid = nr.send("Build Complete", message="All tests passed",
                  severity="info", category="build", source="ci")
    assert nid.startswith("notif-")

    n = nr.get_notification(nid)
    assert n is not None
    assert n["title"] == "Build Complete"
    assert n["severity"] == "info"
    assert len(n["deliveries"]) == 1
    print("OK: send notification")


def test_severity_filter():
    """Severity filter blocks low-severity notifications."""
    nr = PipelineNotificationRouter()
    cid = nr.create_channel("errors_only")
    nr.subscribe("agent_a", cid, filter_severity="error")

    # Info should not deliver
    nid1 = nr.send("Info msg", severity="info")
    assert len(nr.get_notification(nid1)["deliveries"]) == 0

    # Error should deliver
    nid2 = nr.send("Error msg", severity="error")
    assert len(nr.get_notification(nid2)["deliveries"]) == 1
    print("OK: severity filter")


def test_category_filter():
    """Category filter blocks non-matching notifications."""
    nr = PipelineNotificationRouter()
    cid = nr.create_channel("build_channel")
    nr.subscribe("agent_a", cid, filter_category="build")

    nid1 = nr.send("Deploy", category="deploy")
    assert len(nr.get_notification(nid1)["deliveries"]) == 0

    nid2 = nr.send("Build", category="build")
    assert len(nr.get_notification(nid2)["deliveries"]) == 1
    print("OK: category filter")


def test_disabled_channel_no_delivery():
    """Disabled channel doesn't receive notifications."""
    nr = PipelineNotificationRouter()
    cid = nr.create_channel("ch")
    nr.subscribe("agent_a", cid)
    nr.disable_channel(cid)

    nid = nr.send("Test")
    assert len(nr.get_notification(nid)["deliveries"]) == 0
    print("OK: disabled channel no delivery")


def test_paused_subscription_no_delivery():
    """Paused subscription doesn't receive notifications."""
    nr = PipelineNotificationRouter()
    cid = nr.create_channel("ch")
    sid = nr.subscribe("agent_a", cid)
    nr.pause_subscription(sid)

    nid = nr.send("Test")
    assert len(nr.get_notification(nid)["deliveries"]) == 0
    print("OK: paused subscription no delivery")


def test_multiple_channels():
    """Notification routes to multiple channels."""
    nr = PipelineNotificationRouter()
    c1 = nr.create_channel("ch1")
    c2 = nr.create_channel("ch2")
    nr.subscribe("agent_a", c1)
    nr.subscribe("agent_b", c2)

    nid = nr.send("Broadcast")
    assert len(nr.get_notification(nid)["deliveries"]) == 2
    print("OK: multiple channels")


def test_search_notifications():
    """Search notifications."""
    nr = PipelineNotificationRouter()
    cid = nr.create_channel("ch")
    nr.subscribe("a", cid)

    nr.send("Info", severity="info", category="build")
    nr.send("Error", severity="error", category="deploy")

    all_n = nr.search_notifications()
    assert len(all_n) == 2

    by_sev = nr.search_notifications(severity="error")
    assert len(by_sev) == 1

    by_cat = nr.search_notifications(category="build")
    assert len(by_cat) == 1
    print("OK: search notifications")


def test_subscriber_channels():
    """Get subscriber's channels."""
    nr = PipelineNotificationRouter()
    c1 = nr.create_channel("ch1")
    c2 = nr.create_channel("ch2")
    nr.subscribe("agent_a", c1)
    nr.subscribe("agent_a", c2)

    channels = nr.get_subscriber_channels("agent_a")
    assert len(channels) == 2
    print("OK: subscriber channels")


def test_list_channels():
    """List channels with filters."""
    nr = PipelineNotificationRouter()
    nr.create_channel("a", channel_type="log")
    c2 = nr.create_channel("b", channel_type="slack")
    nr.disable_channel(c2)

    all_c = nr.list_channels()
    assert len(all_c) == 2

    by_status = nr.list_channels(status="disabled")
    assert len(by_status) == 1

    by_type = nr.list_channels(channel_type="log")
    assert len(by_type) == 1
    print("OK: list channels")


def test_remove_channel_cascades():
    """Remove channel removes subscriptions."""
    nr = PipelineNotificationRouter()
    cid = nr.create_channel("ch")
    nr.subscribe("agent_a", cid)

    nr.remove_channel(cid)
    assert nr.get_subscriber_channels("agent_a") == []
    print("OK: remove channel cascades")


def test_callback():
    """Callback fires on notification send."""
    nr = PipelineNotificationRouter()
    fired = []
    nr.on_change("mon", lambda a, d: fired.append(a))

    cid = nr.create_channel("ch")
    nr.subscribe("a", cid)
    nr.send("Test")
    assert "notification_sent" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    nr = PipelineNotificationRouter()
    assert nr.on_change("mon", lambda a, d: None) is True
    assert nr.on_change("mon", lambda a, d: None) is False
    assert nr.remove_callback("mon") is True
    assert nr.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    nr = PipelineNotificationRouter()
    cid = nr.create_channel("ch")
    nr.subscribe("a", cid)
    nr.send("Test1")
    nr.send("Test2")

    stats = nr.get_stats()
    assert stats["total_channels_created"] == 1
    assert stats["total_subscriptions"] == 1
    assert stats["total_notifications"] == 2
    assert stats["total_deliveries"] == 2
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    nr = PipelineNotificationRouter()
    cid = nr.create_channel("ch")
    nr.subscribe("a", cid)
    nr.send("Test")

    nr.reset()
    assert nr.list_channels() == []
    assert nr.search_notifications() == []
    stats = nr.get_stats()
    assert stats["current_channels"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Notification Router Tests ===\n")
    test_create_channel()
    test_invalid_channel()
    test_disable_enable_channel()
    test_subscribe()
    test_pause_resume_subscription()
    test_send_notification()
    test_severity_filter()
    test_category_filter()
    test_disabled_channel_no_delivery()
    test_paused_subscription_no_delivery()
    test_multiple_channels()
    test_search_notifications()
    test_subscriber_channels()
    test_list_channels()
    test_remove_channel_cascades()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 19 TESTS PASSED ===")


if __name__ == "__main__":
    main()
