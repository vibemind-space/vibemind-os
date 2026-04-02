"""Test pipeline rollback mechanism."""
import sys
import time
sys.path.insert(0, ".")

from src.services.pipeline_rollback import (
    PipelineRollbackManager,
    SnapshotType,
)


def test_create_snapshot():
    """Create a snapshot of pipeline state."""
    mgr = PipelineRollbackManager()
    snap_id = mgr.create_snapshot(
        phase="planning",
        state={"files": ["main.py"], "config": {"debug": True}},
        description="After planning phase",
    )

    assert snap_id.startswith("snap-")
    info = mgr.get_snapshot(snap_id)
    assert info is not None
    assert info["phase"] == "planning"
    assert info["description"] == "After planning phase"
    assert "files" in info["state_keys"]
    print("OK: create snapshot")


def test_snapshot_state_isolation():
    """Snapshot state is deep-copied (immune to external mutation)."""
    mgr = PipelineRollbackManager()
    state = {"items": [1, 2, 3], "nested": {"a": 1}}
    snap_id = mgr.create_snapshot(phase="test", state=state)

    # Mutate original state
    state["items"].append(4)
    state["nested"]["a"] = 999

    # Snapshot should be unchanged
    saved = mgr.get_snapshot_state(snap_id)
    assert saved["items"] == [1, 2, 3]
    assert saved["nested"]["a"] == 1
    print("OK: snapshot state isolation")


def test_rollback_to():
    """Rollback to a specific snapshot."""
    mgr = PipelineRollbackManager()
    s1 = mgr.create_snapshot(phase="planning", state={"step": 1})
    s2 = mgr.create_snapshot(phase="generation", state={"step": 2})
    s3 = mgr.create_snapshot(phase="testing", state={"step": 3})

    # Rollback to planning
    state = mgr.rollback_to(s1)
    assert state is not None
    assert state["step"] == 1

    # Current should now be s1
    current = mgr.get_current()
    assert current["snapshot_id"] == s1
    print("OK: rollback to")


def test_rollback_saves_current():
    """Rollback auto-saves current state before rolling back."""
    mgr = PipelineRollbackManager()
    s1 = mgr.create_snapshot(phase="v1", state={"version": 1})

    # Rollback with save_current
    state = mgr.rollback_to(
        s1,
        save_current=True,
        current_state={"version": 2, "unsaved_changes": True},
    )

    assert state["version"] == 1

    # Should have a pre_rollback snapshot
    snaps = mgr.list_snapshots(snapshot_type=SnapshotType.PRE_ROLLBACK)
    assert len(snaps) == 1
    assert "pre_rollback" in snaps[0]["tags"]
    print("OK: rollback saves current")


def test_rollback_to_phase():
    """Rollback to most recent snapshot of a given phase."""
    mgr = PipelineRollbackManager()
    mgr.create_snapshot(phase="planning", state={"v": 1})
    mgr.create_snapshot(phase="generation", state={"v": 2})
    mgr.create_snapshot(phase="planning", state={"v": 3})
    mgr.create_snapshot(phase="testing", state={"v": 4})

    state = mgr.rollback_to_phase("planning")
    assert state is not None
    assert state["v"] == 3  # Most recent planning snapshot
    print("OK: rollback to phase")


def test_rollback_to_tag():
    """Rollback to most recent snapshot with a tag."""
    mgr = PipelineRollbackManager()
    s1 = mgr.create_snapshot(phase="v1", state={"v": 1}, tags={"release"})
    mgr.create_snapshot(phase="v2", state={"v": 2})
    mgr.create_snapshot(phase="v3", state={"v": 3}, tags={"release"})

    state = mgr.rollback_to_tag("release")
    assert state is not None
    assert state["v"] == 3
    print("OK: rollback to tag")


def test_undo():
    """Undo one step back."""
    mgr = PipelineRollbackManager()
    s1 = mgr.create_snapshot(phase="step1", state={"step": 1})
    s2 = mgr.create_snapshot(phase="step2", state={"step": 2})
    s3 = mgr.create_snapshot(phase="step3", state={"step": 3})

    state = mgr.undo()
    assert state is not None
    assert state["step"] == 2

    state2 = mgr.undo()
    assert state2 is not None
    assert state2["step"] == 1

    # No more parent
    state3 = mgr.undo()
    assert state3 is None
    print("OK: undo")


def test_rollback_not_found():
    """Rollback to nonexistent snapshot returns None."""
    mgr = PipelineRollbackManager()
    result = mgr.rollback_to("snap-nonexistent")
    assert result is None
    print("OK: rollback not found")


def test_save_point():
    """Manual save point creation."""
    mgr = PipelineRollbackManager()
    snap_id = mgr.save_point("before-refactor", state={"files": ["a.py"]})

    info = mgr.get_snapshot(snap_id)
    assert info["snapshot_type"] == "manual"
    assert "save_point" in info["tags"]
    assert "before-refactor" in info["tags"]
    print("OK: save point")


def test_list_snapshots():
    """List snapshots with filters."""
    mgr = PipelineRollbackManager()
    mgr.create_snapshot(phase="planning", state={})
    mgr.create_snapshot(phase="generation", state={})
    mgr.create_snapshot(phase="planning", state={})

    all_snaps = mgr.list_snapshots()
    assert len(all_snaps) == 3

    planning = mgr.list_snapshots(phase="planning")
    assert len(planning) == 2

    # Limit
    limited = mgr.list_snapshots(limit=1)
    assert len(limited) == 1
    print("OK: list snapshots")


