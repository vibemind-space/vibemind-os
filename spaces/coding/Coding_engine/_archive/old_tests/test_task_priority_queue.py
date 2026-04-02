"""Test task priority queue."""
import sys
import time
sys.path.insert(0, ".")

from src.services.task_priority_queue import TaskPriorityQueue


def test_enqueue():
    """Enqueue tasks."""
    q = TaskPriorityQueue()
    tid = q.enqueue("Build project", priority=80, category="build",
                     tags={"ci", "core"}, metadata={"env": "prod"})
    assert tid.startswith("pq-")

    task = q.get_task(tid)
    assert task is not None
    assert task["name"] == "Build project"
    assert task["priority"] == 80
    assert task["category"] == "build"
    assert task["status"] == "queued"
    assert "ci" in task["tags"]
    print("OK: enqueue")


def test_dequeue_by_priority():
    """Higher priority dequeued first."""
    q = TaskPriorityQueue()
    q.enqueue("Low", priority=10)
    q.enqueue("High", priority=90)
    q.enqueue("Mid", priority=50)

    task = q.dequeue()
    assert task is not None
    assert task["name"] == "High"
    assert task["status"] == "assigned"

    task2 = q.dequeue()
    assert task2["name"] == "Mid"
    print("OK: dequeue by priority")


def test_dequeue_with_category():
    """Dequeue filtered by category."""
    q = TaskPriorityQueue()
    q.enqueue("Build", priority=80, category="build")
    q.enqueue("Test", priority=90, category="test")

    task = q.dequeue(category="build")
    assert task is not None
    assert task["name"] == "Build"
    print("OK: dequeue with category")


def test_dequeue_with_tags():
    """Dequeue filtered by tags."""
    q = TaskPriorityQueue()
    q.enqueue("A", priority=50, tags={"ci", "core"})
    q.enqueue("B", priority=80, tags={"ci"})

    # Requires both ci and core
    task = q.dequeue(tags={"ci", "core"})
    assert task is not None
    assert task["name"] == "A"
    print("OK: dequeue with tags")


def test_dequeue_assign_to():
    """Dequeue assigns to agent."""
    q = TaskPriorityQueue()
    q.enqueue("Task", priority=50)

    task = q.dequeue(assign_to="Builder")
    assert task["assigned_to"] == "Builder"
    print("OK: dequeue assign to")


def test_dequeue_empty():
    """Dequeue from empty queue."""
    q = TaskPriorityQueue()
    assert q.dequeue() is None
    print("OK: dequeue empty")


def test_dequeue_batch():
    """Batch dequeue."""
    q = TaskPriorityQueue()
    for i in range(5):
        q.enqueue(f"Task-{i}", priority=50 + i)

    batch = q.dequeue_batch(3, assign_to="Worker")
    assert len(batch) == 3
    # Highest priority first
    assert batch[0]["name"] == "Task-4"
    assert batch[1]["name"] == "Task-3"
    assert batch[2]["name"] == "Task-2"

    # Only 2 left
    batch2 = q.dequeue_batch(5)
    assert len(batch2) == 2
    print("OK: dequeue batch")


def test_complete():
    """Complete a task."""
    q = TaskPriorityQueue()
    tid = q.enqueue("Task")

    assert q.complete(tid) is True
    task = q.get_task(tid)
    assert task["status"] == "completed"

    # Can't complete again
    assert q.complete(tid) is False
    assert q.complete("fake") is False
    print("OK: complete")


def test_cancel():
    """Cancel a task."""
    q = TaskPriorityQueue()
    tid = q.enqueue("Task")

    assert q.cancel(tid) is True
    task = q.get_task(tid)
    assert task["status"] == "cancelled"

    assert q.cancel(tid) is False
    assert q.cancel("fake") is False
    print("OK: cancel")


def test_requeue():
    """Requeue an assigned task."""
    q = TaskPriorityQueue()
    tid = q.enqueue("Task", priority=50)
    q.dequeue(assign_to="Worker")

    assert q.requeue(tid, priority=80) is True
    task = q.get_task(tid)
    assert task["status"] == "queued"
    assert task["priority"] == 80
    assert task["assigned_to"] == ""

    # Can't requeue queued task
    assert q.requeue(tid) is False
    assert q.requeue("fake") is False
    print("OK: requeue")


def test_update_priority():
    """Update task priority."""
    q = TaskPriorityQueue()
    tid = q.enqueue("Task", priority=50)

    assert q.update_priority(tid, 90) is True
    task = q.get_task(tid)
    assert task["priority"] == 90

    # Can't update non-queued
    q.dequeue()
    assert q.update_priority(tid, 10) is False
    assert q.update_priority("fake", 10) is False
    print("OK: update priority")


