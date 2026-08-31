"""
Test Context Alignment System

Validates the ContextAlignedState and SyntheticConversationGenerator.

Tests:
1. Context alignment calculation (0-1 scale)
2. Confidence adaptation (success/failure)
3. Checkpoint detection (tool calls)
4. Action hierarchy (tool > response > thinking)
5. Synthetic conversation generation

Author: Tahlamus Brain Team
Date: 2025-10-24
"""

import sys
sys.path.insert(0, '.')

from core.context_aligned_state import (
    ContextAlignedState,
    ActionMetadata,
    ContextDimensions
)
from learning_engine.synthetic_conversation_generator import (
    SyntheticConversationGenerator,
    save_conversations,
    load_conversations
)


def test_context_alignment():
    """Test context alignment calculation"""
    print("=" * 70)
    print("TEST 1: Context Alignment Calculation")
    print("=" * 70)

    # Create conversation history with varying context
    conversation = []

    # State 1: First state (no history)
    state1 = ContextAlignedState(
        state_id="state_1",
        step_count=0,
        state_summary="Read config file",
        last_action=ActionMetadata(
            action_type='tool_call',
            action_name='read_file',
            success=True,
            duration=0.5
        )
    )
    conversation.append(state1)

    # State 2: Similar action (high alignment expected)
    state2 = ContextAlignedState(
        state_id="state_2",
        step_count=1,
        state_summary="Write config file",
        last_action=ActionMetadata(
            action_type='tool_call',
            action_name='write_file',
            success=True,
            duration=1.0
        )
    )
    alignment2 = state2.calculate_context_alignment(conversation)
    conversation.append(state2)

    # State 3: Different action (lower alignment expected)
    state3 = ContextAlignedState(
        state_id="state_3",
        step_count=2,
        state_summary="Deploy application",
        last_action=ActionMetadata(
            action_type='tool_call',
            action_name='deploy',
            success=True,
            duration=5.0
        )
    )
    alignment3 = state3.calculate_context_alignment(conversation)
    conversation.append(state3)

    # State 4: Similar to state2 (high alignment expected)
    state4 = ContextAlignedState(
        state_id="state_4",
        step_count=3,
        state_summary="Edit config file",
        last_action=ActionMetadata(
            action_type='tool_call',
            action_name='edit_file',
            success=True,
            duration=1.5
        )
    )
    alignment4 = state4.calculate_context_alignment(conversation)

    print(f"\nState 1 (first state): No history")
    print(f"State 2 (similar to 1): Alignment = {alignment2:.3f} (expected: 0.3-0.6)")
    print(f"State 3 (different):    Alignment = {alignment3:.3f} (expected: 0.1-0.4)")
    print(f"State 4 (similar to 2): Alignment = {alignment4:.3f} (expected: 0.4-0.7)")

    # Verify alignment ranges
    assert 0.0 <= alignment2 <= 1.0, "Alignment out of range"
    assert 0.0 <= alignment3 <= 1.0, "Alignment out of range"
    assert 0.0 <= alignment4 <= 1.0, "Alignment out of range"
    assert alignment4 > alignment3, "Expected higher alignment for similar actions"

    print("\n[PASS] Context alignment test passed!\n")


def test_confidence_adaptation():
    """Test confidence adaptation based on success/failure"""
    print("=" * 70)
    print("TEST 2: Confidence Adaptation")
    print("=" * 70)

    state = ContextAlignedState(
        state_id="test_state",
        step_count=0,
        confidence_level=0.5  # Start at medium confidence
    )

    print(f"\nInitial confidence: {state.confidence_level:.3f}")
    print(f"Initial CTM thinking rate: {state.ctm_thinking_rate:.3f}")

    # Success → confidence increases
    state.adapt_confidence(success=True)
    print(f"\nAfter SUCCESS:")
    print(f"  Confidence: {state.confidence_level:.3f} (expected: ~0.55)")
    print(f"  CTM thinking rate: {state.ctm_thinking_rate:.3f} (expected: ~0.45)")

    # Another success
    state.adapt_confidence(success=True)
    print(f"\nAfter 2nd SUCCESS:")
    print(f"  Confidence: {state.confidence_level:.3f} (expected: ~0.60)")
    print(f"  CTM thinking rate: {state.ctm_thinking_rate:.3f} (expected: ~0.40)")

    # Failure → confidence decreases (more dramatic)
    state.adapt_confidence(success=False)
    print(f"\nAfter FAILURE:")
    print(f"  Confidence: {state.confidence_level:.3f} (expected: ~0.50)")
    print(f"  CTM thinking rate: {state.ctm_thinking_rate:.3f} (expected: ~0.50)")

    # Verify confidence stays in [0, 1]
    assert 0.0 <= state.confidence_level <= 1.0, "Confidence out of range"
    assert 0.0 <= state.ctm_thinking_rate <= 1.0, "CTM thinking rate out of range"

    print("\n[PASS] Confidence adaptation test passed!\n")


