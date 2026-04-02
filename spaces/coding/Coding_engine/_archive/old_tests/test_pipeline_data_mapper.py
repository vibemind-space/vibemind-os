"""Tests for PipelineDataMapper service."""

import sys
sys.path.insert(0, ".")

from src.services.pipeline_data_mapper import PipelineDataMapper


def test_add_mapping():
    m = PipelineDataMapper()
    mid = m.add_mapping("p1", "first_name", "fname")
    assert mid.startswith("pdma-")
    assert len(mid) > 5
    assert m.get_mapping_count() == 1
    print("PASSED test_add_mapping")


def test_apply_copy():
    m = PipelineDataMapper()
    m.add_mapping("p1", "name", "full_name", transform="copy")
    result = m.apply_mappings("p1", {"name": "Alice"})
    assert result == {"full_name": "Alice"}
    print("PASSED test_apply_copy")


def test_apply_uppercase():
    m = PipelineDataMapper()
    m.add_mapping("p1", "city", "CITY", transform="uppercase")
    result = m.apply_mappings("p1", {"city": "tokyo"})
    assert result == {"CITY": "TOKYO"}
    print("PASSED test_apply_uppercase")


def test_apply_lowercase():
    m = PipelineDataMapper()
    m.add_mapping("p1", "code", "code_lower", transform="lowercase")
    result = m.apply_mappings("p1", {"code": "ABC"})
    assert result == {"code_lower": "abc"}
    print("PASSED test_apply_lowercase")


def test_remove_mapping():
    m = PipelineDataMapper()
    mid = m.add_mapping("p1", "a", "b")
    assert m.remove_mapping(mid) is True
    assert m.remove_mapping(mid) is False
    assert m.get_mapping_count() == 0
    print("PASSED test_remove_mapping")


def test_get_mappings():
    m = PipelineDataMapper()
    m.add_mapping("p1", "a", "b")
    m.add_mapping("p1", "c", "d")
    m.add_mapping("p2", "e", "f")
    mappings = m.get_mappings("p1")
    assert len(mappings) == 2
    assert all(mp["pipeline_id"] == "p1" for mp in mappings)
    print("PASSED test_get_mappings")


def test_get_mapping_count():
    m = PipelineDataMapper()
    m.add_mapping("p1", "a", "b")
    m.add_mapping("p1", "c", "d")
    m.add_mapping("p2", "e", "f")
    assert m.get_mapping_count() == 3
    assert m.get_mapping_count("p1") == 2
    assert m.get_mapping_count("p2") == 1
    assert m.get_mapping_count("p3") == 0
    print("PASSED test_get_mapping_count")


def test_list_pipelines():
    m = PipelineDataMapper()
    m.add_mapping("beta", "a", "b")
    m.add_mapping("alpha", "c", "d")
    m.add_mapping("beta", "e", "f")
    assert m.list_pipelines() == ["alpha", "beta"]
    print("PASSED test_list_pipelines")


def test_callbacks():
    m = PipelineDataMapper()
    events = []
    m.on_change("cb1", lambda action, detail: events.append(action))
    m.add_mapping("p1", "a", "b")
    assert "add_mapping" in events
    assert m.remove_callback("cb1") is True
    assert m.remove_callback("cb1") is False
    print("PASSED test_callbacks")


def test_stats():
    m = PipelineDataMapper()
    m.on_change("cb1", lambda a, d: None)
    m.add_mapping("p1", "a", "b")
    m.add_mapping("p2", "c", "d")
    m.apply_mappings("p1", {"a": "val"})
    stats = m.get_stats()
    assert stats["total_mappings"] == 2
    assert stats["total_pipelines"] == 2
    assert stats["total_apply_count"] >= 1
    assert stats["callbacks_registered"] == 1
    print("PASSED test_stats")


def test_reset():
    m = PipelineDataMapper()
    m.on_change("cb1", lambda a, d: None)
    m.add_mapping("p1", "a", "b")
    m.reset()
    assert m.get_mapping_count() == 0
    assert m.list_pipelines() == []
    stats = m.get_stats()
    assert stats["total_mappings"] == 0
    assert stats["callbacks_registered"] == 0
    print("PASSED test_reset")


if __name__ == "__main__":
    test_add_mapping()
    test_apply_copy()
    test_apply_uppercase()
    test_apply_lowercase()
    test_remove_mapping()
    test_get_mappings()
    test_get_mapping_count()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")
