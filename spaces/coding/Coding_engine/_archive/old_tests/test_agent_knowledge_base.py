"""Test agent knowledge base -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_knowledge_base import AgentKnowledgeBase


def test_add_entry():
    kb = AgentKnowledgeBase()
    eid = kb.add_entry("Python", "interpreted language", category="technical", tags=["lang"])
    assert eid.startswith("kb-")
    e = kb.get_entry(eid)
    assert e is not None
    assert e["title"] == "Python"
    print("OK: add entry")


def test_update_entry():
    kb = AgentKnowledgeBase()
    eid = kb.add_entry("Python", "old content", category="technical")
    assert kb.update_entry(eid, content="new content") is True
    e = kb.get_entry(eid)
    assert e["content"] == "new content"
    print("OK: update entry")


def test_search():
    kb = AgentKnowledgeBase()
    kb.add_entry("Python Language", "interpreted", category="technical", tags=["core"])
    kb.add_entry("Git VCS", "version control", category="technical", tags=["core"])
    results = kb.search("Python")
    assert len(results) >= 1
    print("OK: search")


def test_get_by_category():
    kb = AgentKnowledgeBase()
    kb.add_entry("Python", "lang", category="technical")
    kb.add_entry("Scrum", "process", category="process")
    results = kb.get_by_category("technical")
    assert len(results) == 1
    print("OK: get by category")


def test_tags():
    kb = AgentKnowledgeBase()
    kb.add_entry("Python", "lang", category="technical", tags=["core", "lang"])
    kb.add_entry("Git", "vcs", category="technical", tags=["core", "tool"])
    tags = kb.get_all_tags()
    assert "core" in tags
    assert tags["core"] == 2
    by_tag = kb.get_by_tag("lang")
    assert len(by_tag) == 1
    print("OK: tags")


def test_remove_entry():
    kb = AgentKnowledgeBase()
    eid = kb.add_entry("Python", "lang", category="technical")
    assert kb.remove_entry(eid) is True
    assert kb.remove_entry(eid) is False
    print("OK: remove entry")


def test_list_entries():
    kb = AgentKnowledgeBase()
    kb.add_entry("E1", "c1", category="technical")
    kb.add_entry("E2", "c2", category="general")
    entries = kb.list_entries()
    assert len(entries) == 2
    print("OK: list entries")


def test_category_summary():
    kb = AgentKnowledgeBase()
    kb.add_entry("E1", "c1", category="technical")
    kb.add_entry("E2", "c2", category="technical")
    summary = kb.get_category_summary()
    assert len(summary) >= 1  # at least one category entry
    print("OK: category summary")


def test_callbacks():
    kb = AgentKnowledgeBase()
    fired = []
    kb.on_change("mon", lambda a, d: fired.append(a))
    kb.add_entry("E1", "c1", category="technical")
    assert len(fired) >= 1
    assert kb.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    kb = AgentKnowledgeBase()
    kb.add_entry("E1", "c1", category="technical")
    stats = kb.get_stats()
    assert stats["total_entries_created"] >= 1
    print("OK: stats")


def test_reset():
    kb = AgentKnowledgeBase()
    kb.add_entry("E1", "c1", category="technical")
    kb.reset()
    assert kb.list_entries() == []
    print("OK: reset")


def main():
    print("=== Agent Knowledge Base Tests ===\n")
    test_add_entry()
    test_update_entry()
    test_search()
    test_get_by_category()
    test_tags()
    test_remove_entry()
    test_list_entries()
    test_category_summary()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
