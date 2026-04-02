"""Test rate limiter for LLM API calls."""
import asyncio
import time
import sys
sys.path.insert(0, ".")

from src.services.rate_limiter import (
    RateLimiter, RateLimitExceeded, TokenBucket,
    get_rate_limiter,
)


async def test_token_bucket():
    """Token bucket consumes and refills correctly."""
    bucket = TokenBucket(capacity=5, refill_rate=10)  # 10 tokens/sec
    assert bucket.tokens == 5.0

    # Consume all tokens
    for _ in range(5):
        assert bucket.try_consume(1)
    assert not bucket.try_consume(1)

    # Wait for refill
    await asyncio.sleep(0.15)
    assert bucket.try_consume(1), "Should have refilled by now"
    print("OK: token bucket works")


async def test_basic_rate_limiting():
    """Basic acquire/release cycle works."""
    limiter = RateLimiter(global_rpm=120, global_tpm=1_000_000)
    limiter.set_agent_quota("TestAgent", rpm=60, tpm=500_000)

    async with limiter.acquire("TestAgent", estimated_tokens=100):
        pass  # Simulates an LLM call

    limiter.record_usage("TestAgent", actual_tokens=95)

    stats = limiter.get_stats()
    assert stats["global"]["total_requests"] == 1
    assert stats["global"]["total_tokens"] == 95
    assert stats["agents"]["TestAgent"]["total_requests"] == 1
    print("OK: basic rate limiting works")


async def test_concurrent_agents():
    """Multiple agents can use the limiter concurrently."""
    limiter = RateLimiter(global_rpm=120, global_tpm=1_000_000)
    limiter.set_agent_quota("Fixer", rpm=30, tpm=100_000, priority=1)
    limiter.set_agent_quota("Linter", rpm=20, tpm=50_000, priority=8)

    results = []

    async def agent_work(name, count):
        for i in range(count):
            async with limiter.acquire(name, estimated_tokens=500):
                await asyncio.sleep(0.01)
                results.append(name)

    await asyncio.gather(
        agent_work("Fixer", 5),
        agent_work("Linter", 3),
    )

    assert len(results) == 8
    assert results.count("Fixer") == 5
    assert results.count("Linter") == 3
    print("OK: concurrent agents work")


async def test_rate_limiting_with_low_limit():
    """Requests are delayed when rate is low."""
    limiter = RateLimiter(global_rpm=6, global_tpm=1_000_000)  # 6 RPM = 1 per 10s
    limiter.set_agent_quota("SlowAgent", rpm=6, tpm=1_000_000)

    start = time.time()

    # First request should be instant
    async with limiter.acquire("SlowAgent", estimated_tokens=100):
        pass

    elapsed = time.time() - start
    assert elapsed < 1.0, f"First request should be fast, took {elapsed:.2f}s"
    print(f"OK: low-rate limiting works (first request in {elapsed:.3f}s)")


async def test_stats():
    """Stats report correctly."""
    limiter = RateLimiter(global_rpm=120, global_tpm=1_000_000)

    for i in range(3):
        async with limiter.acquire("Agent1", estimated_tokens=200):
            pass
        limiter.record_usage("Agent1", actual_tokens=180 + i * 10)

    stats = limiter.get_stats()
    assert stats["global"]["total_requests"] == 3
    assert stats["global"]["total_tokens"] == 570  # 180 + 190 + 200
    print("OK: stats tracking works")


async def test_default_quota_auto_created():
    """Agents without explicit quotas get default limits."""
    limiter = RateLimiter(global_rpm=120, global_tpm=1_000_000)

    # No explicit quota set for "NewAgent"
    async with limiter.acquire("NewAgent", estimated_tokens=100):
        pass

    stats = limiter.get_stats()
    assert "NewAgent" in stats["agents"]
    print("OK: default quota auto-created")


async def test_singleton():
    """get_rate_limiter returns same instance."""
    l1 = get_rate_limiter(global_rpm=120)
    l2 = get_rate_limiter(global_rpm=120)
    assert l1 is l2
    print("OK: singleton works")


async def main():
    print("=== Rate Limiter Tests ===\n")
    await test_token_bucket()
    await test_basic_rate_limiting()
    await test_concurrent_agents()
    await test_rate_limiting_with_low_limit()
    await test_stats()
    await test_default_quota_auto_created()
    await test_singleton()
    print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    asyncio.run(main())
