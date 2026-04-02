"""Test pipeline configuration store."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_configuration_store import PipelineConfigurationStore


def test_set_get():
    """Set and get config values."""
    store = PipelineConfigurationStore()
    assert store.set("timeout", 30, value_type="int") is True
    assert store.get("timeout") == 30
    assert store.get("nonexistent") is None
    assert store.get("nonexistent", default=42) == 42
    print("OK: set get")


def test_typed_validation():
    """Type validation on set."""
    store = PipelineConfigurationStore()
    assert store.set("name", "test", value_type="str") is True
    assert store.set("count", "not_int", value_type="int") is False
    assert store.set("rate", 1.5, value_type="float") is True
    assert store.set("flag", True, value_type="bool") is True
    assert store.set("items", [1, 2], value_type="list") is True
    assert store.set("config", {"a": 1}, value_type="dict") is True
    assert store.set("x", 1, value_type="invalid_type") is False
    print("OK: typed validation")


def test_type_enforcement():
    """Type enforced on update."""
    store = PipelineConfigurationStore()
    store.set("count", 10, value_type="int")

    # Must stay int
    assert store.set("count", 20) is True
    assert store.set("count", "hello") is False
    assert store.get("count") == 20
    print("OK: type enforcement")


def test_readonly():
    """Readonly entries can't be modified."""
    store = PipelineConfigurationStore()
    store.set("version", "1.0", readonly=True)

    assert store.set("version", "2.0") is False
    assert store.get("version") == "1.0"
    assert store.delete("version") is False
    print("OK: readonly")


def test_delete():
    """Delete entries."""
    store = PipelineConfigurationStore()
    store.set("key", "value")

    assert store.delete("key") is True
    assert store.delete("key") is False
    assert store.exists("key") is False
    print("OK: delete")


def test_exists():
    """Check existence."""
    store = PipelineConfigurationStore()
    store.set("key", "value")

    assert store.exists("key") is True
    assert store.exists("fake") is False
    print("OK: exists")


def test_namespaces():
    """Namespace separation."""
    store = PipelineConfigurationStore()
    store.set("timeout", 30, namespace="api")
    store.set("timeout", 60, namespace="worker")

    assert store.get("timeout", namespace="api") == 30
    assert store.get("timeout", namespace="worker") == 60

    ns = store.list_namespaces()
    assert ns["api"] == 1
    assert ns["worker"] == 1
    print("OK: namespaces")


def test_get_namespace():
    """Get all entries in namespace."""
    store = PipelineConfigurationStore()
    store.set("a", 1, namespace="ns1")
    store.set("b", 2, namespace="ns1")
    store.set("c", 3, namespace="ns2")

    ns1 = store.get_namespace("ns1")
    assert len(ns1) == 2
    assert ns1["a"] == 1
    print("OK: get namespace")


def test_set_many():
    """Bulk set."""
    store = PipelineConfigurationStore()
    count = store.set_many({"a": 1, "b": 2, "c": 3})
    assert count == 3
    assert store.get("b") == 2
    print("OK: set many")


def test_get_many():
    """Bulk get."""
    store = PipelineConfigurationStore()
    store.set("a", 1)
    store.set("b", 2)

    result = store.get_many(["a", "b", "c"])
    assert len(result) == 2
    assert result["a"] == 1
    print("OK: get many")


def test_get_entry():
    """Get full entry info."""
    store = PipelineConfigurationStore()
    store.set("timeout", 30, value_type="int", description="Request timeout")

    entry = store.get_entry("timeout")
    assert entry is not None
    assert entry["value"] == 30
    assert entry["value_type"] == "int"
    assert entry["description"] == "Request timeout"
    print("OK: get entry")


def test_change_history():
    """Change history is recorded."""
    store = PipelineConfigurationStore()
    store.set("count", 1)
    store.set("count", 2, changed_by="admin")
    store.set("count", 3, changed_by="admin")

    history = store.get_history(key="count")
    assert len(history) == 2  # 2 changes (initial set doesn't count)
    assert history[0]["old_value"] == 1
    assert history[0]["new_value"] == 2
    assert history[1]["old_value"] == 2
    assert history[1]["new_value"] == 3
    print("OK: change history")


