"""Test pipeline state store."""
import sys
import time
sys.path.insert(0, ".")

from src.services.pipeline_state_store import PipelineStateStore


def test_set_get():
    """Set and get value."""
    ss = PipelineStateStore()
    assert ss.set("key1", "value1") is True
    assert ss.get("key1") == "value1"
    assert ss.get("missing") is None
    assert ss.get("missing", default="default") == "default"
    print("OK: set get")


def test_invalid_key():
    """Empty key rejected."""
    ss = PipelineStateStore()
    assert ss.set("", "val") is False
    print("OK: invalid key")


def test_max_entries():
    """Max entries enforced."""
    ss = PipelineStateStore(max_entries=2)
    ss.set("a", 1)
    ss.set("b", 2)
    assert ss.set("c", 3) is False
    print("OK: max entries")


def test_update_version():
    """Update increments version."""
    ss = PipelineStateStore()
    ss.set("key", "v1")
    assert ss.get_version("key") == 1
    ss.set("key", "v2")
    assert ss.get_version("key") == 2
    assert ss.get("key") == "v2"
    print("OK: update version")


def test_delete():
    """Delete entry."""
    ss = PipelineStateStore()
    ss.set("key", "val")
    assert ss.delete("key") is True
    assert ss.delete("key") is False
    assert ss.get("key") is None
    print("OK: delete")


def test_exists():
    """Check existence."""
    ss = PipelineStateStore()
    ss.set("key", "val")
    assert ss.exists("key") is True
    assert ss.exists("missing") is False
    print("OK: exists")


def test_namespaces():
    """Namespace isolation."""
    ss = PipelineStateStore()
    ss.set("key", "v1", namespace="ns1")
    ss.set("key", "v2", namespace="ns2")

    assert ss.get("key", namespace="ns1") == "v1"
    assert ss.get("key", namespace="ns2") == "v2"
    print("OK: namespaces")


def test_ttl_expiry():
    """TTL-based expiry."""
    ss = PipelineStateStore()
    ss.set("key", "val", ttl_ms=10.0)  # 10ms TTL
    assert ss.get("key") == "val"

    time.sleep(0.02)  # wait for expiry
    assert ss.get("key") is None
    assert ss.exists("key") is False
    print("OK: ttl expiry")


def test_compare_and_set():
    """Compare-and-set atomicity."""
    ss = PipelineStateStore()
    ss.set("counter", 0)

    # Successful CAS
    assert ss.compare_and_set("counter", 0, 1) is True
    assert ss.get("counter") == 1

    # Failed CAS (wrong expected)
    assert ss.compare_and_set("counter", 0, 2) is False
    assert ss.get("counter") == 1  # unchanged

    # CAS on nonexistent
    assert ss.compare_and_set("missing", None, 1) is False
    print("OK: compare and set")


def test_namespace_keys():
    """Get namespace keys."""
    ss = PipelineStateStore()
    ss.set("a", 1, namespace="ns1")
    ss.set("b", 2, namespace="ns1")
    ss.set("c", 3, namespace="ns2")

    keys = ss.get_namespace_keys("ns1")
    assert len(keys) == 2
    assert "a" in keys and "b" in keys
    print("OK: namespace keys")


def test_clear_namespace():
    """Clear namespace."""
    ss = PipelineStateStore()
    ss.set("a", 1, namespace="ns1")
    ss.set("b", 2, namespace="ns1")
    ss.set("c", 3, namespace="ns2")

    cleared = ss.clear_namespace("ns1")
    assert cleared == 2
    assert ss.get("a", namespace="ns1") is None
    assert ss.get("c", namespace="ns2") == 3
    print("OK: clear namespace")


def test_get_namespaces():
    """List namespaces."""
    ss = PipelineStateStore()
    ss.set("a", 1, namespace="ns1")
    ss.set("b", 2, namespace="ns2")

    ns = ss.get_namespaces()
    assert len(ns) == 2
    assert "ns1" in ns and "ns2" in ns
    print("OK: get namespaces")


def test_history():
    """State change history."""
    ss = PipelineStateStore()
    ss.set("key", "v1")
    ss.set("key", "v2")
    ss.set("key", "v3")

    history = ss.get_history("key")
    assert len(history) == 3
    assert history[0]["new_value"] == "v1"
    assert history[0]["old_value"] is None
    assert history[1]["old_value"] == "v1"
    assert history[1]["new_value"] == "v2"
    print("OK: history")


def test_get_all():
    """Get all entries in namespace."""
    ss = PipelineStateStore()
    ss.set("a", 1)
    ss.set("b", 2)

    all_vals = ss.get_all()
    assert len(all_vals) == 2
    assert all_vals["a"] == 1
    print("OK: get all")


def test_set_many():
    """Set multiple entries."""
    ss = PipelineStateStore()
    count = ss.set_many({"a": 1, "b": 2, "c": 3})
    assert count == 3
    assert ss.get("b") == 2
    print("OK: set many")


def test_callback():
    """Callback fires on set."""
    ss = PipelineStateStore()
    fired = []
    ss.on_change("mon", lambda a, d: fired.append(a))

    ss.set("key", "val")
    assert "state_set" in fired

    ss.delete("key")
    assert "state_deleted" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    ss = PipelineStateStore()
    assert ss.on_change("mon", lambda a, d: None) is True
    assert ss.on_change("mon", lambda a, d: None) is False
    assert ss.remove_callback("mon") is True
    assert ss.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    ss = PipelineStateStore()
    ss.set("a", 1)
    ss.get("a")
    ss.delete("a")
    ss.set("b", 1)
    ss.compare_and_set("b", 1, 2)
    ss.compare_and_set("b", 999, 3)  # fails

    stats = ss.get_stats()
    assert stats["total_sets"] == 2
    assert stats["total_gets"] == 1
    assert stats["total_deletes"] == 1
    assert stats["total_cas_attempts"] == 2
    assert stats["total_cas_successes"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    ss = PipelineStateStore()
    ss.set("key", "val")

    ss.reset()
    assert ss.get("key") is None
    stats = ss.get_stats()
    assert stats["current_entries"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline State Store Tests ===\n")
    test_set_get()
    test_invalid_key()
    test_max_entries()
    test_update_version()
    test_delete()
    test_exists()
    test_namespaces()
    test_ttl_expiry()
    test_compare_and_set()
    test_namespace_keys()
    test_clear_namespace()
    test_get_namespaces()
    test_history()
    test_get_all()
    test_set_many()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 19 TESTS PASSED ===")


if __name__ == "__main__":
    main()
