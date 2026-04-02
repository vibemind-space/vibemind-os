"""Test pipeline warmup controller."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_warmup_controller import PipelineWarmupController


def test_register_component():
    """Register and retrieve component."""
    wc = PipelineWarmupController()
    eid = wc.register_component("database", order=1, tags=["core"])
    assert eid.startswith("wrm-")

    c = wc.get_component(eid)
    assert c is not None
    assert c["component"] == "database"
    assert c["status"] == "pending"
    assert c["order"] == 1
    assert "core" in c["tags"]

    assert wc.remove_component(eid) is True
    assert wc.remove_component(eid) is False
    print("OK: register component")


def test_invalid_register():
    """Invalid registration rejected."""
    wc = PipelineWarmupController()
    assert wc.register_component("") == ""
    print("OK: invalid register")


def test_duplicate():
    """Duplicate name rejected."""
    wc = PipelineWarmupController()
    wc.register_component("db")
    assert wc.register_component("db") == ""
    print("OK: duplicate")


def test_max_entries():
    """Max entries enforced."""
    wc = PipelineWarmupController(max_entries=2)
    wc.register_component("a")
    wc.register_component("b")
    assert wc.register_component("c") == ""
    print("OK: max entries")


def test_get_by_name():
    """Get component by name."""
    wc = PipelineWarmupController()
    wc.register_component("cache")

    c = wc.get_by_name("cache")
    assert c is not None
    assert c["component"] == "cache"
    assert wc.get_by_name("nonexistent") is None
    print("OK: get by name")


def test_warmup():
    """Warmup a component."""
    wc = PipelineWarmupController()
    eid = wc.register_component("db")

    assert wc.warmup(eid) is True
    c = wc.get_component(eid)
    assert c["status"] == "ready"
    assert c["total_warmups"] == 1
    assert c["last_warmup_at"] > 0

    # already ready
    assert wc.warmup(eid) is False
    print("OK: warmup")


def test_warmup_with_fn():
    """Warmup with warmup function."""
    called = []
    wc = PipelineWarmupController()
    eid = wc.register_component("db", warmup_fn=lambda: called.append(1))

    assert wc.warmup(eid) is True
    assert len(called) == 1
    assert wc.get_component(eid)["status"] == "ready"
    print("OK: warmup with fn")


def test_warmup_fn_failure():
    """Warmup function failure sets failed status."""
    def bad_fn():
        raise RuntimeError("fail")

    wc = PipelineWarmupController()
    eid = wc.register_component("db", warmup_fn=bad_fn)

    assert wc.warmup(eid) is False
    assert wc.get_component(eid)["status"] == "failed"
    print("OK: warmup fn failure")


def test_warmup_by_name():
    """Warmup by component name."""
    wc = PipelineWarmupController()
    wc.register_component("cache")

    assert wc.warmup_by_name("cache") is True
    assert wc.get_by_name("cache")["status"] == "ready"
    assert wc.warmup_by_name("nonexistent") is False
    print("OK: warmup by name")


def test_dependencies():
    """Dependencies must be ready before warmup."""
    wc = PipelineWarmupController()
    eid1 = wc.register_component("db", order=1)
    eid2 = wc.register_component("cache", order=2, depends_on=[eid1])

    # cache can't warmup until db is ready
    assert wc.warmup(eid2) is False

    # warmup db first
    assert wc.warmup(eid1) is True
    # now cache can warmup
    assert wc.warmup(eid2) is True
    print("OK: dependencies")


def test_invalid_dependency():
    """Invalid dependency rejected."""
    wc = PipelineWarmupController()
    assert wc.register_component("cache", depends_on=["nonexistent"]) == ""
    print("OK: invalid dependency")


def test_warmup_all():
    """Warmup all components in order."""
    wc = PipelineWarmupController()
    eid1 = wc.register_component("db", order=1)
    eid2 = wc.register_component("cache", order=2, depends_on=[eid1])
    eid3 = wc.register_component("api", order=3, depends_on=[eid2])

    results = wc.warmup_all()
    assert results[eid1] is True
    assert results[eid2] is True
    assert results[eid3] is True
    assert wc.is_all_ready() is True
    print("OK: warmup all")


def test_is_all_ready():
    """Check if all components are ready."""
    wc = PipelineWarmupController()
    wc.register_component("db")
    wc.register_component("cache")

    assert wc.is_all_ready() is False
    wc.warmup_all()
    assert wc.is_all_ready() is True
    print("OK: is all ready")


def test_get_not_ready():
    """Get list of not-ready components."""
    wc = PipelineWarmupController()
    wc.register_component("db")
    wc.register_component("cache")

    nr = wc.get_not_ready()
    assert len(nr) == 2
    assert "db" in nr
    assert "cache" in nr

    wc.warmup_all()
    assert wc.get_not_ready() == []
    print("OK: get not ready")


def test_health_check():
    """Health check via health_fn."""
    wc = PipelineWarmupController()
    eid = wc.register_component("db", health_fn=lambda: True)

    assert wc.check_health(eid) is True

    eid2 = wc.register_component("cache", health_fn=lambda: False)
    assert wc.check_health(eid2) is False

    # no health_fn
    eid3 = wc.register_component("api")
    assert wc.check_health(eid3) is False

    # nonexistent
    assert wc.check_health("nonexistent") is False
    print("OK: health check")


def test_health_check_exception():
    """Health check handles exceptions."""
    def bad_health():
        raise RuntimeError("fail")

    wc = PipelineWarmupController()
    eid = wc.register_component("db", health_fn=bad_health)
    assert wc.check_health(eid) is False
    print("OK: health check exception")


def test_list_components():
    """List components with filters."""
    wc = PipelineWarmupController()
    wc.register_component("db", tags=["core"])
    eid2 = wc.register_component("cache")
    wc.warmup(eid2)

    all_c = wc.list_components()
    assert len(all_c) == 2

    by_status = wc.list_components(status="ready")
    assert len(by_status) == 1

    by_tag = wc.list_components(tag="core")
    assert len(by_tag) == 1
    print("OK: list components")


def test_callback():
    """Callback fires on events."""
    wc = PipelineWarmupController()
    fired = []
    wc.on_change("mon", lambda a, d: fired.append(a))

    eid = wc.register_component("db")
    assert "component_registered" in fired

    wc.warmup(eid)
    assert "warmup_complete" in fired
    print("OK: callback")


def test_callback_on_failure():
    """Callback fires on warmup failure."""
    wc = PipelineWarmupController()
    fired = []
    wc.on_change("mon", lambda a, d: fired.append(a))

    eid = wc.register_component("db", warmup_fn=lambda: (_ for _ in ()).throw(RuntimeError("x")))
    wc.warmup(eid)
    assert "warmup_failed" in fired
    print("OK: callback on failure")


def test_callbacks():
    """Callback registration."""
    wc = PipelineWarmupController()
    assert wc.on_change("mon", lambda a, d: None) is True
    assert wc.on_change("mon", lambda a, d: None) is False
    assert wc.remove_callback("mon") is True
    assert wc.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    wc = PipelineWarmupController()
    eid1 = wc.register_component("db")
    wc.register_component("cache")
    wc.warmup(eid1)

    stats = wc.get_stats()
    assert stats["current_components"] == 2
    assert stats["total_registered"] == 2
    assert stats["total_warmups"] == 1
    assert stats["ready_count"] == 1
    assert stats["pending_count"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    wc = PipelineWarmupController()
    wc.register_component("db")

    wc.reset()
    assert wc.list_components() == []
    stats = wc.get_stats()
    assert stats["current_components"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Warmup Controller Tests ===\n")
    test_register_component()
    test_invalid_register()
    test_duplicate()
    test_max_entries()
    test_get_by_name()
    test_warmup()
    test_warmup_with_fn()
    test_warmup_fn_failure()
    test_warmup_by_name()
    test_dependencies()
    test_invalid_dependency()
    test_warmup_all()
    test_is_all_ready()
    test_get_not_ready()
    test_health_check()
    test_health_check_exception()
    test_list_components()
    test_callback()
    test_callback_on_failure()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 22 TESTS PASSED ===")


if __name__ == "__main__":
    main()
