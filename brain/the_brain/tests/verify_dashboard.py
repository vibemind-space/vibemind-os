"""
Dashboard Verification Script

Automated verification of oscillator API endpoints.
Run this while brain_dashboard_server.py is running on port 5004.

Usage:
    python tests/verify_dashboard.py

Requirements:
    - brain_dashboard_server.py running on localhost:5004
    - requests library installed
"""

import sys
import time
import json
import requests
from typing import Dict, Any, List, Tuple

# Configuration
BASE_URL = "http://localhost:5004"
TIMEOUT = 10


def make_request(method: str, endpoint: str, data: Dict = None) -> Tuple[int, Dict]:
    """Make HTTP request and return status code and response."""
    url = f"{BASE_URL}{endpoint}"

    try:
        if method == "GET":
            response = requests.get(url, timeout=TIMEOUT)
        elif method == "POST":
            response = requests.post(url, json=data, timeout=TIMEOUT)
        else:
            return -1, {"error": f"Unknown method: {method}"}

        try:
            return response.status_code, response.json()
        except json.JSONDecodeError:
            return response.status_code, {"raw": response.text[:200]}

    except requests.exceptions.ConnectionError:
        return -1, {"error": "Connection refused - is the server running?"}
    except requests.exceptions.Timeout:
        return -1, {"error": "Request timed out"}
    except Exception as e:
        return -1, {"error": str(e)}


def print_result(name: str, status: int, expected: int, response: Dict):
    """Print test result with formatting."""
    success = status == expected
    icon = "[PASS]" if success else "[FAIL]"
    color = "\033[92m" if success else "\033[91m"
    reset = "\033[0m"

    print(f"{color}{icon}{reset} {name}")
    print(f"      Status: {status} (expected {expected})")

    if not success or status != 200:
        print(f"      Response: {json.dumps(response, indent=2)[:200]}")

    return success


def test_oscillator_health():
    """Test oscillator health endpoint."""
    status, response = make_request("GET", "/api/oscillator/health")
    success = print_result("Oscillator Health", status, 200, response)

    if success:
        assert response.get('status') == 'healthy', "Health status not healthy"
        assert 'router_initialized' in response, "Missing router_initialized"
        print(f"      Router: {response.get('router_initialized')}")
        print(f"      Ollama: {response.get('using_ollama')}")
        print(f"      Mamba: {response.get('using_mamba')}")

    return success


def test_oscillator_state():
    """Test oscillator state endpoint."""
    status, response = make_request("GET", "/api/oscillator/state")
    success = print_result("Oscillator State", status, 200, response)

    if success:
        channels = response.get('channels', {})
        assert 'A' in channels, "Missing channel A"
        assert 'B' in channels, "Missing channel B"
        assert 'C' in channels, "Missing channel C"

        print(f"      A: {channels['A']['amplitude']:.3f}")
        print(f"      B: {channels['B']['amplitude']:.3f}")
        print(f"      C: {channels['C']['amplitude']:.3f}")
        print(f"      Dominant: {response.get('dominant')}")

    return success


def test_oscillator_history():
    """Test oscillator history endpoint."""
    status, response = make_request("GET", "/api/oscillator/history")
    success = print_result("Oscillator History", status, 200, response)

    if success:
        history = response.get('history', [])
        print(f"      History entries: {len(history)}")

    return success


def test_oscillator_stats():
    """Test oscillator stats endpoint."""
    status, response = make_request("GET", "/api/oscillator/stats")
    success = print_result("Oscillator Stats", status, 200, response)

    if success:
        token_stats = response.get('token_adapter', {})
        print(f"      Tokens processed: {token_stats.get('tokens_processed', 0)}")
        print(f"      Using Ollama: {response.get('using_ollama')}")

    return success


def test_process_tokens():
    """Test token processing endpoint."""
    data = {"text": "Deploy the nginx container but not to production"}
    status, response = make_request("POST", "/api/oscillator/tokens", data)
    success = print_result("Process Tokens", status, 200, response)

    if success:
        tokens = response.get('tokens_extracted', [])
        print(f"      Tokens: {tokens}")
        print(f"      Count: {response.get('token_count')}")
        print(f"      Dominant after: {response.get('state_after', {}).get('dominant')}")

    return success


def test_process_tokens_empty():
    """Test token processing with empty text."""
    data = {"text": ""}
    status, response = make_request("POST", "/api/oscillator/tokens", data)
    success = print_result("Process Empty Tokens", status, 400, response)
    return success


