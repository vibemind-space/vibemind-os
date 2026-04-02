"""Test pipeline snapshot."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_snapshot import PipelineSnapshot


SAMPLE_STATE = {
    "agents": ["Builder", "Tester"],
    "tasks": 42,
    "status": "running",
    "config": {"timeout": 30, "retries": 3},
}

SAMPLE_STATE_V2 = {
    "agents": ["Builder", "Tester", "Deployer"],
    "tasks": 50,
    "status": "running",
    "config": {"timeout": 60, "retries": 5},
    "version": 2,
}


def test_capture():
    """Capture a snapshot."""
    mgr = PipelineSnapshot()
    sid = mgr.capture("checkpoint", SAMPLE_STATE, description="Initial state",
                       created_by="admin", tags={"v1", "stable"})
    assert sid.startswith("snap-")

    snap = mgr.get(sid)
    assert snap is not None
    assert snap["name"] == "checkpoint"
    assert snap["created_by"] == "admin"
    assert "v1" in snap["tags"]
    assert "agents" in snap["data_keys"]
    print("OK: capture")


def test_get_data():
    """Get full snapshot data."""
    mgr = PipelineSnapshot()
    sid = mgr.capture("test", SAMPLE_STATE)

    data = mgr.get_data(sid)
    assert data is not None
    assert data["tasks"] == 42
    assert data["agents"] == ["Builder", "Tester"]

    # Deep copy — modifying doesn't affect original
    data["tasks"] = 999
    assert mgr.get_data(sid)["tasks"] == 42

    assert mgr.get_data("fake") is None
    print("OK: get data")


def test_get_by_name():
    """Get snapshots by name."""
    mgr = PipelineSnapshot()
    mgr.capture("daily", {"day": 1})
    mgr.capture("daily", {"day": 2})
    mgr.capture("weekly", {"week": 1})

    dailies = mgr.get_by_name("daily")
    assert len(dailies) == 2
    # Most recent first
    assert dailies[0]["created_at"] >= dailies[1]["created_at"]

    weeklies = mgr.get_by_name("weekly")
    assert len(weeklies) == 1

    assert mgr.get_by_name("nonexistent") == []
    print("OK: get by name")


def test_get_latest():
    """Get latest snapshot."""
    mgr = PipelineSnapshot()
    mgr.capture("checkpoint", {"v": 1})
    mgr.capture("checkpoint", {"v": 2})
    mgr.capture("other", {"v": 3})

    latest = mgr.get_latest()
    assert latest is not None

    latest_cp = mgr.get_latest(name="checkpoint")
    assert latest_cp is not None

    assert mgr.get_latest(name="nonexistent") is None
    print("OK: get latest")


def test_compare_identical():
    """Compare identical snapshots."""
    mgr = PipelineSnapshot()
    a = mgr.capture("a", SAMPLE_STATE)
    b = mgr.capture("b", SAMPLE_STATE)

    diff = mgr.compare(a, b)
    assert diff is not None
    assert diff["identical"] is True
    assert diff["total_diffs"] == 0
    print("OK: compare identical")


def test_compare_different():
    """Compare different snapshots."""
    mgr = PipelineSnapshot()
    a = mgr.capture("a", SAMPLE_STATE)
    b = mgr.capture("b", SAMPLE_STATE_V2)

    diff = mgr.compare(a, b)
    assert diff is not None
    assert diff["identical"] is False
    assert "version" in diff["added"]  # New in b
    assert "agents" in diff["changed"] or "tasks" in diff["changed"]
    assert diff["total_diffs"] > 0

    # Nonexistent
    assert mgr.compare(a, "fake") is None
    print("OK: compare different")


def test_restore():
    """Restore snapshot data."""
    mgr = PipelineSnapshot()
    sid = mgr.capture("backup", SAMPLE_STATE)

    restored = mgr.restore(sid)
    assert restored is not None
    assert restored["tasks"] == 42

    assert mgr.restore("fake") is None
    print("OK: restore")


def test_update():
    """Update snapshot metadata."""
    mgr = PipelineSnapshot()
    sid = mgr.capture("old_name", {"x": 1})

    assert mgr.update(sid, name="new_name", description="updated",
                       tags={"new"}) is True
    snap = mgr.get(sid)
    assert snap["name"] == "new_name"
    assert snap["description"] == "updated"
    assert "new" in snap["tags"]

    assert mgr.update("fake") is False
    print("OK: update")


def test_delete():
    """Delete a snapshot."""
    mgr = PipelineSnapshot()
    sid = mgr.capture("temp", {"x": 1})

    assert mgr.delete(sid) is True
    assert mgr.get(sid) is None
    assert mgr.delete(sid) is False
    print("OK: delete")


def test_tag_untag():
    """Tag and untag."""
    mgr = PipelineSnapshot()
    sid = mgr.capture("test", {"x": 1})

    assert mgr.tag(sid, "important") is True
    assert "important" in mgr.get(sid)["tags"]

    assert mgr.untag(sid, "important") is True
    assert "important" not in mgr.get(sid)["tags"]

    assert mgr.untag(sid, "nonexistent") is False
    assert mgr.tag("fake", "x") is False
    assert mgr.untag("fake", "x") is False
    print("OK: tag untag")


def test_list_snapshots():
    """List with filters."""
    mgr = PipelineSnapshot()
    mgr.capture("daily", {"d": 1}, created_by="admin", tags={"auto"})
    mgr.capture("weekly", {"w": 1}, created_by="system")
    mgr.capture("daily", {"d": 2}, created_by="admin")

    all_snaps = mgr.list_snapshots()
    assert len(all_snaps) == 3

    by_name = mgr.list_snapshots(name="daily")
    assert len(by_name) == 2

    by_creator = mgr.list_snapshots(created_by="admin")
    assert len(by_creator) == 2

    by_tag = mgr.list_snapshots(tag="auto")
    assert len(by_tag) == 1

    limited = mgr.list_snapshots(limit=1)
    assert len(limited) == 1
    print("OK: list snapshots")


def test_search():
    """Search by name/description."""
    mgr = PipelineSnapshot()
    mgr.capture("Daily Backup", {"x": 1}, description="Automatic daily")
    mgr.capture("Manual Save", {"x": 2}, description="Before deploy")

    results = mgr.search("daily")
    assert len(results) == 1

    results = mgr.search("deploy")
    assert len(results) == 1
    print("OK: search")


def test_list_names():
    """List unique names."""
    mgr = PipelineSnapshot()
    mgr.capture("Beta", {"x": 1})
    mgr.capture("Alpha", {"x": 2})
    mgr.capture("Beta", {"x": 3})

    names = mgr.list_names()
    assert names == ["Alpha", "Beta"]
    print("OK: list names")


def test_list_tags():
    """List tags with counts."""
    mgr = PipelineSnapshot()
    mgr.capture("a", {"x": 1}, tags={"auto", "daily"})
    mgr.capture("b", {"x": 2}, tags={"auto"})

    tags = mgr.list_tags()
    assert tags["auto"] == 2
    assert tags["daily"] == 1
    print("OK: list tags")


def test_max_snapshots():
    """Enforce max snapshot limit."""
    mgr = PipelineSnapshot(max_snapshots=3)
    for i in range(6):
        mgr.capture(f"snap-{i}", {"i": i})

    assert len(mgr._snapshots) <= 3
    print("OK: max snapshots")


def test_stats():
    """Stats are accurate."""
    mgr = PipelineSnapshot()
    s1 = mgr.capture("a", SAMPLE_STATE)
    s2 = mgr.capture("b", SAMPLE_STATE_V2)
    mgr.compare(s1, s2)
    mgr.restore(s1)
    mgr.delete(s2)

    stats = mgr.get_stats()
    assert stats["total_created"] == 2
    assert stats["total_compared"] == 1
    assert stats["total_restored"] == 1
    assert stats["total_deleted"] == 1
    assert stats["total_snapshots"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    mgr = PipelineSnapshot()
    mgr.capture("test", {"x": 1})

    mgr.reset()
    assert mgr.list_snapshots() == []
    stats = mgr.get_stats()
    assert stats["total_snapshots"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Snapshot Tests ===\n")
    test_capture()
    test_get_data()
    test_get_by_name()
    test_get_latest()
    test_compare_identical()
    test_compare_different()
    test_restore()
    test_update()
    test_delete()
    test_tag_untag()
    test_list_snapshots()
    test_search()
    test_list_names()
    test_list_tags()
    test_max_snapshots()
    test_stats()
    test_reset()
    print("\n=== ALL 17 TESTS PASSED ===")


if __name__ == "__main__":
    main()
