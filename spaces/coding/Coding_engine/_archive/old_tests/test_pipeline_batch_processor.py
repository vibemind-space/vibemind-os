"""Test pipeline batch processor."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_batch_processor import PipelineBatchProcessor


def test_create_batch():
    """Create and retrieve batch."""
    bp = PipelineBatchProcessor()
    bid = bp.create_batch("etl_job", total_items=1000, batch_size=100,
                          tags=["daily"])
    assert bid.startswith("batch-")

    b = bp.get_batch(bid)
    assert b is not None
    assert b["name"] == "etl_job"
    assert b["total_items"] == 1000
    assert b["batch_size"] == 100
    assert b["status"] == "pending"
    assert b["total_batches"] == 10
    assert b["progress_pct"] == 0.0

    assert bp.remove_batch(bid) is True
    assert bp.remove_batch(bid) is False
    print("OK: create batch")


def test_invalid_batch():
    """Invalid batch rejected."""
    bp = PipelineBatchProcessor()
    assert bp.create_batch("", 100) == ""
    assert bp.create_batch("x", 0) == ""
    assert bp.create_batch("x", 100, batch_size=0) == ""
    print("OK: invalid batch")


def test_max_batches():
    """Max batches enforced."""
    bp = PipelineBatchProcessor(max_batches=2)
    bp.create_batch("a", 10)
    bp.create_batch("b", 10)
    assert bp.create_batch("c", 10) == ""
    print("OK: max batches")


def test_start_batch():
    """Start a batch."""
    bp = PipelineBatchProcessor()
    bid = bp.create_batch("job", 100)

    assert bp.start_batch(bid) is True
    assert bp.get_batch(bid)["status"] == "processing"
    assert bp.start_batch(bid) is False
    print("OK: start batch")


def test_cancel_batch():
    """Cancel a batch."""
    bp = PipelineBatchProcessor()
    bid = bp.create_batch("job", 100)

    assert bp.cancel_batch(bid) is True
    assert bp.get_batch(bid)["status"] == "cancelled"
    assert bp.cancel_batch(bid) is False
    print("OK: cancel batch")


def test_record_chunk():
    """Record batch chunk processing."""
    bp = PipelineBatchProcessor()
    bid = bp.create_batch("job", 200, batch_size=100)
    bp.start_batch(bid)

    rid = bp.record_chunk(bid, items_processed=100,
                          items_succeeded=95, items_failed=5,
                          duration_ms=500.0)
    assert rid.startswith("bres-")

    b = bp.get_batch(bid)
    assert b["processed_count"] == 100
    assert b["success_count"] == 95
    assert b["error_count"] == 5
    assert b["progress_pct"] == 50.0
    assert b["status"] == "processing"
    print("OK: record chunk")


def test_auto_complete():
    """Batch auto-completes when all items processed."""
    bp = PipelineBatchProcessor()
    bid = bp.create_batch("job", 100, batch_size=50)
    bp.start_batch(bid)

    bp.record_chunk(bid, items_processed=50, items_succeeded=50)
    assert bp.get_batch(bid)["status"] == "processing"

    bp.record_chunk(bid, items_processed=50, items_succeeded=50)
    assert bp.get_batch(bid)["status"] == "completed"
    assert bp.get_batch(bid)["progress_pct"] == 100.0
    print("OK: auto complete")


def test_auto_fail():
    """Batch fails when all items fail."""
    bp = PipelineBatchProcessor()
    bid = bp.create_batch("job", 50, batch_size=50)
    bp.start_batch(bid)

    bp.record_chunk(bid, items_processed=50, items_succeeded=0,
                    items_failed=50)
    assert bp.get_batch(bid)["status"] == "failed"
    print("OK: auto fail")


def test_default_success():
    """Items default to succeeded if not specified."""
    bp = PipelineBatchProcessor()
    bid = bp.create_batch("job", 50, batch_size=50)
    bp.start_batch(bid)

    bp.record_chunk(bid, items_processed=50)
    b = bp.get_batch(bid)
    assert b["success_count"] == 50
    assert b["error_count"] == 0
    print("OK: default success")


def test_remove_cascades():
    """Remove batch removes results."""
    bp = PipelineBatchProcessor()
    bid = bp.create_batch("job", 100)
    bp.start_batch(bid)
    bp.record_chunk(bid, 50)

    bp.remove_batch(bid)
    assert bp.get_batch_results(bid) == []
    print("OK: remove cascades")


def test_search_batches():
    """Search batches."""
    bp = PipelineBatchProcessor()
    bp.create_batch("a", 100, tags=["daily"])
    b2 = bp.create_batch("b", 100)
    bp.cancel_batch(b2)

    all_b = bp.search_batches()
    assert len(all_b) == 2

    by_status = bp.search_batches(status="cancelled")
    assert len(by_status) == 1

    by_tag = bp.search_batches(tag="daily")
    assert len(by_tag) == 1
    print("OK: search batches")


def test_batch_results():
    """Get batch results."""
    bp = PipelineBatchProcessor()
    bid = bp.create_batch("job", 200, batch_size=100)
    bp.start_batch(bid)

    bp.record_chunk(bid, 100, duration_ms=100.0)
    bp.record_chunk(bid, 100, duration_ms=200.0)

    results = bp.get_batch_results(bid)
    assert len(results) == 2
    assert results[0]["batch_num"] == 1
    assert results[1]["batch_num"] == 2
    print("OK: batch results")


def test_batch_throughput():
    """Get batch throughput."""
    bp = PipelineBatchProcessor()
    bid = bp.create_batch("job", 200, batch_size=100)
    bp.start_batch(bid)

    bp.record_chunk(bid, 100, duration_ms=100.0)
    bp.record_chunk(bid, 100, duration_ms=200.0)

    tp = bp.get_batch_throughput(bid)
    assert tp["chunks_processed"] == 2
    assert tp["total_items"] == 200
    assert tp["total_duration_ms"] == 300.0
    assert tp["avg_chunk_duration_ms"] == 150.0
    print("OK: batch throughput")


def test_active_batches():
    """Get active batches."""
    bp = PipelineBatchProcessor()
    bp.create_batch("pending_job", 100)
    b2 = bp.create_batch("active_job", 100)
    bp.start_batch(b2)

    active = bp.get_active_batches()
    assert len(active) == 1
    assert active[0]["name"] == "active_job"
    print("OK: active batches")


def test_callback():
    """Callback fires on batch create and complete."""
    bp = PipelineBatchProcessor()
    fired = []
    bp.on_change("mon", lambda a, d: fired.append(a))

    bid = bp.create_batch("job", 50, batch_size=50)
    assert "batch_created" in fired

    bp.start_batch(bid)
    bp.record_chunk(bid, 50)
    assert "batch_completed" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    bp = PipelineBatchProcessor()
    assert bp.on_change("mon", lambda a, d: None) is True
    assert bp.on_change("mon", lambda a, d: None) is False
    assert bp.remove_callback("mon") is True
    assert bp.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    bp = PipelineBatchProcessor()
    bid = bp.create_batch("job", 100, batch_size=50)
    bp.start_batch(bid)
    bp.record_chunk(bid, 50, items_succeeded=45, items_failed=5)
    bp.record_chunk(bid, 50, items_succeeded=50)

    stats = bp.get_stats()
    assert stats["total_batches_created"] == 1
    assert stats["total_items_processed"] == 100
    assert stats["total_items_succeeded"] == 95
    assert stats["total_items_failed"] == 5
    assert stats["total_completed"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    bp = PipelineBatchProcessor()
    bid = bp.create_batch("job", 100)
    bp.start_batch(bid)
    bp.record_chunk(bid, 50)

    bp.reset()
    assert bp.search_batches() == []
    stats = bp.get_stats()
    assert stats["current_batches"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Batch Processor Tests ===\n")
    test_create_batch()
    test_invalid_batch()
    test_max_batches()
    test_start_batch()
    test_cancel_batch()
    test_record_chunk()
    test_auto_complete()
    test_auto_fail()
    test_default_success()
    test_remove_cascades()
    test_search_batches()
    test_batch_results()
    test_batch_throughput()
    test_active_batches()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 18 TESTS PASSED ===")


if __name__ == "__main__":
    main()
