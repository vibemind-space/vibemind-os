"""
Oscillator Dashboard Web Server

Flask server that exposes oscillator state as JSON API endpoints
and serves an interactive web dashboard with real-time Chart.js visualization.

Usage:
    python -m web.oscillator_dashboard_server

Dashboard URL: http://localhost:5005
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
import numpy as np
import json
from datetime import datetime
import threading
import time

from core.layer4_temporal_router import Layer4TemporalRouter

app = Flask(__name__,
            template_folder='templates',
            static_folder='static')
CORS(app)

# Global router instance
router = None
processing_thread = None
processing_active = False

# History for charts
oscillator_history = []
MAX_HISTORY = 100


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


def initialize_router():
    """Initialize the Layer4TemporalRouter."""
    global router

    print("Initializing Layer4TemporalRouter...")

    router = Layer4TemporalRouter(
        strict_security=True,
        timing_threshold=0.5,
        enable_deep_reasoning=False  # Disable for faster response
    )

    print(f"Router initialized!")
    print(f"  - Oscillator: {router.oscillator}")
    print(f"  - TokenAdapter: {router.token_adapter}")
    print(f"  - EventBridge: {router.event_bridge}")
    print(f"  - Using Mamba: {router.temporal_ctm.use_mamba}")
    print(f"  - Using Ollama: {router.token_adapter._using_ollama}")


def record_oscillator_state():
    """Record current oscillator state to history."""
    global oscillator_history

    if router is None:
        return

    try:
        osc = router.get_oscillator_state()
        sync = router.get_synchrony_vector()
        dominant = router.get_dominant_channel()
        stats = router.get_statistics()
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
        if len(oscillator_history) > MAX_HISTORY:
            oscillator_history = oscillator_history[-MAX_HISTORY:]

    except Exception as e:
        print(f"Error recording state: {e}")


# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.route('/')
def index():
    """Serve the main dashboard page."""
    return render_template('oscillator_dashboard.html')


@app.route('/api/oscillator/state')
def get_oscillator_state():
    """Get current oscillator state."""
    if router is None:
        return jsonify({'error': 'Router not initialized'}), 503

    try:
        osc = router.get_oscillator_state()
        sync = router.get_synchrony_vector()
        dominant = router.get_dominant_channel()

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


@app.route('/api/token/process', methods=['POST'])
def process_tokens():
    """Process tokens through the pipeline."""
    if router is None:
        return jsonify({'error': 'Router not initialized'}), 503

    data = request.get_json() or {}
    text = data.get('text', '')

    if not text:
        return jsonify({'error': 'Text required'}), 400

    try:
        # Process through EventBridge
        result = router.event_bridge.process_text(text)

        # Record state
        record_oscillator_state()

        # Get updated state
        osc = router.get_oscillator_state()
        dominant = router.get_dominant_channel()

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


@app.route('/api/token/stats')
def get_token_stats():
    """Get token processing statistics."""
    if router is None:
        return jsonify({'error': 'Router not initialized'}), 503

    try:
        stats = router.get_statistics()
        token_stats = stats.get('token_adapter', {})
        eb_stats = stats.get('event_bridge', {})

        return jsonify({
            'token_adapter': convert_numpy(token_stats),
            'event_bridge': convert_numpy(eb_stats),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/route', methods=['POST'])
def route_events():
    """Route events through the full pipeline."""
    if router is None:
        return jsonify({'error': 'Router not initialized'}), 503

    data = request.get_json() or {}
    events = data.get('events', [])
    task = data.get('task', 'Web Dashboard Test')

    if not events:
        return jsonify({'error': 'Events required'}), 400

    try:
        result = router.route(events, task_description=task)

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


@app.route('/api/router/stats')
def get_router_stats():
    """Get full router statistics."""
    if router is None:
        return jsonify({'error': 'Router not initialized'}), 503

    try:
        stats = router.get_statistics()
        return jsonify({
            'stats': convert_numpy(stats),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/router/state')
def get_router_state():
    """Get current router state summary."""
    if router is None:
        return jsonify({'error': 'Router not initialized'}), 503

    try:
        summary = router.get_current_state_summary()
        return jsonify({
            'state': convert_numpy(summary),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/reset', methods=['POST'])
def reset_router():
    """Reset router state."""
    global oscillator_history

    if router is None:
        return jsonify({'error': 'Router not initialized'}), 503

    try:
        router.reset()
        oscillator_history = []

        return jsonify({
            'status': 'reset',
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/health')
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'router_initialized': router is not None,
        'using_mamba': router.temporal_ctm.use_mamba if router else False,
        'using_ollama': router.token_adapter._using_ollama if router else False,
        'history_size': len(oscillator_history),
        'timestamp': datetime.now().isoformat()
    })


# ============================================================================
# LIVE PROCESSING
# ============================================================================

def background_processor():
    """Background thread for periodic state recording."""
    global processing_active

    while processing_active:
        record_oscillator_state()
        time.sleep(0.5)  # Record every 500ms


@app.route('/api/live/start', methods=['POST'])
def start_live():
    """Start live processing mode."""
    global processing_thread, processing_active

    if processing_active:
        return jsonify({'status': 'already_running'})

    processing_active = True
    processing_thread = threading.Thread(target=background_processor, daemon=True)
    processing_thread.start()

    return jsonify({
        'status': 'started',
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/live/stop', methods=['POST'])
def stop_live():
    """Stop live processing mode."""
    global processing_active

    processing_active = False

    return jsonify({
        'status': 'stopped',
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/live/status')
def live_status():
    """Get live processing status."""
    return jsonify({
        'active': processing_active,
        'timestamp': datetime.now().isoformat()
    })


# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    print("=" * 80)
    print("OSCILLATOR DASHBOARD SERVER")
    print("=" * 80)
    print()

    # Initialize router
    initialize_router()

    print()
    print("=" * 80)
    print("Starting web server...")
    print("Dashboard URL: http://localhost:5005")
    print("=" * 80)
    print()

    # Run Flask app
    debug_mode = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    port = int(os.environ.get('OSCILLATOR_PORT', 5005))
    app.run(host='0.0.0.0', port=port, debug=debug_mode, use_reloader=False)
