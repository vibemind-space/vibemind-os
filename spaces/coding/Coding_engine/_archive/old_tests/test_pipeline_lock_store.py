"""Test pipeline lock store -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_lock_store import PipelineLockStore


def test_acquire():
    ls = PipelineLockStore()
    lid = ls.acquire("deploy-mutex", "agent-1", ttl=60)
    assert len(lid) > 0
    assert ls.acquire("deploy-mutex", "agent-2") == ""  # already locked
    print("OK: acquire")


def test_release():
    ls = PipelineLockStore()
    ls.acquire("deploy-mutex", "agent-1")
    assert ls.release("deploy-mutex", "agent-1") is True
    assert ls.release("deploy-mutex", "agent-1") is False  # already released
    print("OK: release")


def test_is_locked():
    ls = PipelineLockStore()
    assert ls.is_locked("res1") is False
    ls.acquire("res1", "agent-1")
    assert ls.is_locked("res1") is True
    print("OK: is locked")


def test_get_lock_info():
    ls = PipelineLockStore()
    ls.acquire("res1", "agent-1", ttl=120)
    info = ls.get_lock_info("res1")
    assert info is not None
    assert info["holder"] == "agent-1"
    print("OK: get lock info")


def test_get_holder_locks():
    ls = PipelineLockStore()
    ls.acquire("res1", "agent-1")
    ls.acquire("res2", "agent-1")
    ls.acquire("res3", "agent-2")
    locks = ls.get_holder_locks("agent-1")
    assert len(locks) == 2
    print("OK: get holder locks")


def test_force_release():
    ls = PipelineLockStore()
    ls.acquire("res1", "agent-1")
    assert ls.force_release("res1") is True
    assert ls.is_locked("res1") is False
    print("OK: force release")


def test_list_locks():
    ls = PipelineLockStore()
    ls.acquire("res1", "agent-1")
    ls.acquire("res2", "agent-2")
    locks = ls.list_locks()
    assert len(locks) == 2
    print("OK: list locks")


def test_cleanup_expired():
    ls = PipelineLockStore()
    ls.acquire("res1", "agent-1", ttl=0.01)
    import time
    time.sleep(0.02)
    count = ls.cleanup_expired()
    assert count >= 1
    assert ls.is_locked("res1") is False
    print("OK: cleanup expired")


def test_callbacks():
    ls = PipelineLockStore()
    fired = []
    ls.on_change("mon", lambda a, d: fired.append(a))
    ls.acquire("res1", "agent-1")
    assert len(fired) >= 1
    assert ls.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    ls = PipelineLockStore()
    ls.acquire("res1", "agent-1")
    stats = ls.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    ls = PipelineLockStore()
    ls.acquire("res1", "agent-1")
    ls.reset()
    assert ls.list_locks() == []
    print("OK: reset")


def main():
    print("=== Pipeline Lock Store Tests ===\n")
    test_acquire()
    test_release()
    test_is_locked()
    test_get_lock_info()
    test_get_holder_locks()
    test_force_release()
    test_list_locks()
    test_cleanup_expired()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
