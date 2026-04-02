"""Test pipeline notification store -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_notification_store import PipelineNotificationStore


def test_create_channel():
    ns = PipelineNotificationStore()
    cid = ns.create_channel("alerts", channel_type="urgent", tags=["ops"])
    assert len(cid) > 0
    assert ns.create_channel("alerts") == ""  # dup
    print("OK: create channel")


def test_send():
    ns = PipelineNotificationStore()
    ns.create_channel("alerts")
    nid = ns.send("alerts", "Server is down", severity="error", data={"host": "web-1"})
    assert len(nid) > 0
    n = ns.get_notification(nid)
    assert n is not None
    assert n["message"] == "Server is down"
    print("OK: send")


def test_get_channel_messages():
    ns = PipelineNotificationStore()
    ns.create_channel("logs")
    ns.send("logs", "msg1", severity="info")
    ns.send("logs", "msg2", severity="info")
    msgs = ns.get_channel_messages("logs")
    assert len(msgs) == 2
    print("OK: get channel messages")


def test_subscribe():
    ns = PipelineNotificationStore()
    ns.create_channel("alerts")
    assert ns.subscribe("alerts", "user-1") is True
    print("OK: subscribe")


def test_unsubscribe():
    ns = PipelineNotificationStore()
    ns.create_channel("alerts")
    ns.subscribe("alerts", "user-1")
    assert ns.unsubscribe("alerts", "user-1") is True
    assert ns.unsubscribe("alerts", "user-1") is False
    print("OK: unsubscribe")


def test_list_channels():
    ns = PipelineNotificationStore()
    ns.create_channel("alerts", tags=["ops"])
    ns.create_channel("logs")
    assert len(ns.list_channels()) == 2
    assert len(ns.list_channels(tag="ops")) == 1
    print("OK: list channels")


def test_remove_channel():
    ns = PipelineNotificationStore()
    ns.create_channel("temp")
    assert ns.remove_channel("temp") is True
    assert ns.remove_channel("temp") is False
    print("OK: remove channel")


def test_callbacks():
    ns = PipelineNotificationStore()
    fired = []
    ns.on_change("mon", lambda a, d: fired.append(a))
    ns.create_channel("ch1")
    assert len(fired) >= 1
    ns.remove_callback("mon")  # returns None in this impl
    print("OK: callbacks")


def test_stats():
    ns = PipelineNotificationStore()
    ns.create_channel("ch1")
    stats = ns.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    ns = PipelineNotificationStore()
    ns.create_channel("ch1")
    ns.reset()
    assert ns.list_channels() == []
    print("OK: reset")


def main():
    print("=== Pipeline Notification Store Tests ===\n")
    test_create_channel()
    test_send()
    test_get_channel_messages()
    test_subscribe()
    test_unsubscribe()
    test_list_channels()
    test_remove_channel()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")


if __name__ == "__main__":
    main()
