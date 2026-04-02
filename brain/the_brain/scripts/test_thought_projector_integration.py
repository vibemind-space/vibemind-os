"""
Test ThoughtProjector integration with HybridCTM.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import torch
from core.hybrid_ctm import HybridNeuroSymbolicCTM

def test_without_thought_projection():
    print("=" * 60)
    print("Testing WITHOUT thought projection")
    print("=" * 60)

    ctm = HybridNeuroSymbolicCTM(
        feature_dim=256,
        iterations=30,
        consciousness_threshold=0.85,
        enable_thought_projection=False
    )

    # Initialize lazy modules
    dummy = torch.randint(0, 11, (1, 5, 4))
    with torch.no_grad():
        _ = ctm(dummy, max_iterations=1)

    print(f"Parameters: {ctm.get_num_parameters():,}")

    board = torch.randint(0, 11, (2, 5, 4))
    with torch.no_grad():
        output = ctm(board, max_iterations=15)

    print(f"thought_vector: {output.thought_vector}")
    print(f"reasoning_steps: {output.reasoning_steps}")
    assert output.thought_vector is None, "thought_vector should be None when disabled"
    print("PASSED!")


def test_with_thought_projection():
    print("\n" + "=" * 60)
    print("Testing WITH thought projection")
    print("=" * 60)

    ctm = HybridNeuroSymbolicCTM(
        feature_dim=256,
        iterations=30,
        consciousness_threshold=0.85,
        enable_thought_projection=True,
        thought_dim=2048
    )

    # Initialize lazy modules
    dummy = torch.randint(0, 11, (1, 5, 4))
    with torch.no_grad():
        _ = ctm(dummy, max_iterations=1)

    print(f"Parameters: {ctm.get_num_parameters():,}")
    print("\nComponent breakdown:")
    for name, count in ctm.get_component_params().items():
        print(f"  {name}: {count:,}")

    board = torch.randint(0, 11, (2, 5, 4))
    with torch.no_grad():
        output = ctm(board, max_iterations=15)

    print(f"\nthought_vector shape: {output.thought_vector.shape}")
    print(f"thought_vector range: [{output.thought_vector.min():.3f}, {output.thought_vector.max():.3f}]")
    print(f"thought_vector mean: {output.thought_vector.mean():.3f}")
    print(f"thought_vector std: {output.thought_vector.std():.3f}")
    print(f"reasoning_steps: {output.reasoning_steps}")

    assert output.thought_vector is not None, "thought_vector should not be None"
    assert output.thought_vector.shape == (2, 2048), f"Expected (2, 2048), got {output.thought_vector.shape}"
    print("PASSED!")


def test_gradient_flow():
    print("\n" + "=" * 60)
    print("Testing gradient flow through ThoughtProjector")
    print("=" * 60)

    ctm = HybridNeuroSymbolicCTM(
        feature_dim=256,
        iterations=30,
        consciousness_threshold=0.85,
        enable_thought_projection=True,
        thought_dim=2048
    )

    # Initialize lazy modules
    dummy = torch.randint(0, 11, (1, 5, 4))
    with torch.no_grad():
        _ = ctm(dummy, max_iterations=1)

    # Test gradient flow
    board = torch.randint(0, 11, (2, 5, 4))
    output = ctm(board, max_iterations=10)

    # Loss on thought_vector
    loss = output.thought_vector.sum()
    loss.backward()

    # Check gradients flow to thought_projector
    has_grad = any(p.grad is not None for p in ctm.thought_projector.parameters())
    print(f"Gradient flows to thought_projector: {has_grad}")
    assert has_grad, "Gradients should flow to thought_projector"
    print("PASSED!")


if __name__ == "__main__":
    test_without_thought_projection()
    test_with_thought_projection()
    test_gradient_flow()

    print("\n" + "=" * 60)
    print("ALL INTEGRATION TESTS PASSED!")
    print("=" * 60)
