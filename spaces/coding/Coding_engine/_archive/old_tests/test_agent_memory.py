"""Test agent memory store."""
import sys
import time
sys.path.insert(0, ".")

from src.services.agent_memory import (
    AgentMemoryStore,
    MemoryCategory,
    MemoryTier,
)


def test_remember_and_recall():
    """Store and retrieve a memory."""
    mem = AgentMemoryStore()
    eid = mem.remember("Builder", "learning", "Use dataclasses for DTOs")

    assert eid.startswith("mem-")

    entries = mem.recall("Builder")
    assert len(entries) == 1
    assert entries[0]["content"] == "Use dataclasses for DTOs"
    assert entries[0]["agent_name"] == "Builder"
    assert entries[0]["category"] == "learning"
    print("OK: remember and recall")


def test_recall_by_category():
    """Recall filtered by category."""
    mem = AgentMemoryStore()
    mem.remember("Agent", "learning", "Python is great")
    mem.remember("Agent", "error", "ImportError in module X")
    mem.remember("Agent", "learning", "Use type hints")

    learnings = mem.recall("Agent", category="learning")
    assert len(learnings) == 2
    assert all(e["category"] == "learning" for e in learnings)

    errors = mem.recall("Agent", category="error")
    assert len(errors) == 1
    print("OK: recall by category")


def test_recall_by_tags():
    """Recall filtered by tags."""
    mem = AgentMemoryStore()
    mem.remember("Agent", "pattern", "Use factories", tags={"python", "design"})
    mem.remember("Agent", "pattern", "Use decorators", tags={"python"})
    mem.remember("Agent", "pattern", "Use interfaces", tags={"java"})

    python = mem.recall("Agent", tags={"python"})
    assert len(python) == 2

    python_design = mem.recall("Agent", tags={"python", "design"})
    assert len(python_design) == 1
    assert "factories" in python_design[0]["content"].lower()
    print("OK: recall by tags")


def test_recall_by_tier():
    """Recall filtered by tier."""
    mem = AgentMemoryStore()
    mem.remember("Agent", "fact", "Project uses Python 3.11", tier=MemoryTier.CORE)
    mem.remember("Agent", "context", "Working on auth module", tier=MemoryTier.SHORT_TERM)
    mem.remember("Agent", "learning", "Use async", tier=MemoryTier.LONG_TERM)

    core = mem.recall("Agent", tier=MemoryTier.CORE)
    assert len(core) == 1
    assert core[0]["tier"] == "core"
    print("OK: recall by tier")


def test_recall_sorted_by_importance():
    """Recall sorted by importance descending."""
    mem = AgentMemoryStore()
    mem.remember("Agent", "learning", "Low importance", importance=0.2)
    mem.remember("Agent", "learning", "High importance", importance=0.9)
    mem.remember("Agent", "learning", "Medium importance", importance=0.5)

    entries = mem.recall("Agent")
    assert entries[0]["importance"] == 0.9
    assert entries[1]["importance"] == 0.5
    assert entries[2]["importance"] == 0.2
    print("OK: recall sorted by importance")


def test_recall_recent():
    """Recall most recent memories."""
    mem = AgentMemoryStore()
    mem.remember("Agent", "context", "First thing")
    time.sleep(0.01)
    mem.remember("Agent", "context", "Second thing")
    time.sleep(0.01)
    mem.remember("Agent", "context", "Third thing")

    recent = mem.recall_recent("Agent", limit=2)
    assert len(recent) == 2
    assert recent[0]["content"] == "Third thing"
    assert recent[1]["content"] == "Second thing"
    print("OK: recall recent")


def test_get_entry():
    """Get a specific entry by ID."""
    mem = AgentMemoryStore()
    eid = mem.remember("Agent", "fact", "The answer is 42")

    entry = mem.get_entry(eid)
    assert entry is not None
    assert entry["content"] == "The answer is 42"
    assert entry["access_count"] == 1

    assert mem.get_entry("mem-nonexistent") is None
    print("OK: get entry")


def test_search():
    """Search memories by content."""
    mem = AgentMemoryStore()
    mem.remember("Agent1", "learning", "pytest fixtures are powerful")
    mem.remember("Agent1", "error", "ImportError in main.py")
    mem.remember("Agent2", "learning", "pytest parametrize saves time")
    mem.remember("Agent2", "pattern", "Factory pattern for objects")

    results = mem.search("pytest")
    assert len(results) == 2
    assert all("pytest" in r["content"].lower() for r in results)
    print("OK: search")


