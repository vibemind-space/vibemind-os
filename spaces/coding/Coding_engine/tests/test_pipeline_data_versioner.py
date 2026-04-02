"""Tests for PipelineDataVersioner service."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_data_versioner import PipelineDataVersioner


def test_create_version_returns_id():
    svc = PipelineDataVersioner()
    vid = svc.create_version("pipe1", {"key": "val"})
    assert vid.startswith("pdve-")
    assert len(vid) > len("pdve-")


def test_create_version_unique_ids():
    svc = PipelineDataVersioner()
    id1 = svc.create_version("pipe1", {"a": 1})
    id2 = svc.create_version("pipe1", {"a": 2})
    assert id1 != id2


def test_get_version_by_id():
    svc = PipelineDataVersioner()
    vid = svc.create_version("pipe1", {"x": 10}, version=3, label="beta")
    entry = svc.get_version(vid)
    assert entry is not None
    assert entry["version_id"] == vid
    assert entry["pipeline_id"] == "pipe1"
    assert entry["data"] == {"x": 10}
    assert entry["version"] == 3
    assert entry["label"] == "beta"


def test_get_version_not_found():
    svc = PipelineDataVersioner()
    assert svc.get_version("pdve-nonexistent") is None


def test_get_version_returns_dict():
    svc = PipelineDataVersioner()
    vid = svc.create_version("pipe1", {"a": 1})
    result = svc.get_version(vid)
    assert isinstance(result, dict)


def test_create_version_defaults():
    svc = PipelineDataVersioner()
    vid = svc.create_version("pipe1", {"a": 1})
    entry = svc.get_version(vid)
    assert entry["version"] == 1
    assert entry["label"] == ""


def test_get_versions_for_pipeline():
    svc = PipelineDataVersioner()
    svc.create_version("pipe1", {"a": 1})
    svc.create_version("pipe1", {"a": 2})
    svc.create_version("pipe2", {"a": 3})
    results = svc.get_versions("pipe1")
    assert len(results) == 2
    assert all(r["pipeline_id"] == "pipe1" for r in results)


def test_get_versions_newest_first():
    svc = PipelineDataVersioner()
    svc.create_version("pipe1", {"order": 1})
    svc.create_version("pipe1", {"order": 2})
    svc.create_version("pipe1", {"order": 3})
    results = svc.get_versions("pipe1")
    assert results[0]["data"]["order"] == 3
    assert results[-1]["data"]["order"] == 1


def test_get_versions_limit():
    svc = PipelineDataVersioner()
    for i in range(10):
        svc.create_version("pipe1", {"i": i})
    results = svc.get_versions("pipe1", limit=3)
    assert len(results) == 3


def test_get_versions_default_limit():
    svc = PipelineDataVersioner()
    for i in range(60):
        svc.create_version("pipe1", {"i": i})
    results = svc.get_versions("pipe1")
    assert len(results) == 50


def test_get_versions_empty():
    svc = PipelineDataVersioner()
    results = svc.get_versions("pipe1")
    assert results == []


def test_get_latest_version():
    svc = PipelineDataVersioner()
    svc.create_version("pipe1", {"a": 1}, version=1)
    svc.create_version("pipe1", {"a": 2}, version=5)
    svc.create_version("pipe1", {"a": 3}, version=3)
    latest = svc.get_latest_version("pipe1")
    assert latest is not None
    assert latest["version"] == 5
    assert latest["data"] == {"a": 2}


def test_get_latest_version_not_found():
    svc = PipelineDataVersioner()
    assert svc.get_latest_version("pipe-missing") is None


def test_get_version_count():
    svc = PipelineDataVersioner()
    svc.create_version("pipe1", {"a": 1})
    svc.create_version("pipe1", {"a": 2})
    svc.create_version("pipe2", {"a": 3})
    assert svc.get_version_count() == 3
    assert svc.get_version_count(pipeline_id="pipe1") == 2
    assert svc.get_version_count(pipeline_id="pipe2") == 1
    assert svc.get_version_count(pipeline_id="pipe3") == 0


def test_get_stats():
    svc = PipelineDataVersioner()
    svc.create_version("pipe1", {"a": 1}, version=2)
    svc.create_version("pipe2", {"a": 2}, version=7)
    svc.create_version("pipe1", {"a": 3}, version=4)
    stats = svc.get_stats()
    assert stats["total_versions"] == 3
    assert stats["unique_pipelines"] == 2
    assert stats["max_version_number"] == 7


def test_get_stats_empty():
    svc = PipelineDataVersioner()
    stats = svc.get_stats()
    assert stats["total_versions"] == 0
    assert stats["unique_pipelines"] == 0
    assert stats["max_version_number"] == 0


def test_reset():
    svc = PipelineDataVersioner()
    svc.create_version("pipe1", {"a": 1})
    svc._callbacks["cb1"] = lambda a, d: None
    svc.on_change = lambda a, d: None
    svc.reset()
    assert svc.get_stats()["total_versions"] == 0
    assert len(svc._callbacks) == 0
    assert svc.on_change is None


def test_on_change_callback_create():
    events = []
    svc = PipelineDataVersioner()
    svc.on_change = lambda action, data: events.append(action)
    svc.create_version("pipe1", {"a": 1})
    assert "version_created" in events


def test_on_change_getter_setter():
    svc = PipelineDataVersioner()
    assert svc.on_change is None
    handler = lambda a, d: None
    svc.on_change = handler
    assert svc.on_change is handler


def test_remove_callback():
    svc = PipelineDataVersioner()
    svc._callbacks["cb1"] = lambda a, d: None
    assert svc.remove_callback("cb1") is True
    assert svc.remove_callback("cb1") is False


def test_remove_callback_nonexistent():
    svc = PipelineDataVersioner()
    assert svc.remove_callback("nope") is False


def test_callbacks_dict_fires():
    events = []
    svc = PipelineDataVersioner()
    svc._callbacks["tracker"] = lambda action, data: events.append((action, data["version_id"]))
    vid = svc.create_version("pipe1", {"a": 1})
    assert len(events) == 1
    assert events[0][0] == "version_created"
    assert events[0][1] == vid


def test_callback_exception_silenced():
    svc = PipelineDataVersioner()
    svc._callbacks["bad"] = lambda a, d: (_ for _ in ()).throw(ValueError("boom"))
    svc.on_change = lambda a, d: (_ for _ in ()).throw(RuntimeError("crash"))
    vid = svc.create_version("pipe1", {"a": 1})
    assert vid.startswith("pdve-")


def test_pruning():
    svc = PipelineDataVersioner()
    svc.MAX_ENTRIES = 5
    for i in range(7):
        svc.create_version("pipe1", {"i": i})
    assert len(svc._state.entries) <= 6
    stats = svc.get_stats()
    assert stats["total_versions"] <= 6


def test_prefix_and_max_entries():
    assert PipelineDataVersioner.PREFIX == "pdve-"
    assert PipelineDataVersioner.MAX_ENTRIES == 10000


def test_deepcopy_isolation_create():
    svc = PipelineDataVersioner()
    original = {"nested": {"val": 1}}
    vid = svc.create_version("pipe1", original)
    original["nested"]["val"] = 999
    entry = svc.get_version(vid)
    assert entry["data"]["nested"]["val"] == 1


def test_deepcopy_isolation_get():
    svc = PipelineDataVersioner()
    vid = svc.create_version("pipe1", {"nested": {"val": 1}})
    entry1 = svc.get_version(vid)
    entry1["data"]["nested"]["val"] = 999
    entry2 = svc.get_version(vid)
    assert entry2["data"]["nested"]["val"] == 1


if __name__ == "__main__":
    tests = [
        test_create_version_returns_id,
        test_create_version_unique_ids,
        test_get_version_by_id,
        test_get_version_not_found,
        test_get_version_returns_dict,
        test_create_version_defaults,
        test_get_versions_for_pipeline,
        test_get_versions_newest_first,
        test_get_versions_limit,
        test_get_versions_default_limit,
        test_get_versions_empty,
        test_get_latest_version,
        test_get_latest_version_not_found,
        test_get_version_count,
        test_get_stats,
        test_get_stats_empty,
        test_reset,
        test_on_change_callback_create,
        test_on_change_getter_setter,
        test_remove_callback,
        test_remove_callback_nonexistent,
        test_callbacks_dict_fires,
        test_callback_exception_silenced,
        test_pruning,
        test_prefix_and_max_entries,
        test_deepcopy_isolation_create,
        test_deepcopy_isolation_get,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
    print(f"{passed}/{len(tests)} tests passed")
