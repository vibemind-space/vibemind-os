"""Test agent permission manager."""
import sys
sys.path.insert(0, ".")

from src.services.agent_permission_manager import AgentPermissionManager


def test_create_role():
    """Create and retrieve role."""
    pm = AgentPermissionManager()
    rid = pm.create_role("admin", permissions=["files:read", "files:write"], tags=["core"])
    assert rid.startswith("rol-")

    r = pm.get_role("admin")
    assert r is not None
    assert r["name"] == "admin"
    assert "files:read" in r["permissions"]

    assert pm.remove_role("admin") is True
    assert pm.remove_role("admin") is False
    print("OK: create role")


def test_invalid_create():
    """Invalid creation rejected."""
    pm = AgentPermissionManager()
    assert pm.create_role("") == ""
    print("OK: invalid create")


def test_duplicate():
    """Duplicate name rejected."""
    pm = AgentPermissionManager()
    pm.create_role("admin")
    assert pm.create_role("admin") == ""
    print("OK: duplicate")


def test_max_roles():
    """Max roles enforced."""
    pm = AgentPermissionManager(max_roles=2)
    pm.create_role("a")
    pm.create_role("b")
    assert pm.create_role("c") == ""
    print("OK: max roles")


def test_parent_role():
    """Parent role inheritance."""
    pm = AgentPermissionManager()
    pm.create_role("base", permissions=["files:read"])
    pm.create_role("admin", permissions=["files:write"], parent_role="base")

    # Invalid parent rejected
    assert pm.create_role("bad", parent_role="nonexistent") == ""
    print("OK: parent role")


def test_add_remove_permission():
    """Add and remove permission from role."""
    pm = AgentPermissionManager()
    pm.create_role("editor")

    assert pm.add_permission_to_role("editor", "docs:edit") is True
    r = pm.get_role("editor")
    assert "docs:edit" in r["permissions"]

    assert pm.remove_permission_from_role("editor", "docs:edit") is True
    assert pm.remove_permission_from_role("editor", "docs:edit") is False
    print("OK: add remove permission")


def test_assign_role():
    """Assign role to agent."""
    pm = AgentPermissionManager()
    pm.create_role("reader", permissions=["files:read"])

    assert pm.assign_role("worker1", "reader") is True
    assert pm.assign_role("worker1", "reader") is False  # duplicate
    assert pm.assign_role("worker1", "nonexistent") is False

    roles = pm.get_agent_roles("worker1")
    assert "reader" in roles
    print("OK: assign role")


def test_revoke_role():
    """Revoke role from agent."""
    pm = AgentPermissionManager()
    pm.create_role("reader")
    pm.assign_role("worker1", "reader")

    assert pm.revoke_role("worker1", "reader") is True
    assert pm.revoke_role("worker1", "reader") is False
    print("OK: revoke role")


def test_check_role_permission():
    """Check permission via role."""
    pm = AgentPermissionManager()
    pm.create_role("reader", permissions=["files:read"])
    pm.assign_role("worker1", "reader")

    assert pm.check("worker1", "files", "read") is True
    assert pm.check("worker1", "files", "write") is False
    print("OK: check role permission")


def test_check_inherited_permission():
    """Check permission inherited from parent role."""
    pm = AgentPermissionManager()
    pm.create_role("base", permissions=["files:read"])
    pm.create_role("admin", permissions=["files:write"], parent_role="base")
    pm.assign_role("worker1", "admin")

    assert pm.check("worker1", "files", "read") is True  # inherited
    assert pm.check("worker1", "files", "write") is True  # own
    print("OK: check inherited permission")


def test_explicit_grant():
    """Explicit grant beyond roles."""
    pm = AgentPermissionManager()
    pm.grant_permission("worker1", "special:action")

    assert pm.check("worker1", "special", "action") is True
    assert pm.check("worker1", "other", "action") is False
    print("OK: explicit grant")


def test_explicit_denial():
    """Explicit denial overrides role grant."""
    pm = AgentPermissionManager()
    pm.create_role("admin", permissions=["files:read", "files:write"])
    pm.assign_role("worker1", "admin")
    pm.deny_permission("worker1", "files:write")

    assert pm.check("worker1", "files", "read") is True
    assert pm.check("worker1", "files", "write") is False  # denied
    print("OK: explicit denial")


