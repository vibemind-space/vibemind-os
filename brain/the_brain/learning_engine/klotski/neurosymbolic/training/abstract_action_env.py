"""
Abstract Action Environment Wrapper

Converts piece-specific actions to 4 abstract directional actions:
0 = UP, 1 = DOWN, 2 = LEFT, 3 = RIGHT

This matches the BFS demonstration format and makes the action space
consistent across all states.
"""

import torch
import numpy as np
from typing import Tuple, Dict, Optional
from neurosymbolic.training.puzzle_env import PuzzleEnv


class AbstractActionEnv(PuzzleEnv):
    """
    Environment wrapper that uses 4 abstract directional actions
    instead of piece-specific actions.

    Action mapping:
    0 = UP    (move some piece up)
    1 = DOWN  (move some piece down)
    2 = LEFT  (move some piece left)
    3 = RIGHT (move some piece right)

    The environment automatically selects which piece to move based on:
    1. Which pieces can move in the requested direction
    2. Heuristic priority (pieces closer to goal, blocking pieces, etc.)
    """

    def __init__(self, *args, use_action_masking=False, **kwargs):
        """Initialize with abstract action space

        Args:
            use_action_masking: If True, provide action masks to prevent invalid moves
        """
        super().__init__(*args, **kwargs)
        self.num_abstract_actions = 4
        self.direction_map = {
            0: 'up',
            1: 'down',
            2: 'left',
            3: 'right'
        }
        self.use_action_masking = use_action_masking

        # Track invalid move attempts
        self.invalid_move_counts = {'up': 0, 'down': 0, 'left': 0, 'right': 0}
        self.total_moves = 0
        self.valid_moves = 0

    def reset(self) -> Tuple[torch.Tensor, int]:
        """
        Reset environment

        Returns:
            Tuple of (state_tensor, num_actions=4)
        """
        # Print stats from previous episode if there were any moves
        if self.total_moves > 0:
            invalid_pct = (self.total_moves - self.valid_moves) / self.total_moves * 100
            print(f"\n[Episode Stats] Total: {self.total_moves}, Valid: {self.valid_moves}, Invalid: {self.total_moves - self.valid_moves} ({invalid_pct:.1f}%)")
            print(f"  Invalid by direction: UP={self.invalid_move_counts['up']}, DOWN={self.invalid_move_counts['down']}, "
                  f"LEFT={self.invalid_move_counts['left']}, RIGHT={self.invalid_move_counts['right']}")

        # Reset counters
        self.invalid_move_counts = {'up': 0, 'down': 0, 'left': 0, 'right': 0}
        self.total_moves = 0
        self.valid_moves = 0

        state_tensor, _ = super().reset()
        return state_tensor, self.num_abstract_actions

    def step(self, action: int) -> Tuple[torch.Tensor, float, bool, Dict]:
        """
        Execute abstract action

        Args:
            action: Abstract action index (0=UP, 1=DOWN, 2=LEFT, 3=RIGHT)

        Returns:
            Tuple of (next_state, reward, done, info)
        """
        self.step_count += 1

        # Validate action
        if action not in [0, 1, 2, 3]:
            # Invalid action
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

        # Get direction
        direction = self.direction_map[action]

        # Track move attempt
        self.total_moves += 1

        # Find all pieces that can move in this direction
        candidates = self._find_movable_pieces(direction)

        if not candidates:
            # No piece can move in this direction
            # Track invalid move
            self.invalid_move_counts[direction] += 1

            # Get all available directions for logging
            available_dirs = []
            for d in ['up', 'down', 'left', 'right']:
                if self._find_movable_pieces(d):
                    available_dirs.append(d.upper())

            # Log invalid move (print every 20 invalid attempts to avoid spam)
            total_invalid = sum(self.invalid_move_counts.values())
            if total_invalid % 20 == 1:  # First and every 20th
                print(f"  [Step {self.step_count}] Invalid: {direction.upper()} (total invalid: {total_invalid}), "
                      f"Available: {', '.join(available_dirs) if available_dirs else 'NONE'}")

            # Small penalty but not terminal (agent can try another direction)
            analysis = self.mapper.analyze_state(self.state)
            reward = -0.1
            done = False

            info = {
                'no_valid_move': True,
                'direction': direction,
                'step': self.step_count,
                'consciousness': analysis['consciousness_metric'],
                'integration': analysis['integration_score'],
                'coherence': analysis['coherence'],
                'dmn_distance': analysis['dmn_distance_to_exit'],
                'is_solved': False
            }

            # Check max steps
            if self.step_count >= self.max_steps:
                done = True
                reward -= 50.0

            return self._state_to_tensor(), reward, done, info

        # Select best candidate using heuristic
        selected_piece_id, target_pos = self._select_best_piece(candidates, direction)

        # Track valid move
        self.valid_moves += 1

        # Execute the move using parent class logic
        success = self.state.move_piece(selected_piece_id, target_pos[0], target_pos[1])

        if not success:
            # Should not happen if _find_movable_pieces works correctly
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

        # Calculate reward using parent class reward logic
        analysis = self.mapper.analyze_state(self.state)
        current_consciousness = analysis['consciousness_metric']
        current_dmn_distance = analysis['dmn_distance_to_exit']

        if self.reward_shaping:
            # Multi-component shaped reward
            # REWARD FOR VALID MOVE: Encourage any action (agent was getting stuck)
            valid_move_reward = 1.0

            consciousness_reward = (current_consciousness - self.previous_consciousness) * 1.0

            previous_dmn_distance = getattr(self, 'previous_dmn_distance', current_dmn_distance)
            distance_delta = previous_dmn_distance - current_dmn_distance
            distance_reward = distance_delta * 10.0  # INCREASED: from 5.0 to 10.0 for stronger signal

            step_penalty = 0.0  # No step penalty

            # ACTION SUPERVISION BONUS
            markov_bonus = 0.0
            is_on_path = False
            is_optimal_action = False

            if self.use_markov_guidance and self.markov_guide is not None:
                current_state_tensor = self._state_to_tensor()
                current_state_np = current_state_tensor.squeeze(0).cpu().numpy() if hasattr(current_state_tensor, 'cpu') else current_state_tensor.squeeze(0).numpy()

                if self.previous_state_np is not None:
                    is_optimal_action = self.markov_guide.is_optimal_action(
                        self.previous_state_np,
                        current_state_np
                    )

                    if is_optimal_action:
                        markov_bonus = 10.0 * self.markov_bonus_weight  # INCREASED: from 5.0 to 10.0
                    else:
                        markov_bonus = 0.0  # REMOVED PENALTY: was -0.5, now neutral (agent was getting too much negative)

                    is_on_path = self.markov_guide.is_on_optimal_path(current_state_np)

                self.previous_state_np = current_state_np

            reward = valid_move_reward + consciousness_reward + distance_reward + step_penalty + markov_bonus
            self.previous_dmn_distance = current_dmn_distance
        else:
            reward = 0.0
            is_on_path = False
            is_optimal_action = False

        self.previous_consciousness = current_consciousness

        # Check if solved
        done = self.state.is_solved()

        if done:
            reward += 100.0
            print(f"PUZZLE SOLVED in {self.step_count} steps!")

        # Check max steps
        if self.step_count >= self.max_steps:
            done = True
            reward -= 50.0

        # Info dict
        info = {
            'step': self.step_count,
            'consciousness': current_consciousness,
            'integration': analysis['integration_score'],
            'coherence': analysis['coherence'],
            'dmn_distance': analysis['dmn_distance_to_exit'],
            'is_solved': self.state.is_solved(),
            'is_on_optimal_path': is_on_path,
            'is_optimal_action': is_optimal_action,
            'selected_piece': selected_piece_id,
            'direction': direction
        }

        return self._state_to_tensor(), reward, done, info

    def _find_movable_pieces(self, direction: str) -> list:
        """
        Find all pieces that can move in the given direction

        Args:
            direction: 'up', 'down', 'left', or 'right'

        Returns:
            List of (piece_id, target_position) tuples
        """
        candidates = []

        for piece_id, piece in self.state.pieces.items():
            valid_moves = self.state.get_valid_moves(piece_id)

            for new_x, new_y, move_dir in valid_moves:
                if move_dir == direction:
                    candidates.append((piece_id, (new_x, new_y)))

        return candidates

    def _select_best_piece(self, candidates: list, direction: str) -> Tuple[str, Tuple[int, int]]:
        """
        Select the best piece to move from candidates using heuristics

        Priority:
        1. Move the goal piece (DMN/'G') if possible
        2. Move pieces that are blocking the goal
        3. Move pieces closer to their target positions

        Args:
            candidates: List of (piece_id, target_pos) tuples
            direction: Direction being moved

        Returns:
            Tuple of (selected_piece_id, target_position)
        """
        if len(candidates) == 1:
            return candidates[0]

        # Priority 1: Always prefer moving the goal piece
        for piece_id, target_pos in candidates:
            if piece_id == 'G':  # DMN is the goal piece
                return (piece_id, target_pos)

        # Priority 2: Move pieces toward the exit (bottom center)
        # Exit is at y=4, x=1,2
        exit_center = (1.5, 4)

        def distance_to_exit(pos):
            return abs(pos[0] - exit_center[0]) + abs(pos[1] - exit_center[1])

        # For DOWN and RIGHT movements (toward exit), prefer pieces farther from exit
        # For UP and LEFT movements, prefer pieces closer to exit (clearing path)
        if direction in ['down', 'right']:
            # Moving toward exit - move pieces that are blocking the path
            candidates.sort(key=lambda x: -distance_to_exit((x[1][0], x[1][1])))
        else:
            # Moving away from exit - move pieces that are close (clearing space)
            candidates.sort(key=lambda x: distance_to_exit((x[1][0], x[1][1])))

        return candidates[0]

    def get_num_actions(self) -> int:
        """Return number of abstract actions (always 4)"""
        return self.num_abstract_actions

    def get_action_mask(self) -> np.ndarray:
        """
        Get boolean mask indicating which actions are valid in the current state

        Returns:
            np.ndarray: Boolean array [4] where True = action is valid
                       [UP, DOWN, LEFT, RIGHT]
        """
        mask = np.zeros(4, dtype=bool)

        for action_idx, direction in self.direction_map.items():
            candidates = self._find_movable_pieces(direction)
            mask[action_idx] = len(candidates) > 0

        return mask
