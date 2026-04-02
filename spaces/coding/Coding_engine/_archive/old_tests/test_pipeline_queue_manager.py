"""Test pipeline queue manager."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_queue_manager import PipelineQueueManager


def test_create_queue():
    """Create and retrieve queue."""
    qm = PipelineQueueManager()
    qid = qm.create_queue("builds", tags=["ci"])
    assert qid.startswith("que-")

    q = qm.get_queue(qid)
    assert q is not None
    assert q["name"] == "builds"
    assert q["size"] == 0

    assert qm.remove_queue(qid) is True
    assert qm.remove_queue(qid) is False
    print("OK: create queue")


def test_invalid_queue():
    """Invalid queue rejected."""
    qm = PipelineQueueManager()
    assert qm.create_queue("") == ""
    assert qm.create_queue("x", max_size=0) == ""
    print("OK: invalid queue")


def test_duplicate():
    """Duplicate name rejected."""
    qm = PipelineQueueManager()
    qm.create_queue("builds")
    assert qm.create_queue("builds") == ""
    print("OK: duplicate")


def test_max_queues():
    """Max queues enforced."""
    qm = PipelineQueueManager(max_queues=2)
    qm.create_queue("a")
    qm.create_queue("b")
    assert qm.create_queue("c") == ""
    print("OK: max queues")


def test_enqueue_dequeue():
    """Enqueue and dequeue items."""
    qm = PipelineQueueManager()
    qid = qm.create_queue("tasks")

    iid = qm.enqueue(qid, payload={"task": "build"}, priority=5)
    assert iid.startswith("itm-")
    assert qm.queue_size(qid) == 1

    item = qm.dequeue(qid)
    assert item is not None
    assert item["payload"]["task"] == "build"
    assert item["priority"] == 5
    assert qm.queue_size(qid) == 0
    print("OK: enqueue dequeue")


def test_priority_order():
    """Higher priority dequeued first."""
    qm = PipelineQueueManager()
    qid = qm.create_queue("tasks")

    qm.enqueue(qid, payload="low", priority=1)
    qm.enqueue(qid, payload="high", priority=10)
    qm.enqueue(qid, payload="mid", priority=5)

    item1 = qm.dequeue(qid)
    assert item1["payload"] == "high"
    item2 = qm.dequeue(qid)
    assert item2["payload"] == "mid"
    item3 = qm.dequeue(qid)
    assert item3["payload"] == "low"
    print("OK: priority order")


def test_dequeue_empty():
    """Dequeue from empty queue returns None."""
    qm = PipelineQueueManager()
    qid = qm.create_queue("tasks")
    assert qm.dequeue(qid) is None
    assert qm.dequeue("nonexistent") is None
    print("OK: dequeue empty")


def test_peek():
    """Peek at front of queue."""
    qm = PipelineQueueManager()
    qid = qm.create_queue("tasks")
    qm.enqueue(qid, payload="first", priority=10)
    qm.enqueue(qid, payload="second", priority=5)

    item = qm.peek(qid)
    assert item is not None
    assert item["payload"] == "first"
    # peek should not remove
    assert qm.queue_size(qid) == 2

    assert qm.peek("nonexistent") is None
    print("OK: peek")


def test_max_size():
    """Queue max size enforced."""
    qm = PipelineQueueManager()
    qid = qm.create_queue("tasks", max_size=2)
    qm.enqueue(qid, payload="a")
    qm.enqueue(qid, payload="b")
    assert qm.enqueue(qid, payload="c") == ""

    q = qm.get_queue(qid)
    assert q["total_dropped"] == 1
    print("OK: max size")


def test_purge():
    """Purge queue removes all items."""
    qm = PipelineQueueManager()
    qid = qm.create_queue("tasks")
    qm.enqueue(qid, payload="a")
    qm.enqueue(qid, payload="b")

    count = qm.purge_queue(qid)
    assert count == 2
    assert qm.queue_size(qid) == 0
    assert qm.purge_queue("nonexistent") == 0
    print("OK: purge")


def test_get_by_name():
    """Get queue by name."""
    qm = PipelineQueueManager()
    qm.create_queue("builds")

    q = qm.get_queue_by_name("builds")
    assert q is not None
    assert q["name"] == "builds"
    assert qm.get_queue_by_name("nonexistent") is None
    print("OK: get by name")


def test_list_queues():
    """List queues with tag filter."""
    qm = PipelineQueueManager()
    qm.create_queue("builds", tags=["ci"])
    qm.create_queue("deploys")

    all_q = qm.list_queues()
    assert len(all_q) == 2

    by_tag = qm.list_queues(tag="ci")
    assert len(by_tag) == 1
    print("OK: list queues")


def test_enqueue_nonexistent():
    """Enqueue to nonexistent queue."""
    qm = PipelineQueueManager()
    assert qm.enqueue("nonexistent", payload="x") == ""
    print("OK: enqueue nonexistent")


def test_callback():
    """Callback fires on events."""
    qm = PipelineQueueManager()
    fired = []
    qm.on_change("mon", lambda a, d: fired.append(a))

    qid = qm.create_queue("tasks")
    assert "queue_created" in fired

    qm.enqueue(qid, payload="x")
    assert "item_enqueued" in fired

    qm.dequeue(qid)
    assert "item_dequeued" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    qm = PipelineQueueManager()
    assert qm.on_change("mon", lambda a, d: None) is True
    assert qm.on_change("mon", lambda a, d: None) is False
    assert qm.remove_callback("mon") is True
    assert qm.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    qm = PipelineQueueManager()
    qid = qm.create_queue("tasks")
    qm.enqueue(qid, payload="a")
    qm.enqueue(qid, payload="b")
    qm.dequeue(qid)

    stats = qm.get_stats()
    assert stats["total_queues"] == 1
    assert stats["total_enqueued"] == 2
    assert stats["total_dequeued"] == 1
    assert stats["total_items"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    qm = PipelineQueueManager()
    qm.create_queue("tasks")

    qm.reset()
    assert qm.list_queues() == []
    stats = qm.get_stats()
    assert stats["current_queues"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Queue Manager Tests ===\n")
    test_create_queue()
    test_invalid_queue()
    test_duplicate()
    test_max_queues()
    test_enqueue_dequeue()
    test_priority_order()
    test_dequeue_empty()
    test_peek()
    test_max_size()
    test_purge()
    test_get_by_name()
    test_list_queues()
    test_enqueue_nonexistent()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 17 TESTS PASSED ===")


if __name__ == "__main__":
    main()
