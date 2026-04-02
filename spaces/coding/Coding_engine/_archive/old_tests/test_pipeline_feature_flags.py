"""Test pipeline feature flags."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_feature_flags import PipelineFeatureFlags


def test_create_flag():
    """Create and remove flags."""
    ff = PipelineFeatureFlags()
    fid = ff.create_flag("dark_mode", "Enable dark mode")
    assert fid.startswith("flag-")

    f = ff.get_flag(fid)
    assert f is not None
    assert f["name"] == "dark_mode"
    assert f["enabled"] is False
    assert f["rollout_percentage"] == 100.0

    assert ff.remove_flag(fid) is True
    assert ff.remove_flag(fid) is False
    print("OK: create flag")


def test_duplicate_name():
    """Duplicate flag names rejected."""
    ff = PipelineFeatureFlags()
    ff.create_flag("dark_mode")
    assert ff.create_flag("dark_mode") == ""
    print("OK: duplicate name")


def test_invalid_params():
    """Invalid params rejected."""
    ff = PipelineFeatureFlags()
    assert ff.create_flag("") == ""
    assert ff.create_flag("x", rollout_percentage=-1) == ""
    assert ff.create_flag("x", rollout_percentage=101) == ""
    print("OK: invalid params")


def test_get_by_name():
    """Get flag by name."""
    ff = PipelineFeatureFlags()
    fid = ff.create_flag("dark_mode")

    f = ff.get_flag_by_name("dark_mode")
    assert f is not None
    assert f["flag_id"] == fid

    assert ff.get_flag_by_name("nonexistent") is None
    print("OK: get by name")


def test_enable_disable():
    """Enable and disable flags."""
    ff = PipelineFeatureFlags()
    fid = ff.create_flag("feature")

    assert ff.enable_flag(fid) is True
    assert ff.get_flag(fid)["enabled"] is True

    assert ff.disable_flag(fid) is True
    assert ff.get_flag(fid)["enabled"] is False

    assert ff.enable_flag("nonexistent") is False
    print("OK: enable disable")


def test_set_rollout():
    """Set rollout percentage."""
    ff = PipelineFeatureFlags()
    fid = ff.create_flag("feature")

    assert ff.set_rollout(fid, 50.0) is True
    assert ff.get_flag(fid)["rollout_percentage"] == 50.0

    assert ff.set_rollout(fid, -1) is False
    assert ff.set_rollout(fid, 101) is False
    print("OK: set rollout")


def test_tags():
    """Add and remove tags."""
    ff = PipelineFeatureFlags()
    fid = ff.create_flag("feature", tags=["beta"])

    assert ff.add_tag(fid, "experimental") is True
    assert ff.add_tag(fid, "beta") is False  # Duplicate

    f = ff.get_flag(fid)
    assert "beta" in f["tags"]
    assert "experimental" in f["tags"]

    assert ff.remove_tag(fid, "beta") is True
    assert ff.remove_tag(fid, "beta") is False
    print("OK: tags")


def test_list_flags():
    """List flags with filters."""
    ff = PipelineFeatureFlags()
    f1 = ff.create_flag("a", enabled=True, tags=["beta"])
    f2 = ff.create_flag("b", enabled=False)
    f3 = ff.create_flag("c", enabled=True, tags=["beta"])

    all_f = ff.list_flags()
    assert len(all_f) == 3

    enabled = ff.list_flags(enabled_only=True)
    assert len(enabled) == 2

    tagged = ff.list_flags(tag="beta")
    assert len(tagged) == 2
    print("OK: list flags")


def test_basic_check():
    """Basic flag checking."""
    ff = PipelineFeatureFlags()
    fid = ff.create_flag("feature", enabled=True)

    assert ff.check(fid) is True
    ff.disable_flag(fid)
    assert ff.check(fid) is False
    print("OK: basic check")


def test_check_by_name():
    """Check by flag name."""
    ff = PipelineFeatureFlags()
    ff.create_flag("feature", enabled=True)

    assert ff.check_by_name("feature") is True
    assert ff.check_by_name("nonexistent") is False
    print("OK: check by name")


def test_check_all():
    """Check all flags."""
    ff = PipelineFeatureFlags()
    ff.create_flag("a", enabled=True)
    ff.create_flag("b", enabled=False)

    results = ff.check_all()
    assert results["a"] is True
    assert results["b"] is False
    print("OK: check all")


def test_targeting_rules():
    """Targeting rules filter checks."""
    ff = PipelineFeatureFlags()
    fid = ff.create_flag("premium", enabled=True)
    ff.add_rule(fid, "plan", "eq", "premium")

    assert ff.check(fid, {"key": "user1", "plan": "premium"}) is True
    assert ff.check(fid, {"key": "user2", "plan": "free"}) is False
    assert ff.check(fid, {"key": "user3"}) is False  # Missing attribute
    print("OK: targeting rules")


def test_multiple_rules():
    """All rules must match."""
    ff = PipelineFeatureFlags()
    fid = ff.create_flag("feature", enabled=True)
    ff.add_rule(fid, "plan", "eq", "premium")
    ff.add_rule(fid, "age", "gte", 18)

    assert ff.check(fid, {"key": "u1", "plan": "premium", "age": 25}) is True
    assert ff.check(fid, {"key": "u2", "plan": "premium", "age": 16}) is False
    assert ff.check(fid, {"key": "u3", "plan": "free", "age": 25}) is False
    print("OK: multiple rules")


def test_rule_operators():
    """Various rule operators work."""
    ff = PipelineFeatureFlags()

    # in operator
    fid = ff.create_flag("in_test", enabled=True)
    ff.add_rule(fid, "country", "in", ["US", "UK", "DE"])
    assert ff.check(fid, {"key": "u1", "country": "US"}) is True
    assert ff.check(fid, {"key": "u2", "country": "FR"}) is False

    # contains operator
    fid2 = ff.create_flag("contains_test", enabled=True)
    ff.add_rule(fid2, "email", "contains", "@company.com")
    assert ff.check(fid2, {"key": "u1", "email": "user@company.com"}) is True
    assert ff.check(fid2, {"key": "u2", "email": "user@other.com"}) is False

    # neq operator
    fid3 = ff.create_flag("neq_test", enabled=True)
    ff.add_rule(fid3, "status", "neq", "banned")
    assert ff.check(fid3, {"key": "u1", "status": "active"}) is True
    assert ff.check(fid3, {"key": "u2", "status": "banned"}) is False
    print("OK: rule operators")


def test_invalid_rule():
    """Invalid rule rejected."""
    ff = PipelineFeatureFlags()
    fid = ff.create_flag("feature")
    assert ff.add_rule(fid, "x", "invalid_op", 1) is False
    assert ff.add_rule("nonexistent", "x", "eq", 1) is False
    print("OK: invalid rule")


def test_clear_rules():
    """Clear all rules."""
    ff = PipelineFeatureFlags()
    fid = ff.create_flag("feature", enabled=True)
    ff.add_rule(fid, "a", "eq", 1)
    ff.add_rule(fid, "b", "eq", 2)

    assert ff.clear_rules(fid) == 2
    assert ff.get_flag(fid)["rule_count"] == 0
    print("OK: clear rules")


def test_overrides():
    """Per-context overrides."""
    ff = PipelineFeatureFlags()
    fid = ff.create_flag("feature", enabled=False)

    assert ff.set_override(fid, "vip_user", True) is True
    assert ff.check(fid, {"key": "vip_user"}) is True
    assert ff.check(fid, {"key": "normal_user"}) is False

    overrides = ff.list_overrides(fid)
    assert overrides["vip_user"] is True

    assert ff.remove_override(fid, "vip_user") is True
    assert ff.remove_override(fid, "vip_user") is False
    print("OK: overrides")


def test_rollout_percentage():
    """Rollout percentage filters deterministically."""
    ff = PipelineFeatureFlags()
    fid = ff.create_flag("feature", enabled=True, rollout_percentage=50.0)

    # Deterministic based on hash, some will pass, some won't
    results = [ff.check(fid, {"key": f"user_{i}"}) for i in range(100)]
    true_count = sum(results)
    # Should be roughly 50%, but deterministic
    assert 20 < true_count < 80
    print("OK: rollout percentage")


def test_check_log():
    """Check log recorded."""
    ff = PipelineFeatureFlags()
    fid = ff.create_flag("feature", enabled=True)

    ff.check(fid, {"key": "u1"})
    ff.check(fid, {"key": "u2"})

    log = ff.get_check_log(flag_id=fid)
    assert len(log) == 2
    assert log[0]["result"] is True
    print("OK: check log")


def test_callbacks():
    """Callbacks fire on changes."""
    ff = PipelineFeatureFlags()

    fired = []
    assert ff.on_change("mon", lambda a, fid: fired.append(a)) is True
    assert ff.on_change("mon", lambda a, f: None) is False

    fid = ff.create_flag("feature")
    assert "created" in fired

    ff.enable_flag(fid)
    assert "enabled" in fired

    ff.disable_flag(fid)
    assert "disabled" in fired

    assert ff.remove_callback("mon") is True
    assert ff.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    ff = PipelineFeatureFlags()
    fid = ff.create_flag("feature", enabled=True)
    ff.add_rule(fid, "x", "eq", 1)
    ff.set_override(fid, "user1", True)

    ff.check(fid, {"key": "u1", "x": 1})
    ff.check(fid, {"key": "u2", "x": 2})

    stats = ff.get_stats()
    assert stats["total_created"] == 1
    assert stats["total_flags"] == 1
    assert stats["enabled_flags"] == 1
    assert stats["total_checks"] == 2
    assert stats["total_rules"] == 1
    assert stats["total_overrides"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    ff = PipelineFeatureFlags()
    ff.create_flag("feature")
    ff.on_change("x", lambda a, f: None)

    ff.reset()
    assert ff.list_flags() == []
    stats = ff.get_stats()
    assert stats["total_flags"] == 0
    print("OK: reset")


def test_max_flags():
    """Max flags enforced."""
    ff = PipelineFeatureFlags(max_flags=2)
    ff.create_flag("a")
    ff.create_flag("b")
    assert ff.create_flag("c") == ""
    print("OK: max flags")


def main():
    print("=== Pipeline Feature Flags Tests ===\n")
    test_create_flag()
    test_duplicate_name()
    test_invalid_params()
    test_get_by_name()
    test_enable_disable()
    test_set_rollout()
    test_tags()
    test_list_flags()
    test_basic_check()
    test_check_by_name()
    test_check_all()
    test_targeting_rules()
    test_multiple_rules()
    test_rule_operators()
    test_invalid_rule()
    test_clear_rules()
    test_overrides()
    test_rollout_percentage()
    test_check_log()
    test_callbacks()
    test_stats()
    test_reset()
    test_max_flags()
    print("\n=== ALL 23 TESTS PASSED ===")


if __name__ == "__main__":
    main()
