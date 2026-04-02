"""Test agent token bucket -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_token_bucket import AgentTokenBucket


def test_create_bucket():
    tb = AgentTokenBucket()
    bid = tb.create_bucket("agent-1", capacity=10, refill_rate=2)
    assert len(bid) > 0
    assert bid.startswith("atb-")
    # Duplicate returns ""
    assert tb.create_bucket("agent-1", capacity=5, refill_rate=1) == ""
    print("OK: create bucket")


def test_consume():
    tb = AgentTokenBucket()
    tb.create_bucket("agent-1", capacity=10, refill_rate=1)
    result = tb.consume("agent-1", tokens=3)
    assert result["success"] is True
    assert result["remaining"] == 7
    assert result["wait_time"] == 0
    print("OK: consume")


def test_consume_insufficient():
    tb = AgentTokenBucket()
    tb.create_bucket("agent-1", capacity=5, refill_rate=1)
    tb.consume("agent-1", tokens=5)
    result = tb.consume("agent-1", tokens=1)
    assert result["success"] is False
    assert result["wait_time"] > 0
    print("OK: consume insufficient")


def test_get_tokens():
    tb = AgentTokenBucket()
    tb.create_bucket("agent-1", capacity=10, refill_rate=2)
    info = tb.get_tokens("agent-1")
    assert info is not None
    assert info["agent_id"] == "agent-1"
    assert info["capacity"] == 10
    assert tb.get_tokens("nonexistent") is None
    print("OK: get tokens")


def test_set_capacity():
    tb = AgentTokenBucket()
    tb.create_bucket("agent-1", capacity=10, refill_rate=1)
    assert tb.set_capacity("agent-1", 20) is True
    info = tb.get_tokens("agent-1")
    assert info["capacity"] == 20
    assert tb.set_capacity("nonexistent", 5) is False
    print("OK: set capacity")


def test_reset_bucket():
    tb = AgentTokenBucket()
    tb.create_bucket("agent-1", capacity=10, refill_rate=1)
    tb.consume("agent-1", tokens=8)
    assert tb.reset_bucket("agent-1") is True
    info = tb.get_tokens("agent-1")
    assert info["tokens"] == 10
    assert tb.reset_bucket("nonexistent") is False
    print("OK: reset bucket")


def test_delete_bucket():
    tb = AgentTokenBucket()
    tb.create_bucket("agent-1", capacity=10, refill_rate=1)
    assert tb.delete_bucket("agent-1") is True
    assert tb.delete_bucket("agent-1") is False
    print("OK: delete bucket")


def test_list_buckets():
    tb = AgentTokenBucket()
    tb.create_bucket("agent-1", capacity=10, refill_rate=1)
    tb.create_bucket("agent-2", capacity=5, refill_rate=1)
    buckets = tb.list_buckets()
    assert "agent-1" in buckets
    assert "agent-2" in buckets
    print("OK: list buckets")


def test_get_bucket_count():
    tb = AgentTokenBucket()
    tb.create_bucket("agent-1", capacity=10, refill_rate=1)
    tb.create_bucket("agent-2", capacity=5, refill_rate=1)
    assert tb.get_bucket_count() == 2
    print("OK: get bucket count")


def test_callbacks():
    tb = AgentTokenBucket()
    fired = []
    tb.on_change("mon", lambda a, d: fired.append(a))
    tb.create_bucket("agent-1", capacity=10, refill_rate=1)
    assert len(fired) >= 1
    assert tb.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    tb = AgentTokenBucket()
    tb.create_bucket("agent-1", capacity=10, refill_rate=1)
    stats = tb.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    tb = AgentTokenBucket()
    tb.create_bucket("agent-1", capacity=10, refill_rate=1)
    tb.reset()
    assert tb.list_buckets() == []
    print("OK: reset")


def main():
    print("=== Agent Token Bucket Tests ===\n")
    test_create_bucket()
    test_consume()
    test_consume_insufficient()
    test_get_tokens()
    test_set_capacity()
    test_reset_bucket()
    test_delete_bucket()
    test_list_buckets()
    test_get_bucket_count()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 12 TESTS PASSED ===")


if __name__ == "__main__":
    main()
