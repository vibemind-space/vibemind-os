"""Test container_log_seeder — compile and structure verification."""
import py_compile
import sys
sys.path.insert(0, ".")

SOURCE = "src/services/container_log_seeder.py"

def test_compiles():
    """Module compiles without syntax errors."""
    py_compile.compile(SOURCE, doraise=True)
    print("OK: compiles")

def test_structure():
    """Key classes and functions exist."""
    with open(SOURCE, encoding="utf-8") as f:
        src = f.read()
    assert "class ContainerLogSeeder" in src
    assert "class ContainerLogEntry" in src
    assert "class LogSeedResult" in src
    assert "def get_container_log_seeder" in src
    assert "async def setup_container_log_seeder" in src
    print("OK: structure verified")

def test_imports_declared():
    """Required imports are declared."""
    with open(SOURCE, encoding="utf-8") as f:
        src = f.read()
    assert "import" in src
    assert "structlog" in src
    assert "import subprocess" in src
    print("OK: imports declared")

def main():
    print("=== Container Log Seeder Tests ===\n")
    test_compiles()
    test_structure()
    test_imports_declared()
    print("\n=== ALL 3 TESTS PASSED ===")

if __name__ == "__main__":
    main()
