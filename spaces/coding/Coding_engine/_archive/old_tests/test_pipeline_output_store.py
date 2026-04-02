"""Test pipeline output store -- unit tests."""
import sys
sys.path.insert(0, ".")
import time

from src.services.pipeline_output_store import PipelineOutputStore


def test_store():
    os = PipelineOutputStore()
    oid = os.store("deploy", "exec-1", {"status": "success"}, version="1.0", tags=["prod"])
    assert len(oid) > 0
    o = os.get(oid)
    assert o is not None
    assert o["pipeline_name"] == "deploy"
    print("OK: store")


def test_get_latest():
    os = PipelineOutputStore()
    os.store("deploy", "exec-1", {"v": 1})
    import time
    time.sleep(0.01)  # ensure different timestamp
    os.store("deploy", "exec-2", {"v": 2})
    latest = os.get_latest("deploy")
    assert latest is not None
    assert latest["output"]["v"] == 2
    print("OK: get latest")


def test_get_by_execution():
    os = PipelineOutputStore()
    os.store("deploy", "exec-1", {"a": 1})
    os.store("build", "exec-1", {"b": 2})
    results = os.get_by_execution("exec-1")
    assert len(results) == 2
    print("OK: get by execution")


def test_get_history():
    os = PipelineOutputStore()
    os.store("deploy", "e1", {"v": 1})
    os.store("deploy", "e2", {"v": 2})
    os.store("deploy", "e3", {"v": 3})
    history = os.get_history("deploy")
    assert len(history) == 3
    print("OK: get history")


def test_list_pipelines():
    os = PipelineOutputStore()
    os.store("deploy", "e1", {})
    os.store("build", "e2", {})
    pipelines = os.list_pipelines()
    assert "deploy" in pipelines
    assert "build" in pipelines
    print("OK: list pipelines")


def test_remove():
    os = PipelineOutputStore()
    oid = os.store("deploy", "e1", {})
    assert os.remove(oid) is True
    assert os.remove(oid) is False
    print("OK: remove")


def test_purge():
    os = PipelineOutputStore()
    os.store("deploy", "e1", {})
    time.sleep(0.01)
    count = os.purge(before_timestamp=time.time() + 1)
    assert count >= 1
    print("OK: purge")


def test_callbacks():
    os = PipelineOutputStore()
    fired = []
    os.on_change("mon", lambda a, d: fired.append(a))
    os.store("deploy", "e1", {})
    assert len(fired) >= 1
    assert os.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    os = PipelineOutputStore()
    os.store("deploy", "e1", {})
    stats = os.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    os = PipelineOutputStore()
    os.store("deploy", "e1", {})
    os.reset()
    assert os.list_pipelines() == []
    print("OK: reset")


def main():
    print("=== Pipeline Output Store Tests ===\n")
    test_store()
    test_get_latest()
    test_get_by_execution()
    test_get_history()
    test_list_pipelines()
    test_remove()
    test_purge()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")


if __name__ == "__main__":
    main()
