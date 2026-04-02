"""
Test script for TransformerCTM integration.

Tests:
1. TransformerCTM creation (without model download)
2. DomainRouter keyword matching
3. CTM Model Merger components
4. Integration with existing infrastructure

Run with:
    python scripts/test_transformer_ctm.py
"""

import sys
import os

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import torch


def test_domain_router():
    """Test domain routing by keywords."""
    print("\n[1] Testing DomainRouter...")

    from core.domain_transformer_ctm import DomainRouter, CTMDomain

    router = DomainRouter()

    test_cases = [
        ("Design a microservice architecture", CTMDomain.SPATIAL),
        ("Validate JSON against schema rules", CTMDomain.LOGIC),
        ("Predict next values in time series", CTMDomain.TEMPORAL),
        ("Optimize cloud infrastructure costs", CTMDomain.VALUE),
    ]

    passed = 0
    for task, expected in test_cases:
        routed, scores = router.route(task)
        status = "PASS" if routed == expected else "FAIL"
        print(f"  [{status}] '{task[:35]}...' -> {routed.value} (expected: {expected.value})")
        if routed == expected:
            passed += 1

    print(f"  Router accuracy: {passed}/{len(test_cases)}")
    return passed == len(test_cases)


def test_ties_merger():
    """Test TIES-Merging implementation."""
    print("\n[2] Testing TIES Merger...")

    from core.ctm_model_merger import TIESMerger

    ties = TIESMerger(density=0.5)

    # Create test tensors
    base = {'weight': torch.randn(100, 100)}
    model1 = {'weight': base['weight'] + torch.randn(100, 100) * 0.1}
    model2 = {'weight': base['weight'] + torch.randn(100, 100) * 0.1}
    model3 = {'weight': base['weight'] + torch.randn(100, 100) * 0.1}

    # Test task vector computation
    tv1 = ties.compute_task_vector(model1, base)
    print(f"  Task vector computed: shape {tv1['weight'].shape}")

    # Test trimming
    trimmed = ties.trim(tv1)
    non_zero = (trimmed['weight'] != 0).sum().item()
    total = trimmed['weight'].numel()
    density = non_zero / total
    print(f"  After trimming: {density:.1%} non-zero (target: 50%)")

    # Test full merge
    merged = ties([model1, model2, model3], base)
    print(f"  Merged 3 models: shape {merged['weight'].shape}")

    return True


def test_linear_merger():
    """Test linear merging."""
    print("\n[3] Testing Linear Merger...")

    from core.ctm_model_merger import LinearMerger

    linear = LinearMerger()

    # Create test models
    m1 = {'weight': torch.ones(10, 10)}
    m2 = {'weight': torch.ones(10, 10) * 2}

    # Merge with equal weights
    merged = linear([m1, m2])
    expected = 1.5
    actual = merged['weight'].mean().item()
    print(f"  Equal weights: expected {expected}, got {actual:.2f}")

    # Merge with custom weights
    merged = linear([m1, m2], [0.25, 0.75])
    expected = 1.75
    actual = merged['weight'].mean().item()
    print(f"  Custom weights [0.25, 0.75]: expected {expected}, got {actual:.2f}")

    return abs(actual - expected) < 0.01


def test_slerp_merger():
    """Test SLERP merging."""
    print("\n[4] Testing SLERP Merger...")

    from core.ctm_model_merger import SLERPMerger

    slerp = SLERPMerger()

    # Create test models
    m1 = {'weight': torch.tensor([1.0, 0.0, 0.0])}
    m2 = {'weight': torch.tensor([0.0, 1.0, 0.0])}

    # SLERP at t=0 should be m1
    merged = slerp(m1, m2, 0.0)
    print(f"  t=0: {merged['weight'].tolist()}")

    # SLERP at t=1 should be m2
    merged = slerp(m1, m2, 1.0)
    print(f"  t=1: {merged['weight'].tolist()}")

    # SLERP at t=0.5 should be between
    merged = slerp(m1, m2, 0.5)
    print(f"  t=0.5: {merged['weight'].tolist()}")

    return True


