"""
Test Adaptive CTM Hint Generator - Phase 3
Validates background thinking and proactive hints
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.adaptive_ctm_hint_generator import (
    AdaptiveCTMHintGenerator,
    CTMHint,
    HintType,
    ThinkingIntensity
)
from core.context_aligned_state import (
    ContextAlignedState,
    ActionMetadata,
    ContextDimensions
)
import time


def create_test_state(
    step: int,
    action_name: str,
    success: bool,
    confidence: float,
    progress: float,
    is_checkpoint: bool = False
) -> ContextAlignedState:
    """Create test state"""
    return ContextAlignedState(
        state_id=f"state_{step}",
        step_count=step,
        context=ContextDimensions(0.5, 0.5, 0.5, 0.5),
        confidence_level=confidence,
        ctm_thinking_rate=1.0 - confidence,
        last_action=ActionMetadata(
            action_type='tool_call',
            action_name=action_name,
            success=success,
            duration=1.0
        ),
        is_checkpoint=is_checkpoint,
        checkpoint_type='tool_success' if is_checkpoint else '',
        reliability_score=0.8 if success else 0.4,
        path_progress=progress,
        cumulative_time=step * 1.0
    )


def test_background_thinking():
    """Test 1: Background thinking thread"""
    print("\n" + "="*70)
    print("TEST 1: Background Thinking Thread")
    print("="*70)

    initial_state = create_test_state(
        step=0,
        action_name='start',
        success=True,
        confidence=0.3,  # Novice
        progress=0.0
    )

    generator = AdaptiveCTMHintGenerator(
        hint_cooldown_novice=0.5,  # Fast cooldown for testing
        thinking_interval=0.2,
        enable_proactive=True,
        seed=42
    )

    print("\nStarting background thinking...")
    generator.start_thinking(initial_state)

    print(f"Thinking state: {generator.thinking_state.is_thinking}")
    print(f"Intensity: {generator.thinking_state.intensity.value}")

    # Wait for hints to be generated
    print("\nWaiting 2 seconds for hints...")
    time.sleep(2.0)

    # Get generated hints
    hints = generator.get_all_hints()
    print(f"\nHints generated: {len(hints)}")

    for i, hint in enumerate(hints[:3]):  # Show first 3
        print(f"\nHint {i+1}:")
        print(f"  Type: {hint.hint_type.value}")
        print(f"  Confidence: {hint.confidence:.2f}")
        print(f"  Message: {hint.message}")
        if hint.suggested_action:
            print(f"  Suggested action: {hint.suggested_action}")

    generator.stop_thinking()
    print("\nBackground thinking stopped.")

    if len(hints) > 0:
        print("\n[PASS] Background thinking test passed!")
    else:
        print("\n[FAILED] No hints generated")

    return generator


def test_confidence_adaptation():
    """Test 2: Thinking intensity adapts to confidence"""
    print("\n" + "="*70)
    print("TEST 2: Confidence-Based Adaptation")
    print("="*70)

    generator = AdaptiveCTMHintGenerator(
        hint_cooldown_novice=0.5,
        hint_cooldown_intermediate=1.0,
        hint_cooldown_expert=2.0,
        enable_proactive=True,
        seed=42
    )

    # Test novice (confidence 0.2)
    novice_state = create_test_state(0, 'action', True, 0.2, 0.1)
    generator.start_thinking(novice_state)
    time.sleep(0.1)

    print(f"\nNovice (confidence=0.2):")
    print(f"  Intensity: {generator.thinking_state.intensity.value}")
    print(f"  Expected: intensive")
    assert generator.thinking_state.intensity == ThinkingIntensity.INTENSIVE

    # Update to intermediate
    intermediate_state = create_test_state(1, 'action', True, 0.5, 0.3)
    generator.update_state(intermediate_state)
    time.sleep(0.1)

    print(f"\nIntermediate (confidence=0.5):")
    print(f"  Intensity: {generator.thinking_state.intensity.value}")
    print(f"  Expected: moderate")
    assert generator.thinking_state.intensity == ThinkingIntensity.MODERATE

    # Update to expert
    expert_state = create_test_state(2, 'action', True, 0.8, 0.6)
    generator.update_state(expert_state)
    time.sleep(0.1)

    print(f"\nExpert (confidence=0.8):")
    print(f"  Intensity: {generator.thinking_state.intensity.value}")
    print(f"  Expected: minimal")
    assert generator.thinking_state.intensity == ThinkingIntensity.MINIMAL

    generator.stop_thinking()

    print("\n[PASS] Confidence adaptation test passed!")


def test_hint_cooldown():
    """Test 3: Hint cooldown based on confidence"""
    print("\n" + "="*70)
    print("TEST 3: Hint Cooldown System")
    print("="*70)

    generator = AdaptiveCTMHintGenerator(
        hint_cooldown_novice=0.5,
        hint_cooldown_intermediate=1.5,
        hint_cooldown_expert=3.0,
        seed=42
    )

    # Novice: should provide hint quickly
    novice_state = create_test_state(0, 'action', True, 0.2, 0.1)
    generator.thinking_state.last_hint_time = time.time()
    time.sleep(0.6)  # Wait > 0.5s
    should_hint_novice = generator.should_provide_hint(0.2)

    print(f"\nNovice (cooldown=0.5s, waited=0.6s):")
    print(f"  Should provide hint: {should_hint_novice}")
    print(f"  Expected: True")
    assert should_hint_novice == True

    # Expert: should not provide hint yet
    expert_state = create_test_state(1, 'action', True, 0.8, 0.3)
    generator.thinking_state.last_hint_time = time.time()
    time.sleep(1.0)  # Wait < 3.0s
    should_hint_expert = generator.should_provide_hint(0.8)

    print(f"\nExpert (cooldown=3.0s, waited=1.0s):")
    print(f"  Should provide hint: {should_hint_expert}")
    print(f"  Expected: False")
    assert should_hint_expert == False

    print("\n[PASS] Hint cooldown test passed!")


def test_stuck_detection():
    """Test 4: Stuck-in-loop detection"""
    print("\n" + "="*70)
    print("TEST 4: Stuck-in-Loop Detection")
    print("="*70)

    generator = AdaptiveCTMHintGenerator(
        hint_cooldown_novice=0.1,
        enable_proactive=False,  # Test on-demand hints
        seed=42
    )

    # Create repetitive history (stuck in loop)
    history = [
        create_test_state(i, 'same_action', True, 0.5, 0.1 + i*0.01)
        for i in range(5)
    ]

    current_state = create_test_state(5, 'same_action', True, 0.5, 0.15)

    # Generate hint
    hint = generator._generate_hint(current_state, history)

    print(f"\nRepetitive pattern detected:")
    print(f"  Hint type: {hint.hint_type.value if hint else 'None'}")
    print(f"  Expected: stuck_detection")

    if hint and hint.hint_type == HintType.STUCK_DETECTION:
        print(f"  Message: {hint.message}")
        print(f"  Confidence: {hint.confidence:.2f}")
        print("\n[PASS] Stuck detection test passed!")
    else:
        print("\n[FAILED] Did not detect stuck pattern")


def test_hint_types():
    """Test 5: Different hint types generation"""
    print("\n" + "="*70)
    print("TEST 5: Hint Type Generation")
    print("="*70)

    generator = AdaptiveCTMHintGenerator(seed=42)

    # Test checkpoint ahead detection
    state_near_checkpoint = create_test_state(
        5, 'action', True, 0.6, 0.75  # High progress
    )
    hint1 = generator._generate_hint(state_near_checkpoint, [])

    print(f"\nNear checkpoint (progress=0.75):")
    print(f"  Hint type: {hint1.hint_type.value if hint1 else 'None'}")
    print(f"  Expected: checkpoint_ahead")

    # Test confidence boost after checkpoint
    state_checkpoint_reached = create_test_state(
        6, 'action', True, 0.6, 0.8, is_checkpoint=True
    )
    hint2 = generator._generate_hint(state_checkpoint_reached, [])

    print(f"\nCheckpoint reached:")
    print(f"  Hint type: {hint2.hint_type.value if hint2 else 'None'}")
    print(f"  Expected: confidence_boost")

    # Test next action suggestion for novice
    novice_state = create_test_state(
        1, 'start', True, 0.3, 0.1
    )
    history_with_successes = [
        create_test_state(0, 'read_file', True, 0.4, 0.05, is_checkpoint=True)
    ]
    hint3 = generator._generate_hint(novice_state, history_with_successes)

    print(f"\nNovice needs guidance:")
    print(f"  Hint type: {hint3.hint_type.value if hint3 else 'None'}")
    print(f"  Expected: next_action")
    if hint3:
        print(f"  Suggested: {hint3.suggested_action}")

    hints_generated = sum(1 for h in [hint1, hint2, hint3] if h is not None)
    print(f"\nTotal hints generated: {hints_generated}/3")

    if hints_generated >= 2:
        print("\n[PASS] Hint type generation test passed!")
    else:
        print("\n[FAILED] Not enough hints generated")


def test_on_demand_hints():
    """Test 6: On-demand hint generation"""
    print("\n" + "="*70)
    print("TEST 6: On-Demand Hint Generation")
    print("="*70)

    generator = AdaptiveCTMHintGenerator(
        enable_proactive=False,  # Disable proactive hints
        seed=42
    )

    state = create_test_state(3, 'action', True, 0.5, 0.3)
    history = [
        create_test_state(i, 'action', True, 0.5, i*0.1)
        for i in range(3)
    ]

    generator.start_thinking(state, history)

    # Queue should remain empty (no proactive hints)
    time.sleep(1.0)
    proactive_hints = generator.get_all_hints()

    print(f"\nProactive hints (disabled): {len(proactive_hints)}")
    print(f"  Expected: 0")

    # Request on-demand hint
    print("\nRequesting on-demand hint...")
    on_demand_hint = generator.get_hint(timeout=0.1, force_generate=True)

    print(f"  Hint received: {on_demand_hint is not None}")
    if on_demand_hint:
        print(f"  Type: {on_demand_hint.hint_type.value}")
        print(f"  Message: {on_demand_hint.message}")

    generator.stop_thinking()

    if len(proactive_hints) == 0 and on_demand_hint is not None:
        print("\n[PASS] On-demand hint test passed!")
    else:
        print("\n[FAILED] Expected no proactive hints but on-demand hint")


def test_statistics():
    """Test 7: Statistics tracking"""
    print("\n" + "="*70)
    print("TEST 7: Statistics Tracking")
    print("="*70)

    generator = AdaptiveCTMHintGenerator(
        hint_cooldown_novice=0.2,
        thinking_interval=0.1,
        enable_proactive=True,
        seed=42
    )

    state = create_test_state(0, 'action', True, 0.3, 0.1)
    generator.start_thinking(state)

    time.sleep(1.5)

    hints = generator.get_all_hints()

    # Mark some as accepted
    for i, hint in enumerate(hints[:min(2, len(hints))]):
        generator.mark_hint_outcome(hint, accepted=(i % 2 == 0))

    generator.stop_thinking()

    stats = generator.get_statistics()

    print(f"\nStatistics:")
    print(f"  Total thinking time: {stats['total_thinking_time']:.3f}s")
    print(f"  Hints generated: {stats['total_hints_generated']}")
    print(f"  Hints accepted: {stats['hints_accepted']}")
    print(f"  Hints rejected: {stats['hints_rejected']}")
    print(f"  Acceptance rate: {stats['acceptance_rate']:.1%}")
    print(f"  Current intensity: {stats['current_intensity']}")

    print(f"\nHints by type:")
    for hint_type, count in stats['hints_by_type'].items():
        if count > 0:
            print(f"  {hint_type}: {count}")

    if stats['total_hints_generated'] > 0:
        print("\n[PASS] Statistics tracking test passed!")
    else:
        print("\n[FAILED] No statistics collected")


def main():
    print("="*70)
    print("ADAPTIVE CTM HINT GENERATOR TEST SUITE")
    print("="*70)

    # Run tests
    test_background_thinking()
    test_confidence_adaptation()
    test_hint_cooldown()
    test_stuck_detection()
    test_hint_types()
    test_on_demand_hints()
    test_statistics()

    print("\n" + "="*70)
    print("ALL TESTS COMPLETED")
    print("="*70)


if __name__ == '__main__':
    main()
