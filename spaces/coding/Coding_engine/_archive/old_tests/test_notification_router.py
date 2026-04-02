"""Test notification router."""
import sys
import time
sys.path.insert(0, ".")

from src.services.notification_router import NotificationRouter, Severity


def test_add_channel():
    """Add a notification channel."""
    router = NotificationRouter()
    assert router.add_channel("slack", "slack") is True
    assert router.add_channel("slack", "slack") is False  # Duplicate

    ch = router.get_channel("slack")
    assert ch is not None
    assert ch["name"] == "slack"
    assert ch["channel_type"] == "slack"
    assert ch["enabled"] is True
    print("OK: add channel")


def test_remove_channel():
    """Remove a channel and its subscriptions."""
    router = NotificationRouter()
    router.add_channel("temp", "log")
    router.subscribe("temp")

    assert router.remove_channel("temp") is True
    assert router.get_channel("temp") is None
    assert router.list_subscriptions() == []
    assert router.remove_channel("temp") is False
    print("OK: remove channel")


def test_enable_disable_channel():
    """Enable and disable channels."""
    router = NotificationRouter()
    router.add_channel("ch", "log")
    assert router.disable_channel("ch") is True
    assert router.get_channel("ch")["enabled"] is False
    assert router.enable_channel("ch") is True
    assert router.get_channel("ch")["enabled"] is True
    print("OK: enable disable channel")


def test_list_channels():
    """List channels."""
    router = NotificationRouter()
    router.add_channel("alpha", "slack")
    router.add_channel("beta", "email")
    channels = router.list_channels()
    assert len(channels) == 2
    assert channels[0]["name"] == "alpha"
    print("OK: list channels")


def test_subscribe():
    """Create subscriptions."""
    router = NotificationRouter()
    router.add_channel("slack", "slack")
    sid = router.subscribe("slack", min_severity="warning", sources={"Builder"})
    assert sid is not None
    assert sid.startswith("sub-")

    # Can't subscribe to nonexistent channel
    assert router.subscribe("nonexistent") is None

    sub = router.get_subscription(sid)
    assert sub is not None
    assert sub["channel_name"] == "slack"
    assert sub["min_severity"] == "warning"
    print("OK: subscribe")


def test_unsubscribe():
    """Unsubscribe."""
    router = NotificationRouter()
    router.add_channel("ch", "log")
    sid = router.subscribe("ch")
    assert router.unsubscribe(sid) is True
    assert router.unsubscribe(sid) is False
    print("OK: unsubscribe")


def test_list_subscriptions():
    """List subscriptions."""
    router = NotificationRouter()
    router.add_channel("ch1", "log")
    router.add_channel("ch2", "log")
    router.subscribe("ch1")
    router.subscribe("ch2")
    router.subscribe("ch1", min_severity="error")

    all_subs = router.list_subscriptions()
    assert len(all_subs) == 3

    ch1_subs = router.list_subscriptions(channel_name="ch1")
    assert len(ch1_subs) == 2
    print("OK: list subscriptions")


def test_basic_notify():
    """Send a notification to matching channels."""
    delivered = []
    router = NotificationRouter()
    router.add_channel("log", "log", handler=lambda n: delivered.append(n["title"]))
    router.subscribe("log")

    nid = router.notify("Build done", "All tests passed", severity="info", source="Builder")
    assert nid.startswith("notif-")
    assert delivered == ["Build done"]
    print("OK: basic notify")


def test_notify_severity_filter():
    """Subscriptions filter by severity."""
    delivered = []
    router = NotificationRouter()
    router.add_channel("errors", "log", handler=lambda n: delivered.append(n["severity"]))
    router.subscribe("errors", min_severity="error")

    router.notify("Info msg", "test", severity="info")
    assert delivered == []  # Below threshold

    router.notify("Error msg", "test", severity="error")
    assert delivered == ["error"]
    print("OK: notify severity filter")


