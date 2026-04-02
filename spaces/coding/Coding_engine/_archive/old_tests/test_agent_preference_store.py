"""Test agent preference store -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_preference_store import AgentPreferenceStore


def test_set_get_preference():
    ps = AgentPreferenceStore()
    pid = ps.set_preference("agent-1", "ui", "theme", "dark")
    assert len(pid) > 0
    assert pid.startswith("ape-")
    val = ps.get_preference("agent-1", "ui", "theme")
    assert val == "dark"
    print("OK: set/get preference")


def test_get_default():
    ps = AgentPreferenceStore()
    val = ps.get_preference("agent-1", "ui", "missing", default="light")
    assert val == "light"
    print("OK: get default")


def test_update_existing():
    ps = AgentPreferenceStore()
    ps.set_preference("agent-1", "ui", "theme", "dark")
    ps.set_preference("agent-1", "ui", "theme", "light")
    val = ps.get_preference("agent-1", "ui", "theme")
    assert val == "light"
    print("OK: update existing")


def test_get_agent_preferences():
    ps = AgentPreferenceStore()
    ps.set_preference("agent-1", "ui", "theme", "dark")
    ps.set_preference("agent-1", "ui", "font", "mono")
    ps.set_preference("agent-1", "behavior", "verbose", True)
    all_p = ps.get_agent_preferences("agent-1")
    assert len(all_p) == 3
    ui_only = ps.get_agent_preferences("agent-1", category="ui")
    assert len(ui_only) == 2
    print("OK: get agent preferences")


def test_delete_preference():
    ps = AgentPreferenceStore()
    ps.set_preference("agent-1", "ui", "theme", "dark")
    assert ps.delete_preference("agent-1", "ui", "theme") is True
    assert ps.delete_preference("agent-1", "ui", "theme") is False
    print("OK: delete preference")


def test_clear_agent_preferences():
    ps = AgentPreferenceStore()
    ps.set_preference("agent-1", "ui", "theme", "dark")
    ps.set_preference("agent-1", "behavior", "verbose", True)
    count = ps.clear_agent_preferences("agent-1")
    assert count == 2
    assert ps.get_agent_preferences("agent-1") == []
    print("OK: clear agent preferences")


def test_get_all_categories():
    ps = AgentPreferenceStore()
    ps.set_preference("agent-1", "ui", "theme", "dark")
    ps.set_preference("agent-1", "behavior", "verbose", True)
    cats = ps.get_all_categories("agent-1")
    assert "ui" in cats
    assert "behavior" in cats
    print("OK: get all categories")


def test_export_import():
    ps = AgentPreferenceStore()
    ps.set_preference("agent-1", "ui", "theme", "dark")
    ps.set_preference("agent-1", "ui", "font", "mono")
    exported = ps.export_preferences("agent-1")
    assert "ui" in exported
    assert exported["ui"]["theme"] == "dark"
    # Import to new agent
    count = ps.import_preferences("agent-2", exported)
    assert count >= 2
    assert ps.get_preference("agent-2", "ui", "theme") == "dark"
    print("OK: export/import")


def test_list_agents():
    ps = AgentPreferenceStore()
    ps.set_preference("agent-1", "ui", "theme", "dark")
    ps.set_preference("agent-2", "ui", "theme", "light")
    agents = ps.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    ps = AgentPreferenceStore()
    fired = []
    ps.on_change("mon", lambda a, d: fired.append(a))
    ps.set_preference("agent-1", "ui", "theme", "dark")
    assert len(fired) >= 1
    assert ps.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    ps = AgentPreferenceStore()
    ps.set_preference("agent-1", "ui", "theme", "dark")
    stats = ps.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    ps = AgentPreferenceStore()
    ps.set_preference("agent-1", "ui", "theme", "dark")
    ps.reset()
    assert ps.list_agents() == []
    print("OK: reset")


def main():
    print("=== Agent Preference Store Tests ===\n")
    test_set_get_preference()
    test_get_default()
    test_update_existing()
    test_get_agent_preferences()
    test_delete_preference()
    test_clear_agent_preferences()
    test_get_all_categories()
    test_export_import()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 12 TESTS PASSED ===")


if __name__ == "__main__":
    main()
