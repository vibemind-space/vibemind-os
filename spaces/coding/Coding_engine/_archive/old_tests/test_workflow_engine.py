"""Test workflow engine."""
import sys
sys.path.insert(0, ".")

from src.services.workflow_engine import (
    WorkflowEngine,
    StepStatus,
    WorkflowStatus,
)


def _simple_steps():
    return [
        {"name": "lint", "agent_type": "linter"},
        {"name": "test", "agent_type": "tester", "depends_on": ["lint"]},
        {"name": "build", "agent_type": "builder", "depends_on": ["test"]},
    ]


def _parallel_steps():
    return [
        {"name": "lint", "agent_type": "linter"},
        {"name": "typecheck", "agent_type": "checker"},
        {"name": "test", "agent_type": "tester", "depends_on": ["lint", "typecheck"]},
        {"name": "build", "agent_type": "builder", "depends_on": ["test"]},
    ]


def test_define_workflow():
    """Define a workflow template."""
    engine = WorkflowEngine()
    wf_id = engine.define_workflow("build-pipeline", _simple_steps(), description="CI pipeline")

    assert wf_id.startswith("wf-")

    defn = engine.get_definition("build-pipeline")
    assert defn is not None
    assert defn["name"] == "build-pipeline"
    assert defn["description"] == "CI pipeline"
    assert len(defn["steps"]) == 3
    print("OK: define workflow")


def test_list_definitions():
    """List workflow definitions."""
    engine = WorkflowEngine()
    engine.define_workflow("wf-a", [{"name": "step1"}])
    engine.define_workflow("wf-b", [{"name": "step1"}, {"name": "step2"}])

    defs = engine.list_definitions()
    assert len(defs) == 2
    names = {d["name"] for d in defs}
    assert "wf-a" in names
    assert "wf-b" in names
    print("OK: list definitions")


def test_start_workflow():
    """Start a workflow instance."""
    engine = WorkflowEngine()
    engine.define_workflow("pipeline", _simple_steps())

    inst_id = engine.start_workflow("pipeline", context={"project": "myapp"})
    assert inst_id is not None
    assert inst_id.startswith("wfi-")

    info = engine.get_instance(inst_id)
    assert info["status"] == "running"
    assert info["context"]["project"] == "myapp"
    assert len(info["steps"]) == 3
    print("OK: start workflow")


def test_start_nonexistent():
    """Start a workflow that doesn't exist returns None."""
    engine = WorkflowEngine()
    result = engine.start_workflow("nope")
    assert result is None
    print("OK: start nonexistent")


def test_ready_steps_initial():
    """Steps with no dependencies are immediately ready."""
    engine = WorkflowEngine()
    engine.define_workflow("pipeline", _simple_steps())
    inst_id = engine.start_workflow("pipeline")

    ready = engine.get_ready_steps(inst_id)
    assert len(ready) == 1
    assert ready[0]["name"] == "lint"
    assert ready[0]["status"] == "ready"
    print("OK: ready steps initial")


def test_parallel_ready_steps():
    """Parallel steps with no shared deps are both ready."""
    engine = WorkflowEngine()
    engine.define_workflow("parallel", _parallel_steps())
    inst_id = engine.start_workflow("parallel")

    ready = engine.get_ready_steps(inst_id)
    ready_names = {s["name"] for s in ready}
    assert ready_names == {"lint", "typecheck"}
    print("OK: parallel ready steps")


def test_assign_step():
    """Assign a step to an agent."""
    engine = WorkflowEngine()
    engine.define_workflow("pipeline", _simple_steps())
    inst_id = engine.start_workflow("pipeline")

    assert engine.assign_step(inst_id, "lint", "LintAgent") is True

    step = engine.get_step(inst_id, "lint")
    assert step["status"] == "running"
    assert step["assigned_to"] == "LintAgent"
    print("OK: assign step")


def test_assign_not_ready():
    """Cannot assign a step that isn't ready."""
    engine = WorkflowEngine()
    engine.define_workflow("pipeline", _simple_steps())
    inst_id = engine.start_workflow("pipeline")

    # "test" depends on "lint", so it's pending
    assert engine.assign_step(inst_id, "test", "TestAgent") is False
    print("OK: assign not ready")