def test_search_by_agent():
    """Search scoped to a specific agent."""
    mem = AgentMemoryStore()
    mem.remember("Agent1", "learning", "Python async rocks")
    mem.remember("Agent2", "learning", "Python typing is useful")

    results = mem.search("Python", agent_name="Agent1")
    assert len(results) == 1
    assert results[0]["agent_name"] == "Agent1"
    print("OK: search by agent")


def test_search_by_tags():
    """Search finds entries by tag content."""
    mem = AgentMemoryStore()
    mem.remember("Agent", "pattern", "Use DI", tags={"dependency-injection"})
    mem.remember("Agent", "pattern", "Use singletons", tags={"singleton"})

    results = mem.search("dependency")
    assert len(results) == 1
    print("OK: search by tags")


def test_forget():
    """Forget a specific memory."""
    mem = AgentMemoryStore()
    eid = mem.remember("Agent", "learning", "Forget me")

    assert mem.forget(eid) is True
    assert mem.get_entry(eid) is None
    assert mem.forget(eid) is False  # Already gone
    print("OK: forget")


def test_forget_agent():
    """Forget all memories for an agent."""
    mem = AgentMemoryStore()
    mem.remember("Agent1", "learning", "A")
    mem.remember("Agent1", "learning", "B")
    mem.remember("Agent2", "learning", "C")

    removed = mem.forget_agent("Agent1")
    assert removed == 2
    assert mem.recall("Agent1") == []
    assert len(mem.recall("Agent2")) == 1
    print("OK: forget agent")


def test_update_importance():
    """Update importance of a memory."""
    mem = AgentMemoryStore()
    eid = mem.remember("Agent", "learning", "Test", importance=0.3)

    assert mem.update_importance(eid, 0.9) is True
    entry = mem.get_entry(eid)
    assert entry["importance"] == 0.9

    # Clamp to valid range
    mem.update_importance(eid, 1.5)
    entry = mem.get_entry(eid)
    assert entry["importance"] == 1.0

    assert mem.update_importance("nope", 0.5) is False
    print("OK: update importance")


def test_add_tags():
    """Add tags to a memory."""
    mem = AgentMemoryStore()
    eid = mem.remember("Agent", "pattern", "Use DI", tags={"python"})

    assert mem.add_tags(eid, {"testing", "design"}) is True
    entry = mem.get_entry(eid)
    assert set(entry["tags"]) == {"python", "testing", "design"}

    assert mem.add_tags("nope", {"tag"}) is False
    print("OK: add tags")


def test_promote():
    """Promote memory to higher tier."""
    mem = AgentMemoryStore()
    eid = mem.remember("Agent", "context", "Temp info",
                       tier=MemoryTier.SHORT_TERM, ttl_seconds=60.0)

    assert mem.promote(eid) is True
    entry = mem.get_entry(eid)
    assert entry["tier"] == "long_term"

    assert mem.promote(eid) is True
    entry = mem.get_entry(eid)
    assert entry["tier"] == "core"

    # Already core
    assert mem.promote(eid) is False
    print("OK: promote")


def test_ttl_expiry():
    """Short-term memories expire."""
    mem = AgentMemoryStore()
    eid = mem.remember("Agent", "context", "Ephemeral",
                       tier=MemoryTier.SHORT_TERM, ttl_seconds=0.1)

    # Still alive
    assert mem.get_entry(eid) is not None

    time.sleep(0.15)

    # Expired
    assert mem.get_entry(eid) is None
    entries = mem.recall("Agent")
    assert len(entries) == 0
    print("OK: ttl expiry")


def test_cleanup_expired():
    """Bulk cleanup of expired entries."""
    mem = AgentMemoryStore()
    mem.remember("Agent", "context", "Temp1", ttl_seconds=0.1)
    mem.remember("Agent", "context", "Temp2", ttl_seconds=0.1)
    mem.remember("Agent", "learning", "Permanent")

    time.sleep(0.15)

    removed = mem.cleanup_expired()
    assert removed == 2
    assert len(mem.recall("Agent")) == 1
    print("OK: cleanup expired")


def test_max_entries_pruning():
    """Entries are pruned when over per-agent limit."""
    mem = AgentMemoryStore(max_entries_per_agent=5)

    for i in range(8):
        mem.remember("Agent", "learning", f"Entry {i}",
                     importance=i * 0.1)

    entries = mem.recall("Agent", limit=100)
    assert len(entries) <= 5

    stats = mem.get_stats()
    assert stats["total_pruned"] >= 3
    print("OK: max entries pruning")


