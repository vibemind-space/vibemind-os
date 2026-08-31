"""
Unit tests for Brain Dashboard Server proxy endpoints.

Tests the Flask REST API in web/brain_dashboard_server.py using the Flask
test client with mocked HTTP calls to the unified brain service (port 5003).

Coverage:
- Proxied GET endpoints (cognitive_loop, emotional_state, homeostatic, memory, etc.)
- Proxied POST endpoints (sensory_extract)
- Health check endpoints (health, components, dependencies, readiness, liveness)
- Frequency mode endpoints
- Local-only endpoints (gates, activation, state, strategies, interventions)
- Error handling when the backend service is unreachable
- Response content types and JSON structure
"""

import pytest
import sys
import os
import json
from unittest.mock import MagicMock, patch, PropertyMock

# Add project root to path
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, parent_dir)


# ---------------------------------------------------------------------------
# Helper: mock response object for requests.get / requests.post
# ---------------------------------------------------------------------------

def _mock_response(json_data, status_code=200):
    """Create a mock response object mimicking requests.Response."""
    mock = MagicMock()
    mock.status_code = status_code
    mock.ok = (200 <= status_code < 300)
    mock.json.return_value = json_data
    mock.text = json.dumps(json_data)
    return mock


# ---------------------------------------------------------------------------
# Fixture: Flask test client with all brain globals set to None
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """Create a Flask test client without initializing brain components."""
    # We must import the module so we can patch its globals
    import web.brain_dashboard_server as dashboard

    # Set all brain globals to None so that local-data endpoints return 503
    dashboard.meta_router = None
    dashboard.brain_monitor = None
    dashboard.strategy_lib = None
    dashboard.live_monitor = None
    dashboard.path_planner = None
    dashboard.llm_router = None
    dashboard.hierarchical_planner = None
    dashboard.frequency_controller = None
    dashboard.frequency_mixer = None
    dashboard.layer4_router = None
    dashboard.checkpoint_manager = None

    dashboard.app.config['TESTING'] = True
    with dashboard.app.test_client() as c:
        yield c


@pytest.fixture
def client_with_brain():
    """Create a Flask test client with mocked brain components."""
    import web.brain_dashboard_server as dashboard

    # Create lightweight mocks for brain components
    mock_monitor = MagicMock()
    mock_monitor.gate_history = [[0.1] * 10]
    mock_monitor.get_activation_summary.return_value = {
        'current_activation': [0.5, 0.3],
        'alerts': [],
        'gate_strength': 0.8,
        'avg_error_rate': 0.02,
        'total_memories': 15,
    }

    mock_meta = MagicMock()
    mock_meta.get_state.return_value = {
        'traces_processed': 39,
        'failures_encoded': 5,
        'successes_encoded': 34,
        'thalamo_hippocampal_state': {
            'hippocampal': {'num_memories': 20}
        },
    }

    mock_strategy = MagicMock()
    mock_strategy.get_statistics.return_value = {
        'total_strategies': 42,
        'task_types': ['code', 'deploy'],
        'total_retrievals': 10,
        'strategies_by_type': {'code': 30, 'deploy': 12},
    }

    mock_live = MagicMock()
    mock_live.get_statistics.return_value = {
        'conversations_monitored': 5,
        'interventions_triggered': 2,
        'failures_prevented': 1,
        'intervention_history': [],
    }

    mock_planner = MagicMock()

    dashboard.meta_router = mock_meta
    dashboard.brain_monitor = mock_monitor
    dashboard.strategy_lib = mock_strategy
    dashboard.live_monitor = mock_live
    dashboard.path_planner = mock_planner
    dashboard.hierarchical_planner = MagicMock()
    dashboard.llm_router = None
    dashboard.frequency_controller = None
    dashboard.frequency_mixer = None
    dashboard.layer4_router = None
    dashboard.checkpoint_manager = None

    dashboard.app.config['TESTING'] = True
    with dashboard.app.test_client() as c:
        yield c


# ============================================================================
# 1. PROXIED GET ENDPOINTS (mock requests.get to unified brain service)
# ============================================================================

class TestCognitiveLoopProxy:
    """Tests for GET /api/brain/cognitive_loop."""

    @patch('web.brain_dashboard_server.requests.get')
    def test_cognitive_loop_success(self, mock_get, client):
        payload = {'success': True, 'enabled': True, 'state': {'step': 'perceive'}}
        mock_get.return_value = _mock_response(payload)

        resp = client.get('/api/brain/cognitive_loop')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['enabled'] is True
        assert data['state']['step'] == 'perceive'

    @patch('web.brain_dashboard_server.requests.get')
    def test_cognitive_loop_backend_down(self, mock_get, client):
        import requests as real_requests
        mock_get.side_effect = real_requests.ConnectionError("Connection refused")

        resp = client.get('/api/brain/cognitive_loop')
        assert resp.status_code == 200
        data = resp.get_json()
        # Fallback: returns disabled state
        assert data['enabled'] is False

    @patch('web.brain_dashboard_server.requests.get')
    def test_cognitive_loop_backend_500(self, mock_get, client):
        mock_get.return_value = _mock_response({'error': 'internal'}, 500)

        resp = client.get('/api/brain/cognitive_loop')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['enabled'] is False


