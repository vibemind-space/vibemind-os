"""Test ws_event_streamer — compile and structure verification."""
import py_compile
import sys
sys.path.insert(0, ".")

SOURCE = "src/services/ws_event_streamer.py"


def test_compiles():
    """Module compiles without syntax errors."""
    py_compile.compile(SOURCE, doraise=True)
    print("OK: compiles")


def test_structure():
    """Key classes and functions exist."""
    with open(SOURCE) as f:
        src = f.read()
    assert "class WSEventStreamer" in src
    assert "async def start(" in src
    assert "async def stop(" in src
    assert "def get_stats(" in src
    assert "def _on_event(" in src
    print("OK: structure verified")


def test_imports_declared():
    """Required imports are declared."""
    with open(SOURCE) as f:
        src = f.read()
    assert "import asyncio" in src
    assert "import json" in src
    assert "import structlog" in src
    assert "from ..mind.event_bus import" in src
    print("OK: imports declared")


def main():
    print("=== WS Event Streamer Tests ===\n")
    test_compiles()
    test_structure()
    test_imports_declared()
    print("\n=== ALL 3 TESTS PASSED ===")


if __name__ == "__main__":
    main()
