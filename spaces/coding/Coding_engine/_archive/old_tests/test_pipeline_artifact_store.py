"""Test pipeline artifact store -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_artifact_store import PipelineArtifactStore


def test_store_artifact():
    ars = PipelineArtifactStore()
    aid = ars.store_artifact("deploy", "exec-1", "build.zip", b"binary_content", artifact_type="binary", metadata={"size": 1024})
    assert len(aid) > 0
    assert aid.startswith("par-")
    a = ars.get_artifact(aid)
    assert a is not None
    assert a["pipeline_name"] == "deploy"
    assert a["artifact_name"] == "build.zip"
    print("OK: store artifact")


def test_get_artifact_content():
    ars = PipelineArtifactStore()
    aid = ars.store_artifact("deploy", "exec-1", "log.txt", "log content here")
    content = ars.get_artifact_content(aid)
    assert content == "log content here"
    assert ars.get_artifact_content("nonexistent") is None
    print("OK: get artifact content")


def test_get_artifacts_for_execution():
    ars = PipelineArtifactStore()
    ars.store_artifact("deploy", "exec-1", "build.zip", b"data")
    ars.store_artifact("deploy", "exec-1", "log.txt", "logs")
    ars.store_artifact("deploy", "exec-2", "build.zip", b"data2")
    arts = ars.get_artifacts_for_execution("deploy", "exec-1")
    assert len(arts) == 2
    print("OK: get artifacts for execution")


def test_get_artifacts_by_type():
    ars = PipelineArtifactStore()
    ars.store_artifact("deploy", "exec-1", "build.zip", b"data", artifact_type="binary")
    ars.store_artifact("deploy", "exec-1", "log.txt", "logs", artifact_type="log")
    ars.store_artifact("test", "exec-2", "report.json", "{}", artifact_type="log")
    logs = ars.get_artifacts_by_type("log")
    assert len(logs) == 2
    print("OK: get artifacts by type")


def test_delete_artifact():
    ars = PipelineArtifactStore()
    aid = ars.store_artifact("deploy", "exec-1", "file.txt", "content")
    assert ars.delete_artifact(aid) is True
    assert ars.delete_artifact(aid) is False
    print("OK: delete artifact")


def test_list_artifacts():
    ars = PipelineArtifactStore()
    ars.store_artifact("deploy", "exec-1", "a.txt", "a")
    ars.store_artifact("deploy", "exec-2", "b.txt", "b")
    ars.store_artifact("test", "exec-3", "c.txt", "c")
    all_a = ars.list_artifacts()
    assert len(all_a) == 3
    deploy_a = ars.list_artifacts(pipeline_name="deploy")
    assert len(deploy_a) == 2
    print("OK: list artifacts")


def test_search_artifacts():
    ars = PipelineArtifactStore()
    ars.store_artifact("deploy", "exec-1", "build.zip", b"data")
    ars.store_artifact("deploy", "exec-1", "build_log.txt", "logs")
    ars.store_artifact("deploy", "exec-1", "report.html", "<html>")
    results = ars.search_artifacts("build")
    assert len(results) == 2
    print("OK: search artifacts")


def test_purge():
    ars = PipelineArtifactStore()
    ars.store_artifact("deploy", "exec-1", "old.txt", "old")
    import time
    time.sleep(0.01)
    count = ars.purge(before_timestamp=time.time() + 1)
    assert count >= 1
    print("OK: purge")


def test_callbacks():
    ars = PipelineArtifactStore()
    fired = []
    ars.on_change("mon", lambda a, d: fired.append(a))
    ars.store_artifact("deploy", "exec-1", "file.txt", "content")
    assert len(fired) >= 1
    assert ars.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    ars = PipelineArtifactStore()
    ars.store_artifact("deploy", "exec-1", "file.txt", "content")
    stats = ars.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    ars = PipelineArtifactStore()
    ars.store_artifact("deploy", "exec-1", "file.txt", "content")
    ars.reset()
    assert ars.list_artifacts() == []
    print("OK: reset")


def main():
    print("=== Pipeline Artifact Store Tests ===\n")
    test_store_artifact()
    test_get_artifact_content()
    test_get_artifacts_for_execution()
    test_get_artifacts_by_type()
    test_delete_artifact()
    test_list_artifacts()
    test_search_artifacts()
    test_purge()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
