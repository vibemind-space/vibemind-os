"""Test pipeline queue store -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_queue_store import PipelineQueueStore


def test_enqueue():
    qs = PipelineQueueStore()
    eid = qs.enqueue("deploy", params={"env": "prod"}, priority=1)
    assert len(eid) > 0
    assert eid.startswith("pqs-")
    e = qs.get_entry(eid)
    assert e is not None
    assert e["pipeline_name"] == "deploy"
    assert e["status"] == "queued"
    print("OK: enqueue")


def test_dequeue():
    qs = PipelineQueueStore()
    qs.enqueue("low", priority=10)
    qs.enqueue("high", priority=1)
    item = qs.dequeue()
    assert item is not None
    # Should get highest priority (lowest number) first
    assert item["pipeline_name"] == "high"
    assert item["status"] == "processing"
    print("OK: dequeue")


def test_complete():
    qs = PipelineQueueStore()
    eid = qs.enqueue("task")
    qs.dequeue()
    assert qs.complete(eid, result={"output": 42}) is True
    e = qs.get_entry(eid)
    assert e["status"] == "completed"
    # Can't complete again
    assert qs.complete(eid) is False
    print("OK: complete")


def test_fail():
    qs = PipelineQueueStore()
    eid = qs.enqueue("task")
    qs.dequeue()
    assert qs.fail(eid, error="timeout") is True
    e = qs.get_entry(eid)
    assert e["status"] == "failed"
    print("OK: fail")


def test_cancel():
    qs = PipelineQueueStore()
    eid = qs.enqueue("task")
    assert qs.cancel(eid) is True
    # Can't cancel non-queued
    eid2 = qs.enqueue("task2")
    qs.dequeue()
    assert qs.cancel(eid2) is False
    print("OK: cancel")


def test_queue_size():
    qs = PipelineQueueStore()
    qs.enqueue("a")
    qs.enqueue("b")
    qs.enqueue("c")
    assert qs.get_queue_size() == 3
    qs.dequeue()
    assert qs.get_queue_size() == 2
    print("OK: queue size")


def test_list_entries():
    qs = PipelineQueueStore()
    qs.enqueue("a")
    eid = qs.enqueue("b")
    qs.dequeue()
    all_e = qs.list_entries()
    assert len(all_e) == 2
    queued = qs.list_entries(status="queued")
    assert len(queued) == 1
    print("OK: list entries")


def test_get_position():
    qs = PipelineQueueStore()
    e1 = qs.enqueue("first", priority=1)
    e2 = qs.enqueue("second", priority=2)
    pos1 = qs.get_position(e1)
    pos2 = qs.get_position(e2)
    assert pos1 >= 1
    assert pos2 >= 1
    print("OK: get position")


def test_requeue():
    qs = PipelineQueueStore()
    eid = qs.enqueue("task")
    qs.dequeue()
    qs.fail(eid, error="retry")
    assert qs.requeue(eid) is True
    e = qs.get_entry(eid)
    assert e["status"] == "queued"
    # Can't requeue non-failed
    assert qs.requeue(eid) is False
    print("OK: requeue")


def test_callbacks():
    qs = PipelineQueueStore()
    fired = []
    qs.on_change("mon", lambda a, d: fired.append(a))
    qs.enqueue("task")
    assert len(fired) >= 1
    assert qs.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    qs = PipelineQueueStore()
    qs.enqueue("task")
    stats = qs.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    qs = PipelineQueueStore()
    qs.enqueue("task")
    qs.reset()
    assert qs.get_queue_size() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Queue Store Tests ===\n")
    test_enqueue()
    test_dequeue()
    test_complete()
    test_fail()
    test_cancel()
    test_queue_size()
    test_list_entries()
    test_get_position()
    test_requeue()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 12 TESTS PASSED ===")


if __name__ == "__main__":
    main()
