"""Test code quality gate."""
import sys
sys.path.insert(0, ".")

from src.services.code_quality_gate import (
    CodeQualityGate,
    GateStatus,
    QualityDimension,
)


def _good_metrics():
    return {
        "complexity": 3,
        "lines": 100,
        "functions": 8,
        "docstring_coverage": 0.90,
        "test_coverage": 0.85,
        "lint_issues": 1,
        "security_issues": 0,
    }


def _bad_metrics():
    return {
        "complexity": 35,
        "lines": 500,
        "functions": 3,
        "docstring_coverage": 0.10,
        "test_coverage": 0.20,
        "lint_issues": 30,
        "security_issues": 5,
    }


def test_score_good_file():
    """Good file gets high score."""
    gate = CodeQualityGate()
    fs = gate.score_file("good.py", _good_metrics())

    assert fs.overall_score > 80
    assert fs.scores["complexity"] == 100.0
    assert fs.scores["security"] == 100.0
    assert len(fs.issues) == 0
    print("OK: score good file")


def test_score_bad_file():
    """Bad file gets low score with issues."""
    gate = CodeQualityGate()
    fs = gate.score_file("bad.py", _bad_metrics())

    assert fs.overall_score < 50
    assert len(fs.issues) > 0
    assert any("complexity" in i.lower() for i in fs.issues)
    assert any("security" in i.lower() for i in fs.issues)
    print("OK: score bad file")


def test_score_dimensions():
    """Individual dimension scores are calculated."""
    gate = CodeQualityGate()
    fs = gate.score_file("test.py", {
        "complexity": 8,
        "lines": 200,
        "functions": 10,
        "docstring_coverage": 0.50,
        "test_coverage": 0.70,
        "lint_issues": 3,
        "security_issues": 1,
    })

    assert "complexity" in fs.scores
    assert "style" in fs.scores
    assert "coverage" in fs.scores
    assert "security" in fs.scores
    assert "documentation" in fs.scores
    assert "maintainability" in fs.scores

    assert fs.scores["complexity"] == 80.0  # 8 <= 10
    assert fs.scores["coverage"] == 70.0    # 0.70 * 100
    print("OK: score dimensions")


def test_gate_pass():
    """Gate passes with good files."""
    gate = CodeQualityGate(min_score=70.0)
    gate.score_file("a.py", _good_metrics())
    gate.score_file("b.py", _good_metrics())

    result = gate.check_gate()
    assert result.passed is True
    assert result.status in (GateStatus.PASSED, GateStatus.WARNING)
    assert result.score >= 70.0
    assert result.file_count == 2
    print("OK: gate pass")


def test_gate_fail():
    """Gate fails with bad files."""
    gate = CodeQualityGate(min_score=70.0)
    gate.score_file("bad1.py", _bad_metrics())
    gate.score_file("bad2.py", _bad_metrics())

    result = gate.check_gate()
    assert result.passed is False
    assert result.status == GateStatus.FAILED
    assert result.score < 70.0
    assert len(result.warnings) > 0
    print("OK: gate fail")


def test_gate_warning():
    """Gate warns when score is between min and warning."""
    gate = CodeQualityGate(min_score=60.0, warning_score=85.0)
    gate.score_file("ok.py", {
        "complexity": 10,
        "lines": 200,
        "functions": 10,
        "docstring_coverage": 0.60,
        "test_coverage": 0.70,
        "lint_issues": 5,
        "security_issues": 0,
    })

    result = gate.check_gate()
    assert result.passed is True  # Warning still passes
    assert result.status == GateStatus.WARNING
    print("OK: gate warning")


def test_gate_skipped():
    """Gate skipped when no files scored."""
    gate = CodeQualityGate()
    result = gate.check_gate()
    assert result.status == GateStatus.SKIPPED
    assert result.file_count == 0
    print("OK: gate skipped")


def test_failing_files():
    """Files below per-file minimum are reported."""
    gate = CodeQualityGate(file_min_score=60.0)
    gate.score_file("good.py", _good_metrics())
    gate.score_file("terrible.py", _bad_metrics())

    result = gate.check_gate()
    assert "terrible.py" in result.failing_files
    assert "good.py" not in result.failing_files
    print("OK: failing files")


def test_dimension_scores():
    """Aggregate dimension scores are calculated."""
    gate = CodeQualityGate()
    gate.score_file("a.py", _good_metrics())
    gate.score_file("b.py", _good_metrics())

    result = gate.check_gate()
    assert "complexity" in result.dimension_scores
    assert "coverage" in result.dimension_scores
    assert result.dimension_scores["complexity"] == 100.0
    print("OK: dimension scores")


