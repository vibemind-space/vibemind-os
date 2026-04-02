"""Test pipeline webhook dispatcher."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_webhook_dispatcher import PipelineWebhookDispatcher


def test_register_endpoint():
    """Register and unregister endpoints."""
    d = PipelineWebhookDispatcher()
    eid = d.register_endpoint("slack", "https://hooks.slack.com/xxx")
    assert eid.startswith("wh-")

    ep = d.get_endpoint(eid)
    assert ep is not None
    assert ep["name"] == "slack"
    assert ep["url"] == "https://hooks.slack.com/xxx"
    assert ep["enabled"] is True

    assert d.unregister_endpoint(eid) is True
    assert d.unregister_endpoint(eid) is False
    print("OK: register endpoint")


def test_register_empty_url():
    """Can't register with empty URL."""
    d = PipelineWebhookDispatcher()
    assert d.register_endpoint("bad", "") == ""
    print("OK: register empty url")


def test_enable_disable():
    """Enable and disable endpoints."""
    d = PipelineWebhookDispatcher()
    eid = d.register_endpoint("test", "https://example.com")

    assert d.disable_endpoint(eid) is True
    assert d.disable_endpoint(eid) is False  # Already disabled
    assert d.get_endpoint(eid)["enabled"] is False

    assert d.enable_endpoint(eid) is True
    assert d.enable_endpoint(eid) is False
    print("OK: enable disable")


def test_update_endpoint():
    """Update endpoint settings."""
    d = PipelineWebhookDispatcher()
    eid = d.register_endpoint("test", "https://old.com")

    assert d.update_endpoint(eid, url="https://new.com", max_retries=5) is True
    ep = d.get_endpoint(eid)
    assert ep["url"] == "https://new.com"

    assert d.update_endpoint("fake") is False
    print("OK: update endpoint")


def test_event_filters():
    """Event type filtering."""
    d = PipelineWebhookDispatcher()
    eid = d.register_endpoint("test", "https://example.com")

    assert d.add_event_filter(eid, "build_complete") is True
    assert d.add_event_filter(eid, "build_complete") is False  # Duplicate
    assert "build_complete" in d.get_endpoint(eid)["events"]

    assert d.remove_event_filter(eid, "build_complete") is True
    assert d.remove_event_filter(eid, "build_complete") is False
    print("OK: event filters")


def test_dispatch_all():
    """Dispatch event to all matching endpoints."""
    d = PipelineWebhookDispatcher()
    d.register_endpoint("A", "https://a.com")
    d.register_endpoint("B", "https://b.com")

    results = d.dispatch("build_complete", {"version": "1.0"})
    assert len(results) == 2
    assert all(r["status"] == "success" for r in results)
    print("OK: dispatch all")


def test_dispatch_filtered():
    """Only matching endpoints receive events."""
    d = PipelineWebhookDispatcher()
    e1 = d.register_endpoint("builds", "https://a.com", events={"build_complete"})
    e2 = d.register_endpoint("tests", "https://b.com", events={"test_complete"})

    results = d.dispatch("build_complete", {})
    assert len(results) == 1
    assert results[0]["endpoint_id"] == e1
    print("OK: dispatch filtered")


def test_dispatch_skips_disabled():
    """Disabled endpoints are skipped."""
    d = PipelineWebhookDispatcher()
    e1 = d.register_endpoint("A", "https://a.com")
    e2 = d.register_endpoint("B", "https://b.com", enabled=False)

    results = d.dispatch("event", {})
    assert len(results) == 1
    assert results[0]["endpoint_id"] == e1
    print("OK: dispatch skips disabled")


def test_dispatch_with_handler():
    """Dispatch with custom handler."""
    d = PipelineWebhookDispatcher()
    d.register_endpoint("test", "https://example.com")

    calls = []
    def handler(url, event, payload, secret, timeout):
        calls.append((url, event))
        return True

    d.set_dispatch_handler(handler)
    d.dispatch("build_done", {"v": 1})

    assert len(calls) == 1
    assert calls[0] == ("https://example.com", "build_done")
    print("OK: dispatch with handler")


def test_dispatch_handler_failure():
    """Handler failure records as failed."""
    d = PipelineWebhookDispatcher()
    eid = d.register_endpoint("test", "https://example.com", max_retries=2)

    def failing_handler(url, event, payload, secret, timeout):
        return False

    d.set_dispatch_handler(failing_handler)
    results = d.dispatch("event", {})

    assert len(results) == 1
    assert results[0]["status"] == "failed"
    assert results[0]["attempts"] == 2  # max_retries = 2
    assert d.get_endpoint(eid)["total_failed"] == 1
    print("OK: dispatch handler failure")


