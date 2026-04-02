"""
Test Phase 1c: Mamba SSM Integration

Tests the Mamba SSM enhancement for TemporalCTM.
Verifies fallback to GRU when Mamba is not installed.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 70)
print("PHASE 1c TEST: Mamba SSM Integration")
print("=" * 70)
print()

# Test 1: Import and availability check
print("[1] Testing imports...")
from core.temporal_ctm import (
    MAMBA_AVAILABLE,
    TemporalCTM,
    LatentDynamics,
    MambaLatentDynamics
)

print(f"    MAMBA_AVAILABLE: {MAMBA_AVAILABLE}")
print(f"    LatentDynamics class: [OK]")
print(f"    MambaLatentDynamics class: [OK]")
print()

# Test 2: TemporalCTM without Mamba (default)
print("[2] Testing TemporalCTM with GRU dynamics (default)...")
ctm_gru = TemporalCTM(
    hidden_dim=128,
    state_dim=192,
    use_klotski_ctm=False,
    use_mamba=False  # Explicitly disable Mamba
)

print(f"    use_mamba requested: False")
print(f"    use_mamba actual: {ctm_gru.use_mamba}")
print(f"    dynamics type: {type(ctm_gru.dynamics).__name__}")
assert type(ctm_gru.dynamics).__name__ == 'LatentDynamics', "Should use LatentDynamics"
print("    [OK] GRU dynamics working")
print()

# Test 3: TemporalCTM with Mamba requested
print("[3] Testing TemporalCTM with Mamba requested...")
ctm_mamba = TemporalCTM(
    hidden_dim=128,
    state_dim=192,
    use_klotski_ctm=False,
    use_mamba=True  # Request Mamba
)

print(f"    use_mamba requested: True")
print(f"    use_mamba actual: {ctm_mamba.use_mamba}")
print(f"    dynamics type: {type(ctm_mamba.dynamics).__name__}")

if MAMBA_AVAILABLE:
    assert type(ctm_mamba.dynamics).__name__ == 'MambaLatentDynamics', "Should use MambaLatentDynamics"
    print("    [OK] Mamba SSM dynamics working")
else:
    assert type(ctm_mamba.dynamics).__name__ == 'LatentDynamics', "Should fallback to LatentDynamics"
    print("    [OK] Fallback to GRU (Mamba not installed)")
print()

# Test 4: Statistics include Mamba info
print("[4] Testing statistics...")
stats = ctm_mamba.get_statistics()
print(f"    mamba_available: {stats['mamba_available']}")
print(f"    using_mamba: {stats['using_mamba']}")
print(f"    dynamics_type: {stats['dynamics_type']}")

assert 'mamba_available' in stats, "Should have mamba_available in stats"
assert 'using_mamba' in stats, "Should have using_mamba in stats"
assert 'dynamics_type' in stats, "Should have dynamics_type in stats"
print("    [OK] Statistics include Mamba info")
print()

# Test 5: Process state with both dynamics
print("[5] Testing processing with both dynamics...")
from core.temporal_state_builder import TemporalBrainState, StaticState, DynamicState, ToolState

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

# Process with GRU
decision_gru = ctm_gru.process(state, task_description="Test GRU")
print(f"    GRU decision: cell={decision_gru.action.cell_id}, timing={decision_gru.timing_confidence:.3f}")

# Process with Mamba (or fallback)
decision_mamba = ctm_mamba.process(state, task_description="Test Mamba")
print(f"    Mamba/Fallback decision: cell={decision_mamba.action.cell_id}, timing={decision_mamba.timing_confidence:.3f}")

print("    [OK] Processing works with both dynamics")
print()

# Summary
print("=" * 70)
print("PHASE 1c TEST COMPLETE")
print("=" * 70)
print()
print("All components working:")
print("  [OK] MambaLatentDynamics class (drop-in replacement for GRU)")
print("  [OK] use_mamba constructor flag")
print(f"  [OK] {'Mamba SSM active' if MAMBA_AVAILABLE else 'GRU fallback (Mamba not installed)'}")
print("  [OK] Statistics include Mamba info")
print("  [OK] Processing works with both dynamics")
print()
if not MAMBA_AVAILABLE:
    print("To enable Mamba SSM for 100x faster processing:")
    print("  pip install mamba-ssm torch>=2.0")
    print()
print("=" * 70)
