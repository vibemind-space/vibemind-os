"""
Show Actual Brain Outputs

Demonstrates what each brain component produces as output.
"""

import sys
sys.path.insert(0, 'C:\\Users\\User\\Desktop\\Tahlamus')

import numpy as np
import json
from core.meta_router import MetaRouter
from core.brain_monitor import BrainActivityMonitor
from core.strategy_library import StrategyLibrary
from core.live_brain_monitor import LiveBrainMonitor
from core.conversation_trace_encoder import load_session_logs

print("="*80)
print("BRAIN OUTPUT DEMONSTRATION")
print("="*80)
print()

# Initialize components
log_dir = r"C:\Users\User\Desktop\sakana-desktop-assistant\data\logs\sessions"
meta_router = MetaRouter(enable_hippocampus=True, seed=42)
brain_monitor = BrainActivityMonitor(history_length=100)
strategy_lib = StrategyLibrary(max_strategies_per_type=20)

# Train on a few traces
print("Training on sample data...")
all_traces = load_session_logs(log_dir, limit=10)
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

print(f"Trained on {len(all_traces)} traces")
print()

# ============================================================================
# OUTPUT 1: MetaRouter Output (process_trace)
# ============================================================================
print("="*80)
print("OUTPUT 1: MetaRouter - process_trace()")
print("="*80)
print()

# Process a single trace
trace = all_traces[0]
routing_output = meta_router.process_trace(trace, adapt=False)

print("MetaRouter produces a dictionary with:")
print()
print("1. THALAMIC GATES (10 modalities):")
print("   Shows which brain areas are active")
gates = routing_output.get('final_gates', np.zeros(10))
modality_names = ['vision', 'audio', 'touch', 'taste', 'vestibular', 'threat',
                  'tool_trace', 'temporal', 'error_sig', 'success_sig']
for name, gate_value in zip(modality_names, gates):
    print(f"   {name:15s}: {gate_value:.4f}")

print()
print("2. LATENT STATES:")
if 'v_next' in routing_output:
    print(f"   Shape: {routing_output['v_next'].shape}")
    print(f"   Example values: {routing_output['v_next'][:5]}")
else:
    print(f"   (Latent states computed internally)")

print()
print("3. PREDICTION ERRORS:")
if 'pe' in routing_output:
    print(f"   Shape: {routing_output['pe'].shape}")
    print(f"   Error magnitudes: {routing_output['pe'][:5]}")
else:
    print(f"   (Prediction errors computed internally)")

print()
print("4. ROUTING OUTPUT:")
if 'y' in routing_output:
    print(f"   Shape: {routing_output['y'].shape}")
    print(f"   Routed values: {routing_output['y'][:5]}")
else:
    print(f"   (Routing outputs computed internally)")

print()
print("5. TRACE FEATURES:")
features_output = routing_output['trace_features']
print(f"   Tool type: {features_output['tool_type']}")
print(f"   Duration: {features_output['duration_seconds']:.2f}s")
print(f"   Tools used: {features_output['tools_used'][:3]}...")
print(f"   Error count: {features_output['error_count']}")
print(f"   Success: {features_output['success']}")

print()
print("6. HIPPOCAMPAL OUTPUT:")
hc_output = routing_output.get('hippocampal_output', {})
print(f"   Encoded in memory: {hc_output.get('encoded', False)}")
print(f"   Total memories: {hc_output.get('num_memories', 0)}")
print(f"   Memory novelty: {hc_output.get('pe_metric', 0.0):.3f}")

print()
print("7. SUCCESS PREDICTION:")
print(f"   Predicted success: {routing_output['success']}")
print(f"   Error count: {routing_output['error_count']}")

print()
print("AVAILABLE OUTPUT KEYS:")
print(f"   {list(routing_output.keys())}")
print()
print("FULL OUTPUT STRUCTURE:")
output_summary = {}
for k, v in routing_output.items():
    if isinstance(v, np.ndarray):
        output_summary[k] = f"ndarray shape {v.shape}"
    elif isinstance(v, dict):
        output_summary[k] = f"dict with {len(v)} keys"
    else:
        output_summary[k] = str(type(v).__name__)
