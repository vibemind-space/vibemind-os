"""Test pipeline concurrency manager."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_concurrency_manager import PipelineConcurrencyManager


def test_create_semaphore():
    """Create and retrieve semaphore."""
    cm = PipelineConcurrencyManager()
    sid = cm.create_semaphore("db_pool", max_permits=3, tags=["db"])
    assert sid.startswith("sem-")

    s = cm.get_semaphore(sid)
    assert s is not None
    assert s["name"] == "db_pool"
    assert s["max_permits"] == 3
    assert s["available"] == 3
    assert s["holders"] == []

    assert cm.remove_semaphore(sid) is True
    assert cm.remove_semaphore(sid) is False
    print("OK: create semaphore")


def test_invalid_semaphore():
    """Invalid semaphore rejected."""
    cm = PipelineConcurrencyManager()
    assert cm.create_semaphore("") == ""
    assert cm.create_semaphore("x", max_permits=0) == ""
    print("OK: invalid semaphore")


def test_duplicate_name():
    """Duplicate name rejected."""
    cm = PipelineConcurrencyManager()
    cm.create_semaphore("lock")
    assert cm.create_semaphore("lock") == ""
    print("OK: duplicate name")


def test_max_semaphores():
    """Max semaphores enforced."""
    cm = PipelineConcurrencyManager(max_semaphores=2)
    cm.create_semaphore("a")
    cm.create_semaphore("b")
    assert cm.create_semaphore("c") == ""
    print("OK: max semaphores")


def test_acquire_release():
    """Basic acquire and release."""
    cm = PipelineConcurrencyManager()
    sid = cm.create_semaphore("lock", max_permits=1)

    assert cm.try_acquire(sid, "agent_a") is True
    assert cm.get_semaphore(sid)["available"] == 0
    assert cm.get_semaphore(sid)["holders"] == ["agent_a"]

    assert cm.release(sid, "agent_a") is True
    assert cm.get_semaphore(sid)["available"] == 1
    assert cm.get_semaphore(sid)["holders"] == []
    print("OK: acquire release")


def test_multi_permit():
    """Multiple permits semaphore."""
    cm = PipelineConcurrencyManager()
    sid = cm.create_semaphore("pool", max_permits=2)

    assert cm.try_acquire(sid, "a") is True
    assert cm.try_acquire(sid, "b") is True
    assert cm.try_acquire(sid, "c") is False  # no permits
    assert "c" in cm.get_semaphore(sid)["waiters"]
    print("OK: multi permit")


def test_double_acquire():
    """Same holder can't acquire twice."""
    cm = PipelineConcurrencyManager()
    sid = cm.create_semaphore("lock")

    assert cm.try_acquire(sid, "a") is True
    assert cm.try_acquire(sid, "a") is False  # already holding
    print("OK: double acquire")


def test_waiter_promotion():
    """Waiter gets promoted on release."""
    cm = PipelineConcurrencyManager()
    sid = cm.create_semaphore("lock", max_permits=1)

    cm.try_acquire(sid, "a")
    cm.try_acquire(sid, "b")  # goes to waiters

    cm.release(sid, "a")
    s = cm.get_semaphore(sid)
    assert "b" in s["holders"]
    assert s["available"] == 0
    assert s["waiters"] == []
    print("OK: waiter promotion")


def test_cancel_wait():
    """Cancel a wait."""
    cm = PipelineConcurrencyManager()
    sid = cm.create_semaphore("lock")

    cm.try_acquire(sid, "a")
    cm.try_acquire(sid, "b")  # waiter

    assert cm.cancel_wait(sid, "b") is True
    assert cm.get_semaphore(sid)["waiters"] == []
    assert cm.cancel_wait(sid, "b") is False
    print("OK: cancel wait")


def test_force_release():
    """Force release all."""
    cm = PipelineConcurrencyManager()
    sid = cm.create_semaphore("lock", max_permits=2)

    cm.try_acquire(sid, "a")
    cm.try_acquire(sid, "b")
    cm.try_acquire(sid, "c")  # waiter

    count = cm.force_release_all(sid)
    assert count == 2
    s = cm.get_semaphore(sid)
    assert s["available"] == 2
    assert s["holders"] == []
    assert s["waiters"] == []
    print("OK: force release")


