"""Test minibook_discussion — compile and structure verification."""
import py_compile
import sys
sys.path.insert(0, ".")

SOURCE = "src/services/minibook_discussion.py"


def test_compiles():
    """Module compiles without syntax errors."""
    py_compile.compile(SOURCE, doraise=True)
    print("OK: compiles")


def test_structure():
    """Key classes and functions exist."""
    with open(SOURCE) as f:
        src = f.read()
    assert "class ResolutionStrategy" in src
    assert "class DiscussionStatus" in src
    assert "class DiscussionVote" in src
    assert "class DiscussionOption" in src
    assert "class Discussion" in src
    assert "class DiscussionManager" in src
    assert "async def create_discussion(" in src
    assert "async def cast_vote(" in src
    print("OK: structure verified")


def test_imports_declared():
    """Required imports are declared."""
    with open(SOURCE) as f:
        src = f.read()
    assert "import structlog" in src
    assert "from ..mind.event_bus import" in src
    assert "from enum import Enum" in src
    print("OK: imports declared")


def main():
    print("=== Minibook Discussion Tests ===\n")
    test_compiles()
    test_structure()
    test_imports_declared()
    print("\n=== ALL 3 TESTS PASSED ===")


if __name__ == "__main__":
    main()
