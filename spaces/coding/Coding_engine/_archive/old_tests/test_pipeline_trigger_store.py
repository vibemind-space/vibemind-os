"""Test pipeline trigger store -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_trigger_store import PipelineTriggerStore


def test_create_trigger():
    ts = PipelineTriggerStore()
    tid = ts.create_trigger("deploy", "push", condition="branch==main", metadata={"env": "prod"})
    assert len(tid) > 0
    assert tid.startswith("ptr-")
    t = ts.get_trigger(tid)
    assert t is not None
    assert t["pipeline_name"] == "deploy"
    assert t["event_type"] == "push"
    print("OK: create trigger")


def test_enable_disable():
    ts = PipelineTriggerStore()
    tid = ts.create_trigger("deploy", "push")
    # Starts enabled
    t = ts.get_trigger(tid)
    assert t["enabled"] is True
    assert ts.disable_trigger(tid) is True
    t = ts.get_trigger(tid)
    assert t["enabled"] is False
    assert ts.enable_trigger(tid) is True
    t = ts.get_trigger(tid)
    assert t["enabled"] is True
    print("OK: enable/disable")


def test_fire_trigger():
    ts = PipelineTriggerStore()
    tid = ts.create_trigger("deploy", "push")
    result = ts.fire_trigger(tid, context={"commit": "abc123"})
    assert result is not None
    assert "fire_id" in result or "timestamp" in result or "context" in result
    print("OK: fire trigger")


def test_fire_disabled():
    ts = PipelineTriggerStore()
    tid = ts.create_trigger("deploy", "push")
    ts.disable_trigger(tid)
    result = ts.fire_trigger(tid)
    assert result is None
    print("OK: fire disabled")


def test_get_triggers_for_pipeline():
    ts = PipelineTriggerStore()
    ts.create_trigger("deploy", "push")
    ts.create_trigger("deploy", "schedule")
    ts.create_trigger("test", "push")
    triggers = ts.get_triggers_for_pipeline("deploy")
    assert len(triggers) == 2
    print("OK: get triggers for pipeline")


def test_get_fire_history():
    ts = PipelineTriggerStore()
    tid = ts.create_trigger("deploy", "push")
    ts.fire_trigger(tid, context={"c": 1})
    ts.fire_trigger(tid, context={"c": 2})
    history = ts.get_fire_history(tid)
    assert len(history) == 2
    print("OK: get fire history")


def test_delete_trigger():
    ts = PipelineTriggerStore()
    tid = ts.create_trigger("deploy", "push")
    assert ts.delete_trigger(tid) is True
    assert ts.delete_trigger(tid) is False
    print("OK: delete trigger")


def test_list_triggers():
    ts = PipelineTriggerStore()
    ts.create_trigger("deploy", "push")
    tid2 = ts.create_trigger("test", "schedule")
    ts.disable_trigger(tid2)
    all_t = ts.list_triggers()
    assert len(all_t) == 2
    enabled = ts.list_triggers(enabled_only=True)
    assert len(enabled) == 1
    print("OK: list triggers")


def test_callbacks():
    ts = PipelineTriggerStore()
    fired = []
    ts.on_change("mon", lambda a, d: fired.append(a))
    ts.create_trigger("deploy", "push")
    assert len(fired) >= 1
    assert ts.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    ts = PipelineTriggerStore()
    ts.create_trigger("deploy", "push")
    stats = ts.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    ts = PipelineTriggerStore()
    ts.create_trigger("deploy", "push")
    ts.reset()
    assert ts.list_triggers() == []
    print("OK: reset")


def main():
    print("=== Pipeline Trigger Store Tests ===\n")
    test_create_trigger()
    test_enable_disable()
    test_fire_trigger()
    test_fire_disabled()
    test_get_triggers_for_pipeline()
    test_get_fire_history()
    test_delete_trigger()
    test_list_triggers()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
