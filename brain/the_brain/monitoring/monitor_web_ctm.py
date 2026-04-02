"""
ATM-R CTM Reasoning Monitor - Web Dashboard

Enhanced web monitoring dashboard specifically designed for
Continuous Thought Machine reasoning with clear mode names.

Shows:
- Reasoning mode allocation (not biological metaphors!)
- Thought stream timeline
- Convergence tracking
- Safety monitoring
"""

from flask import Flask, render_template, jsonify
from flask_cors import CORS
import numpy as np
from collections import deque
import threading
import time
from thalamo_pc_adaptive import ThalamoPC6Adaptive
from reasoning_modes import REASONING_MODES, get_display_name, get_icon, get_color

app = Flask(__name__)
CORS(app)

# Global state
class CTMMonitorState:
    def __init__(self):
        self.atmr = None
        self.monitor_data = {
            'gates': deque(maxlen=100),
            'reasoning_history': deque(maxlen=100),
            'confidence': deque(maxlen=100),
            'timestamps': deque(maxlen=100),
            'dominant': deque(maxlen=100),
            'thoughts': deque(maxlen=20),  # Last 20 thoughts
            'current': None,
            'stats': {},
            'modalities': [],
            'mode_info': {}  # Reasoning mode metadata
        }
        self.running = False

state = CTMMonitorState()


def update_monitoring(atmr_output, thought=None):
    """Update monitoring data with new ATM-R output."""
    gates = atmr_output['g']
    pe = atmr_output.get('pe', {})
    timestamp = time.time()

    # Store data
    state.monitor_data['gates'].append(gates.tolist())
    state.monitor_data['confidence'].append(float(np.max(gates)))
    state.monitor_data['timestamps'].append(timestamp)

    dominant_idx = np.argmax(gates)
    dominant_mode = state.monitor_data['modalities'][dominant_idx]
    state.monitor_data['dominant'].append(dominant_mode)

    # Store thought if provided
    if thought:
        state.monitor_data['thoughts'].append({
            'timestamp': timestamp,
            'mode': dominant_mode,
            'text': thought,
            'confidence': float(np.max(gates))
        })

    # Current state
    state.monitor_data['current'] = {
        'gates': gates.tolist(),
        'pe': {m: pe.get(m, 0.0) for m in state.monitor_data['modalities']},
        'confidence': float(np.max(gates)),
        'dominant': dominant_mode,
        'dominant_name': get_display_name(dominant_mode),
        'timestamp': timestamp
    }

    # Compute stats
    if len(state.monitor_data['gates']) > 1:
        avg_gates = np.mean(np.array(list(state.monitor_data['gates'])), axis=0)
        state.monitor_data['stats'] = {
            'avg_confidence': float(np.mean(list(state.monitor_data['confidence']))),
            'avg_gates': avg_gates.tolist(),
            'total_steps': len(state.monitor_data['gates']),
            'entropy': float(-np.sum((gates + 1e-10) * np.log2(gates + 1e-10)))
        }


# Simulated CTM reasoning
def simulate_ctm_reasoning():
    """Simulate CTM reasoning process."""
    atmr = ThalamoPC6Adaptive(seed=42)
    state.atmr = atmr
    state.monitor_data['modalities'] = atmr.modalities

    # Store mode info
    state.monitor_data['mode_info'] = {
        mod: {
            'display_name': get_display_name(mod),
            'icon': get_icon(mod),
            'color': get_color(mod)
        }
        for mod in atmr.modalities
    }

    state.running = True

    # Simulated reasoning buffers
    visual_buffer = np.random.randn(128) * 0.5
    verbal_buffer = np.random.randn(64) * 0.5
    spatial_buffer = np.random.randn(16) * 0.5

    step = 0
    while state.running:
        # Update buffers (simulate thinking)
        visual_buffer += np.random.randn(128) * 0.1
        visual_buffer = np.tanh(visual_buffer)

        verbal_buffer += np.random.randn(64) * 0.1
        verbal_buffer = np.tanh(verbal_buffer)

        spatial_buffer += np.random.randn(16) * 0.1
        spatial_buffer = np.tanh(spatial_buffer)

        # Prepare ATM-R input
        x_t = {
            'vision': visual_buffer[:128],
            'audio': verbal_buffer[:64],
            'touch': np.zeros(32),
            'taste': np.zeros(16),
            'vestibular': spatial_buffer[:16],
            'threat': np.zeros(8)
        }

        # Occasionally boost different modes
        if step % 15 == 0:
            x_t['vision'] *= 3.0
            thought = "Visualizing problem structure..."
        elif step % 15 == 5:
            x_t['audio'] *= 3.0
            thought = "Applying logical reasoning..."
        elif step % 15 == 10:
            x_t['vestibular'] *= 3.0
            thought = "Performing mental rotation..."
        else:
            thought = "Continuous thinking..."

        # Process
        out = atmr.step(x_t, adapt=True)

        # Generate thought based on dominant mode
        dominant_mode = atmr.modalities[np.argmax(out['g'])]
        mode_name = get_display_name(dominant_mode)
        thought = f"[{mode_name}] {thought}"

        # Update monitoring
        update_monitoring(out, thought)

        step += 1
        time.sleep(0.5)  # 2 updates per second


