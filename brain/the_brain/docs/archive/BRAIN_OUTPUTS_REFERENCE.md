# Brain Outputs Reference

## Quick Answer

The brain produces **5 types of outputs**, all as Python dictionaries that can be serialized to JSON:

1. **Routing Output** - Which brain areas are active during a task
2. **Activation Summary** - Real-time monitoring with alerts
3. **Strategy Recommendation** - Proven approaches for similar tasks
4. **Intervention** - Active warnings with suggested alternatives
5. **System State** - Overall learning statistics

---

## Output Type 1: Routing Output

**Method**: `MetaRouter.process_trace(trace)`

**Purpose**: Understand brain activity during task processing

### Structure

```python
{
    # Which brain areas are active (always sums to 1.0)
    'final_gates': np.ndarray([0.076, 0.075, 0.074, 0.073, 0.074,
                               0.127, 0.130, 0.106, 0.090, 0.178]),

    # Gate values at different stages
    'gates': np.ndarray(...),            # Initial gates
    'memory_biased_gates': np.ndarray(...),  # After memory influence
    'ca3_gates': np.ndarray(...),        # CA3 pattern completion

    # Task details
    'trace_features': {
        'tool_type': 'github',
        'duration_seconds': 45.3,
        'tools_used': ['list_repos', 'get_repo'],
        'error_count': 2,
        'success': True,
        ...
    },

    # Memory information
    'hippocampal_output': {
        'encoded': False,          # Was this stored in memory?
        'num_memories': 4,         # Total memories
        'pe_metric': 0.234         # Novelty score
    },

    # Predictions
    'error_count': 2,
    'success': True,

    # Internal structures
    'thalamic_output': {...},      # Raw thalamic processing
    'trace_encoded': {...},        # Encoded modality vectors
    'timestep': 45
}
```

### Gate Interpretation

The 10 gates correspond to modalities:
```
gates[0] = vision (0.076)         # Visual input strength
gates[1] = audio (0.075)          # Audio input strength
gates[2] = touch (0.074)          # Touch input strength
gates[3] = taste (0.073)          # Taste input strength
gates[4] = vestibular (0.074)     # Balance/motion input strength
gates[5] = threat (0.127)         # Threat signal strength
gates[6] = tool_trace (0.130)     # Tool usage pattern strength  ⭐
gates[7] = temporal (0.106)       # Timing pattern strength      ⭐
gates[8] = error_sig (0.090)      # Error signal strength        ⭐
gates[9] = success_sig (0.178)    # Success signal strength      ⭐
```

**Higher values = that modality is more important for this task**

### Use Cases

```python
# Check which modality dominates
routing_out = meta_router.process_trace(trace)
gates = routing_out['final_gates']
dominant_idx = np.argmax(gates)
print(f"Dominant: {modality_names[dominant_idx]}")

# Check if stored in memory
if routing_out['hippocampal_output']['encoded']:
    print("This failure pattern was memorable!")

# Get task features
features = routing_out['trace_features']
print(f"Duration: {features['duration_seconds']:.1f}s")
print(f"Errors: {features['error_count']}")
```

---

## Output Type 2: Activation Summary

**Method**: `BrainActivityMonitor.get_activation_summary()`

**Purpose**: Real-time monitoring and alerting

### Structure

```python
{
    # Module activation levels (0.0 to 1.0)
    'current_activation': {
        'thalamus': 0.100,           # Thalamic routing activity
        'hippocampus': 0.100,        # Memory activity
        'error_detection': 0.800,    # Error detection HIGH!
        'success_prediction': 0.000,  # Success prediction inactive
        'tool_trace': 0.124,         # Tool pattern activity
        'temporal': 0.092            # Temporal pattern activity
    },

    # Active alerts
    'alerts': [
        {
            'level': 'warning',  # 'info', 'warning', 'critical'
            'message': 'High error count: 8',
            'recommendation': 'Check for recurring error patterns'
        }
    ],

    # Statistics
    'gate_strength': 0.100,      # Average gate activation
    'avg_error_rate': 5.90,      # Mean error count
    'total_memories': 2          # Episodic memories stored
}
```

### Alert Levels

- **info**: Minor issue, informational only
- **warning**: Problem detected, should investigate
- **critical**: Serious issue, immediate action needed

### Use Cases

```python
# Get current state
summary = brain_monitor.get_activation_summary()

# Check for alerts
if summary['alerts']:
    for alert in summary['alerts']:
        if alert['level'] == 'critical':
            print(f"CRITICAL: {alert['message']}")
            print(f"Action: {alert['recommendation']}")

# Monitor error detection
if summary['current_activation']['error_detection'] > 0.5:
    print("Brain is detecting high error activity!")

# Visualize
print(brain_monitor.visualize_ascii())
```

---

## Output Type 3: Strategy Recommendation

**Method**: `StrategyLibrary.get_recommendation(task_type, current_errors)`

**Purpose**: Suggest proven approaches based on past success

### Structure

