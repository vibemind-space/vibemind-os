"""Test pipeline batch store -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_batch_store import PipelineBatchStore


def test_create_batch():
    bs = PipelineBatchStore()
    bid = bs.create_batch("deploy-all", ["service-a", "service-b", "service-c"], metadata={"env": "prod"})
    assert len(bid) > 0
    assert bid.startswith("pbs-")
    b = bs.get_batch(bid)
    assert b is not None
    assert b["name"] == "deploy-all"
    assert b["status"] == "pending"
    print("OK: create batch")


def test_start_batch():
    bs = PipelineBatchStore()
    bid = bs.create_batch("batch1", ["p1", "p2"])
    assert bs.start_batch(bid) is True
    b = bs.get_batch(bid)
    assert b["status"] == "running"
    assert bs.start_batch(bid) is False  # Already running
    print("OK: start batch")


def test_complete_batch():
    bs = PipelineBatchStore()
    bid = bs.create_batch("batch1", ["p1"])
    bs.start_batch(bid)
    assert bs.complete_batch(bid, results={"total": 1}) is True
    b = bs.get_batch(bid)
    assert b["status"] == "completed"
    print("OK: complete batch")


def test_fail_batch():
    bs = PipelineBatchStore()
    bid = bs.create_batch("batch1", ["p1"])
    bs.start_batch(bid)
    assert bs.fail_batch(bid, error="timeout") is True
    b = bs.get_batch(bid)
    assert b["status"] == "failed"
    print("OK: fail batch")


def test_cancel_batch():
    bs = PipelineBatchStore()
    bid1 = bs.create_batch("batch1", ["p1"])
    assert bs.cancel_batch(bid1) is True
    b = bs.get_batch(bid1)
    assert b["status"] == "cancelled"
    # Cancel running
    bid2 = bs.create_batch("batch2", ["p1"])
    bs.start_batch(bid2)
    assert bs.cancel_batch(bid2) is True
    print("OK: cancel batch")


def test_list_batches():
    bs = PipelineBatchStore()
    bs.create_batch("b1", ["p1"])
    bid2 = bs.create_batch("b2", ["p2"])
    bs.start_batch(bid2)
    all_b = bs.list_batches()
    assert len(all_b) == 2
    pending = bs.list_batches(status="pending")
    assert len(pending) == 1
    print("OK: list batches")


def test_add_pipeline_result():
    bs = PipelineBatchStore()
    bid = bs.create_batch("batch1", ["p1", "p2"])
    bs.start_batch(bid)
    assert bs.add_pipeline_result(bid, "p1", True, result={"output": "ok"}) is True
    assert bs.add_pipeline_result(bid, "p2", False, result={"error": "fail"}) is True
    print("OK: add pipeline result")


def test_get_batch_progress():
    bs = PipelineBatchStore()
    bid = bs.create_batch("batch1", ["p1", "p2", "p3"])
    bs.start_batch(bid)
    bs.add_pipeline_result(bid, "p1", True)
    bs.add_pipeline_result(bid, "p2", False)
    progress = bs.get_batch_progress(bid)
    assert progress is not None
    assert progress["total"] == 3
    print("OK: get batch progress")


def test_callbacks():
    bs = PipelineBatchStore()
    fired = []
    bs.on_change("mon", lambda a, d: fired.append(a))
    bs.create_batch("batch1", ["p1"])
    assert len(fired) >= 1
    assert bs.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    bs = PipelineBatchStore()
    bs.create_batch("batch1", ["p1"])
    stats = bs.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    bs = PipelineBatchStore()
    bs.create_batch("batch1", ["p1"])
    bs.reset()
    assert bs.list_batches() == []
    print("OK: reset")


def main():
    print("=== Pipeline Batch Store Tests ===\n")
    test_create_batch()
    test_start_batch()
    test_complete_batch()
    test_fail_batch()
    test_cancel_batch()
    test_list_batches()
    test_add_pipeline_result()
    test_get_batch_progress()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
