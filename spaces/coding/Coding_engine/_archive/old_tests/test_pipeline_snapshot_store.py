"""Test pipeline snapshot store -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_snapshot_store import PipelineSnapshotStore


def test_save_snapshot():
    ss = PipelineSnapshotStore()
    sid = ss.save_snapshot("pipeline-1", {"step": 5, "status": "running"}, label="checkpoint-1")
    assert len(sid) > 0
    assert sid.startswith("pss-")
    print("OK: save snapshot")


def test_get_snapshot():
    ss = PipelineSnapshotStore()
    sid = ss.save_snapshot("pipeline-1", {"step": 5}, label="cp1")
    snap = ss.get_snapshot(sid)
    assert snap is not None
    assert snap["pipeline_id"] == "pipeline-1"
    assert snap["label"] == "cp1"
    assert ss.get_snapshot("nonexistent") is None
    print("OK: get snapshot")


def test_get_latest_snapshot():
    ss = PipelineSnapshotStore()
    ss.save_snapshot("pipeline-1", {"step": 1})
    ss.save_snapshot("pipeline-1", {"step": 2})
    ss.save_snapshot("pipeline-1", {"step": 3})
    latest = ss.get_latest_snapshot("pipeline-1")
    assert latest is not None
    assert ss.get_latest_snapshot("nonexistent") is None
    print("OK: get latest snapshot")


def test_get_snapshots():
    ss = PipelineSnapshotStore()
    ss.save_snapshot("pipeline-1", {"s": 1})
    ss.save_snapshot("pipeline-1", {"s": 2})
    ss.save_snapshot("pipeline-2", {"s": 3})
    snaps = ss.get_snapshots("pipeline-1")
    assert len(snaps) == 2
    print("OK: get snapshots")


def test_restore_snapshot():
    ss = PipelineSnapshotStore()
    sid = ss.save_snapshot("pipeline-1", {"step": 5, "data": [1, 2, 3]})
    state = ss.restore_snapshot(sid)
    assert state is not None
    assert ss.restore_snapshot("nonexistent") is None
    print("OK: restore snapshot")


def test_delete_snapshot():
    ss = PipelineSnapshotStore()
    sid = ss.save_snapshot("pipeline-1", {"s": 1})
    assert ss.delete_snapshot(sid) is True
    assert ss.delete_snapshot(sid) is False
    print("OK: delete snapshot")


def test_list_pipelines():
    ss = PipelineSnapshotStore()
    ss.save_snapshot("pipeline-1", {"s": 1})
    ss.save_snapshot("pipeline-2", {"s": 2})
    pipelines = ss.list_pipelines()
    assert "pipeline-1" in pipelines
    assert "pipeline-2" in pipelines
    print("OK: list pipelines")


def test_callbacks():
    ss = PipelineSnapshotStore()
    fired = []
    ss.on_change("mon", lambda a, d: fired.append(a))
    ss.save_snapshot("pipeline-1", {"s": 1})
    assert len(fired) >= 1
    assert ss.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    ss = PipelineSnapshotStore()
    ss.save_snapshot("pipeline-1", {"s": 1})
    stats = ss.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    ss = PipelineSnapshotStore()
    ss.save_snapshot("pipeline-1", {"s": 1})
    ss.reset()
    assert ss.get_snapshot_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Snapshot Store Tests ===\n")
    test_save_snapshot()
    test_get_snapshot()
    test_get_latest_snapshot()
    test_get_snapshots()
    test_restore_snapshot()
    test_delete_snapshot()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")


if __name__ == "__main__":
    main()
