"""
Klotski Dashboard Server

Flask REST API server for the NeuroSymbolic Klotski Evolution dashboard.

Provides real-time state updates for:
- 3 agents (Beginning, Mid, End)
- Klotski puzzle blocks (4x5 grid, 10 brain-module blocks)
- Neural module activations (VIS, AUD, SOM, LAN, DLPFC, OFC, ACC, INS, MTL, DMN)
- Heart/Brain dual system (70%/30% split)
- Generation timeline
- Connection and reproduction events

Usage:
    python web/klotski_dashboard_server.py

    # In another terminal, run evolutionary training
    python -m demos.run_evolutionary_training --generations 3 --episodes 20 --neurosymbolic-mode

    # Open browser
    http://localhost:5004
"""

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
import os
import logging
from threading import Lock
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Thread-safe state management
state_lock = Lock()
dashboard_state = {
    'generation': 0,
    'episodes': 0,
    'success_rate': 0.0,
    'connections': 0,
    'extinctions': 0,
    'agents': {
        'beginning': {
            'status': 'solving',  # 'solving', 'solved', 'failed'
            'steps': 0,
            'moves': 0,
            'distance': float('inf'),
            'conv_cost': 0,
            'blocks': [],  # [{'id': 'G', 'x': 1, 'y': 0, 'w': 2, 'h': 2}, ...]
            'modules': {  # Neural module activations
                'VIS': 0.0, 'AUD': 0.0, 'SOM': 0.0, 'LAN': 0.0, 'DLPFC': 0.0,
                'OFC': 0.0, 'ACC': 0.0, 'INS': 0.0, 'MTL': 0.0, 'DMN': 0.0
            },
            'heart': 0.7,  # Heart confidence
            'brain': 0.3,  # Brain confidence
            'action': None  # Last action: {block_id, direction, from_pos, to_pos}
        },
        'mid': {
            'status': 'solving',
            'steps': 0,
            'moves': 0,
            'distance': float('inf'),
            'conv_cost': 0,
            'blocks': [],
            'modules': {
                'VIS': 0.0, 'AUD': 0.0, 'SOM': 0.0, 'LAN': 0.0, 'DLPFC': 0.0,
                'OFC': 0.0, 'ACC': 0.0, 'INS': 0.0, 'MTL': 0.0, 'DMN': 0.0
            },
            'heart': 0.7,
            'brain': 0.3,
            'action': None  # Last action: {block_id, direction, from_pos, to_pos}
        },
        'end': {
            'status': 'solving',
            'steps': 0,
            'moves': 0,
            'distance': float('inf'),
            'conv_cost': 0,
            'blocks': [],
            'modules': {
                'VIS': 0.0, 'AUD': 0.0, 'SOM': 0.0, 'LAN': 0.0, 'DLPFC': 0.0,
                'OFC': 0.0, 'ACC': 0.0, 'INS': 0.0, 'MTL': 0.0, 'DMN': 0.0
            },
            'heart': 0.7,
            'brain': 0.3,
            'action': None  # Last action: {block_id, direction, from_pos, to_pos}
        }
    },
    'connection_shown': False
}


# Routes
@app.route('/')
def index():
    """Serve dashboard HTML."""
    web_dir = Path(__file__).parent
    return send_from_directory(web_dir, 'klotski_dashboard.html')


@app.route('/api/training_status', methods=['GET'])
def get_training_status():
    """
    Get current training status for dashboard.

    Returns:
        JSON with generation, agents, modules, etc.
    """
    with state_lock:
        # Deep copy to avoid race conditions
        import copy
        import math
        state_copy = copy.deepcopy(dashboard_state)

        # Sanitize Infinity/NaN values for JSON serialization
        for agent_name in state_copy['agents']:
            agent = state_copy['agents'][agent_name]
            if 'distance' in agent:
                if math.isinf(agent['distance']) or math.isnan(agent['distance']):
                    agent['distance'] = 999  # Use large number instead of Infinity

    return jsonify(state_copy)


