"""Test dashboard_event_tracker — compile and structure verification."""
import py_compile
import sys
sys.path.insert(0, ".")

SOURCE = "src/services/dashboard_event_tracker.py"


def test_compiles():
    """Module compiles without syntax errors."""
    py_compile.compile(SOURCE, doraise=True)
    print("OK: compiles")


def test_structure():
    """Key classes and functions exist."""
    with open(SOURCE) as f:
        src = f.read()
    assert "class DashboardEventTracker" in src
    assert "def start(" in src
    assert "def stop(" in src
    assert "async def _handle_event(" in src
    assert "async def _store_event(" in src
    assert "async def _broadcast_event(" in src
    assert "async def track_process_change(" in src
    assert "async def track_connection_change(" in src
    assert "def create_dashboard_event_tracker(" in src
    print("OK: structure verified")


def test_imports_declared():
    """Required imports are declared."""
    with open(SOURCE) as f:
        src = f.read()
    assert "import structlog" in src
    assert "import asyncio" in src
    assert "from src.mind.event_bus import" in src
    print("OK: imports declared")


def main():
    print("=== Dashboard Event Tracker Tests ===\n")
    test_compiles()
    test_structure()
    test_imports_declared()
    print("\n=== ALL 3 TESTS PASSED ===")


if __name__ == "__main__":
    main()
