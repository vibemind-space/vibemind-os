# ATM-R Monitoring Dashboard Guide

**Status:** ✅ Both dashboards tested and working

## Available Dashboards

You now have **two monitoring options** for visualizing ATM-R routing decisions in real-time:

### 1. Terminal Dashboard (monitor_dashboard.py)
### 2. Web Dashboard (monitor_web.py)

---

## Option 1: Terminal Dashboard

**Best for:** Quick debugging, command-line environments, no additional dependencies

### Features
- Real-time ASCII visualization
- Current gate weights (bar charts)
- Prediction errors (novelty signals)
- Agent activity timeline (last 50 steps)
- Health indicators (normalization, entropy, confidence)
- Usage statistics
- CSV export for analysis

### Usage

#### Standalone Demo
```bash
python monitor_dashboard.py
```

This runs a built-in simulation showing ATM-R routing with random multimodal inputs.

**Press Ctrl+C to stop and export data**

#### Integrate into Your Code

```python
from thalamo_pc_adaptive import ThalamoPC6Adaptive
from monitor_dashboard import ATMRMonitor

# Create ATM-R
atmr = ThalamoPC6Adaptive(seed=42)

# Create monitor
monitor = ATMRMonitor(atmr, history_length=100)

# Your processing loop
for step in range(100):
    # Get your multimodal input
    x_t = {
        'vision': vision_features,
        'audio': audio_features,
        'touch': touch_features,
        'taste': taste_features,
        'vestibular': vestibular_features,
        'threat': threat_signal
    }

    # ATM-R processing
    out = atmr.step(x_t, adapt=True)

    # Update monitor
    monitor.update(out)

    # Display dashboard (refreshes screen)
    monitor.display(clear_screen=True)

    # Optional: Small delay for visibility
    time.sleep(0.1)

# Export data when done
monitor.export_csv('my_monitoring_log.csv')
```

#### Display Dashboard Without Clearing Screen

Useful for logging or when you don't want screen flicker:

```python
monitor.display(clear_screen=False)
```

#### Get Statistics Programmatically

```python
stats = monitor.get_stats()

print(f"Total steps: {stats['total_steps']}")
print(f"Current dominant: {stats['current_dominant']}")
print(f"Current confidence: {stats['current_confidence']:.1%}")
print(f"Current entropy: {stats['current_entropy']:.2f} bits")
print(f"Average gates: {stats['average_gates']}")
```

### Dashboard Sections

#### Current Gate Weights
```
[CURRENT GATE WEIGHTS - Agent Attention Allocation]
  vision       [78.2%] #######################################      <<< DOMINANT
  audio        [ 7.1%] ###                                          - active
  threat       [ 8.8%] ####                                         - active
```

**Interpretation:**
- `<<<  DOMINANT` = Gate > 50% (primary agent)
- `<-- ACTIVE` = Gate > 20% (significant attention)
- `- active` = Gate > 5% (minor attention)

#### Prediction Errors
```
[PREDICTION ERRORS - Novelty/Surprise Signals]
  vision       [ 10.99] ****************************** <!> HIGH NOVELTY
  audio        [  7.04] ****************************** <!> HIGH NOVELTY
```

**Interpretation:**
- High PE (>3.0) = Novel/surprising input = learning opportunity
- Low PE (<1.0) = Expected/familiar input = exploitation

#### Agent Activity Timeline
```
[AGENT ACTIVITY TIMELINE - Last 50 steps]
  vision       [61.3%] #########====#####=====####========-----------...
  audio        [31.9%] ------===####------====----========###########...
```

**Symbols:**
- `#` = Dominant (gate > 50%)
- `=` = Active (gate > 20%)
- `-` = Minor (gate > 5%)
- `.` = Inactive (gate < 5%)

#### Health Indicators
```
[HEALTH INDICATORS]
  [OK]     Gate normalization: 1.0000000000
  [OK]     Good diversity (entropy=1.17)
  [OK]     High confidence (78.2%)
```

**Status:**
- `[OK]` = System healthy
- `[WARN]` = Potential issue (low diversity, low confidence)
- `[ERROR]` = Critical issue (NaN/Inf values)

---

## Option 2: Web Dashboard

**Best for:** Production monitoring, remote access, professional visualization, sharing with team

### Features
- Beautiful web interface with gradient styling
- Real-time animated charts (Chart.js)
- Historical trends (last 100 steps)
- Interactive line graphs
- Auto-refreshing every 500ms
- Professional layout with panels
- Health indicators with status lights
- Agent activity heatmap
- No screen clearing issues

### Usage

#### Run Standalone Demo

```bash
python monitor_web.py
```

Then open your browser to: **http://localhost:5000**

The demo will automatically start simulating ATM-R processing.

**Controls:**
- ▶ Start Monitoring - Begin simulation
- ⏸ Stop - Pause simulation
- 🔄 Refresh - Reload page

**Press Ctrl+C in terminal to stop the server**

#### Integrate into Your Code

