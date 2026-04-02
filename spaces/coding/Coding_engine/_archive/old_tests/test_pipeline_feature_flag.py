"""Test pipeline feature flag."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_feature_flag import PipelineFeatureFlag


def test_create():
    """Create and retrieve flag."""
    ff = PipelineFeatureFlag()
    fid = ff.create_flag("dark_mode", tags=["ui"])
    assert fid.startswith("flg-")

    f = ff.get_flag("dark_mode")
    assert f is not None
    assert f["name"] == "dark_mode"
    assert f["enabled"] is False
    assert f["rollout_pct"] == 100.0

    assert ff.remove_flag("dark_mode") is True
    assert ff.remove_flag("dark_mode") is False
    print("OK: create")


def test_invalid_create():
    """Invalid create rejected."""
    ff = PipelineFeatureFlag()
    assert ff.create_flag("") == ""
    print("OK: invalid create")


def test_duplicate():
    """Duplicate name rejected."""
    ff = PipelineFeatureFlag()
    ff.create_flag("f1")
    assert ff.create_flag("f1") == ""
    print("OK: duplicate")


def test_max_flags():
    """Max flags enforced."""
    ff = PipelineFeatureFlag(max_flags=2)
    ff.create_flag("a")
    ff.create_flag("b")
    assert ff.create_flag("c") == ""
    print("OK: max flags")


def test_enable_disable():
    """Enable and disable flag."""
    ff = PipelineFeatureFlag()
    ff.create_flag("f1")

    assert ff.enable_flag("f1") is True
    assert ff.get_flag("f1")["enabled"] is True

    assert ff.disable_flag("f1") is True
    assert ff.get_flag("f1")["enabled"] is False

    assert ff.enable_flag("nonexistent") is False
    assert ff.disable_flag("nonexistent") is False
    print("OK: enable disable")


def test_is_enabled_basic():
    """Basic is_enabled check."""
    ff = PipelineFeatureFlag()
    ff.create_flag("f1", enabled=True)
    ff.create_flag("f2", enabled=False)

    assert ff.is_enabled("f1") is True
    assert ff.is_enabled("f2") is False
    assert ff.is_enabled("nonexistent") is False
    print("OK: is enabled basic")


def test_environment_targeting():
    """Environment targeting works."""
    ff = PipelineFeatureFlag()
    ff.create_flag("f1", enabled=True, environments=["staging", "dev"])

    ff.set_environment("production")
    assert ff.is_enabled("f1") is False

    ff.set_environment("staging")
    assert ff.is_enabled("f1") is True
    print("OK: environment targeting")


def test_rollout_pct_zero():
    """Zero rollout disables flag."""
    ff = PipelineFeatureFlag()
    ff.create_flag("f1", enabled=True, rollout_pct=0.0)
    assert ff.is_enabled("f1") is False
    print("OK: rollout pct zero")


def test_rollout_pct_deterministic():
    """Rollout with user_id is deterministic."""
    ff = PipelineFeatureFlag()
    ff.create_flag("f1", enabled=True, rollout_pct=50.0)

    # Same user_id should give same result consistently
    results = [ff.is_enabled("f1", user_id="user123") for _ in range(10)]
    assert all(r == results[0] for r in results)
    print("OK: rollout pct deterministic")


def test_set_rollout():
    """Set rollout percentage."""
    ff = PipelineFeatureFlag()
    ff.create_flag("f1", enabled=True, rollout_pct=100.0)

    assert ff.set_rollout("f1", 50.0) is True
    assert ff.get_flag("f1")["rollout_pct"] == 50.0

    # Clamped
    ff.set_rollout("f1", 150.0)
    assert ff.get_flag("f1")["rollout_pct"] == 100.0

    ff.set_rollout("f1", -10.0)
    assert ff.get_flag("f1")["rollout_pct"] == 0.0

    assert ff.set_rollout("nonexistent", 50.0) is False
    print("OK: set rollout")


def test_set_environments():
    """Set environments."""
    ff = PipelineFeatureFlag()
    ff.create_flag("f1", enabled=True)

    assert ff.set_environments("f1", ["staging"]) is True
    assert ff.get_flag("f1")["environments"] == ["staging"]

    assert ff.set_environments("nonexistent", []) is False
    print("OK: set environments")


def test_evaluate_all():
    """Evaluate all flags."""
    ff = PipelineFeatureFlag()
    ff.create_flag("f1", enabled=True)
    ff.create_flag("f2", enabled=False)

    results = ff.evaluate_all()
    assert results["f1"] is True
    assert results["f2"] is False
    print("OK: evaluate all")


def test_list_flags():
    """List flags with filters."""
    ff = PipelineFeatureFlag()
    ff.create_flag("f1", enabled=True, tags=["ui"])
    ff.create_flag("f2", enabled=False)

    all_f = ff.list_flags()
    assert len(all_f) == 2

    enabled = ff.list_flags(enabled=True)
    assert len(enabled) == 1

    disabled = ff.list_flags(enabled=False)
    assert len(disabled) == 1

    by_tag = ff.list_flags(tag="ui")
    assert len(by_tag) == 1
    print("OK: list flags")


def test_enabled_count():
    """Enabled count is correct."""
    ff = PipelineFeatureFlag()
    ff.create_flag("f1", enabled=True)
    ff.create_flag("f2", enabled=True)
    ff.create_flag("f3", enabled=False)

    assert ff.get_enabled_count() == 2
    print("OK: enabled count")


def test_history():
    """History tracking."""
    ff = PipelineFeatureFlag()
    ff.create_flag("f1")
    ff.enable_flag("f1")
    ff.disable_flag("f1")

    hist = ff.get_history()
    assert len(hist) == 3  # created, enabled, disabled

    by_action = ff.get_history(action="enabled")
    assert len(by_action) == 1

    by_flag = ff.get_history(flag_name="f1")
    assert len(by_flag) == 3

    limited = ff.get_history(limit=1)
    assert len(limited) == 1
    print("OK: history")


def test_callback():
    """Callback fires on events."""
    ff = PipelineFeatureFlag()
    fired = []
    ff.on_change("mon", lambda a, d: fired.append(a))

    ff.create_flag("f1")
    assert "flag_created" in fired

    ff.enable_flag("f1")
    assert "flag_enabled" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    ff = PipelineFeatureFlag()
    assert ff.on_change("mon", lambda a, d: None) is True
    assert ff.on_change("mon", lambda a, d: None) is False
    assert ff.remove_callback("mon") is True
    assert ff.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    ff = PipelineFeatureFlag()
    ff.create_flag("f1", enabled=True)
    ff.create_flag("f2", enabled=False)
    ff.is_enabled("f1")

    stats = ff.get_stats()
    assert stats["current_flags"] == 2
    assert stats["enabled_flags"] == 1
    assert stats["disabled_flags"] == 1
    assert stats["total_created"] == 2
    assert stats["total_evaluations"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    ff = PipelineFeatureFlag()
    ff.create_flag("f1")

    ff.reset()
    assert ff.list_flags() == []
    stats = ff.get_stats()
    assert stats["current_flags"] == 0
    assert stats["total_created"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Feature Flag Tests ===\n")
    test_create()
    test_invalid_create()
    test_duplicate()
    test_max_flags()
    test_enable_disable()
    test_is_enabled_basic()
    test_environment_targeting()
    test_rollout_pct_zero()
    test_rollout_pct_deterministic()
    test_set_rollout()
    test_set_environments()
    test_evaluate_all()
    test_list_flags()
    test_enabled_count()
    test_history()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 19 TESTS PASSED ===")


if __name__ == "__main__":
    main()
