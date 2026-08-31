"""
Tests for Unified Brain Service REST Endpoints
===============================================

Tests the Flask REST endpoints in production/unified_brain_service.py
using Flask's test client and mocked brain instances to avoid heavy
initialization of ProductionPlanner and related subsystems.

Run with:
    pytest tests/test_unified_brain_endpoints.py -v
"""

import pytest
import json
import sys
import os
import numpy as np
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime

# Ensure the project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from production.unified_brain_service import app


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def client():
    """Create a Flask test client."""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def mock_brain():
    """Create a fully mocked ProductionPlanner instance."""
    brain = MagicMock()

    # Planner sub-object
    brain.planner = MagicMock()
    brain.planner.layer2 = MagicMock()
    brain.planner.layer2.total_predictions = 42
    brain.planner.layer2.routing_matrix = np.array([[0.5, 0.3], [0.2, 0.8]])
    brain.planner.layer2.meta_router = MagicMock()
    brain.planner.layer2.meta_router.multi_llm_router = MagicMock()

    # Cognitive loop
    brain.cognitive_loop = MagicMock()
    brain.cognitive_loop.get_loop_state.return_value = {
        'cycle_count': 10,
        'current_stage': 'reason',
        'stages_completed': ['perceive', 'appraise_emotion', 'remember'],
    }

    # Emotional system
    brain.cognitive_loop._emotional_system = MagicMock()
    brain.cognitive_loop._emotional_system.get_state_dict.return_value = {
        'valence': 0.6,
        'arousal': 0.4,
        'dominant_emotion': 'calm',
    }

    # Homeostatic system
    brain.cognitive_loop._homeostatic = MagicMock()
    brain.cognitive_loop._homeostatic.state = MagicMock()
    brain.cognitive_loop._homeostatic.state.energy = 0.8
    brain.cognitive_loop._homeostatic.state.fatigue = 0.2
    brain.cognitive_loop._homeostatic.state.stress = 0.1
    brain.cognitive_loop._homeostatic.state.allostatic_load = 0.15
    brain.cognitive_loop._homeostatic.state.sleep_pressure = 0.3
    brain.cognitive_loop._homeostatic.get_performance_factor.return_value = 0.9
    brain.cognitive_loop._homeostatic.get_temperature_adjustment.return_value = 0.05
    brain.cognitive_loop._homeostatic.get_attention_degradation.return_value = 0.1
    brain.cognitive_loop._homeostatic.should_trigger_dream.return_value = False

    # Memory system
    brain.planner.memory = MagicMock()
    brain.planner.memory.working = MagicMock()
    brain.planner.memory.episodic = MagicMock()
    brain.planner.memory.working.__len__ = MagicMock(return_value=5)
    brain.planner.memory.episodic.__len__ = MagicMock(return_value=20)
    recent_entry = MagicMock()
    recent_entry.to_dict.return_value = {'task': 'test_task', 'result': 'success'}
    brain.planner.memory.working.get_recent.return_value = [recent_entry]
    brain.planner.memory.working.get_success_rate.return_value = 0.85

    # Sensory preprocessor
    brain.sensory_preprocessor = MagicMock()
    sensory_features = MagicMock()
    sensory_features.detected_intent = 'query'
    sensory_features.detected_domain = 'general'
    sensory_features.overall_complexity = 0.456
    sensory_features.overall_urgency = 0.234
    sensory_features.overall_risk = 0.123
    brain.sensory_preprocessor.extract.return_value = sensory_features

    # Goal graph
    brain.planner.goal_graph = MagicMock()
    mock_goal = MagicMock()
    mock_goal.id = 'goal_1'
    mock_goal.description = 'Complete test suite'
    mock_goal.status = 'active'
    mock_goal.priority = 0.8
    brain.planner.goal_graph.get_all_goals.return_value = [mock_goal]

    # Neuromodulation
    brain.planner.enable_neuromodulation = True
    brain.planner.neuromodulation = MagicMock()
    brain.planner.neuromodulation.total_updates = 100
    brain.planner.neuromodulation.levels = MagicMock()
    brain.planner.neuromodulation.levels.to_dict.return_value = {
        'dopamine': 0.6, 'serotonin': 0.5, 'norepinephrine': 0.4
    }
    brain.planner.neuromodulation.get_state_description.return_value = 'balanced'
    brain.planner.neuromodulation.compute_effects.return_value = MagicMock()
    brain.planner.neuromodulation.compute_effects.return_value.to_dict.return_value = {
        'exploration_bonus': 0.1, 'temperature_mod': 0.05
    }
    brain.planner.neuromodulation.expected_reward = 0.7

    # Consciousness
    brain.planner.enable_consciousness = True
    brain.planner.consciousness = MagicMock()
    brain.planner.consciousness.total_states_tracked = 50
    brain.planner.consciousness.total_assessments = 30
    brain.planner.consciousness.self_awareness_events = 5
    brain.planner.consciousness.known_unknowns = ['uncertainty_1', 'uncertainty_2']
    brain.planner.consciousness.detected_biases = ['recency_bias']
    cs_state = MagicMock()
    cs_state.to_dict.return_value = {
        'awareness_level': 0.75,
        'global_workspace_activation': 0.6,
    }
    brain.planner.consciousness.current_state = cs_state

    # Continuous learning flag
    brain.enable_continuous_learning = True

    # Boolean flags checked by /available_features via getattr()
    brain.planner.enable_semantic_coherence = True
    brain.planner.enable_ctm_async = False
    brain.planner.attention = MagicMock()
    brain.planner.predictive_coding = MagicMock()
    brain.planner.active_inference = MagicMock()
    brain.planner.meta_learner = MagicMock()
    brain.planner.temporal_memory = MagicMock()
    brain.planner.infinite_context = MagicMock()

    # Predict method
    brain.predict.return_value = {
        'prediction': {
            'primary_action': 'suggest',
            'confidence': 0.85,
            'alternatives': ['retry', 'wait'],
        },
        'memory_context': {'similar_tasks': []},
        'attention_state': {'focus': 'high'},
    }

    # Statistics
    brain.get_statistics.return_value = {
        'total_predictions': 42,
        'total_feedback': 15,
        'accuracy': 0.88,
    }

    return brain


