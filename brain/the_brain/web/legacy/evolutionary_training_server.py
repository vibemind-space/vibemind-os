"""
Evolutionary Training Dashboard Server

Serves real-time visual dashboard for monitoring evolutionary training.
Shows agent positions, communication, metrics, and generation progress.

Usage:
    python web/evolutionary_training_server.py

Then open: http://localhost:5004
"""

from flask import Flask, render_template, jsonify, send_from_directory
from flask_cors import CORS
import threading
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from collections import deque
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s:%(name)s:%(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Global state for monitoring
class TrainingMonitor:
    """Singleton for tracking training state"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # Agent positions
        self.positions = {
            'beginning': (1, 1),
            'mid': (3, 4),
            'end': (6, 6),
            'paths': []  # All agent paths combined
        }

        # Metrics
        self.metrics = {
            'generation': 0,
            'episode': 0,
            'connections': 0,
            'path_quality': 0.0,
            'success_rate': 0.0,
            'difficulty': 1.0,
            'conv_penalty': -0.1,
            'total_reward': 0,
            'connected': False,
            'reproduction': False,
            'extinct': False,
            'extinct_generations': []
        }

        # Communication log
        self.comm_log = deque(maxlen=100)  # Keep last 100 messages
        self.last_message_index = 0

        # Lock for thread safety
        self.lock = threading.Lock()

        self._initialized = True

        logger.info("[TrainingMonitor] Initialized")

    def update_positions(self, beginning=None, mid=None, end=None, paths=None):
        """Update agent positions"""
        with self.lock:
            if beginning is not None:
                self.positions['beginning'] = beginning
            if mid is not None:
                self.positions['mid'] = mid
            if end is not None:
                self.positions['end'] = end
            if paths is not None:
                self.positions['paths'] = paths

    def update_metrics(self, **kwargs):
        """Update metrics"""
        with self.lock:
            self.metrics.update(kwargs)

    def add_message(self, agent: str, message: str):
        """Add communication message"""
        with self.lock:
            timestamp = datetime.now().strftime('%H:%M:%S')
            self.comm_log.append({
                'agent': agent,
                'message': message,
                'timestamp': timestamp
            })

    def get_state(self) -> Dict:
        """Get current training state (thread-safe)"""
        with self.lock:
            return {
                'positions': self.positions.copy(),
                'metrics': self.metrics.copy(),
                'new_messages': list(self.comm_log)[self.last_message_index:]
            }

    def mark_messages_read(self):
        """Mark messages as read"""
        with self.lock:
            self.last_message_index = len(self.comm_log)

    def reset(self):
        """Reset for new generation"""
        with self.lock:
            self.positions['paths'] = []
            self.metrics['connected'] = False
            self.metrics['reproduction'] = False


# Global monitor instance
monitor = TrainingMonitor()


@app.route('/')
def index():
    """Serve dashboard HTML"""
    html_path = Path(__file__).parent / 'evolutionary_training_dashboard.html'
    return send_from_directory(html_path.parent, html_path.name)


@app.route('/api/training_status')
def training_status():
    """Get current training status"""
    state = monitor.get_state()
    monitor.mark_messages_read()  # Mark messages as read
    return jsonify(state)


@app.route('/api/update_positions', methods=['POST'])
def update_positions():
    """Update agent positions (called from training script)"""
    from flask import request
    data = request.json

    monitor.update_positions(
        beginning=data.get('beginning'),
        mid=data.get('mid'),
        end=data.get('end'),
        paths=data.get('paths')
    )

    return jsonify({'status': 'ok'})


@app.route('/api/update_metrics', methods=['POST'])
def update_metrics():
    """Update training metrics (called from training script)"""
    from flask import request
    data = request.json

    monitor.update_metrics(**data)

    return jsonify({'status': 'ok'})


@app.route('/api/add_message', methods=['POST'])
def add_message():
    """Add communication message (called from training script)"""
    from flask import request
    data = request.json

    monitor.add_message(
        agent=data.get('agent', 'system'),
        message=data.get('message', '')
    )

    return jsonify({'status': 'ok'})


@app.route('/api/reset')
def reset():
    """Reset monitor for new generation"""
    monitor.reset()
    return jsonify({'status': 'ok'})


def run_server(host='localhost', port=5004):
    """Run Flask server"""
    logger.info("=" * 80)
    logger.info("[EvolutionaryTrainingServer] Starting")
    logger.info("=" * 80)
    logger.info(f"  Dashboard: http://{host}:{port}")
    logger.info(f"  API endpoints:")
    logger.info(f"    GET  /api/training_status")
    logger.info(f"    POST /api/update_positions")
    logger.info(f"    POST /api/update_metrics")
    logger.info(f"    POST /api/add_message")
    logger.info(f"    GET  /api/reset")
    logger.info("=" * 80)

    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    run_server()
