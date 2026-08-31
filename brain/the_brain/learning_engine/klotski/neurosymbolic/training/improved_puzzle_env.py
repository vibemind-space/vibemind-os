"""
Improved Puzzle Environment with Better Reward Shaping

Key improvements:
1. Higher max_steps (1000 instead of 200)
2. Distance-to-goal reward shaping
3. Stronger guidance toward solution
"""

import torch
import numpy as np
from typing import Tuple, List, Dict, Optional
from copy import deepcopy

from neurosymbolic.core.puzzle_state import PuzzleState, PuzzlePiece
from neurosymbolic.core.state_graph_mapper import StateGraphMapper
from neurosymbolic.core.brain_graph import BrainConnectomeGraph
from neurosymbolic.symbolic.allis_rules import Action


class ImprovedPuzzleEnv:
    """
    Improved Klotski Puzzle Environment with better reward shaping
    """

    def __init__(
        self,
        layout_file: str,
        max_steps: int = 1000,  # INCREASED from 200
        reward_shaping: bool = True,
        use_distance_reward: bool = True  # NEW
    ):
        """
        Initialize improved puzzle environment

        Args:
            layout_file: Path to Klotski_NeuroLayout.json
            max_steps: Maximum steps per episode (default: 1000)
            reward_shaping: Use shaped rewards (consciousness delta)
            use_distance_reward: Add distance-to-goal reward shaping
        """
        self.layout_file = layout_file
        self.max_steps = max_steps
        self.reward_shaping = reward_shaping
        self.use_distance_reward = use_distance_reward

        # Initialize puzzle state
        self.initial_state = PuzzleState(layout_file=layout_file)

        # State-graph mapper for cognitive metrics
        brain_graph = BrainConnectomeGraph()
        self.mapper = StateGraphMapper(brain_graph)

        # Current state
        self.state = None
        self.step_count = 0
        self.previous_consciousness = 0.0
        self.previous_distance = 0.0  # Track distance for reward shaping

        # Goal position for DMN piece (exit = bottom-center)
        self.goal_position = (1, 3)  # (x, y) where DMN needs to be

    def reset(self) -> Tuple[torch.Tensor, List[Action]]:
        """Reset environment to initial state"""
        self.state = self.initial_state.clone()
        self.step_count = 0

        # Calculate initial consciousness
        analysis = self.mapper.analyze_state(self.state)
        self.previous_consciousness = analysis['consciousness_metric']

        # Calculate initial distance
        self.previous_distance = self._calculate_distance_to_goal()

        state_tensor = self._state_to_tensor()
        valid_actions = self._get_valid_actions()

        return state_tensor, valid_actions

    def step(self, action_idx: int) -> Tuple[torch.Tensor, float, bool, Dict]:
        """Execute action and return transition with improved rewards

        Args:
            action_idx: Index into the CURRENT valid_actions list (0-based)
        """
        self.step_count += 1

        # Get current valid actions
        valid_actions = self._get_valid_actions()

        # Check if action index is valid
        if action_idx < 0 or action_idx >= len(valid_actions):
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

        # Get action from current valid actions list
        action = valid_actions[action_idx]

        # Execute move
        piece_id = action.piece_id
        new_x, new_y = action.to_pos
        success = self.state.move_piece(piece_id, new_x, new_y)

        if not success:
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

        # Calculate consciousness-based reward
        analysis = self.mapper.analyze_state(self.state)
        current_consciousness = analysis['consciousness_metric']

        reward = 0.0

        # 1. Consciousness shaping (original)
        if self.reward_shaping:
            consciousness_reward = (current_consciousness - self.previous_consciousness) * 5.0
            reward += consciousness_reward

        # 2. Distance-to-goal shaping (NEW - stronger signal)
        if self.use_distance_reward:
            current_distance = self._calculate_distance_to_goal()
            distance_delta = self.previous_distance - current_distance  # Positive if closer

            # Stronger reward for getting closer to goal
            distance_reward = distance_delta * 2.0  # 2.0 reward per step closer
            reward += distance_reward

            self.previous_distance = current_distance

        self.previous_consciousness = current_consciousness

        # Check if solved
        done = self.state.is_solved()

        if done:
            reward += 200.0  # INCREASED from 100 - make solving very rewarding

        # Check max steps
        if self.step_count >= self.max_steps:
            done = True
            reward -= 10.0  # Timeout penalty

        # Info dict
        info = {
            'step': self.step_count,
            'consciousness': current_consciousness,
            'integration': analysis['integration_score'],
            'coherence': analysis['coherence'],
            'dmn_distance': self._calculate_distance_to_goal(),
            'is_solved': self.state.is_solved()
        }

        return self._state_to_tensor(), reward, done, info

    def _calculate_distance_to_goal(self) -> float:
        """
        Calculate Manhattan distance from DMN piece to goal position

        Returns:
            Distance to goal (0 = at goal)
        """
        # Get DMN piece position (top-left corner)
        dmn_piece = self.state.pieces.get('G')
        if dmn_piece is None:
            return 999.0  # DMN not found

        dmn_x = dmn_piece.x
        dmn_y = dmn_piece.y

        # Manhattan distance to goal
        distance = abs(dmn_x - self.goal_position[0]) + abs(dmn_y - self.goal_position[1])

        return float(distance)

    def _state_to_tensor(self) -> torch.Tensor:
        """Convert puzzle state to tensor"""
        board = np.zeros((5, 4), dtype=np.int32)

        for piece in self.state.pieces.values():
            for x, y in piece.get_occupied_cells():
                piece_id_map = {
                    'G': 1, 'V': 2, 'A': 3, 'S': 4, 'L': 5,
                    'D': 6, 'C': 7, 'I': 8, 'M': 9, 'O': 10
                }
                board[y, x] = piece_id_map.get(piece.piece_id, 0)

        return torch.from_numpy(board).unsqueeze(0)

    def _get_valid_actions(self) -> List[Action]:
        """Get list of valid actions from current state

        Returns:
            List of Action objects. Indices into this list (0, 1, 2, ...)
            are used as action_idx in step().
        """
        valid_actions = []

        for piece_id in self.state.pieces.keys():
            # Get valid moves from puzzle state
            valid_moves = self.state.get_valid_moves(piece_id)

            for new_x, new_y, direction in valid_moves:
                piece = self.state.pieces[piece_id]

                action = Action(
                    piece_id=piece_id,
                    from_pos=(piece.x, piece.y),
                    to_pos=(new_x, new_y),
                    direction=direction,
                    module_id='UNKNOWN'  # Not needed for distance reward
                )
                valid_actions.append(action)

        return valid_actions

    def render(self) -> str:
        """Render current board state as string"""
        if self.state is None:
            return "Environment not initialized"
        return self.state.get_board_string()
