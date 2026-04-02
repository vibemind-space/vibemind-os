"""Test agent execution context -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_execution_context import AgentExecutionContext


def test_create_context():
    ec = AgentExecutionContext()
    cid = ec.create_context("agent-1", "exec-001", metadata={"task": "build"})
    assert len(cid) > 0
    assert cid.startswith("aec-")
    print("OK: create context")


def test_get_context():
    ec = AgentExecutionContext()
    cid = ec.create_context("agent-1", "exec-001")
    ctx = ec.get_context(cid)
    assert ctx is not None
    assert ctx["context_id"] == cid
    assert ctx["agent_id"] == "agent-1"
    assert ctx["execution_id"] == "exec-001"
    assert ec.get_context("nonexistent") is None
    print("OK: get context")


def test_set_get_variable():
    ec = AgentExecutionContext()
    cid = ec.create_context("agent-1", "exec-001")
    assert ec.set_variable(cid, "key1", "value1") is True
    assert ec.get_variable(cid, "key1") == "value1"
    assert ec.get_variable(cid, "missing", default="def") == "def"
    assert ec.set_variable("nonexistent", "k", "v") is False
    print("OK: set/get variable")


def test_get_all_variables():
    ec = AgentExecutionContext()
    cid = ec.create_context("agent-1", "exec-001")
    ec.set_variable(cid, "a", 1)
    ec.set_variable(cid, "b", 2)
    vars = ec.get_all_variables(cid)
    assert vars["a"] == 1
    assert vars["b"] == 2
    print("OK: get all variables")


def test_update_status():
    ec = AgentExecutionContext()
    cid = ec.create_context("agent-1", "exec-001")
    assert ec.update_status(cid, "running") is True
    ctx = ec.get_context(cid)
    assert ctx["status"] == "running"
    assert ec.update_status("nonexistent", "x") is False
    print("OK: update status")


def test_get_agent_contexts():
    ec = AgentExecutionContext()
    ec.create_context("agent-1", "exec-001")
    ec.create_context("agent-1", "exec-002")
    ec.create_context("agent-2", "exec-003")
    ctxs = ec.get_agent_contexts("agent-1")
    assert len(ctxs) == 2
    print("OK: get agent contexts")


def test_close_context():
    ec = AgentExecutionContext()
    cid = ec.create_context("agent-1", "exec-001")
    assert ec.close_context(cid) is True
    ctx = ec.get_context(cid)
    assert ctx["status"] == "completed"
    assert ec.close_context("nonexistent") is False
    print("OK: close context")


def test_get_active_contexts():
    ec = AgentExecutionContext()
    c1 = ec.create_context("agent-1", "exec-001")
    c2 = ec.create_context("agent-1", "exec-002")
    ec.close_context(c1)
    active = ec.get_active_contexts("agent-1")
    assert len(active) == 1
    print("OK: get active contexts")


def test_list_agents():
    ec = AgentExecutionContext()
    ec.create_context("agent-1", "exec-001")
    ec.create_context("agent-2", "exec-002")
    agents = ec.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_get_context_count():
    ec = AgentExecutionContext()
    ec.create_context("agent-1", "exec-001")
    ec.create_context("agent-1", "exec-002")
    assert ec.get_context_count("agent-1") == 2
    assert ec.get_context_count() >= 2
    print("OK: get context count")


def test_callbacks():
    ec = AgentExecutionContext()
    fired = []
    ec.on_change("mon", lambda a, d: fired.append(a))
    ec.create_context("agent-1", "exec-001")
    assert len(fired) >= 1
    assert ec.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    ec = AgentExecutionContext()
    ec.create_context("agent-1", "exec-001")
    stats = ec.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    ec = AgentExecutionContext()
    ec.create_context("agent-1", "exec-001")
    ec.reset()
    assert ec.get_context_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Execution Context Tests ===\n")
    test_create_context()
    test_get_context()
    test_set_get_variable()
    test_get_all_variables()
    test_update_status()
    test_get_agent_contexts()
    test_close_context()
    test_get_active_contexts()
    test_list_agents()
    test_get_context_count()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 13 TESTS PASSED ===")


if __name__ == "__main__":
    main()
