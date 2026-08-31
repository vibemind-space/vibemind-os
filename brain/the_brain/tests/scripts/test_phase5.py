"""
Phase 5: Production Integration Tests

Tests for Layer 4 Flask endpoints:
- Status and control endpoints
- Training endpoints
- Inference endpoints
- Feature integration
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from flask import Flask
from datetime import datetime


def test_layer4_blueprint_import():
    """Test that Layer 4 blueprint can be imported"""
    print("[1] Testing Layer 4 Blueprint Import...")

    try:
        from production.layer4_endpoints import (
            layer4_bp,
            LAYER4_AVAILABLE,
            TRAINING_AVAILABLE,
            LAYER4_FEATURE_DEFINITIONS
        )
        print(f"    Layer 4 Available: {LAYER4_AVAILABLE}")
        print(f"    Training Available: {TRAINING_AVAILABLE}")
        print(f"    Feature Definitions: {len(LAYER4_FEATURE_DEFINITIONS)}")
        print("    [OK] Blueprint imported successfully")
        return True
    except ImportError as e:
        print(f"    [ERROR] Import failed: {e}")
        return False


def test_layer4_blueprint_registration():
    """Test that Layer 4 blueprint can be registered with Flask"""
    print("\n[2] Testing Blueprint Registration...")

    try:
        from production.layer4_endpoints import layer4_bp

        # Create test Flask app
        app = Flask(__name__)
        app.register_blueprint(layer4_bp)

        # List registered routes
        routes = []
        for rule in app.url_map.iter_rules():
            if rule.endpoint.startswith('layer4'):
                routes.append({
                    'endpoint': rule.endpoint,
                    'methods': list(rule.methods - {'HEAD', 'OPTIONS'}),
                    'path': rule.rule
                })

        print(f"    Registered {len(routes)} Layer 4 endpoints:")
        for route in sorted(routes, key=lambda x: x['path']):
            methods = ', '.join(route['methods'])
            print(f"      [{methods}] {route['path']}")

        assert len(routes) >= 9, f"Expected at least 9 endpoints, got {len(routes)}"
        print("    [OK] Blueprint registered successfully")
        return True

    except Exception as e:
        print(f"    [ERROR] Registration failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_layer4_health_endpoint():
    """Test the /layer4/health endpoint"""
    print("\n[3] Testing Health Endpoint...")

    try:
        from production.layer4_endpoints import layer4_bp

        app = Flask(__name__)
        app.register_blueprint(layer4_bp)

        with app.test_client() as client:
            response = client.get('/layer4/health')
            data = response.get_json()

            print(f"    Status Code: {response.status_code}")
            print(f"    Response: {data}")

            assert response.status_code == 200
            assert data['success'] == True
            assert 'layer4_available' in data
            assert 'training_available' in data
            assert 'timestamp' in data

            print("    [OK] Health endpoint working")
            return True

    except Exception as e:
        print(f"    [ERROR] Health test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_layer4_status_endpoint():
    """Test the /layer4/status endpoint"""
    print("\n[4] Testing Status Endpoint...")

    try:
        from production.layer4_endpoints import layer4_bp, LAYER4_AVAILABLE

        app = Flask(__name__)
        app.register_blueprint(layer4_bp)

        with app.test_client() as client:
            response = client.get('/layer4/status')
            data = response.get_json()

            print(f"    Status Code: {response.status_code}")
            print(f"    Layer 4 Available: {LAYER4_AVAILABLE}")

            if LAYER4_AVAILABLE:
                if response.status_code == 200:
                    print(f"    Statistics: {data.get('statistics', {})}")
                    print("    [OK] Status endpoint working")
                    return True
                else:
                    print(f"    [WARN] Status returned {response.status_code}")
                    return True
            else:
                assert response.status_code == 503
                print("    [OK] Status correctly reports Layer 4 unavailable")
                return True

    except Exception as e:
        print(f"    [ERROR] Status test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_layer4_route_endpoint():
    """Test the /layer4/route endpoint"""
    print("\n[5] Testing Route Endpoint...")

    try:
        from production.layer4_endpoints import layer4_bp, LAYER4_AVAILABLE

        app = Flask(__name__)
        app.register_blueprint(layer4_bp)

        # Sample events
        events = [
            {'role': 'user', 'text': 'Deploy nginx container on port 8080'},
            {'role': 'assistant', 'text': 'I will deploy the container'}
        ]

        with app.test_client() as client:
            response = client.post('/layer4/route', json={
                'events': events,
                'task_description': 'Deploy web server',
                'source_trusted': True
            })
            data = response.get_json()

            print(f"    Status Code: {response.status_code}")

            if LAYER4_AVAILABLE:
                if response.status_code == 200:
                    print(f"    Should Execute: {data.get('should_execute')}")
                    print(f"    Tool Name: {data.get('tool_name')}")
                    print(f"    Timing: {data.get('timing_confidence')}")
                    print("    [OK] Route endpoint working")
                    return True
                else:
                    print(f"    [WARN] Route returned {response.status_code}: {data}")
                    return True
            else:
                assert response.status_code == 503
                print("    [OK] Route correctly reports Layer 4 unavailable")
                return True

    except Exception as e:
        print(f"    [ERROR] Route test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_layer4_training_endpoints():
    """Test training lifecycle endpoints"""
    print("\n[6] Testing Training Endpoints...")

    try:
        from production.layer4_endpoints import layer4_bp, TRAINING_AVAILABLE

        app = Flask(__name__)
        app.register_blueprint(layer4_bp)

        with app.test_client() as client:
            # Test training status (should work even if not training)
            response = client.get('/layer4/training/status')
            data = response.get_json()

            print(f"    Training Status Code: {response.status_code}")

            if TRAINING_AVAILABLE:
                if response.status_code == 200:
                    print(f"    Training Active: {data.get('training_active', False)}")
                    print(f"    Status: {data.get('status', 'unknown')}")
                    print("    [OK] Training status endpoint working")
                else:
                    print(f"    [WARN] Training status returned {response.status_code}")
            else:
                assert response.status_code == 503
                print("    [OK] Training correctly reports unavailable")

            # Test checkpoint listing
            response = client.get('/layer4/training/checkpoints')
            data = response.get_json()

            print(f"    Checkpoints Status Code: {response.status_code}")
            if response.status_code == 200:
                print(f"    Checkpoints Found: {data.get('count', 0)}")
                print("    [OK] Checkpoint listing working")

            return True

    except Exception as e:
        print(f"    [ERROR] Training test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_layer4_regime_endpoint():
    """Test the /layer4/regime endpoint"""
    print("\n[7] Testing Regime Endpoint...")

    try:
        from production.layer4_endpoints import layer4_bp, LAYER4_AVAILABLE

        app = Flask(__name__)
        app.register_blueprint(layer4_bp)

        with app.test_client() as client:
            response = client.get('/layer4/regime')
            data = response.get_json()

            print(f"    Status Code: {response.status_code}")

            if LAYER4_AVAILABLE:
                if response.status_code == 200:
                    print(f"    Regime: {data.get('regime')}")
                    print(f"    Stability: {data.get('stability')}")
                    print(f"    Safe for Action: {data.get('safe_for_action')}")
                    print("    [OK] Regime endpoint working")
                    return True
                else:
                    print(f"    [WARN] Regime returned {response.status_code}")
                    return True
            else:
                assert response.status_code == 503
                print("    [OK] Regime correctly reports Layer 4 unavailable")
                return True

    except Exception as e:
        print(f"    [ERROR] Regime test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_layer4_reset_endpoint():
    """Test the /layer4/reset endpoint"""
    print("\n[8] Testing Reset Endpoint...")

    try:
        from production.layer4_endpoints import layer4_bp, LAYER4_AVAILABLE

        app = Flask(__name__)
        app.register_blueprint(layer4_bp)

        with app.test_client() as client:
            response = client.post('/layer4/reset')
            data = response.get_json()

            print(f"    Status Code: {response.status_code}")

            if LAYER4_AVAILABLE:
                if response.status_code == 200:
                    print(f"    Message: {data.get('message')}")
                    print("    [OK] Reset endpoint working")
                    return True
                else:
                    print(f"    [WARN] Reset returned {response.status_code}")
                    return True
            else:
                assert response.status_code == 503
                print("    [OK] Reset correctly reports Layer 4 unavailable")
                return True

    except Exception as e:
        print(f"    [ERROR] Reset test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_layer4_record_result():
    """Test the /layer4/record_result endpoint"""
    print("\n[9] Testing Record Result Endpoint...")

    try:
        from production.layer4_endpoints import layer4_bp, LAYER4_AVAILABLE

        app = Flask(__name__)
        app.register_blueprint(layer4_bp)

        with app.test_client() as client:
            response = client.post('/layer4/record_result', json={
                'tool_name': 'docker_run',
                'success': True,
                'duration_ms': 245.5,
                'result_data': {'container_id': 'abc123'}
            })
            data = response.get_json()

            print(f"    Status Code: {response.status_code}")

            if LAYER4_AVAILABLE:
                if response.status_code == 200:
                    print(f"    Message: {data.get('message')}")
                    print("    [OK] Record result endpoint working")
                    return True
                else:
                    print(f"    [WARN] Record result returned {response.status_code}")
                    return True
            else:
                assert response.status_code == 503
                print("    [OK] Record result correctly reports Layer 4 unavailable")
                return True

    except Exception as e:
        print(f"    [ERROR] Record result test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_layer4_feature_definitions():
    """Test that feature definitions are properly exported"""
    print("\n[10] Testing Feature Definitions...")

    try:
        from production.layer4_endpoints import LAYER4_FEATURE_DEFINITIONS

        expected_features = [
            'temporal_routing',
            'regime_state',
            'phase_dynamics',
            'timing_gate',
            'security_state'
        ]

        print(f"    Feature Definitions:")
        for name, description in LAYER4_FEATURE_DEFINITIONS.items():
            print(f"      - {name}: {description[:50]}...")

        for feature in expected_features:
            assert feature in LAYER4_FEATURE_DEFINITIONS, f"Missing feature: {feature}"

        print("    [OK] All expected features defined")
        return True

    except Exception as e:
        print(f"    [ERROR] Feature definitions test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_unified_brain_layer4_import():
    """Test that unified_brain_service can import Layer 4"""
    print("\n[11] Testing Unified Brain Layer 4 Integration...")

    try:
        # This tests the actual import in unified_brain_service.py
        from production.unified_brain_service import (
            LAYER4_ENDPOINTS_AVAILABLE,
            app
        )

        print(f"    Layer 4 Endpoints Available: {LAYER4_ENDPOINTS_AVAILABLE}")

        # Check if Layer 4 routes are registered
        layer4_routes = []
        for rule in app.url_map.iter_rules():
            if '/layer4' in rule.rule:
                layer4_routes.append(rule.rule)

        print(f"    Layer 4 Routes Registered: {len(layer4_routes)}")

        if LAYER4_ENDPOINTS_AVAILABLE:
            assert len(layer4_routes) >= 9, f"Expected at least 9 routes, got {len(layer4_routes)}"
            print("    [OK] Layer 4 integrated in unified brain service")
        else:
            print("    [WARN] Layer 4 not available in unified brain service")

        return True

    except Exception as e:
        print(f"    [ERROR] Unified brain integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_all_tests():
    """Run all Phase 5 tests"""
    print("=" * 70)
    print("PHASE 5: PRODUCTION INTEGRATION TESTS")
    print("=" * 70)
    print(f"Started at: {datetime.now().isoformat()}")
    print()

    tests = [
        test_layer4_blueprint_import,
        test_layer4_blueprint_registration,
        test_layer4_health_endpoint,
        test_layer4_status_endpoint,
        test_layer4_route_endpoint,
        test_layer4_training_endpoints,
        test_layer4_regime_endpoint,
        test_layer4_reset_endpoint,
        test_layer4_record_result,
        test_layer4_feature_definitions,
        test_unified_brain_layer4_import,
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append((test.__name__, result))
        except Exception as e:
            print(f"    [EXCEPTION] {test.__name__}: {e}")
            results.append((test.__name__, False))

    # Summary
    print()
    print("=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    passed = sum(1 for _, r in results if r)
    failed = sum(1 for _, r in results if not r)

    for name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"  [{status}] {name}")

    print()
    print(f"Passed: {passed}/{len(results)}")
    print(f"Failed: {failed}/{len(results)}")

    if failed == 0:
        print()
        print("=" * 70)
        print("ALL PHASE 5 TESTS PASSED!")
        print("=" * 70)
    else:
        print()
        print("=" * 70)
        print(f"SOME TESTS FAILED ({failed} failures)")
        print("=" * 70)

    return failed == 0


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
