"""
ATM-R Web-Based Monitoring Dashboard

Real-time web interface showing:
- Live gate weight visualization
- Historical trends
- Agent activity heatmap
- Health metrics

Usage:
    python monitor_web.py

Then open: http://localhost:5000
"""

from flask import Flask, render_template, jsonify
from flask_cors import CORS
import numpy as np
from collections import deque
import threading
import time
from thalamo_pc_adaptive import ThalamoPC6Adaptive

app = Flask(__name__)
CORS(app)

# Global state
class MonitorState:
    def __init__(self):
        self.atmr = None
        self.monitor_data = {
            'gates': deque(maxlen=100),
            'pe': deque(maxlen=100),
            'confidence': deque(maxlen=100),
            'timestamps': deque(maxlen=100),
            'dominant': deque(maxlen=100),
            'current': None,
            'stats': {},
            'modalities': []
        }
        self.running = False

state = MonitorState()


def update_monitoring(atmr_output):
    """Update monitoring data with new ATM-R output."""
    gates = atmr_output['g']
    pe = atmr_output.get('pe', {})
    timestamp = time.time()

    # Store data
    state.monitor_data['gates'].append(gates.tolist())
    state.monitor_data['pe'].append([pe.get(m, 0.0) for m in state.monitor_data['modalities']])
    state.monitor_data['confidence'].append(float(np.max(gates)))
    state.monitor_data['timestamps'].append(timestamp)
    state.monitor_data['dominant'].append(state.monitor_data['modalities'][np.argmax(gates)])

    # Current state
    state.monitor_data['current'] = {
        'gates': gates.tolist(),
        'pe': {m: pe.get(m, 0.0) for m in state.monitor_data['modalities']},
        'confidence': float(np.max(gates)),
        'dominant': state.monitor_data['modalities'][np.argmax(gates)],
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


# Simulated data generator (for demo)
def simulate_data():
    """Simulate ATM-R processing for demo purposes."""
    atmr = ThalamoPC6Adaptive(seed=42)
    state.atmr = atmr
    state.monitor_data['modalities'] = atmr.modalities
    state.running = True

    step = 0
    while state.running:
        # Generate random input
        x_t = {mod: np.random.randn(atmr.d[mod]) for mod in atmr.modalities}

        # Occasionally boost different modalities
        if step % 20 == 0:
            x_t['vision'] *= 3.0
        elif step % 20 == 7:
            x_t['audio'] *= 3.0
        elif step % 20 == 14:
            x_t['threat'] *= 5.0

        # Process
        out = atmr.step(x_t, adapt=True)

        # Update monitoring
        update_monitoring(out)

        step += 1
        time.sleep(0.5)  # 2 updates per second


@app.route('/')
def index():
    """Serve main dashboard page."""
    return render_template('monitor.html')


@app.route('/api/current')
def api_current():
    """Get current state."""
    return jsonify(state.monitor_data['current'] or {})


@app.route('/api/history')
def api_history():
    """Get historical data."""
    return jsonify({
        'gates': list(state.monitor_data['gates']),
        'pe': list(state.monitor_data['pe']),
        'confidence': list(state.monitor_data['confidence']),
        'timestamps': list(state.monitor_data['timestamps']),
        'dominant': list(state.monitor_data['dominant']),
        'modalities': state.monitor_data['modalities']
    })


@app.route('/api/stats')
def api_stats():
    """Get statistics."""
    return jsonify(state.monitor_data['stats'])


@app.route('/api/start')
def api_start():
    """Start simulation."""
    if not state.running:
        thread = threading.Thread(target=simulate_data, daemon=True)
        thread.start()
        return jsonify({'status': 'started'})
    return jsonify({'status': 'already_running'})


@app.route('/api/stop')
def api_stop():
    """Stop simulation."""
    state.running = False
    return jsonify({'status': 'stopped'})


# HTML Template
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>ATM-R Monitoring Dashboard</title>
    <meta charset="utf-8">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #1a1a2e;
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

        .gate-bar {
            margin-bottom: 15px;
        }

        .gate-label {
            display: flex;
            justify-content: space-between;
            margin-bottom: 5px;
            font-size: 0.9em;
        }

        .gate-progress {
            background: #0f3460;
            height: 25px;
            border-radius: 5px;
            overflow: hidden;
            position: relative;
        }

        .gate-fill {
            height: 100%;
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
            transition: width 0.3s ease;
            display: flex;
            align-items: center;
            padding-left: 10px;
            color: white;
            font-weight: bold;
            font-size: 0.85em;
        }

        .gate-fill.dominant {
            background: linear-gradient(90deg, #f093fb 0%, #f5576c 100%);
            animation: pulse 1s infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.8; }
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

        .chart-container {
            height: 300px;
            margin-top: 20px;
        }

        .health-indicator {
            display: flex;
            align-items: center;
            padding: 10px;
            background: #0f3460;
            border-radius: 5px;
            margin-bottom: 10px;
        }

        .health-indicator.ok {
            border-left: 4px solid #4caf50;
        }

        .health-indicator.warning {
            border-left: 4px solid #ff9800;
        }

        .health-indicator.error {
            border-left: 4px solid #f44336;
        }

        .status-dot {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 10px;
            background: #4caf50;
            animation: blink 2s infinite;
        }

        @keyframes blink {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }

        .timeline {
            font-family: monospace;
            font-size: 0.8em;
            white-space: pre;
            background: #0f3460;
            padding: 10px;
            border-radius: 5px;
            overflow-x: auto;
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

        button:active {
            transform: translateY(0);
        }
    </style>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@3.9.1/dist/chart.min.js"></script>
</head>
<body>
    <div class="header">
        <h1>🧠 ATM-R Monitoring Dashboard</h1>
        <p>Real-time visualization of Adaptive Thalamic Multimodal Routing</p>
    </div>

    <div class="controls">
        <button onclick="startMonitoring()">▶ Start Monitoring</button>
        <button onclick="stopMonitoring()">⏸ Stop</button>
        <button onclick="location.reload()">🔄 Refresh</button>
    </div>

    <div class="grid">
        <div class="panel">
            <h2>📊 Current Gate Weights</h2>
            <div id="gates-container"></div>
        </div>

        <div class="panel">
            <h2>📈 Statistics</h2>
            <div class="stat-grid">
                <div class="stat-box">
                    <div class="stat-value" id="stat-confidence">-</div>
                    <div class="stat-label">Confidence</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value" id="stat-entropy">-</div>
                    <div class="stat-label">Entropy</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value" id="stat-dominant">-</div>
                    <div class="stat-label">Dominant Agent</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value" id="stat-steps">-</div>
                    <div class="stat-label">Total Steps</div>
                </div>
            </div>
        </div>
    </div>

    <div class="grid">
        <div class="panel">
            <h2>📉 Gate History (Last 100 steps)</h2>
            <div class="chart-container">
                <canvas id="gateChart"></canvas>
            </div>
        </div>

        <div class="panel">
            <h2>⚡ Prediction Errors (Novelty)</h2>
            <div id="pe-container"></div>
        </div>
    </div>

    <div class="grid">
        <div class="panel">
            <h2>🏥 Health Indicators</h2>
            <div id="health-container">
                <div class="health-indicator ok">
                    <div class="status-dot"></div>
                    <span>System initializing...</span>
                </div>
            </div>
        </div>

        <div class="panel">
            <h2>📅 Agent Activity Timeline</h2>
            <div class="timeline" id="timeline"></div>
        </div>
    </div>

    <script>
        let chart = null;
        let updateInterval = null;

        // Initialize chart
        const ctx = document.getElementById('gateChart').getContext('2d');

        function startMonitoring() {
            fetch('/api/start').then(r => r.json()).then(data => {
                console.log('Monitoring started:', data);
            });

            if (!updateInterval) {
                updateInterval = setInterval(updateDashboard, 500);
            }
        }

        function stopMonitoring() {
            fetch('/api/stop').then(r => r.json()).then(data => {
                console.log('Monitoring stopped:', data);
            });
        }

        async function updateDashboard() {
            try {
                // Get current state
                const current = await fetch('/api/current').then(r => r.json());
                const history = await fetch('/api/history').then(r => r.json());
                const stats = await fetch('/api/stats').then(r => r.json());

                if (!current.gates) return;

                const modalities = history.modalities;

                // Update current gates
                updateGates(current.gates, current.dominant, modalities);

                // Update prediction errors
                updatePE(current.pe, modalities);

                // Update stats
                document.getElementById('stat-confidence').textContent =
                    (current.confidence * 100).toFixed(0) + '%';
                document.getElementById('stat-entropy').textContent =
                    stats.entropy ? stats.entropy.toFixed(2) : '-';
                document.getElementById('stat-dominant').textContent = current.dominant;
                document.getElementById('stat-steps').textContent = stats.total_steps || 0;

                // Update chart
                updateChart(history, modalities);

                // Update timeline
                updateTimeline(history, modalities);

                // Update health
                updateHealth(current, stats);

            } catch (error) {
                console.error('Update error:', error);
            }
        }

        function updateGates(gates, dominant, modalities) {
            const container = document.getElementById('gates-container');
            container.innerHTML = '';

            gates.forEach((gate, i) => {
                const mod = modalities[i];
                const isDominant = mod === dominant;

                const div = document.createElement('div');
                div.className = 'gate-bar';
                div.innerHTML = `
                    <div class="gate-label">
                        <span>${mod.toUpperCase()}</span>
                        <span>${(gate * 100).toFixed(1)}%</span>
                    </div>
                    <div class="gate-progress">
                        <div class="gate-fill ${isDominant ? 'dominant' : ''}"
                             style="width: ${gate * 100}%">
                            ${gate > 0.1 ? (isDominant ? '<<< ACTIVE' : '') : ''}
                        </div>
                    </div>
                `;
                container.appendChild(div);
            });
        }

        function updatePE(pe, modalities) {
            const container = document.getElementById('pe-container');
            container.innerHTML = '';

            modalities.forEach(mod => {
                const peVal = pe[mod] || 0;
                const barWidth = Math.min(peVal / 5 * 100, 100);

                const div = document.createElement('div');
                div.className = 'gate-bar';
                div.innerHTML = `
                    <div class="gate-label">
                        <span>${mod}</span>
                        <span>${peVal.toFixed(2)}</span>
                    </div>
                    <div class="gate-progress">
                        <div class="gate-fill" style="width: ${barWidth}%; background: #ff6b6b;">
                            ${peVal > 3 ? '<!> HIGH' : ''}
                        </div>
                    </div>
                `;
                container.appendChild(div);
            });
        }

        function updateChart(history, modalities) {
            if (chart) chart.destroy();

            const datasets = modalities.map((mod, i) => ({
                label: mod,
                data: history.gates.map(g => g[i] * 100),
                borderWidth: 2,
                fill: false
            }));

            chart = new Chart(ctx, {
                type: 'line',
                data: { labels: history.gates.map((_, i) => i), datasets },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { labels: { color: '#eee' } } },
                    scales: {
                        y: {
                            beginAtZero: true, max: 100,
                            ticks: { color: '#eee' },
                            grid: { color: '#333' }
                        },
                        x: {
                            ticks: { color: '#eee' },
                            grid: { color: '#333' }
                        }
                    }
                }
            });
        }

        function updateTimeline(history, modalities) {
            const recent = history.dominant.slice(-50);
            let timeline = modalities.map(mod => `${mod.padEnd(12)} `).join('\\n');

            for (let step = 0; step < 50; step++) {
                let col = '\\n';
                modalities.forEach(mod => {
                    const char = recent[step] === mod ? '#' : '.';
                    col += char.padEnd(12) + ' ';
                });
                timeline += col;
            }

            document.getElementById('timeline').textContent = timeline;
        }

        function updateHealth(current, stats) {
            const container = document.getElementById('health-container');
            const gateSum = current.gates.reduce((a, b) => a + b, 0);

            const checks = [
                {
                    ok: Math.abs(gateSum - 1.0) < 0.001,
                    message: `Gate normalization: ${gateSum.toFixed(10)}`
                },
                {
                    ok: stats.entropy > 0.5,
                    message: `Diversity: ${stats.entropy ? stats.entropy.toFixed(2) : '-'} bits`
                },
                {
                    ok: current.confidence > 0.4,
                    message: `Confidence: ${(current.confidence * 100).toFixed(0)}%`
                }
            ];

            container.innerHTML = checks.map(check => `
                <div class="health-indicator ${check.ok ? 'ok' : 'warning'}">
                    <div class="status-dot" style="background: ${check.ok ? '#4caf50' : '#ff9800'}"></div>
                    <span>${check.message}</span>
                </div>
            `).join('');
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
with open('templates/monitor.html', 'w', encoding='utf-8') as f:
    f.write(HTML_TEMPLATE)


if __name__ == '__main__':
    print("="*80)
    print("ATM-R Web Monitoring Dashboard")
    print("="*80)
    print("\nStarting server...")
    print("\nOpen your browser and navigate to:")
    print("  -> http://localhost:5000")
    print("\nPress Ctrl+C to stop")
    print("="*80)

    app.run(debug=False, host='0.0.0.0', port=5000)
