"""Test pipeline step gate -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_step_gate import PipelineStepGate


def test_create_gate():
    sg = PipelineStepGate()
    gid = sg.create_gate("pipeline-1", "deploy", "approved", required_value=True)
    assert len(gid) > 0
    assert gid.startswith("psg-")
    print("OK: create gate")


def test_check_gate_pass():
    sg = PipelineStepGate()
    sg.create_gate("pipeline-1", "deploy", "approved", required_value=True)
    assert sg.check_gate("pipeline-1", "deploy", {"approved": True}) is True
    print("OK: check gate pass")


def test_check_gate_fail():
    sg = PipelineStepGate()
    sg.create_gate("pipeline-1", "deploy", "approved", required_value=True)
    assert sg.check_gate("pipeline-1", "deploy", {"approved": False}) is False
    print("OK: check gate fail")


def test_check_gate_missing_key():
    sg = PipelineStepGate()
    sg.create_gate("pipeline-1", "deploy", "approved", required_value=True)
    assert sg.check_gate("pipeline-1", "deploy", {}) is False
    print("OK: check gate missing key")


def test_open_gate():
    sg = PipelineStepGate()
    sg.create_gate("pipeline-1", "deploy", "approved", required_value=True)
    assert sg.open_gate("pipeline-1", "deploy") is True
    assert sg.check_gate("pipeline-1", "deploy", {"approved": False}) is True  # forced open
    print("OK: open gate")


def test_close_gate():
    sg = PipelineStepGate()
    sg.create_gate("pipeline-1", "deploy", "approved", required_value=True)
    assert sg.close_gate("pipeline-1", "deploy") is True
    assert sg.check_gate("pipeline-1", "deploy", {"approved": True}) is False  # forced closed
    print("OK: close gate")


def test_get_gate():
    sg = PipelineStepGate()
    sg.create_gate("pipeline-1", "deploy", "approved")
    gate = sg.get_gate("pipeline-1", "deploy")
    assert gate is not None
    assert gate["condition_key"] == "approved"
    assert sg.get_gate("pipeline-1", "nonexistent") is None
    print("OK: get gate")


def test_get_gate_count():
    sg = PipelineStepGate()
    sg.create_gate("pipeline-1", "deploy", "approved")
    sg.create_gate("pipeline-2", "test", "passed")
    assert sg.get_gate_count() == 2
    assert sg.get_gate_count("pipeline-1") == 1
    print("OK: get gate count")


def test_list_pipelines():
    sg = PipelineStepGate()
    sg.create_gate("pipeline-1", "deploy", "approved")
    sg.create_gate("pipeline-2", "test", "passed")
    pipelines = sg.list_pipelines()
    assert "pipeline-1" in pipelines
    assert "pipeline-2" in pipelines
    print("OK: list pipelines")


def test_callbacks():
    sg = PipelineStepGate()
    fired = []
    sg.on_change("mon", lambda a, d: fired.append(a))
    sg.create_gate("pipeline-1", "deploy", "approved")
    assert len(fired) >= 1
    assert sg.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    sg = PipelineStepGate()
    sg.create_gate("pipeline-1", "deploy", "approved")
    stats = sg.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    sg = PipelineStepGate()
    sg.create_gate("pipeline-1", "deploy", "approved")
    sg.reset()
    assert sg.get_gate_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Step Gate Tests ===\n")
    test_create_gate()
    test_check_gate_pass()
    test_check_gate_fail()
    test_check_gate_missing_key()
    test_open_gate()
    test_close_gate()
    test_get_gate()
    test_get_gate_count()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 12 TESTS PASSED ===")


if __name__ == "__main__":
    main()
