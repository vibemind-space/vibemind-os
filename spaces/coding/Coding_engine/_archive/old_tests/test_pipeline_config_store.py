"""Test pipeline config store -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_config_store import PipelineConfigStore


def test_set_config():
    cs = PipelineConfigStore()
    cid = cs.set_config("pipeline-1", "timeout", 30)
    assert len(cid) > 0
    assert cid.startswith("pcs-")
    print("OK: set config")


def test_get_config():
    cs = PipelineConfigStore()
    cs.set_config("pipeline-1", "timeout", 30)
    val = cs.get_config("pipeline-1", "timeout")
    assert val == 30
    assert cs.get_config("pipeline-1", "nonexistent") is None
    print("OK: get config")


def test_get_all_config():
    cs = PipelineConfigStore()
    cs.set_config("pipeline-1", "timeout", 30)
    cs.set_config("pipeline-1", "retries", 3)
    all_conf = cs.get_all_config("pipeline-1")
    assert all_conf["timeout"] == 30
    assert all_conf["retries"] == 3
    print("OK: get all config")


def test_update_config():
    cs = PipelineConfigStore()
    cs.set_config("pipeline-1", "timeout", 30)
    cs.set_config("pipeline-1", "timeout", 60)
    val = cs.get_config("pipeline-1", "timeout")
    assert val == 60
    print("OK: update config")


def test_delete_config():
    cs = PipelineConfigStore()
    cs.set_config("pipeline-1", "timeout", 30)
    assert cs.delete_config("pipeline-1", "timeout") is True
    assert cs.delete_config("pipeline-1", "timeout") is False
    print("OK: delete config")


def test_has_config():
    cs = PipelineConfigStore()
    cs.set_config("pipeline-1", "timeout", 30)
    assert cs.has_config("pipeline-1", "timeout") is True
    assert cs.has_config("pipeline-1", "nonexistent") is False
    print("OK: has config")


def test_list_pipelines():
    cs = PipelineConfigStore()
    cs.set_config("pipeline-1", "timeout", 30)
    cs.set_config("pipeline-2", "retries", 3)
    pipelines = cs.list_pipelines()
    assert "pipeline-1" in pipelines
    assert "pipeline-2" in pipelines
    print("OK: list pipelines")


def test_clear_pipeline():
    cs = PipelineConfigStore()
    cs.set_config("pipeline-1", "timeout", 30)
    cs.set_config("pipeline-1", "retries", 3)
    cs.set_config("pipeline-2", "timeout", 60)
    count = cs.clear_pipeline("pipeline-1")
    assert count == 2
    assert cs.get_config_count() == 1
    print("OK: clear pipeline")


def test_callbacks():
    cs = PipelineConfigStore()
    fired = []
    cs.on_change("mon", lambda a, d: fired.append(a))
    cs.set_config("pipeline-1", "timeout", 30)
    assert len(fired) >= 1
    assert cs.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    cs = PipelineConfigStore()
    cs.set_config("pipeline-1", "timeout", 30)
    stats = cs.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    cs = PipelineConfigStore()
    cs.set_config("pipeline-1", "timeout", 30)
    cs.reset()
    assert cs.get_config_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Config Store Tests ===\n")
    test_set_config()
    test_get_config()
    test_get_all_config()
    test_update_config()
    test_delete_config()
    test_has_config()
    test_list_pipelines()
    test_clear_pipeline()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
