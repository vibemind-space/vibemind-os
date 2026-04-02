"""Test agent workflow tracker -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_workflow_tracker import AgentWorkflowTracker


def test_create_workflow():
    wt = AgentWorkflowTracker()
    wid = wt.create_workflow("agent-1", "build-deploy", stages=["build", "test", "deploy"])
    assert len(wid) > 0
    assert wid.startswith("awt-")
    print("OK: create workflow")


def test_get_workflow():
    wt = AgentWorkflowTracker()
    wid = wt.create_workflow("agent-1", "build-deploy", stages=["build", "test", "deploy"])
    wf = wt.get_workflow(wid)
    assert wf is not None
    assert wf["agent_id"] == "agent-1"
    assert wf["workflow_name"] == "build-deploy"
    assert wf["status"] == "active"
    assert wf["current_stage"] == "build"
    assert wt.get_workflow("nonexistent") is None
    print("OK: get workflow")


def test_advance_stage():
    wt = AgentWorkflowTracker()
    wid = wt.create_workflow("agent-1", "wf", stages=["a", "b", "c"])
    assert wt.get_current_stage(wid) == "a"
    assert wt.advance_stage(wid) is True
    assert wt.get_current_stage(wid) == "b"
    assert wt.advance_stage(wid) is True
    assert wt.get_current_stage(wid) == "c"
    assert wt.advance_stage(wid) is False  # At end
    print("OK: advance stage")


def test_complete_workflow():
    wt = AgentWorkflowTracker()
    wid = wt.create_workflow("agent-1", "wf")
    assert wt.complete_workflow(wid) is True
    wf = wt.get_workflow(wid)
    assert wf["status"] == "completed"
    assert wt.complete_workflow(wid) is False  # Already completed
    print("OK: complete workflow")


def test_fail_workflow():
    wt = AgentWorkflowTracker()
    wid = wt.create_workflow("agent-1", "wf")
    assert wt.fail_workflow(wid, reason="timeout") is True
    wf = wt.get_workflow(wid)
    assert wf["status"] == "failed"
    assert wt.fail_workflow("nonexistent") is False
    print("OK: fail workflow")


def test_get_agent_workflows():
    wt = AgentWorkflowTracker()
    wt.create_workflow("agent-1", "wf1")
    wt.create_workflow("agent-1", "wf2")
    wt.create_workflow("agent-2", "wf3")
    wfs = wt.get_agent_workflows("agent-1")
    assert len(wfs) == 2
    print("OK: get agent workflows")


def test_get_active_workflows():
    wt = AgentWorkflowTracker()
    wid1 = wt.create_workflow("agent-1", "wf1")
    wt.create_workflow("agent-1", "wf2")
    wt.complete_workflow(wid1)
    active = wt.get_active_workflows()
    assert len(active) == 1
    print("OK: get active workflows")


def test_get_workflow_count():
    wt = AgentWorkflowTracker()
    wt.create_workflow("agent-1", "wf1")
    wt.create_workflow("agent-1", "wf2")
    wt.create_workflow("agent-2", "wf3")
    assert wt.get_workflow_count("agent-1") == 2
    assert wt.get_workflow_count() == 3
    print("OK: get workflow count")


def test_list_agents():
    wt = AgentWorkflowTracker()
    wt.create_workflow("agent-1", "wf1")
    wt.create_workflow("agent-2", "wf2")
    agents = wt.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    wt = AgentWorkflowTracker()
    fired = []
    wt.on_change("mon", lambda a, d: fired.append(a))
    wt.create_workflow("agent-1", "wf1")
    assert len(fired) >= 1
    assert wt.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    wt = AgentWorkflowTracker()
    wt.create_workflow("agent-1", "wf1")
    stats = wt.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    wt = AgentWorkflowTracker()
    wt.create_workflow("agent-1", "wf1")
    wt.reset()
    assert wt.get_workflow_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Workflow Tracker Tests ===\n")
    test_create_workflow()
    test_get_workflow()
    test_advance_stage()
    test_complete_workflow()
    test_fail_workflow()
    test_get_agent_workflows()
    test_get_active_workflows()
    test_get_workflow_count()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 12 TESTS PASSED ===")


if __name__ == "__main__":
    main()