@pytest.fixture
def mock_heartbeat():
    """Create a mocked BrainHeartbeat instance."""
    hb = MagicMock()
    hb.is_alive.return_value = True
    hb.tick_count = 123
    hb.get_stats.return_value = {
        'ticks': 123,
        'dream_cycles': 2,
        'uptime_seconds': 3600,
    }
    return hb


@pytest.fixture
def mock_freq_controller():
    """Create a mocked BrainFrequencyController instance."""
    ctrl = MagicMock()
    ctrl.get_state.return_value = {
        'dominant_mode': 'alpha',
        'activations': {'alpha': 1.0, 'beta': 0.0, 'gamma': 0.0, 'delta': 0.0, 'theta': 0.0},
    }
    ctrl.get_all_bands.return_value = {
        'alpha': {'range': '8-12 Hz', 'description': 'Relaxed awareness'},
        'beta': {'range': '12-30 Hz', 'description': 'Active thinking'},
        'gamma': {'range': '30-100 Hz', 'description': 'Deep reasoning'},
        'delta': {'range': '0.5-4 Hz', 'description': 'Sleep/consolidation'},
        'theta': {'range': '4-8 Hz', 'description': 'Meditation/memory'},
    }
    ctrl.set_mode.return_value = {'switched': True, 'new_mode': 'beta'}
    ctrl.auto_switch.return_value = {'auto_switched': True, 'current_dominant': 'beta'}
    ctrl.get_recent_markers.return_value = []
    marker = MagicMock()
    marker.marker_id = 'marker_abc'
    marker.decision_point = 'test decision'
    marker.alternatives = ['alt1', 'alt2']
    marker.confidence = 0.7
    ctrl.set_marker.return_value = marker
    ctrl.jump_to_marker.return_value = {'marker_id': 'marker_abc', 'restored': True}
    return ctrl


# =============================================================================
# HELPER
# =============================================================================

def _patch_brain(mock_brain):
    """Return a patch context manager for get_unified_brain."""
    return patch(
        'production.unified_brain_service.get_unified_brain',
        return_value=mock_brain,
    )


def _patch_heartbeat(mock_hb):
    """Return a patch context manager for brain_heartbeat global."""
    return patch(
        'production.unified_brain_service.brain_heartbeat',
        mock_hb,
    )


def _patch_freq(mock_ctrl):
    """Return a patch context manager for get_frequency_controller."""
    return patch(
        'production.unified_brain_service.get_frequency_controller',
        return_value=mock_ctrl,
    )


# =============================================================================
# HEALTH ENDPOINT TESTS
# =============================================================================

