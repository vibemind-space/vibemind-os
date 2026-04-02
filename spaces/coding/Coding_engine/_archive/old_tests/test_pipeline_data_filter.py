"""Test pipeline data filter -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_data_filter import PipelineDataFilter


def test_add_filter():
    df = PipelineDataFilter()
    fid = df.add_filter("pipeline-1", "status", "eq", "active")
    assert len(fid) > 0
    assert fid.startswith("pdf2-")
    print("OK: add filter")


def test_apply_filters_eq():
    df = PipelineDataFilter()
    df.add_filter("pipeline-1", "status", "eq", "active")
    records = [{"status": "active", "name": "a"}, {"status": "inactive", "name": "b"}]
    result = df.apply_filters("pipeline-1", records)
    assert len(result) == 1
    assert result[0]["name"] == "a"
    print("OK: apply filters eq")


def test_apply_filters_gt():
    df = PipelineDataFilter()
    df.add_filter("pipeline-1", "score", "gt", 50)
    records = [{"score": 80}, {"score": 30}, {"score": 60}]
    result = df.apply_filters("pipeline-1", records)
    assert len(result) == 2
    print("OK: apply filters gt")


def test_apply_filters_contains():
    df = PipelineDataFilter()
    df.add_filter("pipeline-1", "tags", "contains", "important")
    records = [{"tags": ["important", "urgent"]}, {"tags": ["normal"]}]
    result = df.apply_filters("pipeline-1", records)
    assert len(result) == 1
    print("OK: apply filters contains")


def test_apply_multiple_filters():
    df = PipelineDataFilter()
    df.add_filter("pipeline-1", "status", "eq", "active")
    df.add_filter("pipeline-1", "score", "gt", 50)
    records = [
        {"status": "active", "score": 80},
        {"status": "active", "score": 30},
        {"status": "inactive", "score": 90},
    ]
    result = df.apply_filters("pipeline-1", records)
    assert len(result) == 1
    assert result[0]["score"] == 80
    print("OK: apply multiple filters")


def test_get_filters():
    df = PipelineDataFilter()
    df.add_filter("pipeline-1", "status", "eq", "active")
    df.add_filter("pipeline-1", "score", "gt", 50)
    filters = df.get_filters("pipeline-1")
    assert len(filters) == 2
    print("OK: get filters")


def test_remove_filter():
    df = PipelineDataFilter()
    fid = df.add_filter("pipeline-1", "status", "eq", "active")
    assert df.remove_filter(fid) is True
    assert df.remove_filter("nonexistent") is False
    assert df.get_filter_count("pipeline-1") == 0
    print("OK: remove filter")


def test_get_filter_count():
    df = PipelineDataFilter()
    df.add_filter("pipeline-1", "status", "eq", "active")
    df.add_filter("pipeline-2", "score", "gt", 50)
    assert df.get_filter_count() == 2
    assert df.get_filter_count("pipeline-1") == 1
    print("OK: get filter count")


def test_list_pipelines():
    df = PipelineDataFilter()
    df.add_filter("pipeline-1", "status", "eq", "active")
    df.add_filter("pipeline-2", "score", "gt", 50)
    pipelines = df.list_pipelines()
    assert "pipeline-1" in pipelines
    assert "pipeline-2" in pipelines
    print("OK: list pipelines")


def test_callbacks():
    df = PipelineDataFilter()
    fired = []
    df.on_change("mon", lambda a, d: fired.append(a))
    df.add_filter("pipeline-1", "status", "eq", "active")
    assert len(fired) >= 1
    assert df.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    df = PipelineDataFilter()
    df.add_filter("pipeline-1", "status", "eq", "active")
    stats = df.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    df = PipelineDataFilter()
    df.add_filter("pipeline-1", "status", "eq", "active")
    df.reset()
    assert df.get_filter_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Data Filter Tests ===\n")
    test_add_filter()
    test_apply_filters_eq()
    test_apply_filters_gt()
    test_apply_filters_contains()
    test_apply_multiple_filters()
    test_get_filters()
    test_remove_filter()
    test_get_filter_count()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 12 TESTS PASSED ===")


if __name__ == "__main__":
    main()
