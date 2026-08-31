"""
Autonomous Goal Generator - AGI Phase 3

Generates goals autonomously based on:
- Prediction errors (curiosity)
- Uncertainty regions (exploration)
- Competence gaps (learning)
- Intrinsic values (motivation)

Key Features:
- Goal generation from prediction errors
- Information gain maximization
- Competence-based goal selection
- Hierarchical goal decomposition
"""

import numpy as np
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
import heapq
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class GoalType(Enum):
    """Types of autonomously generated goals."""
    EXPLORATION = "exploration"  # Explore unknown regions
    LEARNING = "learning"  # Improve competence in area
    ACHIEVEMENT = "achievement"  # Reach specific state
    MAINTENANCE = "maintenance"  # Keep state in range
    CURIOSITY = "curiosity"  # Investigate surprising observation
    MASTERY = "mastery"  # Master a skill


class GoalPriority(Enum):
    """Priority levels for goals."""
    CRITICAL = 0
    HIGH = 1
    MEDIUM = 2
    LOW = 3
    BACKGROUND = 4


class GoalStatus(Enum):
    """Status of a goal."""
    PENDING = "pending"
    ACTIVE = "active"
    ACHIEVED = "achieved"
    FAILED = "failed"
    ABANDONED = "abandoned"


@dataclass
class Goal:
    """Represents an autonomously generated goal."""
    id: str
    goal_type: GoalType
    description: str
    target_state: Optional[np.ndarray] = None
    target_region: Optional[Tuple[np.ndarray, np.ndarray]] = None  # (center, radius)
    priority: GoalPriority = GoalPriority.MEDIUM
    status: GoalStatus = GoalStatus.PENDING
    information_gain: float = 0.0
    competence_gap: float = 0.0
    intrinsic_value: float = 0.0
    parent_goal_id: Optional[str] = None
    subgoal_ids: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    deadline: Optional[datetime] = None
    attempts: int = 0
    max_attempts: int = 5


@dataclass
class GoalGeneratorStats:
    """Statistics for goal generation."""
    total_goals_generated: int = 0
    goals_achieved: int = 0
    goals_failed: int = 0
    goals_abandoned: int = 0
    avg_information_gain: float = 0.0
    avg_completion_time: float = 0.0


class WorldModelInterface:
    """Interface for world model used by goal generator."""

    def get_uncertainty(self, state: np.ndarray) -> float:
        """Get uncertainty at state."""
        raise NotImplementedError

    def get_high_uncertainty_regions(self) -> List[np.ndarray]:
        """Get regions with high uncertainty."""
        raise NotImplementedError

    def predict_next_state(self, state: np.ndarray, action: int) -> np.ndarray:
        """Predict next state."""
        raise NotImplementedError

    def get_prediction_error(self, state: np.ndarray, action: int, actual_next: np.ndarray) -> float:
        """Get prediction error."""
        raise NotImplementedError


