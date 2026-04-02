"""Test pipeline webhook store -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_webhook_store import PipelineWebhookStore


def test_register_webhook():
    ws = PipelineWebhookStore()
    wid = ws.register_webhook("deploy", "https://hooks.example.com/deploy", events=["start", "complete"], tags=["ci"])
    assert len(wid) > 0
    w = ws.get_webhook(wid)
    assert w is not None
    assert w["url"] == "https://hooks.example.com/deploy"
    print("OK: register webhook")


def test_enable_disable():
    ws = PipelineWebhookStore()
    wid = ws.register_webhook("deploy", "https://hooks.example.com/deploy")
    assert ws.disable_webhook(wid) is True
    w = ws.get_webhook(wid)
    assert w["enabled"] is False
    assert ws.enable_webhook(wid) is True
    w = ws.get_webhook(wid)
    assert w["enabled"] is True
    print("OK: enable/disable")


def test_get_webhooks_for_event():
    ws = PipelineWebhookStore()
    ws.register_webhook("deploy", "https://a.com", events=["start", "complete"])
    ws.register_webhook("deploy", "https://b.com", events=["complete"])
    wid3 = ws.register_webhook("deploy", "https://c.com", events=["start"])
    ws.disable_webhook(wid3)
    hooks = ws.get_webhooks_for_event("deploy", "start")
    assert len(hooks) == 1  # only first one (c is disabled)
    hooks2 = ws.get_webhooks_for_event("deploy", "complete")
    assert len(hooks2) == 2
    print("OK: get webhooks for event")


def test_list_webhooks():
    ws = PipelineWebhookStore()
    ws.register_webhook("deploy", "https://a.com")
    ws.register_webhook("test", "https://b.com")
    all_w = ws.list_webhooks()
    assert len(all_w) == 2
    deploy_w = ws.list_webhooks(pipeline_name="deploy")
    assert len(deploy_w) == 1
    print("OK: list webhooks")


def test_remove_webhook():
    ws = PipelineWebhookStore()
    wid = ws.register_webhook("deploy", "https://a.com")
    assert ws.remove_webhook(wid) is True
    assert ws.remove_webhook(wid) is False
    print("OK: remove webhook")


def test_fire_event():
    ws = PipelineWebhookStore()
    ws.register_webhook("deploy", "https://a.com", events=["start", "complete"])
    ws.register_webhook("deploy", "https://b.com", events=["complete"])
    count = ws.fire_event("deploy", "complete", payload={"status": "ok"})
    assert count == 2
    print("OK: fire event")


def test_callbacks():
    ws = PipelineWebhookStore()
    fired = []
    ws.on_change("mon", lambda a, d: fired.append(a))
    ws.register_webhook("deploy", "https://a.com")
    assert len(fired) >= 1
    assert ws.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    ws = PipelineWebhookStore()
    ws.register_webhook("deploy", "https://a.com")
    stats = ws.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    ws = PipelineWebhookStore()
    ws.register_webhook("deploy", "https://a.com")
    ws.reset()
    assert ws.list_webhooks() == []
    print("OK: reset")


def main():
    print("=== Pipeline Webhook Store Tests ===\n")
    test_register_webhook()
    test_enable_disable()
    test_get_webhooks_for_event()
    test_list_webhooks()
    test_remove_webhook()
    test_fire_event()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 9 TESTS PASSED ===")


if __name__ == "__main__":
    main()