def test_notify_source_filter():
    """Subscriptions filter by source."""
    delivered = []
    router = NotificationRouter()
    router.add_channel("ch", "log", handler=lambda n: delivered.append(n["source"]))
    router.subscribe("ch", sources={"Builder"})

    router.notify("Msg", "test", source="Tester")
    assert delivered == []

    router.notify("Msg", "test", source="Builder")
    assert delivered == ["Builder"]
    print("OK: notify source filter")


def test_notify_tag_filter():
    """Subscriptions filter by tags."""
    delivered = []
    router = NotificationRouter()
    router.add_channel("ch", "log", handler=lambda n: delivered.append(n["title"]))
    router.subscribe("ch", tags={"critical"})

    router.notify("Normal", "test", tags={"info"})
    assert delivered == []

    router.notify("Critical", "test", tags={"critical", "urgent"})
    assert delivered == ["Critical"]
    print("OK: notify tag filter")


def test_notify_handler_failure():
    """Failed handler records failure."""
    router = NotificationRouter()
    router.add_channel("bad", "log", handler=lambda n: 1 / 0)
    router.subscribe("bad")

    nid = router.notify("Test", "msg")
    history = router.get_history()
    assert len(history) == 1
    assert history[0]["deliveries"][0]["status"] == "failed"
    print("OK: notify handler failure")


def test_notify_disabled_channel():
    """Disabled channels don't receive notifications."""
    delivered = []
    router = NotificationRouter()
    router.add_channel("ch", "log", handler=lambda n: delivered.append(1))
    router.subscribe("ch")
    router.disable_channel("ch")

    router.notify("Test", "msg")
    assert delivered == []
    print("OK: notify disabled channel")


def test_rate_limit():
    """Rate-limited channels suppress rapid notifications."""
    delivered = []
    router = NotificationRouter()
    router.add_channel("ch", "log", handler=lambda n: delivered.append(1), rate_limit=1.0)
    router.subscribe("ch")

    router.notify("First", "msg")
    assert len(delivered) == 1

    router.notify("Second", "msg")  # Should be suppressed
    assert len(delivered) == 1

    history = router.get_history()
    suppressed = [h for h in history if any(
        d.get("status") == "suppressed" for d in h["deliveries"])]
    assert len(suppressed) == 1
    print("OK: rate limit")


def test_dedup():
    """Deduplicate identical notifications."""
    delivered = []
    router = NotificationRouter(dedup_window=5.0)
    router.add_channel("ch", "log", handler=lambda n: delivered.append(1))
    router.subscribe("ch")

    router.notify("Test", "msg", dedup_key="build-123")
    assert len(delivered) == 1

    router.notify("Test", "msg", dedup_key="build-123")
    assert len(delivered) == 1  # Deduplicated

    router.notify("Test", "msg", dedup_key="build-456")
    assert len(delivered) == 2  # Different key
    print("OK: dedup")


def test_escalation_chain():
    """Escalation chain delivers to multiple channels."""
    delivered = []
    router = NotificationRouter()
    router.add_channel("team", "slack", handler=lambda n: delivered.append("team"))
    router.add_channel("manager", "email", handler=lambda n: delivered.append("manager"))
    router.add_channel("oncall", "whatsapp", handler=lambda n: delivered.append("oncall"))

    router.define_escalation("critical_chain", [
        ("team", 0),
        ("manager", 300),
        ("oncall", 600),
    ])

    results = router.notify_escalation("critical_chain", "Outage", "System down")
    assert len(results) == 3
    assert delivered == ["team", "manager", "oncall"]
    assert results[0]["channel"] == "team"
    assert results[1]["delay"] == 300
    print("OK: escalation chain")


def test_escalation_chain_missing():
    """Missing escalation chain returns empty."""
    router = NotificationRouter()
    results = router.notify_escalation("nonexistent", "Test", "msg")
    assert results == []
    print("OK: escalation chain missing")