```python
{
    # Best strategy
    'strategy': ['resolve', 'get'],     # Tool sequence
    'expected_duration': 72.3,          # Seconds
    'success_rate': 1.0,                # 0.0 to 1.0 (100%)
    'confidence': 0.790,                # Quality score

    # Alternative strategies
    'alternatives': [
        {
            'tools': ['resolve'],
            'success_rate': 1.0
        }
    ],

    # Urgency (if errors detected)
    'urgency': 'high',                  # Only present if current_errors > 3
    'message': 'High error count! Recommend trying proven strategy.'
}
```

### Confidence Score

Computed as:
```
confidence = success_rate * 0.6 + usage_factor * 0.3 + recency_factor * 0.1

where:
  success_rate  = how often this strategy succeeds
  usage_factor  = min(usage_count / 10.0, 1.0)  # trust increases with use
  recency_factor = exp(-0.1 * last_used)         # prefer recent strategies
```

### Use Cases

```python
# Get recommendation
rec = strategy_lib.get_recommendation('github', current_errors=5)

if rec:
    print(f"Try: {' -> '.join(rec['strategy'])}")
    print(f"Success rate: {rec['success_rate']:.1%}")
    print(f"Expected time: {rec['expected_duration']:.1f}s")
    print(f"Confidence: {rec['confidence']:.3f}")

    # Check urgency
    if rec.get('urgency') == 'high':
        print(f"URGENT: {rec['message']}")

    # Show alternatives
    if rec['alternatives']:
        print("\nAlternatives:")
        for i, alt in enumerate(rec['alternatives'], 1):
            print(f"  {i}. {' -> '.join(alt['tools'])}")
```

---

## Output Type 4: Intervention

**Method**: `LiveBrainMonitor.update(conversation)`

**Purpose**: Active failure prevention with recommendations

### Structure

```python
{
    # Why intervention triggered
    'reason': 'High error count (4)',

    # Urgency level
    'urgency': 'high',  # 'low', 'medium', 'high', 'critical'

    # Human-readable message
    'message': 'No proven strategies found for test. Consider terminating.',

    # Current conversation state
    'current_state': {
        'tool_type': 'test',
        'task': 'Test task',
        'duration_seconds': 0.0,
        'tools_used': ['retry_tool', 'test_tool'],
        'tool_counts': {'test_tool': 2, 'retry_tool': 1},
        'max_tool_repetition': 2,
        'error_count': 4,
        'clarification_count': 0,
        'qa_reject_count': 0,
        'outcome': 'in_progress',
        'success': True
    },

    # Recommended strategy (if found)
    'recommendation': {
        'strategy': ['github_list_repos', 'github_get_repo'],
        'expected_duration': 12.5,
        'success_rate': 0.85,
        'confidence': 0.842
    },

    # Alternative strategies
    'alternatives': [
        {'tools': ['github_get_user', 'github_list_repos'],
         'success_rate': 0.78}
    ]
}
```

### Intervention Triggers

| Trigger | Condition | Urgency |
|---------|-----------|---------|
| High errors | error_count >= 5 | high |
| Tool repetition | same_tool >= 3x | **critical** |
| QA rejections | qa_reject_count >= 3 | high |
| User confusion | clarification_count >= 4 | medium |
| Duration exceeded | duration > expected * 2 | medium |

### Use Cases

```python
# Monitor conversation
conversation = live_monitor.start_conversation("Deploy app")

# ... task execution ...
conversation.add_tool_call("docker_create")
conversation.add_error()

# Check for intervention
intervention = live_monitor.update(conversation)

if intervention:
    print(f"[{intervention['urgency'].upper()}] {intervention['reason']}")

    # Critical = stop immediately
    if intervention['urgency'] == 'critical':
        print("Terminating task!")
        return

    # High = try alternative
    elif intervention['urgency'] == 'high':
        if intervention['recommendation']:
            print(f"Trying alternative: {intervention['recommendation']['strategy']}")
            # Execute alternative strategy

    # Medium = warning only
    elif intervention['urgency'] == 'medium':
        print(f"Warning: {intervention['message']}")
```

---

## Output Type 5: System State

**Method**: `MetaRouter.get_state()`

**Purpose**: Monitor system health and learning progress

### Structure

```python
{
    # Processing statistics
    'traces_processed': 11,
    'failures_encoded': 0,
    'successes_encoded': 11,

    # Thalamo-hippocampal state
    'thalamo_hippocampal_state': {
        'hippocampal': {
            'num_memories': 2,         # Total episodic memories
            'timestep': 11,
            'ca3_weights_norm': 0.45,  # CA3 weight magnitude
            'memory_ages': [3, 7],     # How old each memory is
            'memory_strengths': [0.8, 0.6]  # Strength of each memory
        },
        'thalamic': {
            # Internal thalamic state
            ...
        }
    }
}
```

### Derived Metrics

```python
state = meta_router.get_state()

# Success rate
success_rate = state['successes_encoded'] / state['traces_processed']
print(f"Success rate: {success_rate:.1%}")

# Memory efficiency (lower = better)
memory_efficiency = state['failures_encoded'] / state['traces_processed']
print(f"Memory efficiency: {memory_efficiency:.1%}")
# 10.3% = EXCELLENT (only encodes novel failures)
# 40%+ = needs optimization (encoding too much)

# Memory status
num_memories = state['thalamo_hippocampal_state']['hippocampal']['num_memories']
print(f"Episodic memories: {num_memories}")
```

