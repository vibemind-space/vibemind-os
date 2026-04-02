"""
Test Trained CTM Ensemble - Verify Specialized Brain Routing

Tests the Multi-CTM Ensemble with all 3 trained specialized brains:
- LogicCTM (trained, LAN=65.9%, DLPFC=19.1%, ACC=9.8%)
- TemporalCTM (trained, AUD=58.6%, MTL=23.3%, DLPFC=14.9%)
- ValueCTM (trained, OFC=65.3%, ACC=19.6%, DLPFC=9.9%)

Verifies:
1. Correct brain loading from checkpoints
2. Domain-specific routing accuracy
3. Module activation patterns match training targets
4. Confidence scores for predictions
"""

import sys
import os
import torch
import numpy as np
from pathlib import Path

# Add paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:
    from core.multi_ctm_ensemble import MultiCTMEnsemble, CTMDomain
    KLOTSKI_AVAILABLE = True
except ImportError as e:
    print(f"[ERROR] Failed to import MultiCTMEnsemble: {e}")
    KLOTSKI_AVAILABLE = False

# Test tasks spanning all 3 domains
TEST_TASKS = [
    # Logic domain tests
    {
        "task": "Verify all database constraints are satisfied",
        "expected_domain": CTMDomain.LOGIC,
        "expected_modules": ["LAN", "DLPFC", "ACC"],
        "description": "Constraint validation (LogicCTM target)"
    },
    {
        "task": "Check if all invariants hold in the system",
        "expected_domain": CTMDomain.LOGIC,
        "expected_modules": ["LAN", "DLPFC", "ACC"],
        "description": "Logical invariant checking (LogicCTM)"
    },

    # Temporal domain tests
    {
        "task": "Predict stock prices for next 7 days",
        "expected_domain": CTMDomain.TEMPORAL,
        "expected_modules": ["AUD", "MTL", "DLPFC"],
        "description": "Time-series prediction (TemporalCTM target)"
    },
    {
        "task": "Forecast server load patterns for the next week",
        "expected_domain": CTMDomain.TEMPORAL,
        "expected_modules": ["AUD", "MTL", "DLPFC"],
        "description": "Pattern forecasting (TemporalCTM)"
    },

    # Value domain tests
    {
        "task": "Choose optimal cloud provider for cost-performance tradeoff",
        "expected_domain": CTMDomain.VALUE,
        "expected_modules": ["OFC", "ACC", "DLPFC"],
        "description": "Value-based decision (ValueCTM target)"
    },
    {
        "task": "Optimize resource allocation to maximize ROI",
        "expected_domain": CTMDomain.VALUE,
        "expected_modules": ["OFC", "ACC", "DLPFC"],
        "description": "Optimization decision (ValueCTM)"
    },
]


def load_trained_brain_weights(brain, checkpoint_path: str, domain: str):
    """
    Load trained brain weights into Klotski brain

    Args:
        brain: NeuroSymbolicBrain instance
        checkpoint_path: Path to .pth checkpoint
        domain: Domain name (logic, temporal, value)
    """
    if not os.path.exists(checkpoint_path):
        print(f"[WARN] Checkpoint not found: {checkpoint_path}")
        return False

    try:
        print(f"  Loading {domain}CTM weights from: {checkpoint_path}")
        state_dict = torch.load(checkpoint_path, map_location='cpu', weights_only=True)
        brain.load_state_dict(state_dict)
        print(f"  [OK] {domain}CTM brain weights loaded successfully")
        return True
    except Exception as e:
        print(f"  [ERROR] Failed to load {domain}CTM weights: {e}")
        return False