def test_release_invalid():
    """Release by non-holder fails."""
    cm = PipelineConcurrencyManager()
    sid = cm.create_semaphore("lock")
    assert cm.release(sid, "nobody") is False
    print("OK: release invalid")


def test_get_by_name():
    """Get semaphore by name."""
    cm = PipelineConcurrencyManager()
    cm.create_semaphore("my_lock")

    s = cm.get_semaphore_by_name("my_lock")
    assert s is not None
    assert s["name"] == "my_lock"
    assert cm.get_semaphore_by_name("nonexistent") is None
    print("OK: get by name")


def test_list_semaphores():
    """List semaphores with filters."""
    cm = PipelineConcurrencyManager()
    sid1 = cm.create_semaphore("a", tags=["db"])
    sid2 = cm.create_semaphore("b")

    cm.try_acquire(sid2, "x")
    cm.try_acquire(sid2, "y")  # y is waiter since max_permits=1

    all_s = cm.list_semaphores()
    assert len(all_s) == 2

    by_tag = cm.list_semaphores(tag="db")
    assert len(by_tag) == 1

    with_waiters = cm.list_semaphores(has_waiters=True)
    assert len(with_waiters) == 1

    no_waiters = cm.list_semaphores(has_waiters=False)
    assert len(no_waiters) == 1
    print("OK: list semaphores")


def test_detect_deadlocks():
    """Detect circular waits."""
    cm = PipelineConcurrencyManager()
    s1 = cm.create_semaphore("lock1")
    s2 = cm.create_semaphore("lock2")

    # a holds lock1, waits for lock2
    cm.try_acquire(s1, "a")
    cm.try_acquire(s2, "b")
    cm.try_acquire(s2, "a")  # a waits for lock2 (held by b)
    cm.try_acquire(s1, "b")  # b waits for lock1 (held by a) -> deadlock!

    cycles = cm.detect_deadlocks()
    assert len(cycles) > 0
    print("OK: detect deadlocks")


def test_no_deadlock():
    """No deadlock detected when none exists."""
    cm = PipelineConcurrencyManager()
    s1 = cm.create_semaphore("lock1")

    cm.try_acquire(s1, "a")
    cm.try_acquire(s1, "b")  # waits for a, but no cycle

    cycles = cm.detect_deadlocks()
    assert len(cycles) == 0
    print("OK: no deadlock")


def test_callback():
    """Callback fires on events."""
    cm = PipelineConcurrencyManager()
    fired = []
    cm.on_change("mon", lambda a, d: fired.append(a))

    sid = cm.create_semaphore("lock")
    assert "semaphore_created" in fired

    cm.try_acquire(sid, "a")
    assert "permit_acquired" in fired

    cm.release(sid, "a")
    assert "permit_released" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    cm = PipelineConcurrencyManager()
    assert cm.on_change("mon", lambda a, d: None) is True
    assert cm.on_change("mon", lambda a, d: None) is False
    assert cm.remove_callback("mon") is True
    assert cm.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    cm = PipelineConcurrencyManager()
    sid = cm.create_semaphore("lock")
    cm.try_acquire(sid, "a")
    cm.try_acquire(sid, "b")  # contention
    cm.cancel_wait(sid, "b")  # timeout
    cm.release(sid, "a")

    stats = cm.get_stats()
    assert stats["total_semaphores"] == 1
    assert stats["total_acquires"] == 1
    assert stats["total_releases"] == 1
    assert stats["total_timeouts"] == 1
    assert stats["total_contentions"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    cm = PipelineConcurrencyManager()
    cm.create_semaphore("lock")

    cm.reset()
    assert cm.list_semaphores() == []
    stats = cm.get_stats()
    assert stats["current_semaphores"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Concurrency Manager Tests ===\n")
    test_create_semaphore()
    test_invalid_semaphore()
    test_duplicate_name()
    test_max_semaphores()
    test_acquire_release()
    test_multi_permit()
    test_double_acquire()
    test_waiter_promotion()
    test_cancel_wait()
    test_force_release()
    test_release_invalid()
    test_get_by_name()
    test_list_semaphores()
    test_detect_deadlocks()
    test_no_deadlock()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 19 TESTS PASSED ===")


if __name__ == "__main__":
    main()
