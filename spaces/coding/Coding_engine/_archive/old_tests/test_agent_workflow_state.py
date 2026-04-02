"""Test agent workflow state -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_workflow_state import AgentWorkflowState


def test_save_state():
    ws = AgentWorkflowState()
    sid = ws.save_state("agent-1", "wf-deploy", {"step": "build", "progress": 50}, step="build")
    assert len(sid) > 0
    assert sid.startswith("aws-")
    s = ws.get_state("agent-1", "wf-deploy")
    assert s is not None
    assert s["agent_id"] == "agent-1"
    print("OK: save state")


def test_overwrite_state():
    ws = AgentWorkflowState()
    ws.save_state("agent-1", "wf-1", {"step": "build"})
    ws.save_state("agent-1", "wf-1", {"step": "test"})
    s = ws.get_state("agent-1", "wf-1")
    assert s["state_data"]["step"] == "test"
    print("OK: overwrite state")


def test_get_agent_states():
    ws = AgentWorkflowState()
    ws.save_state("agent-1", "wf-1", {"s": 1})
    ws.save_state("agent-1", "wf-2", {"s": 2})
    ws.save_state("agent-2", "wf-1", {"s": 3})
    states = ws.get_agent_states("agent-1")
    assert len(states) == 2
    print("OK: get agent states")


def test_delete_state():
    ws = AgentWorkflowState()
    ws.save_state("agent-1", "wf-1", {"s": 1})
    assert ws.delete_state("agent-1", "wf-1") is True
    assert ws.delete_state("agent-1", "wf-1") is False
    print("OK: delete state")


def test_clear_agent_states():
    ws = AgentWorkflowState()
    ws.save_state("agent-1", "wf-1", {"s": 1})
    ws.save_state("agent-1", "wf-2", {"s": 2})
    count = ws.clear_agent_states("agent-1")
    assert count == 2
    assert ws.get_state_count("agent-1") == 0
    print("OK: clear agent states")


def test_list_agents():
    ws = AgentWorkflowState()
    ws.save_state("agent-1", "wf-1", {})
    ws.save_state("agent-2", "wf-1", {})
    agents = ws.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_list_workflows():
    ws = AgentWorkflowState()
    ws.save_state("agent-1", "wf-a", {})
    ws.save_state("agent-1", "wf-b", {})
    wfs = ws.list_workflows("agent-1")
    assert "wf-a" in wfs
    assert "wf-b" in wfs
    print("OK: list workflows")


def test_get_state_count():
    ws = AgentWorkflowState()
    ws.save_state("agent-1", "wf-1", {})
    ws.save_state("agent-1", "wf-2", {})
    assert ws.get_state_count("agent-1") == 2
    assert ws.get_state_count() >= 2
    print("OK: get state count")


def test_callbacks():
    ws = AgentWorkflowState()
    fired = []
    ws.on_change("mon", lambda a, d: fired.append(a))
    ws.save_state("agent-1", "wf-1", {})
    assert len(fired) >= 1
    assert ws.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    ws = AgentWorkflowState()
    ws.save_state("agent-1", "wf-1", {})
    stats = ws.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    ws = AgentWorkflowState()
    ws.save_state("agent-1", "wf-1", {})
    ws.reset()
    assert ws.get_state_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Workflow State Tests ===\n")
    test_save_state()
    test_overwrite_state()
    test_get_agent_states()
    test_delete_state()
    test_clear_agent_states()
    test_list_agents()
    test_list_workflows()
    test_get_state_count()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
