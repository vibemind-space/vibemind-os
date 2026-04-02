"""Test pipeline output buffer -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_output_buffer import PipelineOutputBuffer


def test_create_buffer():
    buf = PipelineOutputBuffer()
    bid = buf.create_buffer("pipe-1", "step-a", max_size=50)
    assert bid.startswith("pob-")
    assert len(bid) > 0
    print("OK: create_buffer")


def test_write_and_read():
    buf = PipelineOutputBuffer()
    bid = buf.create_buffer("pipe-1", "step-a")
    assert buf.write(bid, {"key": "val1"}) is True
    assert buf.write(bid, {"key": "val2"}) is True
    items = buf.read(bid, 1)
    assert len(items) == 1
    assert items[0] == {"key": "val1"}
    items = buf.read(bid)
    assert len(items) == 1
    assert items[0] == {"key": "val2"}
    print("OK: write_and_read")


def test_write_full_buffer():
    buf = PipelineOutputBuffer()
    bid = buf.create_buffer("pipe-1", "step-a", max_size=3)
    assert buf.write(bid, 1) is True
    assert buf.write(bid, 2) is True
    assert buf.write(bid, 3) is True
    assert buf.write(bid, 4) is False
    # not found case
    assert buf.write("no-such-id", 5) is False
    print("OK: write_full_buffer")


def test_peek():
    buf = PipelineOutputBuffer()
    bid = buf.create_buffer("pipe-1", "step-a")
    buf.write(bid, "a")
    buf.write(bid, "b")
    peeked = buf.peek(bid, 2)
    assert peeked == ["a", "b"]
    # items still present
    assert buf.get_buffer_size(bid) == 2
    # not found
    assert buf.peek("nope") == []
    print("OK: peek")


def test_flush():
    buf = PipelineOutputBuffer()
    bid = buf.create_buffer("pipe-1", "step-a")
    buf.write(bid, 10)
    buf.write(bid, 20)
    flushed = buf.flush(bid)
    assert flushed == [10, 20]
    assert buf.get_buffer_size(bid) == 0
    # not found
    assert buf.flush("nope") == []
    print("OK: flush")


def test_get_buffer_size():
    buf = PipelineOutputBuffer()
    bid = buf.create_buffer("pipe-1", "step-a")
    assert buf.get_buffer_size(bid) == 0
    buf.write(bid, "x")
    assert buf.get_buffer_size(bid) == 1
    assert buf.get_buffer_size("missing") == 0
    print("OK: get_buffer_size")


def test_get_buffer():
    buf = PipelineOutputBuffer()
    bid = buf.create_buffer("pipe-1", "step-a", max_size=50)
    info = buf.get_buffer(bid)
    assert info is not None
    assert info["buffer_id"] == bid
    assert info["pipeline_id"] == "pipe-1"
    assert info["step_name"] == "step-a"
    assert info["max_size"] == 50
    assert info["current_size"] == 0
    assert buf.get_buffer("nope") is None
    print("OK: get_buffer")


def test_get_buffers():
    buf = PipelineOutputBuffer()
    buf.create_buffer("pipe-1", "step-a")
    buf.create_buffer("pipe-1", "step-b")
    buf.create_buffer("pipe-2", "step-c")
    results = buf.get_buffers("pipe-1")
    assert len(results) == 2
    assert all(r["pipeline_id"] == "pipe-1" for r in results)
    print("OK: get_buffers")


def test_get_buffer_count():
    buf = PipelineOutputBuffer()
    buf.create_buffer("pipe-1", "step-a")
    buf.create_buffer("pipe-1", "step-b")
    buf.create_buffer("pipe-2", "step-c")
    assert buf.get_buffer_count() == 3
    assert buf.get_buffer_count("pipe-1") == 2
    assert buf.get_buffer_count("pipe-2") == 1
    assert buf.get_buffer_count("pipe-3") == 0
    print("OK: get_buffer_count")


def test_list_pipelines():
    buf = PipelineOutputBuffer()
    buf.create_buffer("pipe-b", "step-1")
    buf.create_buffer("pipe-a", "step-2")
    pipelines = buf.list_pipelines()
    assert pipelines == ["pipe-a", "pipe-b"]
    print("OK: list_pipelines")


def test_callbacks():
    buf = PipelineOutputBuffer()
    fired = []
    buf.on_change("mon", lambda a, d: fired.append(a))
    buf.create_buffer("pipe-1", "step-a")
    assert "create" in fired
    bid = list(buf._buffers.keys())[0]
    buf.write(bid, "data")
    assert "write" in fired
    assert buf.remove_callback("mon") is True
    assert buf.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    buf = PipelineOutputBuffer()
    bid = buf.create_buffer("pipe-1", "step-a")
    buf.write(bid, "x")
    buf.read(bid)
    stats = buf.get_stats()
    assert stats["total_created"] == 1
    assert stats["total_writes"] == 1
    assert stats["total_reads"] == 1
    assert "current_buffers" in stats
    assert "max_entries" in stats
    print("OK: stats")


def test_reset():
    buf = PipelineOutputBuffer()
    buf.create_buffer("pipe-1", "step-a")
    buf.on_change("x", lambda a, d: None)
    buf.reset()
    assert buf.list_pipelines() == []
    assert buf.get_buffer_count() == 0
    stats = buf.get_stats()
    assert stats["total_created"] == 0
    assert stats["registered_callbacks"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Output Buffer Tests ===\n")
    test_create_buffer()
    test_write_and_read()
    test_write_full_buffer()
    test_peek()
    test_flush()
    test_get_buffer_size()
    test_get_buffer()
    test_get_buffers()
    test_get_buffer_count()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 13 TESTS PASSED ===")


if __name__ == "__main__":
    main()
