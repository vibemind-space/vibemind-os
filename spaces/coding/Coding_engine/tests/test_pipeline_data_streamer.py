"""Tests for PipelineDataStreamer service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_data_streamer import PipelineDataStreamer


class TestCreateStream:
    """create_stream method."""

    def test_create_stream_returns_string_id(self):
        streamer = PipelineDataStreamer()
        stream_id = streamer.create_stream("pipe-1", [1, 2, 3])
        assert isinstance(stream_id, str)
        assert stream_id.startswith("pdst-")

    def test_create_stream_ids_are_unique(self):
        streamer = PipelineDataStreamer()
        ids = [streamer.create_stream("pipe-1", [i]) for i in range(10)]
        assert len(set(ids)) == 10

    def test_create_stream_with_label(self):
        streamer = PipelineDataStreamer()
        stream_id = streamer.create_stream("pipe-1", [1, 2], label="my-label")
        record = streamer.get_stream(stream_id)
        assert record["label"] == "my-label"

    def test_create_stream_deep_copies_data(self):
        streamer = PipelineDataStreamer()
        data = [{"a": 1}, {"a": 2}]
        stream_id = streamer.create_stream("pipe-1", data, chunk_size=2)
        data[0]["a"] = 999
        chunk = streamer.get_next_chunk(stream_id)
        assert chunk[0]["a"] == 1

    def test_create_stream_chunk_size(self):
        streamer = PipelineDataStreamer()
        data = list(range(25))
        stream_id = streamer.create_stream("pipe-1", data, chunk_size=10)
        record = streamer.get_stream(stream_id)
        assert record["total_chunks"] == 3


class TestGetNextChunk:
    """get_next_chunk method."""

    def test_get_next_chunk_returns_first_chunk(self):
        streamer = PipelineDataStreamer()
        stream_id = streamer.create_stream("pipe-1", [1, 2, 3, 4, 5], chunk_size=2)
        chunk = streamer.get_next_chunk(stream_id)
        assert chunk == [1, 2]

    def test_get_next_chunk_advances_cursor(self):
        streamer = PipelineDataStreamer()
        stream_id = streamer.create_stream("pipe-1", [1, 2, 3, 4], chunk_size=2)
        chunk1 = streamer.get_next_chunk(stream_id)
        chunk2 = streamer.get_next_chunk(stream_id)
        assert chunk1 == [1, 2]
        assert chunk2 == [3, 4]

    def test_get_next_chunk_returns_none_when_complete(self):
        streamer = PipelineDataStreamer()
        stream_id = streamer.create_stream("pipe-1", [1, 2], chunk_size=10)
        streamer.get_next_chunk(stream_id)
        assert streamer.get_next_chunk(stream_id) is None

    def test_get_next_chunk_nonexistent_stream(self):
        streamer = PipelineDataStreamer()
        assert streamer.get_next_chunk("pdst-nonexistent") is None

    def test_get_next_chunk_returns_deep_copy(self):
        streamer = PipelineDataStreamer()
        stream_id = streamer.create_stream("pipe-1", [{"v": 1}], chunk_size=10)
        chunk = streamer.get_next_chunk(stream_id)
        chunk[0]["v"] = 999
        # Re-create to verify original data unmodified
        streamer2 = PipelineDataStreamer()
        sid2 = streamer2.create_stream("pipe-1", [{"v": 1}], chunk_size=10)
        chunk2 = streamer2.get_next_chunk(sid2)
        assert chunk2[0]["v"] == 1


class TestGetStream:
    """get_stream method."""

    def test_get_stream_existing(self):
        streamer = PipelineDataStreamer()
        stream_id = streamer.create_stream("pipe-1", [1, 2, 3])
        result = streamer.get_stream(stream_id)
        assert result is not None
        assert result["stream_id"] == stream_id
        assert result["pipeline_id"] == "pipe-1"

    def test_get_stream_nonexistent(self):
        streamer = PipelineDataStreamer()
        assert streamer.get_stream("pdst-missing") is None

    def test_get_stream_returns_deep_copy(self):
        streamer = PipelineDataStreamer()
        stream_id = streamer.create_stream("pipe-1", [1, 2])
        result = streamer.get_stream(stream_id)
        result["pipeline_id"] = "modified"
        original = streamer.get_stream(stream_id)
        assert original["pipeline_id"] == "pipe-1"


class TestGetStreams:
    """get_streams listing."""

    def test_get_streams_returns_list(self):
        streamer = PipelineDataStreamer()
        streamer.create_stream("pipe-1", [1])
        result = streamer.get_streams()
        assert isinstance(result, list)
        assert len(result) == 1

    def test_get_streams_newest_first(self):
        streamer = PipelineDataStreamer()
        id1 = streamer.create_stream("pipe-1", [1])
        id2 = streamer.create_stream("pipe-1", [2])
        results = streamer.get_streams()
        assert results[0]["stream_id"] == id2
        assert results[1]["stream_id"] == id1

    def test_get_streams_filter_by_pipeline_id(self):
        streamer = PipelineDataStreamer()
        streamer.create_stream("pipe-a", [1])
        streamer.create_stream("pipe-b", [2])
        streamer.create_stream("pipe-a", [3])
        results = streamer.get_streams(pipeline_id="pipe-a")
        assert len(results) == 2
        assert all(r["pipeline_id"] == "pipe-a" for r in results)

    def test_get_streams_respects_limit(self):
        streamer = PipelineDataStreamer()
        for i in range(10):
            streamer.create_stream("pipe-1", [i])
        results = streamer.get_streams(limit=3)
        assert len(results) == 3

    def test_get_streams_empty(self):
        streamer = PipelineDataStreamer()
        assert streamer.get_streams() == []


class TestGetStreamCount:
    """get_stream_count method."""

    def test_count_all(self):
        streamer = PipelineDataStreamer()
        for i in range(5):
            streamer.create_stream("pipe-1", [i])
        assert streamer.get_stream_count() == 5

    def test_count_by_pipeline_id(self):
        streamer = PipelineDataStreamer()
        streamer.create_stream("pipe-a", [1])
        streamer.create_stream("pipe-b", [2])
        streamer.create_stream("pipe-a", [3])
        assert streamer.get_stream_count(pipeline_id="pipe-a") == 2
        assert streamer.get_stream_count(pipeline_id="pipe-b") == 1
        assert streamer.get_stream_count(pipeline_id="pipe-c") == 0


class TestIsComplete:
    """is_complete method."""

    def test_is_complete_false_initially(self):
        streamer = PipelineDataStreamer()
        stream_id = streamer.create_stream("pipe-1", [1, 2, 3], chunk_size=2)
        assert streamer.is_complete(stream_id) is False

    def test_is_complete_true_after_all_chunks(self):
        streamer = PipelineDataStreamer()
        stream_id = streamer.create_stream("pipe-1", [1, 2], chunk_size=10)
        streamer.get_next_chunk(stream_id)
        assert streamer.is_complete(stream_id) is True

    def test_is_complete_nonexistent(self):
        streamer = PipelineDataStreamer()
        assert streamer.is_complete("pdst-missing") is False


class TestStats:
    """get_stats method."""

    def test_stats_empty(self):
        streamer = PipelineDataStreamer()
        stats = streamer.get_stats()
        assert stats["total_streams"] == 0
        assert stats["completed_streams"] == 0
        assert stats["total_chunks_delivered"] == 0

    def test_stats_populated(self):
        streamer = PipelineDataStreamer()
        sid1 = streamer.create_stream("pipe-1", [1, 2, 3, 4], chunk_size=2)
        sid2 = streamer.create_stream("pipe-2", [5, 6], chunk_size=10)
        streamer.get_next_chunk(sid1)
        streamer.get_next_chunk(sid1)
        streamer.get_next_chunk(sid2)
        stats = streamer.get_stats()
        assert stats["total_streams"] == 2
        assert stats["completed_streams"] == 2
        assert stats["total_chunks_delivered"] == 3


class TestReset:
    """reset method."""

    def test_reset_clears_entries(self):
        streamer = PipelineDataStreamer()
        streamer.create_stream("pipe-1", [1])
        streamer.create_stream("pipe-2", [2])
        assert streamer.get_stream_count() == 2
        streamer.reset()
        assert streamer.get_stream_count() == 0

    def test_reset_fires_event(self):
        streamer = PipelineDataStreamer()
        events = []
        streamer.on_change = lambda action, data: events.append(action)
        streamer.reset()
        assert "reset" in events


class TestCallbacks:
    """Callback and event system."""

    def test_on_change_fires_on_create(self):
        streamer = PipelineDataStreamer()
        events = []
        streamer.on_change = lambda action, data: events.append((action, data))
        streamer.create_stream("pipe-1", [1])
        assert len(events) == 1
        assert events[0][0] == "create_stream"

    def test_on_change_property(self):
        streamer = PipelineDataStreamer()
        assert streamer.on_change is None
        cb = lambda a, d: None
        streamer.on_change = cb
        assert streamer.on_change is cb

    def test_callback_exception_is_silent(self):
        streamer = PipelineDataStreamer()
        streamer.on_change = lambda a, d: (_ for _ in ()).throw(ValueError("boom"))
        stream_id = streamer.create_stream("pipe-1", [1])
        assert stream_id.startswith("pdst-")

    def test_remove_callback(self):
        streamer = PipelineDataStreamer()
        streamer._callbacks["mycb"] = lambda a, d: None
        assert streamer.remove_callback("mycb") is True
        assert streamer.remove_callback("mycb") is False

    def test_named_callback_fires(self):
        streamer = PipelineDataStreamer()
        fired = []
        streamer._callbacks["tracker"] = lambda a, d: fired.append(a)
        streamer.create_stream("pipe-1", [1])
        assert "create_stream" in fired

    def test_named_callback_exception_silent(self):
        streamer = PipelineDataStreamer()
        streamer._callbacks["bad"] = lambda a, d: 1 / 0
        stream_id = streamer.create_stream("pipe-1", [1])
        assert stream_id.startswith("pdst-")


class TestPruning:
    """Eviction when exceeding MAX_ENTRIES."""

    def test_prune_evicts_oldest(self):
        streamer = PipelineDataStreamer()
        streamer.MAX_ENTRIES = 5
        ids = []
        for i in range(7):
            ids.append(streamer.create_stream("pipe-1", [i]))
        assert streamer.get_stream_count() == 5
        assert streamer.get_stream(ids[0]) is None
        assert streamer.get_stream(ids[1]) is None
        assert streamer.get_stream(ids[6]) is not None
