"""
Puzzle Environment for RL Training

Wraps the Klotski puzzle as an RL environment with:
- State: Board configuration
- Actions: Valid piece moves
- Reward: Progress toward solution (consciousness metric)
- Done: Puzzle solved (DMN at exit)
"""

import torch
import numpy as np
import json
import hashlib
from pathlib import Path
from typing import Tuple, List, Dict, Optional
from copy import deepcopy

from neurosymbolic.core.puzzle_state import PuzzleState, PuzzlePiece
from neurosymbolic.core.state_graph_mapper import StateGraphMapper
from neurosymbolic.core.brain_graph import BrainConnectomeGraph
from neurosymbolic.symbolic.allis_rules import Action
from neurosymbolic.utils.markov_guidance import MarkovGuidance


class PuzzleEnv:
    """
    Klotski Puzzle Environment

    RL Interface:
    - reset() -> state
    - step(action) -> next_state, reward, done, info
    - get_valid_actions() -> List[Action]
    """

    def __init__(
        self,
        layout_file: str,
        max_steps: int = 200,
        reward_shaping: bool = True,
        use_markov_guidance: bool = True,
        markov_bonus_weight: float = 1.0,
        demo_dir: str = "demonstrations_formatted"
    ):
        """
        Initialize puzzle environment

        Args:
            layout_file: Path to Klotski_NeuroLayout.json
            max_steps: Maximum steps per episode
            reward_shaping: Use shaped rewards (consciousness delta)
            use_markov_guidance: Use Markov guidance from demonstrations
            markov_bonus_weight: Weight for Markov progress bonus
            demo_dir: Directory containing expert demonstrations
        """
        self.layout_file = layout_file
        self.max_steps = max_steps
        self.reward_shaping = reward_shaping
        self.use_markov_guidance = use_markov_guidance
        self.markov_bonus_weight = markov_bonus_weight

        # Initialize puzzle state
        self.initial_state = PuzzleState(layout_file=layout_file)

        # State-graph mapper for cognitive metrics
        brain_graph = BrainConnectomeGraph()
        self.mapper = StateGraphMapper(brain_graph)

        # Current state
        self.state = None
        self.step_count = 0
        self.previous_consciousness = 0.0
        self.previous_state_np = None  # For Markov guidance

        # Action mapping
        self.action_to_move = {}  # Will be populated each step
        self.move_to_action = {}

        # Markov guidance (load from demonstrations)
        self.markov_guide = None
        if use_markov_guidance:
            self._load_markov_guidance(demo_dir)
        else:
            self.use_markov_guidance = False

    def reset(self) -> Tuple[torch.Tensor, List[Action]]:
        """
        Reset environment to initial state

        Returns:
            Tuple of (state_tensor, valid_actions)
        """
        self.state = self.initial_state.clone()
        self.step_count = 0

        # Calculate initial consciousness and distance
        analysis = self.mapper.analyze_state(self.state)
        self.previous_consciousness = analysis['consciousness_metric']
        self.previous_dmn_distance = analysis['dmn_distance_to_exit']

        state_tensor = self._state_to_tensor()

        # Initialize previous state for Markov guidance
        if self.use_markov_guidance:
            state_np = state_tensor.squeeze(0).cpu().numpy() if hasattr(state_tensor, 'cpu') else state_tensor.squeeze(0).numpy()
            self.previous_state_np = state_np

        valid_actions = self._get_valid_actions()

        return state_tensor, valid_actions

    def step(self, action_idx: int) -> Tuple[torch.Tensor, float, bool, Dict]:
        """
        Execute action and return transition

        Args:
            action_idx: Index of action to execute

        Returns:
            Tuple of (next_state, reward, done, info)
        """
        self.step_count += 1

        # Get action
        if action_idx not in self.action_to_move:
            # Invalid action index - penalize
            reward = -1.0
            done = True
            info = {
                'invalid_action': True,
                'step': self.step_count,
                'consciousness': 0.0,
                'integration': 0.0,
                'coherence': 0.0,
                'dmn_distance': 999,
                'is_solved': False
            }
            return self._state_to_tensor(), reward, done, info

        action = self.action_to_move[action_idx]

        # Execute move
        piece_id = action.piece_id
        new_x, new_y = action.to_pos

        success = self.state.move_piece(piece_id, new_x, new_y)

        if not success:
            # Move failed - should not happen if action was valid
            reward = -1.0
            done = True
            info = {
                'move_failed': True,
                'step': self.step_count,
                'consciousness': 0.0,
                'integration': 0.0,
                'coherence': 0.0,
                'dmn_distance': 999,
                'is_solved': False
            }
            return self._state_to_tensor(), reward, done, info

        # Calculate reward
        analysis = self.mapper.analyze_state(self.state)
        current_consciousness = analysis['consciousness_metric']
        current_dmn_distance = analysis['dmn_distance_to_exit']

        if self.reward_shaping:
            # Multi-component shaped reward:
            # 1. Consciousness improvement (brain integration) - REDUCED to prevent exploitation
            consciousness_reward = (current_consciousness - self.previous_consciousness) * 1.0

            # 2. Distance-to-goal improvement (MOST IMPORTANT for puzzle solving)
            previous_dmn_distance = getattr(self, 'previous_dmn_distance', current_dmn_distance)
            distance_delta = previous_dmn_distance - current_dmn_distance  # Positive if getting closer
            distance_reward = distance_delta * 5.0  # INCREASED: Reward moving toward goal

            # 3. Step penalty - REMOVED to allow full exploration with action guidance
            step_penalty = 0.0  # DISABLED: Let action bonus guide without penalty

            # 4. ACTION SUPERVISION BONUS - Reward taking actions that match expert
            markov_bonus = 0.0
            is_on_path = False
            is_optimal_action = False
            if self.use_markov_guidance and self.markov_guide is not None:
                # Get current state as numpy array
                current_state_tensor = self._state_to_tensor()
                current_state_np = current_state_tensor.squeeze(0).cpu().numpy() if hasattr(current_state_tensor, 'cpu') else current_state_tensor.squeeze(0).numpy()

                # Check if this action matches the expert demonstration
                if self.previous_state_np is not None:
                    is_optimal_action = self.markov_guide.is_optimal_action(
                        self.previous_state_np,
                        current_state_np
                    )

                    # Give STRONG bonus for taking optimal action
                    if is_optimal_action:
                        markov_bonus = 5.0 * self.markov_bonus_weight  # STRONG bonus for optimal action
                    else:
                        markov_bonus = -0.5 * self.markov_bonus_weight  # Small penalty for wrong action

                    # Check if we're on the optimal path
                    is_on_path = self.markov_guide.is_on_optimal_path(current_state_np)

                # Update previous state
                self.previous_state_np = current_state_np

            # Combined reward
            reward = consciousness_reward + distance_reward + step_penalty + markov_bonus

            # Store for next step
            self.previous_dmn_distance = current_dmn_distance
        else:
            # Sparse reward: only at goal
            reward = -0.02  # Match new step penalty
            is_on_path = False

        self.previous_consciousness = current_consciousness

        # Check if solved
        done = self.state.is_solved()

        if done:
            reward += 100.0  # Large bonus for solving
            print(f"PUZZLE SOLVED in {self.step_count} steps!")

        # Check max steps
        if self.step_count >= self.max_steps:
            done = True
            reward -= 50.0  # INCREASED 5x: Strong penalty for timeout

        # Info dict
        info = {
            'step': self.step_count,
            'consciousness': current_consciousness,
            'integration': analysis['integration_score'],
            'coherence': analysis['coherence'],
            'dmn_distance': analysis['dmn_distance_to_exit'],
            'is_solved': self.state.is_solved(),
            'is_on_optimal_path': is_on_path,  # Track if state is on expert path
            'is_optimal_action': is_optimal_action  # Track if action matched expert
        }

        return self._state_to_tensor(), reward, done, info

    def _state_to_tensor(self) -> torch.Tensor:
        """
        Convert puzzle state to tensor

        Returns:
            Tensor [5, 4] with piece IDs (height=5, width=4)
        """
        # Create board tensor (height x width)
        board = np.zeros((5, 4), dtype=np.int32)

        for piece in self.state.pieces.values():
            for x, y in piece.get_occupied_cells():
                # Map piece ID to integer
                piece_id_map = {
                    'G': 1, 'V': 2, 'A': 3, 'S': 4, 'L': 5,
                    'D': 6, 'C': 7, 'I': 8, 'M': 9, 'O': 10
                }
                board[y, x] = piece_id_map.get(piece.piece_id, 0)

        return torch.from_numpy(board).unsqueeze(0)  # [1, 5, 4]

    def _get_valid_actions(self) -> List[Action]:
        """
        Get list of valid actions from current state

        Returns:
            List of Action objects
        """
        actions = []
        self.action_to_move = {}
        self.move_to_action = {}

        action_idx = 0

        for piece_id in self.state.pieces.keys():
            valid_moves = self.state.get_valid_moves(piece_id)

            for new_x, new_y, direction in valid_moves:
                piece = self.state.pieces[piece_id]
                module_id = self.mapper.get_module_for_piece(piece_id)

                action = Action(
                    piece_id=piece_id,
                    from_pos=(piece.x, piece.y),
                    to_pos=(new_x, new_y),
                    direction=direction,
                    module_id=module_id or 'UNKNOWN'
                )

                actions.append(action)
                self.action_to_move[action_idx] = action
                self.move_to_action[(piece_id, new_x, new_y)] = action_idx

                action_idx += 1

        return actions

    def render(self) -> str:
        """Render current state as string"""
        return self.state.get_board_string()

    def get_state_analysis(self) -> Dict:
        """Get cognitive analysis of current state"""
        return self.mapper.analyze_state(self.state)

    def _load_markov_guidance(self, demo_dir: str):
        """
        Load Markov guidance from expert demonstrations

        Args:
            demo_dir: Directory containing expert demonstrations
        """
        # Extract puzzle name from layout file
        puzzle_name = Path(self.layout_file).stem

        # Create MarkovGuidance instance
        from neurosymbolic.utils.markov_guidance import MarkovGuidance
        self.markov_guide = MarkovGuidance(demo_dir)

        # Load demonstration for this puzzle
        success = self.markov_guide.load_demonstration(puzzle_name)

        if success:
            print(f"[OK] Markov guidance loaded for {puzzle_name}")
            stats = self.markov_guide.get_statistics()
            print(f"  Unique states: {stats['unique_states']}")
            print(f"  Goal states: {stats['goal_states']}")
            print(f"  Max path length: {stats['max_path_length']}")
        else:
            print(f"[WARNING] No Markov guidance for {puzzle_name}")
            self.use_markov_guidance = False


