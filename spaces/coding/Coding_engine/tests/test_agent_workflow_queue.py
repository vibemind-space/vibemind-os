"""Tests for AgentWorkflowQueue."""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.agent_workflow_queue import AgentWorkflowQueue


def test_enqueue_returns_id():
    q = AgentWorkflowQueue()
    item_id = q.enqueue("agent1", "build")
    assert isinstance(item_id, str)
    assert item_id.startswith("awq-")


def test_enqueue_creates_queued_item():
    q = AgentWorkflowQueue()
    item_id = q.enqueue("agent1", "deploy", priority=3, payload={"env": "prod"})
    item = q.get_item(item_id)
    assert item is not None
    assert item["agent_id"] == "agent1"
    assert item["workflow_name"] == "deploy"
    assert item["priority"] == 3
    assert item["payload"] == {"env": "prod"}
    assert item["status"] == "queued"
    assert item["started_at"] is None
    assert item["completed_at"] is None


def test_dequeue_returns_highest_priority():
    q = AgentWorkflowQueue()
    id_low = q.enqueue("a", "low", priority=10)
    id_high = q.enqueue("a", "high", priority=1)
    id_mid = q.enqueue("a", "mid", priority=5)
    result = q.dequeue()
    assert result is not None
    assert result["item_id"] == id_high
    assert result["status"] == "processing"


def test_dequeue_empty_returns_none():
    q = AgentWorkflowQueue()
    assert q.dequeue() is None


def test_dequeue_filters_by_agent_id():
    q = AgentWorkflowQueue()
    q.enqueue("agent1", "task1", priority=1)
    id2 = q.enqueue("agent2", "task2", priority=1)
    result = q.dequeue(agent_id="agent2")
    assert result is not None
    assert result["item_id"] == id2
    assert result["agent_id"] == "agent2"


def test_dequeue_sets_started_at():
    q = AgentWorkflowQueue()
    q.enqueue("a", "w")
    result = q.dequeue()
    assert result["started_at"] is not None
    assert result["started_at"] > 0


def test_complete():
    q = AgentWorkflowQueue()
    item_id = q.enqueue("a", "w")
    q.dequeue()
    assert q.complete(item_id, result={"ok": True}) is True
    item = q.get_item(item_id)
    assert item["status"] == "completed"
    assert item["completed_at"] is not None
    assert item["result"] == {"ok": True}


def test_complete_nonexistent_returns_false():
    q = AgentWorkflowQueue()
    assert q.complete("awq-doesnotexist") is False


def test_fail():
    q = AgentWorkflowQueue()
    item_id = q.enqueue("a", "w")
    q.dequeue()
    assert q.fail(item_id, error="timeout") is True
    item = q.get_item(item_id)
    assert item["status"] == "failed"
    assert item["error"] == "timeout"


def test_fail_nonexistent_returns_false():
    q = AgentWorkflowQueue()
    assert q.fail("awq-nope") is False


def test_requeue():
    q = AgentWorkflowQueue()
    item_id = q.enqueue("a", "w")
    q.dequeue()
    assert q.requeue(item_id) is True
    item = q.get_item(item_id)
    assert item["status"] == "queued"
    assert item["started_at"] is None
    assert item["completed_at"] is None


def test_requeue_nonexistent_returns_false():
    q = AgentWorkflowQueue()
    assert q.requeue("awq-gone") is False


def test_get_item_returns_none_for_missing():
    q = AgentWorkflowQueue()
    assert q.get_item("awq-missing") is None


def test_get_queue_no_filter():
    q = AgentWorkflowQueue()
    q.enqueue("a", "w1")
    q.enqueue("b", "w2")
    assert len(q.get_queue()) == 2


def test_get_queue_filter_by_agent():
    q = AgentWorkflowQueue()
    q.enqueue("a", "w1")
    q.enqueue("b", "w2")
    q.enqueue("a", "w3")
    results = q.get_queue(agent_id="a")
    assert len(results) == 2
    assert all(r["agent_id"] == "a" for r in results)


def test_get_queue_filter_by_status():
    q = AgentWorkflowQueue()
    id1 = q.enqueue("a", "w1")
    q.enqueue("a", "w2")
    q.dequeue()
    results = q.get_queue(status="processing")
    assert len(results) == 1
    assert results[0]["item_id"] == id1


def test_get_queue_length():
    q = AgentWorkflowQueue()
    q.enqueue("a", "w1")
    q.enqueue("a", "w2")
    q.enqueue("b", "w3")
    assert q.get_queue_length() == 3
    assert q.get_queue_length(agent_id="a") == 2
    assert q.get_queue_length(status="queued") == 3


def test_get_stats():
    q = AgentWorkflowQueue()
    q.enqueue("a", "w1")
    id2 = q.enqueue("a", "w2")
    id3 = q.enqueue("a", "w3")
    q.dequeue()  # w1 -> processing
    q.complete(id2)  # w2 -> completed (still queued, but mark it)
    q.fail(id3)  # w3 -> failed
    stats = q.get_stats()
    assert stats["total_items"] == 3
    assert stats["processing"] == 1


def test_reset():
    q = AgentWorkflowQueue()
    q.enqueue("a", "w1")
    q.enqueue("a", "w2")
    q.reset()
    assert q.get_queue_length() == 0
    assert q.get_stats()["total_items"] == 0


def test_on_change_callback():
    events = []
    q = AgentWorkflowQueue()
    q.on_change = lambda event, data: events.append((event, data))
    item_id = q.enqueue("a", "w")
    assert len(events) == 1
    assert events[0][0] == "enqueue"


def test_remove_callback():
    q = AgentWorkflowQueue()
    q._callbacks["mycb"] = lambda e, d: None
    assert q.remove_callback("mycb") is True
    assert q.remove_callback("mycb") is False


def test_generate_id_uniqueness():
    q = AgentWorkflowQueue()
    ids = set()
    for i in range(100):
        ids.add(q._generate_id(f"data{i}"))
    assert len(ids) == 100


def test_fire_catches_callback_exceptions():
    q = AgentWorkflowQueue()
    q.on_change = lambda e, d: (_ for _ in ()).throw(ValueError("boom"))
    q._callbacks["bad"] = lambda e, d: (_ for _ in ()).throw(RuntimeError("crash"))
    # Should not raise
    q.enqueue("a", "w")


def test_prune_removes_oldest():
    q = AgentWorkflowQueue()
    q.MAX_ENTRIES = 5
    for i in range(8):
        q.enqueue("a", f"w{i}")
    assert len(q._state.entries) == 5


if __name__ == "__main__":
    tests = [
        test_enqueue_returns_id,
        test_enqueue_creates_queued_item,
        test_dequeue_returns_highest_priority,
        test_dequeue_empty_returns_none,
        test_dequeue_filters_by_agent_id,
        test_dequeue_sets_started_at,
        test_complete,
        test_complete_nonexistent_returns_false,
        test_fail,
        test_fail_nonexistent_returns_false,
        test_requeue,
        test_requeue_nonexistent_returns_false,
        test_get_item_returns_none_for_missing,
        test_get_queue_no_filter,
        test_get_queue_filter_by_agent,
        test_get_queue_filter_by_status,
        test_get_queue_length,
        test_get_stats,
        test_reset,
        test_on_change_callback,
        test_remove_callback,
        test_generate_id_uniqueness,
        test_fire_catches_callback_exceptions,
        test_prune_removes_oldest,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as exc:
            print(f"FAIL {t.__name__}: {exc}")
    print(f"{passed}/{len(tests)} tests passed")