def test_aging():
    """Priority increases with age."""
    q = TaskPriorityQueue(default_age_rate=1000.0)  # Fast aging for test
    tid = q.enqueue("Old", priority=10)
    time.sleep(0.1)
    q.enqueue("New", priority=50)

    # Old task should have aged enough to beat New (10 + 1000*0.1 = 110 > 50)
    task = q.dequeue()
    assert task["name"] == "Old"
    assert task["effective_priority"] > 10
    print("OK: aging")


def test_deadline_expiry():
    """Tasks expire past deadline."""
    q = TaskPriorityQueue()
    tid = q.enqueue("Urgent", priority=90, deadline_seconds=0.01)
    time.sleep(0.02)

    # Should be expired, dequeue returns None
    assert q.dequeue() is None
    task = q.get_task(tid)
    assert task["status"] == "expired"
    print("OK: deadline expiry")


def test_peek():
    """Peek without dequeuing."""
    q = TaskPriorityQueue()
    q.enqueue("Low", priority=10)
    q.enqueue("High", priority=90)

    top = q.peek(count=2)
    assert len(top) == 2
    assert top[0]["name"] == "High"
    assert top[1]["name"] == "Low"

    # Still queued
    assert q.queue_size() == 2
    print("OK: peek")


def test_list_tasks():
    """List tasks with filters."""
    q = TaskPriorityQueue()
    t1 = q.enqueue("A", category="build")
    t2 = q.enqueue("B", category="test")
    q.dequeue(assign_to="Worker")  # Assigns highest priority

    all_tasks = q.list_tasks()
    assert len(all_tasks) == 2

    queued = q.list_tasks(status="queued")
    assert len(queued) == 1

    assigned = q.list_tasks(assigned_to="Worker")
    assert len(assigned) == 1

    build = q.list_tasks(category="build")
    assert len(build) == 1

    limited = q.list_tasks(limit=1)
    assert len(limited) == 1
    print("OK: list tasks")


def test_queue_size():
    """Queue size counts only queued tasks."""
    q = TaskPriorityQueue()
    q.enqueue("A", category="build")
    q.enqueue("B", category="test")
    q.enqueue("C", category="build")

    assert q.queue_size() == 3
    assert q.queue_size(category="build") == 2
    assert q.queue_size(category="test") == 1

    q.dequeue()
    assert q.queue_size() == 2
    print("OK: queue size")


def test_list_categories():
    """List categories with counts."""
    q = TaskPriorityQueue()
    q.enqueue("A", category="build")
    q.enqueue("B", category="test")
    q.enqueue("C", category="build")

    cats = q.list_categories()
    assert cats["build"] == 2
    assert cats["test"] == 1
    print("OK: list categories")


def test_cleanup():
    """Cleanup removes finished tasks."""
    q = TaskPriorityQueue()
    t1 = q.enqueue("A")
    t2 = q.enqueue("B")
    t3 = q.enqueue("C")

    q.complete(t1)
    q.cancel(t2)

    removed = q.cleanup()
    assert removed == 2
    assert q.get_task(t1) is None
    assert q.get_task(t2) is None
    assert q.get_task(t3) is not None
    print("OK: cleanup")


def test_prune():
    """Prune when over max tasks."""
    q = TaskPriorityQueue(max_tasks=3)
    tids = []
    for i in range(3):
        tids.append(q.enqueue(f"T-{i}"))

    # Complete one to make it prunable
    q.complete(tids[0])

    # Add more to trigger prune
    q.enqueue("Extra")
    assert len(q._tasks) <= 3
    print("OK: prune")


def test_stats():
    """Stats are accurate."""
    q = TaskPriorityQueue()
    t1 = q.enqueue("A")
    t2 = q.enqueue("B")
    q.dequeue()
    q.complete(t1)
    q.cancel(t2)

    stats = q.get_stats()
    assert stats["total_enqueued"] == 2
    assert stats["total_dequeued"] == 1
    assert stats["total_completed"] == 1
    assert stats["total_cancelled"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    q = TaskPriorityQueue()
    q.enqueue("A")

    q.reset()
    assert q.list_tasks() == []
    assert q.queue_size() == 0
    stats = q.get_stats()
    assert stats["total_enqueued"] == 0
    print("OK: reset")


def main():
    print("=== Task Priority Queue Tests ===\n")
    test_enqueue()
    test_dequeue_by_priority()
    test_dequeue_with_category()
    test_dequeue_with_tags()
    test_dequeue_assign_to()
    test_dequeue_empty()
    test_dequeue_batch()
    test_complete()
    test_cancel()
    test_requeue()
    test_update_priority()
    test_aging()
    test_deadline_expiry()
    test_peek()
    test_list_tasks()
    test_queue_size()
    test_list_categories()
    test_cleanup()
    test_prune()
    test_stats()
    test_reset()
    print("\n=== ALL 21 TESTS PASSED ===")


if __name__ == "__main__":
    main()