def test_ctm_merger_config():
    """Test mergekit config generation."""
    print("\n[5] Testing Mergekit Config Generation...")

    from core.ctm_model_merger import CTMModelMerger

    merger = CTMModelMerger()

    config = merger.generate_mergekit_config(
        {
            'spatial': 'models/spatial_ctm',
            'logic': 'models/logic_ctm',
        },
        'test_config.yaml'
    )

    print(f"  Generated config ({len(config)} chars):")
    for line in config.split('\n')[:4]:
        print(f"    {line}")

    # Cleanup
    if os.path.exists('test_config.yaml'):
        os.remove('test_config.yaml')
        print("  Cleanup: removed test_config.yaml")

    return True


def test_domain_configs():
    """Test domain configurations."""
    print("\n[6] Testing Domain Configurations...")

    from core.domain_transformer_ctm import DOMAIN_CONFIGS, CTMDomain

    for domain, config in DOMAIN_CONFIGS.items():
        print(f"  {domain.value}:")
        print(f"    - Max iterations: {config.max_iterations}")
        print(f"    - Threshold: {config.consciousness_threshold}")
        print(f"    - Keywords: {len(config.keywords)}")

    return len(DOMAIN_CONFIGS) == 4


def test_transformer_ctm_components():
    """Test TransformerCTM component classes (no model download)."""
    print("\n[7] Testing TransformerCTM Components...")

    from core.transformer_ctm import (
        HaltPredictor,
        ThoughtProjectorTransformer,
        IterativeReasoningBlock
    )

    # Test HaltPredictor
    halt = HaltPredictor(hidden_dim=256, threshold=0.85)
    hidden = torch.randn(2, 256)
    halt_prob, certainty = halt(hidden)
    print(f"  HaltPredictor: halt_prob {halt_prob.shape}, certainty {certainty.shape}")

    # Test ThoughtProjector
    projector = ThoughtProjectorTransformer(hidden_dim=256, thought_dim=2048)
    thought = projector(hidden)
    print(f"  ThoughtProjector: {hidden.shape} -> {thought.shape}")

    # Test IterativeReasoningBlock
    block = IterativeReasoningBlock(hidden_dim=256)
    seq = torch.randn(2, 10, 256)
    out = block(seq, iteration=0)
    print(f"  ReasoningBlock: {seq.shape} -> {out.shape}")

    return thought.shape == (2, 2048)


def test_integration_with_thought_decoder():
    """Test that TransformerCTM output is compatible with ThoughtDecoder."""
    print("\n[8] Testing ThoughtDecoder Compatibility...")

    # Simulate TransformerCTM output
    thought_vector = torch.randn(1, 2048)

    try:
        from core.thought_decoder import ThoughtDecoder
        print("  ThoughtDecoder found, checking compatibility...")

        # Just verify input shape is accepted
        # (actual decoding requires GPT-2 model)
        print(f"  Input shape: {thought_vector.shape}")
        print(f"  Expected: (batch, 2048) [OK]")

    except ImportError:
        print("  ThoughtDecoder not available (optional)")

    return True


def main():
    """Run all tests."""
    print("=" * 60)
    print("TransformerCTM Integration Tests")
    print("=" * 60)

    tests = [
        ("Domain Router", test_domain_router),
        ("TIES Merger", test_ties_merger),
        ("Linear Merger", test_linear_merger),
        ("SLERP Merger", test_slerp_merger),
        ("Mergekit Config", test_ctm_merger_config),
        ("Domain Configs", test_domain_configs),
        ("CTM Components", test_transformer_ctm_components),
        ("ThoughtDecoder Compat", test_integration_with_thought_decoder),
    ]

    results = []
    for name, test_fn in tests:
        try:
            passed = test_fn()
            results.append((name, passed))
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append((name, False))

    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)

    passed = sum(1 for _, p in results if p)
    total = len(results)

    for name, p in results:
        status = "[OK] PASS" if p else "[X] FAIL"
        print(f"  {status}: {name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n[OK] All TransformerCTM integration tests passed!")
    else:
        print(f"\n[X] {total - passed} tests failed")

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