---

## Complete Integration Example

```python
from core.meta_router import MetaRouter
from core.brain_monitor import BrainActivityMonitor
from core.strategy_library import StrategyLibrary
from core.live_brain_monitor import LiveBrainMonitor

# Initialize
meta_router = MetaRouter(enable_hippocampus=True)
brain_monitor = BrainActivityMonitor()
strategy_lib = StrategyLibrary()
live_monitor = LiveBrainMonitor(meta_router, brain_monitor, strategy_lib)

# Monitor a task
conversation = live_monitor.start_conversation("Deploy application")

# Task execution loop
while task_running:
    # Execute tool
    tool_result = execute_tool()

    # Update brain
    conversation.add_tool_call(tool_result.tool_name)
    if tool_result.error:
        conversation.add_error()

    # Check for intervention
    intervention = live_monitor.update(conversation)

    if intervention:
        print(f"Intervention: {intervention['reason']}")

        # OUTPUT 1: Check brain activity
        routing_out = meta_router.process_trace(create_trace(conversation))
        print(f"Dominant modality: {get_dominant(routing_out['final_gates'])}")

        # OUTPUT 2: Check alerts
        summary = brain_monitor.get_activation_summary()
        if summary['alerts']:
            for alert in summary['alerts']:
                print(f"Alert: {alert['message']}")

        # OUTPUT 3: Get strategy recommendation
        rec = strategy_lib.get_recommendation(
            task_type=conversation.tool_type,
            current_errors=conversation.error_count
        )
        if rec:
            print(f"Recommended: {rec['strategy']}")
            print(f"Success rate: {rec['success_rate']:.1%}")

        # OUTPUT 4: Handle intervention
        if intervention['urgency'] == 'critical':
            break  # Stop task
        elif intervention['recommendation']:
            # Try alternative
            execute_strategy(intervention['recommendation']['strategy'])

    # Continue task...

# End monitoring
live_monitor.end_conversation(conversation, success=True)

# OUTPUT 5: Check system state
state = meta_router.get_state()
print(f"Total processed: {state['traces_processed']}")
print(f"Success rate: {state['successes_encoded']/state['traces_processed']:.1%}")
```

---

## Output Format Summary

| Output | Format | Size | JSON? |
|--------|--------|------|-------|
| Routing Output | Dict + NumPy arrays | ~50 keys | Yes* |
| Activation Summary | Dict | ~10 keys | Yes |
| Strategy Recommendation | Dict | ~6 keys | Yes |
| Intervention | Dict | ~7 keys | Yes |
| System State | Dict | ~5 keys | Yes |

*NumPy arrays need conversion: `array.tolist()`

---

## Logging Example

```python
import json
import numpy as np

def log_brain_output(output, filename):
    """Save brain output to JSON file."""

    # Convert NumPy arrays to lists
    def convert(obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, dict):
            return {k: convert(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert(v) for v in obj]
        return obj

    output_json = convert(output)

    with open(filename, 'w') as f:
        json.dump(output_json, f, indent=2)

# Usage
routing_out = meta_router.process_trace(trace)
log_brain_output(routing_out, 'data/routing_output.json')

intervention = live_monitor.update(conversation)
log_brain_output(intervention, 'data/intervention.json')
```

---

## Dashboard Example

```python
from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/brain/status')
def brain_status():
    """Return current brain status."""
    summary = brain_monitor.get_activation_summary()
    state = meta_router.get_state()

    return jsonify({
        'activation': summary['current_activation'],
        'alerts': summary['alerts'],
        'memories': state['thalamo_hippocampal_state']['hippocampal']['num_memories'],
        'success_rate': state['successes_encoded'] / state['traces_processed']
    })

@app.route('/brain/intervention/<conversation_id>')
def get_intervention(conversation_id):
    """Get intervention for conversation."""
    conversation = get_conversation(conversation_id)
    intervention = live_monitor.update(conversation)

    if intervention:
        return jsonify(intervention)
    else:
        return jsonify({'status': 'ok', 'intervention': None})
```

---

## Key Takeaways

1. **All outputs are Python dicts** - Easy to serialize, log, or send over network

2. **Outputs are composable** - Use them together for complete picture:
   - Routing Output → What brain is thinking
   - Activation Summary → Real-time status
   - Strategy Recommendation → What to do
   - Intervention → When to act
   - System State → Learning progress

3. **Designed for integration** - Drop into existing systems:
   - Event-driven (call update() on events)
   - Stateless (all state in returned dicts)
   - JSON-serializable (for logging/dashboards)

4. **Human-readable** - All outputs include:
   - Clear field names
   - Human-readable messages
   - Actionable recommendations

5. **Machine-actionable** - Can trigger automated actions:
   - Intervention urgency → terminate/retry/continue
   - Alerts → log/notify/escalate
   - Recommendations → execute alternative strategy

---

## Demo Script

Run this to see all outputs:
```bash
python demos/show_brain_outputs.py
```

This demonstrates all 5 output types with real data!
