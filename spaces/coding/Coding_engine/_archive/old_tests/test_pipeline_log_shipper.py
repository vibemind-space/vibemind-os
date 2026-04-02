"""Test pipeline log shipper."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_log_shipper import PipelineLogShipper


def test_add_destination():
    """Add and retrieve destination."""
    ls = PipelineLogShipper()
    did = ls.add_destination("stdout", dest_type="console", tags=["default"])
    assert did.startswith("dst-")

    d = ls.get_destination(did)
    assert d is not None
    assert d["name"] == "stdout"
    assert d["dest_type"] == "console"
    assert d["enabled"] is True

    assert ls.remove_destination(did) is True
    assert ls.remove_destination(did) is False
    print("OK: add destination")


def test_invalid_destination():
    """Invalid destination rejected."""
    ls = PipelineLogShipper()
    assert ls.add_destination("") == ""
    assert ls.add_destination("x", dest_type="invalid") == ""
    print("OK: invalid destination")


def test_duplicate_destination():
    """Duplicate destination name rejected."""
    ls = PipelineLogShipper()
    ls.add_destination("stdout")
    assert ls.add_destination("stdout") == ""
    print("OK: duplicate destination")


def test_max_destinations():
    """Max destinations enforced."""
    ls = PipelineLogShipper(max_destinations=2)
    ls.add_destination("a")
    ls.add_destination("b")
    assert ls.add_destination("c") == ""
    print("OK: max destinations")


def test_enable_disable():
    """Enable and disable destination."""
    ls = PipelineLogShipper()
    did = ls.add_destination("stdout")

    assert ls.disable_destination(did) is True
    assert ls.get_destination(did)["enabled"] is False
    assert ls.disable_destination(did) is False

    assert ls.enable_destination(did) is True
    assert ls.get_destination(did)["enabled"] is True
    assert ls.enable_destination(did) is False
    print("OK: enable disable")


def test_log():
    """Log entries to buffer."""
    ls = PipelineLogShipper()
    lid = ls.log("info", "pipeline", "started processing")
    assert lid.startswith("log-")
    assert ls.get_buffer_size() == 1

    ls.log("error", "worker", "crash detected", metadata={"code": 500})
    assert ls.get_buffer_size() == 2
    print("OK: log")


def test_invalid_log():
    """Invalid log rejected."""
    ls = PipelineLogShipper()
    assert ls.log("info", "src", "") == ""
    assert ls.log("invalid_level", "src", "msg") == ""
    print("OK: invalid log")


def test_buffer_eviction():
    """Buffer evicts oldest when full."""
    ls = PipelineLogShipper(max_buffer=5)
    for i in range(10):
        ls.log("info", "src", f"msg-{i}")
    assert ls.get_buffer_size() == 5
    assert ls.get_stats()["total_dropped"] == 5
    print("OK: buffer eviction")


def test_flush():
    """Flush ships logs to destinations."""
    received = []
    ls = PipelineLogShipper()
    ls.add_destination("collector", handler=lambda log: received.append(log))

    ls.log("info", "src", "msg1")
    ls.log("error", "src", "msg2")

    count = ls.flush()
    assert count == 2
    assert len(received) == 2
    assert received[0]["message"] == "msg1"

    # flush again - no unshipped
    assert ls.flush() == 0
    print("OK: flush")


def test_flush_no_destinations():
    """Flush with no destinations does nothing."""
    ls = PipelineLogShipper()
    ls.log("info", "src", "msg")
    assert ls.flush() == 0
    print("OK: flush no destinations")


def test_flush_disabled_destination():
    """Disabled destinations don't receive logs."""
    received = []
    ls = PipelineLogShipper()
    did = ls.add_destination("collector", handler=lambda log: received.append(log))
    ls.disable_destination(did)

    ls.log("info", "src", "msg")
    assert ls.flush() == 0
    assert len(received) == 0
    print("OK: flush disabled destination")


def test_flush_handler_error():
    """Handler errors don't crash flush."""
    def bad_handler(log):
        raise RuntimeError("fail")

    ls = PipelineLogShipper()
    ls.add_destination("bad", handler=bad_handler)
    ls.log("info", "src", "msg")

    count = ls.flush()
    assert count == 1  # still marks as shipped
    print("OK: flush handler error")


def test_clear_shipped():
    """Clear shipped entries from buffer."""
    ls = PipelineLogShipper()
    ls.add_destination("collector", handler=lambda log: None)
    ls.log("info", "src", "msg1")
    ls.log("info", "src", "msg2")
    ls.flush()

    removed = ls.clear_shipped()
    assert removed == 2
    assert ls.get_buffer_size() == 0
    print("OK: clear shipped")


def test_search_logs():
    """Search logs with filters."""
    ls = PipelineLogShipper()
    ls.log("info", "pipeline", "started")
    ls.log("error", "worker", "crashed")
    ls.log("info", "worker", "restarted")

    all_logs = ls.search_logs()
    assert len(all_logs) == 3

    by_level = ls.search_logs(level="error")
    assert len(by_level) == 1

    by_source = ls.search_logs(source="worker")
    assert len(by_source) == 2

    limited = ls.search_logs(limit=1)
    assert len(limited) == 1
    print("OK: search logs")


def test_list_destinations():
    """List all destinations."""
    ls = PipelineLogShipper()
    ls.add_destination("a")
    ls.add_destination("b")

    dests = ls.list_destinations()
    assert len(dests) == 2
    print("OK: list destinations")


def test_callback():
    """Callback fires on events."""
    ls = PipelineLogShipper()
    fired = []
    ls.on_change("mon", lambda a, d: fired.append(a))

    ls.add_destination("collector", handler=lambda log: None)
    assert "destination_added" in fired

    ls.log("info", "src", "msg")
    ls.flush()
    assert "logs_flushed" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    ls = PipelineLogShipper()
    assert ls.on_change("mon", lambda a, d: None) is True
    assert ls.on_change("mon", lambda a, d: None) is False
    assert ls.remove_callback("mon") is True
    assert ls.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    ls = PipelineLogShipper()
    ls.add_destination("collector", handler=lambda log: None)
    ls.log("info", "src", "msg1")
    ls.log("info", "src", "msg2")
    ls.flush()

    stats = ls.get_stats()
    assert stats["total_logged"] == 2
    assert stats["total_shipped"] == 2
    assert stats["destinations"] == 1
    assert stats["unshipped"] == 0
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    ls = PipelineLogShipper()
    ls.add_destination("collector")
    ls.log("info", "src", "msg")

    ls.reset()
    assert ls.get_buffer_size() == 0
    assert ls.list_destinations() == []
    stats = ls.get_stats()
    assert stats["total_logged"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Log Shipper Tests ===\n")
    test_add_destination()
    test_invalid_destination()
    test_duplicate_destination()
    test_max_destinations()
    test_enable_disable()
    test_log()
    test_invalid_log()
    test_buffer_eviction()
    test_flush()
    test_flush_no_destinations()
    test_flush_disabled_destination()
    test_flush_handler_error()
    test_clear_shipped()
    test_search_logs()
    test_list_destinations()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 19 TESTS PASSED ===")


if __name__ == "__main__":
    main()
