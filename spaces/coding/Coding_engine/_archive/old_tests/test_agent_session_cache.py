"""Test agent session cache -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_session_cache import AgentSessionCache


def test_cache_set():
    sc = AgentSessionCache()
    cid = sc.cache_set("agent-1", "token", "abc123", ttl_seconds=300.0)
    assert len(cid) > 0
    assert cid.startswith("asc-")
    print("OK: cache set")


def test_cache_get():
    sc = AgentSessionCache()
    sc.cache_set("agent-1", "token", "abc123", ttl_seconds=300.0)
    assert sc.cache_get("agent-1", "token") == "abc123"
    assert sc.cache_get("agent-1", "nonexistent") is None
    print("OK: cache get")


def test_cache_get_expired():
    sc = AgentSessionCache()
    sc.cache_set("agent-1", "token", "abc123", ttl_seconds=0.0)
    assert sc.cache_get("agent-1", "token") is None  # expired
    print("OK: cache get expired")


def test_cache_delete():
    sc = AgentSessionCache()
    sc.cache_set("agent-1", "token", "abc123")
    assert sc.cache_delete("agent-1", "token") is True
    assert sc.cache_delete("agent-1", "nonexistent") is False
    assert sc.cache_get("agent-1", "token") is None
    print("OK: cache delete")


def test_cache_has():
    sc = AgentSessionCache()
    sc.cache_set("agent-1", "token", "abc123", ttl_seconds=300.0)
    assert sc.cache_has("agent-1", "token") is True
    assert sc.cache_has("agent-1", "nonexistent") is False
    print("OK: cache has")


def test_cache_has_expired():
    sc = AgentSessionCache()
    sc.cache_set("agent-1", "token", "abc123", ttl_seconds=0.0)
    assert sc.cache_has("agent-1", "token") is False  # expired
    print("OK: cache has expired")


def test_get_cache_size():
    sc = AgentSessionCache()
    sc.cache_set("agent-1", "key1", "val1")
    sc.cache_set("agent-1", "key2", "val2")
    assert sc.get_cache_size("agent-1") == 2
    print("OK: get cache size")


def test_get_cache_count():
    sc = AgentSessionCache()
    sc.cache_set("agent-1", "key1", "val1")
    sc.cache_set("agent-2", "key2", "val2")
    assert sc.get_cache_count() == 2
    assert sc.get_cache_count("agent-1") == 1
    print("OK: get cache count")


def test_list_agents():
    sc = AgentSessionCache()
    sc.cache_set("agent-1", "key", "val")
    sc.cache_set("agent-2", "key", "val")
    agents = sc.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    sc = AgentSessionCache()
    fired = []
    sc.on_change("mon", lambda a, d: fired.append(a))
    sc.cache_set("agent-1", "key", "val")
    assert len(fired) >= 1
    assert sc.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    sc = AgentSessionCache()
    sc.cache_set("agent-1", "key", "val")
    stats = sc.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    sc = AgentSessionCache()
    sc.cache_set("agent-1", "key", "val")
    sc.reset()
    assert sc.get_cache_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Session Cache Tests ===\n")
    test_cache_set()
    test_cache_get()
    test_cache_get_expired()
    test_cache_delete()
    test_cache_has()
    test_cache_has_expired()
    test_get_cache_size()
    test_get_cache_count()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 12 TESTS PASSED ===")


if __name__ == "__main__":
    main()