def test_retry_dispatch():
    """Retry a failed dispatch."""
    d = PipelineWebhookDispatcher()
    eid = d.register_endpoint("test", "https://example.com", max_retries=1)

    attempt = [0]
    def handler(url, event, payload, secret, timeout):
        attempt[0] += 1
        return attempt[0] > 1  # Fail first, succeed on retry

    d.set_dispatch_handler(handler)
    results = d.dispatch("event", {})
    dispatch_id = results[0]["dispatch_id"]
    assert results[0]["status"] == "failed"

    assert d.retry_dispatch(dispatch_id) is True
    rec = d.get_dispatch(dispatch_id)
    assert rec["status"] == "success"
    print("OK: retry dispatch")


def test_retry_non_failed():
    """Can't retry non-failed dispatch."""
    d = PipelineWebhookDispatcher()
    d.register_endpoint("test", "https://example.com")
    results = d.dispatch("event", {})
    dispatch_id = results[0]["dispatch_id"]

    # It succeeded, can't retry
    assert d.retry_dispatch(dispatch_id) is False
    assert d.retry_dispatch("fake") is False
    print("OK: retry non failed")


def test_get_dispatch():
    """Get dispatch record."""
    d = PipelineWebhookDispatcher()
    d.register_endpoint("test", "https://example.com")
    results = d.dispatch("build_done", {"v": 1})

    rec = d.get_dispatch(results[0]["dispatch_id"])
    assert rec is not None
    assert rec["event_type"] == "build_done"
    assert rec["status"] == "success"

    assert d.get_dispatch("fake") is None
    print("OK: get dispatch")


def test_list_dispatches():
    """List dispatches with filters."""
    d = PipelineWebhookDispatcher()
    e1 = d.register_endpoint("A", "https://a.com")
    d.dispatch("build", {})
    d.dispatch("test", {})

    all_recs = d.list_dispatches()
    assert len(all_recs) == 2

    by_event = d.list_dispatches(event_type="build")
    assert len(by_event) == 1

    by_endpoint = d.list_dispatches(endpoint_id=e1)
    assert len(by_endpoint) == 2
    print("OK: list dispatches")


def test_failed_dispatches():
    """Get failed dispatches."""
    d = PipelineWebhookDispatcher()
    d.register_endpoint("test", "https://example.com", max_retries=1)
    d.set_dispatch_handler(lambda u, e, p, s, t: False)

    d.dispatch("event1", {})
    d.dispatch("event2", {})

    failed = d.get_failed_dispatches()
    assert len(failed) == 2
    print("OK: failed dispatches")


def test_list_endpoints():
    """List endpoints with filter."""
    d = PipelineWebhookDispatcher()
    d.register_endpoint("A", "https://a.com")
    d.register_endpoint("B", "https://b.com", enabled=False)

    all_eps = d.list_endpoints()
    assert len(all_eps) == 2

    enabled = d.list_endpoints(enabled_only=True)
    assert len(enabled) == 1
    print("OK: list endpoints")


def test_endpoint_stats_tracked():
    """Endpoint dispatch stats are tracked."""
    d = PipelineWebhookDispatcher()
    eid = d.register_endpoint("test", "https://example.com")

    d.dispatch("event1", {})
    d.dispatch("event2", {})

    ep = d.get_endpoint(eid)
    assert ep["total_dispatched"] == 2
    assert ep["total_succeeded"] == 2
    assert ep["last_status"] == "success"
    print("OK: endpoint stats tracked")


def test_callbacks():
    """Dispatch callbacks fire."""
    d = PipelineWebhookDispatcher()
    d.register_endpoint("test", "https://example.com")

    fired = []
    assert d.on_dispatch("mon", lambda did, eid, evt, st: fired.append((evt, st))) is True
    assert d.on_dispatch("mon", lambda d, e, ev, s: None) is False

    d.dispatch("build", {})
    assert len(fired) == 1
    assert fired[0] == ("build", "success")

    assert d.remove_callback("mon") is True
    assert d.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    d = PipelineWebhookDispatcher()
    d.register_endpoint("A", "https://a.com")
    d.register_endpoint("B", "https://b.com", enabled=False)
    d.dispatch("event", {})

    stats = d.get_stats()
    assert stats["total_endpoints"] == 2
    assert stats["total_enabled"] == 1
    assert stats["total_dispatches"] == 1
    assert stats["total_successes"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    d = PipelineWebhookDispatcher()
    d.register_endpoint("test", "https://example.com")
    d.dispatch("event", {})

    d.reset()
    assert d.list_endpoints() == []
    assert d.list_dispatches() == []
    stats = d.get_stats()
    assert stats["total_endpoints"] == 0
    assert stats["total_dispatches"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Webhook Dispatcher Tests ===\n")
    test_register_endpoint()
    test_register_empty_url()
    test_enable_disable()
    test_update_endpoint()
    test_event_filters()
    test_dispatch_all()
    test_dispatch_filtered()
    test_dispatch_skips_disabled()
    test_dispatch_with_handler()
    test_dispatch_handler_failure()
    test_retry_dispatch()
    test_retry_non_failed()
    test_get_dispatch()
    test_list_dispatches()
    test_failed_dispatches()
    test_list_endpoints()
    test_endpoint_stats_tracked()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 20 TESTS PASSED ===")


if __name__ == "__main__":
    main()
