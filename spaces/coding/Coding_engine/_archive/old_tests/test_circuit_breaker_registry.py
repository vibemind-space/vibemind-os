"""Test circuit breaker registry."""
import sys
import time
sys.path.insert(0, ".")

from src.services.circuit_breaker_registry import CircuitBreakerRegistry


def test_create_remove():
    """Create and remove breakers."""
    r = CircuitBreakerRegistry()
    assert r.create("api") is True
    assert r.create("api") is False

    cb = r.get("api")
    assert cb is not None
    assert cb["state"] == "closed"

    assert r.remove("api") is True
    assert r.remove("api") is False
    assert r.get("api") is None
    print("OK: create remove")


def test_allow_closed():
    """Closed breaker allows calls."""
    r = CircuitBreakerRegistry()
    r.create("api")
    assert r.allow("api") is True
    assert r.allow("unknown") is True  # Unknown allows
    print("OK: allow closed")


def test_open_on_failures():
    """Opens after failure threshold."""
    r = CircuitBreakerRegistry(default_failure_threshold=3)
    r.create("api")

    r.record_failure("api")
    r.record_failure("api")
    assert r.get_state("api") == "closed"

    r.record_failure("api")  # 3rd failure
    assert r.get_state("api") == "open"
    assert r.allow("api") is False
    print("OK: open on failures")


def test_rejection_counting():
    """Rejections are counted when open."""
    r = CircuitBreakerRegistry(default_failure_threshold=1)
    r.create("api")

    r.record_failure("api")
    assert r.get_state("api") == "open"

    r.allow("api")
    r.allow("api")
    cb = r.get("api")
    assert cb["total_rejections"] == 2
    print("OK: rejection counting")


def test_success_resets_failures():
    """Success resets failure count in closed state."""
    r = CircuitBreakerRegistry(default_failure_threshold=3)
    r.create("api")

    r.record_failure("api")
    r.record_failure("api")
    r.record_success("api")  # Reset

    cb = r.get("api")
    assert cb["failure_count"] == 0
    assert cb["state"] == "closed"
    print("OK: success resets failures")


def test_timeout_to_half_open():
    """Open transitions to half_open after timeout."""
    r = CircuitBreakerRegistry(default_failure_threshold=1, default_timeout=0.02)
    r.create("api")

    r.record_failure("api")
    assert r.get_state("api") == "open"

    time.sleep(0.03)
    assert r.get_state("api") == "half_open"
    print("OK: timeout to half open")


def test_half_open_success():
    """Enough successes in half_open closes breaker."""
    r = CircuitBreakerRegistry(
        default_failure_threshold=1,
        default_success_threshold=2,
        default_timeout=0.01,
    )
    r.create("api")

    r.record_failure("api")
    time.sleep(0.02)
    r.get_state("api")  # Trigger half_open check

    assert r.get_state("api") == "half_open"
    r.record_success("api")
    assert r.get_state("api") == "half_open"  # Still half_open
    r.record_success("api")
    assert r.get_state("api") == "closed"  # Now closed
    print("OK: half open success")


def test_half_open_failure():
    """Failure in half_open re-opens breaker."""
    r = CircuitBreakerRegistry(default_failure_threshold=1, default_timeout=0.01)
    r.create("api")

    r.record_failure("api")
    time.sleep(0.02)
    r.get_state("api")  # half_open

    r.record_failure("api")
    assert r.get_state("api") == "open"
    print("OK: half open failure")


def test_force_open():
    """Force breaker open."""
    r = CircuitBreakerRegistry()
    r.create("api")

    assert r.force_open("api") is True
    assert r.get_state("api") == "open"
    assert r.force_open("fake") is False
    print("OK: force open")


def test_force_close():
    """Force breaker closed."""
    r = CircuitBreakerRegistry(default_failure_threshold=1)
    r.create("api")
    r.record_failure("api")

    assert r.force_close("api") is True
    assert r.get_state("api") == "closed"
    cb = r.get("api")
    assert cb["failure_count"] == 0
    print("OK: force close")


def test_force_half_open():
    """Force breaker to half_open."""
    r = CircuitBreakerRegistry()
    r.create("api")

    assert r.force_half_open("api") is True
    assert r.get_state("api") == "half_open"
    print("OK: force half open")


