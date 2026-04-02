"""
Ensemble Path Planner - Phase 2
Quantum-inspired multi-path exploration with checkpoint extraction

Implements 5 diverse search strategies:
1. Greedy - Always take highest value action
2. Exploratory - Random with bias toward unexplored states
3. BFS - Breadth-first search
4. A* - Heuristic-guided optimal search
5. CTM-guided - Deep reasoning for complex decisions

Finds N solutions, extracts common checkpoints, interpolates meta-path.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Set, Callable
from enum import Enum
import heapq
import random
from collections import defaultdict, Counter

from core.context_aligned_state import ContextAlignedState, ActionMetadata, ContextDimensions


class SearchStrategy(Enum):
    """Search strategy types for ensemble"""
    GREEDY = "greedy"
    EXPLORATORY = "exploratory"
    BFS = "bfs"
    ASTAR = "astar"
    CTM_GUIDED = "ctm_guided"


@dataclass
class SolutionPath:
    """Complete solution path with metadata"""
    states: List[ContextAlignedState]
    strategy: SearchStrategy
    total_cost: float
    total_time: float
    checkpoint_count: int
    success: bool
    reliability_score: float

    def get_checkpoints(self) -> List[ContextAlignedState]:
        """Extract checkpoint states"""
        return [s for s in self.states if s.is_checkpoint]

    def get_checkpoint_indices(self) -> List[int]:
        """Get indices of checkpoints in path"""
        return [i for i, s in enumerate(self.states) if s.is_checkpoint]


@dataclass
class CommonCheckpoint:
    """Checkpoint found in multiple solutions"""
    action_type: str
    action_name: str
    occurrence_count: int
    strategies: Set[SearchStrategy]
    average_step: float  # Average position in path
    average_confidence: float
    reliability_score: float


@dataclass
class MetaPath:
    """Interpolated meta-path from multiple solutions"""
    essential_checkpoints: List[CommonCheckpoint]
    interpolated_states: List[ContextAlignedState]
    coverage_score: float  # How many solutions agree on this path
    efficiency_score: float  # Time/cost efficiency
    reliability_score: float  # Success probability


class EnsemblePathPlanner:
    """
    Quantum-inspired multi-path exploration

    Finds multiple diverse solutions to same goal, extracts common checkpoints,
    and interpolates a meta-path representing "essential" steps.

    Inspired by quantum physics: light explores all possible paths simultaneously,
    final result is interference of all paths.
    """

    def __init__(
        self,
        num_solutions: int = 5,
        max_steps_per_search: int = 100,
        checkpoint_threshold: float = 0.6,  # Min occurrence rate to be "common"
        seed: int = 42
    ):
        """
        Args:
            num_solutions: Number of diverse solutions to find
            max_steps_per_search: Max steps per search strategy
            checkpoint_threshold: Min fraction of solutions that must contain checkpoint
            seed: Random seed for reproducibility
        """
        self.num_solutions = num_solutions
        self.max_steps_per_search = max_steps_per_search
        self.checkpoint_threshold = checkpoint_threshold
        self.random = random.Random(seed)

        # Statistics
        self.total_searches = 0
        self.successful_searches = 0
        self.strategy_performance: Dict[SearchStrategy, List[float]] = defaultdict(list)

    def find_ensemble_solutions(
        self,
        initial_state: ContextAlignedState,
        goal_condition: Callable[[ContextAlignedState], bool],
        available_actions: List[Callable[[ContextAlignedState], ContextAlignedState]],
        history: List[ContextAlignedState] = None
    ) -> List[SolutionPath]:
        """
        Find multiple diverse solutions using different strategies

        Args:
            initial_state: Starting state
            goal_condition: Function that returns True if state is goal
            available_actions: List of action functions
            history: Optional conversation history for context

        Returns:
            List of solution paths from different strategies
        """
        solutions = []
        history = history or []

        # Strategy 1: Greedy (fast, suboptimal)
        greedy_solution = self._greedy_search(
            initial_state, goal_condition, available_actions, history
        )
        if greedy_solution:
            solutions.append(greedy_solution)

        # Strategy 2: Exploratory (high diversity)
        exploratory_solution = self._exploratory_search(
            initial_state, goal_condition, available_actions, history
        )
        if exploratory_solution:
            solutions.append(exploratory_solution)

        # Strategy 3: BFS (complete, slow)
        bfs_solution = self._bfs_search(
            initial_state, goal_condition, available_actions, history
        )
        if bfs_solution:
            solutions.append(bfs_solution)

        # Strategy 4: A* (optimal with good heuristic)
        astar_solution = self._astar_search(
            initial_state, goal_condition, available_actions, history
        )
        if astar_solution:
            solutions.append(astar_solution)

        # Strategy 5: CTM-guided (deep reasoning, expensive)
        if len(solutions) < self.num_solutions:
            ctm_solution = self._ctm_guided_search(
                initial_state, goal_condition, available_actions, history
            )
            if ctm_solution:
                solutions.append(ctm_solution)

        # Update statistics
        self.total_searches += 5
        self.successful_searches += len(solutions)

        return solutions

    def extract_common_checkpoints(
        self,
        solutions: List[SolutionPath]
    ) -> List[CommonCheckpoint]:
        """
        Extract checkpoints that appear in multiple solutions

        This identifies "essential" progress points that most strategies agree on.

        Args:
            solutions: List of solution paths

        Returns:
            List of common checkpoints sorted by occurrence
        """
        if not solutions:
            return []

        # Count checkpoint occurrences across solutions
        checkpoint_counter: Dict[Tuple[str, str], Dict] = defaultdict(
            lambda: {
                'count': 0,
                'strategies': set(),
                'steps': [],
                'confidences': [],
                'reliabilities': []
            }
        )

        for solution in solutions:
            checkpoints = solution.get_checkpoints()
            checkpoint_indices = solution.get_checkpoint_indices()

            for checkpoint, idx in zip(checkpoints, checkpoint_indices):
                if checkpoint.last_action:
                    key = (checkpoint.last_action.action_type, checkpoint.last_action.action_name)

                    checkpoint_counter[key]['count'] += 1
                    checkpoint_counter[key]['strategies'].add(solution.strategy)
                    checkpoint_counter[key]['steps'].append(idx)
                    checkpoint_counter[key]['confidences'].append(checkpoint.confidence_level)
                    checkpoint_counter[key]['reliabilities'].append(checkpoint.reliability_score)

        # Filter by threshold and create CommonCheckpoint objects
        min_occurrences = max(1, int(len(solutions) * self.checkpoint_threshold))
        common_checkpoints = []

        for (action_type, action_name), data in checkpoint_counter.items():
            if data['count'] >= min_occurrences:
                common_checkpoint = CommonCheckpoint(
                    action_type=action_type,
                    action_name=action_name,
                    occurrence_count=data['count'],
                    strategies=data['strategies'],
                    average_step=sum(data['steps']) / len(data['steps']),
                    average_confidence=sum(data['confidences']) / len(data['confidences']),
                    reliability_score=sum(data['reliabilities']) / len(data['reliabilities'])
                )
                common_checkpoints.append(common_checkpoint)

        # Sort by occurrence count (desc) then average step (asc)
        common_checkpoints.sort(key=lambda c: (-c.occurrence_count, c.average_step))

        return common_checkpoints

    def interpolate_meta_path(
        self,
        solutions: List[SolutionPath],
        common_checkpoints: List[CommonCheckpoint],
        initial_state: ContextAlignedState
    ) -> MetaPath:
        """
        Interpolate meta-path from multiple solutions

        Combines best aspects of all solutions to create ideal path.
        Like quantum interference - constructive interference of good paths,
        destructive interference of bad paths.

        Args:
            solutions: List of solution paths
            common_checkpoints: Common checkpoints across solutions
            initial_state: Starting state

        Returns:
            Interpolated meta-path
        """
        if not solutions:
            return MetaPath(
                essential_checkpoints=[],
                interpolated_states=[],
                coverage_score=0.0,
                efficiency_score=0.0,
                reliability_score=0.0
            )

        # Calculate coverage score (how many solutions agree)
        coverage_score = len(solutions) / self.num_solutions

        # Calculate efficiency score (average of best solutions)
        successful_solutions = [s for s in solutions if s.success]
        if successful_solutions:
            efficiency_score = sum(
                1.0 / (s.total_time + 1e-6) for s in successful_solutions
            ) / len(successful_solutions)
        else:
            efficiency_score = 0.0

        # Calculate reliability score (success rate * avg checkpoint reliability)
        reliability_score = len(successful_solutions) / len(solutions)
        if common_checkpoints:
            avg_checkpoint_reliability = sum(
                c.reliability_score for c in common_checkpoints
            ) / len(common_checkpoints)
            reliability_score *= avg_checkpoint_reliability

        # Create interpolated states by following common checkpoints
        interpolated_states = [initial_state]

        for checkpoint in common_checkpoints:
            # Find best state matching this checkpoint from solutions
            best_state = self._find_best_checkpoint_state(
                checkpoint, solutions
            )
            if best_state:
                interpolated_states.append(best_state)

        return MetaPath(
            essential_checkpoints=common_checkpoints,
            interpolated_states=interpolated_states,
            coverage_score=coverage_score,
            efficiency_score=efficiency_score,
            reliability_score=reliability_score
        )

    # ============================================
    # Search Strategy Implementations
    # ============================================

    def _greedy_search(
        self,
        initial_state: ContextAlignedState,
        goal_condition: Callable[[ContextAlignedState], bool],
        available_actions: List[Callable],
        history: List[ContextAlignedState]
    ) -> Optional[SolutionPath]:
        """Greedy search - always take highest value action"""
        current = initial_state
        path = [current]
        total_time = 0.0

        for step in range(self.max_steps_per_search):
            if goal_condition(current):
                return self._create_solution_path(
                    path, SearchStrategy.GREEDY, total_time
                )

            # Evaluate all actions, take best
            best_action = None
            best_value = -float('inf')

            for action in available_actions:
                next_state = action(current)
                value = self._evaluate_state_greedy(next_state, history + path)

                if value > best_value:
                    best_value = value
                    best_action = action

            if best_action is None:
                break

            current = best_action(current)
            path.append(current)

            if current.last_action:
                total_time += current.last_action.duration

        # Failed to reach goal
        return self._create_solution_path(path, SearchStrategy.GREEDY, total_time, success=False)

    def _exploratory_search(
        self,
        initial_state: ContextAlignedState,
        goal_condition: Callable[[ContextAlignedState], bool],
        available_actions: List[Callable],
        history: List[ContextAlignedState]
    ) -> Optional[SolutionPath]:
        """Exploratory search - random with bias toward unexplored"""
        current = initial_state
        path = [current]
        visited_actions = set()
        total_time = 0.0

        for step in range(self.max_steps_per_search):
            if goal_condition(current):
                return self._create_solution_path(
                    path, SearchStrategy.EXPLORATORY, total_time
                )

            # Bias toward unexplored actions
            unexplored = [a for a in available_actions
                         if id(a) not in visited_actions]

            if unexplored and self.random.random() < 0.7:
                # 70% chance to explore new action
                action = self.random.choice(unexplored)
            else:
                # 30% chance to revisit known action
                action = self.random.choice(available_actions)

            visited_actions.add(id(action))

            current = action(current)
            path.append(current)

            if current.last_action:
                total_time += current.last_action.duration

        return self._create_solution_path(
            path, SearchStrategy.EXPLORATORY, total_time, success=goal_condition(current)
        )

    def _bfs_search(
        self,
        initial_state: ContextAlignedState,
        goal_condition: Callable[[ContextAlignedState], bool],
        available_actions: List[Callable],
        history: List[ContextAlignedState]
    ) -> Optional[SolutionPath]:
        """BFS - complete search, finds shortest path"""
        from collections import deque

        queue = deque([(initial_state, [initial_state], 0.0)])
        visited = {self._state_signature(initial_state)}

        while queue and len(visited) < self.max_steps_per_search:
            current, path, total_time = queue.popleft()

            if goal_condition(current):
                return self._create_solution_path(
                    path, SearchStrategy.BFS, total_time
                )

            for action in available_actions:
                next_state = action(current)
                sig = self._state_signature(next_state)

                if sig not in visited:
                    visited.add(sig)
                    new_time = total_time + (next_state.last_action.duration
                                            if next_state.last_action else 0.0)
                    queue.append((next_state, path + [next_state], new_time))

        # No solution found within step limit
        return None

    def _astar_search(
        self,
        initial_state: ContextAlignedState,
        goal_condition: Callable[[ContextAlignedState], bool],
        available_actions: List[Callable],
        history: List[ContextAlignedState]
    ) -> Optional[SolutionPath]:
        """A* search - optimal with heuristic"""
        # Priority queue: (f_score, counter, state, path, g_score, total_time)
        # Counter breaks ties when f_scores are equal
        counter = 0
        heap = [(0.0, counter, initial_state, [initial_state], 0.0, 0.0)]
        visited = {self._state_signature(initial_state)}

        while heap and len(visited) < self.max_steps_per_search:
            f_score, _, current, path, g_score, total_time = heapq.heappop(heap)

            if goal_condition(current):
                return self._create_solution_path(
                    path, SearchStrategy.ASTAR, total_time
                )

            for action in available_actions:
                next_state = action(current)
                sig = self._state_signature(next_state)

                if sig not in visited:
                    visited.add(sig)

                    # g_score = cost so far (number of steps)
                    new_g = g_score + 1.0

                    # h_score = heuristic (estimated remaining cost)
                    h = self._heuristic(next_state, history + path)

                    # f_score = g + h
                    new_f = new_g + h

                    new_time = total_time + (next_state.last_action.duration
                                            if next_state.last_action else 0.0)

                    counter += 1
                    heapq.heappush(heap, (new_f, counter, next_state, path + [next_state],
                                         new_g, new_time))

        return None

    def _ctm_guided_search(
        self,
        initial_state: ContextAlignedState,
        goal_condition: Callable[[ContextAlignedState], bool],
        available_actions: List[Callable],
        history: List[ContextAlignedState]
    ) -> Optional[SolutionPath]:
        """CTM-guided search - deep reasoning (placeholder for now)"""
        # For now, use greedy with higher quality evaluation
        # Later: integrate with actual CTM reasoning
        return self._greedy_search(initial_state, goal_condition, available_actions, history)

    # ============================================
    # Helper Methods
    # ============================================

    def _evaluate_state_greedy(
        self,
        state: ContextAlignedState,
        history: List[ContextAlignedState]
    ) -> float:
        """Evaluate state quality for greedy selection"""
        value = 0.0

        # Reward checkpoints
        if state.is_checkpoint:
            value += 10.0

        # Reward action hierarchy
        if state.last_action:
            value += state.last_action.action_value * 5.0

        # Reward progress
        value += state.path_progress * 3.0

        # Reward confidence
        value += state.confidence_level * 2.0

        # Penalty for low context alignment (exploring new territory)
        if history:
            alignment = state.calculate_context_alignment(history)
            value -= (1.0 - alignment) * 1.0

        return value

    def _heuristic(
        self,
        state: ContextAlignedState,
        history: List[ContextAlignedState]
    ) -> float:
        """Heuristic for A* (estimated cost to goal)"""
        # Lower is better (cost estimate)

        # If already at goal (high progress), low cost
        if state.path_progress >= 0.95:
            return 0.0

        # Estimate remaining steps
        remaining_progress = 1.0 - state.path_progress
        estimated_steps = remaining_progress * 10.0  # Assume ~10 steps to goal

        # Adjust by confidence (low confidence = more steps needed)
        estimated_steps /= (state.confidence_level + 0.1)

        return estimated_steps

    def _state_signature(self, state: ContextAlignedState) -> str:
        """Create unique signature for state (for visited set)"""
        return f"{state.step_count}_{state.last_action.action_name if state.last_action else 'init'}"

    def _create_solution_path(
        self,
        states: List[ContextAlignedState],
        strategy: SearchStrategy,
        total_time: float,
        success: bool = True
    ) -> SolutionPath:
        """Create SolutionPath from states"""
        checkpoint_count = sum(1 for s in states if s.is_checkpoint)

        # Calculate reliability score
        if states:
            reliability_score = sum(s.reliability_score for s in states) / len(states)
        else:
            reliability_score = 0.0

        return SolutionPath(
            states=states,
            strategy=strategy,
            total_cost=len(states),
            total_time=total_time,
            checkpoint_count=checkpoint_count,
            success=success,
            reliability_score=reliability_score
        )

    def _find_best_checkpoint_state(
        self,
        checkpoint: CommonCheckpoint,
        solutions: List[SolutionPath]
    ) -> Optional[ContextAlignedState]:
        """Find best state matching checkpoint from solutions"""
        candidates = []

        for solution in solutions:
            for state in solution.states:
                if (state.is_checkpoint and state.last_action and
                    state.last_action.action_type == checkpoint.action_type and
                    state.last_action.action_name == checkpoint.action_name):
                    candidates.append(state)

        if not candidates:
            return None

        # Return state with highest reliability
        return max(candidates, key=lambda s: s.reliability_score)

    def get_statistics(self) -> Dict:
        """Get ensemble planner statistics"""
        return {
            'total_searches': self.total_searches,
            'successful_searches': self.successful_searches,
            'success_rate': self.successful_searches / max(1, self.total_searches),
            'strategy_performance': {
                strategy.value: {
                    'count': len(scores),
                    'avg_score': sum(scores) / len(scores) if scores else 0.0
                }
                for strategy, scores in self.strategy_performance.items()
            }
        }