print(json.dumps(output_summary, indent=2))

print()
print()

# ============================================================================
# OUTPUT 2: Brain Monitor Output
# ============================================================================
print("="*80)
print("OUTPUT 2: BrainActivityMonitor - get_activation_summary()")
print("="*80)
print()

summary = brain_monitor.get_activation_summary()

print("Brain Monitor produces a dictionary with:")
print()
print("1. CURRENT ACTIVATION LEVELS:")
for module, activation in summary['current_activation'].items():
    bar = "#" * int(activation * 30)
    print(f"   {module:20s}: {bar:30s} {activation:.3f}")

print()
print("2. ALERTS:")
if summary['alerts']:
    for alert in summary['alerts']:
        print(f"   [{alert['level'].upper()}] {alert['message']}")
        print(f"   -> {alert['recommendation']}")
else:
    print("   No alerts")

print()
print("3. STATISTICS:")
print(f"   Gate strength: {summary['gate_strength']:.3f}")
print(f"   Avg error rate: {summary['avg_error_rate']:.2f}")
print(f"   Total memories: {summary['total_memories']}")

print()
print("4. ASCII VISUALIZATION:")
print(brain_monitor.visualize_ascii())

print()
print()

# ============================================================================
# OUTPUT 3: Strategy Library Output
# ============================================================================
print("="*80)
print("OUTPUT 3: StrategyLibrary - get_recommendation()")
print("="*80)
print()

# Get recommendation for a task type
recommendation = strategy_lib.get_recommendation(task_type='context7', current_errors=3)

if recommendation:
    print("Strategy Library produces a dictionary with:")
    print()
    print("1. RECOMMENDED STRATEGY:")
    print(f"   Tool sequence: {recommendation['strategy']}")
    print(f"   Expected duration: {recommendation['expected_duration']:.2f}s")
    print(f"   Success rate: {recommendation['success_rate']:.1%}")
    print(f"   Confidence: {recommendation['confidence']:.3f}")

    print()
    print("2. ALTERNATIVES:")
    for i, alt in enumerate(recommendation.get('alternatives', []), 1):
        print(f"   {i}. {alt['tools']}")
        print(f"      Success rate: {alt['success_rate']:.1%}")

    print()
    print("3. URGENCY INFO (if errors):")
    if 'urgency' in recommendation:
        print(f"   Urgency: {recommendation['urgency']}")
        print(f"   Message: {recommendation['message']}")

    print()
    print("FULL RECOMMENDATION STRUCTURE:")
    print(json.dumps(recommendation, indent=2, default=str))
else:
    print("No recommendations available for this task type")

print()
print()

# ============================================================================
# OUTPUT 4: Live Brain Monitor Output (Intervention)
# ============================================================================
print("="*80)
print("OUTPUT 4: LiveBrainMonitor - update() [INTERVENTION]")
print("="*80)
print()

# Initialize live monitor
live_monitor = LiveBrainMonitor(
    meta_router=meta_router,
    brain_monitor=brain_monitor,
    strategy_library=strategy_lib,
    error_threshold=3,  # Lower for demo
    repetition_threshold=2
)

# Simulate a failing conversation
conversation = live_monitor.start_conversation("Test task")
conversation.add_tool_call("test_tool")
conversation.add_error()
conversation.add_tool_call("test_tool")
conversation.add_error()
conversation.add_tool_call("retry_tool")
conversation.add_error()
conversation.add_error()  # Trigger at 4 errors (threshold=3)

intervention = live_monitor.update(conversation)