def test_list_escalation_chains():
    """List escalation chains."""
    router = NotificationRouter()
    router.define_escalation("chain_a", [("ch", 0)])
    router.define_escalation("chain_b", [("ch", 0)])
    chains = router.list_escalation_chains()
    assert chains == ["chain_a", "chain_b"]
    print("OK: list escalation chains")


def test_get_history():
    """Get notification history with filters."""
    router = NotificationRouter()
    router.add_channel("ch", "log")
    router.subscribe("ch")

    router.notify("Info", "msg", severity="info", source="A")
    router.notify("Error", "msg", severity="error", source="B")
    router.notify("Warning", "msg", severity="warning", source="A")

    all_h = router.get_history()
    assert len(all_h) == 3

    errors = router.get_history(severity="error")
    assert len(errors) == 1

    from_a = router.get_history(source="A")
    assert len(from_a) == 2
    print("OK: get history")


def test_get_notification():
    """Get a specific notification."""
    router = NotificationRouter()
    router.add_channel("ch", "log")
    router.subscribe("ch")

    nid = router.notify("Test", "Hello", data={"key": "val"})
    notif = router.get_notification(nid)
    assert notif is not None
    assert notif["title"] == "Test"
    assert notif["data"]["key"] == "val"

    assert router.get_notification("notif-nonexistent") is None
    print("OK: get notification")


def test_multi_channel_delivery():
    """Notification delivered to multiple matching channels."""
    d1, d2 = [], []
    router = NotificationRouter()
    router.add_channel("ch1", "log", handler=lambda n: d1.append(1))
    router.add_channel("ch2", "log", handler=lambda n: d2.append(1))
    router.subscribe("ch1")
    router.subscribe("ch2")

    router.notify("Test", "msg")
    assert len(d1) == 1
    assert len(d2) == 1
    print("OK: multi channel delivery")


def test_stats():
    """Stats are accurate."""
    router = NotificationRouter()
    router.add_channel("ok", "log", handler=lambda n: True)
    router.add_channel("fail", "log", handler=lambda n: 1 / 0)
    router.subscribe("ok")
    router.subscribe("fail")

    router.notify("Test", "msg")

    stats = router.get_stats()
    assert stats["total_notifications"] == 1
    assert stats["total_sent"] == 1
    assert stats["total_failed"] == 1
    assert stats["total_channels"] == 2
    assert stats["total_subscriptions"] == 2
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    router = NotificationRouter()
    router.add_channel("ch", "log")
    router.subscribe("ch")
    router.notify("Test", "msg")

    router.reset()
    assert router.list_channels() == []
    assert router.list_subscriptions() == []
    assert router.get_history() == []
    stats = router.get_stats()
    assert stats["total_channels"] == 0
    print("OK: reset")


def test_history_pruning():
    """History is pruned when over limit."""
    router = NotificationRouter(max_history=5)
    router.add_channel("ch", "log")
    router.subscribe("ch")

    for i in range(10):
        router.notify(f"Msg {i}", "body")

    history = router.get_history(limit=100)
    assert len(history) <= 5
    print("OK: history pruning")


def main():
    print("=== Notification Router Tests ===\n")
    test_add_channel()
    test_remove_channel()
    test_enable_disable_channel()
    test_list_channels()
    test_subscribe()
    test_unsubscribe()
    test_list_subscriptions()
    test_basic_notify()
    test_notify_severity_filter()
    test_notify_source_filter()
    test_notify_tag_filter()
    test_notify_handler_failure()
    test_notify_disabled_channel()
    test_rate_limit()
    test_dedup()
    test_escalation_chain()
    test_escalation_chain_missing()
    test_list_escalation_chains()
    test_get_history()
    test_get_notification()
    test_multi_channel_delivery()
    test_stats()
    test_reset()
    test_history_pruning()
    print("\n=== ALL 24 TESTS PASSED ===")


if __name__ == "__main__":
    main()