@app.route('/')
def index():
    """Serve main dashboard page."""
    return render_template('monitor_ctm.html')


@app.route('/api/current')
def api_current():
    """Get current state."""
    return jsonify(state.monitor_data['current'] or {})


@app.route('/api/history')
def api_history():
    """Get historical data."""
    return jsonify({
        'gates': list(state.monitor_data['gates']),
        'confidence': list(state.monitor_data['confidence']),
        'timestamps': list(state.monitor_data['timestamps']),
        'dominant': list(state.monitor_data['dominant']),
        'modalities': state.monitor_data['modalities'],
        'mode_info': state.monitor_data['mode_info']
    })


@app.route('/api/thoughts')
def api_thoughts():
    """Get recent thoughts."""
    return jsonify({'thoughts': list(state.monitor_data['thoughts'])})


@app.route('/api/stats')
def api_stats():
    """Get statistics."""
    return jsonify(state.monitor_data['stats'])


@app.route('/api/start')
def api_start():
    """Start simulation."""
    if not state.running:
        thread = threading.Thread(target=simulate_ctm_reasoning, daemon=True)
        thread.start()
        return jsonify({'status': 'started'})
    return jsonify({'status': 'already_running'})


@app.route('/api/stop')
def api_stop():
    """Stop simulation."""
    state.running = False
    return jsonify({'status': 'stopped'})