def test_wildcard():
    """Wildcard permission."""
    pm = AgentPermissionManager()
    pm.grant_permission("worker1", "files:*")

    assert pm.check("worker1", "files", "read") is True
    assert pm.check("worker1", "files", "write") is True
    assert pm.check("worker1", "db", "read") is False
    print("OK: wildcard")


def test_unassigned_agent():
    """Unassigned agent is denied."""
    pm = AgentPermissionManager()
    assert pm.check("unknown", "files", "read") is False
    print("OK: unassigned agent")


def test_get_agent_permissions():
    """Get all effective permissions."""
    pm = AgentPermissionManager()
    pm.create_role("reader", permissions=["files:read"])
    pm.assign_role("worker1", "reader")
    pm.grant_permission("worker1", "logs:read")
    pm.deny_permission("worker1", "files:read")

    perms = pm.get_agent_permissions("worker1")
    assert "logs:read" in perms
    assert "files:read" not in perms  # denied
    assert pm.get_agent_permissions("nonexistent") == []
    print("OK: get agent permissions")


def test_remove_role_cleans_agents():
    """Removing role cleans it from agents."""
    pm = AgentPermissionManager()
    pm.create_role("reader")
    pm.assign_role("worker1", "reader")
    pm.remove_role("reader")

    assert pm.get_agent_roles("worker1") == []
    print("OK: remove role cleans agents")


def test_list_roles():
    """List roles with filters."""
    pm = AgentPermissionManager()
    pm.create_role("admin", tags=["core"])
    pm.create_role("reader")

    all_r = pm.list_roles()
    assert len(all_r) == 2

    by_tag = pm.list_roles(tag="core")
    assert len(by_tag) == 1
    print("OK: list roles")


def test_list_agents():
    """List agents."""
    pm = AgentPermissionManager()
    pm.create_role("reader")
    pm.assign_role("w1", "reader")
    pm.assign_role("w2", "reader")

    agents = pm.list_agents()
    assert len(agents) == 2
    print("OK: list agents")


def test_history():
    """Check history tracking."""
    pm = AgentPermissionManager()
    pm.create_role("reader", permissions=["files:read"])
    pm.assign_role("w1", "reader")

    pm.check("w1", "files", "read")
    pm.check("w1", "files", "write")

    hist = pm.get_history()
    assert len(hist) == 2

    allowed = pm.get_history(allowed=True)
    assert len(allowed) == 1

    denied = pm.get_history(allowed=False)
    assert len(denied) == 1

    by_agent = pm.get_history(agent="w1")
    assert len(by_agent) == 2

    limited = pm.get_history(limit=1)
    assert len(limited) == 1
    print("OK: history")


def test_callback():
    """Callback fires on events."""
    pm = AgentPermissionManager()
    fired = []
    pm.on_change("mon", lambda a, d: fired.append(a))

    pm.create_role("admin")
    assert "role_created" in fired

    pm.assign_role("w1", "admin")
    assert "role_assigned" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    pm = AgentPermissionManager()
    assert pm.on_change("mon", lambda a, d: None) is True
    assert pm.on_change("mon", lambda a, d: None) is False
    assert pm.remove_callback("mon") is True
    assert pm.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    pm = AgentPermissionManager()
    pm.create_role("reader", permissions=["files:read"])
    pm.assign_role("w1", "reader")
    pm.check("w1", "files", "read")
    pm.check("w1", "files", "write")

    stats = pm.get_stats()
    assert stats["current_roles"] == 1
    assert stats["current_agents"] == 1
    assert stats["total_checks"] == 2
    assert stats["total_allowed"] == 1
    assert stats["total_denied"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    pm = AgentPermissionManager()
    pm.create_role("admin")

    pm.reset()
    assert pm.list_roles() == []
    stats = pm.get_stats()
    assert stats["current_roles"] == 0
    print("OK: reset")


def main():
    print("=== Agent Permission Manager Tests ===\n")
    test_create_role()
    test_invalid_create()
    test_duplicate()
    test_max_roles()
    test_parent_role()
    test_add_remove_permission()
    test_assign_role()
    test_revoke_role()
    test_check_role_permission()
    test_check_inherited_permission()
    test_explicit_grant()
    test_explicit_denial()
    test_wildcard()
    test_unassigned_agent()
    test_get_agent_permissions()
    test_remove_role_cleans_agents()
    test_list_roles()
    test_list_agents()
    test_history()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 23 TESTS PASSED ===")


if __name__ == "__main__":
    main()
