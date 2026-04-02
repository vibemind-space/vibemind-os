"""Test agent permission store -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_permission_store import AgentPermissionStore


def test_create_role():
    ps = AgentPermissionStore()
    rid = ps.create_role("admin", permissions=["read", "write", "delete"], description="Full access")
    assert len(rid) > 0
    assert ps.create_role("admin") == ""  # dup
    print("OK: create role")


def test_assign_role():
    ps = AgentPermissionStore()
    ps.create_role("admin", permissions=["read", "write"])
    assert ps.assign_role("agent-1", "admin") is True
    roles = ps.get_agent_roles("agent-1")
    assert "admin" in roles
    print("OK: assign role")


def test_revoke_role():
    ps = AgentPermissionStore()
    ps.create_role("admin", permissions=["read"])
    ps.assign_role("agent-1", "admin")
    assert ps.revoke_role("agent-1", "admin") is True
    assert ps.revoke_role("agent-1", "admin") is False
    print("OK: revoke role")


def test_check_permission():
    ps = AgentPermissionStore()
    ps.create_role("editor", permissions=["read", "write"])
    ps.assign_role("agent-1", "editor")
    assert ps.check_permission("agent-1", "read") is True
    assert ps.check_permission("agent-1", "write") is True
    assert ps.check_permission("agent-1", "delete") is False
    print("OK: check permission")


def test_get_agent_permissions():
    ps = AgentPermissionStore()
    ps.create_role("reader", permissions=["read"])
    ps.create_role("writer", permissions=["write"])
    ps.assign_role("agent-1", "reader")
    ps.assign_role("agent-1", "writer")
    perms = ps.get_agent_permissions("agent-1")
    assert "read" in perms
    assert "write" in perms
    print("OK: get agent permissions")


def test_add_permission_to_role():
    ps = AgentPermissionStore()
    ps.create_role("basic", permissions=["read"])
    assert ps.add_permission_to_role("basic", "write") is True
    ps.assign_role("agent-1", "basic")
    assert ps.check_permission("agent-1", "write") is True
    print("OK: add permission to role")


def test_list_roles():
    ps = AgentPermissionStore()
    ps.create_role("admin", permissions=["all"])
    ps.create_role("viewer", permissions=["read"])
    roles = ps.list_roles()
    assert len(roles) == 2
    print("OK: list roles")


def test_remove_role():
    ps = AgentPermissionStore()
    ps.create_role("temp", permissions=["read"])
    assert ps.remove_role("temp") is True
    assert ps.remove_role("temp") is False
    print("OK: remove role")


def test_callbacks():
    ps = AgentPermissionStore()
    fired = []
    ps.on_change("mon", lambda a, d: fired.append(a))
    ps.create_role("r1", permissions=["read"])
    assert len(fired) >= 1
    assert ps.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    ps = AgentPermissionStore()
    ps.create_role("r1", permissions=["read"])
    stats = ps.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    ps = AgentPermissionStore()
    ps.create_role("r1", permissions=["read"])
    ps.reset()
    assert ps.list_roles() == []
    print("OK: reset")


def main():
    print("=== Agent Permission Store Tests ===\n")
    test_create_role()
    test_assign_role()
    test_revoke_role()
    test_check_permission()
    test_get_agent_permissions()
    test_add_permission_to_role()
    test_list_roles()
    test_remove_role()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
