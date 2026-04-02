"""Test agent workflow engine -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_workflow_engine import AgentWorkflowEngine


def test_create_workflow():
    we = AgentWorkflowEngine()
    wid = we.create_workflow("build_pipeline", description="CI/CD workflow", tags=["ci"])
    assert len(wid) > 0
    w = we.get_workflow(wid)
    assert w is not None
    assert w["name"] == "build_pipeline"
    assert we.create_workflow("build_pipeline") == ""  # dup
    print("OK: create workflow")


def test_add_step():
    we = AgentWorkflowEngine()
    wid = we.create_workflow("deploy")
    sid = we.add_step(wid, "build", lambda ctx: ctx)
    assert len(sid) > 0
    sid2 = we.add_step(wid, "test", lambda ctx: ctx)
    assert len(sid2) > 0
    print("OK: add step")


def test_execute_workflow():
    we = AgentWorkflowEngine()
    wid = we.create_workflow("simple")
    we.add_step(wid, "step1", lambda ctx: {**ctx, "step1": True})
    we.add_step(wid, "step2", lambda ctx: {**ctx, "step2": True})
    result = we.execute_workflow(wid, {"initial": True})
    assert result["success"] is True
    assert result["steps_completed"] == 2
    assert result["context"]["step1"] is True
    assert result["context"]["step2"] is True
    assert result["context"]["initial"] is True
    print("OK: execute workflow")


def test_execute_failure():
    we = AgentWorkflowEngine()
    wid = we.create_workflow("failing")
    we.add_step(wid, "good", lambda ctx: {**ctx, "good": True})
    def bad_step(ctx):
        raise RuntimeError("boom")
    we.add_step(wid, "bad", bad_step)
    we.add_step(wid, "never", lambda ctx: {**ctx, "never": True})
    result = we.execute_workflow(wid, {})
    assert result["success"] is False
    assert result["steps_completed"] < 3
    print("OK: execute failure")


def test_workflow_history():
    we = AgentWorkflowEngine()
    wid = we.create_workflow("tracked")
    we.add_step(wid, "s1", lambda ctx: {**ctx, "done": True})
    we.execute_workflow(wid, {})
    we.execute_workflow(wid, {"run": 2})
    history = we.get_workflow_history(wid)
    assert len(history) >= 2
    print("OK: workflow history")


def test_list_workflows():
    we = AgentWorkflowEngine()
    we.create_workflow("w1", tags=["ci"])
    we.create_workflow("w2", tags=["deploy"])
    assert len(we.list_workflows()) == 2
    assert len(we.list_workflows(tag="ci")) == 1
    print("OK: list workflows")


def test_remove_workflow():
    we = AgentWorkflowEngine()
    wid = we.create_workflow("temp")
    assert we.remove_workflow(wid) is True
    assert we.remove_workflow(wid) is False
    print("OK: remove workflow")


def test_callbacks():
    we = AgentWorkflowEngine()
    fired = []
    we.on_change("mon", lambda a, d: fired.append(a))
    we.create_workflow("w1")
    assert len(fired) >= 1
    assert we.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    we = AgentWorkflowEngine()
    we.create_workflow("w1")
    stats = we.get_stats()
    assert stats["total_workflows_created"] >= 1
    print("OK: stats")


def test_reset():
    we = AgentWorkflowEngine()
    we.create_workflow("w1")
    we.reset()
    assert we.list_workflows() == []
    print("OK: reset")


def main():
    print("=== Agent Workflow Engine Tests ===\n")
    test_create_workflow()
    test_add_step()
    test_execute_workflow()
    test_execute_failure()
    test_workflow_history()
    test_list_workflows()
    test_remove_workflow()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")


if __name__ == "__main__":
    main()
