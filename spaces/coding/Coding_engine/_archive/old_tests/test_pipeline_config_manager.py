"""Test pipeline config manager."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_config_manager import PipelineConfigManager


def test_create_profile():
    """Create and remove profile."""
    cm = PipelineConfigManager()
    pid = cm.create_profile("prod_config", environment="production",
                            settings={"timeout": 30}, tags=["v2"])
    assert pid.startswith("cfg-")

    p = cm.get_profile(pid)
    assert p is not None
    assert p["name"] == "prod_config"
    assert p["environment"] == "production"
    assert p["settings"]["timeout"] == 30
    assert p["is_active"] is False

    assert cm.remove_profile(pid) is True
    assert cm.remove_profile(pid) is False
    print("OK: create profile")


def test_invalid_profile():
    """Invalid profile rejected."""
    cm = PipelineConfigManager()
    assert cm.create_profile("") == ""
    assert cm.create_profile("x", environment="invalid") == ""
    print("OK: invalid profile")


def test_max_profiles():
    """Max profiles enforced."""
    cm = PipelineConfigManager(max_profiles=2)
    cm.create_profile("a")
    cm.create_profile("b")
    assert cm.create_profile("c") == ""
    print("OK: max profiles")


def test_activate_profile():
    """Activate/deactivate profile."""
    cm = PipelineConfigManager()
    p1 = cm.create_profile("a", environment="production")
    p2 = cm.create_profile("b", environment="production")

    assert cm.activate_profile(p1) is True
    assert cm.get_profile(p1)["is_active"] is True
    assert cm.activate_profile(p1) is False  # already active

    # Activating p2 deactivates p1
    assert cm.activate_profile(p2) is True
    assert cm.get_profile(p1)["is_active"] is False
    assert cm.get_profile(p2)["is_active"] is True

    assert cm.deactivate_profile(p2) is True
    assert cm.deactivate_profile(p2) is False
    print("OK: activate profile")


def test_cant_remove_active():
    """Can't remove active profile."""
    cm = PipelineConfigManager()
    pid = cm.create_profile("x")
    cm.activate_profile(pid)
    assert cm.remove_profile(pid) is False
    print("OK: cant remove active")


def test_settings():
    """Set and get settings."""
    cm = PipelineConfigManager()
    pid = cm.create_profile("test")

    assert cm.set_setting(pid, "timeout", 30) is True
    assert cm.get_setting(pid, "timeout") == 30
    assert cm.get_setting(pid, "missing", "default") == "default"

    assert cm.remove_setting(pid, "timeout") is True
    assert cm.remove_setting(pid, "timeout") is False
    print("OK: settings")


def test_invalid_settings():
    """Invalid settings rejected."""
    cm = PipelineConfigManager()
    assert cm.set_setting("nonexistent", "key", "val") is False
    pid = cm.create_profile("x")
    assert cm.set_setting(pid, "", "val") is False
    print("OK: invalid settings")


def test_active_setting():
    """Get setting from active profile."""
    cm = PipelineConfigManager()
    pid = cm.create_profile("prod", environment="production",
                            settings={"timeout": 60})
    cm.activate_profile(pid)

    assert cm.get_active_setting("production", "timeout") == 60
    assert cm.get_active_setting("production", "missing", 0) == 0
    assert cm.get_active_setting("staging", "timeout", 0) == 0
    print("OK: active setting")


def test_overrides():
    """Runtime overrides."""
    cm = PipelineConfigManager()
    assert cm.set_override("debug", True) is True
    assert cm.get_override("debug") is True
    assert cm.get_override("missing", "default") == "default"
    assert cm.set_override("", "x") is False

    overrides = cm.list_overrides()
    assert "debug" in overrides

    assert cm.remove_override("debug") is True
    assert cm.remove_override("debug") is False
    print("OK: overrides")


def test_override_takes_precedence():
    """Override takes precedence over profile setting."""
    cm = PipelineConfigManager()
    pid = cm.create_profile("prod", environment="production",
                            settings={"timeout": 60})
    cm.activate_profile(pid)
    cm.set_override("production.timeout", 120)

    assert cm.get_active_setting("production", "timeout") == 120
    print("OK: override takes precedence")


def test_create_flag():
    """Create and manage feature flag."""
    cm = PipelineConfigManager()
    fid = cm.create_flag("dark_mode", enabled=False,
                         description="Enable dark mode")
    assert fid.startswith("flag-")

    f = cm.get_flag(fid)
    assert f is not None
    assert f["name"] == "dark_mode"
    assert f["enabled"] is False

    assert cm.is_enabled(fid) is False
    assert cm.toggle_flag(fid) is True
    assert cm.is_enabled(fid) is True

    assert cm.remove_flag(fid) is True
    assert cm.remove_flag(fid) is False
    print("OK: create flag")


