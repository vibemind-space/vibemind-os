"""Test pipeline rollout scheduler."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_rollout_scheduler import PipelineRolloutScheduler


def test_create_rollout():
    """Create and retrieve rollout."""
    rs = PipelineRolloutScheduler()
    rid = rs.create_rollout("v2_deploy", "api", tags=["prod"])
    assert rid.startswith("rlt-")

    r = rs.get_rollout(rid)
    assert r is not None
    assert r["name"] == "v2_deploy"
    assert r["component"] == "api"
    assert r["status"] == "draft"

    assert rs.remove_rollout(rid) is True
    assert rs.remove_rollout(rid) is False
    print("OK: create rollout")


def test_invalid_create():
    """Invalid creation rejected."""
    rs = PipelineRolloutScheduler()
    assert rs.create_rollout("", "comp") == ""
    assert rs.create_rollout("name", "") == ""
    print("OK: invalid create")


def test_duplicate():
    """Duplicate name rejected."""
    rs = PipelineRolloutScheduler()
    rs.create_rollout("v2", "api")
    assert rs.create_rollout("v2", "api") == ""
    print("OK: duplicate")


def test_max_rollouts():
    """Max rollouts enforced."""
    rs = PipelineRolloutScheduler(max_rollouts=2)
    rs.create_rollout("a", "comp")
    rs.create_rollout("b", "comp")
    assert rs.create_rollout("c", "comp") == ""
    print("OK: max rollouts")


def test_create_with_phases():
    """Create rollout with phases."""
    rs = PipelineRolloutScheduler()
    rid = rs.create_rollout("v2", "api", phases=[
        {"name": "canary", "target_pct": 10.0},
        {"name": "50pct", "target_pct": 50.0},
        {"name": "full", "target_pct": 100.0},
    ])
    r = rs.get_rollout(rid)
    assert len(r["phases"]) == 3
    assert r["phases"][0]["name"] == "canary"
    assert r["phases"][0]["target_pct"] == 10.0
    print("OK: create with phases")


def test_get_by_name():
    """Get rollout by name."""
    rs = PipelineRolloutScheduler()
    rs.create_rollout("v2_deploy", "api")

    r = rs.get_by_name("v2_deploy")
    assert r is not None
    assert rs.get_by_name("nonexistent") is None
    print("OK: get by name")


def test_start():
    """Start rollout."""
    rs = PipelineRolloutScheduler()
    rid = rs.create_rollout("v2", "api", phases=[
        {"name": "canary", "target_pct": 10.0},
    ])

    assert rs.start(rid) is True
    r = rs.get_rollout(rid)
    assert r["status"] == "running"
    assert r["current_phase"] == 0
    assert r["current_pct"] == 10.0
    assert r["phases"][0]["status"] == "active"

    assert rs.start(rid) is False  # not draft anymore
    print("OK: start")


def test_start_no_phases():
    """Can't start rollout without phases."""
    rs = PipelineRolloutScheduler()
    rid = rs.create_rollout("v2", "api")
    assert rs.start(rid) is False
    print("OK: start no phases")


def test_advance():
    """Advance through phases."""
    rs = PipelineRolloutScheduler()
    rid = rs.create_rollout("v2", "api", phases=[
        {"name": "canary", "target_pct": 10.0},
        {"name": "half", "target_pct": 50.0},
        {"name": "full", "target_pct": 100.0},
    ])
    rs.start(rid)

    assert rs.advance(rid) is True
    r = rs.get_rollout(rid)
    assert r["current_phase"] == 1
    assert r["current_pct"] == 50.0
    assert r["phases"][0]["status"] == "completed"
    assert r["phases"][1]["status"] == "active"
    print("OK: advance")


def test_advance_to_complete():
    """Advance through all phases completes rollout."""
    rs = PipelineRolloutScheduler()
    rid = rs.create_rollout("v2", "api", phases=[
        {"name": "canary", "target_pct": 10.0},
        {"name": "full", "target_pct": 100.0},
    ])
    rs.start(rid)
    rs.advance(rid)  # complete canary, start full
    rs.advance(rid)  # complete full

    r = rs.get_rollout(rid)
    assert r["status"] == "completed"
    assert r["current_pct"] == 100.0
    print("OK: advance to complete")


def test_pause_resume():
    """Pause and resume rollout."""
    rs = PipelineRolloutScheduler()
    rid = rs.create_rollout("v2", "api", phases=[{"name": "p1", "target_pct": 50.0}])
    rs.start(rid)

    assert rs.pause(rid) is True
    assert rs.get_rollout(rid)["status"] == "paused"
    assert rs.pause(rid) is False

    assert rs.resume(rid) is True
    assert rs.get_rollout(rid)["status"] == "running"
    assert rs.resume(rid) is False
    print("OK: pause resume")


