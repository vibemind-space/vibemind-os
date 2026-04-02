"""Tests for AgentInputValidator."""

import sys
sys.path.insert(0, ".")

from src.services.agent_input_validator import AgentInputValidator


def test_add_rule():
    v = AgentInputValidator()
    rid = v.add_rule("agent-1", "name", "required")
    assert rid.startswith("aiv-"), f"Expected aiv- prefix, got {rid}"
    assert len(v.rules) == 1
    # empty agent_id should fail
    assert v.add_rule("", "name") == ""
    # empty field should fail
    assert v.add_rule("agent-1", "") == ""
    print("  test_add_rule PASSED")


def test_validate_required():
    v = AgentInputValidator()
    v.add_rule("agent-1", "name", "required")
    result = v.validate("agent-1", {"name": "Alice"})
    assert result["valid"] is True
    result = v.validate("agent-1", {})
    assert result["valid"] is False
    assert any("required" in e for e in result["errors"])
    # None counts as missing
    result = v.validate("agent-1", {"name": None})
    assert result["valid"] is False
    print("  test_validate_required PASSED")


def test_validate_type():
    v = AgentInputValidator()
    v.add_rule("agent-1", "age", "type", "int")
    result = v.validate("agent-1", {"age": 25})
    assert result["valid"] is True
    result = v.validate("agent-1", {"age": "twenty"})
    assert result["valid"] is False
    assert any("type" in e for e in result["errors"])
    print("  test_validate_type PASSED")


def test_validate_min_max():
    v = AgentInputValidator()
    v.add_rule("agent-1", "score", "min", 0)
    v.add_rule("agent-1", "score", "max", 100)
    result = v.validate("agent-1", {"score": 50})
    assert result["valid"] is True
    result = v.validate("agent-1", {"score": -1})
    assert result["valid"] is False
    assert any(">=" in e for e in result["errors"])
    result = v.validate("agent-1", {"score": 101})
    assert result["valid"] is False
    assert any("<=" in e for e in result["errors"])
    print("  test_validate_min_max PASSED")


def test_validate_in():
    v = AgentInputValidator()
    v.add_rule("agent-1", "status", "in", ["active", "inactive", "pending"])
    result = v.validate("agent-1", {"status": "active"})
    assert result["valid"] is True
    result = v.validate("agent-1", {"status": "deleted"})
    assert result["valid"] is False
    assert any("one of" in e for e in result["errors"])
    print("  test_validate_in PASSED")


def test_validate_pass():
    v = AgentInputValidator()
    v.add_rule("agent-1", "name", "required")
    v.add_rule("agent-1", "name", "type", "str")
    v.add_rule("agent-1", "age", "type", "int")
    v.add_rule("agent-1", "age", "min", 0)
    v.add_rule("agent-1", "age", "max", 150)
    result = v.validate("agent-1", {"name": "Alice", "age": 30})
    assert result["valid"] is True
    assert result["errors"] == []
    print("  test_validate_pass PASSED")


def test_remove_rule():
    v = AgentInputValidator()
    rid = v.add_rule("agent-1", "name", "required")
    assert v.remove_rule(rid) is True
    assert v.remove_rule(rid) is False
    assert len(v.rules) == 0
    print("  test_remove_rule PASSED")


def test_get_rule_count():
    v = AgentInputValidator()
    v.add_rule("agent-1", "name", "required")
    v.add_rule("agent-1", "age", "type", "int")
    v.add_rule("agent-2", "status", "required")
    assert v.get_rule_count() == 3
    assert v.get_rule_count("agent-1") == 2
    assert v.get_rule_count("agent-2") == 1
    assert v.get_rule_count("agent-999") == 0
    print("  test_get_rule_count PASSED")


def test_list_agents():
    v = AgentInputValidator()
    v.add_rule("agent-b", "name", "required")
    v.add_rule("agent-a", "name", "required")
    v.add_rule("agent-b", "age", "type", "int")
    agents = v.list_agents()
    assert agents == ["agent-a", "agent-b"]
    print("  test_list_agents PASSED")


def test_callbacks():
    v = AgentInputValidator()
    events = []
    v.on_change("my_cb", lambda action, data: events.append((action, data)))
    # duplicate name should fail
    assert v.on_change("my_cb", lambda a, d: None) is False
    v.add_rule("agent-1", "name", "required")
    assert len(events) == 1
    assert events[0][0] == "rule_added"
    # remove callback
    assert v.remove_callback("my_cb") is True
    assert v.remove_callback("my_cb") is False
    v.add_rule("agent-1", "age", "type", "int")
    assert len(events) == 1  # no new events after removal
    print("  test_callbacks PASSED")


def test_stats():
    v = AgentInputValidator()
    v.add_rule("agent-1", "name", "required")
    v.validate("agent-1", {"name": "Alice"})
    v.validate("agent-1", {})
    stats = v.get_stats()
    assert stats["total_rules"] == 1
    assert stats["total_added"] == 1
    assert stats["total_validated"] == 2
    assert stats["total_agents"] == 1
    print("  test_stats PASSED")


def test_reset():
    v = AgentInputValidator()
    v.add_rule("agent-1", "name", "required")
    v.on_change("cb1", lambda a, d: None)
    v.validate("agent-1", {"name": "test"})
    v.reset()
    assert len(v.rules) == 0
    stats = v.get_stats()
    assert stats["total_rules"] == 0
    assert stats["total_added"] == 0
    assert stats["total_validated"] == 0
    assert stats["total_removed"] == 0
    assert stats["total_agents"] == 0
    print("  test_reset PASSED")


if __name__ == "__main__":
    test_add_rule()
    test_validate_required()
    test_validate_type()
    test_validate_min_max()
    test_validate_in()
    test_validate_pass()
    test_remove_rule()
    test_get_rule_count()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 12 TESTS PASSED ===")
