"""Test pipeline notification dispatcher."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_notification_dispatcher import PipelineNotificationDispatcher


def test_dispatch():
    """Dispatch and retrieve notification."""
    nd = PipelineNotificationDispatcher()
    nid = nd.dispatch("Build Failed", "Module X failed compilation",
                      severity="error", source="ci",
                      channel="slack", recipients=["alice"],
                      tags=["build"], metadata={"run": 42})
    assert nid.startswith("notif-")

    n = nd.get_notification(nid)
    assert n is not None
    assert n["title"] == "Build Failed"
    assert n["message"] == "Module X failed compilation"
    assert n["severity"] == "error"
    assert n["source"] == "ci"
    assert n["channel"] == "slack"
    assert "alice" in n["recipients"]
    assert n["status"] == "pending"

    assert nd.remove_notification(nid) is True
    assert nd.remove_notification(nid) is False
    print("OK: dispatch")


def test_invalid_dispatch():
    """Invalid dispatch rejected."""
    nd = PipelineNotificationDispatcher()
    assert nd.dispatch("", "msg") == ""
    assert nd.dispatch("title", "") == ""
    assert nd.dispatch("t", "m", severity="invalid") == ""
    assert nd.dispatch("t", "m", channel="invalid") == ""
    print("OK: invalid dispatch")


def test_mark_delivered():
    """Mark notification as delivered."""
    nd = PipelineNotificationDispatcher()
    nid = nd.dispatch("Test", "msg")

    assert nd.mark_delivered(nid) is True
    assert nd.get_notification(nid)["status"] == "delivered"
    assert nd.mark_delivered(nid) is False  # not pending anymore
    print("OK: mark delivered")


def test_mark_failed():
    """Mark notification as failed."""
    nd = PipelineNotificationDispatcher()
    nid = nd.dispatch("Test", "msg")

    assert nd.mark_failed(nid, reason="timeout") is True
    assert nd.get_notification(nid)["status"] == "failed"
    assert nd.mark_failed(nid) is False
    print("OK: mark failed")


def test_dismiss():
    """Dismiss a notification."""
    nd = PipelineNotificationDispatcher()
    nid = nd.dispatch("Test", "msg")

    assert nd.dismiss(nid) is True
    assert nd.get_notification(nid)["status"] == "dismissed"
    assert nd.dismiss(nid) is False  # already dismissed
    print("OK: dismiss")


def test_subscribe():
    """Subscribe and retrieve subscription."""
    nd = PipelineNotificationDispatcher()
    sid = nd.subscribe("agent-1", channel="slack",
                       severity_filter="warning",
                       source_filter="ci",
                       tag_filter="build")
    assert sid.startswith("sub-")

    s = nd.get_subscription(sid)
    assert s is not None
    assert s["agent"] == "agent-1"
    assert s["channel"] == "slack"
    assert s["severity_filter"] == "warning"
    assert s["source_filter"] == "ci"
    assert s["tag_filter"] == "build"
    assert s["enabled"] is True

    assert nd.unsubscribe(sid) is True
    assert nd.unsubscribe(sid) is False
    print("OK: subscribe")


def test_invalid_subscribe():
    """Invalid subscribe rejected."""
    nd = PipelineNotificationDispatcher()
    assert nd.subscribe("") == ""
    assert nd.subscribe("a", severity_filter="invalid") == ""
    print("OK: invalid subscribe")


def test_enable_disable_subscription():
    """Enable and disable subscription."""
    nd = PipelineNotificationDispatcher()
    sid = nd.subscribe("agent-1")

    assert nd.disable_subscription(sid) is True
    assert nd.get_subscription(sid)["enabled"] is False
    assert nd.disable_subscription(sid) is False

    assert nd.enable_subscription(sid) is True
    assert nd.get_subscription(sid)["enabled"] is True
    assert nd.enable_subscription(sid) is False
    print("OK: enable disable subscription")


def test_auto_recipient_from_subscription():
    """Subscribers auto-added as recipients."""
    nd = PipelineNotificationDispatcher()
    nd.subscribe("agent-1", channel="slack", severity_filter="error")

    nid = nd.dispatch("Alert", "error occurred",
                      severity="error", channel="slack")
    n = nd.get_notification(nid)
    assert "agent-1" in n["recipients"]
    print("OK: auto recipient from subscription")


def test_subscription_severity_filter():
    """Subscription severity filter works."""
    nd = PipelineNotificationDispatcher()
    nd.subscribe("agent-1", severity_filter="warning")

    # info is below warning, should not include agent-1
    nid1 = nd.dispatch("Info", "just info", severity="info")
    assert "agent-1" not in nd.get_notification(nid1)["recipients"]

    # warning meets threshold
    nid2 = nd.dispatch("Warn", "warning!", severity="warning")
    assert "agent-1" in nd.get_notification(nid2)["recipients"]

    # error is above warning
    nid3 = nd.dispatch("Err", "error!", severity="error")
    assert "agent-1" in nd.get_notification(nid3)["recipients"]
    print("OK: subscription severity filter")


def test_subscription_source_filter():
    """Subscription source filter works."""
    nd = PipelineNotificationDispatcher()
    nd.subscribe("agent-1", source_filter="ci")

    nid1 = nd.dispatch("T", "m", source="ci")
    assert "agent-1" in nd.get_notification(nid1)["recipients"]

    nid2 = nd.dispatch("T", "m", source="cd")
    assert "agent-1" not in nd.get_notification(nid2)["recipients"]
    print("OK: subscription source filter")


def test_subscription_tag_filter():
    """Subscription tag filter works."""
    nd = PipelineNotificationDispatcher()
    nd.subscribe("agent-1", tag_filter="deploy")

    nid1 = nd.dispatch("T", "m", tags=["deploy", "prod"])
    assert "agent-1" in nd.get_notification(nid1)["recipients"]

    nid2 = nd.dispatch("T", "m", tags=["build"])
    assert "agent-1" not in nd.get_notification(nid2)["recipients"]
    print("OK: subscription tag filter")


def test_subscription_channel_filter():
    """Subscription channel filter works."""
    nd = PipelineNotificationDispatcher()
    nd.subscribe("agent-1", channel="email")

    nid1 = nd.dispatch("T", "m", channel="email")
    assert "agent-1" in nd.get_notification(nid1)["recipients"]

    nid2 = nd.dispatch("T", "m", channel="slack")
    assert "agent-1" not in nd.get_notification(nid2)["recipients"]
    print("OK: subscription channel filter")


def test_disabled_subscription_no_route():
    """Disabled subscription doesn't route."""
    nd = PipelineNotificationDispatcher()
    sid = nd.subscribe("agent-1")
    nd.disable_subscription(sid)

    nid = nd.dispatch("T", "m")
    assert "agent-1" not in nd.get_notification(nid)["recipients"]
    print("OK: disabled subscription no route")