def test_checkpoint_detection():
    """Test checkpoint detection for successful tool calls"""
    print("=" * 70)
    print("TEST 3: Checkpoint Detection")
    print("=" * 70)

    # Tool call success → checkpoint
    state1 = ContextAlignedState(
        state_id="state_1",
        step_count=0,
        last_action=ActionMetadata(
            action_type='tool_call',
            action_name='write_file',
            success=True,
            duration=1.0
        )
    )
    state1.mark_as_checkpoint('tool_success', reliability_score=0.95)

    # Tool call failure → not checkpoint
    state2 = ContextAlignedState(
        state_id="state_2",
        step_count=1,
        last_action=ActionMetadata(
            action_type='tool_call',
            action_name='deploy',
            success=False,
            duration=5.0
        )
    )

    # Agent response → can be checkpoint (semantic progress)
    state3 = ContextAlignedState(
        state_id="state_3",
        step_count=2,
        last_action=ActionMetadata(
            action_type='agent_response',
            action_name='generate_response',
            success=True,
            duration=1.5
        )
    )
    state3.mark_as_checkpoint('semantic_progress', reliability_score=0.70)

    # Thinking → never checkpoint
    state4 = ContextAlignedState(
        state_id="state_4",
        step_count=3,
        last_action=ActionMetadata(
            action_type='thinking',
            action_name='evaluate_options',
            success=True,
            duration=0.5
        )
    )

    print(f"\nState 1 (tool success):    Checkpoint = {state1.is_checkpoint} [CHECKPOINT]")
    print(f"State 2 (tool failure):    Checkpoint = {state2.is_checkpoint} (expected: False)")
    print(f"State 3 (agent response):  Checkpoint = {state3.is_checkpoint} [CHECKPOINT]")
    print(f"State 4 (thinking):        Checkpoint = {state4.is_checkpoint} (expected: False)")

    assert state1.is_checkpoint, "Tool success should be checkpoint"
    assert not state2.is_checkpoint, "Tool failure should not be checkpoint"
    assert state3.is_checkpoint, "Semantic progress can be checkpoint"
    assert not state4.is_checkpoint, "Thinking should not be checkpoint"

    print("\n[PASS] Checkpoint detection test passed!\n")


def test_action_hierarchy():
    """Test action value hierarchy"""
    print("=" * 70)
    print("TEST 4: Action Hierarchy")
    print("=" * 70)

    tool_action = ActionMetadata(
        action_type='tool_call',
        action_name='write_file',
        success=True,
        duration=1.0
    )

    response_action = ActionMetadata(
        action_type='agent_response',
        action_name='generate_response',
        success=True,
        duration=1.5
    )

    thinking_action = ActionMetadata(
        action_type='thinking',
        action_name='evaluate_options',
        success=True,
        duration=0.5
    )

    waiting_action = ActionMetadata(
        action_type='waiting',
        action_name='wait_for_response',
        success=True,
        duration=2.0
    )

    print(f"\nAction Values:")
    print(f"  Tool call:      {tool_action.action_value:.2f} (expected: 1.00)")
    print(f"  Agent response: {response_action.action_value:.2f} (expected: 0.50)")
    print(f"  Thinking:       {thinking_action.action_value:.2f} (expected: 0.10)")
    print(f"  Waiting:        {waiting_action.action_value:.2f} (expected: 0.05)")

    assert tool_action.action_value == 1.0, "Tool call should have value 1.0"
    assert response_action.action_value == 0.5, "Agent response should have value 0.5"
    assert thinking_action.action_value == 0.1, "Thinking should have value 0.1"
    assert waiting_action.action_value == 0.05, "Waiting should have value 0.05"

    # Verify hierarchy
    assert tool_action.action_value > response_action.action_value
    assert response_action.action_value > thinking_action.action_value
    assert thinking_action.action_value > waiting_action.action_value

    print("\n[PASS] Action hierarchy test passed!\n")