if __name__ == "__main__":
    # Test environment
    print("Testing Puzzle Environment...")
    print("="*60)

    layout_path = r"C:\Users\User\Downloads\Klotski_NeuroLayout.json"
    env = PuzzleEnv(layout_path, max_steps=200, reward_shaping=True)

    print("Environment created")
    print(f"Max steps: {env.max_steps}")

    # Test reset
    print("\nResetting environment...")
    state, valid_actions = env.reset()
    print(f"Initial state shape: {state.shape}")
    print(f"Valid actions: {len(valid_actions)}")

    print("\nInitial board:")
    print(env.render())

    print("\nValid actions:")
    for i, action in enumerate(valid_actions[:5]):  # Show first 5
        print(f"  {i}: Move {action.piece_id} ({action.module_id}) {action.direction}")

    print(f"\n... and {len(valid_actions) - 5} more actions")

    # Test step
    print("\nTaking action 0...")
    next_state, reward, done, info = env.step(0)
    print(f"Reward: {reward:.3f}")
    print(f"Done: {done}")
    print(f"Info: {info}")

    print("\nBoard after move:")
    print(env.render())

    # Test multiple steps
    print("\nTaking 5 random actions...")
    for i in range(5):
        valid_actions = env._get_valid_actions()
        if not valid_actions:
            print("No valid actions!")
            break

        action_idx = np.random.randint(0, len(valid_actions))
        next_state, reward, done, info = env.step(action_idx)

        print(f"  Step {i+1}: Action {action_idx}, Reward={reward:.3f}, "
              f"Consciousness={info['consciousness']:.3f}, Done={done}")

        if done:
            print("Episode finished!")
            break

    print("\n" + "="*60)
    print("Environment working correctly!")