def test_get_file_score():
    """Retrieve a specific file's score."""
    gate = CodeQualityGate()
    gate.score_file("target.py", _good_metrics())

    info = gate.get_file_score("target.py")
    assert info is not None
    assert info["file_path"] == "target.py"
    assert info["overall_score"] > 0

    assert gate.get_file_score("nonexistent.py") is None
    print("OK: get file score")


def test_get_all_scores():
    """Get all file scores sorted by score."""
    gate = CodeQualityGate()
    gate.score_file("good.py", _good_metrics())
    gate.score_file("bad.py", _bad_metrics())

    scores = gate.get_all_scores()
    assert len(scores) == 2
    assert scores[0]["overall_score"] < scores[1]["overall_score"]  # Worst first
    print("OK: get all scores")


def test_generate_report():
    """Generate quality report."""
    gate = CodeQualityGate()
    gate.score_file("good.py", _good_metrics())
    gate.score_file("bad.py", _bad_metrics())

    report = gate.generate_report()
    assert "gate_result" in report
    assert "summary" in report
    assert report["summary"]["total_files"] == 2
    assert report["summary"]["total_issues"] > 0
    assert len(report["worst_files"]) > 0
    assert len(report["best_files"]) > 0
    print("OK: generate report")


def test_set_threshold():
    """Update thresholds."""
    gate = CodeQualityGate(min_score=70.0)
    assert gate.min_score == 70.0

    gate.set_threshold(50.0, warning_score=60.0)
    assert gate.min_score == 50.0

    # Now bad files should pass with lower threshold
    gate.score_file("mediocre.py", {
        "complexity": 15,
        "lines": 200,
        "functions": 5,
        "docstring_coverage": 0.40,
        "test_coverage": 0.55,
        "lint_issues": 5,
        "security_issues": 0,
    })
    result = gate.check_gate()
    assert result.passed is True
    print("OK: set threshold")


def test_set_weight():
    """Custom dimension weights."""
    gate = CodeQualityGate()
    gate.set_weight("coverage", 0.50)  # Make coverage very important

    assert gate.weights["coverage"] == 0.50
    print("OK: set weight")


def test_gate_history():
    """Gate check history is tracked."""
    gate = CodeQualityGate()
    gate.score_file("a.py", _good_metrics())

    gate.check_gate()
    gate.check_gate()

    history = gate.get_history()
    assert len(history) >= 2
    assert "score" in history[0]
    assert "status" in history[0]
    print("OK: gate history")


def test_trend():
    """Quality trend detection."""
    gate = CodeQualityGate()

    # Not enough data
    trend = gate.get_trend()
    assert trend["trend"] == "insufficient_data"

    # Add some checks
    gate.score_file("a.py", _good_metrics())
    gate.check_gate()
    gate.check_gate()

    trend = gate.get_trend()
    assert trend["trend"] in ("improving", "declining", "stable")
    assert "current_score" in trend
    print("OK: trend")


def test_to_dict():
    """Serialization works."""
    gate = CodeQualityGate()
    fs = gate.score_file("test.py", _good_metrics())

    d = fs.to_dict()
    assert d["file_path"] == "test.py"
    assert "scores" in d
    assert "overall_score" in d

    result = gate.check_gate()
    rd = result.to_dict()
    assert "gate_id" in rd
    assert "passed" in rd
    print("OK: to dict")


def test_stats():
    """Quality gate stats."""
    gate = CodeQualityGate()
    gate.score_file("a.py", _good_metrics())
    gate.check_gate()

    gate.score_file("b.py", _bad_metrics())
    gate.check_gate()

    stats = gate.get_stats()
    assert stats["total_files_scored"] == 2
    assert stats["total_gate_checks"] == 2
    assert stats["current_file_count"] == 2
    print("OK: stats")


def test_reset():
    """Reset clears all data."""
    gate = CodeQualityGate()
    gate.score_file("a.py", _good_metrics())
    gate.check_gate()

    gate.reset()
    assert gate.get_stats()["total_files_scored"] == 0
    assert gate.get_all_scores() == []
    print("OK: reset")


def main():
    print("=== Code Quality Gate Tests ===\n")
    test_score_good_file()
    test_score_bad_file()
    test_score_dimensions()
    test_gate_pass()
    test_gate_fail()
    test_gate_warning()
    test_gate_skipped()
    test_failing_files()
    test_dimension_scores()
    test_get_file_score()
    test_get_all_scores()
    test_generate_report()
    test_set_threshold()
    test_set_weight()
    test_gate_history()
    test_trend()
    test_to_dict()
    test_stats()
    test_reset()
    print("\n=== ALL 19 TESTS PASSED ===")


if __name__ == "__main__":
    main()