if intervention:
    print("Live Brain Monitor produces an INTERVENTION dictionary with:")
    print()
    print("1. REASON:")
    print(f"   {intervention['reason']}")

    print()
    print("2. URGENCY LEVEL:")
    print(f"   {intervention['urgency']} (low/medium/high/critical)")

    print()
    print("3. MESSAGE:")
    print(f"   {intervention['message']}")

    print()
    print("4. CURRENT STATE:")
    current = intervention['current_state']
    print(f"   Tool type: {current['tool_type']}")
    print(f"   Duration: {current['duration_seconds']:.2f}s")
    print(f"   Errors: {current['error_count']}")
    print(f"   Tool calls: {current['tools_used']}")

    print()
    print("5. RECOMMENDATION (if available):")
    if intervention['recommendation']:
        rec = intervention['recommendation']
        print(f"   Strategy: {rec['strategy']}")
        print(f"   Success rate: {rec['success_rate']:.1%}")
        print(f"   Expected duration: {rec['expected_duration']:.2f}s")
        print(f"   Confidence: {rec['confidence']:.3f}")
    else:
        print("   No proven strategies found")

    print()
    print("6. ALTERNATIVES:")
    if intervention['alternatives']:
        for i, alt in enumerate(intervention['alternatives'], 1):
            print(f"   {i}. {alt['tools']}")
    else:
        print("   None available")

    print()
    print("FULL INTERVENTION STRUCTURE:")
    print(json.dumps(intervention, indent=2, default=str))

print()
print()

# ============================================================================
# OUTPUT 5: System State
# ============================================================================
print("="*80)
print("OUTPUT 5: MetaRouter - get_state()")
print("="*80)
print()

state = meta_router.get_state()

print("Meta-Router state produces a dictionary with:")
print()
print("1. PROCESSING STATISTICS:")
print(f"   Traces processed: {state['traces_processed']}")
print(f"   Failures encoded: {state['failures_encoded']}")
print(f"   Successes encoded: {state['successes_encoded']}")

print()
print("2. THALAMO-HIPPOCAMPAL STATE:")
ths = state['thalamo_hippocampal_state']
print(f"   Hippocampal memories: {ths['hippocampal']['num_memories']}")
if 'dg_sparsity' in ths['hippocampal']:
    print(f"   DG sparsity: {ths['hippocampal']['dg_sparsity']:.3f}")
print(f"   Available keys: {list(ths['hippocampal'].keys())}")

print()
print("3. LEARNING METRICS:")
success_rate = state['successes_encoded'] / state['traces_processed'] if state['traces_processed'] > 0 else 0
memory_efficiency = state['failures_encoded'] / state['traces_processed'] if state['traces_processed'] > 0 else 0
print(f"   Success rate: {success_rate:.1%}")
print(f"   Memory efficiency: {memory_efficiency:.1%}")

print()
print()

# ============================================================================
# SUMMARY
# ============================================================================
print("="*80)
print("SUMMARY: BRAIN OUTPUT TYPES")
print("="*80)
print()
print("The brain produces 5 main output types:")
print()
print("[1] ROUTING OUTPUT (from MetaRouter.process_trace):")
print("    - Thalamic gates (which modalities are active)")
print("    - Latent states (internal representations)")
print("    - Prediction errors (novelty signals)")
print("    - Trace features (task details)")
print("    - Hippocampal status (memory encoding)")
print("    -> Used for: Understanding brain activity during task")
print()
print("[2] ACTIVATION SUMMARY (from BrainMonitor.get_activation_summary):")
print("    - Module activation levels (0-1 for each brain area)")
print("    - Alerts (warnings about problematic patterns)")
print("    - Statistics (gate strength, error rates)")
print("    -> Used for: Real-time monitoring and visualization")
print()
print("[3] STRATEGY RECOMMENDATION (from StrategyLibrary.get_recommendation):")
print("    - Recommended tool sequence")
print("    - Success rate and confidence")
print("    - Expected duration")
print("    - Alternative strategies")
print("    -> Used for: Suggesting proven approaches")
print()
print("[4] INTERVENTION (from LiveBrainMonitor.update):")
print("    - Reason for intervention")
print("    - Urgency level (critical/high/medium/low)")
print("    - Current state snapshot")
print("    - Recommended strategy")
print("    - Alternatives")
print("    -> Used for: Active failure prevention")
print()
print("[5] SYSTEM STATE (from MetaRouter.get_state):")
print("    - Processing statistics")
print("    - Memory counts")
print("    - Learning metrics")
print("    -> Used for: Monitoring system health and learning progress")
print()
print("="*80)
print("All outputs are Python dictionaries that can be:")
print("  - Serialized to JSON for logging")
print("  - Sent to web dashboards for visualization")
print("  - Used to trigger automated actions")
print("  - Saved to databases for analysis")
print("="*80)
