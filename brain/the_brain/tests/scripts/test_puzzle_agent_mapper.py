"""
Test Puzzle-Agent Mapper - Phase 4
Validates puzzle-to-agent and agent-to-puzzle mappings
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.puzzle_agent_mapper import (
    PuzzleAgentMapper,
    PuzzleMove,
    AgentAction,
    PuzzleActionType,
    AgentActionType
)
from core.context_aligned_state import (
    ContextAlignedState,
    ActionMetadata,
    ContextDimensions
)


def test_puzzle_to_agent_mapping():
    """Test 1: Puzzle to agent mapping"""
    print("\n" + "="*70)
    print("TEST 1: Puzzle to Agent Mapping")
    print("="*70)

    mapper = PuzzleAgentMapper()

    # Test 1a: Successful move → Tool call
    puzzle_move1 = PuzzleMove(
        action_type=PuzzleActionType.MOVE_PIECE,
        piece_id="block_A",
        direction="right",
        success=True,
        creates_checkpoint=True,
        cost=1.5
    )

    agent_action1 = mapper.puzzle_to_agent(puzzle_move1)

    print("\nTest 1a: Successful piece move")
    print(f"  Puzzle: {puzzle_move1.action_type.value} (success={puzzle_move1.success})")
    print(f"  Agent: {agent_action1.action_type.value} ({agent_action1.action_name})")
    print(f"  Checkpoint: {agent_action1.creates_checkpoint}")
    print(f"  Expected: tool_call with checkpoint")

    assert agent_action1.action_type == AgentActionType.TOOL_CALL
    assert agent_action1.creates_checkpoint == True

    # Test 1b: Failed move → Retry
    puzzle_move2 = PuzzleMove(
        action_type=PuzzleActionType.MOVE_PIECE,
        piece_id="block_B",
        success=False,
        creates_checkpoint=False,
        cost=1.0
    )

    agent_action2 = mapper.puzzle_to_agent(puzzle_move2)

    print("\nTest 1b: Failed piece move")
    print(f"  Puzzle: {puzzle_move2.action_type.value} (success={puzzle_move2.success})")
    print(f"  Agent: {agent_action2.action_type.value}")
    print(f"  Expected: retry")

    assert agent_action2.action_type == AgentActionType.RETRY

    # Test 1c: Analyze board → Thinking
    puzzle_move3 = PuzzleMove(
        action_type=PuzzleActionType.ANALYZE_BOARD,
        success=True,
        cost=0.5
    )

    agent_action3 = mapper.puzzle_to_agent(puzzle_move3)

    print("\nTest 1c: Analyze board")
    print(f"  Puzzle: {puzzle_move3.action_type.value}")
    print(f"  Agent: {agent_action3.action_type.value}")
    print(f"  Expected: thinking")

    assert agent_action3.action_type == AgentActionType.THINKING

    print("\n[PASS] Puzzle to agent mapping test passed!")


def test_agent_to_puzzle_mapping():
    """Test 2: Agent to puzzle mapping (reverse)"""
    print("\n" + "="*70)
    print("TEST 2: Agent to Puzzle Mapping (Reverse)")
    print("="*70)

    mapper = PuzzleAgentMapper()

    # Test 2a: Tool call → Move piece
    agent_action1 = AgentAction(
        action_type=AgentActionType.TOOL_CALL,
        action_name="read_file",
        success=True,
        creates_checkpoint=True,
        cost=1.0
    )

    puzzle_move1 = mapper.agent_to_puzzle(agent_action1)

    print("\nTest 2a: Tool call")
    print(f"  Agent: {agent_action1.action_type.value} ({agent_action1.action_name})")
    print(f"  Puzzle: {puzzle_move1.action_type.value}")
    print(f"  Expected: move_piece")

    assert puzzle_move1.action_type == PuzzleActionType.MOVE_PIECE
    assert puzzle_move1.creates_checkpoint == True

    # Test 2b: Retry → Undo move
    agent_action2 = AgentAction(
        action_type=AgentActionType.RETRY,
        action_name="retry_write",
        success=True,
        cost=1.5
    )

    puzzle_move2 = mapper.agent_to_puzzle(agent_action2)

    print("\nTest 2b: Retry action")
    print(f"  Agent: {agent_action2.action_type.value}")
    print(f"  Puzzle: {puzzle_move2.action_type.value}")
    print(f"  Expected: undo_move")

    assert puzzle_move2.action_type == PuzzleActionType.UNDO_MOVE

    # Test 2c: Validation → Check goal
    agent_action3 = AgentAction(
        action_type=AgentActionType.VALIDATION,
        action_name="verify_output",
        success=True,
        cost=0.8
    )

    puzzle_move3 = mapper.agent_to_puzzle(agent_action3)

    print("\nTest 2c: Validation")
    print(f"  Agent: {agent_action3.action_type.value}")
    print(f"  Puzzle: {puzzle_move3.action_type.value}")
    print(f"  Expected: check_goal")

    assert puzzle_move3.action_type == PuzzleActionType.CHECK_GOAL

    print("\n[PASS] Agent to puzzle mapping test passed!")


def test_conversation_to_puzzle_path():
    """Test 3: Map entire conversation to puzzle path"""
    print("\n" + "="*70)
    print("TEST 3: Conversation to Puzzle Path")
    print("="*70)

    mapper = PuzzleAgentMapper()

    # Create test conversation
    conversation = [
        ContextAlignedState(
            state_id="state_0",
            step_count=0,
            context=ContextDimensions(0.5, 0.5, 0.5, 0.0),
            confidence_level=0.5,
            ctm_thinking_rate=0.5,
            last_action=ActionMetadata(
                action_type='tool_call',
                action_name='read_file',
                success=True,
                duration=1.0
            ),
            is_checkpoint=True,
            checkpoint_type='tool_success',
            reliability_score=0.8,
            path_progress=0.2,
            cumulative_time=1.0
        ),
        ContextAlignedState(
            state_id="state_1",
            step_count=1,
            context=ContextDimensions(0.6, 0.5, 0.6, 0.1),
            confidence_level=0.55,
            ctm_thinking_rate=0.45,
            last_action=ActionMetadata(
                action_type='thinking',
                action_name='analyze',
                success=True,
                duration=0.5
            ),
            is_checkpoint=False,
            reliability_score=0.6,
            path_progress=0.3,
            cumulative_time=1.5
        ),
        ContextAlignedState(
            state_id="state_2",
            step_count=2,
            context=ContextDimensions(0.7, 0.5, 0.7, 0.2),
            confidence_level=0.6,
            ctm_thinking_rate=0.4,
            last_action=ActionMetadata(
                action_type='tool_call',
                action_name='write_file',
                success=True,
                duration=1.2
            ),
            is_checkpoint=True,
            checkpoint_type='tool_success',
            reliability_score=0.85,
            path_progress=0.6,
            cumulative_time=2.7
        )
    ]

    # Map to puzzle path
    puzzle_path = mapper.map_conversation_to_puzzle_path(conversation)

    print(f"\nConversation states: {len(conversation)}")
    print(f"Puzzle moves: {len(puzzle_path)}")
    print(f"Expected: {len(conversation)} moves")

    print(f"\nPuzzle path:")
    for i, move in enumerate(puzzle_path):
        checkpoint = "[CHECKPOINT]" if move.creates_checkpoint else ""
        print(f"  Move {i+1}: {move.action_type.value} (success={move.success}) {checkpoint}")

    # Verify checkpoints preserved
    conversation_checkpoints = sum(1 for s in conversation if s.is_checkpoint)
    puzzle_checkpoints = sum(1 for m in puzzle_path if m.creates_checkpoint)

    print(f"\nCheckpoints preserved:")
    print(f"  Conversation: {conversation_checkpoints}")
    print(f"  Puzzle: {puzzle_checkpoints}")
    print(f"  Match: {conversation_checkpoints == puzzle_checkpoints}")

    assert len(puzzle_path) == len(conversation)
    assert puzzle_checkpoints == conversation_checkpoints

    print("\n[PASS] Conversation to puzzle path test passed!")


def test_puzzle_path_to_conversation():
    """Test 4: Map puzzle path to conversation"""
    print("\n" + "="*70)
    print("TEST 4: Puzzle Path to Conversation")
    print("="*70)

    mapper = PuzzleAgentMapper()

    # Create test puzzle path
    puzzle_path = [
        PuzzleMove(
            action_type=PuzzleActionType.MOVE_PIECE,
            piece_id="block_A",
            success=True,
            creates_checkpoint=True,
            cost=1.0
        ),
        PuzzleMove(
            action_type=PuzzleActionType.ANALYZE_BOARD,
            success=True,
            creates_checkpoint=False,
            cost=0.5
        ),
        PuzzleMove(
            action_type=PuzzleActionType.MOVE_PIECE,
            piece_id="block_B",
            success=True,
            creates_checkpoint=True,
            cost=1.2
        ),
        PuzzleMove(
            action_type=PuzzleActionType.CHECK_GOAL,
            success=True,
            creates_checkpoint=False,
            cost=0.3
        )
    ]

    # Create initial state
    initial_state = ContextAlignedState(
        state_id="state_0",
        step_count=0,
        context=ContextDimensions(0.4, 0.4, 0.4, 0.0),
        confidence_level=0.5,
        ctm_thinking_rate=0.5,
        path_progress=0.0,
        cumulative_time=0.0
    )

    # Map to conversation
    conversation = mapper.map_puzzle_path_to_conversation(puzzle_path, initial_state)

    print(f"\nPuzzle moves: {len(puzzle_path)}")
    print(f"Conversation states: {len(conversation)}")
    print(f"Expected: {len(puzzle_path) + 1} states (including initial)")

    print(f"\nConversation:")
    for i, state in enumerate(conversation):
        action_desc = f"{state.last_action.action_type} - {state.last_action.action_name}" if state.last_action else "initial"
        checkpoint = "[CHECKPOINT]" if state.is_checkpoint else ""
        print(f"  State {i}: {action_desc} {checkpoint}")

    # Verify checkpoints
    puzzle_checkpoints = sum(1 for m in puzzle_path if m.creates_checkpoint)
    conversation_checkpoints = sum(1 for s in conversation if s.is_checkpoint)

    print(f"\nCheckpoints:")
    print(f"  Puzzle: {puzzle_checkpoints}")
    print(f"  Conversation: {conversation_checkpoints}")
    print(f"  Match: {puzzle_checkpoints == conversation_checkpoints}")

    assert len(conversation) == len(puzzle_path) + 1  # +1 for initial state
    assert conversation_checkpoints == puzzle_checkpoints

    print("\n[PASS] Puzzle path to conversation test passed!")


def test_bidirectional_mapping():
    """Test 5: Bidirectional mapping consistency"""
    print("\n" + "="*70)
    print("TEST 5: Bidirectional Mapping Consistency")
    print("="*70)

    mapper = PuzzleAgentMapper()

    # Original puzzle move
    original_puzzle = PuzzleMove(
        action_type=PuzzleActionType.MOVE_PIECE,
        piece_id="block_X",
        success=True,
        creates_checkpoint=True,
        cost=1.5
    )

    # Forward: Puzzle → Agent
    agent_action = mapper.puzzle_to_agent(original_puzzle)

    # Reverse: Agent → Puzzle
    reconstructed_puzzle = mapper.agent_to_puzzle(agent_action)

    print("\nOriginal puzzle move:")
    print(f"  Type: {original_puzzle.action_type.value}")
    print(f"  Success: {original_puzzle.success}")
    print(f"  Checkpoint: {original_puzzle.creates_checkpoint}")

    print("\nIntermediate agent action:")
    print(f"  Type: {agent_action.action_type.value}")
    print(f"  Name: {agent_action.action_name}")
    print(f"  Checkpoint: {agent_action.creates_checkpoint}")

    print("\nReconstructed puzzle move:")
    print(f"  Type: {reconstructed_puzzle.action_type.value}")
    print(f"  Success: {reconstructed_puzzle.success}")
    print(f"  Checkpoint: {reconstructed_puzzle.creates_checkpoint}")

    # Check consistency (types should match)
    print(f"\nConsistency check:")
    print(f"  Action types match: {original_puzzle.action_type == reconstructed_puzzle.action_type}")
    print(f"  Success match: {original_puzzle.success == reconstructed_puzzle.success}")
    print(f"  Checkpoint match: {original_puzzle.creates_checkpoint == reconstructed_puzzle.creates_checkpoint}")

    assert original_puzzle.action_type == reconstructed_puzzle.action_type
    assert original_puzzle.success == reconstructed_puzzle.success
    assert original_puzzle.creates_checkpoint == reconstructed_puzzle.creates_checkpoint

    print("\n[PASS] Bidirectional mapping test passed!")


def test_action_taxonomy():
    """Test 6: Action taxonomy verification"""
    print("\n" + "="*70)
    print("TEST 6: Action Taxonomy Verification")
    print("="*70)

    mapper = PuzzleAgentMapper()

    print(f"\nAction taxonomy categories:")
    for action_type, categories in mapper.action_taxonomy.items():
        print(f"\n  {action_type}:")
        for category, actions in categories.items():
            print(f"    {category}: {len(actions)} actions")
            print(f"      Examples: {', '.join(actions[:3])}")

    # Count total actions
    total_actions = sum(
        len(actions)
        for categories in mapper.action_taxonomy.values()
        for actions in categories.values()
    )

    print(f"\nTotal actions in taxonomy: {total_actions}")
    print(f"Expected: > 20 actions")

    assert total_actions > 20

    print("\n[PASS] Action taxonomy test passed!")


def test_statistics():
    """Test 7: Statistics tracking"""
    print("\n" + "="*70)
    print("TEST 7: Statistics Tracking")
    print("="*70)

    mapper = PuzzleAgentMapper()

    # Perform several mappings
    moves = [
        PuzzleMove(PuzzleActionType.MOVE_PIECE, success=True, creates_checkpoint=True),
        PuzzleMove(PuzzleActionType.ANALYZE_BOARD, success=True),
        PuzzleMove(PuzzleActionType.MOVE_PIECE, success=False),
        PuzzleMove(PuzzleActionType.CHECK_GOAL, success=True),
    ]

    for move in moves:
        mapper.puzzle_to_agent(move)

    stats = mapper.get_statistics()

    print(f"\nStatistics:")
    print(f"  Total mappings: {stats['total_mappings']}")
    print(f"  Successful mappings: {stats['successful_mappings']}")
    print(f"  Failed mappings: {stats['failed_mappings']}")
    print(f"  Success rate: {stats['success_rate']:.1%}")
    print(f"  Number of rules: {stats['num_rules']}")
    print(f"  Taxonomy categories: {stats['taxonomy_categories']}")

    assert stats['total_mappings'] == len(moves)
    assert stats['success_rate'] > 0.5  # At least 50% successful

    print("\n[PASS] Statistics tracking test passed!")


def main():
    print("="*70)
    print("PUZZLE-AGENT MAPPER TEST SUITE")
    print("="*70)

    # Run tests
    test_puzzle_to_agent_mapping()
    test_agent_to_puzzle_mapping()
    test_conversation_to_puzzle_path()
    test_puzzle_path_to_conversation()
    test_bidirectional_mapping()
    test_action_taxonomy()
    test_statistics()

    print("\n" + "="*70)
    print("ALL TESTS COMPLETED")
    print("="*70)


if __name__ == '__main__':
    main()
