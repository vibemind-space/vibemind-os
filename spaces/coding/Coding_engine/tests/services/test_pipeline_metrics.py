"""Test pipeline_metrics — compile and structure verification."""
import py_compile
import sys
sys.path.insert(0, ".")

SOURCE = "src/services/pipeline_metrics.py"


def test_compiles():
    """Module compiles without syntax errors."""
    py_compile.compile(SOURCE, doraise=True)
    print("OK: compiles")


def test_structure():
    """Key classes and functions exist."""
    with open(SOURCE) as f:
        src = f.read()
    assert "class PipelineMetrics" in src
    assert "class PipelineMetricsCollector" in src
    assert "def to_dict(" in src
    assert "def get_metrics(" in src
    assert "def get_summary(" in src
    print("OK: structure verified")


def test_imports_declared():
    """Required imports are declared."""
    with open(SOURCE) as f:
        src = f.read()
    assert "import structlog" in src
    assert "from ..mind.event_bus import" in src
    assert "from ..mind.shared_state import" in src
    print("OK: imports declared")


def main():
    print("=== Pipeline Metrics Tests ===\n")
    test_compiles()
    test_structure()
    test_imports_declared()
    print("\n=== ALL 3 TESTS PASSED ===")


if __name__ == "__main__":
    main()
