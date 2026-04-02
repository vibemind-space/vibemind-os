"""Test config hot reload system."""
import asyncio
import json
import os
import sys
import tempfile
import time
sys.path.insert(0, ".")

from src.services.config_hot_reload import (
    ConfigHotReloader,
    ConfigSnapshot,
    ConfigChange,
    ConfigValidator,
    _hash_config,
    _diff_keys,
    _default_validator,
)


async def test_set_and_get_config():
    """Basic config set and get."""
    reloader = ConfigHotReloader()
    success, errors = reloader.set_config("agent_a", {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 4096,
        "temperature": 0.7,
    })

    assert success is True
    assert errors == []

    config = reloader.get_config("agent_a")
    assert config is not None
    assert config["model"] == "claude-sonnet-4-20250514"
    assert config["max_tokens"] == 4096
    print("OK: set and get config")


async def test_validation_failure():
    """Invalid config is rejected."""
    reloader = ConfigHotReloader()
    success, errors = reloader.set_config("agent_b", {
        "model": "",  # Invalid: empty string
        "max_tokens": -1,  # Invalid: negative
        "temperature": 5.0,  # Invalid: > 2.0
    })

    assert success is False
    assert len(errors) == 3
    print("OK: validation failure")


async def test_config_change_detection():
    """Config changes are detected and recorded."""
    reloader = ConfigHotReloader()
    reloader.set_config("agent_c", {"model": "claude-sonnet-4-20250514", "max_tokens": 4096, "temperature": 0.7})
    reloader.set_config("agent_c", {"model": "claude-sonnet-4-20250514", "max_tokens": 8192, "temperature": 0.5})

    history = reloader.get_change_history("agent_c")
    assert len(history) == 2
    # Second change should show changed keys
    assert "max_tokens" in history[1]["changed_keys"]
    assert "temperature" in history[1]["changed_keys"]
    print("OK: config change detection")


async def test_no_change_no_record():
    """Setting same config doesn't create a new change record."""
    reloader = ConfigHotReloader()
    config = {"model": "claude-sonnet-4-20250514", "max_tokens": 4096, "temperature": 0.7}
    reloader.set_config("agent_d", config)
    reloader.set_config("agent_d", config)  # Same config

    history = reloader.get_change_history("agent_d")
    assert len(history) == 1  # Only initial set
    print("OK: no change no record")


async def test_handler_notification():
    """Handlers are called on config change."""
    reloader = ConfigHotReloader()
    received = []

    def on_change(agent_name, config, changed_keys):
        received.append({
            "agent": agent_name,
            "config": config,
            "changed": changed_keys,
        })

    reloader.register_handler("agent_e", on_change)
    reloader.set_config("agent_e", {"model": "claude-sonnet-4-20250514", "max_tokens": 4096, "temperature": 0.7})

    assert len(received) == 1
    assert received[0]["agent"] == "agent_e"
    assert received[0]["config"]["model"] == "claude-sonnet-4-20250514"
    print("OK: handler notification")


async def test_file_based_reload():
    """Config loaded from JSON file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        reloader = ConfigHotReloader(config_dir=tmpdir)

        # Write config file
        config = {"model": "claude-sonnet-4-20250514", "max_tokens": 2048, "temperature": 0.3}
        config_path = os.path.join(tmpdir, "file_agent.json")
        with open(config_path, "w") as f:
            json.dump(config, f)

        result = reloader.reload("file_agent")
        assert result is True

        loaded = reloader.get_config("file_agent")
        assert loaded is not None
        assert loaded["max_tokens"] == 2048
        print("OK: file-based reload")


async def test_file_reload_missing():
    """Reload returns False for missing file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        reloader = ConfigHotReloader(config_dir=tmpdir)
        result = reloader.reload("nonexistent")
        assert result is False
        print("OK: file reload missing")


async def test_get_all_configs():
    """Get all configs returns all agents."""
    reloader = ConfigHotReloader()
    reloader.set_config("a1", {"model": "m1", "max_tokens": 100, "temperature": 0.5})
    reloader.set_config("a2", {"model": "m2", "max_tokens": 200, "temperature": 0.5})

    all_configs = reloader.get_all_configs()
    assert len(all_configs) == 2
    assert "a1" in all_configs
    assert "a2" in all_configs
    print("OK: get all configs")


async def test_config_hash():
    """Config hashing is deterministic."""
    config = {"b": 2, "a": 1}
    h1 = _hash_config(config)
    h2 = _hash_config({"a": 1, "b": 2})  # Same content, different order
    assert h1 == h2  # Sort keys makes it deterministic
    print("OK: config hash deterministic")


