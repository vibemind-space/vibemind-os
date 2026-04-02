"""Test agent work journal."""
import sys
sys.path.insert(0, ".")

from src.services.agent_work_journal import AgentWorkJournal


def test_add_entry():
    """Add and retrieve entries."""
    wj = AgentWorkJournal()
    eid = wj.add_entry("agent-1", "decision", "Chose algorithm A", content="Because it's faster", tags=["arch"])
    assert eid.startswith("journal-")

    e = wj.get_entry(eid)
    assert e is not None
    assert e["agent"] == "agent-1"
    assert e["entry_type"] == "decision"
    assert e["title"] == "Chose algorithm A"
    assert e["content"] == "Because it's faster"
    assert "arch" in e["tags"]

    assert wj.remove_entry(eid) is True
    assert wj.remove_entry(eid) is False
    print("OK: add entry")


def test_invalid_entry():
    """Invalid entry rejected."""
    wj = AgentWorkJournal()
    assert wj.add_entry("", "decision", "x") == ""
    assert wj.add_entry("a", "invalid", "x") == ""
    assert wj.add_entry("a", "decision", "") == ""
    assert wj.add_entry("a", "decision", "x", parent_id="nonexistent") == ""
    print("OK: invalid entry")


def test_max_entries():
    """Max entries enforced."""
    wj = AgentWorkJournal(max_entries=2)
    wj.add_entry("a", "note", "x")
    wj.add_entry("a", "note", "y")
    assert wj.add_entry("a", "note", "z") == ""
    print("OK: max entries")


def test_max_per_agent():
    """Max entries per agent enforced."""
    wj = AgentWorkJournal(max_entries_per_agent=2)
    wj.add_entry("agent-1", "note", "x")
    wj.add_entry("agent-1", "note", "y")
    assert wj.add_entry("agent-1", "note", "z") == ""
    # Different agent still works
    assert wj.add_entry("agent-2", "note", "z") != ""
    print("OK: max per agent")


def test_agent_journal():
    """Get agent journal with filters."""
    wj = AgentWorkJournal()
    wj.add_entry("agent-1", "decision", "d1", tags=["arch"])
    wj.add_entry("agent-1", "action", "a1")
    wj.add_entry("agent-1", "decision", "d2")
    wj.add_entry("agent-2", "note", "n1")

    all_e = wj.get_agent_journal("agent-1")
    assert len(all_e) == 3

    decisions = wj.get_agent_journal("agent-1", entry_type="decision")
    assert len(decisions) == 2

    tagged = wj.get_agent_journal("agent-1", tag="arch")
    assert len(tagged) == 1
    print("OK: agent journal")


def test_search_entries():
    """Search entries by text."""
    wj = AgentWorkJournal()
    wj.add_entry("agent-1", "decision", "Choose algorithm", content="For sorting")
    wj.add_entry("agent-1", "action", "Built module")
    wj.add_entry("agent-2", "note", "Algorithm note")

    results = wj.search_entries("algorithm")
    assert len(results) == 2

    results2 = wj.search_entries("algorithm", agent="agent-1")
    assert len(results2) == 1

    assert wj.search_entries("") == []
    print("OK: search entries")


def test_thread():
    """Get thread of related entries."""
    wj = AgentWorkJournal()
    e1 = wj.add_entry("a", "decision", "Start task")
    e2 = wj.add_entry("a", "action", "Step 1", parent_id=e1)
    e3 = wj.add_entry("a", "result", "Done", parent_id=e2)

    thread = wj.get_thread(e3)
    assert len(thread) == 3
    assert thread[0]["entry_id"] == e1
    assert thread[2]["entry_id"] == e3
    print("OK: thread")


def test_children():
    """Get child entries."""
    wj = AgentWorkJournal()
    parent = wj.add_entry("a", "decision", "Main task")
    c1 = wj.add_entry("a", "action", "Step 1", parent_id=parent)
    c2 = wj.add_entry("a", "action", "Step 2", parent_id=parent)

    children = wj.get_children(parent)
    assert len(children) == 2
    print("OK: children")


def test_list_entries():
    """List entries with filters."""
    wj = AgentWorkJournal()
    wj.add_entry("a", "decision", "d1", tags=["important"])
    wj.add_entry("b", "action", "a1")
    wj.add_entry("a", "error", "e1")

    all_e = wj.list_entries()
    assert len(all_e) == 3

    decisions = wj.list_entries(entry_type="decision")
    assert len(decisions) == 1

    tagged = wj.list_entries(tag="important")
    assert len(tagged) == 1
    print("OK: list entries")


def test_agent_summary():
    """Agent activity summary."""
    wj = AgentWorkJournal()
    wj.add_entry("agent-1", "decision", "d1")
    wj.add_entry("agent-1", "decision", "d2")
    wj.add_entry("agent-1", "action", "a1")

    summary = wj.get_agent_summary("agent-1")
    assert summary["total_entries"] == 3
    assert summary["by_type"]["decision"] == 2
    assert summary["by_type"]["action"] == 1

    assert wj.get_agent_summary("nonexistent") == {}
    print("OK: agent summary")


def test_type_distribution():
    """Type distribution."""
    wj = AgentWorkJournal()
    wj.add_entry("a", "decision", "x")
    wj.add_entry("a", "decision", "y")
    wj.add_entry("a", "error", "z")

    dist = wj.get_type_distribution()
    assert dist["decision"] == 2
    assert dist["error"] == 1
    print("OK: type distribution")


def test_active_agents():
    """Get active agents."""
    wj = AgentWorkJournal()
    wj.add_entry("agent-1", "note", "x")
    wj.add_entry("agent-2", "note", "y")

    agents = wj.get_active_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: active agents")


def test_recent_activity():
    """Get recent activity."""
    wj = AgentWorkJournal()
    wj.add_entry("a", "note", "first")
    wj.add_entry("b", "note", "second")

    recent = wj.get_recent_activity(limit=5)
    assert len(recent) == 2
    print("OK: recent activity")


def test_callbacks():
    """Callbacks fire on events."""
    wj = AgentWorkJournal()

    fired = []
    assert wj.on_change("mon", lambda a, d: fired.append(a)) is True
    assert wj.on_change("mon", lambda a, d: None) is False

    wj.add_entry("agent-1", "note", "test")
    assert "entry_added" in fired

    assert wj.remove_callback("mon") is True
    assert wj.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    wj = AgentWorkJournal()
    wj.add_entry("agent-1", "note", "a")
    wj.add_entry("agent-1", "note", "b")
    wj.add_entry("agent-2", "note", "c")

    stats = wj.get_stats()
    assert stats["total_entries"] == 3
    assert stats["total_agents"] == 2
    assert stats["current_entries"] == 3
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    wj = AgentWorkJournal()
    wj.add_entry("a", "note", "x")

    wj.reset()
    assert wj.list_entries() == []
    assert wj.get_active_agents() == []
    stats = wj.get_stats()
    assert stats["current_entries"] == 0
    print("OK: reset")


def main():
    print("=== Agent Work Journal Tests ===\n")
    test_add_entry()
    test_invalid_entry()
    test_max_entries()
    test_max_per_agent()
    test_agent_journal()
    test_search_entries()
    test_thread()
    test_children()
    test_list_entries()
    test_agent_summary()
    test_type_distribution()
    test_active_agents()
    test_recent_activity()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 16 TESTS PASSED ===")


if __name__ == "__main__":
    main()
