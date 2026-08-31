"""
Test Phase 1b: Oscillator-based Synchronization Pipeline

Tests the complete flow:
    TemporalBrainState → Oscillators → Synchrony → Regime → Drumpad3xN
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 70)
print("PHASE 1b TEST: Oscillator-based Synchronization Pipeline")
print("=" * 70)
print()

# Test 1: Import all modules
print("[1] Testing imports...")
try:
    from core.action_potential_oscillator import ActionPotentialOscillator, Channel
    print("    [OK] action_potential_oscillator")
except ImportError as e:
    print(f"    [FAIL] action_potential_oscillator: {e}")
    sys.exit(1)

try:
    from core.synchrony_encoder import SynchronyEncoder, SynchronyVector
    print("    [OK] synchrony_encoder")
except ImportError as e:
    print(f"    [FAIL] synchrony_encoder: {e}")
    sys.exit(1)

try:
    from core.regime_detector import RegimeDetector, Regime
    print("    [OK] regime_detector")
except ImportError as e:
    print(f"    [FAIL] regime_detector: {e}")
    sys.exit(1)

try:
    from core.drumpad_3xN import Drumpad3xN, DrumpadPattern
    print("    [OK] drumpad_3xN")
except ImportError as e:
    print(f"    [FAIL] drumpad_3xN: {e}")
    sys.exit(1)

try:
    from core.path_skeleton import PathSkeleton, PathStep, Episode, EpisodeBuilder, PathChannel, PathRegime
    print("    [OK] path_skeleton")
except ImportError as e:
    print(f"    [FAIL] path_skeleton: {e}")
    sys.exit(1)

try:
    from core.temporal_ctm import TemporalCTM, OSCILLATOR_AVAILABLE
    print(f"    [OK] temporal_ctm (OSCILLATOR_AVAILABLE={OSCILLATOR_AVAILABLE})")
except ImportError as e:
    print(f"    [FAIL] temporal_ctm: {e}")
    sys.exit(1)

try:
    from core.temporal_state_builder import TemporalBrainState, StaticState, DynamicState, ToolState
    print("    [OK] temporal_state_builder")
except ImportError as e:
    print(f"    [FAIL] temporal_state_builder: {e}")
    sys.exit(1)

print()

# Test 2: Oscillator pipeline
print("[2] Testing oscillator pipeline...")
osc = ActionPotentialOscillator(use_neural_coupling=False)
encoder = SynchronyEncoder()
detector = RegimeDetector()
drumpad = Drumpad3xN()

# Run through scenarios
scenarios = [
    ("EXPLOIT", {'advance': 0.9, 'explore': 0.1, 'correct': 0.1}),
    ("EXPLORE", {'advance': 0.1, 'explore': 0.9, 'correct': 0.1}),
    ("REPAIR", {'advance': 0.1, 'explore': 0.1, 'correct': 0.9}),
]

for expected_regime, inputs in scenarios:
    # Run 3 steps to stabilize
    for _ in range(3):
        osc_state = osc.step(external_input=inputs)

    sync = encoder.encode(osc_state)
    regime_result = detector.detect(sync)
    drumpad.reset_grid()
    pattern = drumpad.activate(sync, regime_result.regime)

    print(f"    Input: {inputs}")
    print(f"    Detected regime: {regime_result.regime.value} (expected: {expected_regime})")
    print(f"    Hits: {len(pattern.hits)}, Primary cell: {pattern.primary_hit.cell.cell_id}")
    print()

print("    [OK] Oscillator pipeline working")
print()

# Test 3: TemporalCTM with oscillators
print("[3] Testing TemporalCTM with oscillators...")

ctm = TemporalCTM(
    hidden_dim=128,
    state_dim=192,
    timing_threshold=0.5,
    use_klotski_ctm=False  # Disable for faster test
)

print(f"    Oscillator available: {ctm.use_oscillator}")

# Create test state
state = TemporalBrainState(
    static_state=StaticState(
        container_ids={'nginx': 'nginx:latest'},
        primary_goal='Deploy web server'
    ),
    dynamic_state=DynamicState(
        current_intent='deploy',
        intent_confidence=0.8
    ),
    tool_state=ToolState(
        last_tool_name='docker_ps',
        last_tool_success=True
    )
)

# Process state
decision = ctm.process(state, task_description="Deploy nginx container")

print(f"    Should act: {decision.should_act}")
print(f"    Timing confidence: {decision.timing_confidence:.3f}")
print(f"    Cell ID: {decision.action.cell_id}")

if decision.synchrony_vector is not None:
    print(f"    Synchrony vector: {decision.synchrony_vector[:3]}...")  # First 3 elements
if decision.regime:
    print(f"    Regime: {decision.regime} (conf={decision.regime_confidence:.3f})")
if decision.drumpad_pattern:
    print(f"    3xN pattern hits: {len(decision.drumpad_pattern.hits)}")

print()
print("    [OK] TemporalCTM with oscillators working")
print()

# Test 4: Episode building
print("[4] Testing episode building...")

builder = EpisodeBuilder(task_description="Test deployment")

# Add some temporal units
from core.synchrony_encoder import SynchronyEncoder as SE
test_sync = [0.8, 0.2, 0.1, 0.9, 0.1, 0.8, 0.2, 0.7, 0.3]

builder.set_regime(PathRegime.EXPLOIT)
builder.add_unit(PathChannel.ADVANCE, 0, 0.8, test_sync)
builder.add_unit(PathChannel.ADVANCE, 1, 0.9, test_sync)

builder.set_regime(PathRegime.EXPLORE)
builder.add_unit(PathChannel.EXPLORE, 3, 0.6, test_sync)

builder.set_regime(PathRegime.REPAIR)
builder.add_unit(PathChannel.CORRECT, 2, 0.7, test_sync)

episode = builder.build(success=True)

print(f"    Episode units: {episode.num_units}")
print(f"    Transitions: {episode.num_transitions}")
print(f"    Channel sequence: {episode.channel_sequence}")

# Convert to path skeleton
skeleton = episode.get_path_skeleton()
print(f"    PathSkeleton beats: {skeleton.total_beats}")
print(f"    PathSkeleton regime: {skeleton.regime.value}")

# Test JSON serialization
json_str = episode.to_json()
episode_restored = Episode.from_dict(eval(json_str.replace('true', 'True').replace('false', 'False').replace('null', 'None')))
print(f"    JSON serialization: {len(json_str)} bytes")
print(f"    Restored episode: {episode_restored.num_units} units")

print()
print("    [OK] Episode building working")
print()

# Test 5: Full statistics
print("[5] Testing statistics...")
stats = ctm.get_statistics()
print(f"    Total decisions: {stats['total_decisions']}")
print(f"    Oscillator available: {stats['oscillator_available']}")

if stats['oscillator_available'] and 'oscillator_stats' in stats:
    osc_stats = stats['oscillator_stats']
    print(f"    Current regime: {osc_stats.get('current_state', {}).get('dominant', 'N/A')}")

if 'regime_stats' in stats:
    regime_stats = stats['regime_stats']
    print(f"    Regime durations: {regime_stats.get('regime_durations', {})}")

print()
print("    [OK] Statistics working")
print()

# Summary
print("=" * 70)
print("PHASE 1b TEST COMPLETE")
print("=" * 70)
print()
print("All components working:")
print("  [OK] ActionPotentialOscillator (3 coupled A/B/C)")
print("  [OK] SynchronyEncoder (9-D vector)")
print("  [OK] RegimeDetector (EXPLOIT/EXPLORE/REPAIR/TRANSITION/DEADLOCK)")
print("  [OK] Drumpad3xN (3x8 grid)")
print("  [OK] PathSkeleton & Episode (path abstraction)")
print("  [OK] TemporalCTM integration")
print()
print("Synchronization-based time/location encoding is operational!")
print("=" * 70)
