"""Test pipeline state snapshot -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_state_snapshot import PipelineStateSnapshot


def test_take_snapshot():
    svc = PipelineStateSnapshot()
    sid = svc.take_snapshot("pipeline-1", {"step": 5, "status": "running"}, label="checkpoint-1")
    assert len(sid) > 0
    assert sid.startswith("pss-")
    print("OK: take snapshot")


def test_get_snapshot():
    svc = PipelineStateSnapshot()
    sid = svc.take_snapshot("pipeline-1", {"step": 5}, label="cp1")
    snap = svc.get_snapshot(sid)
    assert snap is not None
    assert snap["pipeline_id"] == "pipeline-1"
    assert snap["label"] == "cp1"
    assert snap["state_data"]["step"] == 5
    assert svc.get_snapshot("nonexistent") is None
    print("OK: get snapshot")


def test_get_snapshots():
    svc = PipelineStateSnapshot()
    svc.take_snapshot("pipeline-1", {"s": 1})
    svc.take_snapshot("pipeline-1", {"s": 2})
    svc.take_snapshot("pipeline-2", {"s": 3})
    snaps = svc.get_snapshots("pipeline-1")
    assert len(snaps) == 2
    # ordered by timestamp ascending
    assert snaps[0]["state_data"]["s"] == 1
    assert snaps[1]["state_data"]["s"] == 2
    print("OK: get snapshots")


def test_get_latest_snapshot():
    svc = PipelineStateSnapshot()
    svc.take_snapshot("pipeline-1", {"step": 1})
    svc.take_snapshot("pipeline-1", {"step": 2})
    svc.take_snapshot("pipeline-1", {"step": 3})
    latest = svc.get_latest_snapshot("pipeline-1")
    assert latest is not None
    assert latest["state_data"]["step"] == 3
    assert svc.get_latest_snapshot("nonexistent") is None
    print("OK: get latest snapshot")


def test_restore_snapshot():
    svc = PipelineStateSnapshot()
    sid = svc.take_snapshot("pipeline-1", {"step": 5, "data": [1, 2, 3]})
    state = svc.restore_snapshot(sid)
    assert state is not None
    assert state["step"] == 5
    assert state["data"] == [1, 2, 3]
    assert svc.restore_snapshot("nonexistent") is None
    print("OK: restore snapshot")


def test_delete_snapshot():
    svc = PipelineStateSnapshot()
    sid = svc.take_snapshot("pipeline-1", {"s": 1})
    assert svc.delete_snapshot(sid) is True
    assert svc.delete_snapshot(sid) is False
    assert svc.get_snapshot(sid) is None
    print("OK: delete snapshot")


def test_get_snapshot_count():
    svc = PipelineStateSnapshot()
    svc.take_snapshot("pipeline-1", {"s": 1})
    svc.take_snapshot("pipeline-1", {"s": 2})
    svc.take_snapshot("pipeline-2", {"s": 3})
    assert svc.get_snapshot_count() == 3
    assert svc.get_snapshot_count("pipeline-1") == 2
    assert svc.get_snapshot_count("pipeline-2") == 1
    assert svc.get_snapshot_count("nonexistent") == 0
    print("OK: get snapshot count")


def test_list_pipelines():
    svc = PipelineStateSnapshot()
    svc.take_snapshot("pipeline-1", {"s": 1})
    svc.take_snapshot("pipeline-2", {"s": 2})
    pipelines = svc.list_pipelines()
    assert "pipeline-1" in pipelines
    assert "pipeline-2" in pipelines
    assert len(pipelines) == 2
    print("OK: list pipelines")


def test_callbacks():
    svc = PipelineStateSnapshot()
    fired = []
    svc.on_change("mon", lambda a, d: fired.append((a, d)))
    svc.take_snapshot("pipeline-1", {"s": 1})
    assert len(fired) >= 1
    assert fired[0][0] == "snapshot_taken"
    assert svc.remove_callback("mon") is True
    assert svc.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    svc = PipelineStateSnapshot()
    svc.take_snapshot("pipeline-1", {"s": 1})
    stats = svc.get_stats()
    assert stats["total_taken"] == 1
    assert stats["current_snapshots"] == 1
    assert "max_entries" in stats
    print("OK: stats")


def test_reset():
    svc = PipelineStateSnapshot()
    svc.take_snapshot("pipeline-1", {"s": 1})
    svc.take_snapshot("pipeline-2", {"s": 2})
    svc.reset()
    assert svc.get_snapshot_count() == 0
    assert svc.list_pipelines() == []
    print("OK: reset")


def main():
    print("=== Pipeline State Snapshot Tests ===\n")
    test_take_snapshot()
    test_get_snapshot()
    test_get_snapshots()
    test_get_latest_snapshot()
    test_restore_snapshot()
    test_delete_snapshot()
    test_get_snapshot_count()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