def test_search_notifications():
    """Search notifications with filters."""
    nd = PipelineNotificationDispatcher()
    nd.dispatch("A", "m1", severity="info", channel="slack", source="ci",
                tags=["build"])
    nd.dispatch("B", "m2", severity="error", channel="email", source="cd")
    n3 = nd.dispatch("C", "m3", severity="info", channel="slack")
    nd.mark_delivered(n3)

    by_sev = nd.search_notifications(severity="error")
    assert len(by_sev) == 1

    by_chan = nd.search_notifications(channel="slack")
    assert len(by_chan) == 2

    by_status = nd.search_notifications(status="delivered")
    assert len(by_status) == 1

    by_source = nd.search_notifications(source="ci")
    assert len(by_source) == 1

    by_tag = nd.search_notifications(tag="build")
    assert len(by_tag) == 1
    print("OK: search notifications")


def test_search_limit():
    """Search respects limit."""
    nd = PipelineNotificationDispatcher()
    for i in range(20):
        nd.dispatch(f"T{i}", f"m{i}")

    results = nd.search_notifications(limit=5)
    assert len(results) == 5
    print("OK: search limit")


def test_get_agent_notifications():
    """Get notifications for agent."""
    nd = PipelineNotificationDispatcher()
    nd.dispatch("A", "m1", recipients=["alice"])
    nd.dispatch("B", "m2", recipients=["bob"])
    n3 = nd.dispatch("C", "m3", recipients=["alice"])
    nd.mark_delivered(n3)

    alice_all = nd.get_agent_notifications("alice")
    assert len(alice_all) == 2

    alice_unread = nd.get_agent_notifications("alice", unread_only=True)
    assert len(alice_unread) == 1
    print("OK: get agent notifications")