def test_complete_step():
    """Complete a step and unlock dependents."""
    engine = WorkflowEngine()
    engine.define_workflow("pipeline", _simple_steps())
    inst_id = engine.start_workflow("pipeline")

    engine.assign_step(inst_id, "lint", "LintAgent")
    assert engine.complete_step(inst_id, "lint", result={"passed": True}) is True

    # "test" should now be ready
    ready = engine.get_ready_steps(inst_id)
    assert len(ready) == 1
    assert ready[0]["name"] == "test"

    # Result stored in context
    info = engine.get_instance(inst_id)
    assert info["context"]["step_result:lint"] == {"passed": True}
    print("OK: complete step")


def test_workflow_completion():
    """Workflow completes when all steps done."""
    engine = WorkflowEngine()
    engine.define_workflow("pipeline", _simple_steps())
    inst_id = engine.start_workflow("pipeline")

    engine.complete_step(inst_id, "lint")
    engine.complete_step(inst_id, "test")
    engine.complete_step(inst_id, "build")

    info = engine.get_instance(inst_id)
    assert info["status"] == "completed"
    assert info["progress"] == 100.0
    print("OK: workflow completion")


def test_workflow_progress():
    """Progress tracks completion percentage."""
    engine = WorkflowEngine()
    engine.define_workflow("pipeline", _simple_steps())
    inst_id = engine.start_workflow("pipeline")

    info = engine.get_instance(inst_id)
    assert info["progress"] == 0.0

    engine.complete_step(inst_id, "lint")
    info = engine.get_instance(inst_id)
    assert abs(info["progress"] - 33.3) < 1.0

    engine.complete_step(inst_id, "test")
    info = engine.get_instance(inst_id)
    assert abs(info["progress"] - 66.7) < 1.0
    print("OK: workflow progress")


def test_fail_step():
    """Failing a step fails the workflow."""
    engine = WorkflowEngine()
    engine.define_workflow("pipeline", _simple_steps())
    inst_id = engine.start_workflow("pipeline")

    engine.assign_step(inst_id, "lint", "LintAgent")
    engine.fail_step(inst_id, "lint", error="syntax error")

    info = engine.get_instance(inst_id)
    assert info["status"] == "failed"
    assert "syntax error" in info["error"]
    print("OK: fail step")


def test_fail_step_retry():
    """Step with retries gets retried before failing."""
    engine = WorkflowEngine()
    engine.define_workflow("pipeline", [
        {"name": "flaky", "agent_type": "tester", "max_retries": 2},
    ])
    inst_id = engine.start_workflow("pipeline")

    engine.assign_step(inst_id, "flaky", "TestAgent")

    # First failure -> retry 1
    engine.fail_step(inst_id, "flaky", error="timeout")
    step = engine.get_step(inst_id, "flaky")
    assert step["status"] == "ready"
    assert step["retries"] == 1

    # Second failure -> retry 2
    engine.assign_step(inst_id, "flaky", "TestAgent")
    engine.fail_step(inst_id, "flaky", error="timeout")
    step = engine.get_step(inst_id, "flaky")
    assert step["status"] == "ready"
    assert step["retries"] == 2

    # Third failure -> actually fails
    engine.assign_step(inst_id, "flaky", "TestAgent")
    engine.fail_step(inst_id, "flaky", error="timeout")
    step = engine.get_step(inst_id, "flaky")
    assert step["status"] == "failed"

    info = engine.get_instance(inst_id)
    assert info["status"] == "failed"
    print("OK: fail step retry")


def test_skip_step():
    """Skip a step and unlock dependents."""
    engine = WorkflowEngine()
    engine.define_workflow("pipeline", _simple_steps())
    inst_id = engine.start_workflow("pipeline")

    engine.skip_step(inst_id, "lint")

    ready = engine.get_ready_steps(inst_id)
    assert len(ready) == 1
    assert ready[0]["name"] == "test"
    print("OK: skip step")


def test_skip_completes_workflow():
    """Skipping all steps completes workflow."""
    engine = WorkflowEngine()
    engine.define_workflow("pipeline", _simple_steps())
    inst_id = engine.start_workflow("pipeline")

    engine.skip_step(inst_id, "lint")
    engine.skip_step(inst_id, "test")
    engine.skip_step(inst_id, "build")

    info = engine.get_instance(inst_id)
    assert info["status"] == "completed"
    assert info["progress"] == 100.0
    print("OK: skip completes workflow")


