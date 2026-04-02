"""Test davelovable_bridge — compile and structure verification."""
import py_compile
import sys
sys.path.insert(0, ".")

SOURCE = "src/services/davelovable_bridge.py"


def test_compiles():
    """Module compiles without syntax errors."""
    py_compile.compile(SOURCE, doraise=True)
    print("OK: compiles")


def test_structure():
    """Key classes and functions exist."""
    with open(SOURCE) as f:
        src = f.read()
    assert "class DaveLovableClient" in src
    assert "class DaveLovableBridge" in src
    assert "async def initialize(" in src
    assert "async def push_project_files(" in src
    assert "async def push_verification_results(" in src
    assert "async def push_evolution_result(" in src
    assert "async def create_davelovable_bridge(" in src
    print("OK: structure verified")


def test_imports_declared():
    """Required imports are declared."""
    with open(SOURCE) as f:
        src = f.read()
    assert "import aiohttp" in src
    assert "import structlog" in src
    assert "from ..mind.event_bus import" in src
    print("OK: imports declared")


def main():
    print("=== DaveLovable Bridge Tests ===\n")
    test_compiles()
    test_structure()
    test_imports_declared()
    print("\n=== ALL 3 TESTS PASSED ===")


if __name__ == "__main__":
    main()