def test_severity_counts():
    """Get severity counts."""
    nd = PipelineNotificationDispatcher()
    nd.dispatch("A", "m", severity="info")
    nd.dispatch("B", "m", severity="info")
    nd.dispatch("C", "m", severity="error")
    nd.dispatch("D", "m", severity="critical")

    counts = nd.get_severity_counts()
    assert counts["info"] == 2
    assert counts["error"] == 1
    assert counts["critical"] == 1
    assert counts["debug"] == 0
    assert counts["warning"] == 0
    print("OK: severity counts")


def test_list_subscriptions():
    """List subscriptions with filters."""
    nd = PipelineNotificationDispatcher()
    s1 = nd.subscribe("alice", channel="slack")
    s2 = nd.subscribe("bob", channel="email")
    nd.disable_subscription(s2)

    all_s = nd.list_subscriptions()
    assert len(all_s) == 2

    by_agent = nd.list_subscriptions(agent="alice")
    assert len(by_agent) == 1

    enabled = nd.list_subscriptions(enabled_only=True)
    assert len(enabled) == 1
    print("OK: list subscriptions")


def test_notification_callback():
    """Callback fires on dispatch."""
    nd = PipelineNotificationDispatcher()
    fired = []
    nd.on_change("mon", lambda a, d: fired.append(a))

    nd.dispatch("T", "m")
    assert "notification_dispatched" in fired
    print("OK: notification callback")


def test_callbacks():
    """Callback registration."""
    nd = PipelineNotificationDispatcher()
    assert nd.on_change("mon", lambda a, d: None) is True
    assert nd.on_change("mon", lambda a, d: None) is False
    assert nd.remove_callback("mon") is True
    assert nd.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    nd = PipelineNotificationDispatcher()
    n1 = nd.dispatch("A", "m")
    n2 = nd.dispatch("B", "m")
    n3 = nd.dispatch("C", "m")
    nd.mark_delivered(n1)
    nd.mark_failed(n2)
    nd.dismiss(n3)
    nd.subscribe("alice")

    stats = nd.get_stats()
    assert stats["total_dispatched"] == 3
    assert stats["total_delivered"] == 1
    assert stats["total_failed"] == 1
    assert stats["total_dismissed"] == 1
    assert stats["current_notifications"] == 3
    assert stats["pending_notifications"] == 0
    assert stats["current_subscriptions"] == 1
    assert stats["active_subscriptions"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    nd = PipelineNotificationDispatcher()
    nd.dispatch("T", "m")
    nd.subscribe("alice")

    nd.reset()
    assert nd.search_notifications() == []
    assert nd.list_subscriptions() == []
    stats = nd.get_stats()
    assert stats["current_notifications"] == 0
    print("OK: reset")


def test_max_subscriptions():
    """Max subscriptions enforced."""
    nd = PipelineNotificationDispatcher(max_subscriptions=2)
    nd.subscribe("a")
    nd.subscribe("b")
    assert nd.subscribe("c") == ""
    print("OK: max subscriptions")


def main():
    print("=== Pipeline Notification Dispatcher Tests ===\n")
    test_dispatch()
    test_invalid_dispatch()
    test_mark_delivered()
    test_mark_failed()
    test_dismiss()
    test_subscribe()
    test_invalid_subscribe()
    test_enable_disable_subscription()
    test_auto_recipient_from_subscription()
    test_subscription_severity_filter()
    test_subscription_source_filter()
    test_subscription_tag_filter()
    test_subscription_channel_filter()
    test_disabled_subscription_no_route()
    test_search_notifications()
    test_search_limit()
    test_get_agent_notifications()
    test_severity_counts()
    test_list_subscriptions()
    test_notification_callback()
    test_callbacks()
    test_stats()
    test_reset()
    test_max_subscriptions()
    print("\n=== ALL 24 TESTS PASSED ===")


if __name__ == "__main__":
    main()
