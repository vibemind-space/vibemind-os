"""Test Full Pipeline: Token -> Frequency -> CTM -> Drumpad"""
import sys
sys.path.insert(0, '.')

from datetime import datetime
from core.layer4_temporal_router import Layer4TemporalRouter
from core.temporal_state_builder import TemporalBrainState, StaticState, DynamicState, ToolState

print('=' * 70)
print('  FULL PIPELINE TEST: Token -> Frequency -> CTM -> Drumpad')
print('=' * 70)

# Create router
router = Layer4TemporalRouter(
    strict_security=True,
    timing_threshold=0.5,
    enable_deep_reasoning=False
)

print('\n[Router initialized]')
print(f'  - Oscillator: {router.oscillator}')
print(f'  - TokenAdapter: {router.token_adapter}')
print(f'  - TemporalCTM effective_state_dim: {router.temporal_ctm.effective_state_dim}')

# Test: Process tokens and run CTM
print('\n' + '=' * 70)
print('  TEST: Full CTM Processing with Extended State')
print('=' * 70)

sentence = "Deploy the container but not on port 8080"
tokens = sentence.split()
print(f'\nProcessing: "{sentence}"')

# Process tokens
router.process_tokens(tokens)

# Check oscillator state
osc_state = router.get_oscillator_state()
print(f'\nOscillator State:')
print(f'  A (Advance): {osc_state.A.amplitude:.3f}')
print(f'  B (Explore): {osc_state.B.amplitude:.3f}')
print(f'  C (Correct): {osc_state.C.amplitude:.3f}')
print(f'  Dominant: {router.get_dominant_channel().value}')

# Create brain state with oscillator
brain_state = TemporalBrainState(
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

# Inject oscillator state
brain_state.oscillator_state = router.get_oscillator_state()
brain_state.synchrony_vector = router.get_synchrony_vector()

print(f'\nBrain state with oscillator: {brain_state.has_oscillator}')

# Get vector dimensions
base_vec = brain_state.to_vector(dim=192, include_oscillator=False)
full_vec = brain_state.to_vector(dim=192, include_oscillator=True)
print(f'  Base vector: {base_vec.shape}')
print(f'  Extended vector: {full_vec.shape}')

# Run CTM processing
print('\n' + '-' * 70)
print('Running TemporalCTM.process()...')
print('-' * 70)

decision = router.temporal_ctm.process(brain_state, task_description="Deploy nginx container")

print(f'\nCTM Decision:')
print(f'  Cell ID: {decision.action.cell_id}')
print(f'  Semantic: {decision.action.semantic.value}')
print(f'  Should Act: {decision.should_act}')
print(f'  Timing Confidence: {decision.timing_confidence:.3f}')
print(f'  Hidden State Norm: {decision.hidden_state_norm:.3f}')

if decision.regime:
    print(f'  Regime: {decision.regime} (conf={decision.regime_confidence:.2f})')

# CTM Statistics
print('\n' + '-' * 70)
print('CTM Statistics:')
print('-' * 70)
ctm_stats = router.temporal_ctm.get_statistics()
print(f'  State dim: {ctm_stats["state_dim"]}')
print(f'  Effective state dim: {ctm_stats["effective_state_dim"]}')
print(f'  Oscillator extended: {ctm_stats["oscillator_extended"]}')
print(f'  Total decisions: {ctm_stats["total_decisions"]}')

print('\n' + '=' * 70)
print('  FULL PIPELINE TEST PASSED!')
print('=' * 70)
