"""Test pipeline rate limiter -- unit tests."""
import sys
import time
sys.path.insert(0, ".")

from src.services.pipeline_rate_limiter import PipelineRateLimiter


def test_create_limiter():
    rl = PipelineRateLimiter()
    lid = rl.create_limiter("api_limit", strategy="token_bucket", max_rate=100.0, window_seconds=60.0)
    assert lid.startswith("prl-")
    l = rl.get_limiter("api_limit")
    assert l is not None
    assert l["name"] == "api_limit"
    print("OK: create limiter")


def test_token_bucket_acquire():
    rl = PipelineRateLimiter()
    rl.create_limiter("tb", strategy="token_bucket", max_rate=10.0, window_seconds=1.0, burst=10)
    for _ in range(10):
        result = rl.acquire("tb", tokens=1)
        assert result["allowed"] is True
    result = rl.acquire("tb", tokens=1)
    assert result["allowed"] is False
    assert result["retry_after"] >= 0
    print("OK: token bucket acquire")


def test_sliding_window():
    rl = PipelineRateLimiter()
    rl.create_limiter("sw", strategy="sliding_window", max_rate=5.0, window_seconds=0.1)
    for _ in range(5):
        result = rl.acquire("sw")
        assert result["allowed"] is True
    result = rl.acquire("sw")
    assert result["allowed"] is False
    time.sleep(0.12)
    result = rl.acquire("sw")
    assert result["allowed"] is True
    print("OK: sliding window")


def test_fixed_window():
    rl = PipelineRateLimiter()
    rl.create_limiter("fw", strategy="fixed_window", max_rate=3.0, window_seconds=0.1)
    for _ in range(3):
        result = rl.acquire("fw")
        assert result["allowed"] is True
    result = rl.acquire("fw")
    assert result["allowed"] is False
    time.sleep(0.12)
    result = rl.acquire("fw")
    assert result["allowed"] is True
    print("OK: fixed window")


def test_update_limiter():
    rl = PipelineRateLimiter()
    rl.create_limiter("rl1", max_rate=10.0)
    assert rl.update_limiter("rl1", max_rate=20.0) is True
    l = rl.get_limiter("rl1")
    assert l["max_rate"] == 20.0
    print("OK: update limiter")


def test_usage():
    rl = PipelineRateLimiter()
    rl.create_limiter("rl1", strategy="token_bucket", max_rate=5.0, burst=5)
    rl.acquire("rl1")
    rl.acquire("rl1")
    usage = rl.get_usage("rl1")
    assert usage["total_requests"] == 2
    assert usage["allowed_count"] == 2
    print("OK: usage")


def test_list_limiters():
    rl = PipelineRateLimiter()
    rl.create_limiter("rl1", tags=["api"])
    rl.create_limiter("rl2")
    assert len(rl.list_limiters()) == 2
    assert len(rl.list_limiters(tag="api")) == 1
    print("OK: list limiters")


def test_remove_limiter():
    rl = PipelineRateLimiter()
    rl.create_limiter("rl1")
    assert rl.remove_limiter("rl1") is True
    assert rl.remove_limiter("rl1") is False
    print("OK: remove limiter")


def test_reset_limiter():
    rl = PipelineRateLimiter()
    rl.create_limiter("rl1", strategy="token_bucket", max_rate=5.0, burst=5)
    for _ in range(5):
        rl.acquire("rl1")
    assert rl.reset_limiter("rl1") is True
    result = rl.acquire("rl1")
    assert result["allowed"] is True
    print("OK: reset limiter")


def test_overloaded():
    rl = PipelineRateLimiter()
    rl.create_limiter("rl1", strategy="token_bucket", max_rate=10.0, burst=10)
    rl.create_limiter("rl2", strategy="token_bucket", max_rate=10.0, burst=10)
    for _ in range(9):
        rl.acquire("rl1")
    overloaded = rl.get_overloaded(threshold=0.8)
    assert len(overloaded) >= 1
    print("OK: overloaded")


def test_history():
    rl = PipelineRateLimiter()
    rl.create_limiter("rl1")
    hist = rl.get_history()
    assert len(hist) >= 1
    print("OK: history")


def test_callbacks():
    rl = PipelineRateLimiter()
    fired = []
    rl.on_change("mon", lambda a, d: fired.append(a))
    rl.create_limiter("rl1")
    assert len(fired) >= 1
    assert rl.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    rl = PipelineRateLimiter()
    rl.create_limiter("rl1")
    stats = rl.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    rl = PipelineRateLimiter()
    rl.create_limiter("rl1")
    rl.reset()
    assert rl.list_limiters() == []
    print("OK: reset")


def main():
    print("=== Pipeline Rate Limiter Tests ===\n")
    test_create_limiter()
    test_token_bucket_acquire()
    test_sliding_window()
    test_fixed_window()
    test_update_limiter()
    test_usage()
    test_list_limiters()
    test_remove_limiter()
    test_reset_limiter()
    test_overloaded()
    test_history()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 14 TESTS PASSED ===")


if __name__ == "__main__":
    main()
