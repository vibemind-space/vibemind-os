"""Test agent batch executor -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_batch_executor import AgentBatchExecutor


def test_create_batch():
    be = AgentBatchExecutor()
    bid = be.create_batch("agent-1", ["task_a", "task_b", "task_c"])
    assert len(bid) > 0
    assert bid.startswith("abe-")
    print("OK: create batch")


def test_execute_batch():
    be = AgentBatchExecutor()
    bid = be.create_batch("agent-1", ["task_a", "task_b"])
    result = be.execute_batch(bid)
    assert result["status"] == "completed"
    assert result["task_count"] == 2
    print("OK: execute batch")


def test_get_batch():
    be = AgentBatchExecutor()
    bid = be.create_batch("agent-1", ["task_a"])
    batch = be.get_batch(bid)
    assert batch is not None
    assert batch["status"] == "pending"
    assert be.get_batch("nonexistent") is None
    print("OK: get batch")


def test_get_batches():
    be = AgentBatchExecutor()
    be.create_batch("agent-1", ["task_a"])
    be.create_batch("agent-1", ["task_b"])
    batches = be.get_batches("agent-1")
    assert len(batches) == 2
    print("OK: get batches")


def test_get_batch_count():
    be = AgentBatchExecutor()
    be.create_batch("agent-1", ["task_a"])
    be.create_batch("agent-2", ["task_b"])
    assert be.get_batch_count() == 2
    assert be.get_batch_count("agent-1") == 1
    print("OK: get batch count")


def test_list_agents():
    be = AgentBatchExecutor()
    be.create_batch("agent-1", ["task_a"])
    be.create_batch("agent-2", ["task_b"])
    agents = be.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    be = AgentBatchExecutor()
    fired = []
    be.on_change("mon", lambda a, d: fired.append(a))
    be.create_batch("agent-1", ["task_a"])
    assert len(fired) >= 1
    assert be.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    be = AgentBatchExecutor()
    be.create_batch("agent-1", ["task_a"])
    stats = be.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    be = AgentBatchExecutor()
    be.create_batch("agent-1", ["task_a"])
    be.reset()
    assert be.get_batch_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Batch Executor Tests ===\n")
    test_create_batch()
    test_execute_batch()
    test_get_batch()
    test_get_batches()
    test_get_batch_count()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 9 TESTS PASSED ===")


if __name__ == "__main__":
    main()