def test_checkpoint_operations():
    """Test checkpoint save/list/restore operations."""
    results = []

    # Save checkpoint
    data = {"name": "test_verification_checkpoint"}
    status, response = make_request("POST", "/api/oscillator/checkpoint", data)
    success = print_result("Save Checkpoint", status, 200, response)
    results.append(success)

    if success:
        print(f"      Path: {response.get('path')}")

    # List checkpoints
    status, response = make_request("GET", "/api/oscillator/checkpoints")
    success = print_result("List Checkpoints", status, 200, response)
    results.append(success)

    if success:
        checkpoints = response.get('checkpoints', [])
        print(f"      Count: {len(checkpoints)}")
        if checkpoints:
            print(f"      Latest: {checkpoints[0].get('name')}")

    # Restore checkpoint
    data = {"name": "test_verification_checkpoint"}
    status, response = make_request("POST", "/api/oscillator/restore", data)
    success = print_result("Restore Checkpoint", status, 200, response)
    results.append(success)

    return all(results)


def test_restore_nonexistent():
    """Test restoring nonexistent checkpoint."""
    data = {"name": "nonexistent_checkpoint_12345"}
    status, response = make_request("POST", "/api/oscillator/restore", data)
    success = print_result("Restore Nonexistent", status, 404, response)
    return success


def test_oscillator_reset():
    """Test oscillator reset endpoint."""
    status, response = make_request("POST", "/api/oscillator/reset")
    success = print_result("Oscillator Reset", status, 200, response)

    if success:
        print(f"      Status: {response.get('status')}")

    return success


def test_route_events():
    """Test routing events through oscillator."""
    data = {
        "events": [
            {"role": "user", "text": "Please deploy the application"}
        ],
        "task": "Verification Test"
    }
    status, response = make_request("POST", "/api/oscillator/route", data)
    success = print_result("Route Events", status, 200, response)

    if success:
        print(f"      Should Execute: {response.get('should_execute')}")
        print(f"      Tool: {response.get('tool_name')}")
        print(f"      Confidence: {response.get('timing_confidence'):.3f}")

    return success


def test_route_empty_events():
    """Test routing with empty events."""
    data = {"events": []}
    status, response = make_request("POST", "/api/oscillator/route", data)
    success = print_result("Route Empty Events", status, 400, response)
    return success


def run_all_tests():
    """Run all verification tests."""
    print("=" * 60)
    print("  BRAIN DASHBOARD OSCILLATOR API VERIFICATION")
    print("=" * 60)
    print(f"\nTarget: {BASE_URL}")
    print()

    tests = [
        ("Health Check", test_oscillator_health),
        ("State", test_oscillator_state),
        ("History", test_oscillator_history),
        ("Stats", test_oscillator_stats),
        ("Process Tokens", test_process_tokens),
        ("Process Empty", test_process_tokens_empty),
        ("Checkpoints", test_checkpoint_operations),
        ("Restore Nonexistent", test_restore_nonexistent),
        ("Route Events", test_route_events),
        ("Route Empty", test_route_empty_events),
        ("Reset", test_oscillator_reset),
    ]

    results = []
    for name, test_func in tests:
        print(f"\n--- {name} ---")
        try:
            result = test_func()
            results.append(result)
        except AssertionError as e:
            print(f"\033[91m[FAIL]\033[0m Assertion failed: {e}")
            results.append(False)
        except Exception as e:
            print(f"\033[91m[ERROR]\033[0m {e}")
            results.append(False)

    # Summary
    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    success_rate = (passed / total) * 100 if total > 0 else 0

    if passed == total:
        print(f"\033[92m  ALL TESTS PASSED ({passed}/{total})\033[0m")
    else:
        print(f"\033[91m  TESTS: {passed}/{total} passed ({success_rate:.1f}%)\033[0m")

    print("=" * 60)

    return passed == total


def main():
    """Main entry point."""
    # Check if server is running
    print("Checking server connectivity...")
    status, response = make_request("GET", "/api/oscillator/health")

    if status == -1:
        print("\n\033[91mERROR: Cannot connect to server\033[0m")
        print(f"Make sure brain_dashboard_server.py is running on {BASE_URL}")
        print("\nTo start the server:")
        print("  cd the_brain")
        print("  python web/brain_dashboard_server.py")
        sys.exit(1)

    print("Server is running!\n")

    # Run tests
    success = run_all_tests()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