class TestHealthEndpoint:
    """Tests for GET /health."""

    def test_health_returns_200(self, client, mock_brain, mock_heartbeat):
        with _patch_brain(mock_brain), _patch_heartbeat(mock_heartbeat):
            resp = client.get('/health')
            assert resp.status_code == 200

    def test_health_response_fields(self, client, mock_brain, mock_heartbeat):
        with _patch_brain(mock_brain), _patch_heartbeat(mock_heartbeat):
            resp = client.get('/health')
            data = resp.get_json()
            assert data['status'] == 'operational'
            assert data['service'] == 'unified_brain'
            assert data['brain_type'] == 'ProductionPlanner'
            assert 'llm_enabled' in data
            assert 'cognitive_loop_enabled' in data
            assert 'continuous_learning' in data
            assert 'heartbeat_active' in data
            assert 'connected_services' in data

    def test_health_llm_enabled_true(self, client, mock_brain, mock_heartbeat):
        with _patch_brain(mock_brain), _patch_heartbeat(mock_heartbeat):
            resp = client.get('/health')
            data = resp.get_json()
            assert data['llm_enabled'] is True

    def test_health_llm_enabled_false_when_no_multi_llm(self, client, mock_brain, mock_heartbeat):
        mock_brain.planner.layer2.meta_router.multi_llm_router = None
        with _patch_brain(mock_brain), _patch_heartbeat(mock_heartbeat):
            resp = client.get('/health')
            data = resp.get_json()
            assert data['llm_enabled'] is False

    def test_health_heartbeat_active(self, client, mock_brain, mock_heartbeat):
        with _patch_brain(mock_brain), _patch_heartbeat(mock_heartbeat):
            resp = client.get('/health')
            data = resp.get_json()
            assert data['heartbeat_active'] is True


# =============================================================================
# COGNITIVE LOOP STATE TESTS
# =============================================================================

class TestCognitiveLoopState:
    """Tests for GET /cognitive_loop_state."""

    def test_cognitive_loop_enabled(self, client, mock_brain):
        with _patch_brain(mock_brain):
            resp = client.get('/cognitive_loop_state')
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['success'] is True
            assert data['enabled'] is True
            assert 'state' in data
            assert data['state']['cycle_count'] == 10

    def test_cognitive_loop_disabled(self, client, mock_brain):
        mock_brain.cognitive_loop = None
        with _patch_brain(mock_brain):
            resp = client.get('/cognitive_loop_state')
            data = resp.get_json()
            assert data['success'] is True
            assert data['enabled'] is False
            assert data['state'] is None


# =============================================================================
# HEARTBEAT STATUS TESTS
# =============================================================================

class TestHeartbeatStatus:
    """Tests for GET /heartbeat_status."""

    def test_heartbeat_active(self, client, mock_heartbeat):
        with _patch_heartbeat(mock_heartbeat):
            resp = client.get('/heartbeat_status')
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['active'] is True
            assert data['tick_count'] == 123
            assert 'stats' in data
            assert data['stats']['ticks'] == 123

    def test_heartbeat_inactive(self, client):
        with _patch_heartbeat(None):
            resp = client.get('/heartbeat_status')
            data = resp.get_json()
            assert data['active'] is False


# =============================================================================
# EMOTIONAL STATE TESTS
# =============================================================================

class TestEmotionalState:
    """Tests for GET /emotional_state."""

    def test_emotional_state_enabled(self, client, mock_brain):
        with _patch_brain(mock_brain):
            resp = client.get('/emotional_state')
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['enabled'] is True
            assert data['state']['valence'] == 0.6
            assert data['state']['dominant_emotion'] == 'calm'

    def test_emotional_state_disabled(self, client, mock_brain):
        mock_brain.cognitive_loop = None
        with _patch_brain(mock_brain):
            resp = client.get('/emotional_state')
            data = resp.get_json()
            assert data['enabled'] is False
            assert data['state'] is None

    def test_emotional_state_no_emotional_system(self, client, mock_brain):
        mock_brain.cognitive_loop._emotional_system = None
        with _patch_brain(mock_brain):
            resp = client.get('/emotional_state')
            data = resp.get_json()
            assert data['enabled'] is False


# =============================================================================
# HOMEOSTATIC STATE TESTS
# =============================================================================

class TestHomeostaticState:
    """Tests for GET /homeostatic_state."""

    def test_homeostatic_state_enabled(self, client, mock_brain):
        with _patch_brain(mock_brain):
            resp = client.get('/homeostatic_state')
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['enabled'] is True
            state = data['state']
            assert state['energy'] == 0.8
            assert state['fatigue'] == 0.2
            assert state['stress'] == 0.1
            assert state['allostatic_load'] == 0.15
            assert state['sleep_pressure'] == 0.3
            assert state['performance_factor'] == 0.9
            assert state['should_dream'] is False

    def test_homeostatic_state_disabled(self, client, mock_brain):
        mock_brain.cognitive_loop = None
        with _patch_brain(mock_brain):
            resp = client.get('/homeostatic_state')
            data = resp.get_json()
            assert data['enabled'] is False
            assert data['state'] is None


