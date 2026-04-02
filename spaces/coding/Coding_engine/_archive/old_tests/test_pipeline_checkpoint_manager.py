"""Test pipeline checkpoint manager -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_checkpoint_manager import PipelineCheckpointManager


def test_create_checkpoint():
    cm = PipelineCheckpointManager()
    cid = cm.create_checkpoint("pipeline-1", "step-3", {"progress": 0.5}, label="mid-run")
    assert len(cid) > 0
    assert cid.startswith("pcpm-")
    print("OK: create checkpoint")


def test_get_checkpoint():
    cm = PipelineCheckpointManager()
    cid = cm.create_checkpoint("pipeline-1", "step-1", {"data": "test"})
    cp = cm.get_checkpoint(cid)
    assert cp is not None
    assert cp["pipeline_id"] == "pipeline-1"
    assert cp["step_name"] == "step-1"
    assert cm.get_checkpoint("nonexistent") is None
    print("OK: get checkpoint")


def test_get_latest_checkpoint():
    cm = PipelineCheckpointManager()
    cm.create_checkpoint("pipeline-1", "step-1", {"v": 1})
    cm.create_checkpoint("pipeline-1", "step-2", {"v": 2})
    latest = cm.get_latest_checkpoint("pipeline-1")
    assert latest is not None
    assert latest["step_name"] == "step-2"
    print("OK: get latest checkpoint")


def test_get_checkpoints():
    cm = PipelineCheckpointManager()
    cm.create_checkpoint("pipeline-1", "step-1", {})
    cm.create_checkpoint("pipeline-1", "step-2", {})
    cm.create_checkpoint("pipeline-1", "step-3", {})
    cps = cm.get_checkpoints("pipeline-1")
    assert len(cps) == 3
    print("OK: get checkpoints")


def test_delete_checkpoint():
    cm = PipelineCheckpointManager()
    cid = cm.create_checkpoint("pipeline-1", "step-1", {})
    assert cm.delete_checkpoint(cid) is True
    assert cm.get_checkpoint(cid) is None
    assert cm.delete_checkpoint("nonexistent") is False
    print("OK: delete checkpoint")


def test_list_pipelines():
    cm = PipelineCheckpointManager()
    cm.create_checkpoint("pipeline-1", "step-1", {})
    cm.create_checkpoint("pipeline-2", "step-1", {})
    pipelines = cm.list_pipelines()
    assert "pipeline-1" in pipelines
    assert "pipeline-2" in pipelines
    print("OK: list pipelines")


def test_callbacks():
    cm = PipelineCheckpointManager()
    fired = []
    cm.on_change("mon", lambda a, d: fired.append(a))
    cm.create_checkpoint("pipeline-1", "step-1", {})
    assert len(fired) >= 1
    assert cm.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    cm = PipelineCheckpointManager()
    cm.create_checkpoint("pipeline-1", "step-1", {})
    stats = cm.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    cm = PipelineCheckpointManager()
    cm.create_checkpoint("pipeline-1", "step-1", {})
    cm.reset()
    assert cm.get_checkpoint_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Checkpoint Manager Tests ===\n")
    test_create_checkpoint()
    test_get_checkpoint()
    test_get_latest_checkpoint()
    test_get_checkpoints()
    test_delete_checkpoint()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 9 TESTS PASSED ===")


if __name__ == "__main__":
    main()
