"""Test moderation_service — compile and structure verification."""
import py_compile
import sys
sys.path.insert(0, ".")

SOURCE = "src/services/moderation_service.py"

def test_compiles():
    """Module compiles without syntax errors."""
    py_compile.compile(SOURCE, doraise=True)
    print("OK: compiles")

def test_structure():
    """Key classes and functions exist."""
    with open(SOURCE, encoding="utf-8") as f:
        src = f.read()
    assert "class ModerationService" in src
    assert "class ModerationQueue" in src
    assert "class Report" in src
    assert "class ReportType" in src
    assert "class ReportStatus" in src
    assert "class QuarantineRecord" in src
    assert "class QuarantineReason" in src
    assert "class QuarantineStatus" in src
    assert "class TrustScore" in src
    assert "class ModerationAction" in src
    print("OK: structure verified")

def test_imports_declared():
    """Required imports are declared."""
    with open(SOURCE, encoding="utf-8") as f:
        src = f.read()
    assert "import" in src
    assert "structlog" in src
    assert "import asyncio" in src
    print("OK: imports declared")

def main():
    print("=== Moderation Service Tests ===\n")
    test_compiles()
    test_structure()
    test_imports_declared()
    print("\n=== ALL 3 TESTS PASSED ===")

if __name__ == "__main__":
    main()
