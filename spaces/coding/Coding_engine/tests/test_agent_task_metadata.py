"""Tests for AgentTaskMetadata service."""

import sys
import os
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.agent_task_metadata import AgentTaskMetadata


def test_set_metadata():
    meta = AgentTaskMetadata()
    eid = meta.set_metadata("agent-1", "build", "version", "1.0")
    assert eid.startswith("atm2-")
    assert len(eid) == 5 + 16  # prefix + 16 hex chars


def test_get_metadata():
    meta = AgentTaskMetadata()
    meta.set_metadata("agent-1", "build", "version", "1.0")
    value = meta.get_metadata("agent-1", "build", "version")
    assert value == "1.0"


def test_get_metadata_not_found():
    meta = AgentTaskMetadata()
    assert meta.get_metadata("agent-1", "build", "nonexistent") is None


def test_set_metadata_update_existing():
    meta = AgentTaskMetadata()
    eid1 = meta.set_metadata("agent-1", "build", "version", "1.0")
    eid2 = meta.set_metadata("agent-1", "build", "version", "2.0")
    assert eid1 == eid2
    assert meta.get_metadata("agent-1", "build", "version") == "2.0"
    assert meta.get_metadata_count() == 1


def test_get_all_metadata():
    meta = AgentTaskMetadata()
    meta.set_metadata("agent-1", "build", "version", "1.0")
    meta.set_metadata("agent-1", "build", "status", "ok")
    meta.set_metadata("agent-1", "test", "coverage", "90%")
    all_meta = meta.get_all_metadata("agent-1", "build")
    assert all_meta == {"version": "1.0", "status": "ok"}


def test_get_all_metadata_empty():
    meta = AgentTaskMetadata()
    assert meta.get_all_metadata("agent-1", "build") == {}


def test_delete_metadata():
    meta = AgentTaskMetadata()
    meta.set_metadata("agent-1", "build", "version", "1.0")
    assert meta.delete_metadata("agent-1", "build", "version") is True
    assert meta.get_metadata("agent-1", "build", "version") is None
    assert meta.delete_metadata("agent-1", "build", "version") is False


def test_clear_metadata():
    meta = AgentTaskMetadata()
    meta.set_metadata("agent-1", "build", "version", "1.0")
    meta.set_metadata("agent-1", "build", "status", "ok")
    meta.set_metadata("agent-1", "test", "coverage", "90%")
    count = meta.clear_metadata("agent-1", "build")
    assert count == 2
    assert meta.get_metadata_count() == 1
    assert meta.get_metadata("agent-1", "test", "coverage") == "90%"


def test_clear_metadata_empty():
    meta = AgentTaskMetadata()
    assert meta.clear_metadata("agent-1", "build") == 0


def test_get_metadata_count():
    meta = AgentTaskMetadata()
    meta.set_metadata("agent-1", "build", "version", "1.0")
    meta.set_metadata("agent-1", "test", "status", "ok")
    meta.set_metadata("agent-2", "build", "version", "2.0")
    assert meta.get_metadata_count() == 3
    assert meta.get_metadata_count(agent_id="agent-1") == 2
    assert meta.get_metadata_count(agent_id="agent-2") == 1
    assert meta.get_metadata_count(agent_id="agent-3") == 0


def test_list_tasks_with_metadata():
    meta = AgentTaskMetadata()
    meta.set_metadata("agent-1", "build", "version", "1.0")
    meta.set_metadata("agent-1", "test", "status", "ok")
    meta.set_metadata("agent-1", "deploy", "target", "prod")
    meta.set_metadata("agent-2", "build", "version", "2.0")
    tasks = meta.list_tasks_with_metadata("agent-1")
    assert tasks == ["build", "deploy", "test"]


def test_list_tasks_with_metadata_empty():
    meta = AgentTaskMetadata()
    assert meta.list_tasks_with_metadata("agent-1") == []


def test_get_stats():
    meta = AgentTaskMetadata()
    meta.set_metadata("agent-1", "build", "version", "1.0")
    meta.set_metadata("agent-1", "test", "status", "ok")
    meta.set_metadata("agent-2", "build", "version", "2.0")
    stats = meta.get_stats()
    assert stats["total_entries"] == 3
    assert stats["unique_agents"] == 2
    assert stats["unique_tasks"] == 3


def test_reset():
    meta = AgentTaskMetadata()
    meta.set_metadata("agent-1", "build", "version", "1.0")
    meta.set_metadata("agent-2", "test", "status", "ok")
    meta.reset()
    assert meta.get_metadata_count() == 0
    assert meta.get_stats()["total_entries"] == 0


def test_on_change_and_callbacks():
    events = []

    def on_change(event, data):
        events.append(("on_change", event, data))

    def cb1(event, data):
        events.append(("cb1", event, data))

    meta = AgentTaskMetadata()
    meta.on_change = on_change
    assert meta.on_change is on_change
    meta._callbacks["cb1"] = cb1

    meta.set_metadata("agent-1", "build", "version", "1.0")
    assert len(events) >= 2
    assert events[0][0] == "on_change"
    assert events[1][0] == "cb1"


def test_remove_callback():
    meta = AgentTaskMetadata()
    meta._callbacks["mycb"] = lambda e, d: None
    assert meta.remove_callback("mycb") is True
    assert meta.remove_callback("mycb") is False
    assert meta.remove_callback("nonexistent") is False


def test_prune():
    meta = AgentTaskMetadata()
    meta.MAX_ENTRIES = 5
    for i in range(10):
        meta.set_metadata("agent-1", f"task-{i}", "key", i)
    assert meta.get_metadata_count() <= 5


def test_generate_id_uniqueness():
    meta = AgentTaskMetadata()
    ids = set()
    for i in range(100):
        rid = meta._generate_id(f"data-{i}")
        ids.add(rid)
    assert len(ids) == 100


def test_callback_exception_handling():
    """Callbacks that raise should not break the service."""
    meta = AgentTaskMetadata()

    def bad_on_change(event, data):
        raise ValueError("boom")

    def bad_cb(event, data):
        raise RuntimeError("kaboom")

    meta.on_change = bad_on_change
    meta._callbacks["bad"] = bad_cb

    # Should not raise
    eid = meta.set_metadata("agent-1", "build", "version", "1.0")
    assert eid.startswith("atm2-")


def test_updated_at_changes_on_update():
    meta = AgentTaskMetadata()
    eid = meta.set_metadata("agent-1", "build", "version", "1.0")
    entry_before = dict(meta._state.entries[eid])
    meta.set_metadata("agent-1", "build", "version", "2.0")
    entry_after = meta._state.entries[eid]
    assert entry_after["updated_at"] >= entry_before["updated_at"]
    assert entry_after["created_at"] == entry_before["created_at"]


# -------------------------------------------------------------------
# Runner
# -------------------------------------------------------------------

def _collect_tests():
    return [
        v for k, v in sorted(globals().items())
        if k.startswith("test_") and callable(v)
    ]


if __name__ == "__main__":
    tests = _collect_tests()
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception:
            failed += 1
            print(f"FAIL: {t.__name__}")
            traceback.print_exc()
            print()
    total = passed + failed
    print(f"{passed}/{total} tests passed")
    if failed:
        sys.exit(1)
