"""Tests for PipelineDataSorter."""

import sys
sys.path.insert(0, ".")

from src.services.pipeline_data_sorter import PipelineDataSorter


def test_configure_sort():
    s = PipelineDataSorter()
    cid = s.configure_sort("p1", "score", True)
    assert cid.startswith("pdso-"), f"Expected pdso- prefix, got {cid}"
    assert len(cid) > 5
    # empty args
    assert s.configure_sort("", "field") == ""
    assert s.configure_sort("p1", "") == ""
    print("  test_configure_sort PASSED")


def test_sort_ascending():
    s = PipelineDataSorter()
    s.configure_sort("p1", "score", ascending=True)
    records = [{"score": 30}, {"score": 10}, {"score": 20}]
    result = s.sort_records("p1", records)
    assert [r["score"] for r in result] == [10, 20, 30]
    print("  test_sort_ascending PASSED")


def test_sort_descending():
    s = PipelineDataSorter()
    s.configure_sort("p1", "score", ascending=False)
    records = [{"score": 30}, {"score": 10}, {"score": 20}]
    result = s.sort_records("p1", records)
    assert [r["score"] for r in result] == [30, 20, 10]
    print("  test_sort_descending PASSED")


def test_sort_missing_field():
    s = PipelineDataSorter()
    s.configure_sort("p1", "score", ascending=True)
    records = [{"score": 20}, {"name": "no_score"}, {"score": 10}]
    result = s.sort_records("p1", records)
    # Records with score should come first sorted, missing last
    assert result[0]["score"] == 10
    assert result[1]["score"] == 20
    assert "score" not in result[2]
    print("  test_sort_missing_field PASSED")


def test_get_config():
    s = PipelineDataSorter()
    s.configure_sort("p1", "name", True)
    cfg = s.get_config("p1")
    assert cfg is not None
    assert cfg["pipeline_id"] == "p1"
    assert cfg["sort_field"] == "name"
    assert cfg["ascending"] is True
    assert s.get_config("p99") is None
    print("  test_get_config PASSED")


def test_remove_config():
    s = PipelineDataSorter()
    cid = s.configure_sort("p1", "name", True)
    assert s.remove_config(cid) is True
    assert s.remove_config(cid) is False
    assert s.get_config("p1") is None
    print("  test_remove_config PASSED")


def test_get_config_count():
    s = PipelineDataSorter()
    s.configure_sort("p1", "k1")
    s.configure_sort("p1", "k2")
    s.configure_sort("p2", "k3")
    assert s.get_config_count() == 3
    assert s.get_config_count("p1") == 2
    assert s.get_config_count("p2") == 1
    assert s.get_config_count("p99") == 0
    print("  test_get_config_count PASSED")


def test_list_pipelines():
    s = PipelineDataSorter()
    s.configure_sort("p1", "k")
    s.configure_sort("p2", "k")
    s.configure_sort("p1", "k2")
    pids = s.list_pipelines()
    assert set(pids) == {"p1", "p2"}
    print("  test_list_pipelines PASSED")


def test_callbacks():
    s = PipelineDataSorter()
    events = []
    cb = lambda event, data: events.append((event, data))
    assert s.on_change("cb1", cb) is True
    assert s.on_change("cb1", cb) is False  # duplicate
    s.configure_sort("p1", "score")
    assert len(events) == 1 and events[0][0] == "sort_configured"
    s.sort_records("p1", [{"score": 1}])
    assert len(events) == 2 and events[1][0] == "records_sorted"
    assert s.remove_callback("cb1") is True
    assert s.remove_callback("cb1") is False
    print("  test_callbacks PASSED")


def test_stats():
    s = PipelineDataSorter()
    s.configure_sort("p1", "score")
    s.sort_records("p1", [{"score": 1}, {"score": 2}])
    stats = s.get_stats()
    assert stats["total_configs"] == 1
    assert stats["total_configs_created"] == 1
    assert stats["total_sorts_executed"] == 1
    assert stats["total_records_sorted"] == 2
    assert stats["max_entries"] == 10000
    assert stats["pipelines"] == 1
    print("  test_stats PASSED")


def test_reset():
    s = PipelineDataSorter()
    s.configure_sort("p1", "k")
    s.on_change("cb", lambda e, d: None)
    s.reset()
    assert s.get_config_count() == 0
    assert s.get_stats()["total_configs_created"] == 0
    assert s.get_stats()["callbacks"] == 0
    print("  test_reset PASSED")


if __name__ == "__main__":
    test_configure_sort()
    test_sort_ascending()
    test_sort_descending()
    test_sort_missing_field()
    test_get_config()
    test_remove_config()
    test_get_config_count()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")
