"""Test supermemory_corpus_loader — compile and structure verification."""
import py_compile
import sys
sys.path.insert(0, ".")

SOURCE = "src/services/supermemory_corpus_loader.py"


def test_compiles():
    """Module compiles without syntax errors."""
    py_compile.compile(SOURCE, doraise=True)
    print("OK: compiles")


def test_structure():
    """Key classes and functions exist."""
    with open(SOURCE) as f:
        src = f.read()
    assert "class SupermemoryCorpusLoader" in src
    assert "async def initialize(" in src
    assert "async def fetch_memories(" in src
    assert "async def fetch_as_mcmp_documents(" in src
    assert "async def fetch_as_search_results(" in src
    assert "async def store_pattern(" in src
    assert "def reset(" in src
    assert "async def close(" in src
    print("OK: structure verified")


def test_imports_declared():
    """Required imports are declared."""
    with open(SOURCE) as f:
        src = f.read()
    assert "import structlog" in src
    assert "import os" in src
    print("OK: imports declared")


def main():
    print("=== Supermemory Corpus Loader Tests ===\n")
    test_compiles()
    test_structure()
    test_imports_declared()
    print("\n=== ALL 3 TESTS PASSED ===")


if __name__ == "__main__":
    main()
