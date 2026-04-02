"""Test agent capability registry."""
import sys
sys.path.insert(0, ".")

from src.services.agent_capability_registry import AgentCapabilityRegistry


def test_register():
    """Register and remove capability."""
    cr = AgentCapabilityRegistry()
    cid = cr.register("code_review", "agent-1", category="review",
                       proficiency=0.9, version="2.0", tags=["python"])
    assert cid.startswith("cap-")

    c = cr.get_capability(cid)
    assert c is not None
    assert c["name"] == "code_review"
    assert c["agent"] == "agent-1"
    assert c["proficiency"] == 0.9
    assert c["status"] == "active"
    assert "python" in c["tags"]

    assert cr.remove(cid) is True
    assert cr.remove(cid) is False
    print("OK: register")


def test_invalid_register():
    """Invalid registration rejected."""
    cr = AgentCapabilityRegistry()
    assert cr.register("", "agent") == ""
    assert cr.register("cap", "") == ""
    assert cr.register("cap", "agent", category="invalid") == ""
    assert cr.register("cap", "agent", proficiency=-0.1) == ""
    assert cr.register("cap", "agent", proficiency=1.1) == ""
    print("OK: invalid register")


def test_max_capabilities():
    """Max capabilities enforced."""
    cr = AgentCapabilityRegistry(max_capabilities=2)
    cr.register("a", "agent-1")
    cr.register("b", "agent-1")
    assert cr.register("c", "agent-1") == ""
    print("OK: max capabilities")


def test_update_capability():
    """Update capability."""
    cr = AgentCapabilityRegistry()
    cid = cr.register("coding", "agent-1", proficiency=0.5)

    assert cr.update_capability(cid, proficiency=0.8, version="2.0",
                                 tags=["python"]) is True
    c = cr.get_capability(cid)
    assert c["proficiency"] == 0.8
    assert c["version"] == "2.0"

    assert cr.update_capability("nonexistent") is False
    assert cr.update_capability(cid, proficiency=2.0) is False
    print("OK: update capability")


def test_deprecate():
    """Deprecate a capability."""
    cr = AgentCapabilityRegistry()
    cid = cr.register("old_api", "agent-1")

    assert cr.deprecate(cid) is True
    assert cr.get_capability(cid)["status"] == "deprecated"
    assert cr.deprecate(cid) is False
    print("OK: deprecate")


def test_disable_enable():
    """Disable and enable capability."""
    cr = AgentCapabilityRegistry()
    cid = cr.register("feature", "agent-1")

    assert cr.disable(cid) is True
    assert cr.get_capability(cid)["status"] == "disabled"
    assert cr.disable(cid) is False

    assert cr.enable(cid) is True
    assert cr.get_capability(cid)["status"] == "active"
    assert cr.enable(cid) is False
    print("OK: disable enable")


def test_record_usage():
    """Record capability usage."""
    cr = AgentCapabilityRegistry()
    cid = cr.register("coding", "agent-1")

    cr.record_usage(cid)
    cr.record_usage(cid)
    assert cr.get_capability(cid)["usage_count"] == 2

    assert cr.record_usage("nonexistent") is False
    print("OK: record usage")


def test_find_agents():
    """Find agents with a capability."""
    cr = AgentCapabilityRegistry()
    cr.register("code_review", "agent-1", proficiency=0.9)
    cr.register("code_review", "agent-2", proficiency=0.7)
    cr.register("code_review", "agent-3", proficiency=0.3)
    cr.register("testing", "agent-1")

    agents = cr.find_agents("code_review")
    assert len(agents) == 3
    assert agents[0]["agent"] == "agent-1"  # Highest proficiency first

    agents = cr.find_agents("code_review", min_proficiency=0.5)
    assert len(agents) == 2
    print("OK: find agents")


def test_get_agent_capabilities():
    """Get all capabilities for an agent."""
    cr = AgentCapabilityRegistry()
    cr.register("coding", "agent-1")
    cr.register("testing", "agent-1")
    cid = cr.register("old_api", "agent-1")
    cr.deprecate(cid)

    active = cr.get_agent_capabilities("agent-1")
    assert len(active) == 2

    all_caps = cr.get_agent_capabilities("agent-1", active_only=False)
    assert len(all_caps) == 3
    print("OK: get agent capabilities")


def test_get_best_agent():
    """Get best agent for a capability."""
    cr = AgentCapabilityRegistry()
    cr.register("deploy", "agent-1", proficiency=0.5)
    cr.register("deploy", "agent-2", proficiency=0.9)

    assert cr.get_best_agent("deploy") == "agent-2"
    assert cr.get_best_agent("nonexistent") is None
    print("OK: get best agent")


