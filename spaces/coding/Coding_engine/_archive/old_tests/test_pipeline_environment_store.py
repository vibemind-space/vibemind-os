"""Test pipeline environment store -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_environment_store import PipelineEnvironmentStore


def test_create_environment():
    es = PipelineEnvironmentStore()
    eid = es.create_environment("production", {"db_host": "prod-db", "debug": False}, description="Production env")
    assert len(eid) > 0
    assert eid.startswith("pes-")
    e = es.get_environment("production")
    assert e is not None
    assert e["name"] == "production"
    print("OK: create environment")


def test_create_duplicate():
    es = PipelineEnvironmentStore()
    es.create_environment("prod", {"k": "v"})
    dup = es.create_environment("prod", {"k": "v2"})
    assert dup == ""
    print("OK: create duplicate")


def test_update_environment():
    es = PipelineEnvironmentStore()
    es.create_environment("staging", {"debug": True})
    assert es.update_environment("staging", config={"debug": False}) is True
    e = es.get_environment("staging")
    assert e["config"]["debug"] is False
    assert es.update_environment("nonexistent", config={}) is False
    print("OK: update environment")


def test_delete_environment():
    es = PipelineEnvironmentStore()
    es.create_environment("temp", {})
    assert es.delete_environment("temp") is True
    assert es.delete_environment("temp") is False
    print("OK: delete environment")


def test_list_environments():
    es = PipelineEnvironmentStore()
    es.create_environment("prod", {})
    es.create_environment("staging", {})
    envs = es.list_environments()
    assert len(envs) == 2
    print("OK: list environments")


def test_set_get_variable():
    es = PipelineEnvironmentStore()
    es.create_environment("prod", {"existing": "val"})
    assert es.set_variable("prod", "new_key", "new_val") is True
    assert es.get_variable("prod", "new_key") == "new_val"
    assert es.get_variable("prod", "missing", default="def") == "def"
    assert es.set_variable("nonexistent", "k", "v") is False
    print("OK: set/get variable")


def test_clone_environment():
    es = PipelineEnvironmentStore()
    es.create_environment("prod", {"db": "prod-db", "debug": False})
    new_id = es.clone_environment("prod", "staging")
    assert len(new_id) > 0
    staging = es.get_environment("staging")
    assert staging is not None
    assert staging["config"]["db"] == "prod-db"
    # Clone to existing name fails
    assert es.clone_environment("prod", "staging") == ""
    print("OK: clone environment")


def test_compare_environments():
    es = PipelineEnvironmentStore()
    es.create_environment("env1", {"a": 1, "b": 2, "c": 3})
    es.create_environment("env2", {"b": 2, "c": 99, "d": 4})
    cmp = es.compare_environments("env1", "env2")
    assert "a" in cmp.get("only_in_1", cmp.get("only_in_first", []))
    print("OK: compare environments")


def test_callbacks():
    es = PipelineEnvironmentStore()
    fired = []
    es.on_change("mon", lambda a, d: fired.append(a))
    es.create_environment("prod", {})
    assert len(fired) >= 1
    assert es.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    es = PipelineEnvironmentStore()
    es.create_environment("prod", {})
    stats = es.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    es = PipelineEnvironmentStore()
    es.create_environment("prod", {})
    es.reset()
    assert es.list_environments() == []
    print("OK: reset")


def main():
    print("=== Pipeline Environment Store Tests ===\n")
    test_create_environment()
    test_create_duplicate()
    test_update_environment()
    test_delete_environment()
    test_list_environments()
    test_set_get_variable()
    test_clone_environment()
    test_compare_environments()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
