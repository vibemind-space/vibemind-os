"""Test package dependency resolver."""
import sys
sys.path.insert(0, ".")

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from src.services.package_dependency_resolver import (
    PackageDependencyResolver,
    PackageDependency,
    DependencyGraph,
    CyclicDependencyError,
)


@dataclass
class MockPackage:
    """Minimal mock of PackageManifest."""
    project_name: str
    package_path: Path = field(default_factory=lambda: Path("/tmp/fake"))
    tech_stack: Dict[str, Any] = field(default_factory=dict)


def test_no_packages():
    """Empty input returns empty graph."""
    resolver = PackageDependencyResolver()
    graph = resolver.resolve_build_order([])
    assert len(graph.nodes) == 0
    assert len(graph.build_order) == 0
    print("OK: no packages")


def test_single_package():
    """Single package with no deps → one batch."""
    resolver = PackageDependencyResolver()
    pkgs = [MockPackage("app-server")]
    graph = resolver.resolve_build_order(pkgs)
    assert len(graph.build_order) == 1
    assert graph.build_order[0] == ["app-server"]
    print("OK: single package")


def test_independent_packages():
    """Independent packages can all build in parallel."""
    resolver = PackageDependencyResolver()
    pkgs = [MockPackage("svc-a"), MockPackage("svc-b"), MockPackage("svc-c")]
    graph = resolver.resolve_build_order(pkgs)
    assert len(graph.build_order) == 1
    assert set(graph.build_order[0]) == {"svc-a", "svc-b", "svc-c"}
    print("OK: independent packages")


def test_linear_chain():
    """A → B → C produces 3 sequential batches."""
    resolver = PackageDependencyResolver()

    deps = {
        "shared-lib": PackageDependency(
            "shared-lib", Path("."), depends_on=[], provides=["shared-lib"]
        ),
        "api-server": PackageDependency(
            "api-server", Path("."), depends_on=["shared-lib"], provides=["api-server"]
        ),
        "frontend": PackageDependency(
            "frontend", Path("."), depends_on=["api-server"], provides=["frontend"]
        ),
    }

    graph = resolver.build_graph(deps)
    resolver.topological_sort_batched(graph)

    assert len(graph.build_order) == 3
    assert graph.build_order[0] == ["shared-lib"]
    assert graph.build_order[1] == ["api-server"]
    assert graph.build_order[2] == ["frontend"]
    print("OK: linear chain")


def test_diamond_dependency():
    """Diamond: A → B, A → C, B → D, C → D produces correct batches."""
    resolver = PackageDependencyResolver()

    deps = {
        "core": PackageDependency(
            "core", Path("."), depends_on=[], provides=["core"]
        ),
        "auth": PackageDependency(
            "auth", Path("."), depends_on=["core"], provides=["auth"]
        ),
        "db": PackageDependency(
            "db", Path("."), depends_on=["core"], provides=["db"]
        ),
        "api": PackageDependency(
            "api", Path("."), depends_on=["auth", "db"], provides=["api"]
        ),
    }

    graph = resolver.build_graph(deps)
    resolver.topological_sort_batched(graph)

    assert graph.build_order[0] == ["core"]
    assert set(graph.build_order[1]) == {"auth", "db"}
    assert graph.build_order[2] == ["api"]
    print("OK: diamond dependency")


def test_cycle_detection():
    """Cycles are detected and reported."""
    resolver = PackageDependencyResolver()

    deps = {
        "a": PackageDependency("a", Path("."), depends_on=["b"], provides=["a"]),
        "b": PackageDependency("b", Path("."), depends_on=["a"], provides=["b"]),
    }

    graph = resolver.build_graph(deps)
    cycles = resolver.detect_cycles(graph)

    assert len(cycles) > 0
    print("OK: cycle detection")


