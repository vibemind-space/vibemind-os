"""Test fungus_validation_service — compile and structure verification."""
import py_compile
import sys
sys.path.insert(0, ".")

SOURCE = "src/services/fungus_validation_service.py"

def test_compiles():
    """Module compiles without syntax errors."""
    py_compile.compile(SOURCE, doraise=True)
    print("OK: compiles")

def test_structure():
    """Key classes and functions exist."""
    with open(SOURCE, encoding="utf-8") as f:
        src = f.read()
    assert "class FungusValidationService" in src
    assert "class ValidationJudgeMode" in src
    assert "class ValidationFinding" in src
    assert "class ValidationReport" in src
    print("OK: structure verified")

def test_imports_declared():
    """Required imports are declared."""
    with open(SOURCE, encoding="utf-8") as f:
        src = f.read()
    assert "import" in src
    assert "structlog" in src
    assert "from .mcmp_background import" in src
    print("OK: imports declared")

def main():
    print("=== Fungus Validation Service Tests ===\n")
    test_compiles()
    test_structure()
    test_imports_declared()
    print("\n=== ALL 3 TESTS PASSED ===")

if __name__ == "__main__":
    main()
