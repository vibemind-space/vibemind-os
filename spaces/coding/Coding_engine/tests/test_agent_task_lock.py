"""Tests for AgentTaskLock."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.agent_task_lock import AgentTaskLock


def test_acquire_basic():
    lock = AgentTaskLock()
    lid = lock.acquire("agent-1", "res-a", ttl_seconds=60)
    assert lid != ""
    assert lid.startswith("atl-")


def test_acquire_same_agent_same_resource():
    lock = AgentTaskLock()
    lid1 = lock.acquire("agent-1", "res-a")
    lid2 = lock.acquire("agent-1", "res-a")
    assert lid1 == lid2


def test_acquire_different_agent_blocked():
    lock = AgentTaskLock()
    lid1 = lock.acquire("agent-1", "res-a", ttl_seconds=60)
    assert lid1 != ""
    lid2 = lock.acquire("agent-2", "res-a", ttl_seconds=60)
    assert lid2 == ""


def test_acquire_after_release():
    lock = AgentTaskLock()
    lid1 = lock.acquire("agent-1", "res-a")
    lock.release(lid1)
    lid2 = lock.acquire("agent-2", "res-a")
    assert lid2 != ""


def test_release_basic():
    lock = AgentTaskLock()
    lid = lock.acquire("agent-1", "res-a")
    assert lock.release(lid) is True


def test_release_nonexistent():
    lock = AgentTaskLock()
    assert lock.release("atl-doesnotexist") is False


def test_release_already_released():
    lock = AgentTaskLock()
    lid = lock.acquire("agent-1", "res-a")
    lock.release(lid)
    assert lock.release(lid) is False


def test_is_locked():
    lock = AgentTaskLock()
    assert lock.is_locked("res-a") is False
    lid = lock.acquire("agent-1", "res-a")
    assert lock.is_locked("res-a") is True
    lock.release(lid)
    assert lock.is_locked("res-a") is False


def test_get_lock():
    lock = AgentTaskLock()
    lid = lock.acquire("agent-1", "res-a")
    entry = lock.get_lock(lid)
    assert entry["agent_id"] == "agent-1"
    assert entry["resource"] == "res-a"
    assert entry["status"] == "held"


def test_get_lock_missing():
    lock = AgentTaskLock()
    assert lock.get_lock("atl-nope") == {}


def test_get_locks_filter_agent():
    lock = AgentTaskLock()
    lock.acquire("agent-1", "res-a")
    lock.acquire("agent-2", "res-b")
    results = lock.get_locks(agent_id="agent-1")
    assert len(results) == 1
    assert results[0]["agent_id"] == "agent-1"


def test_get_locks_filter_status():
    lock = AgentTaskLock()
    lid = lock.acquire("agent-1", "res-a")
    lock.acquire("agent-1", "res-b")
    lock.release(lid)
    held = lock.get_locks(status="held")
    released = lock.get_locks(status="released")
    assert len(held) == 1
    assert len(released) == 1


def test_get_lock_holder():
    lock = AgentTaskLock()
    assert lock.get_lock_holder("res-a") == ""
    lock.acquire("agent-1", "res-a")
    assert lock.get_lock_holder("res-a") == "agent-1"


def test_renew():
    lock = AgentTaskLock()
    lid = lock.acquire("agent-1", "res-a", ttl_seconds=10)
    old_expires = lock.get_lock(lid)["expires_at"]
    time.sleep(0.05)
    assert lock.renew(lid, ttl_seconds=120) is True
    new_expires = lock.get_lock(lid)["expires_at"]
    assert new_expires > old_expires


def test_renew_released_fails():
    lock = AgentTaskLock()
    lid = lock.acquire("agent-1", "res-a")
    lock.release(lid)
    assert lock.renew(lid) is False


def test_get_lock_count():
    lock = AgentTaskLock()
    lock.acquire("agent-1", "res-a")
    lock.acquire("agent-2", "res-b")
    assert lock.get_lock_count() == 2
    assert lock.get_lock_count(agent_id="agent-1") == 1
    assert lock.get_lock_count(status="held") == 2


def test_cleanup_expired():
    lock = AgentTaskLock()
    lock.acquire("agent-1", "res-a", ttl_seconds=0.01)
    lock.acquire("agent-2", "res-b", ttl_seconds=0.01)
    lock.acquire("agent-3", "res-c", ttl_seconds=600)
    time.sleep(0.05)
    cleaned = lock.cleanup_expired()
    assert cleaned == 2
    assert lock.is_locked("res-c") is True


def test_get_stats():
    lock = AgentTaskLock()
    lock.acquire("agent-1", "res-a")
    lid2 = lock.acquire("agent-2", "res-b")
    lock.release(lid2)
    stats = lock.get_stats()
    assert stats["total_locks"] == 2
    assert stats["held_locks"] == 1
    assert stats["released_locks"] == 1


def test_reset():
    lock = AgentTaskLock()
    lock.acquire("agent-1", "res-a")
    lock.reset()
    assert lock.get_lock_count() == 0
    assert lock.is_locked("res-a") is False


def test_on_change_callback():
    events = []
    lock = AgentTaskLock()
    lock.on_change = lambda event, data: events.append(event)
    lid = lock.acquire("agent-1", "res-a")
    lock.release(lid)
    assert "acquired" in events
    assert "released" in events


def test_remove_callback():
    lock = AgentTaskLock()
    lock._callbacks["cb1"] = lambda e, d: None
    assert lock.remove_callback("cb1") is True
    assert lock.remove_callback("cb1") is False


def test_acquire_after_expiry():
    lock = AgentTaskLock()
    lock.acquire("agent-1", "res-a", ttl_seconds=0.01)
    time.sleep(0.05)
    lid2 = lock.acquire("agent-2", "res-a")
    assert lid2 != ""
    assert lock.get_lock_holder("res-a") == "agent-2"


def test_empty_agent_or_resource():
    lock = AgentTaskLock()
    assert lock.acquire("", "res-a") == ""
    assert lock.acquire("agent-1", "") == ""


if __name__ == "__main__":
    tests = [
        test_acquire_basic,
        test_acquire_same_agent_same_resource,
        test_acquire_different_agent_blocked,
        test_acquire_after_release,
        test_release_basic,
        test_release_nonexistent,
        test_release_already_released,
        test_is_locked,
        test_get_lock,
        test_get_lock_missing,
        test_get_locks_filter_agent,
        test_get_locks_filter_status,
        test_get_lock_holder,
        test_renew,
        test_renew_released_fails,
        test_get_lock_count,
        test_cleanup_expired,
        test_get_stats,
        test_reset,
        test_on_change_callback,
        test_remove_callback,
        test_acquire_after_expiry,
        test_empty_agent_or_resource,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
    print(f"{passed}/{len(tests)} tests passed")
