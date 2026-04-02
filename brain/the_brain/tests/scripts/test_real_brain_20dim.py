"""Test 20-dim fix with real neurosymbolic brain"""
import sys
sys.path.insert(0, 'learning_engine/klotski')

from core.neurosymbolic_heart_brain import NeuroSymbolicHeartSystem

print("=" * 80)
print("Testing 20-dim fix with REAL neurosymbolic brain")
print("=" * 80)

# Test with pretrained heart
print('\nLoading pretrained heart brain...')
wrapper = NeuroSymbolicHeartSystem(
    pretrained_path='data/test_neurosymbolic_brains/heart_pretrained.pth',
    device='cpu'
)

print(f'\n1. feature_dim: {wrapper.feature_dim}')
print(f'2. Using real brain: {wrapper.using_real_brain}')

# Test representation parsing
test_repr = 'jafi.aehddehbbcgbbc.'
print(f'\n3. Test representation: "{test_repr}"')

# Convert to features
feat = wrapper._state_to_features(test_repr)
print(f'4. Feature shape: {feat.shape}')
print(f'   Expected: torch.Size([1, 20])')

if feat.shape != (1, 20):
    print(f'   ERROR: Shape mismatch!')
    sys.exit(1)

# Test forward pass
print(f'\n5. Testing forward pass...')
try:
    if wrapper.using_real_brain:
        output = wrapper.brain(feat)
    else:
        # Fallback brain
        output = wrapper.brain(feat)

    print(f'   Output shape: {output.shape}')
    print(f'   Expected: torch.Size([1, 40])')

    if output.shape == (1, 40):
        print('\n' + '=' * 80)
        print('SUCCESS: Real brain forward pass works with 20-dim inputs!')
        print('=' * 80)
    else:
        print(f'\n   ERROR: Output shape mismatch!')
        sys.exit(1)

except Exception as e:
    print(f'\n   ERROR: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)
