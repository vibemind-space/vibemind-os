"""Test pipeline workflow engine."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_workflow_engine import PipelineWorkflowEngine


def test_create_workflow():
    """Create and remove workflow."""
    we = PipelineWorkflowEngine()
    wid = we.create_workflow("build_deploy", tags=["ci"])
    assert wid.startswith("wf-")

    w = we.get_workflow(wid)
    assert w is not None
    assert w["name"] == "build_deploy"
    assert w["status"] == "draft"
    assert "ci" in w["tags"]

    assert we.remove_workflow(wid) is True
    assert we.remove_workflow(wid) is False
    print("OK: create workflow")


def test_invalid_workflow():
    """Invalid workflow rejected."""
    we = PipelineWorkflowEngine()
    assert we.create_workflow("") == ""
    print("OK: invalid workflow")


def test_max_workflows():
    """Max workflows enforced."""
    we = PipelineWorkflowEngine(max_workflows=2)
    we.create_workflow("a")
    we.create_workflow("b")
    assert we.create_workflow("c") == ""
    print("OK: max workflows")


def test_add_step():
    """Add steps to workflow."""
    we = PipelineWorkflowEngine()
    wid = we.create_workflow("test")

    s1 = we.add_step(wid, "build", step_type="task")
    assert s1.startswith("step-")

    s2 = we.add_step(wid, "test", step_type="task", dependencies=[s1])
    assert s2 != ""

    steps = we.get_steps(wid)
    assert len(steps) == 2
    assert steps[0]["name"] == "build"
    print("OK: add step")


def test_invalid_step():
    """Invalid step rejected."""
    we = PipelineWorkflowEngine()
    wid = we.create_workflow("test")

    assert we.add_step(wid, "") == ""
    assert we.add_step(wid, "x", step_type="invalid") == ""
    assert we.add_step(wid, "x", dependencies=["nonexistent"]) == ""
    assert we.add_step("nonexistent", "x") == ""
    print("OK: invalid step")


def test_max_steps():
    """Max steps per workflow enforced."""
    we = PipelineWorkflowEngine(max_steps_per_workflow=2)
    wid = we.create_workflow("test")
    we.add_step(wid, "a")
    we.add_step(wid, "b")
    assert we.add_step(wid, "c") == ""
    print("OK: max steps")


def test_remove_step():
    """Remove a step."""
    we = PipelineWorkflowEngine()
    wid = we.create_workflow("test")
    s1 = we.add_step(wid, "build")

    assert we.remove_step(wid, s1) is True
    assert we.remove_step(wid, s1) is False
    print("OK: remove step")


def test_remove_step_with_dependents():
    """Cannot remove step that others depend on."""
    we = PipelineWorkflowEngine()
    wid = we.create_workflow("test")
    s1 = we.add_step(wid, "build")
    s2 = we.add_step(wid, "test", dependencies=[s1])

    assert we.remove_step(wid, s1) is False  # s2 depends on s1
    print("OK: remove step with dependents")


def test_start_workflow():
    """Start a workflow."""
    we = PipelineWorkflowEngine()
    wid = we.create_workflow("test")
    we.add_step(wid, "build")

    assert we.start_workflow(wid) is True
    w = we.get_workflow(wid)
    assert w["status"] == "running"
    print("OK: start workflow")


def test_start_empty_workflow():
    """Cannot start empty workflow."""
    we = PipelineWorkflowEngine()
    wid = we.create_workflow("test")
    assert we.start_workflow(wid) is False
    print("OK: start empty workflow")


def test_cannot_add_step_after_start():
    """Cannot add steps to running workflow."""
    we = PipelineWorkflowEngine()
    wid = we.create_workflow("test")
    we.add_step(wid, "build")
    we.start_workflow(wid)

    assert we.add_step(wid, "extra") == ""
    print("OK: cannot add step after start")


def test_complete_step():
    """Complete a step."""
    we = PipelineWorkflowEngine()
    wid = we.create_workflow("test")
    s1 = we.add_step(wid, "build")
    we.start_workflow(wid)

    assert we.complete_step(wid, s1, result="ok") is True
    step = we.get_step(wid, s1)
    assert step["status"] == "completed"
    assert step["result"] == "ok"
    print("OK: complete step")


def test_workflow_completes_when_all_done():
    """Workflow completes when all steps done."""
    we = PipelineWorkflowEngine()
    wid = we.create_workflow("test")
    s1 = we.add_step(wid, "build")
    s2 = we.add_step(wid, "test")
    we.start_workflow(wid)

    we.complete_step(wid, s1)
    assert we.get_workflow(wid)["status"] == "running"

    we.complete_step(wid, s2)
    assert we.get_workflow(wid)["status"] == "completed"
    print("OK: workflow completes when all done")


def test_dependency_unblocking():
    """Blocked steps unblock when dependencies complete."""
    we = PipelineWorkflowEngine()
    wid = we.create_workflow("test")
    s1 = we.add_step(wid, "build")
    s2 = we.add_step(wid, "test", dependencies=[s1])
    we.start_workflow(wid)

    step2 = we.get_step(wid, s2)
    assert step2["status"] == "blocked"

    we.complete_step(wid, s1)
    step2 = we.get_step(wid, s2)
    assert step2["status"] == "pending"
    print("OK: dependency unblocking")


def test_fail_step():
    """Fail a step fails the workflow."""
    we = PipelineWorkflowEngine()
    wid = we.create_workflow("test")
    s1 = we.add_step(wid, "build")
    we.start_workflow(wid)

    assert we.fail_step(wid, s1, reason="compile error") is True
    assert we.get_workflow(wid)["status"] == "failed"
    print("OK: fail step")


def test_skip_step():
    """Skip a pending step."""
    we = PipelineWorkflowEngine()
    wid = we.create_workflow("test")
    s1 = we.add_step(wid, "optional")
    s2 = we.add_step(wid, "required")
    we.start_workflow(wid)

    assert we.skip_step(wid, s1) is True
    step = we.get_step(wid, s1)
    assert step["status"] == "skipped"

    we.complete_step(wid, s2)
    assert we.get_workflow(wid)["status"] == "completed"
    print("OK: skip step")


def test_start_step():
    """Mark step as running."""
    we = PipelineWorkflowEngine()
    wid = we.create_workflow("test")
    s1 = we.add_step(wid, "build")
    we.start_workflow(wid)

    assert we.start_step(wid, s1) is True
    step = we.get_step(wid, s1)
    assert step["status"] == "running"
    print("OK: start step")


def test_get_next_steps():
    """Get ready-to-execute steps."""
    we = PipelineWorkflowEngine()
    wid = we.create_workflow("test")
    s1 = we.add_step(wid, "build")
    s2 = we.add_step(wid, "test", dependencies=[s1])
    s3 = we.add_step(wid, "lint")
    we.start_workflow(wid)

    nexts = we.get_next_steps(wid)
    names = {n["name"] for n in nexts}
    assert "build" in names
    assert "lint" in names
    assert "test" not in names  # Blocked
    print("OK: get next steps")


def test_cancel_workflow():
    """Cancel a workflow."""
    we = PipelineWorkflowEngine()
    wid = we.create_workflow("test")
    we.add_step(wid, "build")
    we.start_workflow(wid)

    assert we.cancel_workflow(wid) is True
    assert we.get_workflow(wid)["status"] == "cancelled"
    assert we.cancel_workflow(wid) is False
    print("OK: cancel workflow")


def test_list_workflows():
    """List workflows with filters."""
    we = PipelineWorkflowEngine()
    w1 = we.create_workflow("a", tags=["ci"])
    w2 = we.create_workflow("b")
    we.add_step(w2, "x")
    we.start_workflow(w2)

    all_w = we.list_workflows()
    assert len(all_w) == 2

    by_status = we.list_workflows(status="running")
    assert len(by_status) == 1

    by_tag = we.list_workflows(tag="ci")
    assert len(by_tag) == 1
    print("OK: list workflows")


def test_workflow_progress():
    """Get workflow progress."""
    we = PipelineWorkflowEngine()
    wid = we.create_workflow("test")
    s1 = we.add_step(wid, "a")
    s2 = we.add_step(wid, "b")
    s3 = we.add_step(wid, "c")
    s4 = we.add_step(wid, "d")
    we.start_workflow(wid)

    we.complete_step(wid, s1)
    we.complete_step(wid, s2)

    prog = we.get_workflow_progress(wid)
    assert prog["total_steps"] == 4
    assert prog["completed_steps"] == 2
    assert prog["progress"] == 0.5
    print("OK: workflow progress")


def test_workflow_started_callback():
    """Callback fires on workflow start."""
    we = PipelineWorkflowEngine()
    fired = []
    we.on_change("mon", lambda a, d: fired.append(a))

    wid = we.create_workflow("test")
    we.add_step(wid, "build")
    we.start_workflow(wid)
    assert "workflow_started" in fired
    print("OK: workflow started callback")


def test_workflow_completed_callback():
    """Callback fires on workflow completion."""
    we = PipelineWorkflowEngine()
    fired = []
    we.on_change("mon", lambda a, d: fired.append(a))

    wid = we.create_workflow("test")
    s1 = we.add_step(wid, "build")
    we.start_workflow(wid)
    we.complete_step(wid, s1)
    assert "workflow_completed" in fired
    print("OK: workflow completed callback")


def test_callbacks():
    """Callback registration."""
    we = PipelineWorkflowEngine()
    assert we.on_change("mon", lambda a, d: None) is True
    assert we.on_change("mon", lambda a, d: None) is False
    assert we.remove_callback("mon") is True
    assert we.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    we = PipelineWorkflowEngine()
    w1 = we.create_workflow("a")
    s1 = we.add_step(w1, "build")
    s2 = we.add_step(w1, "test")
    we.start_workflow(w1)
    we.complete_step(w1, s1)
    we.complete_step(w1, s2)

    w2 = we.create_workflow("b")
    s3 = we.add_step(w2, "build")
    we.start_workflow(w2)
    we.fail_step(w2, s3)

    stats = we.get_stats()
    assert stats["total_workflows"] == 2
    assert stats["total_completed"] == 1
    assert stats["total_failed"] == 1
    assert stats["total_steps_executed"] == 2
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    we = PipelineWorkflowEngine()
    we.create_workflow("test")

    we.reset()
    assert we.list_workflows() == []
    stats = we.get_stats()
    assert stats["current_workflows"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Workflow Engine Tests ===\n")
    test_create_workflow()
    test_invalid_workflow()
    test_max_workflows()
    test_add_step()
    test_invalid_step()
    test_max_steps()
    test_remove_step()
    test_remove_step_with_dependents()
    test_start_workflow()
    test_start_empty_workflow()
    test_cannot_add_step_after_start()
    test_complete_step()
    test_workflow_completes_when_all_done()
    test_dependency_unblocking()
    test_fail_step()
    test_skip_step()
    test_start_step()
    test_get_next_steps()
    test_cancel_workflow()
    test_list_workflows()
    test_workflow_progress()
    test_workflow_started_callback()
    test_workflow_completed_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 26 TESTS PASSED ===")


if __name__ == "__main__":
    main()
