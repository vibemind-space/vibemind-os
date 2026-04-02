"""Test agent profile store -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_profile_store import AgentProfileStore


def test_create_profile():
    ps = AgentProfileStore()
    pid = ps.create_profile("agent-1", display_name="Worker One", role="developer", metadata={"team": "alpha"})
    assert len(pid) > 0
    assert pid.startswith("apr-")
    p = ps.get_profile("agent-1")
    assert p is not None
    assert p["display_name"] == "Worker One"
    assert p["role"] == "developer"
    print("OK: create profile")


def test_create_duplicate():
    ps = AgentProfileStore()
    ps.create_profile("agent-1", display_name="A1")
    dup = ps.create_profile("agent-1", display_name="A1 again")
    assert dup == ""
    print("OK: create duplicate")


def test_update_profile():
    ps = AgentProfileStore()
    ps.create_profile("agent-1", display_name="Old Name", role="junior")
    assert ps.update_profile("agent-1", display_name="New Name", role="senior") is True
    p = ps.get_profile("agent-1")
    assert p["display_name"] == "New Name"
    assert p["role"] == "senior"
    assert ps.update_profile("nonexistent", display_name="X") is False
    print("OK: update profile")


def test_delete_profile():
    ps = AgentProfileStore()
    ps.create_profile("agent-1")
    assert ps.delete_profile("agent-1") is True
    assert ps.delete_profile("agent-1") is False
    print("OK: delete profile")


def test_list_profiles():
    ps = AgentProfileStore()
    ps.create_profile("a1", role="dev")
    ps.create_profile("a2", role="ops")
    ps.create_profile("a3", role="dev")
    all_p = ps.list_profiles()
    assert len(all_p) == 3
    devs = ps.list_profiles(role="dev")
    assert len(devs) == 2
    print("OK: list profiles")


def test_preferences():
    ps = AgentProfileStore()
    ps.create_profile("agent-1")
    assert ps.set_preference("agent-1", "theme", "dark") is True
    assert ps.get_preference("agent-1", "theme") == "dark"
    assert ps.get_preference("agent-1", "missing", default="light") == "light"
    assert ps.set_preference("nonexistent", "k", "v") is False
    print("OK: preferences")


def test_search_profiles():
    ps = AgentProfileStore()
    ps.create_profile("alpha-worker", display_name="Alpha Worker")
    ps.create_profile("beta-tester", display_name="Beta Tester")
    results = ps.search_profiles("alpha")
    assert len(results) >= 1
    print("OK: search profiles")


def test_get_profiles_by_role():
    ps = AgentProfileStore()
    ps.create_profile("a1", role="engineer")
    ps.create_profile("a2", role="engineer")
    ps.create_profile("a3", role="manager")
    engineers = ps.get_profiles_by_role("engineer")
    assert len(engineers) == 2
    print("OK: get profiles by role")


def test_callbacks():
    ps = AgentProfileStore()
    fired = []
    ps.on_change("mon", lambda a, d: fired.append(a))
    ps.create_profile("agent-1")
    assert len(fired) >= 1
    assert ps.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    ps = AgentProfileStore()
    ps.create_profile("agent-1")
    stats = ps.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    ps = AgentProfileStore()
    ps.create_profile("agent-1")
    ps.reset()
    assert ps.list_profiles() == []
    print("OK: reset")


def main():
    print("=== Agent Profile Store Tests ===\n")
    test_create_profile()
    test_create_duplicate()
    test_update_profile()
    test_delete_profile()
    test_list_profiles()
    test_preferences()
    test_search_profiles()
    test_get_profiles_by_role()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