```python
from flask import Flask
from monitor_web import app, state, update_monitoring
from thalamo_pc_adaptive import ThalamoPC6Adaptive
import threading
import time

# Initialize ATM-R
atmr = ThalamoPC6Adaptive(seed=42)
state.atmr = atmr
state.monitor_data['modalities'] = atmr.modalities

# Your processing function
def process_loop():
    while True:
        # Get your multimodal input
        x_t = {
            'vision': get_vision_features(),
            'audio': get_audio_features(),
            'touch': get_touch_features(),
            'taste': get_taste_features(),
            'vestibular': get_vestibular_features(),
            'threat': get_threat_signal()
        }

        # ATM-R processing
        out = atmr.step(x_t, adapt=True)

        # Update monitoring
        update_monitoring(out)

        time.sleep(0.1)  # Control update rate

# Start processing in background
thread = threading.Thread(target=process_loop, daemon=True)
thread.start()

# Start web server
app.run(debug=False, host='0.0.0.0', port=5000)
```

#### Access Monitoring Data via API

The web dashboard exposes REST API endpoints:

**Get Current State:**
```bash
curl http://localhost:5000/api/current
```

Returns:
```json
{
  "gates": [0.78, 0.07, 0.03, 0.01, 0.01, 0.09],
  "pe": {"vision": 10.2, "audio": 7.0, ...},
  "confidence": 0.78,
  "dominant": "vision",
  "timestamp": 1728765432.123
}
```

**Get Historical Data:**
```bash
curl http://localhost:5000/api/history
```

Returns last 100 steps of gates, PE, confidence, timestamps, and dominant agents.

**Get Statistics:**
```bash
curl http://localhost:5000/api/stats
```

Returns:
```json
{
  "avg_confidence": 0.85,
  "avg_gates": [0.62, 0.31, 0.01, 0.00, 0.00, 0.05],
  "total_steps": 150,
  "entropy": 1.17
}
```

**Control Simulation:**
```bash
curl http://localhost:5000/api/start    # Start simulation
curl http://localhost:5000/api/stop     # Stop simulation
```

### Dashboard Sections

#### 📊 Current Gate Weights
- Animated progress bars
- Percentage labels
- Dominant agent highlighted with pulsing animation

#### 📈 Statistics
- Confidence level
- Entropy (attention diversity)
- Dominant agent name
- Total steps processed

#### 📉 Gate History Chart
- Interactive line chart
- Last 100 steps
- All 6 modalities color-coded
- Hover for exact values

#### ⚡ Prediction Errors
- Real-time novelty signals
- Red bars for high PE (>3.0)
- Shows all modalities

#### 🏥 Health Indicators
- Gate normalization check
- Diversity check (entropy)
- Confidence level
- Status lights (green/yellow/red)

#### 📅 Agent Activity Timeline
- Monospace grid showing last 50 steps
- `#` = Active, `.` = Inactive
- Shows temporal patterns

---

## Comparison: Terminal vs Web

| Feature | Terminal | Web |
|---------|----------|-----|
| Setup | None | Flask + browser |
| Performance | Very fast | Moderate |
| Visual Quality | ASCII | Professional |
| Remote Access | SSH | Yes (port 5000) |
| CSV Export | ✅ Built-in | ❌ Use API |
| Real-time Charts | ❌ ASCII only | ✅ Chart.js |
| Screen Flicker | Minimal | None |
| Interactivity | Keyboard | Mouse + API |
| Best For | Debugging | Production |

---

## Configuration

### Terminal Dashboard

```python
# Adjust history length (default: 100)
monitor = ATMRMonitor(atmr, history_length=200)

# Control display refresh
monitor.display(clear_screen=True)   # Full refresh
monitor.display(clear_screen=False)  # Append mode

# Change CSV export filename
monitor.export_csv('custom_log.csv')
```

### Web Dashboard

```python
# Change port (default: 5000)
app.run(debug=False, host='0.0.0.0', port=8080)

# Enable debug mode for development
app.run(debug=True, host='127.0.0.1', port=5000)

# Adjust history buffer size
# Edit monitor_web.py line 32-37:
self.monitor_data = {
    'gates': deque(maxlen=200),  # Change from 100
    'pe': deque(maxlen=200),
    # ...
}

# Adjust update rate
# Edit HTML template line 446:
updateInterval = setInterval(updateDashboard, 500);  # milliseconds
```

---

## Use Cases

### 1. Development & Debugging
**Use:** Terminal dashboard with `clear_screen=False`

```python
monitor = ATMRMonitor(atmr)
for step in range(100):
    out = atmr.step(x_t)
    monitor.update(out)

    # Only display every 10 steps
    if step % 10 == 0:
        monitor.display(clear_screen=False)
        print(f"\n--- Step {step} ---\n")
```

### 2. Real-time Demo / Presentation
**Use:** Web dashboard

Open http://localhost:5000 on a projector/screen while your system runs.

### 3. Production Monitoring
**Use:** Web dashboard + API polling

```python
# Monitoring script
import requests
import time

while True:
    stats = requests.get('http://localhost:5000/api/stats').json()

    # Alert if confidence drops
    if stats['avg_confidence'] < 0.4:
        send_alert("Low ATM-R confidence!")

    # Alert if entropy too low (collapsed attention)
    if stats['entropy'] < 0.1:
        send_alert("ATM-R attention collapsed!")

    time.sleep(5)
```