def test_pause_resume():
    """Pause and resume a workflow."""
    engine = WorkflowEngine()
    engine.define_workflow("pipeline", _simple_steps())
    inst_id = engine.start_workflow("pipeline")

    assert engine.pause_workflow(inst_id) is True
    info = engine.get_instance(inst_id)
    assert info["status"] == "paused"

    # Can't complete steps while paused (ready steps don't update)
    assert engine.resume_workflow(inst_id) is True
    info = engine.get_instance(inst_id)
    assert info["status"] == "running"
    print("OK: pause resume")


def test_pause_not_running():
    """Can't pause a non-running workflow."""
    engine = WorkflowEngine()
    engine.define_workflow("pipeline", _simple_steps())
    inst_id = engine.start_workflow("pipeline")

    engine.pause_workflow(inst_id)
    assert engine.pause_workflow(inst_id) is False  # Already paused
    print("OK: pause not running")


def test_cancel_workflow():
    """Cancel a workflow."""
    engine = WorkflowEngine()
    engine.define_workflow("pipeline", _simple_steps())
    inst_id = engine.start_workflow("pipeline")

    assert engine.cancel_workflow(inst_id) is True
    info = engine.get_instance(inst_id)
    assert info["status"] == "cancelled"

    # Can't cancel again
    assert engine.cancel_workflow(inst_id) is False
    print("OK: cancel workflow")


def test_step_callback():
    """Step completion callbacks fire."""
    engine = WorkflowEngine()
    engine.define_workflow("pipeline", _simple_steps())

    results = []
    engine.on_step_complete("lint", lambda iid, sn, r: results.append((sn, r)))

    inst_id = engine.start_workflow("pipeline")
    engine.complete_step(inst_id, "lint", result={"ok": True})

    assert len(results) == 1
    assert results[0] == ("lint", {"ok": True})
    print("OK: step callback")


def test_workflow_callback():
    """Workflow completion callbacks fire."""
    engine = WorkflowEngine()
    engine.define_workflow("pipeline", [{"name": "only_step"}])

    completions = []
    engine.on_workflow_complete(lambda iid, status: completions.append(status))

    inst_id = engine.start_workflow("pipeline")
    engine.complete_step(inst_id, "only_step")

    assert len(completions) == 1
    assert completions[0] == "completed"
    print("OK: workflow callback")


def test_list_instances():
    """List instances with filters."""
    engine = WorkflowEngine()
    engine.define_workflow("wf-a", [{"name": "s1"}])
    engine.define_workflow("wf-b", [{"name": "s1"}])

    id_a = engine.start_workflow("wf-a")
    id_b = engine.start_workflow("wf-b")
    engine.complete_step(id_a, "s1")

    all_inst = engine.list_instances()
    assert len(all_inst) == 2

    running = engine.list_instances(status="running")
    assert len(running) == 1
    assert running[0]["workflow_name"] == "wf-b"

    completed = engine.list_instances(status="completed")
    assert len(completed) == 1
    assert completed[0]["workflow_name"] == "wf-a"

    by_name = engine.list_instances(workflow_name="wf-b")
    assert len(by_name) == 1
    print("OK: list instances")


def test_get_step():
    """Get specific step details."""
    engine = WorkflowEngine()
    engine.define_workflow("pipeline", _simple_steps())
    inst_id = engine.start_workflow("pipeline")

    step = engine.get_step(inst_id, "lint")
    assert step is not None
    assert step["name"] == "lint"
    assert step["agent_type"] == "linter"

    assert engine.get_step(inst_id, "nonexistent") is None
    assert engine.get_step("bad-id", "lint") is None
    print("OK: get step")


