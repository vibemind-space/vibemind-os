"""Test pipeline checkpoint store -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_checkpoint_store import PipelineCheckpointStore


def test_save_checkpoint():
    cs = PipelineCheckpointStore()
    cid = cs.save_checkpoint("deploy", "exec-1", "build", {"progress": 50}, tags=["ci"])
    assert len(cid) > 0
    c = cs.get_checkpoint(cid)
    assert c is not None
    assert c["pipeline_name"] == "deploy"
    assert c["step_name"] == "build"
    print("OK: save checkpoint")


def test_get_latest_checkpoint():
    cs = PipelineCheckpointStore()
    cs.save_checkpoint("deploy", "exec-1", "build", {"progress": 50})
    import time
    time.sleep(0.01)
    cs.save_checkpoint("deploy", "exec-1", "test", {"progress": 75})
    latest = cs.get_latest_checkpoint("deploy", "exec-1")
    assert latest is not None
    assert latest["step_name"] == "test"
    print("OK: get latest checkpoint")


def test_list_checkpoints():
    cs = PipelineCheckpointStore()
    cs.save_checkpoint("deploy", "exec-1", "build", {"p": 1})
    cs.save_checkpoint("deploy", "exec-1", "test", {"p": 2})
    cs.save_checkpoint("test", "exec-2", "lint", {"p": 3})
    all_cp = cs.list_checkpoints()
    assert len(all_cp) == 3
    deploy_cp = cs.list_checkpoints(pipeline_name="deploy")
    assert len(deploy_cp) == 2
    print("OK: list checkpoints")


def test_restore_checkpoint():
    cs = PipelineCheckpointStore()
    cid = cs.save_checkpoint("deploy", "exec-1", "build", {"progress": 50, "data": [1, 2, 3]})
    state = cs.restore_checkpoint(cid)
    assert state is not None
    assert state["progress"] == 50
    print("OK: restore checkpoint")


def test_delete_checkpoint():
    cs = PipelineCheckpointStore()
    cid = cs.save_checkpoint("deploy", "exec-1", "build", {"p": 1})
    assert cs.delete_checkpoint(cid) is True
    assert cs.delete_checkpoint(cid) is False
    print("OK: delete checkpoint")


def test_purge():
    cs = PipelineCheckpointStore()
    cs.save_checkpoint("deploy", "exec-1", "build", {"p": 1})
    import time
    time.sleep(0.01)
    count = cs.purge(before_timestamp=time.time() + 1)
    assert count >= 1
    print("OK: purge")


def test_callbacks():
    cs = PipelineCheckpointStore()
    fired = []
    cs.on_change("mon", lambda a, d: fired.append(a))
    cs.save_checkpoint("deploy", "exec-1", "build", {"p": 1})
    assert len(fired) >= 1
    assert cs.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    cs = PipelineCheckpointStore()
    cs.save_checkpoint("deploy", "exec-1", "build", {"p": 1})
    stats = cs.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    cs = PipelineCheckpointStore()
    cs.save_checkpoint("deploy", "exec-1", "build", {"p": 1})
    cs.reset()
    assert cs.list_checkpoints() == []
    print("OK: reset")


def main():
    print("=== Pipeline Checkpoint Store Tests ===\n")
    test_save_checkpoint()
    test_get_latest_checkpoint()
    test_list_checkpoints()
    test_restore_checkpoint()
    test_delete_checkpoint()
    test_purge()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 9 TESTS PASSED ===")


if __name__ == "__main__":
    main()