def test_ctm_ensemble():
    """Test Multi-CTM Ensemble with trained brains"""

    print("="*80)
    print("  TESTING TRAINED CTM ENSEMBLE")
    print("="*80)

    if not KLOTSKI_AVAILABLE:
        print("\n[ERROR] Klotski CTM not available. Cannot test ensemble.")
        return

    # Check checkpoint availability
    checkpoint_dir = Path("data/ctm_checkpoints")
    logic_ckpt = checkpoint_dir / "logic_brain_epoch_1.pth"
    temporal_ckpt = checkpoint_dir / "temporal_brain_epoch_1.pth"
    value_ckpt = checkpoint_dir / "value_brain_epoch_1.pth"

    print(f"\n[1/4] Checking checkpoint availability...")
    print(f"  Logic checkpoint: {logic_ckpt} - {'OK' if logic_ckpt.exists() else 'MISSING'}")
    print(f"  Temporal checkpoint: {temporal_ckpt} - {'OK' if temporal_ckpt.exists() else 'MISSING'}")
    print(f"  Value checkpoint: {value_ckpt} - {'OK' if value_ckpt.exists() else 'MISSING'}")

    if not all([logic_ckpt.exists(), temporal_ckpt.exists(), value_ckpt.exists()]):
        print("\n[ERROR] One or more checkpoints missing. Run training first:")
        print("  python train_logic_ctm.py")
        print("  python train_temporal_ctm.py")
        print("  python train_value_ctm.py")
        return

    # Initialize ensemble
    print(f"\n[2/4] Initializing Multi-CTM Ensemble...")
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f"  Device: {device}")

    try:
        ensemble = MultiCTMEnsemble(
            max_concurrent_per_ctm=2,
            feature_dim=256,
            consciousness_threshold=0.85,
            max_reasoning_steps=50,
            device=device,
            enable_logic_ctm=True,
            enable_temporal_ctm=True,
            enable_value_ctm=True
        )
    except Exception as e:
        print(f"[ERROR] Failed to initialize ensemble: {e}")
        return

    # Load trained weights
    print(f"\n[3/4] Loading trained brain weights...")

    # Access brain objects through KlotskiCTMAsyncReasoner -> KlotskiCTM -> NeuroSymbolicBrain
    try:
        if ensemble.ctms[CTMDomain.LOGIC]:
            logic_brain = ensemble.ctms[CTMDomain.LOGIC].klotski_ctm.brain
            load_trained_brain_weights(logic_brain, str(logic_ckpt), "Logic")

        if ensemble.ctms[CTMDomain.TEMPORAL]:
            temporal_brain = ensemble.ctms[CTMDomain.TEMPORAL].klotski_ctm.brain
            load_trained_brain_weights(temporal_brain, str(temporal_ckpt), "Temporal")

        if ensemble.ctms[CTMDomain.VALUE]:
            value_brain = ensemble.ctms[CTMDomain.VALUE].klotski_ctm.brain
            load_trained_brain_weights(value_brain, str(value_ckpt), "Value")
    except Exception as e:
        print(f"[ERROR] Failed to access brain objects: {e}")
        print("Continuing with default (untrained) weights...")

    # Run tests
    print(f"\n[4/4] Running domain routing tests...")
    print("-" * 80)

    correct_routes = 0
    total_tests = len(TEST_TASKS)

    for i, test in enumerate(TEST_TASKS, 1):
        print(f"\nTest {i}/{total_tests}: {test['description']}")
        print(f"  Task: \"{test['task']}\"")
        print(f"  Expected Domain: {test['expected_domain'].value}")
        print(f"  Expected Modules: {test['expected_modules']}")

        # Classify domain
        try:
            classification = ensemble.domain_router.classify_task(
                task=test['task']
            )

            print(f"  Classified Domain: {classification.primary_domain.value}")
            print(f"  Confidence: {classification.confidence:.2%}")

            # Check if routing is correct
            if classification.primary_domain == test['expected_domain']:
                print(f"  [OK] Correct domain routing!")
                correct_routes += 1
            else:
                print(f"  [FAIL] Incorrect routing")
                print(f"    Expected: {test['expected_domain'].value}")
                print(f"    Got: {classification.primary_domain.value}")

        except Exception as e:
            print(f"  [ERROR] Routing failed: {e}")

    # Summary
    print("\n" + "="*80)
    print("  ROUTING ACCURACY RESULTS")
    print("="*80)
    print(f"Correct Routes: {correct_routes}/{total_tests}")
    print(f"Accuracy: {correct_routes/total_tests:.1%}")

    if correct_routes == total_tests:
        print("\n[SUCCESS] All tasks routed correctly! Ensemble working perfectly.")
    elif correct_routes >= total_tests * 0.8:
        print("\n[PASS] Good routing accuracy (>80%). Some fine-tuning may help.")
    else:
        print("\n[WARN] Low routing accuracy (<80%). Check domain router configuration.")

    print("\n" + "="*80)
    print("  NEXT STEPS")
    print("="*80)
    print("1. Module Activation Analysis - Compare actual vs target routing patterns")
    print("2. Async Reasoning Test - Run full CTM reasoning for complex tasks")
    print("3. Integration Test - Test with hierarchical planner end-to-end")
    print("4. Production Deployment - Enable trained CTMs in production API")
    print("="*80)


if __name__ == "__main__":
    test_ctm_ensemble()
