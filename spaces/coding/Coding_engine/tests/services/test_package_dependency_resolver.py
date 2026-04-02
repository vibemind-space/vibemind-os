"""Test package_dependency_resolver — compile and structure verification."""
import py_compile
import sys
sys.path.insert(0, ".")

SOURCE = "src/services/package_dependency_resolver.py"


def test_compiles():
    """Module compiles without syntax errors."""
    py_compile.compile(SOURCE, doraise=True)
    print("OK: compiles")


def test_structure():
    """Key classes and functions exist."""
    with open(SOURCE) as f:
        src = f.read()
    assert "class PackageDependency" in src
    assert "class DependencyGraph" in src
    assert "class CyclicDependencyError" in src
    assert "class PackageDependencyResolver" in src
    assert "def scan_dependencies(" in src
    assert "def build_graph(" in src
    assert "def detect_cycles(" in src
    assert "def topological_sort_batched(" in src
    assert "def resolve_build_order(" in src
    assert "def get_affected_packages(" in src
    print("OK: structure verified")


def test_imports_declared():
    """Required imports are declared."""
    with open(SOURCE) as f:
        src = f.read()
    assert "import json" in src
    assert "import structlog" in src
    assert "from collections import" in src
    print("OK: imports declared")


def main():
    print("=== Package Dependency Resolver Tests ===\n")
    test_compiles()
    test_structure()
    test_imports_declared()
    print("\n=== ALL 3 TESTS PASSED ===")


if __name__ == "__main__":
    main()
