"""Test pipeline rollback manager -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_rollback_manager import PipelineRollbackManager


def test_save_snapshot():
    rm = PipelineRollbackManager()
    sid = rm.save_snapshot("pipeline-1", {"step": 3, "data": "abc"}, label="before-transform")
    assert len(sid) > 0
    assert sid.startswith("prm-")
    print("OK: save snapshot")


def test_get_snapshot():
    rm = PipelineRollbackManager()
    sid = rm.save_snapshot("pipeline-1", {"step": 3})
    snap = rm.get_snapshot(sid)
    assert snap is not None
    assert snap["state"]["step"] == 3
    assert rm.get_snapshot("nonexistent") is None
    print("OK: get snapshot")


def test_rollback():
    rm = PipelineRollbackManager()
    rm.save_snapshot("pipeline-1", {"step": 1})
    rm.save_snapshot("pipeline-1", {"step": 2})
    state = rm.rollback("pipeline-1")
    assert state is not None
    assert state["restored_state"]["step"] == 2
    print("OK: rollback")


def test_rollback_empty():
    rm = PipelineRollbackManager()
    assert rm.rollback("nonexistent") is None
    print("OK: rollback empty")


def test_get_snapshots():
    rm = PipelineRollbackManager()
    rm.save_snapshot("pipeline-1", {"step": 1})
    rm.save_snapshot("pipeline-1", {"step": 2})
    snaps = rm.get_snapshots("pipeline-1")
    assert len(snaps) == 2
    print("OK: get snapshots")


def test_get_latest_snapshot():
    rm = PipelineRollbackManager()
    rm.save_snapshot("pipeline-1", {"step": 1}, label="first")
    rm.save_snapshot("pipeline-1", {"step": 2}, label="second")
    latest = rm.get_latest_snapshot("pipeline-1")
    assert latest is not None
    assert latest["state"]["step"] == 2
    print("OK: get latest snapshot")


def test_delete_snapshot():
    rm = PipelineRollbackManager()
    sid = rm.save_snapshot("pipeline-1", {"step": 1})
    assert rm.delete_snapshot(sid) is True
    assert rm.get_snapshot(sid) is None
    assert rm.delete_snapshot("nonexistent") is False
    print("OK: delete snapshot")


def test_list_pipelines():
    rm = PipelineRollbackManager()
    rm.save_snapshot("pipeline-1", {"step": 1})
    rm.save_snapshot("pipeline-2", {"step": 1})
    pipelines = rm.list_pipelines()
    assert "pipeline-1" in pipelines
    assert "pipeline-2" in pipelines
    print("OK: list pipelines")


def test_callbacks():
    rm = PipelineRollbackManager()
    fired = []
    rm.on_change("mon", lambda a, **kw: fired.append(a))
    rm.save_snapshot("pipeline-1", {"step": 1})
    assert len(fired) >= 1
    assert rm.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    rm = PipelineRollbackManager()
    rm.save_snapshot("pipeline-1", {"step": 1})
    stats = rm.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    rm = PipelineRollbackManager()
    rm.save_snapshot("pipeline-1", {"step": 1})
    rm.reset()
    assert rm.get_snapshot_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Rollback Manager Tests ===\n")
    test_save_snapshot()
    test_get_snapshot()
    test_rollback()
    test_rollback_empty()
    test_get_snapshots()
    test_get_latest_snapshot()
    test_delete_snapshot()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
