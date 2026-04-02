"""Test agent priority queue -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_priority_queue import AgentPriorityQueue


def test_enqueue():
    pq = AgentPriorityQueue()
    eid = pq.enqueue("agent-1", "task-1", priority=5, payload={"type": "build"})
    assert len(eid) > 0
    assert eid.startswith("apq-")
    assert pq.get_task_count() >= 1
    print("OK: enqueue")


def test_dequeue():
    pq = AgentPriorityQueue()
    pq.enqueue("agent-1", "task-low", priority=1)
    pq.enqueue("agent-1", "task-high", priority=10)
    pq.enqueue("agent-1", "task-mid", priority=5)
    item = pq.dequeue("agent-1")
    assert item is not None
    assert item["task_name"] == "task-high"  # highest priority first
    print("OK: dequeue")


def test_dequeue_other_agent():
    pq = AgentPriorityQueue()
    pq.enqueue("agent-1", "t1", priority=5)
    pq.enqueue("agent-2", "t2", priority=10)
    item = pq.dequeue("agent-1")
    assert item is not None
    assert item["agent_id"] == "agent-1"
    print("OK: dequeue other agent")


def test_peek():
    pq = AgentPriorityQueue()
    pq.enqueue("agent-1", "t1", priority=5)
    item = pq.peek("agent-1")
    assert item is not None
    assert pq.get_queue_size("agent-1") == 1  # peek doesn't remove
    print("OK: peek")


def test_empty_dequeue():
    pq = AgentPriorityQueue()
    assert pq.dequeue("agent-1") is None
    print("OK: empty dequeue")


def test_get_task():
    pq = AgentPriorityQueue()
    eid = pq.enqueue("agent-1", "t1", priority=5)
    task = pq.get_task(eid)
    assert task is not None
    assert task["task_name"] == "t1"
    assert pq.get_task("nonexistent") is None
    print("OK: get task")


def test_cancel_task():
    pq = AgentPriorityQueue()
    eid = pq.enqueue("agent-1", "t1", priority=5)
    assert pq.cancel_task(eid) is True
    assert pq.cancel_task(eid) is False
    print("OK: cancel task")


def test_queue_size():
    pq = AgentPriorityQueue()
    pq.enqueue("agent-1", "t1")
    pq.enqueue("agent-1", "t2")
    pq.enqueue("agent-2", "t3")
    assert pq.get_queue_size("agent-1") == 2
    assert pq.get_queue_size("agent-2") == 1
    print("OK: queue size")


def test_list_agents():
    pq = AgentPriorityQueue()
    pq.enqueue("agent-1", "t1")
    pq.enqueue("agent-2", "t2")
    agents = pq.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    pq = AgentPriorityQueue()
    fired = []
    pq.on_change("mon", lambda a, d: fired.append(a))
    pq.enqueue("agent-1", "t1")
    assert len(fired) >= 1
    assert pq.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    pq = AgentPriorityQueue()
    pq.enqueue("agent-1", "t1")
    stats = pq.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    pq = AgentPriorityQueue()
    pq.enqueue("agent-1", "t1")
    pq.reset()
    assert pq.get_task_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Priority Queue Tests ===\n")
    test_enqueue()
    test_dequeue()
    test_dequeue_other_agent()
    test_peek()
    test_empty_dequeue()
    test_get_task()
    test_cancel_task()
    test_queue_size()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 12 TESTS PASSED ===")


if __name__ == "__main__":
    main()
