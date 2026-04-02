"""Test pipeline circuit manager -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_circuit_manager import PipelineCircuitManager


def test_create_circuit():
    cm = PipelineCircuitManager()
    cid = cm.create_circuit("pipeline-1", failure_threshold=5, recovery_timeout=30.0)
    assert len(cid) > 0
    assert cid.startswith("pcm-")
    print("OK: create circuit")


def test_get_circuit():
    cm = PipelineCircuitManager()
    cid = cm.create_circuit("pipeline-1", failure_threshold=3)
    circuit = cm.get_circuit(cid)
    assert circuit is not None
    assert circuit["pipeline_id"] == "pipeline-1"
    assert circuit["failure_threshold"] == 3
    assert cm.get_circuit("nonexistent") is None
    print("OK: get circuit")


def test_get_circuit_for_pipeline():
    cm = PipelineCircuitManager()
    cm.create_circuit("pipeline-1")
    circuit = cm.get_circuit_for_pipeline("pipeline-1")
    assert circuit is not None
    assert circuit["pipeline_id"] == "pipeline-1"
    assert cm.get_circuit_for_pipeline("nonexistent") is None
    print("OK: get circuit for pipeline")


def test_initial_state():
    cm = PipelineCircuitManager()
    cm.create_circuit("pipeline-1")
    assert cm.get_state("pipeline-1") == "closed"
    assert cm.is_allowed("pipeline-1") is True
    print("OK: initial state")


def test_record_success():
    cm = PipelineCircuitManager()
    cm.create_circuit("pipeline-1", failure_threshold=3)
    assert cm.record_success("pipeline-1") is True
    assert cm.get_state("pipeline-1") == "closed"
    print("OK: record success")


def test_record_failure_opens_circuit():
    cm = PipelineCircuitManager()
    cm.create_circuit("pipeline-1", failure_threshold=3)
    cm.record_failure("pipeline-1")
    cm.record_failure("pipeline-1")
    assert cm.get_state("pipeline-1") == "closed"
    cm.record_failure("pipeline-1")
    assert cm.get_state("pipeline-1") == "open"
    assert cm.is_allowed("pipeline-1") is False
    print("OK: record failure opens circuit")


def test_reset_circuit():
    cm = PipelineCircuitManager()
    cm.create_circuit("pipeline-1", failure_threshold=2)
    cm.record_failure("pipeline-1")
    cm.record_failure("pipeline-1")
    assert cm.get_state("pipeline-1") == "open"
    assert cm.reset_circuit("pipeline-1") is True
    assert cm.get_state("pipeline-1") == "closed"
    assert cm.is_allowed("pipeline-1") is True
    print("OK: reset circuit")


def test_list_pipelines():
    cm = PipelineCircuitManager()
    cm.create_circuit("pipeline-1")
    cm.create_circuit("pipeline-2")
    pipelines = cm.list_pipelines()
    assert "pipeline-1" in pipelines
    assert "pipeline-2" in pipelines
    print("OK: list pipelines")


def test_callbacks():
    cm = PipelineCircuitManager()
    fired = []
    cm.on_change("mon", lambda a, d: fired.append(a))
    cm.create_circuit("pipeline-1")
    assert len(fired) >= 1
    assert cm.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    cm = PipelineCircuitManager()
    cm.create_circuit("pipeline-1")
    stats = cm.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    cm = PipelineCircuitManager()
    cm.create_circuit("pipeline-1")
    cm.reset()
    assert cm.get_circuit_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Circuit Manager Tests ===\n")
    test_create_circuit()
    test_get_circuit()
    test_get_circuit_for_pipeline()
    test_initial_state()
    test_record_success()
    test_record_failure_opens_circuit()
    test_reset_circuit()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
