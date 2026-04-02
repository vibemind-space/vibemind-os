"""Tests for PipelineDataChecksummer service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_data_checksummer import PipelineDataChecksummer


def test_checksum_returns_id():
    c = PipelineDataChecksummer()
    rid = c.checksum("pipe1", "key1", "abc123")
    assert rid.startswith("pdcs-")


def test_checksum_default_algorithm():
    c = PipelineDataChecksummer()
    rid = c.checksum("pipe1", "key1", "abc123")
    entry = c.get_checksum(rid)
    assert entry["algorithm"] == "sha256"


def test_checksum_custom_algorithm():
    c = PipelineDataChecksummer()
    rid = c.checksum("pipe1", "key1", "abc123", algorithm="md5")
    entry = c.get_checksum(rid)
    assert entry["algorithm"] == "md5"


def test_checksum_with_metadata():
    c = PipelineDataChecksummer()
    rid = c.checksum("pipe1", "key1", "abc123", metadata={"source": "test"})
    entry = c.get_checksum(rid)
    assert entry["metadata"] == {"source": "test"}


def test_checksum_default_metadata():
    c = PipelineDataChecksummer()
    rid = c.checksum("pipe1", "key1", "abc123")
    entry = c.get_checksum(rid)
    assert entry["metadata"] == {}


def test_get_checksum_found():
    c = PipelineDataChecksummer()
    rid = c.checksum("pipe1", "key1", "abc123")
    entry = c.get_checksum(rid)
    assert entry is not None
    assert entry["record_id"] == rid
    assert entry["pipeline_id"] == "pipe1"
    assert entry["data_key"] == "key1"
    assert entry["checksum_value"] == "abc123"
    assert "created_at" in entry


def test_get_checksum_not_found():
    c = PipelineDataChecksummer()
    assert c.get_checksum("pdcs-nonexistent") is None


def test_get_checksums_all():
    c = PipelineDataChecksummer()
    c.checksum("pipe1", "k1", "v1")
    c.checksum("pipe2", "k2", "v2")
    results = c.get_checksums()
    assert len(results) == 2


def test_get_checksums_filter_by_pipeline():
    c = PipelineDataChecksummer()
    c.checksum("pipe1", "k1", "v1")
    c.checksum("pipe2", "k2", "v2")
    c.checksum("pipe1", "k3", "v3")
    results = c.get_checksums(pipeline_id="pipe1")
    assert len(results) == 2
    for r in results:
        assert r["pipeline_id"] == "pipe1"


def test_get_checksums_newest_first():
    c = PipelineDataChecksummer()
    r1 = c.checksum("pipe1", "k1", "v1")
    r2 = c.checksum("pipe1", "k2", "v2")
    results = c.get_checksums()
    assert results[0]["record_id"] == r2
    assert results[1]["record_id"] == r1


def test_get_checksums_limit():
    c = PipelineDataChecksummer()
    for i in range(10):
        c.checksum("pipe1", f"k{i}", f"v{i}")
    results = c.get_checksums(limit=3)
    assert len(results) == 3


def test_get_checksum_count_all():
    c = PipelineDataChecksummer()
    c.checksum("pipe1", "k1", "v1")
    c.checksum("pipe2", "k2", "v2")
    assert c.get_checksum_count() == 2


def test_get_checksum_count_filtered():
    c = PipelineDataChecksummer()
    c.checksum("pipe1", "k1", "v1")
    c.checksum("pipe2", "k2", "v2")
    c.checksum("pipe1", "k3", "v3")
    assert c.get_checksum_count(pipeline_id="pipe1") == 2
    assert c.get_checksum_count(pipeline_id="pipe2") == 1


def test_get_checksum_count_empty():
    c = PipelineDataChecksummer()
    assert c.get_checksum_count() == 0


def test_get_stats():
    c = PipelineDataChecksummer()
    c.checksum("pipe1", "k1", "v1")
    c.checksum("pipe2", "k2", "v2")
    c.checksum("pipe1", "k3", "v3")
    stats = c.get_stats()
    assert stats["total_checksums"] == 3
    assert stats["unique_pipelines"] == 2


def test_get_stats_empty():
    c = PipelineDataChecksummer()
    stats = c.get_stats()
    assert stats["total_checksums"] == 0
    assert stats["unique_pipelines"] == 0


def test_reset():
    c = PipelineDataChecksummer()
    c.checksum("pipe1", "k1", "v1")
    c.reset()
    assert c.get_checksum_count() == 0
    assert c.get_checksums() == []


def test_reset_clears_callbacks():
    c = PipelineDataChecksummer()
    c._state.callbacks["my_cb"] = lambda e, d: None
    c.on_change = lambda e, d: None
    c.reset()
    assert len(c._state.callbacks) == 0
    assert c.on_change is None


def test_on_change_property():
    c = PipelineDataChecksummer()
    assert c.on_change is None
    cb = lambda e, d: None
    c.on_change = cb
    assert c.on_change is cb


def test_on_change_fires():
    events = []
    c = PipelineDataChecksummer()
    c.on_change = lambda e, d: events.append(e)
    c.checksum("pipe1", "k1", "v1")
    assert "checksum" in events


def test_on_change_error_handled():
    c = PipelineDataChecksummer()
    c.on_change = lambda e, d: (_ for _ in ()).throw(RuntimeError("boom"))
    # Should not raise
    c.checksum("pipe1", "k1", "v1")


def test_remove_callback():
    c = PipelineDataChecksummer()
    c._state.callbacks["my_cb"] = lambda e, d: None
    assert c.remove_callback("my_cb") is True
    assert c.remove_callback("my_cb") is False


def test_callback_fires():
    events = []
    c = PipelineDataChecksummer()
    c._state.callbacks["cb1"] = lambda e, d: events.append(e)
    c.checksum("pipe1", "k1", "v1")
    assert "checksum" in events


def test_callback_error_handled():
    c = PipelineDataChecksummer()
    c._state.callbacks["bad"] = lambda e, d: (_ for _ in ()).throw(RuntimeError("fail"))
    # Should not raise
    c.checksum("pipe1", "k1", "v1")


def test_generate_id_uniqueness():
    c = PipelineDataChecksummer()
    ids = set()
    for i in range(100):
        rid = c.checksum(f"pipe{i}", f"k{i}", f"v{i}")
        ids.add(rid)
    assert len(ids) == 100


def test_generate_id_prefix():
    c = PipelineDataChecksummer()
    rid = c.checksum("p", "k", "v")
    assert rid.startswith("pdcs-")
    assert len(rid) > len("pdcs-")


def test_prune_enforces_max():
    c = PipelineDataChecksummer()
    c.MAX_ENTRIES = 5
    for i in range(10):
        c.checksum(f"pipe{i}", f"k{i}", f"v{i}")
    assert c.get_checksum_count() <= 5


def test_get_checksums_empty():
    c = PipelineDataChecksummer()
    assert c.get_checksums() == []


def test_get_checksums_nonexistent_pipeline():
    c = PipelineDataChecksummer()
    c.checksum("pipe1", "k1", "v1")
    assert c.get_checksums(pipeline_id="nope") == []


if __name__ == "__main__":
    tests = [
        test_checksum_returns_id,
        test_checksum_default_algorithm,
        test_checksum_custom_algorithm,
        test_checksum_with_metadata,
        test_checksum_default_metadata,
        test_get_checksum_found,
        test_get_checksum_not_found,
        test_get_checksums_all,
        test_get_checksums_filter_by_pipeline,
        test_get_checksums_newest_first,
        test_get_checksums_limit,
        test_get_checksum_count_all,
        test_get_checksum_count_filtered,
        test_get_checksum_count_empty,
        test_get_stats,
        test_get_stats_empty,
        test_reset,
        test_reset_clears_callbacks,
        test_on_change_property,
        test_on_change_fires,
        test_on_change_error_handled,
        test_remove_callback,
        test_callback_fires,
        test_callback_error_handled,
        test_generate_id_uniqueness,
        test_generate_id_prefix,
        test_prune_enforces_max,
        test_get_checksums_empty,
        test_get_checksums_nonexistent_pipeline,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"FAIL: {t.__name__}: {e}")
    print(f"{passed}/{passed + failed} tests passed")
