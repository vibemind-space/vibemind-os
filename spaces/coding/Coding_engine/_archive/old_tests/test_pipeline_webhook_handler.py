"""Test pipeline webhook handler."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_webhook_handler import PipelineWebhookHandler


def test_register_webhook():
    """Register and retrieve webhook."""
    wh = PipelineWebhookHandler()
    wid = wh.register_webhook("deploy_hook", "https://example.com/hook",
                               events=["deploy", "rollback"],
                               secret="s3cret", max_retries=5,
                               tags=["prod"])
    assert wid.startswith("wh-")

    w = wh.get_webhook(wid)
    assert w is not None
    assert w["name"] == "deploy_hook"
    assert w["url"] == "https://example.com/hook"
    assert w["status"] == "active"
    assert w["events"] == ["deploy", "rollback"]
    assert w["max_retries"] == 5

    assert wh.remove_webhook(wid) is True
    assert wh.remove_webhook(wid) is False
    print("OK: register webhook")


def test_invalid_webhook():
    """Invalid webhook rejected."""
    wh = PipelineWebhookHandler()
    assert wh.register_webhook("", "http://x") == ""
    assert wh.register_webhook("a", "") == ""
    print("OK: invalid webhook")


def test_duplicate_name():
    """Duplicate name rejected."""
    wh = PipelineWebhookHandler()
    wh.register_webhook("hook", "http://a")
    assert wh.register_webhook("hook", "http://b") == ""
    print("OK: duplicate name")


def test_max_webhooks():
    """Max webhooks enforced."""
    wh = PipelineWebhookHandler(max_webhooks=2)
    wh.register_webhook("a", "http://a")
    wh.register_webhook("b", "http://b")
    assert wh.register_webhook("c", "http://c") == ""
    print("OK: max webhooks")


def test_disable_enable():
    """Disable and enable webhook."""
    wh = PipelineWebhookHandler()
    wid = wh.register_webhook("hook", "http://x")

    assert wh.disable_webhook(wid) is True
    assert wh.get_webhook(wid)["status"] == "disabled"
    assert wh.disable_webhook(wid) is False

    assert wh.enable_webhook(wid) is True
    assert wh.get_webhook(wid)["status"] == "active"
    assert wh.enable_webhook(wid) is False
    print("OK: disable enable")


def test_update_webhook():
    """Update webhook properties."""
    wh = PipelineWebhookHandler()
    wid = wh.register_webhook("hook", "http://old")

    assert wh.update_webhook(wid, url="http://new", events=["test"],
                              max_retries=10) is True
    w = wh.get_webhook(wid)
    assert w["url"] == "http://new"
    assert w["events"] == ["test"]
    assert w["max_retries"] == 10
    print("OK: update webhook")


def test_get_by_name():
    """Get webhook by name."""
    wh = PipelineWebhookHandler()
    wh.register_webhook("my_hook", "http://x")

    w = wh.get_webhook_by_name("my_hook")
    assert w is not None
    assert w["name"] == "my_hook"
    assert wh.get_webhook_by_name("nonexistent") is None
    print("OK: get by name")


def test_list_webhooks():
    """List webhooks with filters."""
    wh = PipelineWebhookHandler()
    wh.register_webhook("a", "http://a", tags=["prod"])
    wid2 = wh.register_webhook("b", "http://b")
    wh.disable_webhook(wid2)

    all_w = wh.list_webhooks()
    assert len(all_w) == 2

    by_status = wh.list_webhooks(status="disabled")
    assert len(by_status) == 1

    by_tag = wh.list_webhooks(tag="prod")
    assert len(by_tag) == 1
    print("OK: list webhooks")


def test_create_delivery():
    """Create a delivery."""
    wh = PipelineWebhookHandler()
    wid = wh.register_webhook("hook", "http://x")

    did = wh.create_delivery(wid, "deploy", payload_summary="v1.0")
    assert did.startswith("dlv-")

    d = wh.get_delivery(did)
    assert d is not None
    assert d["webhook_id"] == wid
    assert d["event_type"] == "deploy"
    assert d["status"] == "pending"
    assert d["attempts"] == 0
    print("OK: create delivery")


def test_event_filter():
    """Delivery blocked when event not in webhook filter."""
    wh = PipelineWebhookHandler()
    wid = wh.register_webhook("hook", "http://x", events=["deploy"])

    assert wh.create_delivery(wid, "build") == ""  # not in events
    assert wh.create_delivery(wid, "deploy") != ""  # in events
    print("OK: event filter")


def test_disabled_webhook_no_delivery():
    """Disabled webhook blocks delivery."""
    wh = PipelineWebhookHandler()
    wid = wh.register_webhook("hook", "http://x")
    wh.disable_webhook(wid)

    assert wh.create_delivery(wid, "test") == ""
    print("OK: disabled webhook no delivery")


def test_record_attempt_success():
    """Record successful delivery attempt."""
    wh = PipelineWebhookHandler()
    wid = wh.register_webhook("hook", "http://x")
    did = wh.create_delivery(wid, "deploy")

    assert wh.record_attempt(did, True, status_code=200) is True
    d = wh.get_delivery(did)
    assert d["status"] == "success"
    assert d["attempts"] == 1
    assert d["last_status_code"] == 200
    print("OK: record attempt success")


def test_record_attempt_failure_retry():
    """Record failed attempt with retry."""
    wh = PipelineWebhookHandler()
    wid = wh.register_webhook("hook", "http://x", max_retries=3)
    did = wh.create_delivery(wid, "deploy")

    # First failure -> retrying
    assert wh.record_attempt(did, False, status_code=500, error="timeout") is True
    assert wh.get_delivery(did)["status"] == "retrying"

    # Second failure -> retrying
    assert wh.record_attempt(did, False, status_code=500) is True
    assert wh.get_delivery(did)["status"] == "retrying"

    # Third failure -> failed (max_retries=3)
    assert wh.record_attempt(did, False, status_code=500) is True
    assert wh.get_delivery(did)["status"] == "failed"

    # Can't attempt after failed
    assert wh.record_attempt(did, True) is False
    print("OK: record attempt failure retry")


def test_search_deliveries():
    """Search deliveries."""
    wh = PipelineWebhookHandler()
    wid = wh.register_webhook("hook", "http://x")
    d1 = wh.create_delivery(wid, "deploy")
    d2 = wh.create_delivery(wid, "build")
    wh.record_attempt(d1, True)

    all_d = wh.search_deliveries()
    assert len(all_d) == 2

    by_type = wh.search_deliveries(event_type="deploy")
    assert len(by_type) == 1

    by_status = wh.search_deliveries(status="success")
    assert len(by_status) == 1
    print("OK: search deliveries")


def test_webhook_delivery_stats():
    """Webhook delivery stats."""
    wh = PipelineWebhookHandler()
    wid = wh.register_webhook("hook", "http://x", max_retries=1)
    d1 = wh.create_delivery(wid, "a")
    wh.record_attempt(d1, True)
    d2 = wh.create_delivery(wid, "b")
    wh.record_attempt(d2, False)

    stats = wh.get_webhook_delivery_stats(wid)
    assert stats["total"] == 2
    assert stats["successes"] == 1
    assert stats["failures"] == 1
    assert stats["success_rate"] == 50.0
    print("OK: webhook delivery stats")


def test_broadcast_event():
    """Broadcast event to matching webhooks."""
    wh = PipelineWebhookHandler()
    wh.register_webhook("all_hook", "http://a")  # no filter -> gets all
    wh.register_webhook("deploy_hook", "http://b", events=["deploy"])
    wh.register_webhook("build_hook", "http://c", events=["build"])

    dids = wh.broadcast_event("deploy", "v1.0")
    assert len(dids) == 2  # all_hook + deploy_hook
    print("OK: broadcast event")


def test_remove_cascades():
    """Remove webhook removes deliveries."""
    wh = PipelineWebhookHandler()
    wid = wh.register_webhook("hook", "http://x")
    wh.create_delivery(wid, "test")

    wh.remove_webhook(wid)
    assert wh.search_deliveries(webhook_id=wid) == []
    print("OK: remove cascades")


def test_callback():
    """Callback fires on events."""
    wh = PipelineWebhookHandler()
    fired = []
    wh.on_change("mon", lambda a, d: fired.append(a))

    wid = wh.register_webhook("hook", "http://x")
    assert "webhook_registered" in fired

    did = wh.create_delivery(wid, "test")
    assert "delivery_created" in fired

    wh.record_attempt(did, True)
    assert "delivery_succeeded" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    wh = PipelineWebhookHandler()
    assert wh.on_change("mon", lambda a, d: None) is True
    assert wh.on_change("mon", lambda a, d: None) is False
    assert wh.remove_callback("mon") is True
    assert wh.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    wh = PipelineWebhookHandler()
    wid = wh.register_webhook("hook", "http://x", max_retries=1)
    d1 = wh.create_delivery(wid, "a")
    wh.record_attempt(d1, True)
    d2 = wh.create_delivery(wid, "b")
    wh.record_attempt(d2, False)

    stats = wh.get_stats()
    assert stats["total_webhooks_created"] == 1
    assert stats["total_deliveries"] == 2
    assert stats["total_successes"] == 1
    assert stats["total_failures"] == 1
    assert stats["current_webhooks"] == 1
    assert stats["active_webhooks"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    wh = PipelineWebhookHandler()
    wid = wh.register_webhook("hook", "http://x")
    wh.create_delivery(wid, "test")

    wh.reset()
    assert wh.list_webhooks() == []
    assert wh.search_deliveries() == []
    stats = wh.get_stats()
    assert stats["current_webhooks"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Webhook Handler Tests ===\n")
    test_register_webhook()
    test_invalid_webhook()
    test_duplicate_name()
    test_max_webhooks()
    test_disable_enable()
    test_update_webhook()
    test_get_by_name()
    test_list_webhooks()
    test_create_delivery()
    test_event_filter()
    test_disabled_webhook_no_delivery()
    test_record_attempt_success()
    test_record_attempt_failure_retry()
    test_search_deliveries()
    test_webhook_delivery_stats()
    test_broadcast_event()
    test_remove_cascades()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 21 TESTS PASSED ===")


if __name__ == "__main__":
    main()