class TestEmotionalStateProxy:
    """Tests for GET /api/brain/emotional_state."""

    @patch('web.brain_dashboard_server.requests.get')
    def test_emotional_state_success(self, mock_get, client):
        payload = {'enabled': True, 'state': {'valence': 0.6, 'arousal': 0.4}}
        mock_get.return_value = _mock_response(payload)

        resp = client.get('/api/brain/emotional_state')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['enabled'] is True
        assert data['state']['valence'] == 0.6

    @patch('web.brain_dashboard_server.requests.get')
    def test_emotional_state_backend_down(self, mock_get, client):
        import requests as real_requests
        mock_get.side_effect = real_requests.ConnectionError()

        resp = client.get('/api/brain/emotional_state')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['enabled'] is False


class TestHomeostaticStateProxy:
    """Tests for GET /api/brain/homeostatic_state."""

    @patch('web.brain_dashboard_server.requests.get')
    def test_homeostatic_state_success(self, mock_get, client):
        payload = {'enabled': True, 'state': {'energy': 0.9}}
        mock_get.return_value = _mock_response(payload)

        resp = client.get('/api/brain/homeostatic_state')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['enabled'] is True

    @patch('web.brain_dashboard_server.requests.get')
    def test_homeostatic_state_backend_down(self, mock_get, client):
        import requests as real_requests
        mock_get.side_effect = real_requests.ConnectionError()

        resp = client.get('/api/brain/homeostatic_state')
        data = resp.get_json()
        assert data['enabled'] is False


class TestMemoryStateProxy:
    """Tests for GET /api/brain/memory_state."""

    @patch('web.brain_dashboard_server.requests.get')
    def test_memory_state_success(self, mock_get, client):
        payload = {'enabled': True, 'state': {'working_memory_size': 5}}
        mock_get.return_value = _mock_response(payload)

        resp = client.get('/api/brain/memory_state')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['enabled'] is True

    @patch('web.brain_dashboard_server.requests.get')
    def test_memory_state_backend_down(self, mock_get, client):
        import requests as real_requests
        mock_get.side_effect = real_requests.ConnectionError()

        resp = client.get('/api/brain/memory_state')
        data = resp.get_json()
        assert data['enabled'] is False


class TestHeartbeatStatusProxy:
    """Tests for GET /api/brain/heartbeat_status."""

    @patch('web.brain_dashboard_server.requests.get')
    def test_heartbeat_active(self, mock_get, client):
        payload = {'active': True, 'bpm': 60}
        mock_get.return_value = _mock_response(payload)

        resp = client.get('/api/brain/heartbeat_status')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['active'] is True

    @patch('web.brain_dashboard_server.requests.get')
    def test_heartbeat_backend_down(self, mock_get, client):
        import requests as real_requests
        mock_get.side_effect = real_requests.ConnectionError()

        resp = client.get('/api/brain/heartbeat_status')
        data = resp.get_json()
        assert data['active'] is False


class TestGoalGraphStateProxy:
    """Tests for GET /api/brain/goal_graph_state."""

    @patch('web.brain_dashboard_server.requests.get')
    def test_goal_graph_success(self, mock_get, client):
        payload = {'enabled': True, 'state': {'goals': []}}
        mock_get.return_value = _mock_response(payload)

        resp = client.get('/api/brain/goal_graph_state')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['enabled'] is True

    @patch('web.brain_dashboard_server.requests.get')
    def test_goal_graph_backend_down(self, mock_get, client):
        import requests as real_requests
        mock_get.side_effect = real_requests.ConnectionError()

        resp = client.get('/api/brain/goal_graph_state')
        data = resp.get_json()
        assert data['enabled'] is False
        assert data['state'] is None


class TestNeuromodulationStateProxy:
    """Tests for GET /api/brain/neuromodulation_state."""

    @patch('web.brain_dashboard_server.requests.get')
    def test_neuromod_success(self, mock_get, client):
        payload = {'enabled': True, 'state': {'dopamine': 0.5}}
        mock_get.return_value = _mock_response(payload)

        resp = client.get('/api/brain/neuromodulation_state')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['enabled'] is True
        assert data['state']['dopamine'] == 0.5

    @patch('web.brain_dashboard_server.requests.get')
    def test_neuromod_backend_down(self, mock_get, client):
        import requests as real_requests
        mock_get.side_effect = real_requests.ConnectionError()

        resp = client.get('/api/brain/neuromodulation_state')
        data = resp.get_json()
        assert data['enabled'] is False