def test_stats():
    """Engine stats are accurate."""
    engine = WorkflowEngine()
    engine.define_workflow("wf", [{"name": "s1"}, {"name": "s2", "depends_on": ["s1"]}])

    id1 = engine.start_workflow("wf")
    engine.complete_step(id1, "s1")
    engine.complete_step(id1, "s2")

    id2 = engine.start_workflow("wf")
    engine.fail_step(id2, "s1", error="boom")

    stats = engine.get_stats()
    assert stats["total_defined"] == 1
    assert stats["total_started"] == 2
    assert stats["total_completed"] == 1
    assert stats["total_failed"] == 1
    assert stats["total_steps_completed"] == 2
    assert stats["definitions"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears all state."""
    engine = WorkflowEngine()
    engine.define_workflow("wf", [{"name": "s1"}])
    engine.start_workflow("wf")

    engine.reset()

    assert engine.get_definition("wf") is None
    assert engine.list_instances() == []
    stats = engine.get_stats()
    assert stats["total_defined"] == 0
    assert stats["total_started"] == 0
    print("OK: reset")


def test_dag_dependency_chain():
    """Full DAG dependency chain works correctly."""
    engine = WorkflowEngine()
    engine.define_workflow("complex", [
        {"name": "fetch", "agent_type": "fetcher"},
        {"name": "parse", "agent_type": "parser", "depends_on": ["fetch"]},
        {"name": "validate", "agent_type": "validator", "depends_on": ["parse"]},
        {"name": "transform", "agent_type": "transformer", "depends_on": ["validate"]},
        {"name": "store", "agent_type": "storer", "depends_on": ["transform"]},
    ])
    inst_id = engine.start_workflow("complex")

    # Only fetch is ready
    ready = engine.get_ready_steps(inst_id)
    assert len(ready) == 1
    assert ready[0]["name"] == "fetch"

    # Complete each step in order
    for step_name in ["fetch", "parse", "validate", "transform", "store"]:
        engine.complete_step(inst_id, step_name, result=f"{step_name}_done")

    info = engine.get_instance(inst_id)
    assert info["status"] == "completed"
    assert info["progress"] == 100.0
    print("OK: dag dependency chain")


def test_diamond_dependency():
    """Diamond dependency pattern: A -> B,C -> D."""
    engine = WorkflowEngine()
    engine.define_workflow("diamond", [
        {"name": "A"},
        {"name": "B", "depends_on": ["A"]},
        {"name": "C", "depends_on": ["A"]},
        {"name": "D", "depends_on": ["B", "C"]},
    ])
    inst_id = engine.start_workflow("diamond")

    # Only A ready
    ready = engine.get_ready_steps(inst_id)
    assert len(ready) == 1
    assert ready[0]["name"] == "A"

    engine.complete_step(inst_id, "A")

    # B and C both ready
    ready = engine.get_ready_steps(inst_id)
    names = {s["name"] for s in ready}
    assert names == {"B", "C"}

    # Complete B only — D not yet ready
    engine.complete_step(inst_id, "B")
    ready = engine.get_ready_steps(inst_id)
    assert len(ready) == 1
    assert ready[0]["name"] == "C"

    # Complete C — D now ready
    engine.complete_step(inst_id, "C")
    ready = engine.get_ready_steps(inst_id)
    assert len(ready) == 1
    assert ready[0]["name"] == "D"

    engine.complete_step(inst_id, "D")
    info = engine.get_instance(inst_id)
    assert info["status"] == "completed"
    print("OK: diamond dependency")


def test_to_dict():
    """Serialization works."""
    engine = WorkflowEngine()
    engine.define_workflow("pipeline", _simple_steps())
    inst_id = engine.start_workflow("pipeline")

    info = engine.get_instance(inst_id)
    assert "instance_id" in info
    assert "workflow_name" in info
    assert "steps" in info
    assert "progress" in info

    step = engine.get_step(inst_id, "lint")
    assert "name" in step
    assert "status" in step
    assert "agent_type" in step
    print("OK: to dict")


def main():
    print("=== Workflow Engine Tests ===\n")
    test_define_workflow()
    test_list_definitions()
    test_start_workflow()
    test_start_nonexistent()
    test_ready_steps_initial()
    test_parallel_ready_steps()
    test_assign_step()
    test_assign_not_ready()
    test_complete_step()
    test_workflow_completion()
    test_workflow_progress()
    test_fail_step()
    test_fail_step_retry()
    test_skip_step()
    test_skip_completes_workflow()
    test_pause_resume()
    test_pause_not_running()
    test_cancel_workflow()
    test_step_callback()
    test_workflow_callback()
    test_list_instances()
    test_get_step()
    test_stats()
    test_reset()
    test_dag_dependency_chain()
    test_diamond_dependency()
    test_to_dict()
    print("\n=== ALL 27 TESTS PASSED ===")


if __name__ == "__main__":
    main()
