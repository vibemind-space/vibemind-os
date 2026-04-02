"""Test pipeline flow controller -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_flow_controller import PipelineFlowController


def test_register_pipeline():
    fc = PipelineFlowController()
    eid = fc.register_pipeline("pipeline-1", max_throughput=100.0)
    assert len(eid) > 0
    assert eid.startswith("pfc-")
    print("OK: register pipeline")


def test_get_pipeline():
    fc = PipelineFlowController()
    eid = fc.register_pipeline("pipeline-1")
    pipe = fc.get_pipeline(eid)
    assert pipe is not None
    assert fc.get_pipeline("nonexistent") is None
    print("OK: get pipeline")


def test_initial_status():
    fc = PipelineFlowController()
    fc.register_pipeline("pipeline-1")
    assert fc.get_status("pipeline-1") == "running"
    assert fc.is_running("pipeline-1") is True
    print("OK: initial status")


def test_pause_pipeline():
    fc = PipelineFlowController()
    fc.register_pipeline("pipeline-1")
    assert fc.pause_pipeline("pipeline-1") is True
    assert fc.get_status("pipeline-1") == "paused"
    assert fc.is_running("pipeline-1") is False
    print("OK: pause pipeline")


def test_resume_pipeline():
    fc = PipelineFlowController()
    fc.register_pipeline("pipeline-1")
    fc.pause_pipeline("pipeline-1")
    assert fc.resume_pipeline("pipeline-1") is True
    assert fc.get_status("pipeline-1") == "running"
    assert fc.is_running("pipeline-1") is True
    print("OK: resume pipeline")


def test_stop_pipeline():
    fc = PipelineFlowController()
    fc.register_pipeline("pipeline-1")
    assert fc.stop_pipeline("pipeline-1") is True
    assert fc.get_status("pipeline-1") == "stopped"
    assert fc.is_running("pipeline-1") is False
    print("OK: stop pipeline")


def test_unknown_status():
    fc = PipelineFlowController()
    assert fc.get_status("nonexistent") == "unknown"
    assert fc.is_running("nonexistent") is False
    print("OK: unknown status")


def test_list_pipelines():
    fc = PipelineFlowController()
    fc.register_pipeline("pipeline-1")
    fc.register_pipeline("pipeline-2")
    pipelines = fc.list_pipelines()
    assert "pipeline-1" in pipelines
    assert "pipeline-2" in pipelines
    print("OK: list pipelines")


def test_callbacks():
    fc = PipelineFlowController()
    fired = []
    fc.on_change("mon", lambda a, d: fired.append(a))
    fc.register_pipeline("pipeline-1")
    assert len(fired) >= 1
    assert fc.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    fc = PipelineFlowController()
    fc.register_pipeline("pipeline-1")
    stats = fc.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    fc = PipelineFlowController()
    fc.register_pipeline("pipeline-1")
    fc.reset()
    assert fc.get_pipeline_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Flow Controller Tests ===\n")
    test_register_pipeline()
    test_get_pipeline()
    test_initial_status()
    test_pause_pipeline()
    test_resume_pipeline()
    test_stop_pipeline()
    test_unknown_status()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
