"""
Quick test: Verify 20-dim board input fix

Tests that neurosymbolic_heart_brain now correctly converts representation
strings to 20-dim board tensors instead of 256-dim hash embeddings.
"""

import torch
import numpy as np

# Test without actual brain (mock fallback)
from core.neurosymbolic_heart_brain import NeuroSymbolicHeartSystem

def test_20dim_conversion():
    print("=" * 80)
    print("TEST: 20-dim Board Input Fix")
    print("=" * 80)

    # Initialize wrapper (should now use feature_dim=20)
    wrapper = NeuroSymbolicHeartSystem(
        pretrained_path=None,  # Use fallback brain
        device='cpu'
    )

    print(f"\n1. Wrapper feature_dim: {wrapper.feature_dim}")
    assert wrapper.feature_dim == 20, f"Expected feature_dim=20, got {wrapper.feature_dim}"
    print("   ✅ PASS: feature_dim is 20")

    # Test representation string parsing
    test_repr = "jafi.aehddehbbcgbbc."
    print(f"\n2. Test representation: '{test_repr}'")

    # Parse to board
    board = wrapper._parse_representation_to_board(test_repr)
    print(f"   Parsed board shape: {board.shape}")
    print(f"   Parsed board dtype: {board.dtype}")
    print(f"   Parsed board range: [{board.min():.3f}, {board.max():.3f}]")
    assert board.shape == (20,), f"Expected shape (20,), got {board.shape}"
    assert board.dtype == np.float32, f"Expected float32, got {board.dtype}"
    print("   ✅ PASS: Board shape and dtype correct")

    # Test _state_to_features
    features = wrapper._state_to_features(test_repr)
    print(f"\n3. Feature tensor shape: {features.shape}")
    print(f"   Feature tensor dtype: {features.dtype}")
    print(f"   Feature tensor device: {features.device}")
    assert features.shape == (1, 20), f"Expected shape (1, 20), got {features.shape}"
    print("   ✅ PASS: Feature tensor has correct shape (1, 20)")

    # Verify normalized values
    print(f"\n4. Sample feature values (first 10): {features[0, :10].tolist()}")
    assert features.max() <= 1.0, "Features should be normalized to [0, 1]"
    assert features.min() >= 0.0, "Features should be normalized to [0, 1]"
    print("   ✅ PASS: Features normalized to [0, 1]")

    # Test forward pass with fallback brain
    print(f"\n5. Testing forward pass with fallback brain...")
    try:
        output = wrapper.brain(features)
        print(f"   Output shape: {output.shape}")
        assert output.shape == (1, 40), f"Expected output shape (1, 40), got {output.shape}"
        print("   ✅ PASS: Forward pass successful!")
    except Exception as e:
        print(f"   ❌ FAIL: Forward pass error: {e}")
        raise

    print("\n" + "=" * 80)
    print("ALL TESTS PASSED! ✅")
    print("=" * 80)
    print("\nSummary:")
    print("- feature_dim correctly set to 20")
    print("- Representation strings parsed to 20-dim boards")
    print("- Feature tensors have shape (1, 20)")
    print("- Forward pass successful (no shape mismatch)")
    print("\nThe fix resolves the RuntimeError: mat1 and mat2 shapes cannot be multiplied")
    print("=" * 80)

if __name__ == '__main__':
    test_20dim_conversion()
