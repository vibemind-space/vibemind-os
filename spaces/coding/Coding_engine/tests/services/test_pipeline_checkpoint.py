"""Test pipeline_checkpoint — compile and structure verification."""
import py_compile
import sys
sys.path.insert(0, ".")

SOURCE = "src/services/pipeline_checkpoint.py"


def test_compiles():
    """Module compiles without syntax errors."""
    py_compile.compile(SOURCE, doraise=True)
    print("OK: compiles")


def test_structure():
    """Key classes and functions exist."""
    with open(SOURCE) as f:
        src = f.read()
    assert "class PipelineCheckpoint" in src
    assert "class PipelineCheckpointer" in src
    assert "def save(" in src or "async def save(" in src
    assert "def load_latest(" in src
    assert "def load_by_id(" in src
    assert "def list_checkpoints(" in src
    assert "async def restore_from_checkpoint(" in src
    print("OK: structure verified")


def test_imports_declared():
    """Required imports are declared."""
    with open(SOURCE) as f:
        src = f.read()
    assert "import json" in src
    assert "import structlog" in src
    assert "from ..mind.event_bus import" in src
    print("OK: imports declared")


def main():
    print("=== Pipeline Checkpoint Tests ===\n")
    test_compiles()
    test_structure()
    test_imports_declared()
    print("\n=== ALL 3 TESTS PASSED ===")


if __name__ == "__main__":
    main()
