"""
REST API Server for Production Tahlamus System

Endpoints:
  POST /predict - Make a prediction
  POST /feedback - Submit feedback
  GET /stats - Get system statistics
  GET /matrices - List available matrices
  POST /save_matrix - Save current matrix
  POST /load_matrix - Load a specific matrix version
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from production.production_planner import ProductionPlanner
from production.brain_heartbeat import BrainHeartbeat, BrainHeartbeatConfig

app = Flask(__name__)
CORS(app)

# Global planner and heartbeat instances
planner = None
heartbeat = None


def initialize_planner():
    """Initialize the production planner and autonomous heartbeat"""
    global planner, heartbeat

    if planner is not None:
        return

    print("Initializing production planner...")

    session_log_dir = os.environ.get(
        'SESSION_LOG_DIR',
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'logs', 'sessions')
    )
    planner = ProductionPlanner(
        session_log_dir=session_log_dir,
        matrix_dir="production/trained_matrices",
        feedback_dir="production/feedback",
        enable_continuous_learning=True,
        learning_rate=0.005,
        embedding_type="hash"  # Use hash instead of neural to avoid JAX dependency
    )

    print("Production planner ready!")

    # Initialize autonomous heartbeat
    print("Starting autonomous brain heartbeat...")
    config = BrainHeartbeatConfig(
        interval_seconds=30.0,
        enable_dream_mode=True,
        dream_idle_threshold_seconds=300.0,  # 5 minutes
        enable_temporal_updates=True,
        enable_neuromodulation_decay=True,
        enable_meta_learning_checks=True,
        enable_health_monitoring=True
    )

    heartbeat = BrainHeartbeat(
        planner=planner,
        config=config,
        on_tick=lambda tick: print(f"[Heartbeat] Tick #{tick['tick_number']} - Actions: {tick['actions_taken']}"),
        on_dream=lambda dream: print(f"[Heartbeat] Dream mode activated: {dream['num_dreams']} dreams")
    )

    heartbeat.start()
    print("Autonomous heartbeat started! (30s interval)")


@app.route('/predict', methods=['POST'])
def predict():
    """
    Make a prediction for a task

    Request JSON:
    {
        "task": "Deploy with Docker immediately"
    }

    Response JSON:
    {
        "task": "...",
        "prediction": {
            "primary_action": "suggest",
            "primary_weight": 0.348,
            "primary_reasoning": "...",
            "alternatives": [...]
        },
        "brain_state": {...},
        "reasoning_chain": [...]
    }
    """
    try:
        data = request.get_json()

        if 'task' not in data:
            return jsonify({'error': 'Missing task field'}), 400

        task = data['task']

        # Make prediction
        result = planner.predict(task)

        # Mark prediction in heartbeat (resets idle timer)
        if heartbeat:
            heartbeat.mark_prediction()

        return jsonify(result), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/feedback', methods=['POST'])
def feedback():
    """
    Submit feedback for a prediction

    Request JSON:
    {
        "task": "Deploy with Docker immediately",
        "prediction": {...},  # From /predict response
        "actual_action": "suggest",  # Optional
        "success": true,
        "user_rating": 0.9,  # Optional, 0-1
        "execution_time_ms": 1500  # Optional
    }

    Response JSON:
    {
        "message": "Feedback received",
        "total_feedback": 42
    }
    """
    try:
        data = request.get_json()

        required_fields = ['task', 'prediction']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing {field} field'}), 400

        # Submit feedback
        planner.submit_feedback(
            task=data['task'],
            prediction=data['prediction'],
            actual_action=data.get('actual_action'),
            success=data.get('success', True),
            user_rating=data.get('user_rating'),
            execution_time_ms=data.get('execution_time_ms')
        )

        return jsonify({
            'message': 'Feedback received',
            'total_feedback': planner.total_feedback,
            'continuous_learning': planner.enable_continuous_learning
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/stats', methods=['GET'])
def stats():
    """
    Get system statistics

    Response JSON:
    {
        "total_predictions": 42,
        "total_feedback": 38,
        "current_matrix_version": "v20250115_trained",
        "recent_accuracy": 0.85,
        "recent_avg_confidence": 0.54
    }
    """
    try:
        stats = planner.get_statistics()
        return jsonify(stats), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/matrices', methods=['GET'])
def matrices():
    """
    List all available matrix versions

    Response JSON:
    {
        "matrices": [
            {
                "version": "v20250115_trained",
                "timestamp": "2025-01-15T12:00:00",
                "accuracy": 0.75,
                "num_predictions": 500,
                "avg_confidence": 0.54,
                "notes": "..."
            },
            ...
        ]
    }
    """
    try:
        versions = planner.list_available_matrices()
        return jsonify({'matrices': versions}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/save_matrix', methods=['POST'])
def save_matrix():
    """
    Save current routing matrix as new version

    Request JSON:
    {
        "version_name": "v_custom_name",  # Optional
        "notes": "Description of this version"
    }

    Response JSON:
    {
        "version": "v20250115_120000",
        "message": "Matrix saved successfully"
    }
    """
    try:
        data = request.get_json() or {}

        version = planner.save_matrix(
            version_name=data.get('version_name'),
            notes=data.get('notes', '')
        )

        return jsonify({
            'version': version,
            'message': 'Matrix saved successfully'
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/load_matrix', methods=['POST'])
def load_matrix():
    """
    Load a specific matrix version

    Request JSON:
    {
        "version": "v20250115_trained"
    }

    Response JSON:
    {
        "version": "v20250115_trained",
        "message": "Matrix loaded successfully"
    }
    """
    try:
        data = request.get_json()

        if 'version' not in data:
            return jsonify({'error': 'Missing version field'}), 400

        version = planner._load_matrix(data['version'])

        return jsonify({
            'version': version,
            'message': 'Matrix loaded successfully'
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/brain_state', methods=['GET'])
def brain_state():
    """
    Get complete brain cognitive state

    Response JSON:
    {
        "timestamp": "2025-10-16T14:30:00",
        "uptime_seconds": 3600,
        "state": "active",
        "neuromodulation": {...},
        "meta_learning": {...},
        "dream_state": {...},
        "temporal_memory": {...},
        "performance": {...},
        "health": {...}
    }
    """
    try:
        if not heartbeat:
            return jsonify({'error': 'Heartbeat not initialized'}), 503

        state = heartbeat.get_state()
        return jsonify(state), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/heartbeat', methods=['POST', 'GET'])
def manual_heartbeat():
    """
    Manually trigger a heartbeat tick (POST) or get heartbeat status (GET)

    POST Request JSON (optional):
    {
        "force_dream": true  # Force dream mode regardless of idle time
    }

    Response JSON:
    {
        "status": "completed",
        "timestamp": "2025-10-16T14:30:00",
        "tick_number": 42,
        "brain_state": {...}
    }
    """
    try:
        if not heartbeat:
            return jsonify({'error': 'Heartbeat not initialized'}), 503

        if request.method == 'GET':
            # Return heartbeat status
            return jsonify({
                'running': heartbeat.running,
                'tick_count': heartbeat.tick_count,
                'idle_time_seconds': heartbeat.idle_time_seconds,
                'interval_seconds': heartbeat.config.interval_seconds,
                'total_dreams': heartbeat.total_dreams
            }), 200

        # POST - Manual tick
        data = request.get_json() or {}
        force_dream = data.get('force_dream', False)

        # If force_dream, temporarily lower idle threshold
        original_threshold = None
        if force_dream:
            original_threshold = heartbeat.config.dream_idle_threshold_seconds
            heartbeat.config.dream_idle_threshold_seconds = 0.0

        # Trigger tick
        heartbeat.tick()

        # Restore threshold
        if original_threshold is not None:
            heartbeat.config.dream_idle_threshold_seconds = original_threshold

        # Get updated state
        state = heartbeat.get_state()

        return jsonify({
            'status': 'completed',
            'timestamp': state['timestamp'],
            'tick_number': heartbeat.tick_count,
            'brain_state': state
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/heartbeat/config', methods=['POST', 'GET'])
def heartbeat_config():
    """
    Get or update heartbeat configuration

    POST Request JSON:
    {
        "interval_seconds": 60,  # Optional
        "enable_dream_mode": true,  # Optional
        "dream_idle_threshold_seconds": 300  # Optional
    }

    Response JSON:
    {
        "message": "Configuration updated",
        "config": {
            "interval_seconds": 60,
            "enable_dream_mode": true,
            "dream_idle_threshold_seconds": 300,
            ...
        }
    }
    """
    try:
        if not heartbeat:
            return jsonify({'error': 'Heartbeat not initialized'}), 503

        if request.method == 'GET':
            # Return current config
            return jsonify({
                'interval_seconds': heartbeat.config.interval_seconds,
                'enable_dream_mode': heartbeat.config.enable_dream_mode,
                'dream_idle_threshold_seconds': heartbeat.config.dream_idle_threshold_seconds,
                'enable_temporal_updates': heartbeat.config.enable_temporal_updates,
                'enable_neuromodulation_decay': heartbeat.config.enable_neuromodulation_decay,
                'enable_meta_learning_checks': heartbeat.config.enable_meta_learning_checks,
                'enable_health_monitoring': heartbeat.config.enable_health_monitoring,
                'meta_learning_check_interval': heartbeat.config.meta_learning_check_interval
            }), 200

        # POST - Update config
        data = request.get_json() or {}

        # Update config
        if 'interval_seconds' in data:
            heartbeat.config.interval_seconds = float(data['interval_seconds'])

        if 'enable_dream_mode' in data:
            heartbeat.config.enable_dream_mode = bool(data['enable_dream_mode'])

        if 'dream_idle_threshold_seconds' in data:
            heartbeat.config.dream_idle_threshold_seconds = float(data['dream_idle_threshold_seconds'])

        if 'enable_temporal_updates' in data:
            heartbeat.config.enable_temporal_updates = bool(data['enable_temporal_updates'])

        if 'enable_neuromodulation_decay' in data:
            heartbeat.config.enable_neuromodulation_decay = bool(data['enable_neuromodulation_decay'])

        if 'enable_meta_learning_checks' in data:
            heartbeat.config.enable_meta_learning_checks = bool(data['enable_meta_learning_checks'])

        if 'enable_health_monitoring' in data:
            heartbeat.config.enable_health_monitoring = bool(data['enable_health_monitoring'])

        return jsonify({
            'message': 'Configuration updated',
            'config': {
                'interval_seconds': heartbeat.config.interval_seconds,
                'enable_dream_mode': heartbeat.config.enable_dream_mode,
                'dream_idle_threshold_seconds': heartbeat.config.dream_idle_threshold_seconds,
                'enable_temporal_updates': heartbeat.config.enable_temporal_updates,
                'enable_neuromodulation_decay': heartbeat.config.enable_neuromodulation_decay,
                'enable_meta_learning_checks': heartbeat.config.enable_meta_learning_checks,
                'enable_health_monitoring': heartbeat.config.enable_health_monitoring
            }
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'planner_initialized': planner is not None,
        'heartbeat_running': heartbeat is not None and heartbeat.running
    }), 200


@app.route('/', methods=['GET'])
def index():
    """Landing page with API documentation"""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Tahlamus Production API</title>
        <style>
            body {
                font-family: 'Segoe UI', Arial, sans-serif;
                max-width: 1200px;
                margin: 50px auto;
                padding: 20px;
                background: #f5f5f5;
            }
            .header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 30px;
                border-radius: 10px;
                margin-bottom: 30px;
            }
            .header h1 { margin: 0 0 10px 0; }
            .header p { margin: 5px 0; opacity: 0.9; }
            .section {
                background: white;
                padding: 25px;
                border-radius: 10px;
                margin-bottom: 20px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            .endpoint {
                background: #f8f9fa;
                padding: 15px;
                margin: 15px 0;
                border-left: 4px solid #667eea;
                border-radius: 5px;
            }
            .method {
                display: inline-block;
                padding: 4px 8px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 12px;
                margin-right: 10px;
            }
            .post { background: #28a745; color: white; }
            .get { background: #17a2b8; color: white; }
            code {
                background: #e9ecef;
                padding: 2px 6px;
                border-radius: 3px;
                font-family: 'Courier New', monospace;
            }
            pre {
                background: #2d2d2d;
                color: #f8f8f2;
                padding: 15px;
                border-radius: 5px;
                overflow-x: auto;
            }
            .stats {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 15px;
                margin-top: 20px;
            }
            .stat-card {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 20px;
                border-radius: 8px;
                text-align: center;
            }
            .stat-value { font-size: 32px; font-weight: bold; margin: 10px 0; }
            .stat-label { font-size: 14px; opacity: 0.9; }
            .test-button {
                background: #667eea;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                cursor: pointer;
                font-size: 14px;
                margin: 5px;
            }
            .test-button:hover { background: #764ba2; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🧠 Tahlamus Production API</h1>
            <p>Brain-Inspired Cognitive Routing System</p>
            <p>Multi-Target Decision Making with Continuous Learning</p>
        </div>

        <div class="section">
            <h2>System Status</h2>
            <div class="stats" id="stats-container">
                <div class="stat-card">
                    <div class="stat-label">Status</div>
                    <div class="stat-value">✅</div>
                    <div class="stat-label">Operational</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Learning</div>
                    <div class="stat-value" id="learning-status">ON</div>
                    <div class="stat-label">Continuous</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Predictions</div>
                    <div class="stat-value" id="total-predictions">-</div>
                    <div class="stat-label">Total</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Feedback</div>
                    <div class="stat-value" id="total-feedback">-</div>
                    <div class="stat-label">Received</div>
                </div>
            </div>
            <button class="test-button" onclick="loadStats()">Refresh Stats</button>
        </div>

        <div class="section">
            <h2>API Endpoints</h2>

            <div class="endpoint">
                <span class="method post">POST</span>
                <strong>/predict</strong> - Make a prediction
                <p>Get multi-target decision with reasoning chain</p>
                <pre>curl -X POST http://localhost:5001/predict \\
  -H "Content-Type: application/json" \\
  -d '{"task": "Deploy with Docker urgently"}'</pre>
            </div>

            <div class="endpoint">
                <span class="method post">POST</span>
                <strong>/feedback</strong> - Submit feedback (triggers learning!)
                <p>Provide feedback to improve predictions</p>
                <pre>curl -X POST http://localhost:5001/feedback \\
  -H "Content-Type: application/json" \\
  -d '{"task": "...", "prediction": {...}, "success": true, "user_rating": 0.9}'</pre>
            </div>

            <div class="endpoint">
                <span class="method get">GET</span>
                <strong>/stats</strong> - Get system statistics
                <p>View performance metrics and learning status</p>
                <pre>curl http://localhost:5001/stats</pre>
            </div>

            <div class="endpoint">
                <span class="method get">GET</span>
                <strong>/matrices</strong> - List matrix versions
                <p>View all available trained matrices</p>
                <pre>curl http://localhost:5001/matrices</pre>
            </div>

            <div class="endpoint">
                <span class="method post">POST</span>
                <strong>/save_matrix</strong> - Save current matrix
                <p>Create a new version of the routing matrix</p>
                <pre>curl -X POST http://localhost:5001/save_matrix \\
  -H "Content-Type: application/json" \\
  -d '{"version_name": "v_custom", "notes": "My version"}'</pre>
            </div>

            <div class="endpoint">
                <span class="method post">POST</span>
                <strong>/load_matrix</strong> - Load specific version
                <p>Switch to a different matrix version</p>
                <pre>curl -X POST http://localhost:5001/load_matrix \\
  -H "Content-Type: application/json" \\
  -d '{"version": "v20250115_trained"}'</pre>
            </div>

            <div class="endpoint">
                <span class="method get">GET</span>
                <strong>/health</strong> - Health check
                <p>Check if API is running</p>
                <pre>curl http://localhost:5001/health</pre>
            </div>
        </div>

        <div class="section">
            <h2>Quick Test</h2>
            <button class="test-button" onclick="testPredict()">Test Prediction</button>
            <button class="test-button" onclick="testHealth()">Test Health</button>
            <div id="test-result" style="margin-top: 20px;"></div>
        </div>

        <div class="section">
            <h2>What Makes This Special?</h2>
            <ul>
                <li><strong>Multi-Target Decisions:</strong> Not single predictions, but weighted distributions (e.g., "45% suggest, 30% retry, 18% terminate")</li>
                <li><strong>Brain-Inspired:</strong> 10 modalities (vision, threat, error, success, etc.) with competitive gating</li>
                <li><strong>Continuous Learning:</strong> Improves from every feedback - updates routing matrix in real-time</li>
                <li><strong>Explainable:</strong> Full 10-step reasoning chains showing how decisions are made</li>
                <li><strong>Versioned:</strong> Save/load different matrix versions, A/B testing ready</li>
            </ul>
        </div>

        <div class="section">
            <h2>Documentation</h2>
            <p>For complete documentation, see:</p>
            <ul>
                <li><code>production/PRODUCTION_GUIDE.md</code> - Complete usage guide</li>
                <li><code>PRODUCTION_SYSTEM_COMPLETE.md</code> - System architecture</li>
                <li><code>FINAL_STATUS.md</code> - Status report</li>
            </ul>
        </div>

        <script>
            async function loadStats() {
                try {
                    const response = await fetch('/stats');
                    const data = await response.json();
                    document.getElementById('total-predictions').textContent = data.total_predictions;
                    document.getElementById('total-feedback').textContent = data.total_feedback;
                    document.getElementById('learning-status').textContent = data.continuous_learning_enabled ? 'ON' : 'OFF';
                } catch (error) {
                    console.error('Error loading stats:', error);
                }
            }

            async function testHealth() {
                const resultDiv = document.getElementById('test-result');
                try {
                    const response = await fetch('/health');
                    const data = await response.json();
                    resultDiv.innerHTML = '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
                } catch (error) {
                    resultDiv.innerHTML = '<p style="color: red;">Error: ' + error + '</p>';
                }
            }

            async function testPredict() {
                const resultDiv = document.getElementById('test-result');
                resultDiv.innerHTML = '<p>Making prediction...</p>';
                try {
                    const response = await fetch('/predict', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({task: 'Deploy with Docker urgently'})
                    });
                    const data = await response.json();
                    resultDiv.innerHTML = '<strong>Prediction Result:</strong><pre>' + JSON.stringify(data, null, 2) + '</pre>';
                } catch (error) {
                    resultDiv.innerHTML = '<p style="color: red;">Error: ' + error + '</p>';
                }
            }

            // Load stats on page load
            loadStats();
        </script>
    </body>
    </html>
    """
    return html


if __name__ == '__main__':
    # Initialize planner on startup
    initialize_planner()

    # Run server
    print()
    print("=" * 70)
    print("TAHLAMUS PRODUCTION API SERVER")
    print("=" * 70)
    print()
    print("API Endpoints:")
    print("  POST   /predict        - Make a prediction")
    print("  POST   /feedback       - Submit feedback")
    print("  GET    /stats          - Get statistics")
    print("  GET    /matrices       - List matrix versions")
    print("  POST   /save_matrix    - Save current matrix")
    print("  POST   /load_matrix    - Load specific matrix")
    print("  GET    /brain_state    - Get complete brain cognitive state")
    print("  GET    /heartbeat      - Get heartbeat status")
    print("  POST   /heartbeat      - Trigger manual heartbeat")
    print("  GET    /heartbeat/config - Get heartbeat configuration")
    print("  POST   /heartbeat/config - Update heartbeat configuration")
    print("  GET    /health         - Health check")
    print()
    print("[AUTONOMOUS BRAIN] Active - 30s heartbeat running")
    print()
    print("Server running on http://localhost:5001")
    print("=" * 70)
    print()

    app.run(host='0.0.0.0', port=5001, debug=False)
