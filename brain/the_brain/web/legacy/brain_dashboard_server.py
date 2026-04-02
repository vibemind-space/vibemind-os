"""
Brain Dashboard Web Server

Flask server that exposes brain outputs as JSON API endpoints
and serves an interactive web dashboard.
"""

import sys
import os
# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from flask import Flask, jsonify, render_template, send_from_directory, request
from flask_cors import CORS
import numpy as np
import json
from datetime import datetime
import threading
import time

from core.meta_router import MetaRouter
from core.brain_monitor import BrainActivityMonitor
from core.strategy_library import StrategyLibrary
from core.live_brain_monitor import LiveBrainMonitor, LiveConversationState
from core.conversation_trace_encoder import load_session_logs
from core.conversation_path_planner import ConversationPathPlanner
from core.multi_llm_router import MultiLLMRouter
from core.hierarchical_planner import HierarchicalPlanner
from core.brain_frequency_controller import BrainFrequencyController, FrequencyMode, FrequencyMixer
from core.layer4_temporal_router import Layer4TemporalRouter
from core.oscillator_checkpoint import CheckpointManager
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__ + '/..')))
from load_env import get_openrouter_key
import requests

app = Flask(__name__,
            template_folder='templates',
            static_folder='static')
CORS(app)

# Global brain components
meta_router = None
brain_monitor = None
strategy_lib = None
live_monitor = None
path_planner = None
llm_router = None
hierarchical_planner = None
frequency_controller = None
frequency_mixer = None

# Layer4 Oscillator components
layer4_router = None
checkpoint_manager = None
oscillator_history = []
MAX_OSCILLATOR_HISTORY = 100

# Unified Brain Service URL
UNIFIED_BRAIN_URL = "http://localhost:5003"

# Global state
current_conversation = None
conversation_history = []
intervention_history = []
chat_history = []

# Session management for user IDs (for Infinite Chat memory isolation)
import uuid
session_user_id = None  # Will be generated on first chat message

def convert_numpy(obj):
    """Convert NumPy types to Python types for JSON serialization."""
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: convert_numpy(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy(v) for v in obj]
    return obj

def initialize_brain():
    """Initialize brain components with training data."""
    global meta_router, brain_monitor, strategy_lib, live_monitor, path_planner

    print("Initializing brain components...")

    # Initialize components
    meta_router = MetaRouter(enable_hippocampus=True, seed=42)
    brain_monitor = BrainActivityMonitor(history_length=100)
    strategy_lib = StrategyLibrary(max_strategies_per_type=20)

    # Train on session logs
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'logs', 'sessions')
    print(f"Loading session logs from {log_dir}...")

    all_traces = load_session_logs(log_dir, limit=39)
    print(f"Loaded {len(all_traces)} traces")

    for trace in all_traces:
        out = meta_router.process_trace(trace, adapt=True)
        brain_monitor.update(out)

        features = trace.get_features()
        if features['success']:
            strategy_lib.add_strategy(
                task_type=features['tool_type'],
                tool_sequence=features['tools_used'],
                duration=features['duration_seconds'],
                success=True
            )

    # Initialize live monitor
    live_monitor = LiveBrainMonitor(
        meta_router=meta_router,
        brain_monitor=brain_monitor,
        strategy_library=strategy_lib,
        error_threshold=5,
        repetition_threshold=3,
        check_interval=2
    )

    # Initialize path planner
    print("Initializing path planner...")
    path_planner = ConversationPathPlanner(
        meta_router=meta_router,
        strategy_library=strategy_lib,
        brain_monitor=brain_monitor
    )
    # Train from same session logs
    path_planner.train_from_sessions(log_dir, limit=None)

    print(f"Brain initialized! {strategy_lib.total_strategies} strategies learned")
    print(f"Path planner ready with conversation graph!")

    # Initialize Multi-LLM Router
    global llm_router, hierarchical_planner
    try:
        api_key = get_openrouter_key()
        if api_key:
            llm_router = MultiLLMRouter(openrouter_api_key=api_key)
            mode = "DEV" if llm_router.dev_mode else "PRODUCTION"
            print(f"Multi-LLM Router initialized ({mode} mode)")
        else:
            print("Multi-LLM Router not initialized (no API key)")
    except Exception as e:
        print(f"Multi-LLM Router initialization failed: {e}")

    # Initialize Hierarchical Planner
    try:
        hierarchical_planner = HierarchicalPlanner(
            conversation_planner=path_planner,
            intervention_types=['suggest', 'retry', 'wait', 'terminate', 'execute'],
            # ALL 13 COGNITIVE PHASES ENABLED! (Multi-Brain Swarm disabled to avoid JAX dependency)
            enable_memory=True,                     # PHASE 1: Memory Systems
            enable_predictive_coding=True,          # PHASE 2: Predictive Coding
            enable_attention=True,                  # PHASE 3: Attention Mechanisms
            enable_meta_learning=True,              # PHASE 4: Meta-Learning
            enable_dream_mode=True,                 # PHASE 5: Dream Mode
            enable_neuromodulation=True,            # PHASE 6: Neuromodulation
            enable_temporal_memory=True,            # PHASE 7: Temporal Memory
            enable_active_inference=True,           # PHASE 8: Active Inference
            enable_compositional_reasoning=True,    # PHASE 9: Compositional Reasoning
            enable_tool_creation=True,              # PHASE 10: Tool Creation
            enable_consciousness_metrics=True,      # PHASE 11: Consciousness Metrics
            enable_multi_brain_swarm=False,         # PHASE 12: Multi-Brain Swarm 🐝 (disabled to avoid JAX)
            num_swarm_brains=1,                     # 1 brain (swarm disabled)
            enable_ctm_async=True,                  # PHASE 13: CTM Async Reasoning 🧠
            ctm_complexity_threshold=0.40,          # Trigger CTM at 40% complexity (lowered for LLM limitations)
            ctm_max_steps=50,                       # Max reasoning steps
            seed=42
        )
        print("Hierarchical Planner initialized")
    except Exception as e:
        print(f"Hierarchical Planner initialization failed: {e}")

    # Initialize Layer4 Temporal Router (Oscillator-based routing)
    global layer4_router, checkpoint_manager
    try:
        layer4_router = Layer4TemporalRouter(
            strict_security=True,
            timing_threshold=0.5,
            enable_deep_reasoning=False  # Disable for faster response
        )
        checkpoint_manager = CheckpointManager()
        print(f"Layer4 Temporal Router initialized!")
        print(f"  - Oscillator: {layer4_router.oscillator}")
        print(f"  - Using Mamba: {layer4_router.temporal_ctm.use_mamba}")
        print(f"  - Using Ollama: {layer4_router.token_adapter._using_ollama}")
    except Exception as e:
        print(f"Layer4 Temporal Router initialization failed: {e}")

# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.route('/')
def index():
    """Serve the main dashboard page."""
    return render_template('brain_dashboard.html')


@app.route('/cognitive_loop')
def cognitive_loop_viz():
    """Serve the cognitive loop visualization page (P7.93)."""
    return render_template('cognitive_loop_viz.html')


@app.route('/api/brain/gates')
def get_gates():
    """Get current thalamic gate distribution."""
    if brain_monitor is None:
        return jsonify({'error': 'Brain not initialized'}), 503

    # Get latest gate distribution from brain monitor
    if brain_monitor.gate_history:
        gates = brain_monitor.gate_history[-1]

        modality_names = [
            'vision', 'audio', 'touch', 'taste', 'vestibular', 'threat',
            'tool_trace', 'temporal', 'error_sig', 'success_sig'
        ]

        return jsonify({
            'modalities': modality_names,
            'values': convert_numpy(gates),
            'timestamp': datetime.now().isoformat()
        })

    return jsonify({'error': 'No gate data available'}), 404