# =============================================================================
# MEMORY STATE TESTS
# =============================================================================

class TestMemoryState:
    """Tests for GET /memory_state."""

    def test_memory_state_enabled(self, client, mock_brain):
        with _patch_brain(mock_brain):
            resp = client.get('/memory_state')
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['enabled'] is True
            state = data['state']
            assert state['working_memory_size'] == 5
            assert state['episodic_memory_size'] == 20
            assert state['recent_success_rate'] == 0.85
            assert len(state['recent_tasks']) == 1

    def test_memory_state_disabled(self, client, mock_brain):
        mock_brain.planner.memory = None
        # Make hasattr return False for 'memory'
        del mock_brain.planner.memory
        with _patch_brain(mock_brain):
            resp = client.get('/memory_state')
            data = resp.get_json()
            assert data['enabled'] is False
            assert data['state'] is None


# =============================================================================
# SENSORY EXTRACT TESTS
# =============================================================================

class TestSensoryExtract:
    """Tests for POST /sensory_extract."""

    def test_sensory_extract_success(self, client, mock_brain):
        with _patch_brain(mock_brain):
            resp = client.post(
                '/sensory_extract',
                data=json.dumps({'text': 'Deploy a Docker container for production'}),
                content_type='application/json',
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['enabled'] is True
            features = data['features']
            assert features['detected_intent'] == 'query'
            assert features['detected_domain'] == 'general'
            assert features['overall_complexity'] == 0.456
            assert features['overall_urgency'] == 0.234
            assert features['overall_risk'] == 0.123

    def test_sensory_extract_empty_text(self, client, mock_brain):
        with _patch_brain(mock_brain):
            resp = client.post(
                '/sensory_extract',
                data=json.dumps({'text': ''}),
                content_type='application/json',
            )
            assert resp.status_code == 200
            mock_brain.sensory_preprocessor.extract.assert_called_with('')

    def test_sensory_extract_no_body(self, client, mock_brain):
        with _patch_brain(mock_brain):
            resp = client.post(
                '/sensory_extract',
                data=json.dumps({}),
                content_type='application/json',
            )
            assert resp.status_code == 200
            mock_brain.sensory_preprocessor.extract.assert_called_with('')

    def test_sensory_extract_disabled(self, client, mock_brain):
        mock_brain.sensory_preprocessor = None
        with _patch_brain(mock_brain):
            resp = client.post(
                '/sensory_extract',
                data=json.dumps({'text': 'test'}),
                content_type='application/json',
            )
            data = resp.get_json()
            assert data['enabled'] is False


# =============================================================================
# GOAL GRAPH STATE TESTS
# =============================================================================

class TestGoalGraphState:
    """Tests for GET /goal_graph_state."""

    def test_goal_graph_enabled(self, client, mock_brain):
        with _patch_brain(mock_brain):
            resp = client.get('/goal_graph_state')
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['enabled'] is True
            state = data['state']
            assert state['total_goals'] == 1
            assert state['active_goals'] == 1
            assert len(state['goals']) == 1
            assert state['goals'][0]['id'] == 'goal_1'
            assert state['goals'][0]['description'] == 'Complete test suite'
            assert state['goals'][0]['status'] == 'active'

    def test_goal_graph_disabled(self, client, mock_brain):
        mock_brain.planner.goal_graph = None
        del mock_brain.planner.goal_graph
        with _patch_brain(mock_brain):
            resp = client.get('/goal_graph_state')
            data = resp.get_json()
            assert data['enabled'] is False
            assert data['state'] is None


# =============================================================================
# NEUROMODULATION STATE TESTS
# =============================================================================

class TestNeuromodulationState:
    """Tests for GET /neuromodulation_state."""

    def test_neuromodulation_enabled(self, client, mock_brain):
        with _patch_brain(mock_brain):
            resp = client.get('/neuromodulation_state')
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['enabled'] is True
            state = data['state']
            assert state['total_updates'] == 100
            assert state['current_levels']['dopamine'] == 0.6
            assert state['current_state'] == 'balanced'
            assert state['expected_reward'] == 0.7

    def test_neuromodulation_disabled(self, client, mock_brain):
        mock_brain.planner.enable_neuromodulation = False
        with _patch_brain(mock_brain):
            resp = client.get('/neuromodulation_state')
            data = resp.get_json()
            assert data['enabled'] is False
            assert data['state'] is None


# =============================================================================
# CONSCIOUSNESS STATE TESTS
# =============================================================================

class TestConsciousnessState:
    """Tests for GET /consciousness_state."""

    def test_consciousness_enabled(self, client, mock_brain):
        with _patch_brain(mock_brain):
            resp = client.get('/consciousness_state')
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['enabled'] is True
            state = data['state']
            assert state['total_states_tracked'] == 50
            assert state['total_assessments'] == 30
            assert state['self_awareness_events'] == 5
            assert state['known_unknowns_count'] == 2
            assert state['detected_biases_count'] == 1
            assert state['current_state']['awareness_level'] == 0.75

    def test_consciousness_disabled(self, client, mock_brain):
        mock_brain.planner.enable_consciousness = False
        with _patch_brain(mock_brain):
            resp = client.get('/consciousness_state')
            data = resp.get_json()
            assert data['enabled'] is False
            assert data['state'] is None

    def test_consciousness_no_current_state(self, client, mock_brain):
        mock_brain.planner.consciousness.current_state = None
        with _patch_brain(mock_brain):
            resp = client.get('/consciousness_state')
            data = resp.get_json()
            assert data['enabled'] is True
            assert data['state']['current_state'] is None


# =============================================================================
# REGISTER SERVICE TESTS
# =============================================================================

class TestRegisterService:
    """Tests for POST /register."""

    def test_register_known_service(self, client):
        resp = client.post(
            '/register',
            data=json.dumps({'service_name': 'dashboard'}),
            content_type='application/json',
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['brain_ready'] is True

    def test_register_api_service(self, client):
        resp = client.post(
            '/register',
            data=json.dumps({'service_name': 'api'}),
            content_type='application/json',
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True

    def test_register_swarm_service(self, client):
        resp = client.post(
            '/register',
            data=json.dumps({'service_name': 'swarm'}),
            content_type='application/json',
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True

    def test_register_unknown_service(self, client):
        resp = client.post(
            '/register',
            data=json.dumps({'service_name': 'unknown_service'}),
            content_type='application/json',
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['success'] is False


# =============================================================================
# PREDICT ENDPOINT TESTS
# =============================================================================

class TestPredictEndpoint:
    """Tests for POST /predict."""

    def test_predict_success(self, client, mock_brain):
        with _patch_brain(mock_brain):
            resp = client.post(
                '/predict',
                data=json.dumps({'task': 'Deploy Docker container', 'service_name': 'test'}),
                content_type='application/json',
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['success'] is True
            assert data['result']['prediction']['primary_action'] == 'suggest'
            assert data['result']['prediction']['confidence'] == 0.85
            assert data['service_name'] == 'test'

    def test_predict_no_task(self, client, mock_brain):
        with _patch_brain(mock_brain):
            resp = client.post(
                '/predict',
                data=json.dumps({'task': '', 'service_name': 'test'}),
                content_type='application/json',
            )
            assert resp.status_code == 400
            data = resp.get_json()
            assert 'error' in data

    def test_predict_missing_task_key(self, client, mock_brain):
        with _patch_brain(mock_brain):
            resp = client.post(
                '/predict',
                data=json.dumps({'service_name': 'test'}),
                content_type='application/json',
            )
            assert resp.status_code == 400

    def test_predict_internal_error(self, client, mock_brain):
        mock_brain.predict.side_effect = RuntimeError('Brain malfunction')
        with _patch_brain(mock_brain):
            resp = client.post(
                '/predict',
                data=json.dumps({'task': 'fail task'}),
                content_type='application/json',
            )
            assert resp.status_code == 500
            data = resp.get_json()
            assert 'error' in data
            assert 'Brain malfunction' in data['error']


# =============================================================================
# FEEDBACK ENDPOINT TESTS
# =============================================================================

class TestFeedbackEndpoint:
    """Tests for POST /feedback."""

    def test_feedback_success(self, client, mock_brain):
        with _patch_brain(mock_brain):
            resp = client.post(
                '/feedback',
                data=json.dumps({
                    'task': 'Deploy Docker container',
                    'prediction': {'primary_action': 'suggest', 'confidence': 0.85},
                    'success': True,
                    'user_rating': 0.9,
                    'execution_time_ms': 1500,
                    'service_name': 'test',
                }),
                content_type='application/json',
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['success'] is True
            assert data['message'] == 'Feedback submitted'

    def test_feedback_missing_task(self, client, mock_brain):
        with _patch_brain(mock_brain):
            resp = client.post(
                '/feedback',
                data=json.dumps({
                    'task': '',
                    'prediction': {'action': 'suggest'},
                }),
                content_type='application/json',
            )
            assert resp.status_code == 400

    def test_feedback_missing_prediction(self, client, mock_brain):
        with _patch_brain(mock_brain):
            resp = client.post(
                '/feedback',
                data=json.dumps({
                    'task': 'some task',
                    'prediction': {},
                }),
                content_type='application/json',
            )
            assert resp.status_code == 400

    def test_feedback_internal_error(self, client, mock_brain):
        mock_brain.submit_feedback.side_effect = RuntimeError('Feedback failed')
        with _patch_brain(mock_brain):
            resp = client.post(
                '/feedback',
                data=json.dumps({
                    'task': 'some task',
                    'prediction': {'action': 'suggest'},
                    'success': True,
                }),
                content_type='application/json',
            )
            assert resp.status_code == 500


# =============================================================================
# STATISTICS ENDPOINT TESTS
# =============================================================================

class TestStatisticsEndpoint:
    """Tests for GET /statistics."""

    def test_statistics_success(self, client, mock_brain):
        with _patch_brain(mock_brain):
            resp = client.get('/statistics')
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['success'] is True
            stats = data['statistics']
            assert stats['total_predictions'] == 42
            assert stats['total_feedback'] == 15
            assert stats['accuracy'] == 0.88

    def test_statistics_error(self, client, mock_brain):
        mock_brain.get_statistics.side_effect = RuntimeError('Stats unavailable')
        with _patch_brain(mock_brain):
            resp = client.get('/statistics')
            assert resp.status_code == 500
            data = resp.get_json()
            assert 'error' in data


# =============================================================================
# BRAIN STATE ENDPOINT TESTS
# =============================================================================

class TestBrainStateEndpoint:
    """Tests for GET /brain_state."""

    def test_brain_state_success(self, client, mock_brain):
        with _patch_brain(mock_brain):
            resp = client.get('/brain_state')
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['success'] is True
            state = data['state']
            assert state['total_predictions'] == 42
            assert state['learning_enabled'] is True
            assert state['llm_enabled'] is True
            assert state['routing_matrix'] is not None

    def test_brain_state_no_llm(self, client, mock_brain):
        mock_brain.planner.layer2.meta_router.multi_llm_router = None
        with _patch_brain(mock_brain):
            resp = client.get('/brain_state')
            data = resp.get_json()
            assert data['state']['llm_enabled'] is False


# =============================================================================
# AVAILABLE FEATURES ENDPOINT TESTS
# =============================================================================

class TestAvailableFeatures:
    """Tests for GET /available_features."""

    def test_available_features_returns_200(self, client, mock_brain):
        with _patch_brain(mock_brain):
            resp = client.get('/available_features')
            assert resp.status_code == 200

    def test_available_features_response_structure(self, client, mock_brain):
        with _patch_brain(mock_brain):
            resp = client.get('/available_features')
            data = resp.get_json()
            assert data['success'] is True
            assert 'features' in data
            assert 'total_features' in data
            assert 'enabled_features' in data
            assert 'cognitive_loop_enabled' in data

    def test_available_features_core_features_present(self, client, mock_brain):
        with _patch_brain(mock_brain):
            resp = client.get('/available_features')
            data = resp.get_json()
            features = data['features']
            expected_features = [
                'memory_context', 'attention_state', 'predictive_coding',
                'consciousness_metrics', 'active_inference',
                'compositional_reasoning', 'tool_recommendations',
                'meta_learning', 'neuromodulation', 'temporal_memory',
                'semantic_coherence', 'ctm_insights', 'infinite_chat_context',
            ]
            for feat in expected_features:
                assert feat in features, f"Missing feature: {feat}"

    def test_available_features_enabled_count(self, client, mock_brain):
        with _patch_brain(mock_brain):
            resp = client.get('/available_features')
            data = resp.get_json()
            assert data['enabled_features'] > 0
            assert data['total_features'] >= 13


# =============================================================================
# FREQUENCY MODE ENDPOINT TESTS
# =============================================================================

class TestFrequencyModeEndpoints:
    """Tests for frequency controller endpoints."""

    def test_get_frequency_mode(self, client, mock_freq_controller):
        with _patch_freq(mock_freq_controller):
            resp = client.get('/frequency_mode')
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['success'] is True
            assert 'frequency_state' in data
            assert data['frequency_state']['dominant_mode'] == 'alpha'
            assert 'bands' in data

    def test_set_frequency_mode_valid(self, client, mock_freq_controller):
        with _patch_freq(mock_freq_controller):
            resp = client.post(
                '/set_frequency_mode',
                data=json.dumps({'mode': 'beta', 'activation': 0.8}),
                content_type='application/json',
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['success'] is True

    def test_set_frequency_mode_invalid(self, client, mock_freq_controller):
        with _patch_freq(mock_freq_controller):
            resp = client.post(
                '/set_frequency_mode',
                data=json.dumps({'mode': 'invalid_mode'}),
                content_type='application/json',
            )
            assert resp.status_code == 400
            data = resp.get_json()
            assert 'error' in data
            assert 'available_modes' in data

    def test_get_frequency_bands(self, client, mock_freq_controller):
        with _patch_freq(mock_freq_controller):
            resp = client.get('/frequency_bands')
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['success'] is True
            assert 'bands' in data
            bands = data['bands']
            assert 'alpha' in bands
            assert 'gamma' in bands


# =============================================================================
# FEATURE CALL ENDPOINT TESTS
# =============================================================================

class TestFeatureCallEndpoint:
    """Tests for POST /feature_call."""

    def test_feature_call_memory_context(self, client, mock_brain):
        with _patch_brain(mock_brain):
            resp = client.post(
                '/feature_call',
                data=json.dumps({
                    'feature': 'memory_context',
                    'task': 'Deploy Docker',
                    'service_name': 'test',
                }),
                content_type='application/json',
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['success'] is True
            assert data['feature'] == 'memory_context'
            assert 'data' in data
            assert data['task'] == 'Deploy Docker'

    def test_feature_call_missing_feature(self, client, mock_brain):
        with _patch_brain(mock_brain):
            resp = client.post(
                '/feature_call',
                data=json.dumps({'task': 'Deploy Docker'}),
                content_type='application/json',
            )
            assert resp.status_code == 400

    def test_feature_call_missing_task(self, client, mock_brain):
        with _patch_brain(mock_brain):
            resp = client.post(
                '/feature_call',
                data=json.dumps({'feature': 'memory_context'}),
                content_type='application/json',
            )
            assert resp.status_code == 400

    def test_feature_call_unknown_feature(self, client, mock_brain):
        with _patch_brain(mock_brain):
            resp = client.post(
                '/feature_call',
                data=json.dumps({
                    'feature': 'nonexistent_feature',
                    'task': 'Deploy Docker',
                }),
                content_type='application/json',
            )
            assert resp.status_code == 400
            data = resp.get_json()
            assert 'available_features' in data


# =============================================================================
# AUTO FREQUENCY ENDPOINT TESTS
# =============================================================================

class TestAutoFrequencyEndpoint:
    """Tests for POST /auto_frequency."""

    def test_auto_frequency_switch(self, client, mock_freq_controller):
        with _patch_freq(mock_freq_controller):
            resp = client.post(
                '/auto_frequency',
                data=json.dumps({
                    'task_type': 'reasoning',
                    'urgency': 0.8,
                    'complexity': 0.9,
                    'requires_learning': False,
                    'requires_action': True,
                }),
                content_type='application/json',
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['success'] is True


# =============================================================================
# MARKER ENDPOINT TESTS
# =============================================================================

class TestMarkerEndpoints:
    """Tests for marker-related endpoints."""

    def test_get_markers(self, client, mock_freq_controller):
        with _patch_freq(mock_freq_controller):
            resp = client.get('/markers')
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['success'] is True
            assert 'markers' in data
            assert 'total' in data

    def test_set_marker(self, client, mock_freq_controller):
        with _patch_freq(mock_freq_controller):
            resp = client.post(
                '/set_marker',
                data=json.dumps({
                    'decision_point': 'Choose deployment strategy',
                    'alternatives': ['blue-green', 'canary', 'rolling'],
                    'confidence': 0.75,
                }),
                content_type='application/json',
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['success'] is True
            assert data['marker']['marker_id'] == 'marker_abc'
            assert data['marker']['decision_point'] == 'test decision'

    def test_jump_to_marker_success(self, client, mock_freq_controller):
        with _patch_freq(mock_freq_controller):
            resp = client.post(
                '/jump_to_marker',
                data=json.dumps({'marker_id': 'marker_abc'}),
                content_type='application/json',
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['success'] is True
            assert data['jumped'] is True

    def test_jump_to_marker_missing_id(self, client, mock_freq_controller):
        with _patch_freq(mock_freq_controller):
            resp = client.post(
                '/jump_to_marker',
                data=json.dumps({}),
                content_type='application/json',
            )
            assert resp.status_code == 400

    def test_jump_to_marker_not_found(self, client, mock_freq_controller):
        mock_freq_controller.jump_to_marker.return_value = None
        with _patch_freq(mock_freq_controller):
            resp = client.post(
                '/jump_to_marker',
                data=json.dumps({'marker_id': 'nonexistent'}),
                content_type='application/json',
            )
            assert resp.status_code == 404
            data = resp.get_json()
            assert data['jumped'] is False


# =============================================================================
# CONTENT TYPE TESTS
# =============================================================================

class TestResponseContentTypes:
    """Verify all endpoints return application/json."""

    def test_health_content_type(self, client, mock_brain, mock_heartbeat):
        with _patch_brain(mock_brain), _patch_heartbeat(mock_heartbeat):
            resp = client.get('/health')
            assert resp.content_type == 'application/json'

    def test_cognitive_loop_content_type(self, client, mock_brain):
        with _patch_brain(mock_brain):
            resp = client.get('/cognitive_loop_state')
            assert resp.content_type == 'application/json'

    def test_predict_content_type(self, client, mock_brain):
        with _patch_brain(mock_brain):
            resp = client.post(
                '/predict',
                data=json.dumps({'task': 'test'}),
                content_type='application/json',
            )
            assert resp.content_type == 'application/json'

    def test_frequency_mode_content_type(self, client, mock_freq_controller):
        with _patch_freq(mock_freq_controller):
            resp = client.get('/frequency_mode')
            assert resp.content_type == 'application/json'

    def test_statistics_content_type(self, client, mock_brain):
        with _patch_brain(mock_brain):
            resp = client.get('/statistics')
            assert resp.content_type == 'application/json'


# =============================================================================
# EDGE CASE TESTS
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_predict_default_service_name(self, client, mock_brain):
        """When service_name is not provided, defaults to 'unknown'."""
        with _patch_brain(mock_brain):
            resp = client.post(
                '/predict',
                data=json.dumps({'task': 'test task'}),
                content_type='application/json',
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['service_name'] == 'unknown'

    def test_homeostatic_error_handling(self, client, mock_brain):
        """When homeostatic system throws, endpoint returns error gracefully."""
        mock_brain.cognitive_loop._homeostatic.state.energy = PropertyMock(
            side_effect=AttributeError('no energy')
        )
        # Force the AttributeError by making state access fail
        mock_brain.cognitive_loop._homeostatic.state = MagicMock(
            side_effect=AttributeError('broken state')
        )
        with _patch_brain(mock_brain):
            resp = client.get('/homeostatic_state')
            assert resp.status_code == 200
            data = resp.get_json()
            # Should return error key due to AttributeError
            assert data['enabled'] is True
            assert 'error' in data

    def test_emotional_state_error_handling(self, client, mock_brain):
        """When emotional system throws, endpoint returns error gracefully."""
        mock_brain.cognitive_loop._emotional_system.get_state_dict.side_effect = TypeError('bad state')
        with _patch_brain(mock_brain):
            resp = client.get('/emotional_state')
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['enabled'] is True
            assert 'error' in data

    def test_consciousness_state_error_handling(self, client, mock_brain):
        """When consciousness system throws, endpoint returns error gracefully."""
        type(mock_brain.planner.consciousness).current_state = PropertyMock(
            side_effect=TypeError('broken consciousness')
        )
        with _patch_brain(mock_brain):
            resp = client.get('/consciousness_state')
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['enabled'] is True
            assert 'error' in data

    def test_neuromodulation_error_handling(self, client, mock_brain):
        """When neuromodulation system throws, endpoint returns error gracefully."""
        mock_brain.planner.neuromodulation.levels.to_dict.side_effect = AttributeError('levels broken')
        with _patch_brain(mock_brain):
            resp = client.get('/neuromodulation_state')
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['enabled'] is True
            assert 'error' in data

    def test_goal_graph_error_handling(self, client, mock_brain):
        """When goal graph throws, endpoint returns error gracefully."""
        mock_brain.planner.goal_graph.get_all_goals.side_effect = TypeError('graph broken')
        with _patch_brain(mock_brain):
            resp = client.get('/goal_graph_state')
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['enabled'] is True
            assert 'error' in data

    def test_sensory_extract_error_handling(self, client, mock_brain):
        """When sensory preprocessor throws, endpoint returns error gracefully."""
        mock_brain.sensory_preprocessor.extract.side_effect = TypeError('extract failed')
        with _patch_brain(mock_brain):
            resp = client.post(
                '/sensory_extract',
                data=json.dumps({'text': 'test'}),
                content_type='application/json',
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['enabled'] is True
            assert 'error' in data

    def test_memory_state_error_handling(self, client, mock_brain):
        """When memory system throws, endpoint returns error gracefully."""
        mock_brain.planner.memory.working.__len__ = MagicMock(side_effect=TypeError('broken'))
        with _patch_brain(mock_brain):
            resp = client.get('/memory_state')
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['enabled'] is True
            assert 'error' in data