# HTML Template for CTM Dashboard
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>CTM-ATM-R Reasoning Monitor</title>
    <meta charset="utf-8">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #0a0e27;
            color: #eee;
            padding: 20px;
        }

        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        }

        .header h1 {
            font-size: 2em;
            margin-bottom: 10px;
        }

        .header p {
            opacity: 0.9;
            font-size: 1.1em;
        }

        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }

        .panel {
            background: #16213e;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        }

        .panel h2 {
            color: #667eea;
            margin-bottom: 20px;
            font-size: 1.3em;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
        }

        .mode-bar {
            margin-bottom: 15px;
        }

        .mode-label {
            display: flex;
            justify-content: space-between;
            margin-bottom: 5px;
            font-size: 1em;
        }

        .mode-icon {
            font-size: 1.2em;
            margin-right: 8px;
        }

        .mode-progress {
            background: #0f3460;
            height: 30px;
            border-radius: 5px;
            overflow: hidden;
            position: relative;
        }

        .mode-fill {
            height: 100%;
            transition: width 0.3s ease;
            display: flex;
            align-items: center;
            padding-left: 10px;
            color: white;
            font-weight: bold;
            font-size: 0.9em;
        }

        .mode-fill.dominant {
            animation: pulse 1s infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.8; }
        }

        .thought-stream {
            background: #0f3460;
            border-radius: 8px;
            padding: 15px;
            max-height: 400px;
            overflow-y: auto;
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
            line-height: 1.6;
        }

        .thought {
            padding: 8px;
            margin-bottom: 8px;
            border-left: 3px solid #667eea;
            background: rgba(255,255,255,0.05);
            border-radius: 4px;
        }

        .thought-time {
            color: #888;
            font-size: 0.85em;
        }

        .thought-mode {
            color: #f093fb;
            font-weight: bold;
        }

        .stat-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 15px;
        }

        .stat-box {
            background: #0f3460;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
        }

        .stat-value {
            font-size: 2em;
            color: #667eea;
            font-weight: bold;
        }

        .stat-label {
            font-size: 0.85em;
            color: #aaa;
            margin-top: 5px;
        }

        .controls {
            text-align: center;
            padding: 20px;
        }

        button {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 12px 30px;
            border-radius: 5px;
            font-size: 1em;
            cursor: pointer;
            margin: 0 10px;
            transition: transform 0.2s;
        }

        button:hover {
            transform: translateY(-2px);
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🧠 CTM-ATM-R Reasoning Monitor</h1>
        <p>Real-time visualization of Continuous Thought Machine with Adaptive Routing</p>
    </div>

    <div class="controls">
        <button onclick="startMonitoring()">▶ Start Reasoning</button>
        <button onclick="stopMonitoring()">⏸ Pause</button>
        <button onclick="location.reload()">🔄 Reset</button>
    </div>

    <div class="grid">
        <div class="panel">
            <h2>🎯 Reasoning Mode Allocation</h2>
            <div id="modes-container"></div>
        </div>

        <div class="panel">
            <h2>📈 Reasoning Stats</h2>
            <div class="stat-grid">
                <div class="stat-box">
                    <div class="stat-value" id="stat-confidence">-</div>
                    <div class="stat-label">Confidence</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value" id="stat-entropy">-</div>
                    <div class="stat-label">Diversity</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value" id="stat-dominant">-</div>
                    <div class="stat-label">Active Mode</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value" id="stat-steps">-</div>
                    <div class="stat-label">Reasoning Steps</div>
                </div>
            </div>
        </div>
    </div>

    <div class="panel">
        <h2>💭 Thought Stream</h2>
        <div class="thought-stream" id="thought-stream">
            <div class="thought">
                <div class="thought-time">Waiting for reasoning to start...</div>
            </div>
        </div>
    </div>

    <script>
        let updateInterval = null;

        function startMonitoring() {
            fetch('/api/start').then(r => r.json()).then(data => {
                console.log('Reasoning started:', data);
            });

            if (!updateInterval) {
                updateInterval = setInterval(updateDashboard, 500);
            }
        }

        function stopMonitoring() {
            fetch('/api/stop').then(r => r.json()).then(data => {
                console.log('Reasoning stopped:', data);
            });
        }

        async function updateDashboard() {
            try {
                const current = await fetch('/api/current').then(r => r.json());
                const history = await fetch('/api/history').then(r => r.json());
                const thoughts = await fetch('/api/thoughts').then(r => r.json());
                const stats = await fetch('/api/stats').then(r => r.json());

                if (!current.gates) return;

                updateModes(current.gates, current.dominant, history.modalities, history.mode_info);
                updateStats(current, stats);
                updateThoughts(thoughts.thoughts);

            } catch (error) {
                console.error('Update error:', error);
            }
        }

        function updateModes(gates, dominant, modalities, mode_info) {
            const container = document.getElementById('modes-container');
            container.innerHTML = '';

            gates.forEach((gate, i) => {
                const mod = modalities[i];
                const info = mode_info[mod] || {};
                const isDominant = mod === dominant;
                const displayName = info.display_name || mod;
                const icon = info.icon || '';
                const color = info.color || '#667eea';

                const div = document.createElement('div');
                div.className = 'mode-bar';
                div.innerHTML = `
                    <div class="mode-label">
                        <span><span class="mode-icon">${icon}</span>${displayName}</span>
                        <span>${(gate * 100).toFixed(1)}%</span>
                    </div>
                    <div class="mode-progress">
                        <div class="mode-fill ${isDominant ? 'dominant' : ''}"
                             style="width: ${gate * 100}%; background: linear-gradient(90deg, ${color} 0%, ${color}dd 100%);">
                            ${gate > 0.15 ? (isDominant ? '<<< ACTIVE' : '') : ''}
                        </div>
                    </div>
                `;
                container.appendChild(div);
            });
        }

        function updateStats(current, stats) {
            document.getElementById('stat-confidence').textContent =
                (current.confidence * 100).toFixed(0) + '%';
            document.getElementById('stat-entropy').textContent =
                stats.entropy ? stats.entropy.toFixed(2) + ' bits' : '-';
            document.getElementById('stat-dominant').textContent =
                current.dominant_name || current.dominant;
            document.getElementById('stat-steps').textContent = stats.total_steps || 0;
        }

        function updateThoughts(thoughts) {
            const container = document.getElementById('thought-stream');

            if (thoughts.length === 0) return;

            // Show last 10 thoughts
            const recentThoughts = thoughts.slice(-10).reverse();

            container.innerHTML = recentThoughts.map(t => {
                const time = new Date(t.timestamp * 1000).toLocaleTimeString();
                return `
                    <div class="thought">
                        <div class="thought-time">${time}</div>
                        <div class="thought-mode">${t.mode}</div>
                        <div>${t.text}</div>
                    </div>
                `;
            }).join('');
        }

        // Auto-start
        setTimeout(() => {
            startMonitoring();
        }, 1000);
    </script>
</body>
</html>
"""

# Create templates directory and save HTML
import os
os.makedirs('templates', exist_ok=True)
with open('templates/monitor_ctm.html', 'w', encoding='utf-8') as f:
    f.write(HTML_TEMPLATE)


if __name__ == '__main__':
    print("="*80)
    print("CTM-ATM-R Reasoning Monitor")
    print("="*80)
    print("\nStarting server...")
    print("\nOpen your browser and navigate to:")
    print("  -> http://localhost:5001")
    print("\nPress Ctrl+C to stop")
    print("="*80)

    app.run(debug=False, host='0.0.0.0', port=5001)