def test_rollback():
    """Roll back rollout."""
    rs = PipelineRolloutScheduler()
    rid = rs.create_rollout("v2", "api", phases=[{"name": "p1", "target_pct": 50.0}])
    rs.start(rid)

    assert rs.rollback(rid, reason="errors") is True
    r = rs.get_rollout(rid)
    assert r["status"] == "rolled_back"
    assert r["current_pct"] == 0.0

    assert rs.rollback(rid) is False
    print("OK: rollback")


def test_rollback_paused():
    """Roll back from paused state."""
    rs = PipelineRolloutScheduler()
    rid = rs.create_rollout("v2", "api", phases=[{"name": "p1", "target_pct": 50.0}])
    rs.start(rid)
    rs.pause(rid)

    assert rs.rollback(rid) is True
    assert rs.get_rollout(rid)["status"] == "rolled_back"
    print("OK: rollback paused")


def test_get_progress():
    """Get rollout progress."""
    rs = PipelineRolloutScheduler()
    rid = rs.create_rollout("v2", "api", phases=[
        {"name": "p1", "target_pct": 25.0},
        {"name": "p2", "target_pct": 50.0},
        {"name": "p3", "target_pct": 75.0},
        {"name": "p4", "target_pct": 100.0},
    ])
    rs.start(rid)
    rs.advance(rid)  # complete p1

    prog = rs.get_progress(rid)
    assert prog["total_phases"] == 4
    assert prog["completed_phases"] == 1
    assert prog["current_phase"] == 1
    assert abs(prog["pct_complete"] - 25.0) < 0.01

    assert rs.get_progress("nonexistent") is None
    print("OK: get progress")


def test_list_rollouts():
    """List rollouts with filters."""
    rs = PipelineRolloutScheduler()
    rid1 = rs.create_rollout("v2", "api", tags=["prod"], phases=[{"name": "p1", "target_pct": 100.0}])
    rs.create_rollout("v3", "worker")
    rs.start(rid1)

    all_r = rs.list_rollouts()
    assert len(all_r) == 2

    by_status = rs.list_rollouts(status="running")
    assert len(by_status) == 1

    by_comp = rs.list_rollouts(component="api")
    assert len(by_comp) == 1

    by_tag = rs.list_rollouts(tag="prod")
    assert len(by_tag) == 1
    print("OK: list rollouts")


def test_get_active():
    """Get active rollouts."""
    rs = PipelineRolloutScheduler()
    rid1 = rs.create_rollout("v2", "api", phases=[{"name": "p1", "target_pct": 100.0}])
    rs.create_rollout("v3", "worker")
    rs.start(rid1)

    active = rs.get_active_rollouts()
    assert len(active) == 1
    print("OK: get active")


def test_callback():
    """Callback fires on events."""
    rs = PipelineRolloutScheduler()
    fired = []
    rs.on_change("mon", lambda a, d: fired.append(a))

    rid = rs.create_rollout("v2", "api", phases=[
        {"name": "p1", "target_pct": 50.0},
        {"name": "p2", "target_pct": 100.0},
    ])
    assert "rollout_created" in fired

    rs.start(rid)
    assert "rollout_started" in fired
    assert "phase_started" in fired

    rs.advance(rid)
    rs.advance(rid)
    assert "rollout_completed" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    rs = PipelineRolloutScheduler()
    assert rs.on_change("mon", lambda a, d: None) is True
    assert rs.on_change("mon", lambda a, d: None) is False
    assert rs.remove_callback("mon") is True
    assert rs.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    rs = PipelineRolloutScheduler()
    rid1 = rs.create_rollout("v2", "api", phases=[{"name": "p1", "target_pct": 100.0}])
    rs.start(rid1)
    rs.advance(rid1)

    rid2 = rs.create_rollout("v3", "worker", phases=[{"name": "p1", "target_pct": 100.0}])
    rs.start(rid2)
    rs.rollback(rid2)

    stats = rs.get_stats()
    assert stats["total_created"] == 2
    assert stats["total_completed"] == 1
    assert stats["total_rolled_back"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    rs = PipelineRolloutScheduler()
    rs.create_rollout("v2", "api")

    rs.reset()
    assert rs.list_rollouts() == []
    stats = rs.get_stats()
    assert stats["current_rollouts"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Rollout Scheduler Tests ===\n")
    test_create_rollout()
    test_invalid_create()
    test_duplicate()
    test_max_rollouts()
    test_create_with_phases()
    test_get_by_name()
    test_start()
    test_start_no_phases()
    test_advance()
    test_advance_to_complete()
    test_pause_resume()
    test_rollback()
    test_rollback_paused()
    test_get_progress()
    test_list_rollouts()
    test_get_active()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 20 TESTS PASSED ===")


if __name__ == "__main__":
    main()
