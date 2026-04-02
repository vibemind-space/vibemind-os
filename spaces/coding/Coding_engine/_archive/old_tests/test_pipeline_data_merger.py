"""Test pipeline data merger -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_data_merger import PipelineDataMerger


def test_create_merge():
    dm = PipelineDataMerger()
    mid = dm.create_merge("pipeline-1", ["src_a", "src_b"])
    assert len(mid) > 0
    assert mid.startswith("pdm-")
    print("OK: create merge")


def test_execute_merge_concat():
    dm = PipelineDataMerger()
    mid = dm.create_merge("pipeline-1", ["a", "b"], strategy="concat")
    result = dm.execute_merge(mid, [[1, 2], [3, 4]])
    assert result["result"] == [1, 2, 3, 4]
    assert result["source_count"] == 2
    print("OK: execute merge concat")


def test_execute_merge_union():
    dm = PipelineDataMerger()
    mid = dm.create_merge("pipeline-1", ["a", "b"], strategy="union")
    result = dm.execute_merge(mid, [[1, 2, 3], [2, 3, 4]])
    assert set(result["result"]) == {1, 2, 3, 4}
    print("OK: execute merge union")


def test_get_merge():
    dm = PipelineDataMerger()
    mid = dm.create_merge("pipeline-1", ["a", "b"])
    merge = dm.get_merge(mid)
    assert merge is not None
    assert merge["pipeline_id"] == "pipeline-1"
    assert dm.get_merge("nonexistent") is None
    print("OK: get merge")


def test_get_merges():
    dm = PipelineDataMerger()
    dm.create_merge("pipeline-1", ["a"])
    dm.create_merge("pipeline-1", ["b"])
    merges = dm.get_merges("pipeline-1")
    assert len(merges) == 2
    print("OK: get merges")


def test_get_merge_count():
    dm = PipelineDataMerger()
    dm.create_merge("pipeline-1", ["a"])
    dm.create_merge("pipeline-2", ["b"])
    assert dm.get_merge_count() == 2
    assert dm.get_merge_count("pipeline-1") == 1
    print("OK: get merge count")


def test_list_pipelines():
    dm = PipelineDataMerger()
    dm.create_merge("pipeline-1", ["a"])
    dm.create_merge("pipeline-2", ["b"])
    pipelines = dm.list_pipelines()
    assert "pipeline-1" in pipelines
    assert "pipeline-2" in pipelines
    print("OK: list pipelines")


def test_callbacks():
    dm = PipelineDataMerger()
    fired = []
    dm.on_change("mon", lambda a, d: fired.append(a))
    dm.create_merge("pipeline-1", ["a"])
    assert len(fired) >= 1
    assert dm.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    dm = PipelineDataMerger()
    dm.create_merge("pipeline-1", ["a"])
    stats = dm.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    dm = PipelineDataMerger()
    dm.create_merge("pipeline-1", ["a"])
    dm.reset()
    assert dm.get_merge_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Data Merger Tests ===\n")
    test_create_merge()
    test_execute_merge_concat()
    test_execute_merge_union()
    test_get_merge()
    test_get_merges()
    test_get_merge_count()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")


if __name__ == "__main__":
    main()