def test_diff_snapshots():
    """Compare two snapshots."""
    mgr = PipelineRollbackManager()
    s1 = mgr.create_snapshot(phase="v1", state={
        "files": ["a.py", "b.py"],
        "config": {"debug": True},
        "version": 1,
    })
    s2 = mgr.create_snapshot(phase="v2", state={
        "files": ["a.py", "b.py", "c.py"],
        "config": {"debug": False},
        "new_feature": True,
    })

    diff = mgr.diff_snapshots(s1, s2)
    assert diff["total_changes"] > 0
    assert "new_feature" in diff["added"]
    assert "version" in diff["removed"]
    assert "config" in diff["modified"]
    assert diff["modified"]["config"]["old"] == {"debug": True}
    assert diff["modified"]["config"]["new"] == {"debug": False}
    print("OK: diff snapshots")


def test_diff_not_found():
    """Diff with nonexistent snapshot returns error."""
    mgr = PipelineRollbackManager()
    s1 = mgr.create_snapshot(phase="v1", state={})
    diff = mgr.diff_snapshots(s1, "snap-nope")
    assert "error" in diff
    print("OK: diff not found")


def test_tags():
    """Add and remove tags."""
    mgr = PipelineRollbackManager()
    snap_id = mgr.create_snapshot(phase="v1", state={})

    assert mgr.add_tag(snap_id, "release") is True
    assert mgr.add_tag(snap_id, "stable") is True

    info = mgr.get_snapshot(snap_id)
    assert "release" in info["tags"]
    assert "stable" in info["tags"]

    assert mgr.remove_tag(snap_id, "release") is True
    assert mgr.remove_tag(snap_id, "release") is False  # Already removed

    # Nonexistent snapshot
    assert mgr.add_tag("nope", "tag") is False
    print("OK: tags")


def test_chain():
    """Get snapshot chain (ancestry)."""
    mgr = PipelineRollbackManager()
    s1 = mgr.create_snapshot(phase="step1", state={"step": 1})
    s2 = mgr.create_snapshot(phase="step2", state={"step": 2})
    s3 = mgr.create_snapshot(phase="step3", state={"step": 3})

    chain = mgr.get_chain(s3)
    assert len(chain) == 3
    assert chain[0]["snapshot_id"] == s3
    assert chain[1]["snapshot_id"] == s2
    assert chain[2]["snapshot_id"] == s1

    # Default: current
    chain2 = mgr.get_chain()
    assert len(chain2) == 3
    print("OK: chain")


def test_delete_snapshot():
    """Delete a specific snapshot."""
    mgr = PipelineRollbackManager()
    s1 = mgr.create_snapshot(phase="v1", state={"step": 1})
    s2 = mgr.create_snapshot(phase="v2", state={"step": 2})
    s3 = mgr.create_snapshot(phase="v3", state={"step": 3})

    assert mgr.delete_snapshot(s2) is True
    assert mgr.get_snapshot(s2) is None

    # s3's parent should now point to s1's parent (s2's parent)
    snaps = mgr.list_snapshots()
    assert len(snaps) == 2
    print("OK: delete snapshot")


def test_max_snapshots():
    """Snapshots are pruned when over limit."""
    mgr = PipelineRollbackManager(max_snapshots=3)

    ids = []
    for i in range(5):
        ids.append(mgr.create_snapshot(phase=f"step{i}", state={"i": i}))

    snaps = mgr.list_snapshots()
    assert len(snaps) == 3

    stats = mgr.get_stats()
    assert stats["total_pruned"] == 2
    print("OK: max snapshots")


def test_clear_older_than():
    """Remove old snapshots."""
    mgr = PipelineRollbackManager()
    s1 = mgr.create_snapshot(phase="old", state={"old": True})

    # Backdate it
    mgr._snapshot_map[s1].created_at = time.time() - 3600

    mgr.create_snapshot(phase="new", state={"new": True})

    removed = mgr.clear_older_than(1800)  # 30 min
    assert removed == 1
    assert mgr.get_snapshot(s1) is None
    assert len(mgr.list_snapshots()) == 1
    print("OK: clear older than")


def test_stats():
    """Stats are accurate."""
    mgr = PipelineRollbackManager()
    s1 = mgr.create_snapshot(phase="planning", state={"v": 1})
    s2 = mgr.create_snapshot(phase="generation", state={"v": 2})
    mgr.rollback_to(s1)

    stats = mgr.get_stats()
    assert stats["total_snapshots"] == 2
    assert stats["total_created"] == 2
    assert stats["total_rollbacks"] == 1
    assert stats["current_snapshot"] == s1
    assert stats["phase_counts"]["planning"] == 1
    assert stats["phase_counts"]["generation"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    mgr = PipelineRollbackManager()
    mgr.create_snapshot(phase="v1", state={"x": 1})

    mgr.reset()
    assert mgr.list_snapshots() == []
    assert mgr.get_stats()["total_created"] == 0
    assert mgr.get_current() is None
    print("OK: reset")


def main():
    print("=== Pipeline Rollback Tests ===\n")
    test_create_snapshot()
    test_snapshot_state_isolation()
    test_rollback_to()
    test_rollback_saves_current()
    test_rollback_to_phase()
    test_rollback_to_tag()
    test_undo()
    test_rollback_not_found()
    test_save_point()
    test_list_snapshots()
    test_diff_snapshots()
    test_diff_not_found()
    test_tags()
    test_chain()
    test_delete_snapshot()
    test_max_snapshots()
    test_clear_older_than()
    test_stats()
    test_reset()
    print("\n=== ALL 19 TESTS PASSED ===")


if __name__ == "__main__":
    main()
