"""Test agent policy engine -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_policy_engine import AgentPolicyEngine


def test_create_policy():
    pe = AgentPolicyEngine()
    pid = pe.create_policy("deploy-policy", rules=[{"action": "deploy", "effect": "allow"}])
    assert len(pid) > 0
    assert pid.startswith("ape-")
    # Duplicate returns ""
    assert pe.create_policy("deploy-policy", rules=[]) == ""
    print("OK: create policy")


def test_get_policy():
    pe = AgentPolicyEngine()
    pid = pe.create_policy("test-policy", rules=[{"action": "test", "effect": "allow"}], description="Test only")
    pol = pe.get_policy(pid)
    assert pol is not None
    assert pol["name"] == "test-policy"
    assert pol["enabled"] is True
    assert pe.get_policy("nonexistent") is None
    print("OK: get policy")


def test_get_policy_by_name():
    pe = AgentPolicyEngine()
    pe.create_policy("my-policy", rules=[])
    pol = pe.get_policy_by_name("my-policy")
    assert pol is not None
    assert pol["name"] == "my-policy"
    assert pe.get_policy_by_name("nonexistent") is None
    print("OK: get policy by name")


def test_evaluate_allow():
    pe = AgentPolicyEngine()
    pe.create_policy("allow-deploy", rules=[{"action": "deploy", "effect": "allow"}])
    result = pe.evaluate("agent-1", "deploy")
    assert result["allowed"] is True
    print("OK: evaluate allow")


def test_evaluate_deny():
    pe = AgentPolicyEngine()
    pe.create_policy("deny-delete", rules=[{"action": "delete", "effect": "deny"}])
    result = pe.evaluate("agent-1", "delete")
    assert result["allowed"] is False
    assert result["denied_by"] is not None
    print("OK: evaluate deny")


def test_evaluate_no_match():
    pe = AgentPolicyEngine()
    pe.create_policy("some-policy", rules=[{"action": "build", "effect": "allow"}])
    result = pe.evaluate("agent-1", "unknown_action")
    assert result["allowed"] is True  # Default allow
    print("OK: evaluate no match")


def test_enable_disable():
    pe = AgentPolicyEngine()
    pid = pe.create_policy("p", rules=[{"action": "x", "effect": "deny"}])
    pe.disable_policy(pid)
    result = pe.evaluate("agent-1", "x")
    assert result["allowed"] is True  # Disabled policy doesn't apply
    pe.enable_policy(pid)
    result = pe.evaluate("agent-1", "x")
    assert result["allowed"] is False
    print("OK: enable/disable")


def test_update_policy():
    pe = AgentPolicyEngine()
    pid = pe.create_policy("p", rules=[{"action": "x", "effect": "allow"}])
    assert pe.update_policy(pid, description="Updated") is True
    pol = pe.get_policy(pid)
    assert pol["description"] == "Updated"
    assert pe.update_policy("nonexistent") is False
    print("OK: update policy")


def test_delete_policy():
    pe = AgentPolicyEngine()
    pid = pe.create_policy("p", rules=[])
    assert pe.delete_policy(pid) is True
    assert pe.delete_policy(pid) is False
    print("OK: delete policy")


def test_list_policies():
    pe = AgentPolicyEngine()
    pe.create_policy("p1", rules=[], enabled=True)
    p2 = pe.create_policy("p2", rules=[], enabled=True)
    pe.disable_policy(p2)
    all_pols = pe.list_policies()
    assert len(all_pols) == 2
    enabled = pe.list_policies(enabled_only=True)
    assert len(enabled) == 1
    print("OK: list policies")


def test_get_policy_count():
    pe = AgentPolicyEngine()
    pe.create_policy("p1", rules=[])
    pe.create_policy("p2", rules=[])
    assert pe.get_policy_count() == 2
    print("OK: get policy count")


def test_callbacks():
    pe = AgentPolicyEngine()
    fired = []
    pe.on_change("mon", lambda a, d: fired.append(a))
    pe.create_policy("p", rules=[])
    assert len(fired) >= 1
    assert pe.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    pe = AgentPolicyEngine()
    pe.create_policy("p", rules=[])
    stats = pe.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    pe = AgentPolicyEngine()
    pe.create_policy("p", rules=[])
    pe.reset()
    assert pe.get_policy_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Policy Engine Tests ===\n")
    test_create_policy()
    test_get_policy()
    test_get_policy_by_name()
    test_evaluate_allow()
    test_evaluate_deny()
    test_evaluate_no_match()
    test_enable_disable()
    test_update_policy()
    test_delete_policy()
    test_list_policies()
    test_get_policy_count()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 14 TESTS PASSED ===")


if __name__ == "__main__":
    main()