def test_synthetic_generation():
    """Test synthetic conversation generation"""
    print("=" * 70)
    print("TEST 5: Synthetic Conversation Generation")
    print("=" * 70)

    generator = SyntheticConversationGenerator(seed=42)

    # Generate conversations with different context types
    print("\nGenerating conversations...")

    new_conv = generator.generate_conversation(
        task_description="Fix bug in authentication",
        target_steps=10,
        context_type='new',
        include_errors=True
    )

    familiar_conv = generator.generate_conversation(
        task_description="Deploy API endpoint",
        target_steps=10,
        context_type='familiar',
        include_errors=True
    )

    balanced_conv = generator.generate_conversation(
        task_description="Update configuration file",
        target_steps=10,
        context_type='balanced',
        include_errors=True
    )

    print(f"\nNew context conversation:")
    print(f"  Steps: {len(new_conv)}")
    print(f"  Checkpoints: {sum(1 for s in new_conv if s.is_checkpoint)}")
    print(f"  Context alignment (final): {new_conv[-1].context.overall_alignment:.3f}")
    print(f"  Expected: Low context (0.0-0.4)")

    print(f"\nFamiliar context conversation:")
    print(f"  Steps: {len(familiar_conv)}")
    print(f"  Checkpoints: {sum(1 for s in familiar_conv if s.is_checkpoint)}")
    print(f"  Context alignment (final): {familiar_conv[-1].context.overall_alignment:.3f}")
    print(f"  Expected: High context (0.6-1.0)")

    print(f"\nBalanced context conversation:")
    print(f"  Steps: {len(balanced_conv)}")
    print(f"  Checkpoints: {sum(1 for s in balanced_conv if s.is_checkpoint)}")
    print(f"  Context alignment (final): {balanced_conv[-1].context.overall_alignment:.3f}")
    print(f"  Expected: Medium context (0.3-0.7)")

    # Verify conversations have expected structure
    assert len(new_conv) > 0, "New conversation should have states"
    assert len(familiar_conv) > 0, "Familiar conversation should have states"
    assert len(balanced_conv) > 0, "Balanced conversation should have states"

    # Verify checkpoints exist
    assert sum(1 for s in new_conv if s.is_checkpoint) > 0, "Should have checkpoints"
    assert sum(1 for s in familiar_conv if s.is_checkpoint) > 0, "Should have checkpoints"
    assert sum(1 for s in balanced_conv if s.is_checkpoint) > 0, "Should have checkpoints"

    # Verify final state is goal
    assert new_conv[-1].is_goal, "Final state should be goal"
    assert familiar_conv[-1].is_goal, "Final state should be goal"
    assert balanced_conv[-1].is_goal, "Final state should be goal"

    print("\n[PASS] Synthetic generation test passed!\n")


def test_serialization():
    """Test state serialization to/from dict"""
    print("=" * 70)
    print("TEST 6: State Serialization")
    print("=" * 70)

    # Create state
    original = ContextAlignedState(
        state_id="test_state",
        step_count=5,
        state_summary="Test state",
        confidence_level=0.75,
        last_action=ActionMetadata(
            action_type='tool_call',
            action_name='write_file',
            success=True,
            duration=1.0
        )
    )
    original.mark_as_checkpoint('tool_success', reliability_score=0.90)

    # Serialize to dict
    state_dict = original.to_dict()

    # Deserialize from dict
    restored = ContextAlignedState.from_dict(state_dict)

    print(f"\nOriginal state:  {original}")
    print(f"Restored state:  {restored}")

    # Verify fields match
    assert restored.state_id == original.state_id
    assert restored.step_count == original.step_count
    assert restored.confidence_level == original.confidence_level
    assert restored.is_checkpoint == original.is_checkpoint
    assert restored.checkpoint_type == original.checkpoint_type

    print("\n[PASS] Serialization test passed!\n")


if __name__ == '__main__':
    print("\n" + "=" * 70)
    print("CONTEXT ALIGNMENT SYSTEM TEST SUITE")
    print("=" * 70 + "\n")

    try:
        test_context_alignment()
        test_confidence_adaptation()
        test_checkpoint_detection()
        test_action_hierarchy()
        test_synthetic_generation()
        test_serialization()

        print("=" * 70)
        print("ALL TESTS PASSED!")
        print("=" * 70 + "\n")

    except AssertionError as e:
        print(f"\n[FAILED] TEST FAILED: {e}\n")
        raise
    except Exception as e:
        print(f"\n[ERROR] ERROR: {e}\n")
        raise