@app.route('/api/brain/activation')
def get_activation():
    """Get current brain activation levels."""
    if brain_monitor is None:
        return jsonify({'error': 'Brain not initialized'}), 503

    summary = brain_monitor.get_activation_summary()

    return jsonify({
        'activation': convert_numpy(summary['current_activation']),
        'alerts': convert_numpy(summary['alerts']),
        'statistics': {
            'gate_strength': float(summary['gate_strength']),
            'avg_error_rate': float(summary['avg_error_rate']),
            'total_memories': int(summary['total_memories'])
        },
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/brain/state')
def get_state():
    """Get overall brain state."""
    if meta_router is None:
        return jsonify({'error': 'Brain not initialized'}), 503

    state = meta_router.get_state()

    return jsonify({
        'traces_processed': state['traces_processed'],
        'failures_encoded': state['failures_encoded'],
        'successes_encoded': state['successes_encoded'],
        'success_rate': state['successes_encoded'] / state['traces_processed'] if state['traces_processed'] > 0 else 0,
        'memory_efficiency': state['failures_encoded'] / state['traces_processed'] if state['traces_processed'] > 0 else 0,
        'hippocampal_memories': state['thalamo_hippocampal_state']['hippocampal']['num_memories'],
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/brain/strategies')
def get_strategies():
    """Get strategy library statistics."""
    if strategy_lib is None:
        return jsonify({'error': 'Brain not initialized'}), 503

    stats = strategy_lib.get_statistics()

    return jsonify({
        'total_strategies': stats['total_strategies'],
        'task_types': stats['task_types'],
        'total_retrievals': stats['total_retrievals'],
        'strategies_by_type': convert_numpy(stats['strategies_by_type']),
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/brain/interventions')
def get_interventions():
    """Get recent interventions."""
    if live_monitor is None:
        return jsonify({'error': 'Brain not initialized'}), 503

    stats = live_monitor.get_statistics()

    return jsonify({
        'conversations_monitored': stats['conversations_monitored'],
        'interventions_triggered': stats['interventions_triggered'],
        'failures_prevented': stats['failures_prevented'],
        'recent_interventions': convert_numpy(stats['intervention_history']),
        'timestamp': datetime.now().isoformat()
    })

# ============================================================================
# COGNITIVE LOOP API
# ============================================================================

@app.route('/api/brain/cognitive_loop')
def get_cognitive_loop_state():
    """Get cognitive loop state from unified brain service."""
    try:
        resp = requests.get(f'{UNIFIED_BRAIN_URL}/cognitive_loop_state', timeout=2)
        if resp.ok:
            return jsonify(resp.json())
    except Exception:
        pass
    return jsonify({'success': True, 'enabled': False, 'state': None})


# ============================================================================
# AGENT LOOP API (V2 P3.31-33)
# ============================================================================

@app.route('/api/brain/agent_loop_state')
def get_agent_loop_state():
    """Get agent loop state from unified brain service."""
    try:
        resp = requests.get(f'{UNIFIED_BRAIN_URL}/agent_loop_state', timeout=2)
        if resp.ok:
            return jsonify(resp.json())
    except (requests.RequestException, ValueError, KeyError):
        pass
    return jsonify({'success': True, 'enabled': False, 'state': None})


@app.route('/api/brain/agent_loop/submit', methods=['POST'])
def agent_loop_submit():
    """Submit a task to the agent loop via unified brain service."""
    try:
        resp = requests.post(
            f'{UNIFIED_BRAIN_URL}/agent_loop/submit',
            json=request.json,
            timeout=5
        )
        if resp.ok:
            return jsonify(resp.json())
        return jsonify(resp.json()), resp.status_code
    except (requests.RequestException, ValueError, KeyError) as e:
        return jsonify({'error': f'Agent loop not reachable: {e}'}), 503


# ============================================================================
# EMOTIONAL SYSTEM API
# ============================================================================

@app.route('/api/brain/emotional_state')
def get_emotional_state():
    """Get emotional system state from unified brain service."""
    try:
        resp = requests.get(f'{UNIFIED_BRAIN_URL}/emotional_state', timeout=2)
        if resp.ok:
            return jsonify(resp.json())
    except (requests.RequestException, ValueError, KeyError):
        pass
    return jsonify({'enabled': False, 'state': None})


# ============================================================================
# HOMEOSTATIC REGULATION API
# ============================================================================

@app.route('/api/brain/homeostatic_state')
def get_homeostatic_state():
    """Get homeostatic regulation state from unified brain service."""
    try:
        resp = requests.get(f'{UNIFIED_BRAIN_URL}/homeostatic_state', timeout=2)
        if resp.ok:
            return jsonify(resp.json())
    except (requests.RequestException, ValueError, KeyError):
        pass
    return jsonify({'enabled': False, 'state': None})


# ============================================================================
# MEMORY SYSTEM API
# ============================================================================

@app.route('/api/brain/memory_state')
def get_memory_state():
    """Get memory system state from unified brain service."""
    try:
        resp = requests.get(f'{UNIFIED_BRAIN_URL}/memory_state', timeout=2)
        if resp.ok:
            return jsonify(resp.json())
    except (requests.RequestException, ValueError, KeyError):
        pass
    return jsonify({'enabled': False, 'state': None})


# ============================================================================
# HEARTBEAT API (proxied from unified brain)
# ============================================================================

@app.route('/api/brain/heartbeat_status')
def get_heartbeat_status():
    """Get brain heartbeat status from unified brain service."""
    try:
        resp = requests.get(f'{UNIFIED_BRAIN_URL}/heartbeat_status', timeout=2)
        if resp.ok:
            return jsonify(resp.json())
    except (requests.RequestException, ValueError, KeyError):
        pass
    return jsonify({'active': False})


# ============================================================================
# SENSORY PREPROCESSOR API
# ============================================================================

@app.route('/api/brain/sensory_extract', methods=['POST'])
def sensory_extract():
    """Extract sensory features from text via unified brain service."""
    try:
        resp = requests.post(
            f'{UNIFIED_BRAIN_URL}/sensory_extract',
            json=request.json,
            timeout=3
        )
        if resp.ok:
            return jsonify(resp.json())
    except (requests.RequestException, ValueError, KeyError):
        pass
    return jsonify({'enabled': False})


# ============================================================================
# GOAL GRAPH API
# ============================================================================

@app.route('/api/brain/goal_graph_state')
def get_goal_graph_state():
    """Get goal graph state from unified brain service."""
    try:
        resp = requests.get(f'{UNIFIED_BRAIN_URL}/goal_graph_state', timeout=2)
        if resp.ok:
            return jsonify(resp.json())
    except (requests.RequestException, ValueError, KeyError):
        pass
    return jsonify({'enabled': False, 'state': None})


@app.route('/api/brain/neuromodulation_state')
def get_neuromodulation_state():
    """Get neuromodulation state from unified brain service."""
    try:
        resp = requests.get(f'{UNIFIED_BRAIN_URL}/neuromodulation_state', timeout=2)
        if resp.ok:
            return jsonify(resp.json())
    except (requests.RequestException, ValueError, KeyError):
        pass
    return jsonify({'enabled': False, 'state': None})


@app.route('/api/brain/consciousness_state')
def get_consciousness_state():
    """Get consciousness metrics state from unified brain service."""
    try:
        resp = requests.get(f'{UNIFIED_BRAIN_URL}/consciousness_state', timeout=2)
        if resp.ok:
            return jsonify(resp.json())
    except (requests.RequestException, ValueError, KeyError):
        pass
    return jsonify({'enabled': False, 'state': None})


# ============================================================================
# MONITORING & OBSERVABILITY API (P4.60-65)
# ============================================================================

@app.route('/api/brain/metrics')
def get_metrics():
    """Prometheus metrics from unified brain service (P4.61)."""
    try:
        resp = requests.get(f'{UNIFIED_BRAIN_URL}/metrics', timeout=2)
        if resp.ok:
            return resp.text, 200, {'Content-Type': 'text/plain; charset=utf-8'}
    except (requests.RequestException, ValueError):
        pass
    return '# Metrics unavailable\n', 200, {'Content-Type': 'text/plain; charset=utf-8'}


@app.route('/api/brain/metrics_json')
def get_metrics_json():
    """JSON metrics from unified brain service (P4.61)."""
    try:
        resp = requests.get(f'{UNIFIED_BRAIN_URL}/metrics_json', timeout=2)
        if resp.ok:
            return jsonify(resp.json())
    except (requests.RequestException, ValueError):
        pass
    return jsonify({'error': 'metrics unavailable'})


@app.route('/api/brain/audit_trail')
def get_audit_trail():
    """Prediction audit trail from unified brain service (P4.62)."""
    try:
        resp = requests.get(f'{UNIFIED_BRAIN_URL}/audit_trail', timeout=2)
        if resp.ok:
            return jsonify(resp.json())
    except (requests.RequestException, ValueError):
        pass
    return jsonify({'recent': [], 'stats': {}})


@app.route('/api/brain/loop_traces')
def get_loop_traces():
    """Cognitive loop traces from unified brain service (P4.63)."""
    try:
        resp = requests.get(f'{UNIFIED_BRAIN_URL}/loop_traces', timeout=2)
        if resp.ok:
            return jsonify(resp.json())
    except (requests.RequestException, ValueError):
        pass
    return jsonify({'recent_traces': [], 'phase_stats': {}, 'total_traces': 0})


@app.route('/api/brain/error_rates')
def get_error_rates():
    """Per-subsystem error rates from unified brain service (P4.64)."""
    try:
        resp = requests.get(f'{UNIFIED_BRAIN_URL}/error_rates', timeout=2)
        if resp.ok:
            return jsonify(resp.json())
    except (requests.RequestException, ValueError):
        pass
    return jsonify({'error_rates': {}, 'recent_errors': []})


@app.route('/api/brain/heatmap')
def get_brain_heatmap():
    """Brain activity heatmap from unified brain service (P4.65)."""
    try:
        resp = requests.get(f'{UNIFIED_BRAIN_URL}/brain_heatmap', timeout=2)
        if resp.ok:
            return jsonify(resp.json())
    except (requests.RequestException, ValueError):
        pass
    return jsonify({'heatmap': {'modalities': [], 'matrix': []}, 'modality_averages': {}})


# ============================================================================
# FREQUENCY CONTROLLER API
# ============================================================================

@app.route('/api/brain/frequency')
def get_frequency():
    """Get current frequency mode state."""
    global frequency_controller, frequency_mixer

    # Try to get from unified brain service first
    try:
        resp = requests.get(f"{UNIFIED_BRAIN_URL}/frequency_mode", timeout=2)
        if resp.status_code == 200:
            data = resp.json()
            return jsonify({
                'source': 'unified_brain',
                'dominant_mode': data.get('dominant_mode', 'alpha'),
                'activations': data.get('activations', {}),
                'active_modes': data.get('active_modes', []),
                'mode_switches': data.get('mode_switches', 0),
                'markers_count': data.get('markers_count', 0),
                'timestamp': datetime.now().isoformat()
            })
    except (requests.RequestException, ValueError, KeyError):
        pass

    # Fallback to local frequency controller
    if frequency_controller is None:
        frequency_controller = BrainFrequencyController(
            default_mode=FrequencyMode.ALPHA,
            enable_auto_switch=True
        )
        frequency_mixer = FrequencyMixer(frequency_controller)

    state = frequency_controller.get_state()
    return jsonify({
        'source': 'local',
        'dominant_mode': state['dominant_mode'],
        'activations': state['activations'],
        'active_modes': state['active_modes'],
        'mode_switches': state['mode_switches'],
        'markers_count': state['markers_count'],
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/brain/frequency/set', methods=['POST'])
def set_frequency():
    """Set frequency mode."""
    global frequency_controller

    data = request.json or {}
    mode = data.get('mode', 'alpha')
    activation = data.get('activation', 1.0)

    # Try unified brain service first
    try:
        resp = requests.post(
            f"{UNIFIED_BRAIN_URL}/set_frequency_mode",
            json={'mode': mode, 'activation': activation},
            timeout=2
        )
        if resp.status_code == 200:
            return jsonify(resp.json())
    except (requests.RequestException, ValueError, KeyError):
        pass

    # Fallback to local
    if frequency_controller is None:
        frequency_controller = BrainFrequencyController(default_mode=FrequencyMode.ALPHA)

    try:
        mode_enum = FrequencyMode(mode)
        result = frequency_controller.set_mode(mode_enum, activation, suppress_others=True)
        return jsonify(result)
    except ValueError:
        return jsonify({'error': f'Invalid mode: {mode}'}), 400

@app.route('/api/brain/frequency/bands')
def get_frequency_bands():
    """Get frequency band information."""
    # Try unified brain service first
    try:
        resp = requests.get(f"{UNIFIED_BRAIN_URL}/frequency_bands", timeout=2)
        if resp.status_code == 200:
            return jsonify(resp.json())
    except (requests.RequestException, ValueError, KeyError):
        pass

    # Return static band info
    bands = []
    for mode in FrequencyMode:
        band = BrainFrequencyController.FREQUENCY_BANDS[mode]
        bands.append({
            'mode': mode.value,
            'min_hz': band.min_hz,
            'max_hz': band.max_hz,
            'description': band.description,
            'primary_function': band.primary_function,
            'components': band.associated_components
        })

    return jsonify({'bands': bands, 'timestamp': datetime.now().isoformat()})

@app.route('/api/brain/frequency/markers')
def get_frequency_markers():
    """Get recent frequency markers."""
    # Try unified brain service first
    try:
        resp = requests.get(f"{UNIFIED_BRAIN_URL}/markers", timeout=2)
        if resp.status_code == 200:
            return jsonify(resp.json())
    except (requests.RequestException, ValueError, KeyError):
        pass

    # Fallback to local
    if frequency_controller is None:
        return jsonify({'markers': [], 'count': 0})

    markers = frequency_controller.get_recent_markers(20)
    return jsonify({
        'markers': [
            {
                'id': m.marker_id,
                'mode': m.mode.value,
                'decision_point': m.decision_point,
                'confidence': m.confidence,
                'timestamp': m.timestamp.isoformat(),
                'visited': m.visited
            }
            for m in markers
        ],
        'count': len(markers),
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/conversation/start', methods=['POST'])
def start_conversation():
    """Start monitoring a new conversation."""
    global current_conversation

    if live_monitor is None:
        return jsonify({'error': 'Brain not initialized'}), 503

    current_conversation = live_monitor.start_conversation("Web Dashboard Test Task")

    return jsonify({
        'status': 'started',
        'conversation_id': id(current_conversation),
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/conversation/event/<event_type>')
def add_event(event_type):
    """Add an event to the current conversation."""
    global current_conversation

    if current_conversation is None:
        return jsonify({'error': 'No active conversation'}), 400

    if event_type == 'tool_call':
        current_conversation.add_tool_call('test_tool')
    elif event_type == 'error':
        current_conversation.add_error()
    elif event_type == 'clarification':
        current_conversation.add_clarification()
    elif event_type == 'qa_reject':
        current_conversation.add_qa_reject()

    # Check for intervention
    intervention = live_monitor.update(current_conversation)

    response = {
        'status': 'ok',
        'current_state': convert_numpy(current_conversation.get_features()),
        'intervention': None,
        'timestamp': datetime.now().isoformat()
    }

    if intervention:
        response['intervention'] = convert_numpy(intervention)

    return jsonify(response)

@app.route('/api/conversation/end/<outcome>')
def end_conversation(outcome):
    """End the current conversation."""
    global current_conversation

    if current_conversation is None:
        return jsonify({'error': 'No active conversation'}), 400

    success = outcome == 'success'
    live_monitor.end_conversation(current_conversation, success=success, outcome=outcome)

    conversation_history.append({
        'task': current_conversation.task,
        'duration': current_conversation.get_duration(),
        'errors': current_conversation.error_count,
        'success': success,
        'outcome': outcome,
        'timestamp': datetime.now().isoformat()
    })

    current_conversation = None

    return jsonify({
        'status': 'ended',
        'outcome': outcome,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/simulate/scenario/<scenario_name>')
def simulate_scenario(scenario_name):
    """Simulate a conversation scenario."""
    conversation = live_monitor.start_conversation(f"Simulated: {scenario_name}")

    if scenario_name == 'success':
        # Quick successful task
        conversation.add_tool_call('list_items')
        conversation.add_tool_call('format_output')
        intervention = live_monitor.update(conversation)
        live_monitor.end_conversation(conversation, success=True, outcome='completed')

    elif scenario_name == 'errors':
        # Errors accumulating
        for i in range(6):
            conversation.add_tool_call('retry_operation')
            conversation.add_error()
            intervention = live_monitor.update(conversation)
            if intervention:
                break
        live_monitor.end_conversation(conversation, success=False, outcome='failed')

    elif scenario_name == 'loop':
        # Stuck in loop
        for i in range(4):
            conversation.add_tool_call('check_status')
        intervention = live_monitor.update(conversation)
        live_monitor.end_conversation(conversation, success=False, outcome='terminated')

    # Update brain monitor with simulated data
    if brain_monitor and conversation:
        # Create a mock routing output for brain monitor
        features = conversation.get_features()
        mock_output = {
            'final_gates': brain_monitor.gate_history[-1] if brain_monitor.gate_history else np.ones(10) / 10,
            'trace_features': features,
            'error_count': features['error_count'],
            'success': features['success']
        }
        brain_monitor.update(mock_output)

    return jsonify({
        'status': 'simulated',
        'scenario': scenario_name,
        'intervention': convert_numpy(intervention) if intervention else None,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/predict/path', methods=['POST'])
def predict_path():
    """Predict optimal path for a given task description."""
    from flask import request

    if path_planner is None:
        return jsonify({'error': 'Path planner not initialized'}), 503

    data = request.get_json()
    task_description = data.get('task', '')

    if not task_description:
        return jsonify({'error': 'Task description required'}), 400

    # Get prediction
    prediction = path_planner.predict_optimal_path(task_description)

    if prediction is None:
        return jsonify({
            'status': 'no_prediction',
            'task': task_description,
            'message': 'Not enough training data for this task type'
        })

    # Convert to JSON-serializable format
    return jsonify({
        'status': 'success',
        'task': task_description,
        'prediction': {
            'task_type': prediction.task_type,
            'predicted_sequence': prediction.predicted_sequence,
            'expected_duration': float(prediction.expected_duration),
            'expected_errors': int(prediction.expected_errors),
            'success_probability': float(prediction.success_probability),
            'confidence': float(prediction.confidence),
            'similar_sessions': int(prediction.similar_sessions),
            'alternative_paths': prediction.alternative_paths,
            'dominant_modalities': prediction.dominant_modalities,
            'memory_retrieval': convert_numpy(prediction.memory_retrieval)
        },
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/chat/send', methods=['POST'])
def send_chat():
    """Send a message to the brain chat system."""
    global chat_history, session_user_id

    data = request.get_json()
    message = data.get('message', '')

    if not message:
        return jsonify({'error': 'Message required'}), 400

    # Generate session user_id if not exists (for Infinite Chat memory isolation)
    if session_user_id is None:
        session_user_id = f"dashboard_session_{uuid.uuid4().hex[:8]}"
        print(f"[Dashboard] Created session user_id: {session_user_id}")

        # Set user_id in llm_router and hierarchical_planner
        if llm_router:
            llm_router.set_user_id(session_user_id)
        if hierarchical_planner:
            hierarchical_planner.set_user_id(session_user_id)

    # Add user message to history
    chat_history.append({
        'role': 'user',
        'content': message,
        'timestamp': datetime.now().isoformat()
    })

    response = {
        'task_type': 'unknown',
        'confidence': 0.0,
        'action': 'unknown',
        'reasoning': 'System not fully initialized',
        'sequence': [],
        'llm_stats': None,
        'session_user_id': session_user_id  # Include in response for debugging
    }

    # Phase 1: Extract features with LLM (with automatic memory via Infinite Chat)
    if llm_router:
        try:
            features = llm_router.extract_features(message)
            response['task_type'] = features.get('task_type', 'unknown')
            response['complexity'] = features.get('complexity', 0.5)
            response['urgency'] = features.get('urgency', 0.5)
        except Exception as e:
            response['llm_error'] = str(e)

    # Phase 2: Plan with hierarchical planner (with automatic memory via Infinite Chat)
    if hierarchical_planner:
        try:
            result = hierarchical_planner.predict(message)
            response['task_type'] = result.task_type
            response['confidence'] = float(result.confidence)
            response['sequence'] = result.predicted_sequence

            # Add more detailed information
            if result.actionable_decision:
                # Extract the useful info from actionable decision
                decision = result.actionable_decision
                if hasattr(decision, 'multi_target_decision') and decision.multi_target_decision:
                    primary = decision.multi_target_decision.get('primary', {})
                    response['action'] = primary.get('type', 'unknown').upper()
                    response['action_reasoning'] = primary.get('reasoning', '')
                    response['action_confidence'] = primary.get('confidence', 0)

                    # Add alternatives
                    alternatives = decision.multi_target_decision.get('alternatives', [])
                    if alternatives:
                        response['alternative_actions'] = [
                            {
                                'type': alt.get('type', ''),
                                'weight': alt.get('weight', 0),
                                'reasoning': alt.get('reasoning', '')
                            }
                            for alt in alternatives[:2]  # Top 2 alternatives
                        ]

                # Add reasoning chain if available
                if hasattr(decision, 'reasoning_chain'):
                    response['reasoning_chain'] = decision.reasoning_chain

            # Add questions if generated
            if result.inference_state and hasattr(result.inference_state, 'generated_questions') and result.inference_state.generated_questions:
                response['questions'] = [
                    {
                        'text': q.question_text,
                        'type': q.question_type if hasattr(q, 'question_type') else 'clarification'
                    }
                    for q in result.inference_state.generated_questions
                ]

            # Add dominant modalities
            if result.dominant_modalities:
                response['brain_areas'] = result.dominant_modalities

            # Add success probability
            if hasattr(result, 'success_probability'):
                response['success_probability'] = float(result.success_probability)

        except Exception as e:
            response['planner_error'] = str(e)

    # Get LLM stats
    if llm_router:
        try:
            stats = llm_router.get_statistics()
            response['llm_stats'] = {
                'total_calls': stats['overall']['total_calls'],
                'total_cost': stats['overall']['total_estimated_cost_usd'],
                'mode': 'DEV' if llm_router.dev_mode else 'PRODUCTION'
            }
        except (AttributeError, KeyError, TypeError):
            pass

    # Add assistant response to history
    chat_history.append({
        'role': 'assistant',
        'content': response,
        'timestamp': datetime.now().isoformat()
    })

    return jsonify({
        'status': 'success',
        'response': convert_numpy(response),
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/chat/history')
def get_chat_history():
    """Get chat history."""
    return jsonify({
        'history': convert_numpy(chat_history),
        'count': len(chat_history),
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/chat/clear', methods=['POST'])
def clear_chat():
    """Clear chat history and reset session (creates new user_id for fresh memory)."""
    global chat_history, session_user_id

    chat_history = []

    # Reset session user_id to start fresh memory context
    session_user_id = None
    if llm_router:
        llm_router.set_user_id(None)
    if hierarchical_planner:
        hierarchical_planner.set_user_id(None)

    print("[Dashboard] Cleared chat history and reset session user_id")

    return jsonify({
        'status': 'cleared',
        'message': 'Chat history cleared. Next message will start new memory session.',
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/llm/stats')
def get_llm_stats():
    """Get LLM router statistics."""
    if llm_router is None:
        return jsonify({'error': 'LLM router not initialized'}), 503

    try:
        stats = llm_router.get_statistics()
        return jsonify({
            'mode': 'DEV' if llm_router.dev_mode else 'PRODUCTION',
            'models': {
                name: config.model
                for name, config in llm_router.llm_configs.items()
            },
            'statistics': convert_numpy(stats),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================================================
# AUTONOMOUS BRAIN API PROXIES (Port 5001)
# ============================================================================

import requests

AUTONOMOUS_BRAIN_URL = "http://localhost:5001"

@app.route('/api/autonomous/health')
def autonomous_health():
    """Get autonomous brain health status."""
    try:
        response = requests.get(f"{AUTONOMOUS_BRAIN_URL}/health", timeout=2)
        return jsonify(response.json()), response.status_code
    except requests.RequestException as e:
        return jsonify({'error': 'Autonomous brain not reachable', 'details': str(e)}), 503

@app.route('/api/autonomous/heartbeat')
def autonomous_heartbeat():
    """Get autonomous brain heartbeat status."""
    try:
        response = requests.get(f"{AUTONOMOUS_BRAIN_URL}/heartbeat", timeout=2)
        return jsonify(response.json()), response.status_code
    except requests.RequestException as e:
        return jsonify({'error': 'Autonomous brain not reachable', 'details': str(e)}), 503

@app.route('/api/autonomous/brain_state')
def autonomous_brain_state():
    """Get complete autonomous brain cognitive state."""
    try:
        response = requests.get(f"{AUTONOMOUS_BRAIN_URL}/brain_state", timeout=2)
        return jsonify(response.json()), response.status_code
    except requests.RequestException as e:
        return jsonify({'error': 'Autonomous brain not reachable', 'details': str(e)}), 503

@app.route('/api/autonomous/heartbeat/config')
def autonomous_heartbeat_config():
    """Get autonomous brain heartbeat configuration."""
    try:
        response = requests.get(f"{AUTONOMOUS_BRAIN_URL}/heartbeat/config", timeout=2)
        return jsonify(response.json()), response.status_code
    except requests.RequestException as e:
        return jsonify({'error': 'Autonomous brain not reachable', 'details': str(e)}), 503

# ============================================================================
# NEW COGNITIVE FEATURES API (Phase 8 - Meta-CTM, Goal Graph, Evolution)
# ============================================================================

@app.route('/api/brain/ctm_health')
def get_ctm_health():
    """Get CTM health status from Meta-CTM Supervisor."""
    if hierarchical_planner is None:
        return jsonify({'error': 'Hierarchical planner not initialized'}), 503

    try:
        # Access through multi_ctm_ensemble if available
        if hasattr(hierarchical_planner, 'multi_ctm_ensemble') and hierarchical_planner.multi_ctm_ensemble:
            health = hierarchical_planner.multi_ctm_ensemble.get_ctm_health()
            routing_stats = hierarchical_planner.multi_ctm_ensemble.supervisor.get_statistics()
            return jsonify({
                'ctm_health': convert_numpy(health),
                'routing_stats': convert_numpy(routing_stats),
                'timestamp': datetime.now().isoformat()
            })
        else:
            return jsonify({
                'message': 'Multi-CTM Ensemble not enabled',
                'ctm_health': {},
                'timestamp': datetime.now().isoformat()
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/brain/goals')
def get_goals():
    """Get Goal Graph status."""
    if hierarchical_planner is None:
        return jsonify({'error': 'Hierarchical planner not initialized'}), 503

    try:
        if hasattr(hierarchical_planner, 'goal_graph') and hierarchical_planner.goal_graph:
            goals_data = hierarchical_planner.get_goals()
            return jsonify({
                'goals': convert_numpy(goals_data),
                'timestamp': datetime.now().isoformat()
            })
        else:
            return jsonify({
                'message': 'Goal Graph not enabled',
                'goals': {},
                'timestamp': datetime.now().isoformat()
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/brain/goals/add', methods=['POST'])
def add_goal():
    """Add a new goal to the Goal Graph."""
    if hierarchical_planner is None:
        return jsonify({'error': 'Hierarchical planner not initialized'}), 503

    try:
        data = request.get_json()
        description = data.get('description', '')
        priority = data.get('priority', 'medium')
        parent_id = data.get('parent_id', None)

        if not description:
            return jsonify({'error': 'Description required'}), 400

        goal = hierarchical_planner.add_goal(
            description=description,
            priority=priority,
            parent_id=parent_id
        )

        if goal:
            return jsonify({
                'success': True,
                'goal_id': goal.goal_id,
                'description': goal.description,
                'timestamp': datetime.now().isoformat()
            })
        else:
            return jsonify({'error': 'Failed to add goal'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/brain/goals/<goal_id>/complete', methods=['POST'])
def complete_goal(goal_id):
    """Mark a goal as completed."""
    if hierarchical_planner is None:
        return jsonify({'error': 'Hierarchical planner not initialized'}), 503

    try:
        # First start the goal (required before completion)
        if hierarchical_planner.goal_graph:
            hierarchical_planner.goal_graph.start_goal(goal_id)

        success = hierarchical_planner.complete_goal(goal_id)
        if success:
            return jsonify({
                'success': True,
                'goal_id': goal_id,
                'timestamp': datetime.now().isoformat()
            })
        else:
            return jsonify({'error': 'Failed to complete goal'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/brain/goals/<goal_id>/fail', methods=['POST'])
def fail_goal(goal_id):
    """Mark a goal as failed."""
    if hierarchical_planner is None:
        return jsonify({'error': 'Hierarchical planner not initialized'}), 503

    try:
        data = request.get_json() or {}
        reason = data.get('reason', '')

        # First start the goal (required before failing)
        if hierarchical_planner.goal_graph:
            hierarchical_planner.goal_graph.start_goal(goal_id)

        success = hierarchical_planner.fail_goal(goal_id, reason)
        if success:
            return jsonify({
                'success': True,
                'goal_id': goal_id,
                'reason': reason,
                'timestamp': datetime.now().isoformat()
            })
        else:
            return jsonify({'error': 'Failed to mark goal as failed'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/brain/evolution')
def get_evolution_stats():
    """Get evolutionary CTM selection statistics."""
    if hierarchical_planner is None:
        return jsonify({'error': 'Hierarchical planner not initialized'}), 503

    try:
        if hasattr(hierarchical_planner, 'multi_ctm_ensemble') and hierarchical_planner.multi_ctm_ensemble:
            ensemble = hierarchical_planner.multi_ctm_ensemble
            if ensemble.enable_evolution and ensemble.evolutionary_selector:
                evolution_stats = ensemble.get_evolution_stats()
                return jsonify({
                    'evolution_enabled': True,
                    'stats': convert_numpy(evolution_stats),
                    'domain_task_counts': convert_numpy(ensemble.domain_task_counts),
                    'timestamp': datetime.now().isoformat()
                })
            else:
                return jsonify({
                    'evolution_enabled': False,
                    'message': 'Evolutionary optimization not enabled',
                    'timestamp': datetime.now().isoformat()
                })
        else:
            return jsonify({
                'evolution_enabled': False,
                'message': 'Multi-CTM Ensemble not enabled',
                'timestamp': datetime.now().isoformat()
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/brain/evolution/evolve', methods=['POST'])
def trigger_evolution():
    """Trigger evolution for a specific domain."""
    if hierarchical_planner is None:
        return jsonify({'error': 'Hierarchical planner not initialized'}), 503

    try:
        data = request.get_json()
        domain = data.get('domain', 'spatial')

        if hasattr(hierarchical_planner, 'multi_ctm_ensemble') and hierarchical_planner.multi_ctm_ensemble:
            ensemble = hierarchical_planner.multi_ctm_ensemble
            if ensemble.enable_evolution:
                result = ensemble.evolve_domain(domain)
                return jsonify({
                    'success': True,
                    'domain': domain,
                    'evolution_result': convert_numpy(result),
                    'timestamp': datetime.now().isoformat()
                })
            else:
                return jsonify({'error': 'Evolution not enabled'}), 400
        else:
            return jsonify({'error': 'Multi-CTM Ensemble not enabled'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/brain/cognitive_status')
def get_cognitive_status():
    """Get comprehensive status of all cognitive systems."""
    if hierarchical_planner is None:
        return jsonify({'error': 'Hierarchical planner not initialized'}), 503

    try:
        status = {
            'timestamp': datetime.now().isoformat(),
            'systems': {}
        }

        # Meta-CTM Supervisor status
        if hasattr(hierarchical_planner, 'multi_ctm_ensemble') and hierarchical_planner.multi_ctm_ensemble:
            ensemble = hierarchical_planner.multi_ctm_ensemble
            status['systems']['meta_ctm'] = {
                'enabled': True,
                'health': convert_numpy(ensemble.get_ctm_health()),
                'active_ctms': [d for d, c in ensemble.ctms.items() if c is not None]
            }
        else:
            status['systems']['meta_ctm'] = {'enabled': False}

        # Goal Graph status
        if hasattr(hierarchical_planner, 'goal_graph') and hierarchical_planner.goal_graph:
            goals = hierarchical_planner.get_goals()
            status['systems']['goal_graph'] = {
                'enabled': True,
                'total_goals': goals.get('total_goals', 0),
                'active_goals': goals.get('active_count', 0),
                'completed_goals': goals.get('completed_count', 0)
            }
        else:
            status['systems']['goal_graph'] = {'enabled': False}

        # Evolution status
        if hasattr(hierarchical_planner, 'multi_ctm_ensemble') and hierarchical_planner.multi_ctm_ensemble:
            ensemble = hierarchical_planner.multi_ctm_ensemble
            if ensemble.enable_evolution:
                evo_stats = ensemble.get_evolution_stats()
                status['systems']['evolution'] = {
                    'enabled': True,
                    'domains': list(evo_stats.keys()) if isinstance(evo_stats, dict) else []
                }
            else:
                status['systems']['evolution'] = {'enabled': False}
        else:
            status['systems']['evolution'] = {'enabled': False}

        return jsonify(status)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# OSCILLATOR API ENDPOINTS (Layer4 Temporal Router)
# ============================================================================

def record_oscillator_state():
    """Record current oscillator state to history."""
    global oscillator_history

    if layer4_router is None:
        return

    try:
        osc = layer4_router.get_oscillator_state()
        sync = layer4_router.get_synchrony_vector()
        dominant = layer4_router.get_dominant_channel()
        stats = layer4_router.get_statistics()
        token_stats = stats.get('token_adapter', {})

        entry = {
            'timestamp': datetime.now().isoformat(),
            'A': float(osc.A.amplitude),
            'B': float(osc.B.amplitude),
            'C': float(osc.C.amplitude),
            'phase_A': float(osc.A.phase),
            'phase_B': float(osc.B.phase),
            'phase_C': float(osc.C.phase),
            'coherence': float(sync.mean_coherence),
            'dominant': dominant.value,
            'tokens_processed': token_stats.get('tokens_processed', 0)
        }

        oscillator_history.append(entry)

        # Limit history size
        if len(oscillator_history) > MAX_OSCILLATOR_HISTORY:
            oscillator_history = oscillator_history[-MAX_OSCILLATOR_HISTORY:]

    except Exception as e:
        print(f"Error recording oscillator state: {e}")


@app.route('/api/oscillator/state')
def get_oscillator_state():
    """Get current oscillator state."""
    if layer4_router is None:
        return jsonify({'error': 'Layer4 Router not initialized'}), 503

    try:
        osc = layer4_router.get_oscillator_state()
        sync = layer4_router.get_synchrony_vector()
        dominant = layer4_router.get_dominant_channel()

        return jsonify({
            'channels': {
                'A': {
                    'amplitude': float(osc.A.amplitude),
                    'phase': float(osc.A.phase),
                    'label': 'Advance'
                },
                'B': {
                    'amplitude': float(osc.B.amplitude),
                    'phase': float(osc.B.phase),
                    'label': 'Explore'
                },
                'C': {
                    'amplitude': float(osc.C.amplitude),
                    'phase': float(osc.C.phase),
                    'label': 'Correct'
                }
            },
            'dominant': dominant.value,
            'synchrony': {
                'mean_coherence': float(sync.mean_coherence),
                'vector': convert_numpy(sync.to_vector())
            },
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/oscillator/history')
def get_oscillator_history():
    """Get oscillator history for charts."""
    return jsonify({
        'history': oscillator_history[-50:],  # Last 50 entries
        'count': len(oscillator_history),
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/oscillator/tokens', methods=['POST'])
def process_oscillator_tokens():
    """Process tokens through the oscillator pipeline."""
    if layer4_router is None:
        return jsonify({'error': 'Layer4 Router not initialized'}), 503

    data = request.get_json() or {}
    text = data.get('text', '')

    if not text:
        return jsonify({'error': 'Text required'}), 400

    try:
        # Process through EventBridge
        result = layer4_router.event_bridge.process_text(text)

        # Record state
        record_oscillator_state()

        # Get updated state
        osc = layer4_router.get_oscillator_state()
        dominant = layer4_router.get_dominant_channel()

        return jsonify({
            'tokens_extracted': result,
            'token_count': len(result),
            'state_after': {
                'A': float(osc.A.amplitude),
                'B': float(osc.B.amplitude),
                'C': float(osc.C.amplitude),
                'dominant': dominant.value
            },
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/oscillator/stats')
def get_oscillator_stats():
    """Get oscillator processing statistics."""
    if layer4_router is None:
        return jsonify({'error': 'Layer4 Router not initialized'}), 503

    try:
        stats = layer4_router.get_statistics()
        token_stats = stats.get('token_adapter', {})
        eb_stats = stats.get('event_bridge', {})

        return jsonify({
            'token_adapter': convert_numpy(token_stats),
            'event_bridge': convert_numpy(eb_stats),
            'total_routes': stats.get('total_routes', 0),
            'total_executions': stats.get('total_executions', 0),
            'total_blocks': stats.get('total_blocks', 0),
            'using_mamba': layer4_router.temporal_ctm.use_mamba,
            'using_ollama': layer4_router.token_adapter._using_ollama,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/oscillator/route', methods=['POST'])
def route_oscillator_events():
    """Route events through the full oscillator pipeline."""
    if layer4_router is None:
        return jsonify({'error': 'Layer4 Router not initialized'}), 503

    data = request.get_json() or {}
    events = data.get('events', [])
    task = data.get('task', 'Brain Dashboard Test')

    if not events:
        return jsonify({'error': 'Events required'}), 400

    try:
        result = layer4_router.route(events, task_description=task)

        # Record state
        record_oscillator_state()

        return jsonify({
            'should_execute': result.should_execute,
            'tool_name': result.tool_name,
            'blocked': result.blocked,
            'block_reason': result.block_reason,
            'timing_confidence': float(result.decision.timing_confidence),
            'processing_time_ms': float(result.processing_time_ms),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/oscillator/checkpoint', methods=['POST'])
def save_oscillator_checkpoint():
    """Save current oscillator checkpoint."""
    if layer4_router is None or checkpoint_manager is None:
        return jsonify({'error': 'Layer4 Router not initialized'}), 503

    data = request.get_json() or {}
    name = data.get('name', None)

    try:
        path = checkpoint_manager.save_checkpoint(layer4_router, name)
        return jsonify({
            'status': 'saved',
            'path': path,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/oscillator/checkpoints')
def list_oscillator_checkpoints():
    """List available oscillator checkpoints."""
    if checkpoint_manager is None:
        return jsonify({'error': 'Checkpoint manager not initialized'}), 503

    try:
        checkpoints = checkpoint_manager.list_checkpoints()
        return jsonify({
            'checkpoints': checkpoints,
            'count': len(checkpoints),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/oscillator/restore', methods=['POST'])
def restore_oscillator_checkpoint():
    """Restore oscillator from checkpoint."""
    global oscillator_history

    if layer4_router is None or checkpoint_manager is None:
        return jsonify({'error': 'Layer4 Router not initialized'}), 503

    data = request.get_json() or {}
    name = data.get('name', '')

    if not name:
        return jsonify({'error': 'Checkpoint name required'}), 400

    try:
        checkpoint = checkpoint_manager.load_checkpoint(name)
        if checkpoint is None:
            return jsonify({'error': f'Checkpoint not found: {name}'}), 404

        success = checkpoint_manager.restore_router(layer4_router, checkpoint)

        if success:
            # Clear history after restore
            oscillator_history = []
            record_oscillator_state()

            return jsonify({
                'status': 'restored',
                'checkpoint_name': name,
                'timestamp': datetime.now().isoformat()
            })
        else:
            return jsonify({'error': 'Failed to restore checkpoint'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/oscillator/reset', methods=['POST'])
def reset_oscillator():
    """Reset oscillator state."""
    global oscillator_history

    if layer4_router is None:
        return jsonify({'error': 'Layer4 Router not initialized'}), 503

    try:
        layer4_router.reset()
        oscillator_history = []

        return jsonify({
            'status': 'reset',
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/oscillator/health')
def oscillator_health():
    """Get oscillator health status."""
    return jsonify({
        'status': 'healthy',
        'router_initialized': layer4_router is not None,
        'checkpoint_manager': checkpoint_manager is not None,
        'using_mamba': layer4_router.temporal_ctm.use_mamba if layer4_router else False,
        'using_ollama': layer4_router.token_adapter._using_ollama if layer4_router else False,
        'history_size': len(oscillator_history),
        'timestamp': datetime.now().isoformat()
    })


# ============================================================================
# HEALTH CHECK ENDPOINTS
# ============================================================================

@app.route('/api/health')
def health_check():
    """Overall system health check."""
    components = {
        'meta_router': meta_router is not None,
        'brain_monitor': brain_monitor is not None,
        'strategy_lib': strategy_lib is not None,
        'live_monitor': live_monitor is not None,
        'path_planner': path_planner is not None,
        'llm_router': llm_router is not None,
        'hierarchical_planner': hierarchical_planner is not None,
        'frequency_controller': frequency_controller is not None,
        'layer4_router': layer4_router is not None,
        'checkpoint_manager': checkpoint_manager is not None
    }

    initialized_count = sum(1 for v in components.values() if v)
    total_count = len(components)
    health_percentage = (initialized_count / total_count) * 100

    if health_percentage >= 80:
        status = 'healthy'
    elif health_percentage >= 50:
        status = 'degraded'
    else:
        status = 'unhealthy'

    return jsonify({
        'status': status,
        'health_percentage': health_percentage,
        'components_initialized': initialized_count,
        'components_total': total_count,
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/health/components')
def health_components():
    """Detailed component health status."""
    components = {}

    components['meta_router'] = {'initialized': meta_router is not None}
    components['brain_monitor'] = {'initialized': brain_monitor is not None}
    components['strategy_lib'] = {'initialized': strategy_lib is not None}
    components['live_monitor'] = {'initialized': live_monitor is not None}
    components['path_planner'] = {'initialized': path_planner is not None}
    components['llm_router'] = {'initialized': llm_router is not None}
    components['hierarchical_planner'] = {'initialized': hierarchical_planner is not None}
    components['frequency_controller'] = {'initialized': frequency_controller is not None}

    # Layer4 Router details
    components['layer4_router'] = {'initialized': layer4_router is not None}
    if layer4_router:
        try:
            components['layer4_router']['using_mamba'] = layer4_router.temporal_ctm.use_mamba
            components['layer4_router']['using_ollama'] = layer4_router.token_adapter._using_ollama
            stats = layer4_router.get_statistics()
            components['layer4_router']['tokens_processed'] = stats.get('token_adapter', {}).get('tokens_processed', 0)
        except (AttributeError, KeyError, TypeError):
            pass

    # Checkpoint Manager details
    components['checkpoint_manager'] = {'initialized': checkpoint_manager is not None}
    if checkpoint_manager:
        try:
            checkpoints = checkpoint_manager.list_checkpoints()
            components['checkpoint_manager']['checkpoint_count'] = len(checkpoints)
        except (AttributeError, KeyError, TypeError):
            pass

    return jsonify({'components': components, 'timestamp': datetime.now().isoformat()})


@app.route('/api/health/dependencies')
def health_dependencies():
    """Check external service dependencies."""
    dependencies = {}

    # Check Ollama
    ollama_status = {'name': 'Ollama', 'available': False}
    try:
        response = requests.get('http://localhost:11434/api/tags', timeout=2)
        if response.status_code == 200:
            ollama_status['available'] = True
            ollama_status['models'] = [m['name'] for m in response.json().get('models', [])]
    except (requests.RequestException, ValueError, KeyError):
        ollama_status['error'] = 'Connection failed'
    dependencies['ollama'] = ollama_status

    # Check Unified Brain Service
    unified_status = {'name': 'Unified Brain', 'available': False, 'url': UNIFIED_BRAIN_URL}
    try:
        response = requests.get(f'{UNIFIED_BRAIN_URL}/health', timeout=2)
        unified_status['available'] = response.status_code == 200
    except (requests.RequestException, ValueError):
        unified_status['error'] = 'Connection failed'
    dependencies['unified_brain'] = unified_status

    return jsonify({'dependencies': dependencies, 'timestamp': datetime.now().isoformat()})


@app.route('/api/health/readiness')
def health_readiness():
    """Kubernetes-style readiness probe."""
    critical = [meta_router is not None, brain_monitor is not None, hierarchical_planner is not None]
    if all(critical):
        return jsonify({'ready': True}), 200
    return jsonify({'ready': False, 'reason': 'Critical components not initialized'}), 503


@app.route('/api/health/liveness')
def health_liveness():
    """Kubernetes-style liveness probe."""
    return jsonify({'alive': True, 'timestamp': datetime.now().isoformat()}), 200


# ============================================================================
# PHASE 8B: ADVANCED LEARNING ENDPOINTS
# ============================================================================

# Global Phase 8B components (lazy loaded)
_causal_dag = None
_meta_learner = None
_federated_coordinator = None


def get_causal_dag():
    """Lazy load causal reasoning components."""
    global _causal_dag
    if _causal_dag is None:
        try:
            from core.causal_reasoning import CausalDAG
            _causal_dag = CausalDAG()
            # Add some demo nodes
            _causal_dag.add_variable("user_intent", description="User's underlying goal")
            _causal_dag.add_variable("context", description="Conversation context")
            _causal_dag.add_variable("response_quality", description="Quality of response")
            _causal_dag.add_edge("user_intent", "response_quality", strength=0.8)
            _causal_dag.add_edge("context", "response_quality", strength=0.6)
        except ImportError:
            _causal_dag = None
    return _causal_dag


def get_meta_learner():
    """Lazy load meta-learning components."""
    global _meta_learner
    if _meta_learner is None:
        try:
            from core.meta_learning import MetaLearner
            _meta_learner = MetaLearner()
        except ImportError:
            _meta_learner = None
    return _meta_learner


def get_federated_coordinator():
    """Lazy load federated learning components."""
    global _federated_coordinator
    if _federated_coordinator is None:
        try:
            from core.federated_learning import FederatedCoordinator
            _federated_coordinator = FederatedCoordinator(aggregation_strategy='fedavg')
        except ImportError:
            _federated_coordinator = None
    return _federated_coordinator


@app.route('/api/causal/status')
def causal_status():
    """Get causal reasoning status."""
    dag = get_causal_dag()
    if dag is None:
        return jsonify({
            'available': False,
            'error': 'Causal reasoning module not available'
        }), 503

    return jsonify({
        'available': True,
        'num_variables': len(dag.nodes),
        'num_edges': len(dag.edges),
        'variables': list(dag.nodes.keys()),
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/causal/graph')
def causal_graph():
    """Get causal DAG structure."""
    dag = get_causal_dag()
    if dag is None:
        return jsonify({'error': 'Causal reasoning not available'}), 503

    nodes = []
    for name, node in dag.nodes.items():
        nodes.append({
            'id': name,
            'description': node.description,
            'has_distribution': node.distribution is not None
        })

    edges = []
    for edge in dag.edges:
        edges.append({
            'source': edge.cause,
            'target': edge.effect,
            'strength': edge.strength,
            'type': edge.edge_type.value
        })

    return jsonify({
        'nodes': nodes,
        'edges': edges,
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/causal/analyze', methods=['POST'])
def causal_analyze():
    """Analyze causal relationships."""
    dag = get_causal_dag()
    if dag is None:
        return jsonify({'error': 'Causal reasoning not available'}), 503

    data = request.get_json() or {}
    symptoms = data.get('symptoms', {})

    try:
        from core.causal_reasoning import CausalInference, RootCauseAnalyzer
        inference = CausalInference(dag)
        analyzer = RootCauseAnalyzer(dag)

        # Analyze
        root_causes = analyzer.analyze_failure(symptoms)
        ranked = analyzer.rank_causes(root_causes)

        return jsonify({
            'root_causes': [
                {'variable': rc.variable, 'probability': prob, 'mechanism': rc.mechanism}
                for rc, prob in ranked[:5]
            ],
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/meta/status')
def meta_status():
    """Get meta-learning status."""
    learner = get_meta_learner()
    if learner is None:
        return jsonify({
            'available': False,
            'error': 'Meta-learning module not available'
        }), 503

    try:
        stats = learner.get_stats()
        return jsonify({
            'available': True,
            'total_adaptations': stats.get('total_adaptations', 0),
            'success_rate': stats.get('success_rate', 0),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            'available': True,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        })


@app.route('/api/meta/adapt', methods=['POST'])
def meta_adapt():
    """Perform meta-learning adaptation."""
    learner = get_meta_learner()
    if learner is None:
        return jsonify({'error': 'Meta-learning not available'}), 503

    data = request.get_json() or {}
    context = data.get('context', {})
    pattern = data.get('pattern', 'default')

    try:
        # Record adaptation
        learner.adapt(context, strategy=pattern)
        return jsonify({
            'success': True,
            'pattern': pattern,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/federated/status')
def federated_status():
    """Get federated learning status."""
    coordinator = get_federated_coordinator()
    if coordinator is None:
        return jsonify({
            'available': False,
            'error': 'Federated learning module not available'
        }), 503

    try:
        stats = coordinator.get_statistics()
        return jsonify({
            'available': True,
            'round_number': stats.get('round_number', 0),
            'num_nodes': stats.get('num_nodes', 0),
            'active_nodes': stats.get('active_nodes', 0),
            'aggregation_strategy': stats.get('aggregation_strategy', 'unknown'),
            'total_samples': stats.get('total_samples', 0),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            'available': True,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        })


@app.route('/api/federated/nodes')
def federated_nodes():
    """Get federated learning nodes."""
    coordinator = get_federated_coordinator()
    if coordinator is None:
        return jsonify({'error': 'Federated learning not available'}), 503

    try:
        nodes = []
        for node_id, node in coordinator.nodes.items():
            stats = node.get_statistics()
            nodes.append({
                'node_id': node_id,
                'is_active': stats.get('is_active', False),
                'total_rounds': stats.get('total_rounds', 0),
                'total_samples': stats.get('total_samples', 0),
                'avg_loss': stats.get('avg_loss', 0)
            })
        return jsonify({
            'nodes': nodes,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/federated/rounds')
def federated_rounds():
    """Get federated learning round history."""
    coordinator = get_federated_coordinator()
    if coordinator is None:
        return jsonify({'error': 'Federated learning not available'}), 503

    try:
        stats = coordinator.get_statistics()
        return jsonify({
            'round_number': stats.get('round_number', 0),
            'recent_rounds': stats.get('recent_rounds', []),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/advanced_learning/health')
def advanced_learning_health():
    """Health check for all Phase 8B components."""
    components = {
        'causal_reasoning': get_causal_dag() is not None,
        'meta_learning': get_meta_learner() is not None,
        'federated_learning': get_federated_coordinator() is not None
    }

    available_count = sum(1 for v in components.values() if v)

    return jsonify({
        'components': components,
        'available_count': available_count,
        'total_count': len(components),
        'all_available': all(components.values()),
        'timestamp': datetime.now().isoformat()
    })


# ============================================================================
# MOLTBOOK KNOWLEDGE SYSTEM API (Proxy to unified brain service)
# ============================================================================

@app.route('/api/moltbook/state')
def moltbook_state():
    """Get Moltbook system overview."""
    try:
        resp = requests.get(f'{UNIFIED_BRAIN_URL}/moltbook/state', timeout=3)
        if resp.ok:
            return jsonify(resp.json())
    except Exception:
        pass
    return jsonify({'enabled': False, 'timestamp': datetime.now().isoformat()})


@app.route('/api/moltbook/entries')
def moltbook_entries():
    """Get recent Moltbook entries."""
    try:
        top_k = request.args.get('top_k', 20)
        resp = requests.get(f'{UNIFIED_BRAIN_URL}/moltbook/entries?top_k={top_k}', timeout=3)
        if resp.ok:
            return jsonify(resp.json())
    except Exception:
        pass
    return jsonify({'entries': [], 'count': 0})


@app.route('/api/moltbook/search', methods=['POST'])
def moltbook_search():
    """Search Moltbook entries."""
    try:
        resp = requests.post(f'{UNIFIED_BRAIN_URL}/moltbook/search',
                             json=request.json, timeout=5)
        if resp.ok:
            return jsonify(resp.json())
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 503


@app.route('/api/moltbook/feed', methods=['POST'])
def moltbook_feed():
    """Feed knowledge into Moltbook."""
    try:
        resp = requests.post(f'{UNIFIED_BRAIN_URL}/moltbook/feed',
                             json=request.json, timeout=5)
        if resp.ok:
            return jsonify(resp.json())
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 503


@app.route('/api/moltbook/debug')
def moltbook_debug():
    """Get Moltbook debug stream."""
    try:
        n = request.args.get('n', 30)
        resp = requests.get(f'{UNIFIED_BRAIN_URL}/moltbook/debug?n={n}', timeout=3)
        if resp.ok:
            return jsonify(resp.json())
    except Exception:
        pass
    return jsonify({'enabled': False, 'entries': [], 'formatted': ''})


if __name__ == '__main__':
    print("="*80)
    print("BRAIN DASHBOARD SERVER")
    print("="*80)
    print()

    # Initialize brain components
    initialize_brain()

    print()
    print("="*80)
    print("Starting web server...")
    print("Dashboard URL: http://localhost:5004")
    print("="*80)
    print()

    # Run Flask app
    debug_mode = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    port = int(os.environ.get('DASHBOARD_PORT', 5004))
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