def test_cycle_raises():
    """fail_on_cycles=True raises CyclicDependencyError."""
    resolver = PackageDependencyResolver()

    deps = {
        "a": PackageDependency("a", Path("."), depends_on=["b"], provides=["a"]),
        "b": PackageDependency("b", Path("."), depends_on=["c"], provides=["b"]),
        "c": PackageDependency("c", Path("."), depends_on=["a"], provides=["c"]),
    }

    # Build graph manually to test fail_on_cycles
    graph = resolver.build_graph(deps)
    cycles = resolver.detect_cycles(graph)
    assert len(cycles) > 0

    # The resolve_build_order should raise
    try:
        # Create mock packages with tech_stack deps
        mock_a = MockPackage("a", tech_stack={"dependencies": {"internal": ["b"]}})
        mock_b = MockPackage("b", tech_stack={"dependencies": {"internal": ["c"]}})
        mock_c = MockPackage("c", tech_stack={"dependencies": {"internal": ["a"]}})
        resolver.resolve_build_order([mock_a, mock_b, mock_c], fail_on_cycles=True)
        assert False, "Should have raised CyclicDependencyError"
    except CyclicDependencyError as e:
        assert len(e.cycles) > 0
    print("OK: cycle raises error")


def test_affected_packages():
    """Changing a package reports all transitive dependents."""
    resolver = PackageDependencyResolver()

    deps = {
        "core": PackageDependency("core", Path("."), depends_on=[], provides=["core"]),
        "auth": PackageDependency("auth", Path("."), depends_on=["core"], provides=["auth"]),
        "api": PackageDependency("api", Path("."), depends_on=["auth"], provides=["api"]),
        "frontend": PackageDependency("frontend", Path("."), depends_on=["api"], provides=["frontend"]),
        "docs": PackageDependency("docs", Path("."), depends_on=[], provides=["docs"]),
    }

    graph = resolver.build_graph(deps)
    affected = resolver.get_affected_packages(graph, "core")

    assert "core" in affected
    assert "auth" in affected
    assert "api" in affected
    assert "frontend" in affected
    assert "docs" not in affected
    print("OK: affected packages")


def test_build_plan_for_target():
    """Build plan for a specific target includes only needed packages."""
    resolver = PackageDependencyResolver()

    deps = {
        "core": PackageDependency("core", Path("."), depends_on=[], provides=["core"]),
        "auth": PackageDependency("auth", Path("."), depends_on=["core"], provides=["auth"]),
        "api": PackageDependency("api", Path("."), depends_on=["auth"], provides=["api"]),
        "unrelated": PackageDependency("unrelated", Path("."), depends_on=[], provides=["unrelated"]),
    }

    graph = resolver.build_graph(deps)
    resolver.topological_sort_batched(graph)

    plan = resolver.get_build_plan_for(graph, "api")

    all_planned = [p for batch in plan for p in batch]
    assert "core" in all_planned
    assert "auth" in all_planned
    assert "api" in all_planned
    assert "unrelated" not in all_planned
    print("OK: build plan for target")


def test_missing_dep_non_strict():
    """Missing dependencies are warned in non-strict mode."""
    resolver = PackageDependencyResolver(strict=False)

    deps = {
        "app": PackageDependency(
            "app", Path("."), depends_on=["nonexistent-lib"], provides=["app"]
        ),
    }

    graph = resolver.build_graph(deps)
    # Should not raise, just warn
    assert len(graph.nodes) == 1
    print("OK: missing dep non-strict")


def test_missing_dep_strict():
    """Missing dependencies raise in strict mode."""
    resolver = PackageDependencyResolver(strict=True)

    deps = {
        "app": PackageDependency(
            "app", Path("."), depends_on=["nonexistent-lib"], provides=["app"]
        ),
    }

    try:
        resolver.build_graph(deps)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "nonexistent-lib" in str(e)
    print("OK: missing dep strict")


def test_graph_serialization():
    """DependencyGraph serializes to dict correctly."""
    resolver = PackageDependencyResolver()

    deps = {
        "a": PackageDependency("a", Path("."), depends_on=[], provides=["a"]),
        "b": PackageDependency("b", Path("."), depends_on=["a"], provides=["b"]),
    }

    graph = resolver.build_graph(deps)
    resolver.topological_sort_batched(graph)

    data = graph.to_dict()
    assert data["total_packages"] == 2
    assert data["total_batches"] == 2
    assert "a" in data["nodes"]
    assert "b" in data["nodes"]
    print("OK: graph serialization")


def main():
    print("=== Package Dependency Resolver Tests ===\n")
    test_no_packages()
    test_single_package()
    test_independent_packages()
    test_linear_chain()
    test_diamond_dependency()
    test_cycle_detection()
    test_cycle_raises()
    test_affected_packages()
    test_build_plan_for_target()
    test_missing_dep_non_strict()
    test_missing_dep_strict()
    test_graph_serialization()
    print("\n=== ALL 12 TESTS PASSED ===")


if __name__ == "__main__":
    main()
