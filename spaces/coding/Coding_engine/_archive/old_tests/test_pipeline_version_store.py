"""Test pipeline version store -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_version_store import PipelineVersionStore


def test_create_version():
    vs = PipelineVersionStore()
    vid = vs.create_version("deploy", config={"steps": ["build", "test"]}, description="Initial", tags=["ci"])
    assert len(vid) > 0
    v = vs.get_version(vid)
    assert v is not None
    assert v["pipeline_name"] == "deploy"
    print("OK: create version")


def test_auto_increment_version():
    vs = PipelineVersionStore()
    vid1 = vs.create_version("deploy", config={"v": 1})
    vid2 = vs.create_version("deploy", config={"v": 2})
    v1 = vs.get_version(vid1)
    v2 = vs.get_version(vid2)
    assert v2["version_number"] > v1["version_number"]
    print("OK: auto increment version")


def test_get_latest_version():
    vs = PipelineVersionStore()
    vs.create_version("deploy", config={"v": 1})
    vs.create_version("deploy", config={"v": 2})
    latest = vs.get_latest_version("deploy")
    assert latest is not None
    assert latest["config"]["v"] == 2
    print("OK: get latest version")


def test_get_version_history():
    vs = PipelineVersionStore()
    vs.create_version("deploy", config={"v": 1})
    vs.create_version("deploy", config={"v": 2})
    vs.create_version("deploy", config={"v": 3})
    history = vs.get_version_history("deploy")
    assert len(history) == 3
    print("OK: get version history")


def test_activate_version():
    vs = PipelineVersionStore()
    vid1 = vs.create_version("deploy", config={"v": 1})
    vid2 = vs.create_version("deploy", config={"v": 2})
    assert vs.activate_version("deploy", vid1) is True
    active = vs.get_active_version("deploy")
    assert active is not None
    assert active["config"]["v"] == 1
    print("OK: activate version")


def test_diff_versions():
    vs = PipelineVersionStore()
    vid1 = vs.create_version("deploy", config={"a": 1, "b": 2})
    vid2 = vs.create_version("deploy", config={"b": 3, "c": 4})
    diff = vs.diff_versions(vid1, vid2)
    assert "added" in diff or "changed" in diff or "removed" in diff
    print("OK: diff versions")


def test_list_pipelines():
    vs = PipelineVersionStore()
    vs.create_version("deploy", config={"v": 1})
    vs.create_version("test", config={"v": 1})
    pipelines = vs.list_pipelines()
    assert "deploy" in pipelines
    assert "test" in pipelines
    print("OK: list pipelines")


def test_remove_version():
    vs = PipelineVersionStore()
    vid = vs.create_version("temp", config={"v": 1})
    assert vs.remove_version(vid) is True
    assert vs.remove_version(vid) is False
    print("OK: remove version")


def test_callbacks():
    vs = PipelineVersionStore()
    fired = []
    vs.on_change("mon", lambda a, d: fired.append(a))
    vs.create_version("deploy", config={"v": 1})
    assert len(fired) >= 1
    assert vs.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    vs = PipelineVersionStore()
    vs.create_version("deploy", config={"v": 1})
    stats = vs.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    vs = PipelineVersionStore()
    vs.create_version("deploy", config={"v": 1})
    vs.reset()
    assert vs.list_pipelines() == []
    print("OK: reset")


def main():
    print("=== Pipeline Version Store Tests ===\n")
    test_create_version()
    test_auto_increment_version()
    test_get_latest_version()
    test_get_version_history()
    test_activate_version()
    test_diff_versions()
    test_list_pipelines()
    test_remove_version()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
