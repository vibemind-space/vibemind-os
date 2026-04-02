"""Test pipeline feature toggle."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_feature_toggle import PipelineFeatureToggle


def test_create_toggle():
    """Create and retrieve toggle."""
    ft = PipelineFeatureToggle()
    tid = ft.create_toggle("dark_mode", enabled=True, tags=["ui"])
    assert tid.startswith("tgl-")

    t = ft.get_toggle(tid)
    assert t is not None
    assert t["name"] == "dark_mode"
    assert t["enabled"] is True

    assert ft.remove_toggle(tid) is True
    assert ft.remove_toggle(tid) is False
    print("OK: create toggle")


def test_invalid_toggle():
    """Invalid toggle rejected."""
    ft = PipelineFeatureToggle()
    assert ft.create_toggle("") == ""
    print("OK: invalid toggle")


def test_duplicate():
    """Duplicate name rejected."""
    ft = PipelineFeatureToggle()
    ft.create_toggle("feature1")
    assert ft.create_toggle("feature1") == ""
    print("OK: duplicate")


def test_max_toggles():
    """Max toggles enforced."""
    ft = PipelineFeatureToggle(max_toggles=2)
    ft.create_toggle("a")
    ft.create_toggle("b")
    assert ft.create_toggle("c") == ""
    print("OK: max toggles")


def test_enable_disable():
    """Enable and disable toggle."""
    ft = PipelineFeatureToggle()
    tid = ft.create_toggle("feature1", enabled=False)

    assert ft.enable_toggle(tid) is True
    assert ft.get_toggle(tid)["enabled"] is True
    assert ft.enable_toggle(tid) is False  # already enabled

    assert ft.disable_toggle(tid) is True
    assert ft.get_toggle(tid)["enabled"] is False
    assert ft.disable_toggle(tid) is False  # already disabled
    print("OK: enable disable")


def test_is_enabled():
    """Check if feature is enabled."""
    ft = PipelineFeatureToggle()
    ft.create_toggle("feature1", enabled=True)
    ft.create_toggle("feature2", enabled=False)

    assert ft.is_enabled("feature1") is True
    assert ft.is_enabled("feature2") is False
    assert ft.is_enabled("nonexistent") is False
    print("OK: is enabled")


def test_environment_filter():
    """Environment filtering."""
    ft = PipelineFeatureToggle()
    ft.create_toggle("feature1", enabled=True, environment="prod")

    assert ft.is_enabled("feature1", environment="prod") is True
    assert ft.is_enabled("feature1", environment="staging") is False
    assert ft.is_enabled("feature1") is True  # no env = pass
    print("OK: environment filter")


def test_rollout():
    """Rollout percentage."""
    ft = PipelineFeatureToggle()
    tid = ft.create_toggle("feature1", enabled=True, rollout_pct=100.0)
    assert ft.is_enabled("feature1") is True

    ft.set_rollout(tid, 0.0)
    assert ft.is_enabled("feature1") is False

    assert ft.set_rollout("nonexistent", 50.0) is False
    print("OK: rollout")


def test_get_by_name():
    """Get toggle by name."""
    ft = PipelineFeatureToggle()
    ft.create_toggle("my_feature")

    t = ft.get_toggle_by_name("my_feature")
    assert t is not None
    assert t["name"] == "my_feature"
    assert ft.get_toggle_by_name("nonexistent") is None
    print("OK: get by name")


def test_list_toggles():
    """List toggles with filters."""
    ft = PipelineFeatureToggle()
    ft.create_toggle("f1", enabled=True, environment="prod", tags=["ui"])
    ft.create_toggle("f2", enabled=False)

    all_t = ft.list_toggles()
    assert len(all_t) == 2

    by_enabled = ft.list_toggles(enabled=True)
    assert len(by_enabled) == 1

    by_env = ft.list_toggles(environment="prod")
    assert len(by_env) == 1

    by_tag = ft.list_toggles(tag="ui")
    assert len(by_tag) == 1
    print("OK: list toggles")


def test_check_count():
    """Check count tracked."""
    ft = PipelineFeatureToggle()
    ft.create_toggle("feature1", enabled=True)
    ft.is_enabled("feature1")
    ft.is_enabled("feature1")

    t = ft.get_toggle_by_name("feature1")
    assert t["total_checks"] == 2
    assert t["total_enabled_checks"] == 2
    print("OK: check count")


def test_callback():
    """Callback fires on events."""
    ft = PipelineFeatureToggle()
    fired = []
    ft.on_change("mon", lambda a, d: fired.append(a))

    tid = ft.create_toggle("f1")
    assert "toggle_created" in fired

    ft.enable_toggle(tid)
    assert "toggle_enabled" in fired

    ft.disable_toggle(tid)
    assert "toggle_disabled" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    ft = PipelineFeatureToggle()
    assert ft.on_change("mon", lambda a, d: None) is True
    assert ft.on_change("mon", lambda a, d: None) is False
    assert ft.remove_callback("mon") is True
    assert ft.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    ft = PipelineFeatureToggle()
    ft.create_toggle("f1", enabled=True)
    ft.create_toggle("f2", enabled=False)
    ft.is_enabled("f1")

    stats = ft.get_stats()
    assert stats["total_toggles"] == 2
    assert stats["total_checks"] == 1
    assert stats["enabled_count"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    ft = PipelineFeatureToggle()
    ft.create_toggle("f1")

    ft.reset()
    assert ft.list_toggles() == []
    stats = ft.get_stats()
    assert stats["current_toggles"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Feature Toggle Tests ===\n")
    test_create_toggle()
    test_invalid_toggle()
    test_duplicate()
    test_max_toggles()
    test_enable_disable()
    test_is_enabled()
    test_environment_filter()
    test_rollout()
    test_get_by_name()
    test_list_toggles()
    test_check_count()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 15 TESTS PASSED ===")


if __name__ == "__main__":
    main()
