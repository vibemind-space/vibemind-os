"""Test agent notification preferences -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_notification_preferences import AgentNotificationPreferences


def test_subscribe():
    np = AgentNotificationPreferences()
    sid = np.subscribe("agent-1", "email", notification_type="alert")
    assert len(sid) > 0
    assert sid.startswith("anp-")
    assert np.is_subscribed("agent-1", "email", notification_type="alert") is True
    print("OK: subscribe")


def test_subscribe_duplicate():
    np = AgentNotificationPreferences()
    np.subscribe("agent-1", "email", notification_type="alert")
    dup = np.subscribe("agent-1", "email", notification_type="alert")
    assert dup == ""
    print("OK: subscribe duplicate")


def test_unsubscribe():
    np = AgentNotificationPreferences()
    np.subscribe("agent-1", "email")
    assert np.unsubscribe("agent-1", "email") is True
    assert np.unsubscribe("agent-1", "email") is False
    print("OK: unsubscribe")


def test_get_subscriptions():
    np = AgentNotificationPreferences()
    np.subscribe("agent-1", "email")
    np.subscribe("agent-1", "slack")
    subs = np.get_subscriptions("agent-1")
    assert len(subs) == 2
    print("OK: get subscriptions")


def test_get_subscribers():
    np = AgentNotificationPreferences()
    np.subscribe("agent-1", "email")
    np.subscribe("agent-2", "email")
    np.subscribe("agent-3", "slack")
    subs = np.get_subscribers("email")
    assert len(subs) == 2
    print("OK: get subscribers")


def test_quiet_hours():
    np = AgentNotificationPreferences()
    assert np.set_quiet_hours("agent-1", 22, 6) is True
    qh = np.get_quiet_hours("agent-1")
    assert qh is not None
    assert qh["start_hour"] == 22
    assert qh["end_hour"] == 6
    assert np.get_quiet_hours("nonexistent") is None
    print("OK: quiet hours")


def test_clear_subscriptions():
    np = AgentNotificationPreferences()
    np.subscribe("agent-1", "email")
    np.subscribe("agent-1", "slack")
    count = np.clear_subscriptions("agent-1")
    assert count == 2
    assert np.get_subscriptions("agent-1") == []
    print("OK: clear subscriptions")


def test_list_channels():
    np = AgentNotificationPreferences()
    np.subscribe("agent-1", "email")
    np.subscribe("agent-2", "slack")
    channels = np.list_channels()
    assert "email" in channels
    assert "slack" in channels
    print("OK: list channels")


def test_callbacks():
    np = AgentNotificationPreferences()
    fired = []
    np.on_change("mon", lambda a, d: fired.append(a))
    np.subscribe("agent-1", "email")
    assert len(fired) >= 1
    assert np.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    np = AgentNotificationPreferences()
    np.subscribe("agent-1", "email")
    stats = np.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    np = AgentNotificationPreferences()
    np.subscribe("agent-1", "email")
    np.reset()
    assert np.get_subscriptions("agent-1") == []
    print("OK: reset")


def main():
    print("=== Agent Notification Preferences Tests ===\n")
    test_subscribe()
    test_subscribe_duplicate()
    test_unsubscribe()
    test_get_subscriptions()
    test_get_subscribers()
    test_quiet_hours()
    test_clear_subscriptions()
    test_list_channels()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
