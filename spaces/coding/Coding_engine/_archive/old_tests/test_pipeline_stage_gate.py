"""Test pipeline stage gate -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_stage_gate import PipelineStageGate


def test_create_gate():
    sg = PipelineStageGate()
    gid = sg.create_gate("pipeline-1", "deploy", required_approvals=2)
    assert len(gid) > 0
    assert gid.startswith("psg2-")
    print("OK: create gate")


def test_get_gate():
    sg = PipelineStageGate()
    gid = sg.create_gate("pipeline-1", "deploy", required_approvals=2)
    gate = sg.get_gate(gid)
    assert gate is not None
    assert gate["pipeline_id"] == "pipeline-1"
    assert gate["stage_name"] == "deploy"
    assert gate["required_approvals"] == 2
    assert gate["status"] == "pending"
    assert sg.get_gate("nonexistent") is None
    print("OK: get gate")


def test_approve_gate():
    sg = PipelineStageGate()
    gid = sg.create_gate("pipeline-1", "deploy", required_approvals=2)
    assert sg.approve_gate(gid, "reviewer-1") is True
    assert sg.is_approved(gid) is False
    assert sg.approve_gate(gid, "reviewer-2") is True
    assert sg.is_approved(gid) is True
    print("OK: approve gate")


def test_reject_gate():
    sg = PipelineStageGate()
    gid = sg.create_gate("pipeline-1", "deploy", required_approvals=2)
    assert sg.reject_gate(gid, "reviewer-1", reason="not ready") is True
    assert sg.get_gate_status(gid) == "rejected"
    assert sg.approve_gate(gid, "reviewer-2") is False
    print("OK: reject gate")


def test_is_approved():
    sg = PipelineStageGate()
    gid = sg.create_gate("pipeline-1", "deploy", required_approvals=1)
    assert sg.is_approved(gid) is False
    sg.approve_gate(gid, "reviewer-1")
    assert sg.is_approved(gid) is True
    print("OK: is approved")


def test_get_gate_status():
    sg = PipelineStageGate()
    gid = sg.create_gate("pipeline-1", "deploy", required_approvals=1)
    assert sg.get_gate_status(gid) == "pending"
    sg.approve_gate(gid, "reviewer-1")
    assert sg.get_gate_status(gid) == "approved"
    print("OK: get gate status")


def test_get_pipeline_gates():
    sg = PipelineStageGate()
    sg.create_gate("pipeline-1", "build")
    sg.create_gate("pipeline-1", "deploy")
    sg.create_gate("pipeline-2", "test")
    gates = sg.get_pipeline_gates("pipeline-1")
    assert len(gates) == 2
    print("OK: get pipeline gates")


def test_reset_gate():
    sg = PipelineStageGate()
    gid = sg.create_gate("pipeline-1", "deploy", required_approvals=1)
    sg.approve_gate(gid, "reviewer-1")
    assert sg.get_gate_status(gid) == "approved"
    assert sg.reset_gate(gid) is True
    assert sg.get_gate_status(gid) == "pending"
    assert sg.reset_gate("nonexistent") is False
    print("OK: reset gate")


def test_remove_gate():
    sg = PipelineStageGate()
    gid = sg.create_gate("pipeline-1", "deploy")
    assert sg.remove_gate(gid) is True
    assert sg.remove_gate(gid) is False
    print("OK: remove gate")


def test_list_pipelines():
    sg = PipelineStageGate()
    sg.create_gate("pipeline-1", "deploy")
    sg.create_gate("pipeline-2", "test")
    pipelines = sg.list_pipelines()
    assert "pipeline-1" in pipelines
    assert "pipeline-2" in pipelines
    print("OK: list pipelines")


def test_callbacks():
    sg = PipelineStageGate()
    fired = []
    sg.on_change("mon", lambda a, d: fired.append(a))
    sg.create_gate("pipeline-1", "deploy")
    assert len(fired) >= 1
    assert sg.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    sg = PipelineStageGate()
    sg.create_gate("pipeline-1", "deploy")
    stats = sg.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    sg = PipelineStageGate()
    sg.create_gate("pipeline-1", "deploy")
    sg.reset()
    assert sg.get_gate_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Stage Gate Tests ===\n")
    test_create_gate()
    test_get_gate()
    test_approve_gate()
    test_reject_gate()
    test_is_approved()
    test_get_gate_status()
    test_get_pipeline_gates()
    test_reset_gate()
    test_remove_gate()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 13 TESTS PASSED ===")


if __name__ == "__main__":
    main()
