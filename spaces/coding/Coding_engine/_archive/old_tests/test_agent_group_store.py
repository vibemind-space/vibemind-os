"""Test agent group store -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_group_store import AgentGroupStore


def test_create_group():
    gs = AgentGroupStore()
    gid = gs.create_group("team-alpha", description="Alpha team", max_members=10, tags=["ml"])
    assert len(gid) > 0
    assert gs.create_group("team-alpha") == ""  # dup
    print("OK: create group")


def test_get_group():
    gs = AgentGroupStore()
    gid = gs.create_group("team-alpha", description="Alpha")
    g = gs.get_group(gid)
    assert g is not None
    assert g["name"] == "team-alpha"
    print("OK: get group")


def test_add_member():
    gs = AgentGroupStore()
    gid = gs.create_group("team-alpha", max_members=3)
    assert gs.add_member(gid, "agent-1") is True
    assert gs.add_member(gid, "agent-1") is False  # already member
    assert gs.add_member(gid, "agent-2") is True
    print("OK: add member")


def test_remove_member():
    gs = AgentGroupStore()
    gid = gs.create_group("team-alpha")
    gs.add_member(gid, "agent-1")
    assert gs.remove_member(gid, "agent-1") is True
    assert gs.remove_member(gid, "agent-1") is False
    print("OK: remove member")


def test_get_members():
    gs = AgentGroupStore()
    gid = gs.create_group("team-alpha")
    gs.add_member(gid, "agent-1")
    gs.add_member(gid, "agent-2")
    members = gs.get_members(gid)
    assert "agent-1" in members
    assert "agent-2" in members
    print("OK: get members")


def test_find_groups_for_agent():
    gs = AgentGroupStore()
    gid1 = gs.create_group("team-alpha")
    gid2 = gs.create_group("team-beta")
    gs.add_member(gid1, "agent-1")
    gs.add_member(gid2, "agent-1")
    groups = gs.find_groups_for_agent("agent-1")
    assert len(groups) == 2
    print("OK: find groups for agent")


def test_list_groups():
    gs = AgentGroupStore()
    gs.create_group("team-alpha", tags=["ml"])
    gs.create_group("team-beta", tags=["ops"])
    all_g = gs.list_groups()
    assert len(all_g) == 2
    ml_g = gs.list_groups(tag="ml")
    assert len(ml_g) == 1
    print("OK: list groups")


def test_remove_group():
    gs = AgentGroupStore()
    gid = gs.create_group("temp")
    assert gs.remove_group(gid) is True
    assert gs.remove_group(gid) is False
    print("OK: remove group")


def test_callbacks():
    gs = AgentGroupStore()
    fired = []
    gs.on_change("mon", lambda a, d: fired.append(a))
    gs.create_group("team-alpha")
    assert len(fired) >= 1
    assert gs.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    gs = AgentGroupStore()
    gs.create_group("team-alpha")
    stats = gs.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    gs = AgentGroupStore()
    gs.create_group("team-alpha")
    gs.reset()
    assert gs.list_groups() == []
    print("OK: reset")


def main():
    print("=== Agent Group Store Tests ===\n")
    test_create_group()
    test_get_group()
    test_add_member()
    test_remove_member()
    test_get_members()
    test_find_groups_for_agent()
    test_list_groups()
    test_remove_group()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
