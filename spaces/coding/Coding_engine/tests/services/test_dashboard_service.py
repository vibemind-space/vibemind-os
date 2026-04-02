"""Test dashboard_service — compile and structure verification."""
import py_compile
import sys
sys.path.insert(0, ".")

SOURCE = "src/services/dashboard_service.py"


def test_compiles():
    """Module compiles without syntax errors."""
    py_compile.compile(SOURCE, doraise=True)
    print("OK: compiles")


def test_structure():
    """Key classes and functions exist."""
    with open(SOURCE) as f:
        src = f.read()
    assert "class DashboardService" in src
    assert "async def get_timeline(" in src
    assert "async def get_process_metrics(" in src
    assert "async def get_connection_metrics(" in src
    assert "async def get_dashboard_metrics(" in src
    assert "async def get_dashboard_overview(" in src
    assert "async def get_process_list(" in src
    assert "async def record_event(" in src
    assert "async def cleanup_old_events(" in src
    print("OK: structure verified")


def test_imports_declared():
    """Required imports are declared."""
    with open(SOURCE) as f:
        src = f.read()
    assert "import psutil" in src
    assert "from sqlalchemy" in src
    assert "from src.models.connection_event import" in src
    print("OK: imports declared")


def main():
    print("=== Dashboard Service Tests ===\n")
    test_compiles()
    test_structure()
    test_imports_declared()
    print("\n=== ALL 3 TESTS PASSED ===")


if __name__ == "__main__":
    main()
