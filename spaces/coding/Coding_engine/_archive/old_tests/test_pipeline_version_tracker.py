"""Test pipeline version tracker."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_version_tracker import PipelineVersionTracker


def test_create_version():
    """Create and retrieve version."""
    vt = PipelineVersionTracker()
    vid = vt.create_version("auth_module", "1.2.3",
                            changelog="Added OAuth",
                            author="alice", tags=["release"])
    assert vid.startswith("ver-")

    v = vt.get_version(vid)
    assert v is not None
    assert v["component"] == "auth_module"
    assert v["version"] == "1.2.3"
    assert v["major"] == 1
    assert v["minor"] == 2
    assert v["patch"] == 3
    assert v["status"] == "draft"

    assert vt.remove_version(vid) is True
    assert vt.remove_version(vid) is False
    print("OK: create version")


def test_invalid_version():
    """Invalid version rejected."""
    vt = PipelineVersionTracker()
    assert vt.create_version("", "1.0.0") == ""
    assert vt.create_version("c", "") == ""
    assert vt.create_version("c", "1.0") == ""  # not 3 parts
    assert vt.create_version("c", "a.b.c") == ""  # non-numeric
    print("OK: invalid version")


def test_release_version():
    """Release a version."""
    vt = PipelineVersionTracker()
    vid = vt.create_version("c", "1.0.0")

    assert vt.release_version(vid) is True
    assert vt.get_version(vid)["status"] == "released"
    assert vt.release_version(vid) is False
    print("OK: release version")


def test_deprecate_version():
    """Deprecate a version."""
    vt = PipelineVersionTracker()
    vid = vt.create_version("c", "1.0.0")

    assert vt.deprecate_version(vid) is True
    assert vt.get_version(vid)["status"] == "deprecated"
    assert vt.deprecate_version(vid) is False
    print("OK: deprecate version")


def test_get_latest():
    """Get latest version for component."""
    vt = PipelineVersionTracker()
    vt.create_version("mod", "1.0.0")
    vt.create_version("mod", "2.1.0")
    vt.create_version("mod", "1.5.0")

    latest = vt.get_latest("mod")
    assert latest is not None
    assert latest["version"] == "2.1.0"
    print("OK: get latest")


def test_get_latest_released():
    """Get latest released version."""
    vt = PipelineVersionTracker()
    v1 = vt.create_version("mod", "1.0.0")
    vt.release_version(v1)
    vt.create_version("mod", "2.0.0")  # draft

    latest = vt.get_latest("mod", status="released")
    assert latest is not None
    assert latest["version"] == "1.0.0"
    print("OK: get latest released")


def test_component_history():
    """Get version history for component."""
    vt = PipelineVersionTracker()
    vt.create_version("mod", "1.0.0", changelog="Initial")
    vt.create_version("mod", "1.1.0", changelog="Update")
    vt.create_version("other", "1.0.0")

    history = vt.get_component_history("mod")
    assert len(history) == 2
    # Most recent first (by seq)
    assert history[0]["version"] == "1.1.0"
    assert history[1]["version"] == "1.0.0"
    print("OK: component history")


def test_search_versions():
    """Search versions with filters."""
    vt = PipelineVersionTracker()
    v1 = vt.create_version("auth", "1.0.0", author="alice", tags=["v1"])
    vt.release_version(v1)
    vt.create_version("auth", "2.0.0", author="bob")
    vt.create_version("db", "1.0.0", author="alice")

    by_comp = vt.search_versions(component="auth")
    assert len(by_comp) == 2

    by_status = vt.search_versions(status="released")
    assert len(by_status) == 1

    by_author = vt.search_versions(author="alice")
    assert len(by_author) == 2

    by_tag = vt.search_versions(tag="v1")
    assert len(by_tag) == 1
    print("OK: search versions")


def test_search_limit():
    """Search respects limit."""
    vt = PipelineVersionTracker()
    for i in range(20):
        vt.create_version("mod", f"1.0.{i}")

    results = vt.search_versions(limit=5)
    assert len(results) == 5
    print("OK: search limit")


def test_list_components():
    """List all components."""
    vt = PipelineVersionTracker()
    vt.create_version("auth", "1.0.0")
    vt.create_version("auth", "2.0.0")
    vt.create_version("db", "1.0.0")

    comps = vt.list_components()
    assert len(comps) == 2
    auth = next(c for c in comps if c["component"] == "auth")
    assert auth["latest_version"] == "2.0.0"
    assert auth["version_count"] == 2
    print("OK: list components")


def test_compare_versions():
    """Compare version strings."""
    vt = PipelineVersionTracker()
    assert vt.compare_versions("1.0.0", "2.0.0") == -1
    assert vt.compare_versions("2.0.0", "1.0.0") == 1
    assert vt.compare_versions("1.0.0", "1.0.0") == 0
    assert vt.compare_versions("1.2.3", "1.2.4") == -1
    assert vt.compare_versions("1.3.0", "1.2.9") == 1
    print("OK: compare versions")


def test_version_callback():
    """Callback fires on version create."""
    vt = PipelineVersionTracker()
    fired = []
    vt.on_change("mon", lambda a, d: fired.append(a))

    vt.create_version("c", "1.0.0")
    assert "version_created" in fired
    print("OK: version callback")


def test_callbacks():
    """Callback registration."""
    vt = PipelineVersionTracker()
    assert vt.on_change("mon", lambda a, d: None) is True
    assert vt.on_change("mon", lambda a, d: None) is False
    assert vt.remove_callback("mon") is True
    assert vt.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    vt = PipelineVersionTracker()
    v1 = vt.create_version("a", "1.0.0")
    v2 = vt.create_version("b", "1.0.0")
    vt.release_version(v1)
    vt.deprecate_version(v2)

    stats = vt.get_stats()
    assert stats["total_versions_created"] == 2
    assert stats["total_released"] == 1
    assert stats["total_deprecated"] == 1
    assert stats["current_versions"] == 2
    assert stats["released_versions"] == 1
    assert stats["component_count"] == 2
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    vt = PipelineVersionTracker()
    vt.create_version("c", "1.0.0")

    vt.reset()
    assert vt.search_versions() == []
    stats = vt.get_stats()
    assert stats["current_versions"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Version Tracker Tests ===\n")
    test_create_version()
    test_invalid_version()
    test_release_version()
    test_deprecate_version()
    test_get_latest()
    test_get_latest_released()
    test_component_history()
    test_search_versions()
    test_search_limit()
    test_list_components()
    test_compare_versions()
    test_version_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 15 TESTS PASSED ===")


if __name__ == "__main__":
    main()