async def test_diff_keys():
    """Diff keys finds changed, added, removed keys."""
    old = {"a": 1, "b": 2, "c": 3}
    new = {"a": 1, "b": 99, "d": 4}  # b changed, c removed, d added

    changed = _diff_keys(old, new)
    assert "b" in changed
    assert "c" in changed  # Removed
    assert "d" in changed  # Added
    assert "a" not in changed  # Unchanged
    print("OK: diff keys")


async def test_validator_custom_rules():
    """Custom validation rules work."""
    v = ConfigValidator()
    v.add_rule("name", lambda x: len(x) <= 50, "name too long")
    v.add_rule("priority", lambda x: 0 <= x <= 10, "priority must be 0-10")

    errors = v.validate({"name": "ok", "priority": 5})
    assert len(errors) == 0

    errors2 = v.validate({"name": "x" * 100, "priority": 99})
    assert len(errors2) == 2
    print("OK: custom validation rules")


async def test_config_info():
    """Config info returns metadata."""
    reloader = ConfigHotReloader()
    reloader.set_config("info_agent", {"model": "test", "max_tokens": 100, "temperature": 0.5})

    info = reloader.get_config_info("info_agent")
    assert info is not None
    assert info["agent_name"] == "info_agent"
    assert info["valid"] is True
    assert "config_hash" in info

    none_info = reloader.get_config_info("nonexistent")
    assert none_info is None
    print("OK: config info")


async def test_stats():
    """Stats report correctly."""
    reloader = ConfigHotReloader()
    reloader.set_config("s1", {"model": "m", "max_tokens": 100, "temperature": 0.5})
    reloader.register_handler("s1", lambda *a: None)
    reloader.register_handler("s1", lambda *a: None)

    stats = reloader.get_stats()
    assert stats["total_agents_configured"] == 1
    assert stats["total_handlers_registered"] == 2
    assert stats["total_config_changes"] == 1
    assert "s1" in stats["agents"]
    print("OK: stats")


async def test_file_watcher_detects_change():
    """File watcher detects config file changes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        reloader = ConfigHotReloader(config_dir=tmpdir, poll_interval=0.1)

        # Write initial config
        config_path = os.path.join(tmpdir, "watched_agent.json")
        with open(config_path, "w") as f:
            json.dump({"model": "v1", "max_tokens": 100, "temperature": 0.5}, f)

        reloader.start()

        # Wait for initial scan
        await asyncio.sleep(0.3)

        # Modify the file
        with open(config_path, "w") as f:
            json.dump({"model": "v2", "max_tokens": 200, "temperature": 0.5}, f)

        # Wait for detection
        await asyncio.sleep(0.3)

        reloader.stop()

        config = reloader.get_config("watched_agent")
        assert config is not None
        assert config["model"] == "v2"
        assert config["max_tokens"] == 200
        print("OK: file watcher detects change")


async def test_snapshot_to_dict():
    """ConfigSnapshot serialization."""
    snap = ConfigSnapshot(
        agent_name="test",
        config={"model": "m"},
        config_hash="abc123def456",
        source_file="/tmp/test.json",
    )
    d = snap.to_dict()
    assert d["agent_name"] == "test"
    assert d["config_hash"] == "abc123def456"[:12]
    assert d["valid"] is True
    print("OK: snapshot to_dict")


async def test_change_to_dict():
    """ConfigChange serialization."""
    change = ConfigChange(
        agent_name="test",
        old_hash="old",
        new_hash="new",
        changed_keys=["model", "temperature"],
    )
    d = change.to_dict()
    assert d["agent_name"] == "test"
    assert d["changed_keys"] == ["model", "temperature"]
    assert d["applied"] is True
    assert d["rolled_back"] is False
    print("OK: change to_dict")


async def test_default_validator():
    """Default validator catches common errors."""
    v = _default_validator()

    # Valid config
    errors = v.validate({"model": "claude-sonnet-4-20250514", "max_tokens": 4096, "temperature": 0.7})
    assert len(errors) == 0

    # Various invalid fields
    errors = v.validate({"model": "", "max_tokens": 0, "temperature": -1.0, "timeout": -5})
    assert len(errors) == 4
    print("OK: default validator")


async def main():
    print("=== Config Hot Reload Tests ===\n")
    await test_set_and_get_config()
    await test_validation_failure()
    await test_config_change_detection()
    await test_no_change_no_record()
    await test_handler_notification()
    await test_file_based_reload()
    await test_file_reload_missing()
    await test_get_all_configs()
    await test_config_hash()
    await test_diff_keys()
    await test_validator_custom_rules()
    await test_config_info()
    await test_stats()
    await test_file_watcher_detects_change()
    await test_snapshot_to_dict()
    await test_change_to_dict()
    await test_default_validator()
    print("\n=== ALL 17 TESTS PASSED ===")


if __name__ == "__main__":
    asyncio.run(main())
