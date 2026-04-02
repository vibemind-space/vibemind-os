"""Test pipeline data splitter -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_data_splitter import PipelineDataSplitter


def test_create_splitter():
    ds = PipelineDataSplitter()
    sid = ds.create_splitter("pipeline-1", strategy="chunks", chunk_size=5)
    assert len(sid) > 0
    assert sid.startswith("pds-")
    print("OK: create splitter")


def test_split_chunks():
    ds = PipelineDataSplitter()
    sid = ds.create_splitter("pipeline-1", strategy="chunks", chunk_size=3)
    result = ds.split(sid, [1, 2, 3, 4, 5, 6, 7])
    assert len(result) == 3  # [1,2,3], [4,5,6], [7]
    assert result[0] == [1, 2, 3]
    assert result[2] == [7]
    print("OK: split chunks")


def test_split_empty():
    ds = PipelineDataSplitter()
    sid = ds.create_splitter("pipeline-1", strategy="chunks", chunk_size=3)
    result = ds.split(sid, [])
    assert len(result) == 0
    print("OK: split empty")


def test_get_splitter():
    ds = PipelineDataSplitter()
    sid = ds.create_splitter("pipeline-1", strategy="chunks", chunk_size=5)
    splitter = ds.get_splitter(sid)
    assert splitter is not None
    assert splitter["chunk_size"] == 5
    assert ds.get_splitter("nonexistent") is None
    print("OK: get splitter")


def test_get_splitters():
    ds = PipelineDataSplitter()
    ds.create_splitter("pipeline-1", chunk_size=3)
    ds.create_splitter("pipeline-1", chunk_size=5)
    splitters = ds.get_splitters("pipeline-1")
    assert len(splitters) == 2
    print("OK: get splitters")


def test_get_splitter_count():
    ds = PipelineDataSplitter()
    ds.create_splitter("pipeline-1")
    ds.create_splitter("pipeline-2")
    assert ds.get_splitter_count() == 2
    assert ds.get_splitter_count("pipeline-1") == 1
    print("OK: get splitter count")


def test_list_pipelines():
    ds = PipelineDataSplitter()
    ds.create_splitter("pipeline-1")
    ds.create_splitter("pipeline-2")
    pipelines = ds.list_pipelines()
    assert "pipeline-1" in pipelines
    assert "pipeline-2" in pipelines
    print("OK: list pipelines")


def test_callbacks():
    ds = PipelineDataSplitter()
    fired = []
    ds.on_change("mon", lambda a, d: fired.append(a))
    ds.create_splitter("pipeline-1")
    assert len(fired) >= 1
    assert ds.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    ds = PipelineDataSplitter()
    ds.create_splitter("pipeline-1")
    stats = ds.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    ds = PipelineDataSplitter()
    ds.create_splitter("pipeline-1")
    ds.reset()
    assert ds.get_splitter_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Data Splitter Tests ===\n")
    test_create_splitter()
    test_split_chunks()
    test_split_empty()
    test_get_splitter()
    test_get_splitters()
    test_get_splitter_count()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")


if __name__ == "__main__":
    main()
