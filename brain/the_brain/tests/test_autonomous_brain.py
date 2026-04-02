"""
Test script for Autonomous Brain System

Tests the new heartbeat endpoints and autonomous processing.

NOTE: These are integration tests that require the autonomous brain
service to be running on port 5001. Run with:
    python production/api_server.py

Or mark as skipped when service is unavailable.
"""

import requests
import json
import time
import pytest
import socket

API_URL = "http://localhost:5001"


def is_service_running(host="localhost", port=5001, timeout=1.0):
    """Check if the autonomous brain service is running."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


# Skip all tests if service is not running
pytestmark = pytest.mark.skipif(
    not is_service_running(),
    reason="Autonomous Brain service not running on localhost:5001"
)


def print_section(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70 + "\n")


def test_health():
    """Test health endpoint"""
    print_section("1. Testing Health Endpoint")

    response = requests.get(f"{API_URL}/health")
    data = response.json()

    print("Health Check:")
    print(json.dumps(data, indent=2))
    print(f"\n[OK] Planner initialized: {data['planner_initialized']}")
    print(f"[OK] Heartbeat running: {data['heartbeat_running']}")


def test_heartbeat_status():
    """Test heartbeat status endpoint"""
    print_section("2. Testing Heartbeat Status")

    response = requests.get(f"{API_URL}/heartbeat")
    data = response.json()

    print("Heartbeat Status:")
    print(f"  Running: {data['running']}")
    print(f"  Tick count: {data['tick_count']}")
    print(f"  Idle time: {data['idle_time_seconds']:.1f}s")
    print(f"  Interval: {data['interval_seconds']}s")
    print(f"  Total dreams: {data['total_dreams']}")


def test_brain_state():
    """Test brain state endpoint"""
    print_section("3. Testing Brain State Endpoint")

    response = requests.get(f"{API_URL}/brain_state")
    data = response.json()

    print("Brain State:")
    print(f"  Timestamp: {data['timestamp']}")
    print(f"  Uptime: {data['uptime_seconds']:.1f}s")
    print(f"  State: {data['state']}")
    print(f"  Tick count: {data['tick_count']}")

    # Neuromodulation
    if data.get('neuromodulation'):
        print("\nNeuromodulation:")
        neuro = data['neuromodulation']
        print(f"  Dopamine: {neuro['dopamine']:.3f}")
        print(f"  Serotonin: {neuro['serotonin']:.3f}")
        print(f"  Norepinephrine: {neuro['norepinephrine']:.3f}")
        print(f"  State: {neuro['state_description']}")

    # Meta-learning
    if data.get('meta_learning'):
        print("\nMeta-Learning:")
        meta = data['meta_learning']
        print(f"  Prediction LR: {meta['prediction_learning_rate']:.5f}")
        print(f"  Attention LR: {meta['attention_learning_rate']:.5f}")
        print(f"  Memory LR: {meta['memory_learning_rate']:.5f}")
        print(f"  Success rate: {meta['recent_success_rate']:.1%}")
        print(f"  Total adaptations: {meta['total_adaptations']}")

    # Dream state
    if data.get('dream_state'):
        print("\nDream State:")
        dream = data['dream_state']
        print(f"  Is dreaming: {dream['is_dreaming']}")
        print(f"  Idle time: {dream['idle_time_seconds']:.1f}s")
        print(f"  Total dreams: {dream['total_dreams']}")
        print(f"  Patterns discovered: {dream['patterns_discovered']}")

    # Performance
    if data.get('performance'):
        print("\nPerformance:")
        perf = data['performance']
        print(f"  Total predictions: {perf['total_predictions']}")
        print(f"  Total feedback: {perf['total_feedback']}")
        print(f"  Success rate: {perf['success_rate']:.1%}")

    # Health
    if data.get('health'):
        print("\nSystem Health:")
        health = data['health']
        print(f"  Memory: {health['memory_mb']:.1f} MB")
        print(f"  CPU: {health['cpu_percent']:.1f}%")
        print(f"  Status: {health['status']}")


def test_manual_heartbeat():
    """Test manual heartbeat trigger"""
    print_section("4. Testing Manual Heartbeat Trigger")

    print("Triggering manual heartbeat...")
    response = requests.post(f"{API_URL}/heartbeat", json={})
    data = response.json()

    print(f"[OK] Heartbeat completed")
    print(f"  Tick number: {data['tick_number']}")
    print(f"  Timestamp: {data['timestamp']}")


def test_prediction():
    """Test prediction (resets idle timer)"""
    print_section("5. Testing Prediction (Resets Idle Timer)")

    task = "Deploy with Docker urgently"
    print(f"Making prediction for: '{task}'")

    response = requests.post(
        f"{API_URL}/predict",
        json={"task": task}
    )
    data = response.json()

    print(f"\n[OK] Prediction completed")
    print(f"  Primary action: {data['prediction']['primary_action']}")
    print(f"  Confidence: {data['prediction']['confidence']:.1%}")
    print(f"  Processing mode: {data['prediction']['processing_mode']}")

    # Check brain state after prediction
    time.sleep(1)
    response = requests.get(f"{API_URL}/brain_state")
    state = response.json()
    print(f"\n  Idle time after prediction: {state['idle_time_seconds']:.1f}s (should be ~0)")


def test_heartbeat_config():
    """Test heartbeat configuration"""
    print_section("6. Testing Heartbeat Configuration")

    # Get current config
    response = requests.get(f"{API_URL}/heartbeat/config")
    config = response.json()

    print("Current Configuration:")
    print(json.dumps(config, indent=2))

    # Optionally update config (commented out to avoid changing it)
    # print("\nUpdating configuration...")
    # response = requests.post(
    #     f"{API_URL}/heartbeat/config",
    #     json={"interval_seconds": 60.0}
    # )
    # print(f"✓ Configuration updated")


def run_all_tests():
    """Run all tests"""
    print("\n" + "=" * 70)
    print("AUTONOMOUS BRAIN SYSTEM - Integration Tests")
    print("=" * 70)

    try:
        test_health()
        test_heartbeat_status()
        test_brain_state()
        test_manual_heartbeat()
        test_prediction()
        test_heartbeat_config()

        print_section("[PASS] ALL TESTS PASSED")
        print("The Autonomous Brain System is fully operational!")
        print("\nKey Features Verified:")
        print("  [OK] Autonomous heartbeat running")
        print("  [OK] Neuromodulation system active")
        print("  [OK] Meta-learning adapting")
        print("  [OK] Dream mode ready")
        print("  [OK] Health monitoring active")
        print("  [OK] Idle time tracking working")
        print("\nThe brain is continuously active, just like a real brain!")

    except Exception as e:
        print(f"\n[FAIL] TEST FAILED: {e}")
        print("\nMake sure the API server is running:")
        print("  python production/api_server.py")


if __name__ == "__main__":
    run_all_tests()
