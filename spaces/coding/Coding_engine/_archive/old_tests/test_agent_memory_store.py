"""Test agent memory store -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_memory_store import AgentMemoryStore


def test_store_memory():
    ms = AgentMemoryStore()
    mid = ms.store_memory("agent-1", "task_result", {"score": 95})
    assert len(mid) > 0
    assert mid.startswith("ams-")
    print("OK: store memory")


def test_get_memory():
    ms = AgentMemoryStore()
    mid = ms.store_memory("agent-1", "task_result", {"score": 95})
    mem = ms.get_memory(mid)
    assert mem is not None
    assert mem["agent_id"] == "agent-1"
    assert mem["key"] == "task_result"
    assert mem["value"]["score"] == 95
    assert ms.get_memory("nonexistent") is None
    print("OK: get memory")


def test_recall():
    ms = AgentMemoryStore()
    ms.store_memory("agent-1", "name", "Alice")
    ms.store_memory("agent-1", "name", "Bob")
    result = ms.recall("agent-1", "name")
    assert result == "Bob"
    assert ms.recall("agent-1", "nonexistent") is None
    print("OK: recall")


def test_get_agent_memories():
    ms = AgentMemoryStore()
    ms.store_memory("agent-1", "k1", "v1")
    ms.store_memory("agent-1", "k2", "v2")
    ms.store_memory("agent-2", "k1", "v3")
    mems = ms.get_agent_memories("agent-1")
    assert len(mems) == 2
    print("OK: get agent memories")


def test_search_memories():
    ms = AgentMemoryStore()
    ms.store_memory("agent-1", "k1", "v1", memory_type="episodic")
    ms.store_memory("agent-1", "k2", "v2", memory_type="semantic")
    ms.store_memory("agent-1", "k3", "v3", memory_type="episodic")
    results = ms.search_memories("agent-1", memory_type="episodic")
    assert len(results) == 2
    print("OK: search memories")


def test_forget():
    ms = AgentMemoryStore()
    mid = ms.store_memory("agent-1", "k1", "v1")
    assert ms.forget(mid) is True
    assert ms.forget(mid) is False
    print("OK: forget")


def test_forget_all():
    ms = AgentMemoryStore()
    ms.store_memory("agent-1", "k1", "v1")
    ms.store_memory("agent-1", "k2", "v2")
    ms.store_memory("agent-2", "k1", "v3")
    count = ms.forget_all("agent-1")
    assert count == 2
    assert ms.get_memory_count() == 1
    print("OK: forget all")


def test_list_agents():
    ms = AgentMemoryStore()
    ms.store_memory("agent-1", "k1", "v1")
    ms.store_memory("agent-2", "k1", "v2")
    agents = ms.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    ms = AgentMemoryStore()
    fired = []
    ms.on_change("mon", lambda a, d: fired.append(a))
    ms.store_memory("agent-1", "k1", "v1")
    assert len(fired) >= 1
    assert ms.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    ms = AgentMemoryStore()
    ms.store_memory("agent-1", "k1", "v1")
    stats = ms.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    ms = AgentMemoryStore()
    ms.store_memory("agent-1", "k1", "v1")
    ms.reset()
    assert ms.get_memory_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Memory Store Tests ===\n")
    test_store_memory()
    test_get_memory()
    test_recall()
    test_get_agent_memories()
    test_search_memories()
    test_forget()
    test_forget_all()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
