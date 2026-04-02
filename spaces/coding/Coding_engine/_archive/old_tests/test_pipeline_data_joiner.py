"""Tests for PipelineDataJoiner."""

import sys
sys.path.insert(0, ".")

from src.services.pipeline_data_joiner import PipelineDataJoiner


def test_create_join():
    j = PipelineDataJoiner()
    jid = j.create_join("p1", "user_id", "inner")
    assert jid.startswith("pdj-"), f"Expected pdj- prefix, got {jid}"
    assert len(jid) > 4
    # invalid join type
    assert j.create_join("p1", "k", "full") == ""
    # empty args
    assert j.create_join("", "k") == ""
    assert j.create_join("p1", "") == ""
    print("  test_create_join PASSED")


def test_inner_join():
    j = PipelineDataJoiner()
    jid = j.create_join("p1", "id", "inner")
    left = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}, {"id": 3, "name": "Carol"}]
    right = [{"id": 1, "score": 90}, {"id": 3, "score": 70}]
    result = j.execute_join(jid, left, right)
    assert len(result) == 2, f"Expected 2 results, got {len(result)}"
    assert result[0]["name"] == "Alice" and result[0]["score"] == 90
    assert result[1]["name"] == "Carol" and result[1]["score"] == 70
    # non-existent join
    assert j.execute_join("pdj-fake", [], []) == []
    print("  test_inner_join PASSED")


def test_left_join():
    j = PipelineDataJoiner()
    jid = j.create_join("p1", "id", "left")
    left = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}, {"id": 3, "name": "Carol"}]
    right = [{"id": 1, "score": 90}]
    result = j.execute_join(jid, left, right)
    assert len(result) == 3, f"Expected 3 results, got {len(result)}"
    assert result[0]["score"] == 90
    assert "score" not in result[1]
    assert "score" not in result[2]
    print("  test_left_join PASSED")


def test_get_join():
    j = PipelineDataJoiner()
    jid = j.create_join("p1", "key", "inner")
    entry = j.get_join(jid)
    assert entry is not None
    assert entry["pipeline_id"] == "p1"
    assert entry["join_key"] == "key"
    assert entry["join_type"] == "inner"
    assert j.get_join("pdj-nonexistent") is None
    print("  test_get_join PASSED")


def test_get_joins():
    j = PipelineDataJoiner()
    j.create_join("p1", "k1", "inner")
    j.create_join("p1", "k2", "left")
    j.create_join("p2", "k3", "inner")
    joins = j.get_joins("p1")
    assert len(joins) == 2
    joins2 = j.get_joins("p2")
    assert len(joins2) == 1
    assert j.get_joins("p99") == []
    print("  test_get_joins PASSED")


def test_get_join_count():
    j = PipelineDataJoiner()
    j.create_join("p1", "k1", "inner")
    j.create_join("p1", "k2", "left")
    j.create_join("p2", "k3", "inner")
    assert j.get_join_count() == 3
    assert j.get_join_count("p1") == 2
    assert j.get_join_count("p2") == 1
    assert j.get_join_count("p99") == 0
    print("  test_get_join_count PASSED")


def test_list_pipelines():
    j = PipelineDataJoiner()
    j.create_join("p1", "k", "inner")
    j.create_join("p2", "k", "inner")
    j.create_join("p1", "k2", "left")
    pids = j.list_pipelines()
    assert set(pids) == {"p1", "p2"}
    print("  test_list_pipelines PASSED")


def test_callbacks():
    j = PipelineDataJoiner()
    events = []
    cb = lambda event, data: events.append((event, data))
    assert j.on_change("cb1", cb) is True
    assert j.on_change("cb1", cb) is False  # duplicate
    jid = j.create_join("p1", "id", "inner")
    assert len(events) == 1 and events[0][0] == "join_created"
    j.execute_join(jid, [{"id": 1}], [{"id": 1}])
    assert len(events) == 2 and events[1][0] == "join_executed"
    assert j.remove_callback("cb1") is True
    assert j.remove_callback("cb1") is False
    print("  test_callbacks PASSED")


def test_stats():
    j = PipelineDataJoiner()
    jid = j.create_join("p1", "id", "inner")
    j.execute_join(jid, [{"id": 1}], [{"id": 1}])
    stats = j.get_stats()
    assert stats["total_joins"] == 1
    assert stats["total_joins_created"] == 1
    assert stats["total_joins_executed"] == 1
    assert stats["total_records_produced"] == 1
    assert stats["max_entries"] == 10000
    assert stats["pipelines"] == 1
    print("  test_stats PASSED")


def test_reset():
    j = PipelineDataJoiner()
    j.create_join("p1", "k", "inner")
    j.on_change("cb", lambda e, d: None)
    j.reset()
    assert j.get_join_count() == 0
    assert j.get_stats()["total_joins_created"] == 0
    assert j.get_stats()["callbacks"] == 0
    print("  test_reset PASSED")


if __name__ == "__main__":
    test_create_join()
    test_inner_join()
    test_left_join()
    test_get_join()
    test_get_joins()
    test_get_join_count()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")
