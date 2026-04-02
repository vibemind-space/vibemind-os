"""Test pipeline version control -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_version_control import PipelineVersionControl


def test_create_version():
    vc = PipelineVersionControl()
    vid = vc.create_version("pipeline-1", {"workers": 4}, version_tag="v1.0")
    assert len(vid) > 0
    assert vid.startswith("pvc-")
    print("OK: create version")


def test_get_version():
    vc = PipelineVersionControl()
    vid = vc.create_version("pipeline-1", {"workers": 4}, version_tag="v1.0")
    ver = vc.get_version(vid)
    assert ver is not None
    assert ver["pipeline_id"] == "pipeline-1"
    assert ver["definition"]["workers"] == 4
    assert ver["version_tag"] == "v1.0"
    assert vc.get_version("nonexistent") is None
    print("OK: get version")


def test_get_latest_version():
    vc = PipelineVersionControl()
    vc.create_version("pipeline-1", {"v": 1})
    vc.create_version("pipeline-1", {"v": 2})
    latest = vc.get_latest_version("pipeline-1")
    assert latest is not None
    assert latest["definition"]["v"] == 2
    assert vc.get_latest_version("nonexistent") is None
    print("OK: get latest version")


def test_get_version_history():
    vc = PipelineVersionControl()
    vc.create_version("pipeline-1", {"v": 1})
    vc.create_version("pipeline-1", {"v": 2})
    vc.create_version("pipeline-1", {"v": 3})
    history = vc.get_version_history("pipeline-1")
    assert len(history) == 3
    print("OK: get version history")


def test_rollback():
    vc = PipelineVersionControl()
    v1 = vc.create_version("pipeline-1", {"v": 1})
    v2 = vc.create_version("pipeline-1", {"v": 2})
    assert vc.rollback("pipeline-1", v1) is True
    active = vc.get_active_version("pipeline-1")
    assert active["version_id"] == v1
    assert vc.rollback("pipeline-1", "nonexistent") is False
    print("OK: rollback")


def test_get_active_version():
    vc = PipelineVersionControl()
    v1 = vc.create_version("pipeline-1", {"v": 1})
    active = vc.get_active_version("pipeline-1")
    assert active is not None
    assert active["version_id"] == v1
    assert vc.get_active_version("nonexistent") is None
    print("OK: get active version")


def test_delete_version():
    vc = PipelineVersionControl()
    v1 = vc.create_version("pipeline-1", {"v": 1})
    assert vc.delete_version(v1) is True
    assert vc.delete_version(v1) is False
    print("OK: delete version")


def test_list_pipelines():
    vc = PipelineVersionControl()
    vc.create_version("pipeline-1", {"v": 1})
    vc.create_version("pipeline-2", {"v": 1})
    pipelines = vc.list_pipelines()
    assert "pipeline-1" in pipelines
    assert "pipeline-2" in pipelines
    print("OK: list pipelines")


def test_callbacks():
    vc = PipelineVersionControl()
    fired = []
    vc.on_change("mon", lambda a, d: fired.append(a))
    vc.create_version("pipeline-1", {"v": 1})
    assert len(fired) >= 1
    assert vc.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    vc = PipelineVersionControl()
    vc.create_version("pipeline-1", {"v": 1})
    stats = vc.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    vc = PipelineVersionControl()
    vc.create_version("pipeline-1", {"v": 1})
    vc.reset()
    assert vc.get_version_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Version Control Tests ===\n")
    test_create_version()
    test_get_version()
    test_get_latest_version()
    test_get_version_history()
    test_rollback()
    test_get_active_version()
    test_delete_version()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