def test_configure():
    """Update breaker configuration."""
    r = CircuitBreakerRegistry()
    r.create("api")

    assert r.configure("api", failure_threshold=10, timeout_seconds=60.0) is True
    cb = r.get("api")
    assert cb["failure_threshold"] == 10
    assert cb["timeout_seconds"] == 60.0

    assert r.configure("fake") is False
    print("OK: configure")


def test_groups():
    """Grouped breakers."""
    r = CircuitBreakerRegistry()
    r.create("api_v1", group="api")
    r.create("api_v2", group="api")
    r.create("db")

    group = r.get_group("api")
    assert len(group) == 2

    groups = r.list_groups()
    assert groups["api"] == 2
    print("OK: groups")


def test_group_cleanup():
    """Removing breaker cleans group."""
    r = CircuitBreakerRegistry()
    r.create("a", group="g1")
    r.create("b", group="g1")

    r.remove("a")
    assert len(r.get_group("g1")) == 1

    r.remove("b")
    assert "g1" not in r.list_groups()
    print("OK: group cleanup")


def test_list_breakers():
    """List breakers with filters."""
    r = CircuitBreakerRegistry(default_failure_threshold=1)
    r.create("api", group="web")
    r.create("db", group="data")

    r.record_failure("api")  # Opens api

    all_cb = r.list_breakers()
    assert len(all_cb) == 2

    open_cb = r.list_breakers(state="open")
    assert len(open_cb) == 1
    assert open_cb[0]["name"] == "api"

    web = r.list_breakers(group="web")
    assert len(web) == 1
    print("OK: list breakers")


def test_get_open_breakers():
    """Get all open breakers."""
    r = CircuitBreakerRegistry(default_failure_threshold=1)
    r.create("api")
    r.create("db")

    r.record_failure("api")
    open_cbs = r.get_open_breakers()
    assert len(open_cbs) == 1
    assert open_cbs[0]["name"] == "api"
    print("OK: get open breakers")


def test_summary():
    """Summary counts by state."""
    r = CircuitBreakerRegistry(default_failure_threshold=1)
    r.create("api")
    r.create("db")
    r.create("cache")

    r.record_failure("api")

    summary = r.get_summary()
    assert summary.get("closed", 0) == 2
    assert summary.get("open", 0) == 1
    print("OK: summary")


def test_callbacks():
    """State change callbacks fire."""
    r = CircuitBreakerRegistry(default_failure_threshold=1)
    r.create("api")

    fired = []
    assert r.on_state_change("mon", lambda n, o, s: fired.append((n, o, s))) is True
    assert r.on_state_change("mon", lambda n, o, s: None) is False

    r.record_failure("api")  # closed -> open
    assert len(fired) == 1
    assert fired[0] == ("api", "closed", "open")

    assert r.remove_callback("mon") is True
    assert r.remove_callback("mon") is False
    print("OK: callbacks")


def test_record_invalid():
    """Record on nonexistent breaker."""
    r = CircuitBreakerRegistry()
    assert r.record_success("fake") is False
    assert r.record_failure("fake") is False
    print("OK: record invalid")


def test_stats():
    """Stats are accurate."""
    r = CircuitBreakerRegistry(default_failure_threshold=1)
    r.create("api")
    r.record_failure("api")

    stats = r.get_stats()
    assert stats["total_created"] == 1
    assert stats["total_breakers"] == 1
    assert stats["total_state_changes"] >= 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    r = CircuitBreakerRegistry()
    r.create("api")

    r.reset()
    assert r.list_breakers() == []
    stats = r.get_stats()
    assert stats["total_breakers"] == 0
    print("OK: reset")


def main():
    print("=== Circuit Breaker Registry Tests ===\n")
    test_create_remove()
    test_allow_closed()
    test_open_on_failures()
    test_rejection_counting()
    test_success_resets_failures()
    test_timeout_to_half_open()
    test_half_open_success()
    test_half_open_failure()
    test_force_open()
    test_force_close()
    test_force_half_open()
    test_configure()
    test_groups()
    test_group_cleanup()
    test_list_breakers()
    test_get_open_breakers()
    test_summary()
    test_callbacks()
    test_record_invalid()
    test_stats()
    test_reset()
    print("\n=== ALL 21 TESTS PASSED ===")


if __name__ == "__main__":
    main()
