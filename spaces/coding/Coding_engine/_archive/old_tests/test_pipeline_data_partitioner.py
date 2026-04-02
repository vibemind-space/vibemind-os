"""Test pipeline data partitioner -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_data_partitioner import PipelineDataPartitioner


def test_create_partition():
    dp = PipelineDataPartitioner()
    pid = dp.create_partition("pipeline-1", total_items=100, partition_count=4)
    assert len(pid) > 0
    assert pid.startswith("pdp-")
    print("OK: create partition")


def test_get_partition():
    dp = PipelineDataPartitioner()
    pid = dp.create_partition("pipeline-1", total_items=100, partition_count=4)
    part = dp.get_partition(pid)
    assert part is not None
    assert part["pipeline_id"] == "pipeline-1"
    assert part["total_items"] == 100
    assert dp.get_partition("nonexistent") is None
    print("OK: get partition")


def test_get_partition_ranges():
    dp = PipelineDataPartitioner()
    pid = dp.create_partition("pipeline-1", total_items=100, partition_count=4)
    ranges = dp.get_partition_ranges(pid)
    assert len(ranges) == 4
    total = sum(r["size"] for r in ranges)
    assert total == 100
    print("OK: get partition ranges")


def test_mark_partition_complete():
    dp = PipelineDataPartitioner()
    pid = dp.create_partition("pipeline-1", total_items=100, partition_count=4)
    assert dp.mark_partition_complete(pid, 0) is True
    assert dp.mark_partition_complete(pid, 1) is True
    print("OK: mark partition complete")


def test_get_completion_status():
    dp = PipelineDataPartitioner()
    pid = dp.create_partition("pipeline-1", total_items=100, partition_count=4)
    dp.mark_partition_complete(pid, 0)
    dp.mark_partition_complete(pid, 1)
    status = dp.get_completion_status(pid)
    assert status["total"] == 4
    assert status["completed"] == 2
    assert abs(status["percentage"] - 50.0) < 0.1
    print("OK: get completion status")


def test_list_pipelines():
    dp = PipelineDataPartitioner()
    dp.create_partition("pipeline-1", total_items=50)
    dp.create_partition("pipeline-2", total_items=100)
    pipelines = dp.list_pipelines()
    assert "pipeline-1" in pipelines
    assert "pipeline-2" in pipelines
    print("OK: list pipelines")


def test_callbacks():
    dp = PipelineDataPartitioner()
    fired = []
    dp.on_change("mon", lambda a, d: fired.append(a))
    dp.create_partition("pipeline-1", total_items=50)
    assert len(fired) >= 1
    assert dp.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    dp = PipelineDataPartitioner()
    dp.create_partition("pipeline-1", total_items=50)
    stats = dp.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    dp = PipelineDataPartitioner()
    dp.create_partition("pipeline-1", total_items=50)
    dp.reset()
    assert dp.get_partition_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Data Partitioner Tests ===\n")
    test_create_partition()
    test_get_partition()
    test_get_partition_ranges()
    test_mark_partition_complete()
    test_get_completion_status()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 9 TESTS PASSED ===")


if __name__ == "__main__":
    main()
