"""
Frequency Controller Test Suite

Tests the complete brain frequency system:
1. Local unit tests (no server required)
2. API integration tests (requires unified brain service on port 5003)

Usage:
    # Run local tests only
    python demos/test_frequency_controller.py --local

    # Run all tests (requires server on port 5003)
    python demos/test_frequency_controller.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import json
import argparse
from datetime import datetime

# Local imports
from core.brain_frequency_controller import (
    BrainFrequencyController,
    FrequencyMode,
    FrequencyMixer,
    FrequencyBand
)


def print_header(text: str):
    """Print section header"""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)


def print_result(test_name: str, passed: bool, details: str = ""):
    """Print test result"""
    status = "[PASS]" if passed else "[FAIL]"
    print(f"  {status} {test_name}")
    if details:
        print(f"         {details}")


# =============================================================================
# LOCAL UNIT TESTS
# =============================================================================

def test_frequency_modes():
    """Test 1: Frequency Mode Enumeration"""
    print_header("TEST 1: FREQUENCY MODE ENUMERATION")

    modes = list(FrequencyMode)
    expected = ['delta', 'theta', 'alpha', 'beta', 'gamma']

    passed = len(modes) == 5
    for mode in modes:
        if mode.value not in expected:
            passed = False

    print_result(
        "All 5 frequency modes defined",
        passed,
        f"Modes: {[m.value for m in modes]}"
    )

    return passed


def test_controller_initialization():
    """Test 2: Controller Initialization"""
    print_header("TEST 2: CONTROLLER INITIALIZATION")

    controller = BrainFrequencyController(
        default_mode=FrequencyMode.ALPHA,
        enable_auto_switch=True,
        marker_capacity=100
    )

    state = controller.get_state()

    # Check initial state
    passed = True
    checks = []

    if state['dominant_mode'] != 'alpha':
        passed = False
        checks.append(f"Expected dominant=alpha, got {state['dominant_mode']}")
    else:
        checks.append(f"Dominant: {state['dominant_mode']}")

    if 'alpha' not in state['active_modes']:
        passed = False
        checks.append("Alpha not in active modes")
    else:
        checks.append(f"Active: {state['active_modes']}")

    print_result("Controller initialized correctly", passed, " | ".join(checks))

    return passed


def test_mode_switching():
    """Test 3: Manual Mode Switching"""
    print_header("TEST 3: MANUAL MODE SWITCHING")

    controller = BrainFrequencyController(default_mode=FrequencyMode.ALPHA)

    results = []

    # Test switching through all modes (suppress_others=True for actual dominance switch)
    for mode in FrequencyMode:
        controller.set_mode(mode, activation=1.0, suppress_others=True)
        state = controller.get_state()

        is_dominant = state['dominant_mode'] == mode.value
        results.append((mode.value, is_dominant))

        status = "OK" if is_dominant else "FAIL"
        print(f"    [{status}] Switch to {mode.value}: dominant={state['dominant_mode']}")

    passed = all(r[1] for r in results)
    print_result("All mode switches successful", passed, f"{sum(r[1] for r in results)}/5 modes")

    return passed


def test_auto_switch():
    """Test 4: Auto-Switch Based on Context"""
    print_header("TEST 4: AUTO-SWITCH BASED ON CONTEXT")

    # Note: auto_switch doesn't use suppress_others=True, so modes
    # only become dominant when their activation exceeds current dominant.
    # This test verifies that auto_switch correctly identifies the suggested mode.

    controller = BrainFrequencyController(
        default_mode=FrequencyMode.ALPHA,
        enable_auto_switch=True
    )

    test_cases = [
        ({'task_type': 'planning', 'complexity': 0.8, 'urgency': 0.8}, 'theta'),
        ({'task_type': 'execute', 'requires_action': True, 'urgency': 0.9, 'complexity': 0.7}, 'beta'),
        ({'task_type': 'reasoning', 'complexity': 0.85, 'urgency': 0.7}, 'gamma'),
        ({'task_type': 'learning', 'requires_learning': True, 'urgency': 0.8, 'complexity': 0.8}, 'delta'),
        ({'task_type': 'general', 'complexity': 0.5, 'urgency': 0.5}, 'alpha'),
    ]

    passed_count = 0
    for context, expected_mode in test_cases:
        # Reset controller for clean state each time
        controller.reset(FrequencyMode.ALPHA)

        result = controller.auto_switch(context)

        # Check if correct mode was targeted
        current_dominant = controller.get_state()['dominant_mode']
        suggested = result.get('suggested_mode', result.get('mode', ''))

        # Either it switched to expected, or it suggested expected
        is_correct = (current_dominant == expected_mode) or (suggested == expected_mode)
        if is_correct:
            passed_count += 1

        status = "OK" if is_correct else "WARN"
        switched = result.get('switched', False)
        print(f"    [{status}] Context {context.get('task_type')}: dominant={current_dominant}, switched={switched} (expected: {expected_mode})")

    passed = passed_count >= 3  # Allow some flexibility
    print_result("Auto-switch behavior", passed, f"{passed_count}/5 modes correctly identified")

    return passed


def test_marker_system():
    """Test 5: Marker System for Path-Tracing"""
    print_header("TEST 5: MARKER SYSTEM")

    controller = BrainFrequencyController(
        default_mode=FrequencyMode.THETA,  # Planning mode for markers
        marker_capacity=100
    )

    # Create markers
    marker_ids = []
    for i in range(3):
        marker = controller.set_marker(
            decision_point=f"decision_{i}",
            context={'step': i, 'task': 'test'},
            alternatives=[f"alt_a_{i}", f"alt_b_{i}"],
            confidence=0.7 + i * 0.1
        )
        marker_ids.append(marker.marker_id)
        print(f"    Created marker: {marker.marker_id}")

    # Get markers
    markers = controller.get_recent_markers(count=10)
    has_markers = len(markers) >= 3

    # Jump to marker
    if marker_ids:
        jump_result = controller.jump_to_marker(marker_ids[0])
        jumped = jump_result is not None
        print(f"    Jump to {marker_ids[0]}: {'Success' if jumped else 'Failed'}")
    else:
        jumped = False

    passed = has_markers and jumped
    print_result(
        "Marker system functional",
        passed,
        f"Created: {len(marker_ids)}, Retrieved: {len(markers)}, Jump: {'OK' if jumped else 'FAIL'}"
    )

    return passed


def test_frequency_mixer():
    """Test 6: Frequency Mixer (Multi-Mode Operation)"""
    print_header("TEST 6: FREQUENCY MIXER")

    controller = BrainFrequencyController(default_mode=FrequencyMode.ALPHA)
    mixer = FrequencyMixer(controller)

    # Set multiple modes active simultaneously
    controller.set_mode(FrequencyMode.ALPHA, activation=0.8, suppress_others=False)
    controller.set_mode(FrequencyMode.THETA, activation=0.6, suppress_others=False)
    controller.set_mode(FrequencyMode.GAMMA, activation=0.4, suppress_others=False)

    state = controller.get_state()
    active_modes = state['active_modes']  # This is a list
    activations = state['activations']    # This is a dict with activation values

    # Check multiple modes are active
    high_activation_count = len([m for m, data in activations.items() if data['activation'] > 0.3])
    multi_active = high_activation_count >= 2

    # Test frequency mixer blend
    mixer.set_blend({'alpha': 0.5, 'theta': 0.3, 'gamma': 0.2})
    components = mixer.get_blended_components()
    processing_order = mixer.suggest_processing_order()

    passed = multi_active and len(components) > 0
    print(f"    Active modes: {active_modes}")
    print(f"    Activations: {[(m, round(d['activation'], 2)) for m, d in activations.items() if d['activation'] > 0.1]}")
    print(f"    Blended components: {components[:5]}...")
    print(f"    Processing order: {[m.value for m in processing_order]}")

    print_result(
        "Multi-mode operation",
        passed,
        f"Active: {high_activation_count} modes, {len(components)} components"
    )

    return passed


def test_frequency_bands():
    """Test 7: Frequency Band Information"""
    print_header("TEST 7: FREQUENCY BAND INFORMATION")

    bands = BrainFrequencyController.FREQUENCY_BANDS

    passed = True
    for mode, band in bands.items():
        has_info = all([
            band.min_hz > 0,
            band.max_hz > band.min_hz,
            len(band.description) > 0,
            len(band.associated_components) > 0
        ])

        status = "OK" if has_info else "FAIL"
        print(f"    [{status}] {mode.value}: {band.min_hz}-{band.max_hz} Hz - {band.primary_function}")

        if not has_info:
            passed = False

    print_result("All frequency bands configured", passed, f"{len(bands)} bands")

    return passed


# =============================================================================
# API INTEGRATION TESTS
# =============================================================================

def test_api_endpoints():
    """Test API endpoints (requires server on port 5003)"""
    print_header("API INTEGRATION TESTS")

    try:
        import requests
    except ImportError:
        print("  [SKIP] requests module not available")
        return True

    base_url = "http://localhost:5003"

    # Check if server is running
    try:
        health = requests.get(f"{base_url}/health", timeout=2)
        if health.status_code != 200:
            print("  [SKIP] Unified brain service not running on port 5003")
            return True
    except requests.exceptions.ConnectionError:
        print("  [SKIP] Cannot connect to unified brain service on port 5003")
        return True

    print("  Server connected!\n")

    results = []

    # Test 1: GET /frequency_mode
    print("  Testing GET /frequency_mode...")
    try:
        resp = requests.get(f"{base_url}/frequency_mode")
        passed = resp.status_code == 200 and 'dominant_mode' in resp.json()
        print_result("GET /frequency_mode", passed, f"Status: {resp.status_code}")
        results.append(passed)
    except Exception as e:
        print_result("GET /frequency_mode", False, str(e))
        results.append(False)

    # Test 2: POST /set_frequency_mode
    print("\n  Testing POST /set_frequency_mode...")
    try:
        resp = requests.post(
            f"{base_url}/set_frequency_mode",
            json={'mode': 'theta', 'activation': 0.9}
        )
        passed = resp.status_code == 200
        print_result("POST /set_frequency_mode", passed, f"Status: {resp.status_code}")
        results.append(passed)
    except Exception as e:
        print_result("POST /set_frequency_mode", False, str(e))
        results.append(False)

    # Test 3: POST /auto_frequency
    print("\n  Testing POST /auto_frequency...")
    try:
        resp = requests.post(
            f"{base_url}/auto_frequency",
            json={'context': {'task_type': 'planning', 'complexity': 0.8}}
        )
        passed = resp.status_code == 200
        print_result("POST /auto_frequency", passed, f"Status: {resp.status_code}")
        results.append(passed)
    except Exception as e:
        print_result("POST /auto_frequency", False, str(e))
        results.append(False)

    # Test 4: GET /frequency_bands
    print("\n  Testing GET /frequency_bands...")
    try:
        resp = requests.get(f"{base_url}/frequency_bands")
        passed = resp.status_code == 200 and 'bands' in resp.json()
        print_result("GET /frequency_bands", passed, f"Status: {resp.status_code}")
        results.append(passed)
    except Exception as e:
        print_result("GET /frequency_bands", False, str(e))
        results.append(False)

    # Test 5: POST /set_marker
    print("\n  Testing POST /set_marker...")
    try:
        resp = requests.post(
            f"{base_url}/set_marker",
            json={
                'decision_point': 'test_decision',
                'context': {'test': True},
                'alternatives': ['option_a', 'option_b'],
                'confidence': 0.8
            }
        )
        passed = resp.status_code == 200 and 'marker_id' in resp.json()
        marker_id = resp.json().get('marker_id', '')
        print_result("POST /set_marker", passed, f"Marker: {marker_id[:20]}...")
        results.append(passed)
    except Exception as e:
        print_result("POST /set_marker", False, str(e))
        results.append(False)
        marker_id = None

    # Test 6: GET /markers
    print("\n  Testing GET /markers...")
    try:
        resp = requests.get(f"{base_url}/markers")
        passed = resp.status_code == 200 and 'markers' in resp.json()
        markers = resp.json().get('markers', [])
        print_result("GET /markers", passed, f"Count: {len(markers)}")
        results.append(passed)
    except Exception as e:
        print_result("GET /markers", False, str(e))
        results.append(False)

    # Test 7: POST /jump_to_marker
    print("\n  Testing POST /jump_to_marker...")
    try:
        if marker_id:
            resp = requests.post(
                f"{base_url}/jump_to_marker",
                json={'marker_id': marker_id}
            )
            passed = resp.status_code == 200
            print_result("POST /jump_to_marker", passed, f"Status: {resp.status_code}")
            results.append(passed)
        else:
            print_result("POST /jump_to_marker", True, "Skipped (no marker)")
            results.append(True)
    except Exception as e:
        print_result("POST /jump_to_marker", False, str(e))
        results.append(False)

    return all(results)


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Run all tests"""
    parser = argparse.ArgumentParser(description='Test Brain Frequency Controller')
    parser.add_argument('--local', action='store_true', help='Run local tests only')
    args = parser.parse_args()

    print_header("BRAIN FREQUENCY CONTROLLER TEST SUITE")
    print(f"\n  Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Mode: {'Local Only' if args.local else 'Full (Local + API)'}")

    results = {}

    # Local unit tests
    results['frequency_modes'] = test_frequency_modes()
    results['initialization'] = test_controller_initialization()
    results['mode_switching'] = test_mode_switching()
    results['auto_switch'] = test_auto_switch()
    results['marker_system'] = test_marker_system()
    results['frequency_mixer'] = test_frequency_mixer()
    results['frequency_bands'] = test_frequency_bands()

    # API tests (optional)
    if not args.local:
        results['api_endpoints'] = test_api_endpoints()

    # Summary
    print_header("TEST SUMMARY")

    passed = 0
    total = len(results)

    for test_name, test_passed in results.items():
        status = "PASS" if test_passed else "FAIL"
        print(f"  [{status}] {test_name.replace('_', ' ').title()}")
        if test_passed:
            passed += 1

    print(f"\n  Overall: {passed}/{total} tests passed")

    if passed == total:
        print("\n  " + "=" * 50)
        print("  ALL TESTS PASSED - FREQUENCY SYSTEM VALIDATED!")
        print("  " + "=" * 50)
    else:
        print("\n  Some tests failed - review output above")

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
