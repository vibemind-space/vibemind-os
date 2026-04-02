"""Test pipeline feature flag manager."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_feature_flag_manager import PipelineFeatureFlagManager


def test_create_flag():
    """Create and retrieve flag."""
    fm = PipelineFeatureFlagManager()
    fid = fm.create_flag("dark_mode", description="Enable dark mode",
                         enabled=True, rollout_percentage=50.0,
                         tags=["ui"])
    assert fid.startswith("ff-")

    f = fm.get_flag(fid)
    assert f is not None
    assert f["name"] == "dark_mode"
    assert f["enabled"] is True
    assert f["rollout_percentage"] == 50.0
    assert f["status"] == "active"

    assert fm.remove_flag(fid) is True
    assert fm.remove_flag(fid) is False
    print("OK: create flag")


def test_invalid_flag():
    """Invalid flag rejected."""
    fm = PipelineFeatureFlagManager()
    assert fm.create_flag("") == ""
    print("OK: invalid flag")


def test_duplicate_name():
    """Duplicate name rejected."""
    fm = PipelineFeatureFlagManager()
    fm.create_flag("feature_x")
    assert fm.create_flag("feature_x") == ""
    print("OK: duplicate name")


def test_max_flags():
    """Max flags enforced."""
    fm = PipelineFeatureFlagManager(max_flags=2)
    fm.create_flag("a")
    fm.create_flag("b")
    assert fm.create_flag("c") == ""
    print("OK: max flags")


def test_enable_disable():
    """Enable and disable flag."""
    fm = PipelineFeatureFlagManager()
    fid = fm.create_flag("test", enabled=False)

    assert fm.enable_flag(fid) is True
    assert fm.get_flag(fid)["enabled"] is True
    assert fm.enable_flag(fid) is False

    assert fm.disable_flag(fid) is True
    assert fm.get_flag(fid)["enabled"] is False
    assert fm.disable_flag(fid) is False
    print("OK: enable disable")


def test_archive():
    """Archive flag."""
    fm = PipelineFeatureFlagManager()
    fid = fm.create_flag("test")

    assert fm.archive_flag(fid) is True
    assert fm.get_flag(fid)["status"] == "archived"
    assert fm.archive_flag(fid) is False
    print("OK: archive")


def test_update_flag():
    """Update flag properties."""
    fm = PipelineFeatureFlagManager()
    fid = fm.create_flag("test", rollout_percentage=50)

    assert fm.update_flag(fid, description="Updated",
                          rollout_percentage=75.0) is True
    f = fm.get_flag(fid)
    assert f["description"] == "Updated"
    assert f["rollout_percentage"] == 75.0
    print("OK: update flag")


def test_evaluate_enabled():
    """Evaluate enabled flag at 100% rollout."""
    fm = PipelineFeatureFlagManager()
    fid = fm.create_flag("test", enabled=True, rollout_percentage=100)

    assert fm.evaluate(fid) is True
    assert fm.get_flag(fid)["evaluation_count"] == 1
    assert fm.get_flag(fid)["true_count"] == 1
    print("OK: evaluate enabled")


def test_evaluate_disabled():
    """Evaluate disabled flag."""
    fm = PipelineFeatureFlagManager()
    fid = fm.create_flag("test", enabled=False)

    assert fm.evaluate(fid) is False
    assert fm.get_flag(fid)["evaluation_count"] == 1
    assert fm.get_flag(fid)["true_count"] == 0
    print("OK: evaluate disabled")


def test_evaluate_by_name():
    """Evaluate flag by name."""
    fm = PipelineFeatureFlagManager()
    fm.create_flag("my_feature", enabled=True)

    assert fm.evaluate_by_name("my_feature") is True
    assert fm.evaluate_by_name("nonexistent") is False
    print("OK: evaluate by name")


def test_evaluate_archived():
    """Archived flag evaluates to false."""
    fm = PipelineFeatureFlagManager()
    fid = fm.create_flag("test", enabled=True)
    fm.archive_flag(fid)

    assert fm.evaluate(fid) is False
    print("OK: evaluate archived")


def test_search():
    """Search flags."""
    fm = PipelineFeatureFlagManager()
    f1 = fm.create_flag("a", enabled=True, tags=["ui"])
    f2 = fm.create_flag("b", enabled=False)
    fm.archive_flag(f2)

    all_f = fm.search()
    assert len(all_f) == 2

    active = fm.search(status="active")
    assert len(active) == 1

    enabled = fm.search(enabled=True)
    assert len(enabled) == 1

    by_tag = fm.search(tag="ui")
    assert len(by_tag) == 1
    print("OK: search")


def test_search_limit():
    """Search respects limit."""
    fm = PipelineFeatureFlagManager()
    for i in range(20):
        fm.create_flag(f"flag_{i}")

    results = fm.search(limit=5)
    assert len(results) == 5
    print("OK: search limit")


def test_get_by_name():
    """Get flag by name."""
    fm = PipelineFeatureFlagManager()
    fm.create_flag("my_flag")

    f = fm.get_flag_by_name("my_flag")
    assert f is not None
    assert f["name"] == "my_flag"

    assert fm.get_flag_by_name("nonexistent") is None
    print("OK: get by name")


def test_evaluation_stats():
    """Get evaluation stats."""
    fm = PipelineFeatureFlagManager()
    fid = fm.create_flag("test", enabled=True)
    fm.evaluate(fid)
    fm.evaluate(fid)

    stats = fm.get_evaluation_stats(fid)
    assert stats["total_evaluations"] == 2
    assert stats["true_count"] == 2
    assert stats["true_rate"] == 100.0
    print("OK: evaluation stats")


def test_callback():
    """Callback fires on flag create."""
    fm = PipelineFeatureFlagManager()
    fired = []
    fm.on_change("mon", lambda a, d: fired.append(a))

    fm.create_flag("test")
    assert "flag_created" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    fm = PipelineFeatureFlagManager()
    assert fm.on_change("mon", lambda a, d: None) is True
    assert fm.on_change("mon", lambda a, d: None) is False
    assert fm.remove_callback("mon") is True
    assert fm.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    fm = PipelineFeatureFlagManager()
    f1 = fm.create_flag("a", enabled=True)
    fm.create_flag("b", enabled=False)
    fm.evaluate(f1)

    stats = fm.get_stats()
    assert stats["total_flags_created"] == 2
    assert stats["total_evaluations"] == 1
    assert stats["current_flags"] == 2
    assert stats["enabled_flags"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    fm = PipelineFeatureFlagManager()
    fm.create_flag("test")

    fm.reset()
    assert fm.search() == []
    stats = fm.get_stats()
    assert stats["current_flags"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Feature Flag Manager Tests ===\n")
    test_create_flag()
    test_invalid_flag()
    test_duplicate_name()
    test_max_flags()
    test_enable_disable()
    test_archive()
    test_update_flag()
    test_evaluate_enabled()
    test_evaluate_disabled()
    test_evaluate_by_name()
    test_evaluate_archived()
    test_search()
    test_search_limit()
    test_get_by_name()
    test_evaluation_stats()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 19 TESTS PASSED ===")


if __name__ == "__main__":
    main()
