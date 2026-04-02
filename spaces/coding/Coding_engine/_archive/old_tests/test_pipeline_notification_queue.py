"""Test pipeline notification queue -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_notification_queue import PipelineNotificationQueue


def test_enqueue():
    nq = PipelineNotificationQueue()
    nid = nq.enqueue("pipeline-1", "alert", "Step failed", priority=5)
    assert len(nid) > 0
    assert nid.startswith("pnq-")
    print("OK: enqueue")


def test_dequeue():
    nq = PipelineNotificationQueue()
    nq.enqueue("pipeline-1", "info", "Started", priority=1)
    nq.enqueue("pipeline-1", "alert", "Critical", priority=10)
    item = nq.dequeue("pipeline-1")
    assert item is not None
    assert item["message"] == "Critical"  # highest priority first
    print("OK: dequeue")


def test_peek():
    nq = PipelineNotificationQueue()
    nq.enqueue("pipeline-1", "info", "msg1", priority=1)
    nq.enqueue("pipeline-1", "alert", "msg2", priority=5)
    item = nq.peek("pipeline-1")
    assert item is not None
    assert item["priority"] == 5
    assert nq.get_queue_length("pipeline-1") == 2  # peek doesn't remove
    print("OK: peek")


def test_dequeue_empty():
    nq = PipelineNotificationQueue()
    assert nq.dequeue("nonexistent") is None
    print("OK: dequeue empty")


def test_get_queue_length():
    nq = PipelineNotificationQueue()
    nq.enqueue("pipeline-1", "info", "msg1")
    nq.enqueue("pipeline-1", "info", "msg2")
    assert nq.get_queue_length("pipeline-1") == 2
    print("OK: get queue length")


def test_list_pipelines():
    nq = PipelineNotificationQueue()
    nq.enqueue("pipeline-1", "info", "msg")
    nq.enqueue("pipeline-2", "info", "msg")
    pipelines = nq.list_pipelines()
    assert "pipeline-1" in pipelines
    assert "pipeline-2" in pipelines
    print("OK: list pipelines")


def test_callbacks():
    nq = PipelineNotificationQueue()
    fired = []
    nq.on_change("mon", lambda a, d: fired.append(a))
    nq.enqueue("pipeline-1", "info", "msg")
    assert len(fired) >= 1
    assert nq.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    nq = PipelineNotificationQueue()
    nq.enqueue("pipeline-1", "info", "msg")
    stats = nq.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    nq = PipelineNotificationQueue()
    nq.enqueue("pipeline-1", "info", "msg")
    nq.reset()
    assert nq.get_total_queued() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Notification Queue Tests ===\n")
    test_enqueue()
    test_dequeue()
    test_peek()
    test_dequeue_empty()
    test_get_queue_length()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 9 TESTS PASSED ===")


if __name__ == "__main__":
    main()
