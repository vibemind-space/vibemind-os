"""Test agent resource pool -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_resource_pool import AgentResourcePool


def test_create_pool():
    rp = AgentResourcePool()
    pid = rp.create_pool("gpu-pool", capacity=10, resource_type="gpu")
    assert len(pid) > 0
    assert pid.startswith("arp-")
    print("OK: create pool")


def test_get_pool():
    rp = AgentResourcePool()
    pid = rp.create_pool("gpu-pool", capacity=10)
    pool = rp.get_pool(pid)
    assert pool is not None
    assert rp.get_pool("nonexistent") is None
    print("OK: get pool")


def test_acquire():
    rp = AgentResourcePool()
    rp.create_pool("gpu-pool", capacity=5)
    assert rp.acquire("gpu-pool", "agent-1", amount=3) is True
    assert rp.get_available("gpu-pool") == 2
    print("OK: acquire")


def test_acquire_exceeds_capacity():
    rp = AgentResourcePool()
    rp.create_pool("gpu-pool", capacity=3)
    assert rp.acquire("gpu-pool", "agent-1", amount=5) is False
    assert rp.get_available("gpu-pool") == 3
    print("OK: acquire exceeds capacity")


def test_release():
    rp = AgentResourcePool()
    rp.create_pool("gpu-pool", capacity=5)
    rp.acquire("gpu-pool", "agent-1", amount=3)
    assert rp.release("gpu-pool", "agent-1", amount=2) is True
    assert rp.get_available("gpu-pool") == 4
    print("OK: release")


def test_get_usage():
    rp = AgentResourcePool()
    rp.create_pool("gpu-pool", capacity=10)
    rp.acquire("gpu-pool", "agent-1", amount=3)
    rp.acquire("gpu-pool", "agent-2", amount=2)
    usage = rp.get_usage("gpu-pool")
    assert usage["agent-1"] == 3
    assert usage["agent-2"] == 2
    print("OK: get usage")


def test_list_pools():
    rp = AgentResourcePool()
    rp.create_pool("pool-1")
    rp.create_pool("pool-2")
    pools = rp.list_pools()
    assert "pool-1" in pools
    assert "pool-2" in pools
    print("OK: list pools")


def test_remove_pool():
    rp = AgentResourcePool()
    rp.create_pool("pool-1")
    assert rp.remove_pool("pool-1") is True
    assert rp.remove_pool("pool-1") is False
    print("OK: remove pool")


def test_callbacks():
    rp = AgentResourcePool()
    fired = []
    rp.on_change("mon", lambda a, d: fired.append(a))
    rp.create_pool("pool-1")
    assert len(fired) >= 1
    assert rp.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    rp = AgentResourcePool()
    rp.create_pool("pool-1")
    stats = rp.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    rp = AgentResourcePool()
    rp.create_pool("pool-1")
    rp.reset()
    assert rp.get_pool_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Resource Pool Tests ===\n")
    test_create_pool()
    test_get_pool()
    test_acquire()
    test_acquire_exceeds_capacity()
    test_release()
    test_get_usage()
    test_list_pools()
    test_remove_pool()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
