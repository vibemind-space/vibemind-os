"""Test agent capability matcher."""
import sys
sys.path.insert(0, ".")

from src.services.agent_capability_matcher import AgentCapabilityMatcher


def test_register_agent():
    """Register and unregister agents."""
    cm = AgentCapabilityMatcher()
    assert cm.register_agent("agent-1", capabilities=["python", "testing"]) is True
    assert cm.register_agent("agent-1") is False  # Duplicate

    a = cm.get_agent("agent-1")
    assert a is not None
    assert "python" in a["capabilities"]
    assert a["proficiency"]["python"] == 1.0

    assert cm.unregister_agent("agent-1") is True
    assert cm.unregister_agent("agent-1") is False
    print("OK: register agent")


def test_invalid_registration():
    """Invalid registration rejected."""
    cm = AgentCapabilityMatcher()
    assert cm.register_agent("") is False
    assert cm.register_agent("x", max_concurrent=0) is False
    print("OK: invalid registration")


def test_max_agents():
    """Max agents enforced."""
    cm = AgentCapabilityMatcher(max_agents=2)
    cm.register_agent("a")
    cm.register_agent("b")
    assert cm.register_agent("c") is False
    print("OK: max agents")


def test_add_remove_capability():
    """Add and remove capabilities."""
    cm = AgentCapabilityMatcher()
    cm.register_agent("agent-1")

    assert cm.add_capability("agent-1", "python", 0.8) is True
    assert cm.add_capability("agent-1", "python") is False  # Duplicate
    assert cm.get_agent("agent-1")["proficiency"]["python"] == 0.8

    assert cm.remove_capability("agent-1", "python") is True
    assert cm.remove_capability("agent-1", "python") is False
    print("OK: add remove capability")


def test_set_proficiency():
    """Set proficiency levels."""
    cm = AgentCapabilityMatcher()
    cm.register_agent("agent-1", capabilities=["python"])

    assert cm.set_proficiency("agent-1", "python", 0.5) is True
    assert cm.get_agent("agent-1")["proficiency"]["python"] == 0.5

    assert cm.set_proficiency("agent-1", "python", -0.1) is False
    assert cm.set_proficiency("agent-1", "python", 1.1) is False
    assert cm.set_proficiency("agent-1", "nonexistent", 0.5) is False
    print("OK: set proficiency")


def test_set_available():
    """Set agent availability."""
    cm = AgentCapabilityMatcher()
    cm.register_agent("agent-1")

    assert cm.set_available("agent-1", False) is True
    assert cm.get_agent("agent-1")["available"] is False
    print("OK: set available")


def test_list_agents():
    """List agents with filters."""
    cm = AgentCapabilityMatcher()
    cm.register_agent("a", capabilities=["python"], tags=["gpu"])
    cm.register_agent("b", capabilities=["java"], tags=["cpu"])
    cm.register_agent("c", capabilities=["python"])
    cm.set_available("c", False)

    all_a = cm.list_agents()
    assert len(all_a) == 3

    by_cap = cm.list_agents(capability="python")
    assert len(by_cap) == 2

    by_tag = cm.list_agents(tag="gpu")
    assert len(by_tag) == 1

    available = cm.list_agents(available_only=True)
    assert len(available) == 2
    print("OK: list agents")


def test_create_task():
    """Create and remove tasks."""
    cm = AgentCapabilityMatcher()
    tid = cm.create_task("build_app", required=["python", "docker"])
    assert tid.startswith("match-")

    t = cm.get_task(tid)
    assert t is not None
    assert t["name"] == "build_app"
    assert "python" in t["required_capabilities"]

    assert cm.remove_task(tid) is True
    assert cm.remove_task(tid) is False
    print("OK: create task")


def test_invalid_task():
    """Invalid task rejected."""
    cm = AgentCapabilityMatcher()
    assert cm.create_task("") == ""
    print("OK: invalid task")


def test_max_tasks():
    """Max tasks enforced."""
    cm = AgentCapabilityMatcher(max_tasks=2)
    cm.create_task("a")
    cm.create_task("b")
    assert cm.create_task("c") == ""
    print("OK: max tasks")


def test_find_matches():
    """Find matching agents for a task."""
    cm = AgentCapabilityMatcher()
    cm.register_agent("expert", capabilities=["python", "docker", "testing"], proficiency={"python": 0.9, "docker": 0.8, "testing": 0.7})
    cm.register_agent("junior", capabilities=["python"], proficiency={"python": 0.5})
    cm.register_agent("java-dev", capabilities=["java"])

    tid = cm.create_task("deploy", required=["python", "docker"])
    matches = cm.find_matches(tid)

    assert len(matches) == 1  # Only expert has both
    assert matches[0]["name"] == "expert"
    print("OK: find matches")


def test_find_matches_preferred():
    """Preferred capabilities improve score."""
    cm = AgentCapabilityMatcher()
    cm.register_agent("a", capabilities=["python", "testing"])
    cm.register_agent("b", capabilities=["python", "testing", "docker"])

    tid = cm.create_task("test", required=["python"], preferred=["docker"])
    matches = cm.find_matches(tid)

    assert len(matches) == 2
    assert matches[0]["name"] == "b"  # Has preferred capability
    print("OK: find matches preferred")


