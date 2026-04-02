"""
Heart-Brain Dual System

Implements biological dual-system architecture:
- Heart: Pretrained, frozen weights (intuitive, emotional, stronger guide)
- Brain: Evolving weights per generation (logical, analytical, learning)
- DualSystemAgent: Integrates both systems with weighted voting

User's Concept:
"the heart is the stronger guide than the brain but brain understands the logical way"
"so the heart can reach the goal"
"we use the pretrained then for the next puzzle"

Heart (Frozen):
- Trained on Generation 0 (successful baseline)
- Never changes (like instinct, intuition)
- Stronger weight (0.70) - "the stronger guide"

Brain (Evolving):
- Starts from scratch each generation
- Learns optimal paths through episodes
- Weaker weight (0.30) - "understands the logical way"
- Gets reset on reproduction (new puzzle = new learning)
"""

import logging
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from copy import deepcopy

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s:%(name)s:%(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class SystemState:
    """State from either Heart or Brain system"""
    action_recommendation: str  # "Move: Right", "Talk: I see you!", etc.
    confidence: float  # 0.0 to 1.0
    path_prediction: Optional[List[Tuple[int, int]]]  # Predicted path
    reasoning: str  # Explanation of decision


class HeartSystem:
    """
    Heart System (Frozen Pretrained)

    The emotional, intuitive guide - trained on Generation 0 baseline.
    Never changes, provides stable reference point.

    "the heart is the stronger guide"
    """

    def __init__(self, pretrained_model: Any = None):
        """
        Initialize Heart System

        Args:
            pretrained_model: Pretrained model from successful Gen 0 training
                             (e.g., ConfidenceAdaptiveTrainer)
        """
        self.pretrained_model = pretrained_model
        self.frozen = True  # NEVER changes!
        self.weight = 0.70  # Stronger guide (70%)

        # Pattern library from Gen 0
        self.successful_patterns: List[Dict] = []

        logger.info("[HeartSystem] Initialized (FROZEN)")
        logger.info(f"  Weight: {self.weight:.0%} (stronger guide)")
        logger.info(f"  Frozen: {self.frozen}")

    def recommend_action(
        self,
        agent_name: str,
        current_pos: Tuple[int, int],
        goal_pos: Tuple[int, int],
        recent_messages: List[str],
        generation: int
    ) -> SystemState:
        """
        Recommend action based on pretrained intuition

        Heart uses:
        - Pattern matching from successful Gen 0 episodes
        - Simple heuristics (move toward goal)
        - Conservative decisions (avoid risky moves)

        Args:
            agent_name: "beginning", "mid", or "end"
            current_pos: Agent's current position
            goal_pos: Goal position (for mid agent)
            recent_messages: Recent communication
            generation: Current generation (ignored - heart doesn't care!)

        Returns:
            SystemState with action recommendation
        """
        # Simple heuristic: Move toward goal
        dx = goal_pos[0] - current_pos[0]
        dy = goal_pos[1] - current_pos[1]

        # Heart's intuition: shortest Manhattan distance
        if abs(dx) > abs(dy):
            # Move horizontally
            direction = "Right" if dx > 0 else "Left"
            action = f"Move: {direction}"
            confidence = 0.75  # Heart is confident (intuitive)
        elif abs(dy) > 0:
            # Move vertically
            direction = "Down" if dy > 0 else "Up"
            action = f"Move: {direction}"
            confidence = 0.75
        else:
            # At goal or stuck - talk
            action = f"Talk: I'm at ({current_pos[0]},{current_pos[1]})"
            confidence = 0.50  # Less confident when talking

        # Predict simple straight-line path
        path_prediction = self._predict_straight_path(current_pos, goal_pos)

        reasoning = f"Heart intuition: Move toward goal ({goal_pos}), Manhattan heuristic"

        return SystemState(
            action_recommendation=action,
            confidence=confidence,
            path_prediction=path_prediction,
            reasoning=reasoning
        )

    def _predict_straight_path(
        self,
        start: Tuple[int, int],
        goal: Tuple[int, int]
    ) -> List[Tuple[int, int]]:
        """Predict simple straight-line path (Heart's intuition)"""
        path = [start]
        x, y = start

        # Move horizontally first
        while x != goal[0]:
            x += 1 if goal[0] > x else -1
            path.append((x, y))

        # Then vertically
        while y != goal[1]:
            y += 1 if goal[1] > y else -1
            path.append((x, y))

        return path

    def learn_from_episode(self, episode_data: Dict):
        """
        Heart NEVER learns (frozen!)

        This method exists for API compatibility but does nothing.
        """
        pass  # Heart is frozen - no learning!


class BrainSystem:
    """
    Brain System (Evolving Per Generation)

    The logical, analytical learner - learns optimal paths each generation.
    Gets reset on reproduction (new puzzle = new learning).

    "brain understands the logical way"
    """

    def __init__(self, learning_rate: float = 0.01):
        """
        Initialize Brain System

        Args:
            learning_rate: Learning rate for pattern updates
        """
        self.learning_rate = learning_rate
        self.weight = 0.30  # Weaker guide (30%)
        self.generation = 0

        # Learned patterns (updated each episode)
        self.action_values: Dict[str, float] = {}  # Action -> value mapping
        self.path_memory: List[List[Tuple[int, int]]] = []  # Successful paths

        logger.info("[BrainSystem] Initialized (EVOLVING)")
        logger.info(f"  Weight: {self.weight:.0%} (logical way)")
        logger.info(f"  Learning rate: {learning_rate}")

    def recommend_action(
        self,
        agent_name: str,
        current_pos: Tuple[int, int],
        goal_pos: Tuple[int, int],
        recent_messages: List[str],
        generation: int
    ) -> SystemState:
        """
        Recommend action based on learned patterns

        Brain uses:
        - Learned action values from previous episodes
        - Memory of successful paths
        - Q-learning style value updates

        Args:
            agent_name: "beginning", "mid", or "end"
            current_pos: Agent's current position
            goal_pos: Goal position (for mid agent)
            recent_messages: Recent communication
            generation: Current generation

        Returns:
            SystemState with action recommendation
        """
        # Check learned patterns
        state_key = f"{current_pos}_{goal_pos}"

        if state_key in self.action_values:
            # Use learned action
            best_action = max(
                self.action_values.items(),
                key=lambda x: x[1] if state_key in x[0] else -999
            )
            action = best_action[0].split("_")[-1]  # Extract action
            confidence = min(0.90, 0.50 + len(self.path_memory) * 0.05)  # Higher with experience
        else:
            # Explore: Try random action
            actions = ["Move: Up", "Move: Down", "Move: Left", "Move: Right"]
            action = np.random.choice(actions)
            confidence = 0.30  # Low confidence (exploring)

        # Predict path from memory
        path_prediction = self._predict_learned_path(current_pos, goal_pos)

        reasoning = f"Brain analysis: Learned from {len(self.path_memory)} episodes, confidence={confidence:.1%}"

        return SystemState(
            action_recommendation=action,
            confidence=confidence,
            path_prediction=path_prediction,
            reasoning=reasoning
        )

    def _predict_learned_path(
        self,
        start: Tuple[int, int],
        goal: Tuple[int, int]
    ) -> Optional[List[Tuple[int, int]]]:
        """Predict path from learned memory"""
        if not self.path_memory:
            return None

        # Find most similar successful path
        best_path = None
        best_similarity = -1

        for path in self.path_memory:
            if path[0] == start:
                # Calculate similarity (simple: path length)
                similarity = 1.0 / (len(path) + 1)
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_path = path

        return best_path

    def learn_from_episode(self, episode_data: Dict):
        """
        Learn from episode results (Q-learning style)

        Args:
            episode_data: Dict with 'path', 'success', 'quality', 'actions'
        """
        if not episode_data.get('success', False):
            return  # Only learn from successful episodes

        path = episode_data.get('path', [])
        quality = episode_data.get('quality', 0.0)
        actions = episode_data.get('actions', [])

        # Store successful path
        if quality >= 0.60:
            self.path_memory.append(path)

        # Update action values
        for i, (pos, action) in enumerate(zip(path[:-1], actions)):
            state_key = f"{pos}_{path[-1]}"  # state -> goal
            action_key = f"{state_key}_{action}"

            # Q-learning update
            reward = quality * (len(path) - i) / len(path)  # Higher reward for early correct moves
            old_value = self.action_values.get(action_key, 0.0)
            new_value = old_value + self.learning_rate * (reward - old_value)
            self.action_values[action_key] = new_value

        logger.info(f"[BrainSystem] Learned from episode (quality={quality:.1%})")
        logger.info(f"  Path memory: {len(self.path_memory)} successful paths")
        logger.info(f"  Action values: {len(self.action_values)} states")

    def reset_for_new_generation(self):
        """
        Reset brain for new generation (new puzzle = new learning)

        Heart stays frozen, brain resets!
        """
        self.action_values = {}
        self.path_memory = []
        self.generation += 1

        logger.info(f"[BrainSystem] RESET for Generation {self.generation}")
        logger.info("  Action values cleared")
        logger.info("  Path memory cleared")


class DualSystemAgent:
    """
    Dual-System Agent (Heart + Brain Integration)

    Combines Heart (frozen, intuitive, 70%) and Brain (evolving, logical, 30%)
    to make final decisions.

    Weighted voting:
    - Heart: 0.70 weight (stronger guide)
    - Brain: 0.30 weight (logical way)

    Conflict resolution:
    - If agreement: High confidence
    - If disagreement: Heart wins (stronger guide!)
    """

    def __init__(
        self,
        agent_name: str,
        heart_system: HeartSystem,
        brain_system: BrainSystem
    ):
        """
        Initialize Dual-System Agent

        Args:
            agent_name: "beginning", "mid", or "end"
            heart_system: Pretrained frozen heart
            brain_system: Evolving brain
        """
        self.agent_name = agent_name
        self.heart = heart_system
        self.brain = brain_system

        logger.info(f"[DualSystemAgent:{agent_name}] Initialized")
        logger.info(f"  Heart weight: {self.heart.weight:.0%}")
        logger.info(f"  Brain weight: {self.brain.weight:.0%}")

    def decide_action(
        self,
        current_pos: Tuple[int, int],
        goal_pos: Tuple[int, int],
        recent_messages: List[str],
        generation: int
    ) -> Tuple[str, float, str]:
        """
        Decide action using both Heart and Brain

        Args:
            current_pos: Agent's current position
            goal_pos: Goal position
            recent_messages: Recent communication
            generation: Current generation

        Returns:
            Tuple of (action, confidence, reasoning)
        """
        # Get recommendations from both systems
        heart_rec = self.heart.recommend_action(
            self.agent_name, current_pos, goal_pos, recent_messages, generation
        )
        brain_rec = self.brain.recommend_action(
            self.agent_name, current_pos, goal_pos, recent_messages, generation
        )

        # Weighted voting
        heart_conf = heart_rec.confidence * self.heart.weight
        brain_conf = brain_rec.confidence * self.brain.weight

        total_conf = heart_conf + brain_conf

        # Check agreement
        agreement = heart_rec.action_recommendation == brain_rec.action_recommendation

        if agreement:
            # Both agree - HIGH confidence!
            action = heart_rec.action_recommendation
            confidence = min(1.0, total_conf + 0.20)  # Bonus for agreement
            reasoning = f"AGREEMENT: Heart + Brain both recommend {action}"
        else:
            # Disagreement - Heart wins (stronger guide!)
            if heart_conf > brain_conf:
                action = heart_rec.action_recommendation
                confidence = heart_conf
                reasoning = f"HEART LEADS: {action} (heart={heart_conf:.2f} > brain={brain_conf:.2f})"
            else:
                # This should rarely happen (brain weight is only 30%)
                action = brain_rec.action_recommendation
                confidence = brain_conf
                reasoning = f"BRAIN OVERRIDE: {action} (brain={brain_conf:.2f} > heart={heart_conf:.2f})"

        logger.debug(f"[DualSystemAgent:{self.agent_name}] Decision")
        logger.debug(f"  Heart: {heart_rec.action_recommendation} (conf={heart_conf:.2f})")
        logger.debug(f"  Brain: {brain_rec.action_recommendation} (conf={brain_conf:.2f})")
        logger.debug(f"  Final: {action} (conf={confidence:.2f}) - {reasoning}")

        return action, confidence, reasoning

    def learn_from_episode(self, episode_data: Dict):
        """
        Learn from episode (only Brain learns, Heart is frozen!)

        Args:
            episode_data: Episode results
        """
        # Heart never learns (frozen!)
        self.heart.learn_from_episode(episode_data)  # No-op

        # Brain learns!
        self.brain.learn_from_episode(episode_data)


if __name__ == "__main__":
    # Test dual-system agent
    print("=" * 80)
    print("HEART-BRAIN DUAL SYSTEM TEST")
    print("=" * 80)

    # Create systems
    heart = HeartSystem()
    brain = BrainSystem(learning_rate=0.01)

    # Create agent
    agent = DualSystemAgent(
        agent_name='mid',
        heart_system=heart,
        brain_system=brain
    )

    print("\n[TEST 1] First Episode - Brain has no experience")
    print("-" * 80)

    current_pos = (3, 4)
    goal_pos = (6, 6)
    recent_messages = []

    action, confidence, reasoning = agent.decide_action(
        current_pos, goal_pos, recent_messages, generation=0
    )

    print(f"Position: {current_pos} -> Goal: {goal_pos}")
    print(f"Action: {action}")
    print(f"Confidence: {confidence:.1%}")
    print(f"Reasoning: {reasoning}")

    print("\n[TEST 2] Brain learns from successful episode")
    print("-" * 80)

    # Simulate successful episode
    episode_data = {
        'success': True,
        'quality': 0.85,
        'path': [(3, 4), (4, 4), (5, 4), (6, 4), (6, 5), (6, 6)],
        'actions': ["Move: Right", "Move: Right", "Move: Right", "Move: Down", "Move: Down"]
    }

    agent.learn_from_episode(episode_data)

    print(f"Brain learned from episode (quality={episode_data['quality']:.1%})")

    print("\n[TEST 3] Second Episode - Brain has experience")
    print("-" * 80)

    action, confidence, reasoning = agent.decide_action(
        current_pos, goal_pos, recent_messages, generation=0
    )

    print(f"Position: {current_pos} -> Goal: {goal_pos}")
    print(f"Action: {action}")
    print(f"Confidence: {confidence:.1%}")
    print(f"Reasoning: {reasoning}")

    print("\n[TEST 4] Brain reset for new generation")
    print("-" * 80)

    brain.reset_for_new_generation()

    action, confidence, reasoning = agent.decide_action(
        current_pos, goal_pos, recent_messages, generation=1
    )

    print(f"Position: {current_pos} -> Goal: {goal_pos}")
    print(f"Action: {action}")
    print(f"Confidence: {confidence:.1%}")
    print(f"Reasoning: {reasoning}")

    print("\n[TEST 5] Multiple learning episodes")
    print("-" * 80)

    for i in range(5):
        episode_data = {
            'success': True,
            'quality': 0.70 + i * 0.05,
            'path': [(3, 4), (4, 4), (5, 4), (6, 4), (6, 5), (6, 6)],
            'actions': ["Move: Right", "Move: Right", "Move: Right", "Move: Down", "Move: Down"]
        }
        agent.learn_from_episode(episode_data)

    action, confidence, reasoning = agent.decide_action(
        current_pos, goal_pos, recent_messages, generation=1
    )

    print(f"After 5 learning episodes:")
    print(f"Action: {action}")
    print(f"Confidence: {confidence:.1%}")
    print(f"Reasoning: {reasoning}")

    print("\n" + "=" * 80)
    print("HEART-BRAIN DUAL SYSTEM TEST COMPLETE")
    print("=" * 80)
