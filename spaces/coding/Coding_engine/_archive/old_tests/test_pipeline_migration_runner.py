"""Test pipeline migration runner."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_migration_runner import PipelineMigrationRunner


def test_register():
    """Register and retrieve migration."""
    mr = PipelineMigrationRunner()
    mid = mr.register(1, "add_users_table", tags=["schema"])
    assert mid.startswith("mig-")

    m = mr.get_migration(mid)
    assert m is not None
    assert m["version"] == 1
    assert m["name"] == "add_users_table"
    assert m["status"] == "pending"

    assert mr.remove_migration(mid) is True
    assert mr.remove_migration(mid) is False
    print("OK: register")


def test_invalid_register():
    """Invalid register rejected."""
    mr = PipelineMigrationRunner()
    assert mr.register(0, "name") == ""
    assert mr.register(-1, "name") == ""
    assert mr.register(1, "") == ""
    print("OK: invalid register")


def test_duplicate_version():
    """Duplicate version rejected."""
    mr = PipelineMigrationRunner()
    mr.register(1, "first")
    assert mr.register(1, "second") == ""
    print("OK: duplicate version")


def test_duplicate_name():
    """Duplicate name rejected."""
    mr = PipelineMigrationRunner()
    mr.register(1, "migration_a")
    assert mr.register(2, "migration_a") == ""
    print("OK: duplicate name")


def test_max_migrations():
    """Max migrations enforced."""
    mr = PipelineMigrationRunner(max_migrations=2)
    mr.register(1, "a")
    mr.register(2, "b")
    assert mr.register(3, "c") == ""
    print("OK: max migrations")


def test_get_by_version():
    """Get migration by version."""
    mr = PipelineMigrationRunner()
    mr.register(1, "first")
    assert mr.get_by_version(1) is not None
    assert mr.get_by_version(99) is None
    print("OK: get by version")


def test_get_by_name():
    """Get migration by name."""
    mr = PipelineMigrationRunner()
    mr.register(1, "first")
    assert mr.get_by_name("first") is not None
    assert mr.get_by_name("nonexistent") is None
    print("OK: get by name")


def test_migrate_up():
    """Migrate up applies pending."""
    mr = PipelineMigrationRunner()
    state = []
    mr.register(1, "m1", up_fn=lambda: state.append("m1"))
    mr.register(2, "m2", up_fn=lambda: state.append("m2"))

    result = mr.migrate_up()
    assert result["applied"] == [1, 2]
    assert result["current_version"] == 2
    assert state == ["m1", "m2"]
    assert mr.get_current_version() == 2
    print("OK: migrate up")


def test_migrate_up_partial():
    """Migrate up to specific version."""
    mr = PipelineMigrationRunner()
    mr.register(1, "m1", up_fn=lambda: None)
    mr.register(2, "m2", up_fn=lambda: None)
    mr.register(3, "m3", up_fn=lambda: None)

    result = mr.migrate_up(target_version=2)
    assert result["applied"] == [1, 2]
    assert result["current_version"] == 2
    print("OK: migrate up partial")


def test_migrate_up_no_fn():
    """Migrate up without function just marks applied."""
    mr = PipelineMigrationRunner()
    mr.register(1, "m1")  # no up_fn

    result = mr.migrate_up()
    assert result["applied"] == [1]
    assert mr.get_by_version(1)["status"] == "applied"
    print("OK: migrate up no fn")


def test_migrate_up_failure():
    """Migration failure stops further migrations."""
    mr = PipelineMigrationRunner()
    mr.register(1, "m1", up_fn=lambda: None)
    mr.register(2, "m2", up_fn=lambda: (_ for _ in ()).throw(RuntimeError("fail")))
    mr.register(3, "m3", up_fn=lambda: None)

    result = mr.migrate_up()
    assert 1 in result["applied"]
    assert 2 in result["failed"]
    assert 3 not in result["applied"]
    assert mr.get_current_version() == 1
    print("OK: migrate up failure")


def test_migrate_down():
    """Migrate down rolls back."""
    mr = PipelineMigrationRunner()
    state = {"v": 0}
    mr.register(1, "m1", up_fn=lambda: None, down_fn=lambda: state.update(v=0))
    mr.register(2, "m2", up_fn=lambda: None, down_fn=lambda: state.update(v=1))

    mr.migrate_up()
    result = mr.migrate_down(target_version=0)
    assert result["rolled_back"] == [2, 1]
    assert result["current_version"] == 0
    print("OK: migrate down")


def test_migrate_down_partial():
    """Migrate down to specific version."""
    mr = PipelineMigrationRunner()
    mr.register(1, "m1", up_fn=lambda: None, down_fn=lambda: None)
    mr.register(2, "m2", up_fn=lambda: None, down_fn=lambda: None)
    mr.register(3, "m3", up_fn=lambda: None, down_fn=lambda: None)

    mr.migrate_up()
    result = mr.migrate_down(target_version=1)
    assert result["rolled_back"] == [3, 2]
    assert result["current_version"] == 1
    print("OK: migrate down partial")


def test_get_pending():
    """Get pending migrations."""
    mr = PipelineMigrationRunner()
    mr.register(1, "m1", up_fn=lambda: None)
    mr.register(2, "m2", up_fn=lambda: None)

    pending = mr.get_pending()
    assert len(pending) == 2

    mr.migrate_up(target_version=1)
    pending = mr.get_pending()
    assert len(pending) == 1
    assert pending[0]["version"] == 2
    print("OK: get pending")


def test_list_migrations():
    """List migrations with filters."""
    mr = PipelineMigrationRunner()
    mr.register(1, "m1", up_fn=lambda: None, tags=["schema"])
    mr.register(2, "m2")
    mr.migrate_up(target_version=1)

    all_m = mr.list_migrations()
    assert len(all_m) == 2

    applied = mr.list_migrations(status="applied")
    assert len(applied) == 1

    by_tag = mr.list_migrations(tag="schema")
    assert len(by_tag) == 1
    print("OK: list migrations")


def test_history():
    """History tracking."""
    mr = PipelineMigrationRunner()
    mr.register(1, "m1", up_fn=lambda: None, down_fn=lambda: None)
    mr.migrate_up()
    mr.migrate_down()

    hist = mr.get_history()
    assert len(hist) == 2

    applied = mr.get_history(action="applied")
    assert len(applied) == 1

    rolled = mr.get_history(action="rolled_back")
    assert len(rolled) == 1

    limited = mr.get_history(limit=1)
    assert len(limited) == 1
    print("OK: history")


def test_callback():
    """Callback fires on events."""
    mr = PipelineMigrationRunner()
    fired = []
    mr.on_change("mon", lambda a, d: fired.append(a))

    mr.register(1, "m1", up_fn=lambda: None)
    assert "migration_registered" in fired

    mr.migrate_up()
    assert "migration_applied" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    mr = PipelineMigrationRunner()
    assert mr.on_change("mon", lambda a, d: None) is True
    assert mr.on_change("mon", lambda a, d: None) is False
    assert mr.remove_callback("mon") is True
    assert mr.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    mr = PipelineMigrationRunner()
    mr.register(1, "m1", up_fn=lambda: None)
    mr.register(2, "m2")
    mr.migrate_up(target_version=1)

    stats = mr.get_stats()
    assert stats["total_migrations"] == 2
    assert stats["total_registered"] == 2
    assert stats["total_applied"] == 1
    assert stats["pending_count"] == 1
    assert stats["current_version"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    mr = PipelineMigrationRunner()
    mr.register(1, "m1")

    mr.reset()
    assert mr.list_migrations() == []
    stats = mr.get_stats()
    assert stats["total_migrations"] == 0
    assert stats["current_version"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Migration Runner Tests ===\n")
    test_register()
    test_invalid_register()
    test_duplicate_version()
    test_duplicate_name()
    test_max_migrations()
    test_get_by_version()
    test_get_by_name()
    test_migrate_up()
    test_migrate_up_partial()
    test_migrate_up_no_fn()
    test_migrate_up_failure()
    test_migrate_down()
    test_migrate_down_partial()
    test_get_pending()
    test_list_migrations()
    test_history()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 20 TESTS PASSED ===")


if __name__ == "__main__":
    main()
