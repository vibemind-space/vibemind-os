"""Test pipeline workflow orchestrator -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_workflow_orchestrator import PipelineWorkflowOrchestrator


def test_create_workflow():
    wo = PipelineWorkflowOrchestrator()
    wid = wo.create_workflow("pipeline-1", name="etl-flow")
    assert len(wid) > 0
    assert wid.startswith("pwo-")
    print("OK: create workflow")


def test_add_step():
    wo = PipelineWorkflowOrchestrator()
    wid = wo.create_workflow("pipeline-1")
    assert wo.add_step(wid, "extract", step_order=1) is True
    assert wo.add_step(wid, "transform", step_order=2) is True
    assert wo.add_step(wid, "load", step_order=3) is True
    print("OK: add step")


def test_start_workflow():
    wo = PipelineWorkflowOrchestrator()
    wid = wo.create_workflow("pipeline-1")
    wo.add_step(wid, "step-1", step_order=1)
    assert wo.start_workflow(wid) is True
    print("OK: start workflow")


def test_complete_step():
    wo = PipelineWorkflowOrchestrator()
    wid = wo.create_workflow("pipeline-1")
    wo.add_step(wid, "step-1", step_order=1)
    wo.start_workflow(wid)
    assert wo.complete_step(wid, "step-1") is True
    print("OK: complete step")


def test_get_current_step():
    wo = PipelineWorkflowOrchestrator()
    wid = wo.create_workflow("pipeline-1")
    wo.add_step(wid, "extract", step_order=1)
    wo.add_step(wid, "transform", step_order=2)
    wo.start_workflow(wid)
    current = wo.get_current_step(wid)
    assert current == "extract"
    wo.complete_step(wid, "extract")
    current2 = wo.get_current_step(wid)
    assert current2 == "transform"
    print("OK: get current step")


def test_is_workflow_complete():
    wo = PipelineWorkflowOrchestrator()
    wid = wo.create_workflow("pipeline-1")
    wo.add_step(wid, "step-1", step_order=1)
    wo.start_workflow(wid)
    assert wo.is_workflow_complete(wid) is False
    wo.complete_step(wid, "step-1")
    assert wo.is_workflow_complete(wid) is True
    print("OK: is workflow complete")


def test_get_workflow():
    wo = PipelineWorkflowOrchestrator()
    wid = wo.create_workflow("pipeline-1", name="test-flow")
    wf = wo.get_workflow(wid)
    assert wf is not None
    assert wf["pipeline_id"] == "pipeline-1"
    assert wo.get_workflow("nonexistent") is None
    print("OK: get workflow")


def test_list_pipelines():
    wo = PipelineWorkflowOrchestrator()
    wo.create_workflow("pipeline-1")
    wo.create_workflow("pipeline-2")
    pipelines = wo.list_pipelines()
    assert "pipeline-1" in pipelines
    assert "pipeline-2" in pipelines
    print("OK: list pipelines")


def test_callbacks():
    wo = PipelineWorkflowOrchestrator()
    fired = []
    wo.on_change("mon", lambda a, d: fired.append(a))
    wo.create_workflow("pipeline-1")
    assert len(fired) >= 1
    assert wo.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    wo = PipelineWorkflowOrchestrator()
    wo.create_workflow("pipeline-1")
    stats = wo.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    wo = PipelineWorkflowOrchestrator()
    wo.create_workflow("pipeline-1")
    wo.reset()
    assert wo.get_workflow_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Workflow Orchestrator Tests ===\n")
    test_create_workflow()
    test_add_step()
    test_start_workflow()
    test_complete_step()
    test_get_current_step()
    test_is_workflow_complete()
    test_get_workflow()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
