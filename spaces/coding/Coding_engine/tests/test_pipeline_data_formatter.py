"""Tests for PipelineDataFormatter."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_data_formatter import PipelineDataFormatter


def test_register_format():
    fmt = PipelineDataFormatter()
    fid = fmt.register_format("price_fmt", "price", "${value}")
    assert fid.startswith("pdfo-")
    assert len(fid) > len("pdfo-")


def test_get_format():
    fmt = PipelineDataFormatter()
    fid = fmt.register_format("price_fmt", "price", "${value}")
    entry = fmt.get_format(fid)
    assert entry["name"] == "price_fmt"
    assert entry["field"] == "price"
    assert entry["template_str"] == "${value}"
    assert entry["usage_count"] == 0


def test_get_format_not_found():
    fmt = PipelineDataFormatter()
    assert fmt.get_format("pdfo-nonexistent") == {}


def test_format_record():
    fmt = PipelineDataFormatter()
    fid = fmt.register_format("price_fmt", "price", "${value}")
    record = {"name": "Widget", "price": "9.99"}
    result = fmt.format_record(fid, record)
    assert result["price"] == "$9.99"
    assert result["name"] == "Widget"
    # Original unchanged
    assert record["price"] == "9.99"


def test_format_record_missing_field():
    fmt = PipelineDataFormatter()
    fid = fmt.register_format("price_fmt", "price", "${value}")
    record = {"name": "Widget"}
    result = fmt.format_record(fid, record)
    assert result == {"name": "Widget"}


def test_format_record_nonexistent_format():
    fmt = PipelineDataFormatter()
    record = {"name": "Widget", "price": "9.99"}
    result = fmt.format_record("pdfo-fake", record)
    assert result == record


def test_format_record_increments_usage():
    fmt = PipelineDataFormatter()
    fid = fmt.register_format("price_fmt", "price", "${value}")
    fmt.format_record(fid, {"price": "10"})
    fmt.format_record(fid, {"price": "20"})
    assert fmt.get_format(fid)["usage_count"] == 2


def test_format_batch():
    fmt = PipelineDataFormatter()
    fid = fmt.register_format("wrap", "val", "[{value}]")
    records = [{"val": "a"}, {"val": "b"}, {"val": "c"}]
    results = fmt.format_batch(fid, records)
    assert len(results) == 3
    assert results[0]["val"] == "[a]"
    assert results[1]["val"] == "[b]"
    assert results[2]["val"] == "[c]"


def test_format_all():
    fmt = PipelineDataFormatter()
    fid1 = fmt.register_format("wrap", "val", "[{value}]")
    fid2 = fmt.register_format("prefix", "name", "Item: {value}")
    record = {"val": "x", "name": "thing"}
    result = fmt.format_all(record, [fid1, fid2])
    assert result["val"] == "[x]"
    assert result["name"] == "Item: thing"


def test_get_formats():
    fmt = PipelineDataFormatter()
    fmt.register_format("a", "f1", "{value}!")
    fmt.register_format("b", "f2", "{value}?")
    formats = fmt.get_formats()
    assert len(formats) == 2
    names = {f["name"] for f in formats}
    assert names == {"a", "b"}


def test_get_format_count():
    fmt = PipelineDataFormatter()
    assert fmt.get_format_count() == 0
    fmt.register_format("a", "f1", "{value}")
    assert fmt.get_format_count() == 1
    fmt.register_format("b", "f2", "{value}")
    assert fmt.get_format_count() == 2


def test_remove_format():
    fmt = PipelineDataFormatter()
    fid = fmt.register_format("a", "f1", "{value}")
    assert fmt.remove_format(fid) is True
    assert fmt.get_format_count() == 0
    assert fmt.get_format(fid) == {}


def test_remove_format_not_found():
    fmt = PipelineDataFormatter()
    assert fmt.remove_format("pdfo-nope") is False


def test_get_stats():
    fmt = PipelineDataFormatter()
    fid1 = fmt.register_format("a", "f1", "{value}!")
    fid2 = fmt.register_format("b", "f2", "{value}?")
    fmt.format_record(fid1, {"f1": "x"})
    fmt.format_record(fid1, {"f1": "y"})
    fmt.format_record(fid2, {"f2": "z"})
    stats = fmt.get_stats()
    assert stats["total_formats"] == 2
    assert stats["total_operations"] == 3


def test_reset():
    fmt = PipelineDataFormatter()
    fmt.register_format("a", "f1", "{value}")
    fmt.reset()
    assert fmt.get_format_count() == 0
    assert fmt.get_stats() == {"total_formats": 0, "total_operations": 0}


def test_on_change_callback():
    events = []
    fmt = PipelineDataFormatter()
    fmt.on_change = lambda evt, data: events.append((evt, data))
    fid = fmt.register_format("a", "f1", "{value}")
    fmt.remove_format(fid)
    assert len(events) == 2
    assert events[0][0] == "register"
    assert events[1][0] == "remove"


def test_remove_callback():
    fmt = PipelineDataFormatter()
    fmt._callbacks["cb1"] = lambda e, d: None
    assert fmt.remove_callback("cb1") is True
    assert fmt.remove_callback("cb1") is False


def test_unique_ids():
    fmt = PipelineDataFormatter()
    ids = set()
    for i in range(50):
        fid = fmt.register_format(f"fmt_{i}", "field", "{value}")
        ids.add(fid)
    assert len(ids) == 50


if __name__ == "__main__":
    tests = [
        test_register_format,
        test_get_format,
        test_get_format_not_found,
        test_format_record,
        test_format_record_missing_field,
        test_format_record_nonexistent_format,
        test_format_record_increments_usage,
        test_format_batch,
        test_format_all,
        test_get_formats,
        test_get_format_count,
        test_remove_format,
        test_remove_format_not_found,
        test_get_stats,
        test_reset,
        test_on_change_callback,
        test_remove_callback,
        test_unique_ids,
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
