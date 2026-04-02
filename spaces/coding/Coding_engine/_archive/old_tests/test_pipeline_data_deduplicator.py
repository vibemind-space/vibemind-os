"""Tests for PipelineDataDeduplicator service."""

import sys
sys.path.insert(0, ".")

from src.services.pipeline_data_deduplicator import PipelineDataDeduplicator


def test_configure():
    svc = PipelineDataDeduplicator()
    cid = svc.configure("p1", "email")
    assert cid.startswith("pdd-"), f"Expected pdd- prefix, got {cid}"
    assert len(cid) > 4
    # second configure for same pipeline overwrites
    cid2 = svc.configure("p1", "name")
    assert cid2.startswith("pdd-")
    assert cid != cid2
    # empty args return empty
    assert svc.configure("", "email") == ""
    assert svc.configure("p1", "") == ""
    print("  test_configure PASSED")


def test_deduplicate():
    svc = PipelineDataDeduplicator()
    svc.configure("p1", "email")
    records = [
        {"email": "a@b.com", "name": "Alice"},
        {"email": "c@d.com", "name": "Bob"},
        {"email": "a@b.com", "name": "Alice2"},
        {"email": "e@f.com", "name": "Carol"},
        {"email": "c@d.com", "name": "Bob2"},
    ]
    result = svc.deduplicate("p1", records)
    assert len(result) == 3, f"Expected 3 unique records, got {len(result)}"
    emails = [r["email"] for r in result]
    assert emails == ["a@b.com", "c@d.com", "e@f.com"]
    # first occurrence wins
    assert result[0]["name"] == "Alice"
    assert result[1]["name"] == "Bob"
    print("  test_deduplicate PASSED")


def test_deduplicate_no_config():
    svc = PipelineDataDeduplicator()
    records = [{"a": 1}, {"a": 2}]
    result = svc.deduplicate("no_config", records)
    assert len(result) == 2, "Without config, all records should be returned"
    assert result == records
    print("  test_deduplicate_no_config PASSED")


def test_get_config():
    svc = PipelineDataDeduplicator()
    assert svc.get_config("p1") is None
    cid = svc.configure("p1", "email")
    config = svc.get_config("p1")
    assert config is not None
    assert config["config_id"] == cid
    assert config["pipeline_id"] == "p1"
    assert config["dedup_key"] == "email"
    assert "created_at" in config
    print("  test_get_config PASSED")


def test_get_seen_count():
    svc = PipelineDataDeduplicator()
    assert svc.get_seen_count("p1") == 0
    svc.configure("p1", "email")
    svc.deduplicate("p1", [
        {"email": "a@b.com"},
        {"email": "c@d.com"},
        {"email": "a@b.com"},
    ])
    assert svc.get_seen_count("p1") == 2, f"Expected 2, got {svc.get_seen_count('p1')}"
    print("  test_get_seen_count PASSED")


def test_clear_seen():
    svc = PipelineDataDeduplicator()
    svc.configure("p1", "email")
    svc.deduplicate("p1", [
        {"email": "a@b.com"},
        {"email": "c@d.com"},
    ])
    cleared = svc.clear_seen("p1")
    assert cleared == 2, f"Expected 2 cleared, got {cleared}"
    assert svc.get_seen_count("p1") == 0
    # clearing empty returns 0
    assert svc.clear_seen("p1") == 0
    assert svc.clear_seen("nonexistent") == 0
    print("  test_clear_seen PASSED")


def test_get_config_count():
    svc = PipelineDataDeduplicator()
    assert svc.get_config_count() == 0
    svc.configure("p1", "email")
    svc.configure("p2", "name")
    assert svc.get_config_count() == 2
    assert svc.get_config_count("p1") == 1
    assert svc.get_config_count("p2") == 1
    assert svc.get_config_count("p_none") == 0
    print("  test_get_config_count PASSED")


def test_list_pipelines():
    svc = PipelineDataDeduplicator()
    assert svc.list_pipelines() == []
    svc.configure("beta", "email")
    svc.configure("alpha", "name")
    result = svc.list_pipelines()
    assert result == ["alpha", "beta"], f"Expected sorted list, got {result}"
    print("  test_list_pipelines PASSED")


def test_callbacks():
    svc = PipelineDataDeduplicator()
    events = []
    svc.on_change("my_cb", lambda action, detail: events.append((action, detail)))
    svc.configure("p1", "email")
    assert len(events) == 1
    assert events[0][0] == "configure"
    svc.deduplicate("p1", [
        {"email": "a@b.com"},
        {"email": "a@b.com"},
    ])
    assert len(events) == 2
    assert events[1][0] == "deduplicate"
    # remove_callback returns True/False
    assert svc.remove_callback("my_cb") is True
    assert svc.remove_callback("my_cb") is False
    svc.configure("p2", "name")
    assert len(events) == 2  # no new events after callback removed
    print("  test_callbacks PASSED")


def test_stats():
    svc = PipelineDataDeduplicator()
    svc.on_change("cb1", lambda a, d: None)
    svc.configure("p1", "email")
    svc.configure("p2", "name")
    svc.deduplicate("p1", [{"email": "a@b.com"}, {"email": "c@d.com"}])
    stats = svc.get_stats()
    assert stats["total_configs"] == 2
    assert stats["total_pipelines"] == 2
    assert stats["total_seen_values"] >= 2
    assert stats["callbacks_registered"] == 1
    print("  test_stats PASSED")


def test_reset():
    svc = PipelineDataDeduplicator()
    svc.on_change("cb1", lambda a, d: None)
    svc.configure("p1", "email")
    svc.configure("p2", "name")
    svc.deduplicate("p1", [{"email": "a@b.com"}])
    svc.reset()
    assert svc.get_config_count() == 0
    assert svc.list_pipelines() == []
    assert svc.get_stats()["callbacks_registered"] == 0
    assert svc.get_seen_count("p1") == 0
    print("  test_reset PASSED")


if __name__ == "__main__":
    passed = 0
    tests = [
        test_configure,
        test_deduplicate,
        test_deduplicate_no_config,
        test_get_config,
        test_get_seen_count,
        test_clear_seen,
        test_get_config_count,
        test_list_pipelines,
        test_callbacks,
        test_stats,
        test_reset,
    ]
    for t in tests:
        t()
        passed += 1
    print(f"\n=== ALL {passed} TESTS PASSED ===")
