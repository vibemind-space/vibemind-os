"""
Quick test to verify ConvergenceMetrics has test_pass_rate attribute.
"""
from src.mind.shared_state import ConvergenceMetrics

def test_convergence_metrics():
    """Test that test_pass_rate attribute exists and works."""
    metrics = ConvergenceMetrics(
        total_tests=10,
        tests_passed=8,
        tests_failed=2,
    )

    # Test the property exists
    try:
        pass_rate = metrics.test_pass_rate
        print(f"[PASS] test_pass_rate property exists")
        print(f"  Value: {pass_rate}%")
        assert pass_rate == 80.0, f"Expected 80.0, got {pass_rate}"
        print(f"[PASS] test_pass_rate returns correct value (80.0)")
    except AttributeError as e:
        print(f"[FAIL] test_pass_rate attribute missing: {e}")
        return False

    # Test the alias matches the original
    try:
        assert metrics.test_pass_rate == metrics.tests_passing_rate
        print(f"[PASS] test_pass_rate matches tests_passing_rate")
    except AssertionError:
        print(f"[FAIL] test_pass_rate doesn't match tests_passing_rate")
        return False

    # Test to_dict includes pass_rate
    try:
        metrics_dict = metrics.to_dict()
        assert "pass_rate" in metrics_dict["tests"]
        print(f"[PASS] to_dict() includes pass_rate in tests section")
        print(f"  Value: {metrics_dict['tests']['pass_rate']}%")
    except (KeyError, AssertionError) as e:
        print(f"[FAIL] to_dict() missing pass_rate: {e}")
        return False

    # Test edge case: no tests
    metrics_no_tests = ConvergenceMetrics()
    try:
        pass_rate_no_tests = metrics_no_tests.test_pass_rate
        assert pass_rate_no_tests == 100.0
        print(f"[PASS] test_pass_rate handles no tests correctly (returns 100.0)")
    except Exception as e:
        print(f"[FAIL] test_pass_rate failed on no tests: {e}")
        return False

    print("\n[SUCCESS] All tests passed!")
    return True

if __name__ == "__main__":
    success = test_convergence_metrics()
    exit(0 if success else 1)
