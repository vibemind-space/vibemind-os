"""Test pipeline dependency resolver -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_dependency_resolver import PipelineDependencyResolver


def test_register_component():
    dr = PipelineDependencyResolver()
    cid = dr.register_component("auth_service", version="1.0.0", tags=["core"])
    assert cid.startswith("pdr-")
    c = dr.get_component("auth_service")
    assert c is not None
    assert c["name"] == "auth_service"
    assert dr.register_component("auth_service") == ""  # dup
    print("OK: register component")


def test_add_dependency():
    dr = PipelineDependencyResolver()
    dr.register_component("app")
    dr.register_component("db")
    dr.register_component("cache")
    assert dr.add_dependency("app", "db") is True
    assert dr.add_dependency("app", "cache") is True
    deps = dr.get_dependencies("app")
    assert "db" in deps
    assert "cache" in deps
    print("OK: add dependency")


def test_cycle_detection():
    dr = PipelineDependencyResolver()
    dr.register_component("a")
    dr.register_component("b")
    dr.register_component("c")
    dr.add_dependency("a", "b")
    dr.add_dependency("b", "c")
    result = dr.add_dependency("c", "a")
    assert result is False
    print("OK: cycle detection")


def test_resolve():
    dr = PipelineDependencyResolver()
    dr.register_component("app")
    dr.register_component("db")
    dr.register_component("cache")
    dr.register_component("config")
    dr.add_dependency("app", "db")
    dr.add_dependency("app", "cache")
    dr.add_dependency("db", "config")
    dr.add_dependency("cache", "config")
    order = dr.resolve("app")
    assert order.index("config") < order.index("db")
    assert order.index("config") < order.index("cache")
    print("OK: resolve")


def test_install_order():
    dr = PipelineDependencyResolver()
    dr.register_component("app")
    dr.register_component("db")
    dr.register_component("cache")
    dr.register_component("config")
    dr.add_dependency("app", "db")
    dr.add_dependency("app", "cache")
    dr.add_dependency("db", "config")
    dr.add_dependency("cache", "config")
    waves = dr.get_install_order()
    assert len(waves) >= 2
    assert "config" in waves[0]
    print("OK: install order")


def test_dependents():
    dr = PipelineDependencyResolver()
    dr.register_component("app")
    dr.register_component("db")
    dr.add_dependency("app", "db")
    dependents = dr.get_dependents("db")
    assert "app" in dependents
    print("OK: dependents")


def test_remove_dependency():
    dr = PipelineDependencyResolver()
    dr.register_component("a")
    dr.register_component("b")
    dr.add_dependency("a", "b")
    assert dr.remove_dependency("a", "b") is True
    assert dr.remove_dependency("a", "b") is False
    print("OK: remove dependency")


def test_leaf_components():
    dr = PipelineDependencyResolver()
    dr.register_component("app")
    dr.register_component("db")
    dr.register_component("config")
    dr.add_dependency("app", "db")
    dr.add_dependency("db", "config")
    leaves = dr.get_leaf_components()
    assert "config" in leaves
    print("OK: leaf components")


def test_orphan_components():
    dr = PipelineDependencyResolver()
    dr.register_component("app")
    dr.register_component("db")
    dr.register_component("config")
    dr.add_dependency("app", "db")
    dr.add_dependency("db", "config")
    orphans = dr.get_orphan_components()
    assert "app" in orphans
    print("OK: orphan components")


def test_list_components():
    dr = PipelineDependencyResolver()
    dr.register_component("a", tags=["core"])
    dr.register_component("b")
    assert len(dr.list_components()) == 2
    assert len(dr.list_components(tag="core")) == 1
    print("OK: list components")


def test_remove_component():
    dr = PipelineDependencyResolver()
    dr.register_component("a")
    assert dr.remove_component("a") is True
    assert dr.remove_component("a") is False
    print("OK: remove component")


def test_history():
    dr = PipelineDependencyResolver()
    dr.register_component("a")
    hist = dr.get_history()
    assert len(hist) >= 1
    print("OK: history")


def test_callbacks():
    dr = PipelineDependencyResolver()
    fired = []
    dr.on_change("mon", lambda a, d: fired.append(a))
    dr.register_component("a")
    assert len(fired) >= 1
    assert dr.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    dr = PipelineDependencyResolver()
    dr.register_component("a")
    stats = dr.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    dr = PipelineDependencyResolver()
    dr.register_component("a")
    dr.reset()
    assert dr.list_components() == []
    print("OK: reset")


def main():
    print("=== Pipeline Dependency Resolver Tests ===\n")
    test_register_component()
    test_add_dependency()
    test_cycle_detection()
    test_resolve()
    test_install_order()
    test_dependents()
    test_remove_dependency()
    test_leaf_components()
    test_orphan_components()
    test_list_components()
    test_remove_component()
    test_history()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 15 TESTS PASSED ===")


if __name__ == "__main__":
    main()