def test_category_capabilities():
    """Get capabilities by category."""
    cr = AgentCapabilityRegistry()
    cr.register("review_code", "a1", category="review")
    cr.register("review_pr", "a2", category="review")
    cr.register("write_tests", "a1", category="testing")

    review = cr.get_category_capabilities("review")
    assert len(review) == 2
    print("OK: category capabilities")


def test_all_capability_names():
    """Get unique capability names."""
    cr = AgentCapabilityRegistry()
    cr.register("coding", "agent-1")
    cr.register("coding", "agent-2")
    cr.register("testing", "agent-1")

    names = cr.get_all_capability_names()
    assert names == ["coding", "testing"]
    print("OK: all capability names")


def test_all_agents():
    """Get all agents."""
    cr = AgentCapabilityRegistry()
    cr.register("a", "charlie")
    cr.register("b", "alice")
    cr.register("c", "bob")

    agents = cr.get_all_agents()
    assert agents == ["alice", "bob", "charlie"]
    print("OK: all agents")


def test_agent_summary():
    """Get agent capability summary."""
    cr = AgentCapabilityRegistry()
    c1 = cr.register("coding", "agent-1", category="coding", proficiency=0.8)
    cr.register("testing", "agent-1", category="testing", proficiency=0.6)
    cr.record_usage(c1)

    summary = cr.get_agent_summary("agent-1")
    assert summary["total_capabilities"] == 2
    assert summary["active"] == 2
    assert summary["avg_proficiency"] == 0.7
    assert summary["total_usage"] == 1
    assert summary["by_category"]["coding"] == 1

    assert cr.get_agent_summary("nonexistent") == {}
    print("OK: agent summary")


def test_capability_coverage():
    """Get capability coverage."""
    cr = AgentCapabilityRegistry()
    cr.register("coding", "agent-1")
    cr.register("coding", "agent-2")
    cr.register("testing", "agent-1")

    coverage = cr.get_capability_coverage()
    assert len(coverage) == 2
    assert coverage[0]["capability"] == "coding"
    assert coverage[0]["agent_count"] == 2
    print("OK: capability coverage")


def test_list_capabilities():
    """List with filters."""
    cr = AgentCapabilityRegistry()
    cr.register("a", "agent-1", category="coding", tags=["python"])
    cid = cr.register("b", "agent-2", category="testing")
    cr.deprecate(cid)

    all_c = cr.list_capabilities()
    assert len(all_c) == 2

    by_cat = cr.list_capabilities(category="coding")
    assert len(by_cat) == 1

    by_tag = cr.list_capabilities(tag="python")
    assert len(by_tag) == 1

    by_status = cr.list_capabilities(status="deprecated")
    assert len(by_status) == 1
    print("OK: list capabilities")


def test_registered_callback():
    """Callback fires on registration."""
    cr = AgentCapabilityRegistry()
    fired = []
    cr.on_change("mon", lambda a, d: fired.append(a))

    cr.register("test", "agent-1")
    assert "capability_registered" in fired
    print("OK: registered callback")


def test_callbacks():
    """Callback registration."""
    cr = AgentCapabilityRegistry()
    assert cr.on_change("mon", lambda a, d: None) is True
    assert cr.on_change("mon", lambda a, d: None) is False
    assert cr.remove_callback("mon") is True
    assert cr.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    cr = AgentCapabilityRegistry()
    c1 = cr.register("a", "agent-1")
    c2 = cr.register("b", "agent-1")
    cr.deprecate(c1)
    cr.remove(c2)
    cr.find_agents("a")

    stats = cr.get_stats()
    assert stats["total_registered"] == 2
    assert stats["total_deprecated"] == 1
    assert stats["total_removed"] == 1
    assert stats["total_lookups"] == 1
    assert stats["current_capabilities"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    cr = AgentCapabilityRegistry()
    cr.register("test", "agent-1")

    cr.reset()
    assert cr.list_capabilities() == []
    stats = cr.get_stats()
    assert stats["current_capabilities"] == 0
    print("OK: reset")


def main():
    print("=== Agent Capability Registry Tests ===\n")
    test_register()
    test_invalid_register()
    test_max_capabilities()
    test_update_capability()
    test_deprecate()
    test_disable_enable()
    test_record_usage()
    test_find_agents()
    test_get_agent_capabilities()
    test_get_best_agent()
    test_category_capabilities()
    test_all_capability_names()
    test_all_agents()
    test_agent_summary()
    test_capability_coverage()
    test_list_capabilities()
    test_registered_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 20 TESTS PASSED ===")


if __name__ == "__main__":
    main()