class CompetenceModel:
    """Tracks competence (skill) levels across different tasks/regions."""

    def __init__(self, num_skills: int = 10):
        self.num_skills = num_skills
        self.competence = np.zeros(num_skills)
        self.attempts = np.zeros(num_skills)
        self.successes = np.zeros(num_skills)
        self.learning_progress = np.zeros(num_skills)
        self._history_window = 100
        self._recent_outcomes: Dict[int, List[bool]] = defaultdict(list)

    def update(self, skill_id: int, success: bool):
        """Update competence for a skill."""
        self.attempts[skill_id] += 1
        if success:
            self.successes[skill_id] += 1

        # Track recent outcomes
        self._recent_outcomes[skill_id].append(success)
        if len(self._recent_outcomes[skill_id]) > self._history_window:
            self._recent_outcomes[skill_id].pop(0)

        # Update competence (success rate)
        self.competence[skill_id] = self.successes[skill_id] / max(self.attempts[skill_id], 1)

        # Calculate learning progress (derivative of competence)
        outcomes = self._recent_outcomes[skill_id]
        if len(outcomes) >= 20:
            old_rate = sum(outcomes[:len(outcomes) // 2]) / (len(outcomes) // 2)
            new_rate = sum(outcomes[len(outcomes) // 2:]) / (len(outcomes) - len(outcomes) // 2)
            self.learning_progress[skill_id] = new_rate - old_rate

    def get_competence_gap(self, skill_id: int, target_competence: float = 0.9) -> float:
        """Get gap between current and target competence."""
        return max(0, target_competence - self.competence[skill_id])

    def get_skills_with_high_learning_progress(self, threshold: float = 0.1) -> List[int]:
        """Get skills where learning is progressing well."""
        return [i for i in range(self.num_skills) if self.learning_progress[i] > threshold]

    def get_skills_needing_practice(self, min_attempts: int = 10, max_competence: float = 0.5) -> List[int]:
        """Get skills that need more practice."""
        return [
            i for i in range(self.num_skills)
            if self.attempts[i] < min_attempts or self.competence[i] < max_competence
        ]


class AutonomousGoalGenerator:
    """
    Generates goals autonomously based on internal drives.

    Uses prediction errors, uncertainty, and competence gaps to
    create meaningful self-directed goals.
    """

    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        num_skills: int = 10,
        max_active_goals: int = 5,
        curiosity_weight: float = 0.4,
        competence_weight: float = 0.3,
        exploration_weight: float = 0.3,
        goal_timeout_steps: int = 1000
    ):
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.max_active_goals = max_active_goals
        self.curiosity_weight = curiosity_weight
        self.competence_weight = competence_weight
        self.exploration_weight = exploration_weight
        self.goal_timeout_steps = goal_timeout_steps

        # Competence model
        self.competence_model = CompetenceModel(num_skills)

        # Goal storage
        self.goals: Dict[str, Goal] = {}
        self.active_goals: List[str] = []
        self._goal_counter = 0

        # Observation history for curiosity
        self.observation_history: List[np.ndarray] = []
        self.prediction_errors: List[float] = []
        self._max_history = 10000

        # Statistics
        self.stats = GoalGeneratorStats()

    def _generate_goal_id(self) -> str:
        """Generate unique goal ID."""
        self._goal_counter += 1
        return f"goal_{self._goal_counter:06d}"

    def observe(
        self,
        state: np.ndarray,
        action: int,
        next_state: np.ndarray,
        prediction_error: float
    ):
        """
        Observe a state transition.

        Updates internal models and may trigger goal generation.
        """
        self.observation_history.append(state.copy())
        self.prediction_errors.append(prediction_error)

        # Trim history
        if len(self.observation_history) > self._max_history:
            self.observation_history.pop(0)
            self.prediction_errors.pop(0)

        # Check for surprising observations (high prediction error)
        if len(self.prediction_errors) > 10:
            avg_error = np.mean(self.prediction_errors[-10:])
            if prediction_error > 2 * avg_error:
                # Generate curiosity goal
                goal = self._generate_curiosity_goal(next_state, prediction_error)
                if goal:
                    self._add_goal(goal)

    def generate_goals(
        self,
        current_state: np.ndarray,
        world_model: Optional[WorldModelInterface] = None
    ) -> List[Goal]:
        """
        Generate new goals based on current state and internal drives.

        Args:
            current_state: Current observation
            world_model: Optional world model for uncertainty estimation

        Returns:
            List of newly generated goals
        """
        new_goals = []

        # Don't generate if at capacity
        if len(self.active_goals) >= self.max_active_goals:
            return new_goals

        # 1. Generate exploration goals (from uncertainty)
        if world_model is not None:
            exploration_goals = self._generate_exploration_goals(world_model)
            new_goals.extend(exploration_goals)

        # 2. Generate learning goals (from competence gaps)
        learning_goals = self._generate_learning_goals()
        new_goals.extend(learning_goals)

        # 3. Generate curiosity goals (from prediction errors)
        if self.prediction_errors:
            curiosity_goals = self._generate_curiosity_goals_from_history()
            new_goals.extend(curiosity_goals)

        # Score and prioritize goals
        scored_goals = []
        for goal in new_goals:
            score = self._score_goal(goal)
            scored_goals.append((score, goal))

        # Sort by score and add top goals
        scored_goals.sort(reverse=True, key=lambda x: x[0])

        added_goals = []
        for score, goal in scored_goals:
            if len(self.active_goals) >= self.max_active_goals:
                break
            self._add_goal(goal)
            added_goals.append(goal)

        return added_goals

    def _generate_exploration_goals(self, world_model: WorldModelInterface) -> List[Goal]:
        """Generate goals to explore uncertain regions."""
        goals = []

        try:
            uncertain_regions = world_model.get_high_uncertainty_regions()

            for i, region in enumerate(uncertain_regions[:3]):  # Top 3
                goal = Goal(
                    id=self._generate_goal_id(),
                    goal_type=GoalType.EXPLORATION,
                    description=f"Explore uncertain region {i + 1}",
                    target_state=region,
                    target_region=(region, np.ones(self.state_dim) * 0.5),
                    priority=GoalPriority.MEDIUM,
                    information_gain=world_model.get_uncertainty(region)
                )
                goals.append(goal)
        except Exception as e:
            logger.warning(f"Could not generate exploration goals: {e}")

        return goals

    def _generate_learning_goals(self) -> List[Goal]:
        """Generate goals to improve competence."""
        goals = []

        # Find skills needing practice
        skills_to_practice = self.competence_model.get_skills_needing_practice()

        for skill_id in skills_to_practice[:2]:  # Top 2
            competence_gap = self.competence_model.get_competence_gap(skill_id)
            goal = Goal(
                id=self._generate_goal_id(),
                goal_type=GoalType.LEARNING,
                description=f"Improve skill {skill_id} (current: {self.competence_model.competence[skill_id]:.2f})",
                priority=GoalPriority.MEDIUM,
                competence_gap=competence_gap
            )
            goals.append(goal)

        # Find skills with high learning progress (zone of proximal development)
        progressing_skills = self.competence_model.get_skills_with_high_learning_progress()

        for skill_id in progressing_skills[:1]:  # Top 1
            goal = Goal(
                id=self._generate_goal_id(),
                goal_type=GoalType.MASTERY,
                description=f"Master skill {skill_id} (high learning progress)",
                priority=GoalPriority.HIGH,
                intrinsic_value=self.competence_model.learning_progress[skill_id]
            )
            goals.append(goal)

        return goals

    def _generate_curiosity_goal(self, state: np.ndarray, prediction_error: float) -> Optional[Goal]:
        """Generate curiosity goal from surprising observation."""
        if prediction_error < 0.1:  # Not surprising enough
            return None

        return Goal(
            id=self._generate_goal_id(),
            goal_type=GoalType.CURIOSITY,
            description=f"Investigate surprising state (PE: {prediction_error:.3f})",
            target_state=state.copy(),
            priority=GoalPriority.MEDIUM if prediction_error < 0.5 else GoalPriority.HIGH,
            information_gain=prediction_error
        )

    def _generate_curiosity_goals_from_history(self) -> List[Goal]:
        """Generate curiosity goals from historical prediction errors."""
        if len(self.prediction_errors) < 10:
            return []

        goals = []
        errors = np.array(self.prediction_errors[-100:])
        states = self.observation_history[-100:]

        # Find peaks in prediction error
        threshold = np.percentile(errors, 90)
        peaks = np.where(errors > threshold)[0]

        for peak_idx in peaks[-3:]:  # Top 3 recent peaks
            if peak_idx < len(states):
                goal = Goal(
                    id=self._generate_goal_id(),
                    goal_type=GoalType.CURIOSITY,
                    description=f"Revisit surprising state from step {peak_idx}",
                    target_state=states[peak_idx].copy(),
                    priority=GoalPriority.LOW,
                    information_gain=errors[peak_idx]
                )
                goals.append(goal)

        return goals

    def _score_goal(self, goal: Goal) -> float:
        """Score a goal based on internal drives."""
        score = 0.0

        # Information gain (curiosity)
        score += self.curiosity_weight * goal.information_gain

        # Competence gap (learning)
        score += self.competence_weight * goal.competence_gap

        # Intrinsic value
        score += 0.2 * goal.intrinsic_value

        # Priority bonus
        priority_bonus = {
            GoalPriority.CRITICAL: 1.0,
            GoalPriority.HIGH: 0.5,
            GoalPriority.MEDIUM: 0.2,
            GoalPriority.LOW: 0.1,
            GoalPriority.BACKGROUND: 0.0
        }
        score += priority_bonus.get(goal.priority, 0.0)

        # Novelty bonus (new goal types)
        active_types = [self.goals[gid].goal_type for gid in self.active_goals if gid in self.goals]
        if goal.goal_type not in active_types:
            score += 0.3

        return score

    def _add_goal(self, goal: Goal):
        """Add goal to active goals."""
        self.goals[goal.id] = goal
        self.active_goals.append(goal.id)
        goal.status = GoalStatus.ACTIVE
        self.stats.total_goals_generated += 1
        logger.info(f"New goal: {goal.description}")

    def update_goal_status(
        self,
        goal_id: str,
        achieved: bool = False,
        failed: bool = False
    ):
        """Update the status of a goal."""
        if goal_id not in self.goals:
            return

        goal = self.goals[goal_id]

        if achieved:
            goal.status = GoalStatus.ACHIEVED
            self.stats.goals_achieved += 1
            if goal_id in self.active_goals:
                self.active_goals.remove(goal_id)
            logger.info(f"Goal achieved: {goal.description}")

        elif failed:
            goal.attempts += 1
            if goal.attempts >= goal.max_attempts:
                goal.status = GoalStatus.FAILED
                self.stats.goals_failed += 1
                if goal_id in self.active_goals:
                    self.active_goals.remove(goal_id)
                logger.info(f"Goal failed: {goal.description}")

    def get_active_goals(self) -> List[Goal]:
        """Get list of active goals."""
        return [self.goals[gid] for gid in self.active_goals if gid in self.goals]

    def get_highest_priority_goal(self) -> Optional[Goal]:
        """Get the highest priority active goal."""
        active = self.get_active_goals()
        if not active:
            return None
        return min(active, key=lambda g: g.priority.value)

    def check_goal_achieved(self, goal_id: str, current_state: np.ndarray) -> bool:
        """Check if a goal has been achieved."""
        if goal_id not in self.goals:
            return False

        goal = self.goals[goal_id]

        if goal.target_state is not None:
            distance = np.linalg.norm(current_state - goal.target_state)
            threshold = 0.5  # Could be goal-specific
            return distance < threshold

        if goal.target_region is not None:
            center, radius = goal.target_region
            distance = np.linalg.norm(current_state - center)
            return distance < np.mean(radius)

        return False

    def decompose_goal(self, goal_id: str, subgoals: List[Goal]):
        """Decompose a goal into subgoals."""
        if goal_id not in self.goals:
            return

        parent_goal = self.goals[goal_id]

        for subgoal in subgoals:
            subgoal.parent_goal_id = goal_id
            self._add_goal(subgoal)
            parent_goal.subgoal_ids.append(subgoal.id)
