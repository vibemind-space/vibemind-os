"""Test pipeline feature gate."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_feature_gate import PipelineFeatureGate


def test_create_flag():
    """Create and retrieve flag."""
    fg = PipelineFeatureGate()
    fid = fg.create_flag("dark_mode", enabled=True, tags=["ui"])
    assert fid.startswith("ffg-")

    f = fg.get_flag(fid)
    assert f is not None
    assert f["name"] == "dark_mode"
    assert f["enabled"] is True

    assert fg.remove_flag(fid) is True
    assert fg.remove_flag(fid) is False
    print("OK: create flag")


def test_invalid_create():
    """Invalid create rejected."""
    fg = PipelineFeatureGate()
    assert fg.create_flag("") == ""
    print("OK: invalid create")


def test_duplicate():
    """Duplicate name rejected."""
    fg = PipelineFeatureGate()
    fg.create_flag("f1")
    assert fg.create_flag("f1") == ""
    print("OK: duplicate")


def test_max_flags():
    """Max flags enforced."""
    fg = PipelineFeatureGate(max_flags=2)
    fg.create_flag("a")
    fg.create_flag("b")
    assert fg.create_flag("c") == ""
    print("OK: max flags")


def test_get_by_name():
    """Get flag by name."""
    fg = PipelineFeatureGate()
    fg.create_flag("dark_mode", enabled=True)

    f = fg.get_by_name("dark_mode")
    assert f is not None
    assert fg.get_by_name("nonexistent") is None
    print("OK: get by name")


def test_enable_disable():
    """Enable and disable flag."""
    fg = PipelineFeatureGate()
    fid = fg.create_flag("feature", enabled=False)

    assert fg.enable_flag(fid) is True
    assert fg.enable_flag(fid) is False  # already enabled
    assert fg.get_flag(fid)["enabled"] is True

    assert fg.disable_flag(fid) is True
    assert fg.disable_flag(fid) is False  # already disabled
    assert fg.get_flag(fid)["enabled"] is False
    print("OK: enable disable")


def test_is_enabled_basic():
    """Basic is_enabled check."""
    fg = PipelineFeatureGate()
    fg.create_flag("feature_on", enabled=True)
    fg.create_flag("feature_off", enabled=False)

    assert fg.is_enabled("feature_on") is True
    assert fg.is_enabled("feature_off") is False
    assert fg.is_enabled("nonexistent") is False
    print("OK: is enabled basic")


def test_blocked_agents():
    """Blocked agents are denied."""
    fg = PipelineFeatureGate()
    fg.create_flag("feature", enabled=True, blocked_agents=["bad_agent"])

    assert fg.is_enabled("feature", agent="good_agent") is True
    assert fg.is_enabled("feature", agent="bad_agent") is False
    print("OK: blocked agents")


def test_allowed_agents():
    """Only allowed agents pass."""
    fg = PipelineFeatureGate()
    fg.create_flag("feature", enabled=True, allowed_agents=["vip_agent"])

    assert fg.is_enabled("feature", agent="vip_agent") is True
    assert fg.is_enabled("feature", agent="other_agent") is False
    print("OK: allowed agents")


def test_rollout_pct():
    """Rollout percentage is deterministic per agent."""
    fg = PipelineFeatureGate()
    fg.create_flag("gradual", enabled=True, rollout_pct=50.0)

    # Same agent should always get same result
    r1 = fg.is_enabled("gradual", agent="worker1")
    r2 = fg.is_enabled("gradual", agent="worker1")
    assert r1 == r2  # deterministic

    # 0% should reject all
    fg.create_flag("zero", enabled=True, rollout_pct=0.0)
    assert fg.is_enabled("zero", agent="worker1") is False

    # 100% should accept all
    fg.create_flag("full", enabled=True, rollout_pct=100.0)
    assert fg.is_enabled("full", agent="worker1") is True
    print("OK: rollout pct")


def test_set_rollout_pct():
    """Set rollout percentage."""
    fg = PipelineFeatureGate()
    fid = fg.create_flag("feature", enabled=True)

    assert fg.set_rollout_pct(fid, 50.0) is True
    assert fg.get_flag(fid)["rollout_pct"] == 50.0

    # Clamped to 0-100
    fg.set_rollout_pct(fid, 150.0)
    assert fg.get_flag(fid)["rollout_pct"] == 100.0

    fg.set_rollout_pct(fid, -10.0)
    assert fg.get_flag(fid)["rollout_pct"] == 0.0

    assert fg.set_rollout_pct("nonexistent", 50.0) is False
    print("OK: set rollout pct")


def test_check_all():
    """Check all flags for agent."""
    fg = PipelineFeatureGate()
    fg.create_flag("a", enabled=True)
    fg.create_flag("b", enabled=False)

    results = fg.check_all()
    assert results["a"] is True
    assert results["b"] is False
    print("OK: check all")


def test_flag_stats():
    """Flag check stats updated."""
    fg = PipelineFeatureGate()
    fg.create_flag("feature", enabled=True)

    fg.is_enabled("feature", agent="w1")
    fg.is_enabled("feature", agent="w2")

    f = fg.get_by_name("feature")
    assert f["total_checks"] == 2
    assert f["total_enabled"] == 2
    print("OK: flag stats")


def test_list_flags():
    """List flags with filters."""
    fg = PipelineFeatureGate()
    fg.create_flag("a", enabled=True, tags=["ui"])
    fg.create_flag("b", enabled=False)

    all_f = fg.list_flags()
    assert len(all_f) == 2

    enabled = fg.list_flags(enabled=True)
    assert len(enabled) == 1

    by_tag = fg.list_flags(tag="ui")
    assert len(by_tag) == 1
    print("OK: list flags")


def test_get_enabled_flags():
    """Get list of enabled flag names."""
    fg = PipelineFeatureGate()
    fg.create_flag("a", enabled=True)
    fg.create_flag("b", enabled=False)
    fg.create_flag("c", enabled=True)

    enabled = fg.get_enabled_flags()
    assert "a" in enabled
    assert "c" in enabled
    assert "b" not in enabled
    print("OK: get enabled flags")


def test_history():
    """Check history."""
    fg = PipelineFeatureGate()
    fg.create_flag("feature", enabled=True)

    fg.is_enabled("feature", agent="w1")
    fg.is_enabled("feature", agent="w2")

    hist = fg.get_history()
    assert len(hist) == 2

    by_agent = fg.get_history(agent="w1")
    assert len(by_agent) == 1

    by_name = fg.get_history(name="feature")
    assert len(by_name) == 2

    limited = fg.get_history(limit=1)
    assert len(limited) == 1
    print("OK: history")


def test_callback():
    """Callback fires on events."""
    fg = PipelineFeatureGate()
    fired = []
    fg.on_change("mon", lambda a, d: fired.append(a))

    fid = fg.create_flag("feature")
    assert "flag_created" in fired

    fg.enable_flag(fid)
    assert "flag_enabled" in fired

    fg.disable_flag(fid)
    assert "flag_disabled" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    fg = PipelineFeatureGate()
    assert fg.on_change("mon", lambda a, d: None) is True
    assert fg.on_change("mon", lambda a, d: None) is False
    assert fg.remove_callback("mon") is True
    assert fg.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    fg = PipelineFeatureGate()
    fg.create_flag("a", enabled=True)
    fg.create_flag("b", enabled=False)
    fg.is_enabled("a")

    stats = fg.get_stats()
    assert stats["current_flags"] == 2
    assert stats["enabled_flags"] == 1
    assert stats["total_created"] == 2
    assert stats["total_checks"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    fg = PipelineFeatureGate()
    fg.create_flag("a")

    fg.reset()
    assert fg.list_flags() == []
    stats = fg.get_stats()
    assert stats["current_flags"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Feature Gate Tests ===\n")
    test_create_flag()
    test_invalid_create()
    test_duplicate()
    test_max_flags()
    test_get_by_name()
    test_enable_disable()
    test_is_enabled_basic()
    test_blocked_agents()
    test_allowed_agents()
    test_rollout_pct()
    test_set_rollout_pct()
    test_check_all()
    test_flag_stats()
    test_list_flags()
    test_get_enabled_flags()
    test_history()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 20 TESTS PASSED ===")


if __name__ == "__main__":
    main()