### 4. Batch Analysis
**Use:** Terminal dashboard with CSV export

```python
monitor = ATMRMonitor(atmr, history_length=10000)

# Process entire dataset
for data in dataset:
    out = atmr.step(data)
    monitor.update(out)

# Export for analysis
monitor.export_csv('batch_results.csv')

# Analyze in pandas
import pandas as pd
df = pd.read_csv('batch_results.csv')
print(df.groupby('dominant')['confidence'].mean())
```

### 5. Multi-Agent System Integration
**Use:** Web dashboard with custom frontend

Your multi-agent OS can:
1. Run monitor_web.py as a service
2. Poll `/api/current` to get routing decisions
3. Embed the dashboard in your admin panel
4. Use routing info for orchestration

```python
# In your agent orchestrator
def get_active_agents():
    """Get agents that ATM-R is currently routing to."""
    response = requests.get('http://localhost:5000/api/current')
    data = response.json()

    # Get agents with >10% attention
    active = []
    for i, mod in enumerate(['vision', 'audio', 'touch', 'taste', 'vestibular', 'threat']):
        if data['gates'][i] > 0.1:
            active.append(mod)

    return active
```

---

## Troubleshooting

### Terminal Dashboard

**Issue:** Screen flickering
**Solution:** Increase sleep time or use `clear_screen=False`

**Issue:** Encoding errors on Windows
**Solution:** All fixed! ASCII characters used throughout.

**Issue:** History not showing
**Solution:** Need at least 10 steps before timeline displays.

### Web Dashboard

**Issue:** Port 5000 already in use
**Solution:** Change port: `app.run(port=8080)`

**Issue:** Browser shows "This site can't be reached"
**Solution:**
1. Check Flask server is running
2. Check firewall settings
3. Try http://127.0.0.1:5000 instead

**Issue:** Dashboard not updating
**Solution:**
1. Click "▶ Start Monitoring"
2. Check browser console for errors (F12)
3. Verify `/api/current` returns data

**Issue:** Chart not rendering
**Solution:** Check internet connection (Chart.js loaded from CDN)

---

## Examples

### Example 1: Monitor Threat Scenarios

```python
from thalamo_pc_adaptive import ThalamoPC6Adaptive
from monitor_dashboard import ATMRMonitor
import numpy as np
import time

atmr = ThalamoPC6Adaptive(seed=42)
monitor = ATMRMonitor(atmr)

print("Simulating security monitoring scenario...")

for step in range(50):
    # Normal operation
    x_t = {mod: np.random.randn(atmr.d[mod]) * 0.5
           for mod in atmr.modalities}

    # Inject threats periodically
    if step % 20 == 10:
        print("\n[ALERT] Threat detected!\n")
        x_t['threat'] = np.random.randn(8) * 10.0  # AMPLIFIED!
        out = atmr.step(x_t, hazard={'threat': 1.0}, adapt=True)
    else:
        out = atmr.step(x_t, adapt=True)

    monitor.update(out)
    monitor.display()
    time.sleep(0.2)

monitor.export_csv('threat_scenario.csv')
```

### Example 2: Compare Configurations

```python
from thalamo_pc_adaptive import ThalamoPC6Adaptive
from monitor_dashboard import ATMRMonitor
import numpy as np

configs = [
    {'seed': 42, 'config': 'configs/default.yaml'},
    {'seed': 42, 'config': 'configs/safety_priority.yaml'}
]

for i, cfg in enumerate(configs):
    print(f"\nTesting config {i+1}: {cfg['config']}")

    atmr = ThalamoPC6Adaptive(seed=cfg['seed'], config=cfg['config'])
    monitor = ATMRMonitor(atmr)

    # Run same inputs
    for step in range(100):
        x_t = {mod: np.random.randn(atmr.d[mod])
               for mod in atmr.modalities}
        out = atmr.step(x_t, adapt=True)
        monitor.update(out)

    # Export results
    monitor.export_csv(f'config_{i+1}_results.csv')

    # Print summary
    stats = monitor.get_stats()
    print(f"  Average confidence: {stats['average_confidence']:.1%}")
    print(f"  Average entropy: {stats['current_entropy']:.2f} bits")
    print(f"  Agent distribution: {stats['average_gates']}")
```

---

## Next Steps

1. **Try the terminal demo:**
   ```bash
   python monitor_dashboard.py
   ```

2. **Try the web demo:**
   ```bash
   python monitor_web.py
   # Open http://localhost:5000
   ```

3. **Integrate into your code** using examples above

4. **Customize** colors, update rates, history length

5. **Export data** for offline analysis

---

## Summary

✅ **Terminal Dashboard:** Fast, lightweight, great for debugging
✅ **Web Dashboard:** Beautiful, interactive, great for production
✅ **Both Tested:** All features working correctly
✅ **Easy Integration:** Drop-in monitoring for your ATM-R code
✅ **Flexible:** Standalone demo or integrated monitoring
✅ **Export:** CSV export for analysis (terminal) or REST API (web)

**Your ATM-R monitoring infrastructure is ready to use!**
