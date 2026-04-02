"""Test pipeline rate controller."""
import sys
import time
sys.path.insert(0, ".")

from src.services.pipeline_rate_controller import PipelineRateController


def test_create_bucket():
    """Create and remove buckets."""
    rc = PipelineRateController()
    assert rc.create_bucket("api", capacity=10.0, refill_rate=2.0) is True
    assert rc.create_bucket("api") is False

    b = rc.get_bucket("api")
    assert b is not None
    assert b["capacity"] == 10.0
    assert b["refill_rate"] == 2.0

    assert rc.remove_bucket("api") is True
    assert rc.remove_bucket("api") is False
    assert rc.get_bucket("api") is None
    print("OK: create bucket")


def test_acquire_tokens():
    """Acquire tokens from bucket."""
    rc = PipelineRateController()
    rc.create_bucket("api", capacity=5.0, refill_rate=0.0)  # No refill

    r = rc.try_acquire("api", 3.0)
    assert r["allowed"] is True
    assert r["remaining"] == 2.0

    r = rc.try_acquire("api", 3.0)
    assert r["allowed"] is False
    assert r["reason"] == "rate_limited"
    assert "retry_after" in r

    r = rc.try_acquire("api", 2.0)
    assert r["allowed"] is True
    print("OK: acquire tokens")


def test_bucket_refill():
    """Tokens refill over time."""
    rc = PipelineRateController()
    rc.create_bucket("api", capacity=10.0, refill_rate=200.0)  # Fast refill

    # Use all tokens
    rc.try_acquire("api", 10.0)
    b = rc.get_bucket("api")
    assert b["tokens"] < 10.0

    time.sleep(0.05)  # Wait for refill
    b = rc.get_bucket("api")
    assert b["tokens"] > 0  # Some tokens refilled
    print("OK: bucket refill")


def test_bucket_not_found():
    """Try acquire from nonexistent bucket."""
    rc = PipelineRateController()
    r = rc.try_acquire("nonexistent")
    assert r["allowed"] is False
    assert r["reason"] == "bucket_not_found"
    print("OK: bucket not found")


def test_create_window():
    """Create and remove windows."""
    rc = PipelineRateController()
    assert rc.create_window("api", window_seconds=60.0, max_requests=100) is True
    assert rc.create_window("api") is False

    w = rc.get_window("api")
    assert w is not None
    assert w["max_requests"] == 100

    assert rc.remove_window("api") is True
    assert rc.remove_window("api") is False
    print("OK: create window")


def test_window_check():
    """Sliding window rate check."""
    rc = PipelineRateController()
    rc.create_window("api", window_seconds=60.0, max_requests=3)

    r1 = rc.window_check("api")
    assert r1["allowed"] is True
    r2 = rc.window_check("api")
    assert r2["allowed"] is True
    r3 = rc.window_check("api")
    assert r3["allowed"] is True

    r4 = rc.window_check("api")
    assert r4["allowed"] is False
    assert r4["reason"] == "rate_limited"
    print("OK: window check")


def test_window_not_found():
    """Check nonexistent window."""
    rc = PipelineRateController()
    r = rc.window_check("nonexistent")
    assert r["allowed"] is False
    assert r["reason"] == "window_not_found"
    print("OK: window not found")


def test_window_expiry():
    """Old window entries expire."""
    rc = PipelineRateController()
    rc.create_window("api", window_seconds=0.05, max_requests=2)

    rc.window_check("api")
    rc.window_check("api")
    assert rc.window_check("api")["allowed"] is False

    time.sleep(0.06)  # Window expires
    assert rc.window_check("api")["allowed"] is True
    print("OK: window expiry")


def test_adjust_rate():
    """Dynamically adjust bucket rate."""
    rc = PipelineRateController()
    rc.create_bucket("api", capacity=10.0, refill_rate=1.0)

    assert rc.adjust_rate("api", new_capacity=20.0, new_refill_rate=5.0) is True
    b = rc.get_bucket("api")
    assert b["capacity"] == 20.0
    assert b["refill_rate"] == 5.0

    assert rc.adjust_rate("fake") is False
    print("OK: adjust rate")


def test_adjust_window():
    """Dynamically adjust window."""
    rc = PipelineRateController()
    rc.create_window("api", max_requests=10)

    assert rc.adjust_window("api", max_requests=50) is True
    w = rc.get_window("api")
    assert w["max_requests"] == 50

    assert rc.adjust_window("fake") is False
    print("OK: adjust window")


def test_groups():
    """Bucket groups."""
    rc = PipelineRateController()
    rc.create_bucket("api_a", capacity=10.0, group="api")
    rc.create_bucket("api_b", capacity=5.0, group="api")
    rc.create_bucket("other", capacity=10.0)

    group_buckets = rc.get_group("api")
    assert len(group_buckets) == 2

    groups = rc.list_groups()
    assert groups["api"] == 2
    print("OK: groups")


def test_group_cleanup():
    """Removing bucket cleans up group."""
    rc = PipelineRateController()
    rc.create_bucket("a", group="g1")
    rc.create_bucket("b", group="g1")

    rc.remove_bucket("a")
    assert len(rc.get_group("g1")) == 1

    rc.remove_bucket("b")
    assert "g1" not in rc.list_groups()
    print("OK: group cleanup")


def test_list_buckets():
    """List all buckets."""
    rc = PipelineRateController()
    rc.create_bucket("a", group="api")
    rc.create_bucket("b")

    all_b = rc.list_buckets()
    assert len(all_b) == 2

    api = rc.list_buckets(group="api")
    assert len(api) == 1
    print("OK: list buckets")


def test_list_windows():
    """List all windows."""
    rc = PipelineRateController()
    rc.create_window("a")
    rc.create_window("b")

    windows = rc.list_windows()
    assert len(windows) == 2
    print("OK: list windows")


def test_stats():
    """Stats are accurate."""
    rc = PipelineRateController()
    rc.create_bucket("api", capacity=2.0, refill_rate=0.0)
    rc.create_window("w")

    rc.try_acquire("api", 1.0)
    rc.try_acquire("api", 1.0)
    rc.try_acquire("api", 1.0)  # Denied
    rc.window_check("w")

    stats = rc.get_stats()
    assert stats["total_allowed"] == 3
    assert stats["total_denied"] == 1
    assert stats["total_buckets"] == 1
    assert stats["total_windows"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    rc = PipelineRateController()
    rc.create_bucket("api")
    rc.create_window("w")

    rc.reset()
    assert rc.list_buckets() == []
    assert rc.list_windows() == []
    stats = rc.get_stats()
    assert stats["total_buckets"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Rate Controller Tests ===\n")
    test_create_bucket()
    test_acquire_tokens()
    test_bucket_refill()
    test_bucket_not_found()
    test_create_window()
    test_window_check()
    test_window_not_found()
    test_window_expiry()
    test_adjust_rate()
    test_adjust_window()
    test_groups()
    test_group_cleanup()
    test_list_buckets()
    test_list_windows()
    test_stats()
    test_reset()
    print("\n=== ALL 16 TESTS PASSED ===")


if __name__ == "__main__":
    main()
