"""Test project_indexer — compile and structure verification."""
import py_compile
import sys
sys.path.insert(0, ".")

SOURCE = "src/services/project_indexer.py"


def test_compiles():
    """Module compiles without syntax errors."""
    py_compile.compile(SOURCE, doraise=True)
    print("OK: compiles")


def test_structure():
    """Key classes and functions exist."""
    with open(SOURCE) as f:
        src = f.read()
    assert "class CodeChunk" in src
    assert "class ASTChunker" in src
    assert "class TypeScriptChunker" in src
    assert "class ContentAnalyzer" in src
    assert "class ProjectIndexer" in src
    assert "async def index_project(" in src
    assert "async def index_file(" in src
    assert "async def search(" in src
    assert "def implementation_score(" in src
    assert "def has_fetch_pattern(" in src
    print("OK: structure verified")


def test_imports_declared():
    """Required imports are declared."""
    with open(SOURCE) as f:
        src = f.read()
    assert "import ast" in src
    assert "import structlog" in src
    assert "from pathlib import Path" in src
    print("OK: imports declared")


def main():
    print("=== Project Indexer Tests ===\n")
    test_compiles()
    test_structure()
    test_imports_declared()
    print("\n=== ALL 3 TESTS PASSED ===")


if __name__ == "__main__":
    main()
