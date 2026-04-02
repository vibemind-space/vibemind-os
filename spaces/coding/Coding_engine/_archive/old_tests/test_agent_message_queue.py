"""Test agent message queue -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_message_queue import AgentMessageQueue


def test_create_queue():
    mq = AgentMessageQueue()
    qid = mq.create_queue("agent-1")
    assert len(qid) > 0
    assert qid.startswith("amq-")
    print("OK: create queue")


def test_enqueue():
    mq = AgentMessageQueue()
    mq.create_queue("agent-1")
    mid = mq.enqueue("agent-1", "hello world", priority=5, sender="agent-2")
    assert len(mid) > 0
    print("OK: enqueue")


def test_dequeue():
    mq = AgentMessageQueue()
    mq.create_queue("agent-1")
    mq.enqueue("agent-1", "low priority", priority=1)
    mq.enqueue("agent-1", "high priority", priority=10)
    msg = mq.dequeue("agent-1")
    assert msg is not None
    assert msg["message"] == "high priority"
    print("OK: dequeue")


def test_peek():
    mq = AgentMessageQueue()
    mq.create_queue("agent-1")
    mq.enqueue("agent-1", "test msg", priority=5)
    msg = mq.peek("agent-1")
    assert msg is not None
    assert mq.get_queue_size("agent-1") == 1  # peek doesn't remove
    print("OK: peek")


def test_empty_dequeue():
    mq = AgentMessageQueue()
    mq.create_queue("agent-1")
    assert mq.dequeue("agent-1") is None
    print("OK: empty dequeue")


def test_queue_size():
    mq = AgentMessageQueue()
    mq.create_queue("agent-1")
    mq.enqueue("agent-1", "msg1")
    mq.enqueue("agent-1", "msg2")
    mq.enqueue("agent-1", "msg3")
    assert mq.get_queue_size("agent-1") == 3
    print("OK: queue size")


def test_clear_queue():
    mq = AgentMessageQueue()
    mq.create_queue("agent-1")
    mq.enqueue("agent-1", "msg1")
    mq.enqueue("agent-1", "msg2")
    removed = mq.clear_queue("agent-1")
    assert removed == 2
    assert mq.get_queue_size("agent-1") == 0
    print("OK: clear queue")


def test_list_agents():
    mq = AgentMessageQueue()
    mq.create_queue("agent-1")
    mq.create_queue("agent-2")
    agents = mq.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    mq = AgentMessageQueue()
    fired = []
    mq.on_change("mon", lambda a, d: fired.append(a))
    mq.create_queue("agent-1")
    assert len(fired) >= 1
    assert mq.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    mq = AgentMessageQueue()
    mq.create_queue("agent-1")
    stats = mq.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    mq = AgentMessageQueue()
    mq.create_queue("agent-1")
    mq.enqueue("agent-1", "msg1")
    mq.reset()
    assert mq.get_message_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Message Queue Tests ===\n")
    test_create_queue()
    test_enqueue()
    test_dequeue()
    test_peek()
    test_empty_dequeue()
    test_queue_size()
    test_clear_queue()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
