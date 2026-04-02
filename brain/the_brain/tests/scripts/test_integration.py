"""Test Token→Frequency Integration in Layer4TemporalRouter"""
import sys
sys.path.insert(0, '.')

from datetime import datetime
from core.layer4_temporal_router import Layer4TemporalRouter

print('=' * 70)
print('  TOKEN -> FREQUENCY INTEGRATION TEST')
print('=' * 70)

# Create router
router = Layer4TemporalRouter(
    strict_security=True,
    timing_threshold=0.5,
    enable_deep_reasoning=False  # Disable for testing
)

print('\n[Router initialized with Token->Frequency components]')
print(f'  - Oscillator: {router.oscillator}')
print(f'  - TokenAdapter: {router.token_adapter}')

# Test 1: Process tokens before routing
print('\n' + '=' * 70)
print('  TEST 1: Token Processing')
print('=' * 70)

sentence = "Deploy the container but not on port 8080"
tokens = sentence.split()
print(f'\nProcessing: "{sentence}"')
print('-' * 70)

# Process tokens
router.process_tokens(tokens)

# Check oscillator state
osc_state = router.get_oscillator_state()
print(f'\nOscillator State after token processing:')
print(f'  A (Advance): amplitude={osc_state.A.amplitude:.3f}, phase={osc_state.A.phase:.3f}')
print(f'  B (Explore): amplitude={osc_state.B.amplitude:.3f}, phase={osc_state.B.phase:.3f}')
print(f'  C (Correct): amplitude={osc_state.C.amplitude:.3f}, phase={osc_state.C.phase:.3f}')

dominant = router.get_dominant_channel()
print(f'\n  Dominant channel: {dominant.value}')

sync = router.get_synchrony_vector()
print(f'  Mean coherence: {sync.mean_coherence:.3f}')

# Test 2: Brain State with oscillator
print('\n' + '=' * 70)
print('  TEST 2: Brain State with Oscillator')
print('=' * 70)

from core.temporal_state_builder import TemporalBrainState

# Create brain state and inject oscillator
brain_state = TemporalBrainState()
brain_state.oscillator_state = router.get_oscillator_state()
brain_state.synchrony_vector = router.get_synchrony_vector()

print(f'\nBrain state has oscillator: {brain_state.has_oscillator}')

if brain_state.oscillator_state:
    print(f'  Oscillator in brain_state:')
    print(f'    A amplitude: {brain_state.oscillator_state.A.amplitude:.3f}')
    print(f'    B amplitude: {brain_state.oscillator_state.B.amplitude:.3f}')
    print(f'    C amplitude: {brain_state.oscillator_state.C.amplitude:.3f}')

# Convert to vector (base only, without oscillator extension)
base_vec = brain_state.to_vector(dim=192, include_oscillator=False)
print(f'\nBase state vector: shape={base_vec.shape}')

# Convert to vector with oscillator (192 + 9 = 201)
full_vec = brain_state.to_vector(dim=192, include_oscillator=True)
print(f'Full state vector (with synchrony): shape={full_vec.shape}')

# Convert to dict and check
state_dict = brain_state.to_dict()
if 'oscillator' in state_dict:
    print(f'\nOscillator in to_dict():')
    print(f'  {state_dict["oscillator"]}')

if 'synchrony' in state_dict:
    print(f'Synchrony in to_dict():')
    print(f'  {state_dict["synchrony"]}')

# Test 3: Statistics
print('\n' + '=' * 70)
print('  TEST 3: Statistics')
print('=' * 70)

stats = router.get_statistics()
print(f'\nToken Adapter Stats:')
print(f'  Tokens processed: {stats["token_adapter"]["tokens_processed"]}')
print(f'  Local hit rate: {stats["token_adapter"]["local_hit_rate"]:.1%}')

print('\n' + '=' * 70)
print('  INTEGRATION TEST PASSED!')
print('=' * 70)
