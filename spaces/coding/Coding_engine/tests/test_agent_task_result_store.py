"""Tests for AgentTaskResultStore service."""

import sys
import os
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.agent_task_result_store import AgentTaskResultStore


def test_store_result():
    store = AgentTaskResultStore()
    rid = store.store_result("agent-1", "build", {"ok": True})
    assert rid.startswith("atrs-")
    assert len(rid) == 5 + 16  # prefix + 16 hex chars


def test_get_result():
    store = AgentTaskResultStore()
    rid = store.store_result("agent-1", "build", {"ok": True})
    result = store.get_result(rid)
    assert result is not None
    assert result["agent_id"] == "agent-1"
    assert result["task_name"] == "build"
    assert result["result"] == {"ok": True}
    assert result["status"] == "success"
    assert result["metadata"] == {}
    assert "created_at" in result


def test_get_result_not_found():
    store = AgentTaskResultStore()
    assert store.get_result("atrs-nonexistent") is None


def test_store_result_with_status_and_metadata():
    store = AgentTaskResultStore()
    rid = store.store_result("agent-1", "deploy", "failed", status="error", metadata={"reason": "timeout"})
    result = store.get_result(rid)
    assert result["status"] == "error"
    assert result["metadata"] == {"reason": "timeout"}


def test_get_results_basic():
    store = AgentTaskResultStore()
    store.store_result("agent-1", "build", "ok")
    store.store_result("agent-1", "test", "ok")
    store.store_result("agent-2", "build", "ok")
    results = store.get_results("agent-1")
    assert len(results) == 2
    assert all(r["agent_id"] == "agent-1" for r in results)


def test_get_results_filter_task_name():
    store = AgentTaskResultStore()
    store.store_result("agent-1", "build", "ok")
    store.store_result("agent-1", "test", "ok")
    results = store.get_results("agent-1", task_name="build")
    assert len(results) == 1
    assert results[0]["task_name"] == "build"


def test_get_results_filter_status():
    store = AgentTaskResultStore()
    store.store_result("agent-1", "build", "ok", status="success")
    store.store_result("agent-1", "build", "fail", status="error")
    results = store.get_results("agent-1", status="error")
    assert len(results) == 1
    assert results[0]["status"] == "error"


def test_get_results_newest_first():
    store = AgentTaskResultStore()
    r1 = store.store_result("agent-1", "build", "first")
    r2 = store.store_result("agent-1", "build", "second")
    results = store.get_results("agent-1")
    assert results[0]["result"] == "second"
    assert results[1]["result"] == "first"


def test_get_results_limit():
    store = AgentTaskResultStore()
    for i in range(10):
        store.store_result("agent-1", "build", i)
    results = store.get_results("agent-1", limit=3)
    assert len(results) == 3


def test_get_latest_result():
    store = AgentTaskResultStore()
    store.store_result("agent-1", "build", "first")
    store.store_result("agent-1", "build", "second")
    store.store_result("agent-1", "test", "other")
    latest = store.get_latest_result("agent-1", "build")
    assert latest is not None
    assert latest["result"] == "second"


def test_get_latest_result_not_found():
    store = AgentTaskResultStore()
    assert store.get_latest_result("agent-1", "nonexistent") is None


def test_get_result_count():
    store = AgentTaskResultStore()
    store.store_result("agent-1", "build", "ok")
    store.store_result("agent-1", "test", "ok")
    store.store_result("agent-2", "build", "ok", status="error")
    assert store.get_result_count() == 3
    assert store.get_result_count(agent_id="agent-1") == 2
    assert store.get_result_count(status="error") == 1
    assert store.get_result_count(agent_id="agent-2", status="error") == 1


def test_remove_result():
    store = AgentTaskResultStore()
    rid = store.store_result("agent-1", "build", "ok")
    assert store.remove_result(rid) is True
    assert store.get_result(rid) is None
    assert store.remove_result(rid) is False


def test_clear_results():
    store = AgentTaskResultStore()
    store.store_result("agent-1", "build", "ok")
    store.store_result("agent-1", "test", "ok")
    store.store_result("agent-2", "build", "ok")
    count = store.clear_results("agent-1")
    assert count == 2
    assert store.get_result_count() == 1
    assert store.get_result_count(agent_id="agent-1") == 0


def test_get_stats():
    store = AgentTaskResultStore()
    store.store_result("agent-1", "build", "ok", status="success")
    store.store_result("agent-1", "test", "fail", status="error")
    store.store_result("agent-2", "build", "ok", status="success")
    stats = store.get_stats()
    assert stats["total_results"] == 3
    assert stats["unique_agents"] == 2
    assert stats["success_count"] == 2
    assert stats["error_count"] == 1


def test_reset():
    store = AgentTaskResultStore()
    store.store_result("agent-1", "build", "ok")
    store.store_result("agent-2", "test", "ok")
    store.reset()
    assert store.get_result_count() == 0
    assert store.get_stats()["total_results"] == 0


def test_on_change_and_callbacks():
    events = []

    def on_change(event, data):
        events.append(("on_change", event, data))

    def cb1(event, data):
        events.append(("cb1", event, data))

    store = AgentTaskResultStore()
    store.on_change = on_change
    assert store.on_change is on_change
    store._callbacks["cb1"] = cb1

    store.store_result("agent-1", "build", "ok")
    assert len(events) >= 2
    assert events[0][0] == "on_change"
    assert events[1][0] == "cb1"


def test_remove_callback():
    store = AgentTaskResultStore()
    store._callbacks["mycb"] = lambda e, d: None
    assert store.remove_callback("mycb") is True
    assert store.remove_callback("mycb") is False
    assert store.remove_callback("nonexistent") is False


def test_prune():
    store = AgentTaskResultStore()
    store.MAX_ENTRIES = 5
    for i in range(10):
        store.store_result("agent-1", f"task-{i}", i)
    assert store.get_result_count() <= 5


def test_generate_id_uniqueness():
    store = AgentTaskResultStore()
    ids = set()
    for i in range(100):
        rid = store._generate_id(f"data-{i}")
        ids.add(rid)
    assert len(ids) == 100


def test_callback_exception_handling():
    """Callbacks that raise should not break the service."""
    store = AgentTaskResultStore()

    def bad_on_change(event, data):
        raise ValueError("boom")

    def bad_cb(event, data):
        raise RuntimeError("kaboom")

    store.on_change = bad_on_change
    store._callbacks["bad"] = bad_cb

    # Should not raise
    rid = store.store_result("agent-1", "build", "ok")
    assert rid.startswith("atrs-")


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
