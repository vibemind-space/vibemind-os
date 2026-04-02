"""Test pipeline backpressure controller."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_backpressure_controller import PipelineBackpressureController


def test_create_channel():
    """Create and remove a channel."""
    bp = PipelineBackpressureController()
    cid = bp.create_channel("input_queue", max_pending=50, strategy="drop", tags=["io"])
    assert cid.startswith("bp-")

    ch = bp.get_channel(cid)
    assert ch is not None
    assert ch["name"] == "input_queue"
    assert ch["max_pending"] == 50
    assert ch["strategy"] == "drop"
    assert ch["status"] == "open"
    assert "io" in ch["tags"]

    assert bp.remove_channel(cid) is True
    assert bp.remove_channel(cid) is False
    print("OK: create channel")


def test_invalid_channel():
    """Invalid channel rejected."""
    bp = PipelineBackpressureController()
    assert bp.create_channel("") == ""
    assert bp.create_channel("x", strategy="invalid") == ""
    assert bp.create_channel("x", max_pending=0) == ""
    print("OK: invalid channel")


def test_max_channels():
    """Max channels enforced."""
    bp = PipelineBackpressureController(max_channels=2)
    bp.create_channel("a")
    bp.create_channel("b")
    assert bp.create_channel("c") == ""
    print("OK: max channels")


def test_accept_items():
    """Accept items into channel."""
    bp = PipelineBackpressureController()
    cid = bp.create_channel("q", max_pending=5)

    assert bp.try_accept(cid, 3) is True
    ch = bp.get_channel(cid)
    assert ch["current_pending"] == 3

    assert bp.try_accept(cid, 2) is True
    ch = bp.get_channel(cid)
    assert ch["current_pending"] == 5
    print("OK: accept items")


def test_reject_when_full():
    """Reject items when channel is full (drop strategy)."""
    bp = PipelineBackpressureController()
    cid = bp.create_channel("q", max_pending=3, strategy="drop")

    bp.try_accept(cid, 3)
    assert bp.try_accept(cid, 1) is False

    ch = bp.get_channel(cid)
    assert ch["total_rejected"] == 1
    print("OK: reject when full")


def test_sample_strategy():
    """Sample strategy accepts 1 when over capacity."""
    bp = PipelineBackpressureController()
    cid = bp.create_channel("q", max_pending=3, strategy="sample")

    bp.try_accept(cid, 3)
    assert bp.try_accept(cid, 5) is True  # Accepts 1 of 5

    ch = bp.get_channel(cid)
    assert ch["current_pending"] == 4  # 3 + 1
    assert ch["total_rejected"] == 4  # 5 - 1
    print("OK: sample strategy")


def test_drain():
    """Drain items from channel."""
    bp = PipelineBackpressureController()
    cid = bp.create_channel("q", max_pending=10)

    bp.try_accept(cid, 5)
    drained = bp.drain(cid, 3)
    assert drained == 3

    ch = bp.get_channel(cid)
    assert ch["current_pending"] == 2
    print("OK: drain")


def test_drain_more_than_available():
    """Drain more than available returns actual count."""
    bp = PipelineBackpressureController()
    cid = bp.create_channel("q", max_pending=10)

    bp.try_accept(cid, 3)
    drained = bp.drain(cid, 10)
    assert drained == 3

    ch = bp.get_channel(cid)
    assert ch["current_pending"] == 0
    print("OK: drain more than available")


def test_drain_all():
    """Drain all pending items."""
    bp = PipelineBackpressureController()
    cid = bp.create_channel("q", max_pending=10)

    bp.try_accept(cid, 7)
    drained = bp.drain_all(cid)
    assert drained == 7

    ch = bp.get_channel(cid)
    assert ch["current_pending"] == 0
    print("OK: drain all")


def test_pause_resume():
    """Pause and resume channel."""
    bp = PipelineBackpressureController()
    cid = bp.create_channel("q", max_pending=10)

    assert bp.pause_channel(cid) is True
    ch = bp.get_channel(cid)
    assert ch["status"] == "paused"

    # Paused channel rejects
    assert bp.try_accept(cid, 1) is False

    assert bp.resume_channel(cid) is True
    ch = bp.get_channel(cid)
    assert ch["status"] == "open"

    assert bp.try_accept(cid, 1) is True
    print("OK: pause resume")


def test_close_channel():
    """Close a channel."""
    bp = PipelineBackpressureController()
    cid = bp.create_channel("q", max_pending=10)

    assert bp.close_channel(cid) is True
    assert bp.try_accept(cid, 1) is False
    assert bp.close_channel(cid) is False
    print("OK: close channel")


def test_set_max_pending():
    """Update max pending."""
    bp = PipelineBackpressureController()
    cid = bp.create_channel("q", max_pending=5)

    assert bp.set_max_pending(cid, 20) is True
    ch = bp.get_channel(cid)
    assert ch["max_pending"] == 20

    assert bp.set_max_pending(cid, 0) is False
    print("OK: set max pending")


def test_pressure_ratio():
    """Pressure ratio calculated correctly."""
    bp = PipelineBackpressureController()
    cid = bp.create_channel("q", max_pending=10)

    bp.try_accept(cid, 5)
    ch = bp.get_channel(cid)
    assert ch["pressure_ratio"] == 0.5
    print("OK: pressure ratio")


def test_list_channels():
    """List channels with filters."""
    bp = PipelineBackpressureController()
    c1 = bp.create_channel("a", strategy="drop", tags=["io"])
    c2 = bp.create_channel("b", strategy="buffer")
    bp.pause_channel(c1)

    all_c = bp.list_channels()
    assert len(all_c) == 2

    by_status = bp.list_channels(status="paused")
    assert len(by_status) == 1

    by_strategy = bp.list_channels(strategy="buffer")
    assert len(by_strategy) == 1

    by_tag = bp.list_channels(tag="io")
    assert len(by_tag) == 1
    print("OK: list channels")


def test_pressure_report():
    """Get pressure report sorted by ratio."""
    bp = PipelineBackpressureController()
    c1 = bp.create_channel("low", max_pending=100)
    c2 = bp.create_channel("high", max_pending=10)

    bp.try_accept(c1, 10)  # 10%
    bp.try_accept(c2, 8)   # 80%

    report = bp.get_pressure_report()
    assert len(report) == 2
    assert report[0]["name"] == "high"
    assert report[0]["pressure_ratio"] == 0.8
    print("OK: pressure report")


def test_high_pressure_channels():
    """Get high pressure channels."""
    bp = PipelineBackpressureController()
    c1 = bp.create_channel("low", max_pending=100)
    c2 = bp.create_channel("high", max_pending=10)

    bp.try_accept(c1, 10)  # 10%
    bp.try_accept(c2, 9)   # 90%

    high = bp.get_high_pressure_channels(threshold=0.8)
    assert len(high) == 1
    assert high[0]["name"] == "high"
    print("OK: high pressure channels")


def test_channel_throughput():
    """Get channel throughput stats."""
    bp = PipelineBackpressureController()
    cid = bp.create_channel("q", max_pending=5)

    bp.try_accept(cid, 3)
    bp.try_accept(cid, 5)  # Rejected
    bp.drain(cid, 2)

    tp = bp.get_channel_throughput(cid)
    assert tp["total_accepted"] == 3
    assert tp["total_rejected"] == 5
    assert tp["total_drained"] == 2
    assert tp["reject_ratio"] > 0

    assert bp.get_channel_throughput("nonexistent") == {}
    print("OK: channel throughput")


def test_high_pressure_callback():
    """Callback fires on high pressure."""
    bp = PipelineBackpressureController()
    cid = bp.create_channel("q", max_pending=10, strategy="drop")

    fired = []
    bp.on_change("mon", lambda a, d: fired.append(a))

    bp.try_accept(cid, 9)  # 90% - should fire
    assert "high_pressure" in fired
    print("OK: high pressure callback")


def test_pause_callback():
    """Callback fires on pause."""
    bp = PipelineBackpressureController()
    cid = bp.create_channel("q")

    fired = []
    bp.on_change("mon", lambda a, d: fired.append(a))

    bp.pause_channel(cid)
    assert "channel_paused" in fired

    bp.resume_channel(cid)
    assert "channel_resumed" in fired
    print("OK: pause callback")


def test_callbacks():
    """Callback registration."""
    bp = PipelineBackpressureController()
    assert bp.on_change("mon", lambda a, d: None) is True
    assert bp.on_change("mon", lambda a, d: None) is False
    assert bp.remove_callback("mon") is True
    assert bp.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    bp = PipelineBackpressureController()
    c1 = bp.create_channel("a", max_pending=5)
    c2 = bp.create_channel("b", max_pending=5)

    bp.try_accept(c1, 3)
    bp.try_accept(c1, 5)  # Rejected
    bp.drain(c1, 2)
    bp.pause_channel(c2)

    stats = bp.get_stats()
    assert stats["total_channels"] == 2
    assert stats["total_accepted"] == 3
    assert stats["total_rejected"] == 5
    assert stats["total_drained"] == 2
    assert stats["current_channels"] == 2
    assert stats["open_channels"] == 1
    assert stats["paused_channels"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    bp = PipelineBackpressureController()
    bp.create_channel("test")

    bp.reset()
    assert bp.list_channels() == []
    stats = bp.get_stats()
    assert stats["current_channels"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Backpressure Controller Tests ===\n")
    test_create_channel()
    test_invalid_channel()
    test_max_channels()
    test_accept_items()
    test_reject_when_full()
    test_sample_strategy()
    test_drain()
    test_drain_more_than_available()
    test_drain_all()
    test_pause_resume()
    test_close_channel()
    test_set_max_pending()
    test_pressure_ratio()
    test_list_channels()
    test_pressure_report()
    test_high_pressure_channels()
    test_channel_throughput()
    test_high_pressure_callback()
    test_pause_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 22 TESTS PASSED ===")


if __name__ == "__main__":
    main()