@app.route('/api/update_state', methods=['POST'])
def update_state():
    """
    Update dashboard state (called by training system).

    Expected JSON:
    {
        'generation': 1,
        'episodes': 42,
        'agents': {
            'beginning': {'status': 'solved', 'steps': 120, ...},
            'mid': {...},
            'end': {...}
        }
    }
    """
    from flask import request

    data = request.get_json()

    with state_lock:
        # Update generation info
        if 'generation' in data:
            dashboard_state['generation'] = data['generation']
        if 'episodes' in data:
            dashboard_state['episodes'] = data['episodes']
        if 'success_rate' in data:
            dashboard_state['success_rate'] = data['success_rate']
        if 'connections' in data:
            dashboard_state['connections'] = data['connections']
        if 'extinctions' in data:
            dashboard_state['extinctions'] = data['extinctions']

        # Update agents
        if 'agents' in data:
            for agent_name, agent_data in data['agents'].items():
                if agent_name in dashboard_state['agents']:
                    dashboard_state['agents'][agent_name].update(agent_data)

        # Reset connection_shown if new generation
        if 'reset_connection' in data and data['reset_connection']:
            dashboard_state['connection_shown'] = False

    return jsonify({'success': True})


@app.route('/api/update_agent', methods=['POST'])
def update_agent():
    """
    Update single agent state.

    Expected JSON:
    {
        'agent': 'beginning',
        'status': 'solving',
        'steps': 45,
        'modules': {'VIS': 0.8, 'AUD': 0.6, ...},
        'blocks': [{'id': 'G', 'x': 1, 'y': 0, 'w': 2, 'h': 2}, ...]
    }
    """
    from flask import request

    data = request.get_json()
    agent_name = data.get('agent')

    if agent_name not in dashboard_state['agents']:
        return jsonify({'success': False, 'error': 'Invalid agent name'}), 400

    with state_lock:
        agent = dashboard_state['agents'][agent_name]

        # Update fields
        if 'status' in data:
            agent['status'] = data['status']
        if 'steps' in data:
            agent['steps'] = data['steps']
        if 'moves' in data:
            agent['moves'] = data['moves']
        if 'distance' in data:
            agent['distance'] = data['distance']
        if 'conv_cost' in data:
            agent['conv_cost'] = data['conv_cost']
        if 'blocks' in data:
            agent['blocks'] = data['blocks']
        if 'modules' in data:
            agent['modules'].update(data['modules'])
        if 'heart' in data:
            agent['heart'] = data['heart']
        if 'brain' in data:
            agent['brain'] = data['brain']
        if 'action' in data:
            agent['action'] = data['action']  # Store action info for animation

    return jsonify({'success': True})


@app.route('/api/reset', methods=['POST'])
def reset_dashboard():
    """Reset dashboard to initial state."""
    with state_lock:
        dashboard_state['generation'] = 0
        dashboard_state['episodes'] = 0
        dashboard_state['success_rate'] = 0.0
        dashboard_state['connections'] = 0
        dashboard_state['extinctions'] = 0
        dashboard_state['connection_shown'] = False

        for agent_name in dashboard_state['agents']:
            agent = dashboard_state['agents'][agent_name]
            agent['status'] = 'solving'
            agent['steps'] = 0
            agent['moves'] = 0
            agent['distance'] = float('inf')
            agent['conv_cost'] = 0
            agent['blocks'] = []
            agent['modules'] = {
                'VIS': 0.0, 'AUD': 0.0, 'SOM': 0.0, 'LAN': 0.0, 'DLPFC': 0.0,
                'OFC': 0.0, 'ACC': 0.0, 'INS': 0.0, 'MTL': 0.0, 'DMN': 0.0
            }
            agent['heart'] = 0.7
            agent['brain'] = 0.3

    logger.info("[Dashboard] Reset to initial state")
    return jsonify({'success': True})


@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'service': 'klotski_dashboard_server',
        'version': '1.0.0',
        'generation': dashboard_state['generation'],
        'agents_status': {
            agent: dashboard_state['agents'][agent]['status']
            for agent in dashboard_state['agents']
        }
    })