def test_rollback():
    """Rollback a change."""
    store = PipelineConfigurationStore()
    store.set("count", 1)
    store.set("count", 99, changed_by="bad_actor")

    history = store.get_history(key="count")
    assert len(history) == 1
    change_id = history[0]["change_id"]

    assert store.rollback(change_id) is True
    assert store.get("count") == 1

    assert store.rollback("fake") is False
    print("OK: rollback")


def test_reset_to_defaults():
    """Reset namespace to defaults."""
    store = PipelineConfigurationStore()
    store.set("a", 10, namespace="ns1")
    store.set("b", 20, namespace="ns1")

    store.set("a", 99, namespace="ns1")
    store.set("b", 88, namespace="ns1")

    count = store.reset_to_defaults("ns1")
    assert count == 2
    assert store.get("a", namespace="ns1") == 10
    assert store.get("b", namespace="ns1") == 20
    print("OK: reset to defaults")


def test_profiles():
    """Save and load profiles."""
    store = PipelineConfigurationStore()
    store.set("timeout", 30)
    store.set("retries", 3)

    assert store.save_profile("prod") is True
    assert "prod" in store.list_profiles()

    # Change values
    store.set("timeout", 5)
    store.set("retries", 1)

    # Load prod profile
    assert store.load_profile("prod") is True
    assert store.get("timeout") == 30
    assert store.get("retries") == 3

    # Delete profile
    assert store.delete_profile("prod") is True
    assert store.delete_profile("prod") is False
    assert store.load_profile("prod") is False
    print("OK: profiles")


def test_save_empty_profile():
    """Can't save empty namespace as profile."""
    store = PipelineConfigurationStore()
    assert store.save_profile("empty", namespace="nonexistent") is False
    print("OK: save empty profile")


def test_search():
    """Search by key or description."""
    store = PipelineConfigurationStore()
    store.set("api_timeout", 30, description="API request timeout")
    store.set("db_timeout", 60, description="Database timeout")
    store.set("retries", 3)

    results = store.search("timeout")
    assert len(results) == 2

    results = store.search("api")
    assert len(results) == 1
    print("OK: search")


def test_list_keys():
    """List keys in namespace."""
    store = PipelineConfigurationStore()
    store.set("a", 1)
    store.set("b", 2)
    store.set("c", 3, namespace="other")

    keys = store.list_keys()
    assert len(keys) == 2
    assert "a" in keys
    assert "b" in keys
    print("OK: list keys")


def test_callbacks():
    """Change callbacks fire."""
    store = PipelineConfigurationStore()
    store.set("count", 1)

    fired = []
    assert store.on_change("watcher", lambda k, ns, old, new: fired.append((k, old, new))) is True
    assert store.on_change("watcher", lambda k, ns, o, n: None) is False

    store.set("count", 2)
    assert len(fired) == 1
    assert fired[0] == ("count", 1, 2)

    assert store.remove_callback("watcher") is True
    assert store.remove_callback("watcher") is False
    print("OK: callbacks")


def test_deep_copy():
    """Values are deep copied."""
    store = PipelineConfigurationStore()
    original = {"nested": [1, 2, 3]}
    store.set("data", original, value_type="dict")

    # Modify original
    original["nested"].append(4)

    # Store value should be unchanged
    assert store.get("data") == {"nested": [1, 2, 3]}
    print("OK: deep copy")


def test_stats():
    """Stats are accurate."""
    store = PipelineConfigurationStore()
    store.set("a", 1)
    store.set("b", 2)
    store.get("a")
    store.delete("b")

    stats = store.get_stats()
    assert stats["total_sets"] == 2
    assert stats["total_gets"] == 1
    assert stats["total_deletes"] == 1
    assert stats["total_entries"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    store = PipelineConfigurationStore()
    store.set("a", 1)
    store.save_profile("p")

    store.reset()
    assert store.list_keys() == []
    assert store.list_profiles() == []
    stats = store.get_stats()
    assert stats["total_entries"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Configuration Store Tests ===\n")
    test_set_get()
    test_typed_validation()
    test_type_enforcement()
    test_readonly()
    test_delete()
    test_exists()
    test_namespaces()
    test_get_namespace()
    test_set_many()
    test_get_many()
    test_get_entry()
    test_change_history()
    test_rollback()
    test_reset_to_defaults()
    test_profiles()
    test_save_empty_profile()
    test_search()
    test_list_keys()
    test_callbacks()
    test_deep_copy()
    test_stats()
    test_reset()
    print("\n=== ALL 22 TESTS PASSED ===")


if __name__ == "__main__":
    main()
