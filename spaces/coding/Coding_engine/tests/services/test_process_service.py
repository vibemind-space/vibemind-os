"""Test process_service — compile and structure verification."""
import py_compile
import sys
sys.path.insert(0, ".")

SOURCE = "src/services/process_service.py"


def test_compiles():
    """Module compiles without syntax errors."""
    py_compile.compile(SOURCE, doraise=True)
    print("OK: compiles")


def test_structure():
    """Key classes and functions exist."""
    with open(SOURCE) as f:
        src = f.read()
    assert "class ProcessInfo" in src
    assert "class ProcessMonitorService" in src
    assert "def get_all_processes(" in src
    assert "def get_process_by_pid(" in src
    assert "def get_processes_by_port(" in src
    assert "def get_system_stats(" in src
    assert "def get_listening_ports(" in src
    assert "def kill_process(" in src
    print("OK: structure verified")


def test_imports_declared():
    """Required imports are declared."""
    with open(SOURCE) as f:
        src = f.read()
    assert "import psutil" in src
    assert "import structlog" in src
    print("OK: imports declared")


def main():
    print("=== Process Service Tests ===\n")
    test_compiles()
    test_structure()
    test_imports_declared()
    print("\n=== ALL 3 TESTS PASSED ===")


if __name__ == "__main__":
    main()