class TestConsciousnessStateProxy:
    """Tests for GET /api/brain/consciousness_state."""

    @patch('web.brain_dashboard_server.requests.get')
    def test_consciousness_success(self, mock_get, client):
        payload = {'enabled': True, 'state': {'phi': 0.8}}
        mock_get.return_value = _mock_response(payload)

        resp = client.get('/api/brain/consciousness_state')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['enabled'] is True

    @patch('web.brain_dashboard_server.requests.get')
    def test_consciousness_backend_down(self, mock_get, client):
        import requests as real_requests
        mock_get.side_effect = real_requests.ConnectionError()

        resp = client.get('/api/brain/consciousness_state')
        data = resp.get_json()
        assert data['enabled'] is False


# ============================================================================
# 2. PROXIED POST ENDPOINT
# ============================================================================

class TestSensoryExtractProxy:
    """Tests for POST /api/brain/sensory_extract."""

    @patch('web.brain_dashboard_server.requests.post')
    def test_sensory_extract_success(self, mock_post, client):
        payload = {
            'enabled': True,
            'features': {'vision': 0.7, 'audio': 0.3},
        }
        mock_post.return_value = _mock_response(payload)

        resp = client.post(
            '/api/brain/sensory_extract',
            json={'text': 'Hello world'},
            content_type='application/json',
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['enabled'] is True
        assert 'features' in data

    @patch('web.brain_dashboard_server.requests.post')
    def test_sensory_extract_backend_down(self, mock_post, client):
        import requests as real_requests
        mock_post.side_effect = real_requests.ConnectionError()

        resp = client.post(
            '/api/brain/sensory_extract',
            json={'text': 'Hello'},
            content_type='application/json',
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['enabled'] is False


# ============================================================================
# 3. FREQUENCY MODE ENDPOINTS
# ============================================================================

class TestFrequencyProxy:
    """Tests for GET /api/brain/frequency."""

    @patch('web.brain_dashboard_server.requests.get')
    def test_frequency_from_unified_brain(self, mock_get, client):
        payload = {
            'dominant_mode': 'beta',
            'activations': {'alpha': 0.2, 'beta': 0.8},
            'active_modes': ['beta'],
            'mode_switches': 3,
            'markers_count': 10,
        }
        mock_get.return_value = _mock_response(payload)

        resp = client.get('/api/brain/frequency')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['source'] == 'unified_brain'
        assert data['dominant_mode'] == 'beta'

    @patch('web.brain_dashboard_server.requests.get')
    def test_frequency_fallback_to_local(self, mock_get, client):
        """When unified brain is down, falls back to local frequency controller."""
        import requests as real_requests
        mock_get.side_effect = real_requests.ConnectionError()

        resp = client.get('/api/brain/frequency')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['source'] == 'local'
        assert 'dominant_mode' in data
        assert 'timestamp' in data


# ============================================================================
# 4. LOCAL-ONLY ENDPOINTS (require initialized brain components)
# ============================================================================

class TestGatesEndpoint:
    """Tests for GET /api/brain/gates."""

    def test_gates_not_initialized(self, client):
        resp = client.get('/api/brain/gates')
        assert resp.status_code == 503
        data = resp.get_json()
        assert 'error' in data

    def test_gates_success(self, client_with_brain):
        resp = client_with_brain.get('/api/brain/gates')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'modalities' in data
        assert 'values' in data
        assert len(data['modalities']) == 10
        assert 'timestamp' in data

    def test_gates_no_history(self, client_with_brain):
        """When gate_history is empty, returns 404."""
        import web.brain_dashboard_server as dashboard
        dashboard.brain_monitor.gate_history = []

        resp = client_with_brain.get('/api/brain/gates')
        assert resp.status_code == 404


class TestActivationEndpoint:
    """Tests for GET /api/brain/activation."""

    def test_activation_not_initialized(self, client):
        resp = client.get('/api/brain/activation')
        assert resp.status_code == 503

    def test_activation_success(self, client_with_brain):
        resp = client_with_brain.get('/api/brain/activation')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'activation' in data
        assert 'alerts' in data
        assert 'statistics' in data
        assert data['statistics']['gate_strength'] == 0.8


class TestStateEndpoint:
    """Tests for GET /api/brain/state."""

    def test_state_not_initialized(self, client):
        resp = client.get('/api/brain/state')
        assert resp.status_code == 503

    def test_state_success(self, client_with_brain):
        resp = client_with_brain.get('/api/brain/state')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['traces_processed'] == 39
        assert data['successes_encoded'] == 34
        assert data['hippocampal_memories'] == 20
        assert 'success_rate' in data


class TestStrategiesEndpoint:
    """Tests for GET /api/brain/strategies."""

    def test_strategies_not_initialized(self, client):
        resp = client.get('/api/brain/strategies')
        assert resp.status_code == 503

    def test_strategies_success(self, client_with_brain):
        resp = client_with_brain.get('/api/brain/strategies')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['total_strategies'] == 42
        assert 'code' in data['task_types']


class TestInterventionsEndpoint:
    """Tests for GET /api/brain/interventions."""

    def test_interventions_not_initialized(self, client):
        resp = client.get('/api/brain/interventions')
        assert resp.status_code == 503

    def test_interventions_success(self, client_with_brain):
        resp = client_with_brain.get('/api/brain/interventions')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['conversations_monitored'] == 5
        assert data['interventions_triggered'] == 2


# ============================================================================
# 5. HEALTH CHECK ENDPOINTS
# ============================================================================

class TestHealthEndpoints:
    """Tests for /api/health/*."""

    def test_health_all_uninitialized(self, client):
        resp = client.get('/api/health')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'unhealthy'
        assert data['health_percentage'] == 0.0
        assert data['components_initialized'] == 0

    def test_health_partially_initialized(self, client_with_brain):
        resp = client_with_brain.get('/api/health')
        assert resp.status_code == 200
        data = resp.get_json()
        # meta_router, brain_monitor, strategy_lib, live_monitor, path_planner,
        # hierarchical_planner are set; llm_router, freq_ctrl, layer4, checkpoint are None
        assert data['components_initialized'] == 6
        assert data['health_percentage'] == 60.0
        assert data['status'] == 'degraded'

    def test_health_components(self, client_with_brain):
        resp = client_with_brain.get('/api/health/components')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'components' in data
        assert data['components']['meta_router']['initialized'] is True
        assert data['components']['llm_router']['initialized'] is False
        assert 'timestamp' in data

    @patch('web.brain_dashboard_server.requests.get')
    def test_health_dependencies_all_down(self, mock_get, client):
        import requests as real_requests
        mock_get.side_effect = real_requests.ConnectionError("refused")

        resp = client.get('/api/health/dependencies')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'dependencies' in data
        assert data['dependencies']['ollama']['available'] is False
        assert data['dependencies']['unified_brain']['available'] is False

    @patch('web.brain_dashboard_server.requests.get')
    def test_health_dependencies_all_up(self, mock_get, client):
        # Ollama returns model list; unified brain returns health
        def side_effect(url, **kwargs):
            if 'ollama' in url or '11434' in url:
                return _mock_response({'models': [{'name': 'llama2'}]})
            else:
                return _mock_response({'status': 'ok'})

        mock_get.side_effect = side_effect

        resp = client.get('/api/health/dependencies')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['dependencies']['ollama']['available'] is True
        assert data['dependencies']['unified_brain']['available'] is True

    def test_liveness_always_200(self, client):
        resp = client.get('/api/health/liveness')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['alive'] is True
        assert 'timestamp' in data

    def test_readiness_not_ready(self, client):
        resp = client.get('/api/health/readiness')
        assert resp.status_code == 503
        data = resp.get_json()
        assert data['ready'] is False

    def test_readiness_ready(self, client_with_brain):
        resp = client_with_brain.get('/api/health/readiness')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ready'] is True


# ============================================================================
# 6. CONTENT-TYPE AND JSON STRUCTURE VALIDATION
# ============================================================================

class TestResponseFormat:
    """Verify all endpoints return proper JSON content type."""

    def test_liveness_content_type(self, client):
        resp = client.get('/api/health/liveness')
        assert resp.content_type == 'application/json'

    @patch('web.brain_dashboard_server.requests.get')
    def test_cognitive_loop_content_type(self, mock_get, client):
        mock_get.return_value = _mock_response({'enabled': False})
        resp = client.get('/api/brain/cognitive_loop')
        assert resp.content_type == 'application/json'

    def test_health_content_type(self, client):
        resp = client.get('/api/health')
        assert resp.content_type == 'application/json'

    @patch('web.brain_dashboard_server.requests.get')
    def test_proxy_returns_valid_json(self, mock_get, client):
        """Ensure proxy endpoints always return parseable JSON."""
        mock_get.return_value = _mock_response({'test': 123})

        endpoints = [
            '/api/brain/cognitive_loop',
            '/api/brain/emotional_state',
            '/api/brain/homeostatic_state',
            '/api/brain/memory_state',
            '/api/brain/heartbeat_status',
            '/api/brain/goal_graph_state',
            '/api/brain/neuromodulation_state',
            '/api/brain/consciousness_state',
        ]
        for ep in endpoints:
            resp = client.get(ep)
            assert resp.status_code == 200, f"{ep} failed with {resp.status_code}"
            data = resp.get_json()
            assert data is not None, f"{ep} returned non-JSON"