def test_core_not_pruned():
    """Core entries are never auto-pruned."""
    mem = AgentMemoryStore(max_entries_per_agent=3)

    # Add 2 core entries
    mem.remember("Agent", "fact", "Core 1", tier=MemoryTier.CORE, importance=0.1)
    mem.remember("Agent", "fact", "Core 2", tier=MemoryTier.CORE, importance=0.1)

    # Add more entries to trigger pruning
    for i in range(5):
        mem.remember("Agent", "learning", f"Normal {i}", importance=0.5)

    # Core entries should survive
    entries = mem.recall("Agent", tier=MemoryTier.CORE)
    assert len(entries) == 2
    print("OK: core not pruned")


def test_agent_summary():
    """Get agent memory summary."""
    mem = AgentMemoryStore()
    mem.remember("Agent", "learning", "A", tier=MemoryTier.LONG_TERM)
    mem.remember("Agent", "error", "B", tier=MemoryTier.LONG_TERM)
    mem.remember("Agent", "learning", "C", tier=MemoryTier.CORE)

    summary = mem.get_agent_summary("Agent")
    assert summary["total_entries"] == 3
    assert summary["categories"]["learning"] == 2
    assert summary["categories"]["error"] == 1
    assert summary["tiers"]["long_term"] == 2
    assert summary["tiers"]["core"] == 1
    print("OK: agent summary")


def test_list_agents():
    """List all agents with memories."""
    mem = AgentMemoryStore()
    mem.remember("Builder", "learning", "X")
    mem.remember("Tester", "learning", "Y")
    mem.remember("Designer", "learning", "Z")

    agents = mem.list_agents()
    assert agents == ["Builder", "Designer", "Tester"]
    print("OK: list agents")


def test_export_import():
    """Export and import memories."""
    mem = AgentMemoryStore()
    mem.remember("Agent", "learning", "Exported fact", tags={"python"}, importance=0.8)
    mem.remember("Agent", "error", "Exported error")

    exported = mem.export_agent("Agent")
    assert len(exported) == 2

    # Import into fresh store
    mem2 = AgentMemoryStore()
    imported = mem2.import_memories("Agent", exported)
    assert imported == 2

    entries = mem2.recall("Agent")
    assert len(entries) == 2
    print("OK: export import")


def test_stats():
    """Stats are accurate."""
    mem = AgentMemoryStore()
    mem.remember("Agent", "learning", "A")
    mem.remember("Agent", "learning", "B")

    mem.recall("Agent")
    mem.search("A")

    stats = mem.get_stats()
    assert stats["total_agents"] == 1
    assert stats["total_entries"] == 2
    assert stats["total_stored"] == 2
    assert stats["total_recalled"] == 1
    assert stats["total_searches"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    mem = AgentMemoryStore()
    mem.remember("Agent", "learning", "A")
    mem.recall("Agent")

    mem.reset()
    assert mem.list_agents() == []
    stats = mem.get_stats()
    assert stats["total_stored"] == 0
    assert stats["total_recalled"] == 0
    print("OK: reset")


def test_recall_limit():
    """Recall respects limit parameter."""
    mem = AgentMemoryStore()
    for i in range(20):
        mem.remember("Agent", "learning", f"Entry {i}")

    entries = mem.recall("Agent", limit=5)
    assert len(entries) == 5
    print("OK: recall limit")


def test_empty_recall():
    """Recall from non-existent agent returns empty."""
    mem = AgentMemoryStore()
    assert mem.recall("NonExistent") == []
    assert mem.recall_recent("NonExistent") == []
    print("OK: empty recall")


def main():
    print("=== Agent Memory Store Tests ===\n")
    test_remember_and_recall()
    test_recall_by_category()
    test_recall_by_tags()
    test_recall_by_tier()
    test_recall_sorted_by_importance()
    test_recall_recent()
    test_get_entry()
    test_search()
    test_search_by_agent()
    test_search_by_tags()
    test_forget()
    test_forget_agent()
    test_update_importance()
    test_add_tags()
    test_promote()
    test_ttl_expiry()
    test_cleanup_expired()
    test_max_entries_pruning()
    test_core_not_pruned()
    test_agent_summary()
    test_list_agents()
    test_export_import()
    test_stats()
    test_reset()
    test_recall_limit()
    test_empty_recall()
    print("\n=== ALL 26 TESTS PASSED ===")


if __name__ == "__main__":
    main()
