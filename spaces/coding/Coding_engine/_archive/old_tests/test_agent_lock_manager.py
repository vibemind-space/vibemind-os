"""Test agent lock manager -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_lock_manager import AgentLockManager


def test_acquire_lock():
    lm = AgentLockManager()
    lid = lm.acquire_lock("agent-1", "database")
    assert len(lid) > 0
    assert lid.startswith("alm-")
    print("OK: acquire lock")


def test_acquire_lock_conflict():
    lm = AgentLockManager()
    lm.acquire_lock("agent-1", "database")
    lid2 = lm.acquire_lock("agent-2", "database")
    assert lid2 == ""  # conflict
    print("OK: acquire lock conflict")


def test_acquire_lock_same_agent():
    lm = AgentLockManager()
    lid1 = lm.acquire_lock("agent-1", "database")
    lid2 = lm.acquire_lock("agent-1", "database")
    assert len(lid2) > 0  # same agent can re-acquire
    print("OK: acquire lock same agent")


def test_release_lock():
    lm = AgentLockManager()
    lm.acquire_lock("agent-1", "database")
    assert lm.release_lock("agent-1", "database") is True
    assert lm.release_lock("agent-1", "nonexistent") is False
    print("OK: release lock")


def test_is_locked():
    lm = AgentLockManager()
    lm.acquire_lock("agent-1", "database")
    assert lm.is_locked("database") is True
    assert lm.is_locked("other") is False
    print("OK: is locked")


def test_get_lock_holder():
    lm = AgentLockManager()
    lm.acquire_lock("agent-1", "database")
    assert lm.get_lock_holder("database") == "agent-1"
    assert lm.get_lock_holder("other") == ""
    print("OK: get lock holder")


def test_get_locks():
    lm = AgentLockManager()
    lm.acquire_lock("agent-1", "database")
    lm.acquire_lock("agent-1", "cache")
    locks = lm.get_locks("agent-1")
    assert len(locks) == 2
    print("OK: get locks")


def test_get_lock_count():
    lm = AgentLockManager()
    lm.acquire_lock("agent-1", "database")
    lm.acquire_lock("agent-2", "cache")
    assert lm.get_lock_count() == 2
    assert lm.get_lock_count("agent-1") == 1
    print("OK: get lock count")


def test_list_agents():
    lm = AgentLockManager()
    lm.acquire_lock("agent-1", "database")
    lm.acquire_lock("agent-2", "cache")
    agents = lm.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    lm = AgentLockManager()
    fired = []
    lm.on_change("mon", lambda a, d: fired.append(a))
    lm.acquire_lock("agent-1", "database")
    assert len(fired) >= 1
    assert lm.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    lm = AgentLockManager()
    lm.acquire_lock("agent-1", "database")
    stats = lm.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    lm = AgentLockManager()
    lm.acquire_lock("agent-1", "database")
    lm.reset()
    assert lm.get_lock_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Lock Manager Tests ===\n")
    test_acquire_lock()
    test_acquire_lock_conflict()
    test_acquire_lock_same_agent()
    test_release_lock()
    test_is_locked()
    test_get_lock_holder()
    test_get_locks()
    test_get_lock_count()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 12 TESTS PASSED ===")


if __name__ == "__main__":
    main()
