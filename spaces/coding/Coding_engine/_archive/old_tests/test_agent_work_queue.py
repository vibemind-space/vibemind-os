"""Test agent work queue -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_work_queue import AgentWorkQueue


def test_create_queue():
    wq = AgentWorkQueue()
    qid = wq.create_queue("agent-1")
    assert len(qid) > 0
    assert qid.startswith("awq-")
    print("OK: create queue")


def test_push():
    wq = AgentWorkQueue()
    wq.create_queue("agent-1")
    iid = wq.push("agent-1", "build-task", priority=5)
    assert len(iid) > 0
    print("OK: push")


def test_pop():
    wq = AgentWorkQueue()
    wq.create_queue("agent-1")
    wq.push("agent-1", "low-prio", priority=1)
    wq.push("agent-1", "high-prio", priority=10)
    item = wq.pop("agent-1")
    assert item is not None
    assert item["work_item"] == "high-prio"
    print("OK: pop")


def test_peek():
    wq = AgentWorkQueue()
    wq.create_queue("agent-1")
    wq.push("agent-1", "task-1", priority=5)
    item = wq.peek("agent-1")
    assert item is not None
    assert wq.get_queue_length("agent-1") == 1  # peek doesn't remove
    print("OK: peek")


def test_get_queue_length():
    wq = AgentWorkQueue()
    wq.create_queue("agent-1")
    wq.push("agent-1", "t1")
    wq.push("agent-1", "t2")
    wq.push("agent-1", "t3")
    assert wq.get_queue_length("agent-1") == 3
    print("OK: get queue length")


def test_clear_queue():
    wq = AgentWorkQueue()
    wq.create_queue("agent-1")
    wq.push("agent-1", "t1")
    wq.push("agent-1", "t2")
    removed = wq.clear_queue("agent-1")
    assert removed == 2
    assert wq.get_queue_length("agent-1") == 0
    print("OK: clear queue")


def test_empty_pop():
    wq = AgentWorkQueue()
    wq.create_queue("agent-1")
    assert wq.pop("agent-1") is None
    print("OK: empty pop")


def test_list_agents():
    wq = AgentWorkQueue()
    wq.create_queue("agent-1")
    wq.create_queue("agent-2")
    agents = wq.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    wq = AgentWorkQueue()
    fired = []
    wq.on_change("mon", lambda a, d: fired.append(a))
    wq.create_queue("agent-1")
    assert len(fired) >= 1
    assert wq.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    wq = AgentWorkQueue()
    wq.create_queue("agent-1")
    stats = wq.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    wq = AgentWorkQueue()
    wq.create_queue("agent-1")
    wq.reset()
    assert wq.get_queue_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Work Queue Tests ===\n")
    test_create_queue()
    test_push()
    test_pop()
    test_peek()
    test_get_queue_length()
    test_clear_queue()
    test_empty_pop()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
