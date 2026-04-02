"""Test agent connection pool -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_connection_pool import AgentConnectionPool


def test_create_pool():
    cp = AgentConnectionPool()
    pid = cp.create_pool("agent-1", max_connections=10)
    assert len(pid) > 0
    assert pid.startswith("acp-")
    print("OK: create pool")


def test_acquire():
    cp = AgentConnectionPool()
    cp.create_pool("agent-1", max_connections=5)
    assert cp.acquire("agent-1") is True
    assert cp.get_in_use("agent-1") == 1
    print("OK: acquire")


def test_release():
    cp = AgentConnectionPool()
    cp.create_pool("agent-1", max_connections=5)
    cp.acquire("agent-1")
    assert cp.release("agent-1") is True
    assert cp.get_in_use("agent-1") == 0
    print("OK: release")


def test_acquire_exhausted():
    cp = AgentConnectionPool()
    cp.create_pool("agent-1", max_connections=2)
    assert cp.acquire("agent-1") is True
    assert cp.acquire("agent-1") is True
    assert cp.acquire("agent-1") is False  # pool exhausted
    print("OK: acquire exhausted")


def test_get_available():
    cp = AgentConnectionPool()
    cp.create_pool("agent-1", max_connections=5)
    cp.acquire("agent-1")
    cp.acquire("agent-1")
    assert cp.get_available("agent-1") == 3
    print("OK: get available")


def test_get_pool_info():
    cp = AgentConnectionPool()
    cp.create_pool("agent-1", max_connections=10)
    info = cp.get_pool_info("agent-1")
    assert info is not None
    assert cp.get_pool_info("nonexistent") is None
    print("OK: get pool info")


def test_list_agents():
    cp = AgentConnectionPool()
    cp.create_pool("agent-1", max_connections=5)
    cp.create_pool("agent-2", max_connections=10)
    agents = cp.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    cp = AgentConnectionPool()
    fired = []
    cp.on_change("mon", lambda a, d: fired.append(a))
    cp.create_pool("agent-1")
    assert len(fired) >= 1
    assert cp.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    cp = AgentConnectionPool()
    cp.create_pool("agent-1")
    stats = cp.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    cp = AgentConnectionPool()
    cp.create_pool("agent-1")
    cp.reset()
    assert cp.get_pool_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Connection Pool Tests ===\n")
    test_create_pool()
    test_acquire()
    test_release()
    test_acquire_exhausted()
    test_get_available()
    test_get_pool_info()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")


if __name__ == "__main__":
    main()