def test_find_matches_proficiency():
    """Min proficiency filters agents."""
    cm = AgentCapabilityMatcher()
    cm.register_agent("expert", capabilities=["python"], proficiency={"python": 0.9})
    cm.register_agent("novice", capabilities=["python"], proficiency={"python": 0.3})

    tid = cm.create_task("critical", required=["python"], min_proficiency=0.5)
    matches = cm.find_matches(tid)

    assert len(matches) == 1
    assert matches[0]["name"] == "expert"
    print("OK: find matches proficiency")


def test_find_matches_excludes_full():
    """Full agents excluded from matches."""
    cm = AgentCapabilityMatcher()
    cm.register_agent("busy", capabilities=["python"], max_concurrent=1)
    cm.register_agent("free", capabilities=["python"], max_concurrent=5)

    # Fill up busy agent
    t1 = cm.create_task("t1", required=["python"])
    cm.auto_assign(t1)

    t2 = cm.create_task("t2", required=["python"])
    matches = cm.find_matches(t2)

    names = [m["name"] for m in matches]
    assert "busy" not in names
    assert "free" in names
    print("OK: find matches excludes full")


def test_auto_assign():
    """Auto-assign task to best agent."""
    cm = AgentCapabilityMatcher()
    cm.register_agent("agent-1", capabilities=["python"])
    cm.register_agent("agent-2", capabilities=["java"])

    tid = cm.create_task("py_task", required=["python"])
    agent = cm.auto_assign(tid)
    assert agent == "agent-1"

    t = cm.get_task(tid)
    assert t["assigned_to"] == "agent-1"
    print("OK: auto assign")


def test_auto_assign_no_match():
    """Auto-assign returns empty when no match."""
    cm = AgentCapabilityMatcher()
    cm.register_agent("agent-1", capabilities=["java"])

    tid = cm.create_task("py_task", required=["python"])
    assert cm.auto_assign(tid) == ""
    print("OK: auto assign no match")


def test_release_assignment():
    """Release task assignment."""
    cm = AgentCapabilityMatcher()
    cm.register_agent("agent-1", capabilities=["python"])

    tid = cm.create_task("task", required=["python"])
    cm.auto_assign(tid)
    assert cm.get_agent("agent-1")["current_load"] == 1

    assert cm.release_assignment(tid) is True
    assert cm.get_agent("agent-1")["current_load"] == 0
    assert cm.release_assignment(tid) is False
    print("OK: release assignment")


def test_agent_assignments():
    """Get tasks assigned to agent."""
    cm = AgentCapabilityMatcher()
    cm.register_agent("agent-1", capabilities=["python"], max_concurrent=10)

    t1 = cm.create_task("a", required=["python"])
    t2 = cm.create_task("b", required=["python"])
    cm.auto_assign(t1)
    cm.auto_assign(t2)

    assignments = cm.get_agent_assignments("agent-1")
    assert len(assignments) == 2
    print("OK: agent assignments")


def test_capability_coverage():
    """Capability coverage across agents."""
    cm = AgentCapabilityMatcher()
    cm.register_agent("a", capabilities=["python", "docker"])
    cm.register_agent("b", capabilities=["python", "java"])

    coverage = cm.get_capability_coverage()
    assert coverage["python"] == 2
    assert coverage["docker"] == 1
    assert coverage["java"] == 1
    print("OK: capability coverage")


def test_unmatched_capabilities():
    """Find capabilities no agent has."""
    cm = AgentCapabilityMatcher()
    cm.register_agent("a", capabilities=["python"])

    tid = cm.create_task("task", required=["python", "quantum_computing"])
    unmatched = cm.get_unmatched_capabilities(tid)
    assert "quantum_computing" in unmatched
    assert "python" not in unmatched
    print("OK: unmatched capabilities")


def test_callbacks():
    """Callbacks fire on events."""
    cm = AgentCapabilityMatcher()
    cm.register_agent("agent-1", capabilities=["python"])

    fired = []
    assert cm.on_change("mon", lambda a, d: fired.append(a)) is True
    assert cm.on_change("mon", lambda a, d: None) is False

    tid = cm.create_task("task", required=["python"])
    cm.auto_assign(tid)
    assert "task_assigned" in fired

    assert cm.remove_callback("mon") is True
    assert cm.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    cm = AgentCapabilityMatcher()
    cm.register_agent("a", capabilities=["python"])
    t1 = cm.create_task("t1", required=["python"])
    t2 = cm.create_task("t2", required=["rust"])
    cm.auto_assign(t1)
    cm.auto_assign(t2)  # No match

    stats = cm.get_stats()
    assert stats["total_registered"] == 1
    assert stats["total_tasks_created"] == 2
    assert stats["total_matched"] == 1
    assert stats["total_no_match"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    cm = AgentCapabilityMatcher()
    cm.register_agent("a", capabilities=["python"])
    cm.create_task("t")

    cm.reset()
    assert cm.list_agents() == []
    stats = cm.get_stats()
    assert stats["current_agents"] == 0
    print("OK: reset")


def main():
    print("=== Agent Capability Matcher Tests ===\n")
    test_register_agent()
    test_invalid_registration()
    test_max_agents()
    test_add_remove_capability()
    test_set_proficiency()
    test_set_available()
    test_list_agents()
    test_create_task()
    test_invalid_task()
    test_max_tasks()
    test_find_matches()
    test_find_matches_preferred()
    test_find_matches_proficiency()
    test_find_matches_excludes_full()
    test_auto_assign()
    test_auto_assign_no_match()
    test_release_assignment()
    test_agent_assignments()
    test_capability_coverage()
    test_unmatched_capabilities()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 23 TESTS PASSED ===")


if __name__ == "__main__":
    main()