def test_invalid_flag():
    """Invalid flag rejected."""
    cm = PipelineConfigManager()
    assert cm.create_flag("") == ""
    print("OK: invalid flag")


def test_max_flags():
    """Max flags enforced."""
    cm = PipelineConfigManager(max_flags=2)
    cm.create_flag("a")
    cm.create_flag("b")
    assert cm.create_flag("c") == ""
    print("OK: max flags")


def test_list_flags():
    """List flags with filter."""
    cm = PipelineConfigManager()
    f1 = cm.create_flag("a", enabled=True)
    f2 = cm.create_flag("b", enabled=False)

    all_f = cm.list_flags()
    assert len(all_f) == 2

    enabled = cm.list_flags(enabled_only=True)
    assert len(enabled) == 1
    print("OK: list flags")


def test_list_profiles():
    """List profiles with filters."""
    cm = PipelineConfigManager()
    p1 = cm.create_profile("a", environment="production", tags=["v1"])
    p2 = cm.create_profile("b", environment="staging")
    cm.activate_profile(p1)

    all_p = cm.list_profiles()
    assert len(all_p) == 2

    by_env = cm.list_profiles(environment="production")
    assert len(by_env) == 1

    by_tag = cm.list_profiles(tag="v1")
    assert len(by_tag) == 1

    active = cm.list_profiles(active_only=True)
    assert len(active) == 1
    print("OK: list profiles")


def test_active_profiles():
    """Get all active profiles."""
    cm = PipelineConfigManager()
    p1 = cm.create_profile("prod", environment="production")
    p2 = cm.create_profile("stage", environment="staging")
    cm.activate_profile(p1)
    cm.activate_profile(p2)

    active = cm.get_active_profiles()
    assert len(active) == 2
    print("OK: active profiles")


def test_profile_activated_callback():
    """Callback fires on profile activation."""
    cm = PipelineConfigManager()
    fired = []
    cm.on_change("mon", lambda a, d: fired.append(a))

    pid = cm.create_profile("x")
    cm.activate_profile(pid)
    assert "profile_activated" in fired
    print("OK: profile activated callback")


def test_setting_changed_callback():
    """Callback fires on setting change."""
    cm = PipelineConfigManager()
    fired = []
    cm.on_change("mon", lambda a, d: fired.append(a))

    pid = cm.create_profile("x")
    cm.set_setting(pid, "key", "val")
    assert "setting_changed" in fired
    print("OK: setting changed callback")


def test_callbacks():
    """Callback registration."""
    cm = PipelineConfigManager()
    assert cm.on_change("mon", lambda a, d: None) is True
    assert cm.on_change("mon", lambda a, d: None) is False
    assert cm.remove_callback("mon") is True
    assert cm.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    cm = PipelineConfigManager()
    pid = cm.create_profile("x")
    cm.set_setting(pid, "a", 1)
    cm.activate_profile(pid)
    fid = cm.create_flag("f", enabled=True)
    cm.set_override("key", "val")

    stats = cm.get_stats()
    assert stats["total_profiles_created"] == 1
    assert stats["total_flags_created"] == 1
    assert stats["total_config_changes"] >= 2  # setting + override
    assert stats["current_profiles"] == 1
    assert stats["active_profiles"] == 1
    assert stats["current_flags"] == 1
    assert stats["enabled_flags"] == 1
    assert stats["current_overrides"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    cm = PipelineConfigManager()
    cm.create_profile("x")
    cm.create_flag("f")
    cm.set_override("k", "v")

    cm.reset()
    assert cm.list_profiles() == []
    assert cm.list_flags() == []
    assert cm.list_overrides() == {}
    stats = cm.get_stats()
    assert stats["current_profiles"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Config Manager Tests ===\n")
    test_create_profile()
    test_invalid_profile()
    test_max_profiles()
    test_activate_profile()
    test_cant_remove_active()
    test_settings()
    test_invalid_settings()
    test_active_setting()
    test_overrides()
    test_override_takes_precedence()
    test_create_flag()
    test_invalid_flag()
    test_max_flags()
    test_list_flags()
    test_list_profiles()
    test_active_profiles()
    test_profile_activated_callback()
    test_setting_changed_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 21 TESTS PASSED ===")


if __name__ == "__main__":
    main()
