"""Tests for PipelineDataDecompressor service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_data_decompressor import PipelineDataDecompressor


def test_decompress_returns_id():
    d = PipelineDataDecompressor()
    rid = d.decompress("pipe1", "key1")
    assert rid.startswith("pddc-")


def test_decompress_default_algorithm():
    d = PipelineDataDecompressor()
    rid = d.decompress("pipe1", "key1")
    entry = d.get_decompression(rid)
    assert entry["algorithm"] == "gzip"


def test_decompress_custom_algorithm():
    d = PipelineDataDecompressor()
    rid = d.decompress("pipe1", "key1", algorithm="zstd")
    entry = d.get_decompression(rid)
    assert entry["algorithm"] == "zstd"


def test_decompress_with_metadata():
    d = PipelineDataDecompressor()
    rid = d.decompress("pipe1", "key1", metadata={"source": "test"})
    entry = d.get_decompression(rid)
    assert entry["metadata"] == {"source": "test"}


def test_decompress_default_metadata():
    d = PipelineDataDecompressor()
    rid = d.decompress("pipe1", "key1")
    entry = d.get_decompression(rid)
    assert entry["metadata"] == {}


def test_get_decompression_found():
    d = PipelineDataDecompressor()
    rid = d.decompress("pipe1", "key1")
    entry = d.get_decompression(rid)
    assert entry is not None
    assert entry["record_id"] == rid
    assert entry["pipeline_id"] == "pipe1"
    assert entry["data_key"] == "key1"
    assert "created_at" in entry


def test_get_decompression_not_found():
    d = PipelineDataDecompressor()
    assert d.get_decompression("pddc-nonexistent") is None


def test_get_decompressions_all():
    d = PipelineDataDecompressor()
    d.decompress("pipe1", "k1")
    d.decompress("pipe2", "k2")
    results = d.get_decompressions()
    assert len(results) == 2


def test_get_decompressions_filter_by_pipeline():
    d = PipelineDataDecompressor()
    d.decompress("pipe1", "k1")
    d.decompress("pipe2", "k2")
    d.decompress("pipe1", "k3")
    results = d.get_decompressions(pipeline_id="pipe1")
    assert len(results) == 2
    for r in results:
        assert r["pipeline_id"] == "pipe1"


def test_get_decompressions_newest_first():
    d = PipelineDataDecompressor()
    r1 = d.decompress("pipe1", "k1")
    r2 = d.decompress("pipe1", "k2")
    results = d.get_decompressions()
    assert results[0]["record_id"] == r2
    assert results[1]["record_id"] == r1


def test_get_decompressions_limit():
    d = PipelineDataDecompressor()
    for i in range(10):
        d.decompress("pipe1", f"k{i}")
    results = d.get_decompressions(limit=3)
    assert len(results) == 3


def test_get_decompression_count_all():
    d = PipelineDataDecompressor()
    d.decompress("pipe1", "k1")
    d.decompress("pipe2", "k2")
    assert d.get_decompression_count() == 2


def test_get_decompression_count_filtered():
    d = PipelineDataDecompressor()
    d.decompress("pipe1", "k1")
    d.decompress("pipe2", "k2")
    d.decompress("pipe1", "k3")
    assert d.get_decompression_count(pipeline_id="pipe1") == 2
    assert d.get_decompression_count(pipeline_id="pipe2") == 1


def test_get_decompression_count_empty():
    d = PipelineDataDecompressor()
    assert d.get_decompression_count() == 0


def test_get_stats():
    d = PipelineDataDecompressor()
    d.decompress("pipe1", "k1")
    d.decompress("pipe2", "k2")
    d.decompress("pipe1", "k3")
    stats = d.get_stats()
    assert stats["total_decompressions"] == 3
    assert stats["unique_pipelines"] == 2


def test_get_stats_empty():
    d = PipelineDataDecompressor()
    stats = d.get_stats()
    assert stats["total_decompressions"] == 0
    assert stats["unique_pipelines"] == 0


def test_reset():
    d = PipelineDataDecompressor()
    d.decompress("pipe1", "k1")
    d.reset()
    assert d.get_decompression_count() == 0
    assert d.get_decompressions() == []


def test_reset_clears_callbacks():
    d = PipelineDataDecompressor()
    d._state.callbacks["my_cb"] = lambda e, data: None
    d.on_change = lambda e, data: None
    d.reset()
    assert len(d._state.callbacks) == 0
    assert d.on_change is None


def test_on_change_property():
    d = PipelineDataDecompressor()
    assert d.on_change is None
    cb = lambda e, data: None
    d.on_change = cb
    assert d.on_change is cb


def test_on_change_fires():
    events = []
    d = PipelineDataDecompressor()
    d.on_change = lambda e, data: events.append(e)
    d.decompress("pipe1", "k1")
    assert "decompress" in events


def test_on_change_error_handled():
    d = PipelineDataDecompressor()
    d.on_change = lambda e, data: (_ for _ in ()).throw(RuntimeError("boom"))
    # Should not raise
    d.decompress("pipe1", "k1")


def test_remove_callback():
    d = PipelineDataDecompressor()
    d._state.callbacks["my_cb"] = lambda e, data: None
    assert d.remove_callback("my_cb") is True
    assert d.remove_callback("my_cb") is False


def test_callback_fires():
    events = []
    d = PipelineDataDecompressor()
    d._state.callbacks["cb1"] = lambda e, data: events.append(e)
    d.decompress("pipe1", "k1")
    assert "decompress" in events


def test_callback_error_handled():
    d = PipelineDataDecompressor()
    d._state.callbacks["bad"] = lambda e, data: (_ for _ in ()).throw(RuntimeError("fail"))
    # Should not raise
    d.decompress("pipe1", "k1")


def test_generate_id_uniqueness():
    d = PipelineDataDecompressor()
    ids = set()
    for i in range(100):
        rid = d.decompress(f"pipe{i}", f"k{i}")
        ids.add(rid)
    assert len(ids) == 100


def test_generate_id_prefix():
    d = PipelineDataDecompressor()
    rid = d.decompress("p", "k")
    assert rid.startswith("pddc-")
    assert len(rid) > len("pddc-")


def test_prune_enforces_max():
    d = PipelineDataDecompressor()
    d.MAX_ENTRIES = 5
    for i in range(10):
        d.decompress(f"pipe{i}", f"k{i}")
    assert d.get_decompression_count() <= 5


def test_get_decompressions_empty():
    d = PipelineDataDecompressor()
    assert d.get_decompressions() == []


def test_get_decompressions_nonexistent_pipeline():
    d = PipelineDataDecompressor()
    d.decompress("pipe1", "k1")
    assert d.get_decompressions(pipeline_id="nope") == []


def test_on_change_set_to_none():
    d = PipelineDataDecompressor()
    d.on_change = lambda e, data: None
    assert d.on_change is not None
    d.on_change = None
    assert d.on_change is None


def test_decompress_multiple_pipelines_stats():
    d = PipelineDataDecompressor()
    d.decompress("pipe1", "k1")
    d.decompress("pipe2", "k2")
    d.decompress("pipe3", "k3")
    stats = d.get_stats()
    assert stats["unique_pipelines"] == 3
    assert stats["total_decompressions"] == 3


if __name__ == "__main__":
    tests = [
        test_decompress_returns_id,
        test_decompress_default_algorithm,
        test_decompress_custom_algorithm,
        test_decompress_with_metadata,
        test_decompress_default_metadata,
        test_get_decompression_found,
        test_get_decompression_not_found,
        test_get_decompressions_all,
        test_get_decompressions_filter_by_pipeline,
        test_get_decompressions_newest_first,
        test_get_decompressions_limit,
        test_get_decompression_count_all,
        test_get_decompression_count_filtered,
        test_get_decompression_count_empty,
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
        test_get_decompressions_empty,
        test_get_decompressions_nonexistent_pipeline,
        test_on_change_set_to_none,
        test_decompress_multiple_pipelines_stats,
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