# Client helper class
class KlotskiDashboardClient:
    """
    Python client for updating Klotski dashboard from training system.

    Usage:
        from web.klotski_dashboard_server import KlotskiDashboardClient

        client = KlotskiDashboardClient()

        # Update generation
        client.update_generation(generation=2, episodes=150, success_rate=0.75)

        # Update agent
        client.update_agent(
            agent='beginning',
            status='solved',
            steps=120,
            modules={'VIS': 0.8, 'DLPFC': 0.9, ...},
            blocks=[{'id': 'G', 'x': 1, 'y': 3, 'w': 2, 'h': 2}, ...]
        )

        # Trigger connection
        client.trigger_connection(quality=0.95, reward=9025)
    """

    def __init__(self, base_url: str = 'http://localhost:5004'):
        """Initialize client."""
        self.base_url = base_url
        self.session = None

    def _get_session(self):
        """Get or create requests session."""
        if self.session is None:
            try:
                import requests
                self.session = requests.Session()
            except ImportError:
                logger.warning("[DashboardClient] requests library not available")
                self.session = False
        return self.session

    def update_generation(self, generation: int, episodes: int, success_rate: float,
                         connections: int = None, extinctions: int = None):
        """Update generation-level statistics."""
        session = self._get_session()
        if not session:
            return

        data = {
            'generation': generation,
            'episodes': episodes,
            'success_rate': success_rate
        }
        if connections is not None:
            data['connections'] = connections
        if extinctions is not None:
            data['extinctions'] = extinctions

        try:
            response = session.post(f"{self.base_url}/api/update_state", json=data, timeout=1)
            if response.status_code == 200:
                logger.debug(f"[DashboardClient] Updated generation: {generation}")
        except Exception as e:
            logger.debug(f"[DashboardClient] Failed to update generation: {e}")

    def _sanitize_float(self, value):
        """Convert Infinity/NaN to None for JSON serialization."""
        import math
        if value is None:
            return None
        if math.isinf(value) or math.isnan(value):
            return None
        return value

    def update_agent(self, agent: str, status: str = None, steps: int = None,
                    moves: int = None, distance: float = None, conv_cost: float = None,
                    blocks: list = None, modules: dict = None, heart: float = None,
                    brain: float = None, action: dict = None):
        """Update single agent state."""
        session = self._get_session()
        if not session:
            return

        data = {'agent': agent}
        if status is not None:
            data['status'] = status
        if steps is not None:
            data['steps'] = steps
        if moves is not None:
            data['moves'] = moves
        if distance is not None:
            data['distance'] = self._sanitize_float(distance)
        if conv_cost is not None:
            data['conv_cost'] = self._sanitize_float(conv_cost)
        if blocks is not None:
            data['blocks'] = blocks
        if modules is not None:
            data['modules'] = modules
        if heart is not None:
            data['heart'] = self._sanitize_float(heart)
        if brain is not None:
            data['brain'] = self._sanitize_float(brain)
        if action is not None:
            data['action'] = action  # Include action for animation

        try:
            response = session.post(f"{self.base_url}/api/update_agent", json=data, timeout=1)
            if response.status_code == 200:
                logger.debug(f"[DashboardClient] Updated agent {agent}")
        except Exception as e:
            logger.debug(f"[DashboardClient] Failed to update agent: {e}")

    def trigger_connection(self, quality: float, reward: float):
        """Trigger connection event (all 3 solved)."""
        session = self._get_session()
        if not session:
            return

        data = {
            'reset_connection': False,  # Don't reset, just allow showing
            'quality': quality,
            'reward': reward
        }

        try:
            response = session.post(f"{self.base_url}/api/update_state", json=data, timeout=1)
            if response.status_code == 200:
                logger.info(f"[DashboardClient] Connection triggered! Quality={quality:.2f}, Reward={reward:.0f}")
        except Exception as e:
            logger.debug(f"[DashboardClient] Failed to trigger connection: {e}")

    def reset(self):
        """Reset dashboard to initial state."""
        session = self._get_session()
        if not session:
            return

        try:
            response = session.post(f"{self.base_url}/api/reset", timeout=1)
            if response.status_code == 200:
                logger.info("[DashboardClient] Dashboard reset")
        except Exception as e:
            logger.debug(f"[DashboardClient] Failed to reset: {e}")

    def health_check(self) -> bool:
        """Check if dashboard server is healthy."""
        session = self._get_session()
        if not session:
            return False

        try:
            response = session.get(f"{self.base_url}/api/health", timeout=1)
            return response.status_code == 200
        except Exception:
            return False


def main():
    """Run dashboard server."""
    logger.info("=" * 80)
    logger.info("NeuroSymbolic Klotski Evolution Dashboard Server")
    logger.info("=" * 80)
    logger.info("Starting server on http://localhost:5004")
    logger.info("Endpoints:")
    logger.info("  GET  /                     - Dashboard HTML")
    logger.info("  GET  /api/training_status  - Get current state (JSON)")
    logger.info("  POST /api/update_state     - Update generation/agents")
    logger.info("  POST /api/update_agent     - Update single agent")
    logger.info("  POST /api/reset            - Reset to initial state")
    logger.info("  GET  /api/health           - Health check")
    logger.info("=" * 80)
    logger.info("")
    logger.info("Open browser: http://localhost:5004")
    logger.info("")

    # Run Flask app
    app.run(host='0.0.0.0', port=5004, debug=False, threaded=True)


if __name__ == '__main__':
    main()
