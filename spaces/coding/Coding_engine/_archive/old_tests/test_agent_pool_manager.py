"""Test agent pool manager."""
import sys
sys.path.insert(0, ".")

from src.services.agent_pool_manager import AgentPoolManager


def test_create_pool():
    """Create and list pools."""
    pm = AgentPoolManager()
    assert pm.create_pool("workers", tags=["gpu"]) is True
    assert pm.create_pool("workers") is False  # duplicate

    pools = pm.list_pools()
    assert len(pools) == 1
    assert pools[0]["pool_name"] == "workers"

    assert pm.remove_pool("workers") is True
    assert pm.remove_pool("workers") is False
    print("OK: create pool")


def test_max_pools():
    """Max pools enforced."""
    pm = AgentPoolManager(max_pools=2)
    pm.create_pool("a")
    pm.create_pool("b")
    assert pm.create_pool("c") is False
    print("OK: max pools")


def test_add_agent():
    """Add agent to pool."""
    pm = AgentPoolManager()
    pm.create_pool("workers")

    eid = pm.add_agent("workers", "agent1", tags=["fast"])
    assert eid.startswith("pe-")

    # duplicate agent_id rejected
    assert pm.add_agent("workers", "agent1") == ""

    # nonexistent pool
    assert pm.add_agent("nonexistent", "agent1") == ""
    print("OK: add agent")


def test_max_agents_per_pool():
    """Max agents per pool enforced."""
    pm = AgentPoolManager(max_agents_per_pool=2)
    pm.create_pool("workers")
    pm.add_agent("workers", "a1")
    pm.add_agent("workers", "a2")
    assert pm.add_agent("workers", "a3") == ""
    print("OK: max agents per pool")


def test_acquire_release():
    """Acquire and release agent."""
    pm = AgentPoolManager()
    pm.create_pool("workers")
    eid = pm.add_agent("workers", "agent1")

    result = pm.acquire("workers", requester="task1")
    assert result is not None
    assert result["agent_id"] == "agent1"
    assert result["entry_id"] == eid

    # No more idle agents
    assert pm.acquire("workers") is None

    # Release
    assert pm.release("workers", eid) is True
    assert pm.release("workers", eid) is False  # already idle

    # Can acquire again
    result = pm.acquire("workers")
    assert result is not None
    print("OK: acquire release")


def test_acquire_best_health():
    """Acquire picks highest health agent."""
    pm = AgentPoolManager()
    pm.create_pool("workers")
    eid1 = pm.add_agent("workers", "low")
    eid2 = pm.add_agent("workers", "high")

    pm.update_health("workers", eid1, 30.0)
    pm.update_health("workers", eid2, 90.0)

    result = pm.acquire("workers")
    assert result["agent_id"] == "high"
    print("OK: acquire best health")


def test_evict():
    """Evict agent from pool."""
    pm = AgentPoolManager()
    pm.create_pool("workers")
    eid = pm.add_agent("workers", "agent1")

    assert pm.evict("workers", eid) is True
    assert pm.evict("workers", eid) is False
    print("OK: evict")


def test_update_health():
    """Update health marks unhealthy."""
    pm = AgentPoolManager(min_health=20.0)
    pm.create_pool("workers")
    eid = pm.add_agent("workers", "agent1")

    assert pm.update_health("workers", eid, 10.0) is True
    info = pm.get_pool_info("workers")
    assert info["agents"][0]["status"] == "unhealthy"

    # Unhealthy agents not acquired
    assert pm.acquire("workers") is None
    print("OK: update health")


def test_evict_unhealthy():
    """Evict unhealthy agents."""
    pm = AgentPoolManager(min_health=20.0)
    pm.create_pool("workers")
    eid1 = pm.add_agent("workers", "a1")
    pm.add_agent("workers", "a2")

    pm.update_health("workers", eid1, 5.0)
    count = pm.evict_unhealthy("workers")
    assert count == 1
    assert pm.get_pool_info("workers")["size"] == 1
    print("OK: evict unhealthy")


def test_evict_idle():
    """Evict idle agents past timeout."""
    pm = AgentPoolManager(idle_timeout=0.001)
    pm.create_pool("workers")
    pm.add_agent("workers", "a1")

    import time
    time.sleep(0.01)
    count = pm.evict_idle("workers")
    assert count == 1
    print("OK: evict idle")


def test_get_pool_info():
    """Get pool info."""
    pm = AgentPoolManager()
    pm.create_pool("workers")
    pm.add_agent("workers", "a1")
    pm.add_agent("workers", "a2")

    info = pm.get_pool_info("workers")
    assert info is not None
    assert info["size"] == 2
    assert len(info["agents"]) == 2

    assert pm.get_pool_info("nonexistent") is None
    print("OK: get pool info")


def test_acquire_nonexistent():
    """Acquire from nonexistent pool."""
    pm = AgentPoolManager()
    assert pm.acquire("nonexistent") is None
    print("OK: acquire nonexistent")


def test_history():
    """History tracking."""
    pm = AgentPoolManager()
    pm.create_pool("workers")
    eid = pm.add_agent("workers", "a1")
    pm.acquire("workers")
    pm.release("workers", eid)

    hist = pm.get_history()
    assert len(hist) == 3  # added, acquired, released

    by_action = pm.get_history(action="acquired")
    assert len(by_action) == 1

    limited = pm.get_history(limit=1)
    assert len(limited) == 1
    print("OK: history")


def test_callback():
    """Callback fires on events."""
    pm = AgentPoolManager()
    fired = []
    pm.on_change("mon", lambda a, d: fired.append(a))

    pm.create_pool("workers")
    assert "pool_created" in fired

    pm.add_agent("workers", "a1")
    assert "agent_added" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    pm = AgentPoolManager()
    assert pm.on_change("mon", lambda a, d: None) is True
    assert pm.on_change("mon", lambda a, d: None) is False
    assert pm.remove_callback("mon") is True
    assert pm.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    pm = AgentPoolManager()
    pm.create_pool("workers")
    eid = pm.add_agent("workers", "a1")
    pm.add_agent("workers", "a2")
    pm.acquire("workers")

    stats = pm.get_stats()
    assert stats["total_pools"] == 1
    assert stats["total_agents"] == 2
    assert stats["total_idle"] == 1
    assert stats["total_acquired_now"] == 1
    assert stats["total_added"] == 2
    assert stats["total_acquired"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    pm = AgentPoolManager()
    pm.create_pool("workers")
    pm.add_agent("workers", "a1")

    pm.reset()
    assert pm.list_pools() == []
    stats = pm.get_stats()
    assert stats["total_pools"] == 0
    assert stats["total_added"] == 0
    print("OK: reset")


def main():
    print("=== Agent Pool Manager Tests ===\n")
    test_create_pool()
    test_max_pools()
    test_add_agent()
    test_max_agents_per_pool()
    test_acquire_release()
    test_acquire_best_health()
    test_evict()
    test_update_health()
    test_evict_unhealthy()
    test_evict_idle()
    test_get_pool_info()
    test_acquire_nonexistent()
    test_history()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 17 TESTS PASSED ===")


if __name__ == "__main__":
    main()
