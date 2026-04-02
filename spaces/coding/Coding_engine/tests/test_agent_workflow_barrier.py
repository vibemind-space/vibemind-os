"""Tests for AgentWorkflowBarrier service."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.agent_workflow_barrier import AgentWorkflowBarrier


def test_create_barrier_returns_id():
    b = AgentWorkflowBarrier()
    bid = b.create_barrier("wf1", required_count=3, label="sync-step")
    assert bid.startswith("awba-")
    assert len(bid) > len("awba-")


def test_create_barrier_unique_ids():
    b = AgentWorkflowBarrier()
    id1 = b.create_barrier("wf1")
    id2 = b.create_barrier("wf1")
    assert id1 != id2


def test_create_barrier_returns_dict_via_get():
    b = AgentWorkflowBarrier()
    bid = b.create_barrier("wf1", required_count=2, label="step-a")
    entry = b.get_barrier(bid)
    assert isinstance(entry, dict)
    assert entry["barrier_id"] == bid
    assert entry["workflow_id"] == "wf1"
    assert entry["required_count"] == 2
    assert entry["label"] == "step-a"
    assert entry["arrivals"] == []


def test_create_barrier_default_args():
    b = AgentWorkflowBarrier()
    bid = b.create_barrier("wf1")
    entry = b.get_barrier(bid)
    assert entry["required_count"] == 1
    assert entry["label"] == ""


def test_arrive_records_arrival():
    b = AgentWorkflowBarrier()
    bid = b.create_barrier("wf1", required_count=2)
    result = b.arrive(bid, agent_id="agent-1")
    assert result is True
    entry = b.get_barrier(bid)
    assert len(entry["arrivals"]) == 1
    assert entry["arrivals"][0]["agent_id"] == "agent-1"


def test_arrive_nonexistent_barrier():
    b = AgentWorkflowBarrier()
    result = b.arrive("awba-nonexistent", agent_id="a1")
    assert result is False


def test_arrive_default_agent_id():
    b = AgentWorkflowBarrier()
    bid = b.create_barrier("wf1")
    b.arrive(bid)
    entry = b.get_barrier(bid)
    assert entry["arrivals"][0]["agent_id"] == ""


def test_is_complete_true():
    b = AgentWorkflowBarrier()
    bid = b.create_barrier("wf1", required_count=2)
    b.arrive(bid, "a1")
    assert b.is_complete(bid) is False
    b.arrive(bid, "a2")
    assert b.is_complete(bid) is True


def test_is_complete_exceeds_required():
    b = AgentWorkflowBarrier()
    bid = b.create_barrier("wf1", required_count=1)
    b.arrive(bid, "a1")
    b.arrive(bid, "a2")
    assert b.is_complete(bid) is True


def test_is_complete_nonexistent():
    b = AgentWorkflowBarrier()
    assert b.is_complete("awba-missing") is False


def test_get_barrier_not_found():
    b = AgentWorkflowBarrier()
    assert b.get_barrier("awba-nonexistent") is None


def test_get_barriers_all():
    b = AgentWorkflowBarrier()
    b.create_barrier("wf1")
    b.create_barrier("wf2")
    b.create_barrier("wf1")
    results = b.get_barriers()
    assert len(results) == 3


def test_get_barriers_filter_workflow():
    b = AgentWorkflowBarrier()
    b.create_barrier("wf1")
    b.create_barrier("wf2")
    b.create_barrier("wf1")
    results = b.get_barriers(workflow_id="wf1")
    assert len(results) == 2
    assert all(r["workflow_id"] == "wf1" for r in results)


def test_get_barriers_newest_first():
    b = AgentWorkflowBarrier()
    b.create_barrier("wf1", label="first")
    b.create_barrier("wf1", label="second")
    b.create_barrier("wf1", label="third")
    results = b.get_barriers(workflow_id="wf1")
    assert results[0]["label"] == "third"
    assert results[-1]["label"] == "first"


def test_get_barriers_limit():
    b = AgentWorkflowBarrier()
    for i in range(10):
        b.create_barrier("wf1", label=f"b{i}")
    results = b.get_barriers(limit=3)
    assert len(results) == 3


def test_get_barriers_default_limit():
    b = AgentWorkflowBarrier()
    for i in range(60):
        b.create_barrier("wf1")
    results = b.get_barriers()
    assert len(results) == 50


def test_get_barriers_empty():
    b = AgentWorkflowBarrier()
    assert b.get_barriers() == []


def test_get_barrier_count_all():
    b = AgentWorkflowBarrier()
    b.create_barrier("wf1")
    b.create_barrier("wf2")
    b.create_barrier("wf1")
    assert b.get_barrier_count() == 3


def test_get_barrier_count_filtered():
    b = AgentWorkflowBarrier()
    b.create_barrier("wf1")
    b.create_barrier("wf2")
    b.create_barrier("wf1")
    assert b.get_barrier_count(workflow_id="wf1") == 2
    assert b.get_barrier_count(workflow_id="wf2") == 1
    assert b.get_barrier_count(workflow_id="wf3") == 0


def test_get_stats():
    b = AgentWorkflowBarrier()
    bid1 = b.create_barrier("wf1", required_count=2)
    bid2 = b.create_barrier("wf1", required_count=1)
    b.arrive(bid1, "a1")
    b.arrive(bid1, "a2")
    b.arrive(bid2, "a1")
    stats = b.get_stats()
    assert stats["total_barriers"] == 2
    assert stats["completed_barriers"] == 2
    assert stats["total_arrivals"] == 3


def test_get_stats_empty():
    b = AgentWorkflowBarrier()
    stats = b.get_stats()
    assert stats["total_barriers"] == 0
    assert stats["completed_barriers"] == 0
    assert stats["total_arrivals"] == 0


def test_get_stats_partial_completion():
    b = AgentWorkflowBarrier()
    bid = b.create_barrier("wf1", required_count=3)
    b.arrive(bid, "a1")
    stats = b.get_stats()
    assert stats["total_barriers"] == 1
    assert stats["completed_barriers"] == 0
    assert stats["total_arrivals"] == 1


def test_reset():
    b = AgentWorkflowBarrier()
    b.create_barrier("wf1")
    b._callbacks["cb1"] = lambda a, d: None
    b.on_change = lambda a, d: None
    b.reset()
    assert b.get_stats()["total_barriers"] == 0
    assert len(b._callbacks) == 0
    assert b.on_change is None


def test_on_change_callback_create():
    events = []
    b = AgentWorkflowBarrier()
    b.on_change = lambda action, data: events.append(action)
    b.create_barrier("wf1")
    assert "barrier_created" in events


def test_on_change_callback_arrive():
    events = []
    b = AgentWorkflowBarrier()
    b.on_change = lambda action, data: events.append(action)
    bid = b.create_barrier("wf1", required_count=1)
    b.arrive(bid, "a1")
    assert "barrier_arrival" in events
    assert "barrier_completed" in events


def test_on_change_getter_setter():
    b = AgentWorkflowBarrier()
    assert b.on_change is None
    handler = lambda a, d: None
    b.on_change = handler
    assert b.on_change is handler


def test_remove_callback():
    b = AgentWorkflowBarrier()
    b._callbacks["cb1"] = lambda a, d: None
    assert b.remove_callback("cb1") is True
    assert b.remove_callback("cb1") is False


def test_remove_callback_nonexistent():
    b = AgentWorkflowBarrier()
    assert b.remove_callback("nope") is False


def test_callbacks_dict_fires():
    events = []
    b = AgentWorkflowBarrier()
    b._callbacks["tracker"] = lambda action, data: events.append((action, data["barrier_id"]))
    bid = b.create_barrier("wf1")
    assert len(events) == 1
    assert events[0][0] == "barrier_created"
    assert events[0][1] == bid


def test_callback_exception_silenced():
    b = AgentWorkflowBarrier()
    b._callbacks["bad"] = lambda a, d: (_ for _ in ()).throw(ValueError("boom"))
    b.on_change = lambda a, d: (_ for _ in ()).throw(RuntimeError("crash"))
    bid = b.create_barrier("wf1")
    assert bid.startswith("awba-")


def test_pruning():
    b = AgentWorkflowBarrier()
    b.MAX_ENTRIES = 5
    for i in range(7):
        b.create_barrier("wf1", label=f"b{i}")
    assert len(b._state.entries) <= 6
    stats = b.get_stats()
    assert stats["total_barriers"] <= 6


def test_prefix_and_max_entries():
    assert AgentWorkflowBarrier.PREFIX == "awba-"
    assert AgentWorkflowBarrier.MAX_ENTRIES == 10000


def test_barrier_completed_event_fires_on_last_arrival():
    events = []
    b = AgentWorkflowBarrier()
    b.on_change = lambda action, data: events.append(action)
    bid = b.create_barrier("wf1", required_count=2)
    b.arrive(bid, "a1")
    assert "barrier_completed" not in events
    b.arrive(bid, "a2")
    assert "barrier_completed" in events


if __name__ == "__main__":
    tests = [
        test_create_barrier_returns_id,
        test_create_barrier_unique_ids,
        test_create_barrier_returns_dict_via_get,
        test_create_barrier_default_args,
        test_arrive_records_arrival,
        test_arrive_nonexistent_barrier,
        test_arrive_default_agent_id,
        test_is_complete_true,
        test_is_complete_exceeds_required,
        test_is_complete_nonexistent,
        test_get_barrier_not_found,
        test_get_barriers_all,
        test_get_barriers_filter_workflow,
        test_get_barriers_newest_first,
        test_get_barriers_limit,
        test_get_barriers_default_limit,
        test_get_barriers_empty,
        test_get_barrier_count_all,
        test_get_barrier_count_filtered,
        test_get_stats,
        test_get_stats_empty,
        test_get_stats_partial_completion,
        test_reset,
        test_on_change_callback_create,
        test_on_change_callback_arrive,
        test_on_change_getter_setter,
        test_remove_callback,
        test_remove_callback_nonexistent,
        test_callbacks_dict_fires,
        test_callback_exception_silenced,
        test_pruning,
        test_prefix_and_max_entries,
        test_barrier_completed_event_fires_on_last_arrival,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
    print(f"{passed}/{len(tests)} tests passed")
