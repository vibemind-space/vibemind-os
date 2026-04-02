"""Tests for PipelineDataCompressor."""

import sys
import base64

sys.path.insert(0, ".")

from src.services.pipeline_data_compressor import PipelineDataCompressor


def test_configure():
    svc = PipelineDataCompressor()
    cid = svc.configure("pipe-1", "base64")
    assert cid.startswith("pdco-"), f"Expected pdco- prefix, got {cid}"
    assert len(cid) > 5
    # Invalid strategy returns empty
    bad = svc.configure("pipe-1", "gzip")
    assert bad == "", f"Expected empty for invalid strategy, got {bad}"
    # Empty pipeline_id returns empty
    bad2 = svc.configure("", "base64")
    assert bad2 == "", f"Expected empty for empty pipeline_id, got {bad2}"
    print("  PASSED test_configure")


def test_compress_base64():
    svc = PipelineDataCompressor()
    svc.configure("pipe-1", "base64")
    original = "Hello, World!"
    compressed = svc.compress("pipe-1", original)
    expected = base64.b64encode(original.encode()).decode()
    assert compressed == expected, f"Expected {expected}, got {compressed}"
    print("  PASSED test_compress_base64")


def test_decompress_base64():
    svc = PipelineDataCompressor()
    svc.configure("pipe-1", "base64")
    original = "Hello, World!"
    compressed = svc.compress("pipe-1", original)
    decompressed = svc.decompress("pipe-1", compressed)
    assert decompressed == original, f"Expected {original}, got {decompressed}"
    print("  PASSED test_decompress_base64")


def test_compress_json_compact():
    svc = PipelineDataCompressor()
    svc.configure("pipe-2", "json_compact")
    data = '{ "key" : "value" , "num" : 42 }'
    compressed = svc.compress("pipe-2", data)
    assert " " not in compressed, f"Expected no spaces, got {compressed}"
    assert "\n" not in compressed
    assert "\t" not in compressed
    # json_compact decompress returns as-is
    decompressed = svc.decompress("pipe-2", compressed)
    assert decompressed == compressed, f"Expected {compressed}, got {decompressed}"
    print("  PASSED test_compress_json_compact")


def test_get_config():
    svc = PipelineDataCompressor()
    assert svc.get_config("pipe-1") is None
    svc.configure("pipe-1", "base64")
    cfg = svc.get_config("pipe-1")
    assert cfg is not None
    assert cfg["pipeline_id"] == "pipe-1"
    assert cfg["strategy"] == "base64"
    assert cfg["config_id"].startswith("pdco-")
    print("  PASSED test_get_config")


def test_get_config_count():
    svc = PipelineDataCompressor()
    assert svc.get_config_count() == 0
    svc.configure("pipe-1", "base64")
    svc.configure("pipe-2", "json_compact")
    svc.configure("pipe-1", "json_compact")
    assert svc.get_config_count() == 3
    assert svc.get_config_count("pipe-1") == 2
    assert svc.get_config_count("pipe-2") == 1
    assert svc.get_config_count("pipe-99") == 0
    print("  PASSED test_get_config_count")


def test_list_pipelines():
    svc = PipelineDataCompressor()
    assert svc.list_pipelines() == []
    svc.configure("pipe-1", "base64")
    svc.configure("pipe-2", "json_compact")
    svc.configure("pipe-1", "json_compact")
    pipelines = svc.list_pipelines()
    assert "pipe-1" in pipelines
    assert "pipe-2" in pipelines
    assert len(pipelines) == 2
    print("  PASSED test_list_pipelines")


def test_callbacks():
    svc = PipelineDataCompressor()
    events = []

    def my_cb(event, data):
        events.append((event, data))

    assert svc.on_change("cb1", my_cb) is True
    # Duplicate name returns False
    assert svc.on_change("cb1", my_cb) is False
    svc.configure("pipe-1", "base64")
    assert len(events) == 1
    assert events[0][0] == "configured"
    svc.compress("pipe-1", "test")
    assert len(events) == 2
    assert events[1][0] == "compressed"
    # Remove callback
    assert svc.remove_callback("cb1") is True
    assert svc.remove_callback("cb1") is False
    svc.compress("pipe-1", "test2")
    assert len(events) == 2  # no new events after removal
    print("  PASSED test_callbacks")


def test_stats():
    svc = PipelineDataCompressor()
    stats = svc.get_stats()
    assert stats["total_configs"] == 0
    assert stats["total_configs_created"] == 0
    assert stats["total_compressions"] == 0
    assert stats["total_decompressions"] == 0
    assert stats["max_entries"] == 10000
    svc.configure("pipe-1", "base64")
    svc.compress("pipe-1", "hello")
    svc.decompress("pipe-1", base64.b64encode(b"hello").decode())
    stats = svc.get_stats()
    assert stats["total_configs"] == 1
    assert stats["total_configs_created"] == 1
    assert stats["total_compressions"] == 1
    assert stats["total_decompressions"] == 1
    assert stats["pipelines"] == 1
    print("  PASSED test_stats")


def test_reset():
    svc = PipelineDataCompressor()
    svc.configure("pipe-1", "base64")
    svc.on_change("cb1", lambda e, d: None)
    svc.compress("pipe-1", "data")
    svc.reset()
    assert svc.get_config_count() == 0
    assert svc.list_pipelines() == []
    stats = svc.get_stats()
    assert stats["total_configs_created"] == 0
    assert stats["total_compressions"] == 0
    assert stats["total_decompressions"] == 0
    assert stats["callbacks"] == 0
    print("  PASSED test_reset")


if __name__ == "__main__":
    test_configure()
    test_compress_base64()
    test_decompress_base64()
    test_compress_json_compact()
    test_get_config()
    test_get_config_count()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")
