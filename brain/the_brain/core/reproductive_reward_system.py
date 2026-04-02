"""
Reproductive Reward System

Implements biological reproduction concept:
- Connection (path found) = "Sex" = Reproduction opportunity
- Quality threshold required for reproduction (60% path quality + 60% success rate)
- Successful reproduction multiplies puzzle (1.5x harder next generation)
- Track generational lineage and extinction pressure

User's Concept:
"on match we have sex which means the agents would never stop until they get it"
"when we have sex we multiply the puzzle so we know it's solveable for now"
"the next puzzle which should be harder"
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s:%(name)s:%(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class ReproductionEvent:
    """Record of successful reproduction"""
    generation: int
    parent_fitness: float  # Path quality of parent generation
    offspring_difficulty: float  # Multiplier for next generation
    timestamp: datetime
    episode_count: int  # How many episodes to achieve reproduction
    connection_quality: float  # Final path quality when connected
    conversation_cost: float  # Total conversation penalties paid

    def to_dict(self) -> Dict:
        """Convert to JSON-serializable dict"""
        return {
            'generation': self.generation,
            'parent_fitness': self.parent_fitness,
            'offspring_difficulty': self.offspring_difficulty,
            'timestamp': self.timestamp.isoformat(),
            'episode_count': self.episode_count,
            'connection_quality': self.connection_quality,
            'conversation_cost': self.conversation_cost
        }


@dataclass
class GenerationStats:
    """Statistics for a single generation"""
    generation: int
    episodes_run: int
    successful_connections: int
    failed_connections: int
    total_conversation_cost: float
    best_path_quality: float
    average_path_quality: float
    reproduction_achieved: bool
    extinction: bool  # Failed to reproduce

    def to_dict(self) -> Dict:
        """Convert to JSON-serializable dict"""
        return {
            'generation': self.generation,
            'episodes_run': self.episodes_run,
            'successful_connections': self.successful_connections,
            'failed_connections': self.failed_connections,
            'total_conversation_cost': self.total_conversation_cost,
            'best_path_quality': self.best_path_quality,
            'average_path_quality': self.average_path_quality,
            'reproduction_achieved': self.reproduction_achieved,
            'extinction': self.extinction
        }


class ReproductiveRewardSystem:
    """
    Reproductive Reward System

    Manages reproduction events, difficulty scaling, and extinction pressure.

    Reproduction Conditions:
    1. Path quality >= 60% (optimal_length / actual_length)
    2. Success rate >= 60% (in recent episodes)
    3. Connection established (all 3 agents on same path)

    Reproduction Rewards:
    - Connection reward: 10,000 * (path_quality)^2
    - Generational bonus: +5,000 per generation survived
    - Quality bonus: +2,000 * path_quality if >= 80%

    Difficulty Scaling:
    - Each generation: 1.5x harder puzzle
    - Conversation penalties increase: -0.1 -> -0.5 -> -1.0 -> -2.0 -> -5.0

    Extinction:
    - If reproduction fails after max episodes -> generation extinct
    - Evolution stops, system reverts to previous generation
    """

    def __init__(
        self,
        difficulty_multiplier: float = 1.5,
        reproduction_quality_threshold: float = 0.60,
        reproduction_success_threshold: float = 0.60,
        connection_reward_base: float = 10000.0,
        generational_bonus: float = 5000.0,
        quality_bonus_threshold: float = 0.80,
        quality_bonus_reward: float = 2000.0,
        max_episodes_per_generation: int = 200
    ):
        """
        Initialize Reproductive Reward System

        Args:
            difficulty_multiplier: Multiplier for next generation difficulty (1.5 = 50% harder)
            reproduction_quality_threshold: Min path quality for reproduction (0.60 = 60%)
            reproduction_success_threshold: Min success rate for reproduction (0.60 = 60%)
            connection_reward_base: Base reward for connection (10,000)
            generational_bonus: Bonus per generation survived (5,000)
            quality_bonus_threshold: Quality threshold for bonus (0.80 = 80%)
            quality_bonus_reward: Bonus for high quality (2,000)
            max_episodes_per_generation: Max episodes before extinction
        """
        self.difficulty_multiplier = difficulty_multiplier
        self.reproduction_quality_threshold = reproduction_quality_threshold
        self.reproduction_success_threshold = reproduction_success_threshold
        self.connection_reward_base = connection_reward_base
        self.generational_bonus = generational_bonus
        self.quality_bonus_threshold = quality_bonus_threshold
        self.quality_bonus_reward = quality_bonus_reward
        self.max_episodes_per_generation = max_episodes_per_generation

        # Track generational history
        self.reproduction_events: List[ReproductionEvent] = []
        self.generation_stats: List[GenerationStats] = []

        # Current generation tracking
        self.current_generation = 0
        self.current_difficulty = 1.0  # Cumulative difficulty multiplier
        self.episodes_this_generation = 0
        self.connections_this_generation = 0
        self.path_qualities_this_generation: List[float] = []
        self.conversation_cost_this_generation = 0.0

        logger.info("[ReproductiveRewardSystem] Initialized")
        logger.info(f"  Difficulty multiplier: {difficulty_multiplier}x per generation")
        logger.info(f"  Reproduction thresholds: Quality >= {reproduction_quality_threshold:.0%}, Success >= {reproduction_success_threshold:.0%}")
        logger.info(f"  Connection reward: {connection_reward_base:,.0f} * quality^2")
        logger.info(f"  Max episodes per generation: {max_episodes_per_generation}")

    def calculate_connection_reward(
        self,
        path_quality: float,
        conversation_cost: float
    ) -> float:
        """
        Calculate reward for successful connection

        Reward Components:
        1. Base: 10,000 * (path_quality)^2
        2. Generational bonus: +5,000 per generation
        3. Quality bonus: +2,000 if quality >= 80%

        Args:
            path_quality: Path quality (optimal_length / actual_length)
            conversation_cost: Total conversation penalties paid

        Returns:
            Total reward (positive, massive for good quality!)
        """
        # Base exponential reward (quality matters A LOT!)
        base_reward = self.connection_reward_base * (path_quality ** 2)

        # Generational survival bonus
        gen_bonus = self.generational_bonus * self.current_generation

        # High-quality bonus
        quality_bonus = 0.0
        if path_quality >= self.quality_bonus_threshold:
            quality_bonus = self.quality_bonus_reward * path_quality

        total_reward = base_reward + gen_bonus + quality_bonus

        logger.info(f"[ReproductiveRewardSystem] Connection reward calculated")
        logger.info(f"  Base: {base_reward:,.0f} (quality={path_quality:.1%})")
        logger.info(f"  Gen bonus: {gen_bonus:,.0f} (generation={self.current_generation})")
        logger.info(f"  Quality bonus: {quality_bonus:,.0f}")
        logger.info(f"  Conversation cost: {conversation_cost:,.0f}")
        logger.info(f"  TOTAL REWARD: {total_reward:,.0f}")

        return total_reward

    def record_episode(
        self,
        connected: bool,
        path_quality: float,
        conversation_cost: float
    ):
        """
        Record episode results for reproduction tracking

        Args:
            connected: Whether agents successfully connected
            path_quality: Path quality if connected (0.0 if not)
            conversation_cost: Total conversation penalties paid
        """
        self.episodes_this_generation += 1
        self.conversation_cost_this_generation += abs(conversation_cost)

        if connected:
            self.connections_this_generation += 1
            self.path_qualities_this_generation.append(path_quality)

            logger.info(f"[ReproductiveRewardSystem] Connection {self.connections_this_generation}/{self.episodes_this_generation}")
            logger.info(f"  Quality: {path_quality:.1%}")
        else:
            logger.info(f"[ReproductiveRewardSystem] Failed episode {self.episodes_this_generation}/{self.max_episodes_per_generation}")

    def check_reproduction_conditions(self) -> Tuple[bool, Dict]:
        """
        Check if reproduction conditions are met

        Conditions:
        1. At least one successful connection
        2. Best path quality >= 60%
        3. Success rate >= 60% (in recent episodes)

        Returns:
            Tuple of (reproduction_possible, details_dict)
        """
        if self.connections_this_generation == 0:
            return False, {
                'reason': 'No successful connections',
                'connections': 0,
                'episodes': self.episodes_this_generation
            }

        # Check path quality
        best_quality = max(self.path_qualities_this_generation)
        avg_quality = sum(self.path_qualities_this_generation) / len(self.path_qualities_this_generation)

        quality_met = best_quality >= self.reproduction_quality_threshold

        # Check success rate
        success_rate = self.connections_this_generation / self.episodes_this_generation
        success_met = success_rate >= self.reproduction_success_threshold

        reproduction_possible = quality_met and success_met

        details = {
            'quality_met': quality_met,
            'success_met': success_met,
            'best_quality': best_quality,
            'avg_quality': avg_quality,
            'success_rate': success_rate,
            'connections': self.connections_this_generation,
            'episodes': self.episodes_this_generation,
            'reproduction_possible': reproduction_possible
        }

        logger.info(f"[ReproductiveRewardSystem] Reproduction check")
        logger.info(f"  Quality: {best_quality:.1%} (threshold: {self.reproduction_quality_threshold:.0%}) - {'PASS' if quality_met else 'FAIL'}")
        logger.info(f"  Success rate: {success_rate:.1%} (threshold: {self.reproduction_success_threshold:.0%}) - {'PASS' if success_met else 'FAIL'}")
        logger.info(f"  Reproduction: {'POSSIBLE' if reproduction_possible else 'NOT YET'}")

        return reproduction_possible, details

    def reproduce(self) -> Tuple[int, float]:
        """
        Trigger reproduction - multiply puzzle for next generation

        Returns:
            Tuple of (next_generation, new_difficulty)
        """
        # Calculate new difficulty
        new_difficulty = self.current_difficulty * self.difficulty_multiplier

        # Record reproduction event
        best_quality = max(self.path_qualities_this_generation)
        event = ReproductionEvent(
            generation=self.current_generation,
            parent_fitness=best_quality,
            offspring_difficulty=new_difficulty,
            timestamp=datetime.now(),
            episode_count=self.episodes_this_generation,
            connection_quality=best_quality,
            conversation_cost=self.conversation_cost_this_generation
        )
        self.reproduction_events.append(event)

        # Record generation stats
        avg_quality = sum(self.path_qualities_this_generation) / len(self.path_qualities_this_generation)
        stats = GenerationStats(
            generation=self.current_generation,
            episodes_run=self.episodes_this_generation,
            successful_connections=self.connections_this_generation,
            failed_connections=self.episodes_this_generation - self.connections_this_generation,
            total_conversation_cost=self.conversation_cost_this_generation,
            best_path_quality=best_quality,
            average_path_quality=avg_quality,
            reproduction_achieved=True,
            extinction=False
        )
        self.generation_stats.append(stats)

        logger.info("=" * 60)
        logger.info(f"[ReproductiveRewardSystem] REPRODUCTION EVENT - Generation {self.current_generation}")
        logger.info(f"  Parent fitness: {best_quality:.1%}")
        logger.info(f"  Episodes to reproduce: {self.episodes_this_generation}")
        logger.info(f"  Conversation cost: {self.conversation_cost_this_generation:,.0f}")
        logger.info(f"  NEW OFFSPRING - Generation {self.current_generation + 1}")
        logger.info(f"  Difficulty: {self.current_difficulty:.2f}x -> {new_difficulty:.2f}x")
        logger.info(f"  Multiplier: {self.difficulty_multiplier}x")
        logger.info("=" * 60)

        # Advance generation
        next_generation = self.current_generation + 1
        self.current_generation = next_generation
        self.current_difficulty = new_difficulty

        # Reset generation tracking
        self._reset_generation_tracking()

        return next_generation, new_difficulty

    def check_extinction(self) -> bool:
        """
        Check if current generation has gone extinct

        Extinction occurs if:
        - Max episodes reached without reproduction conditions met

        Returns:
            True if extinct, False otherwise
        """
        if self.episodes_this_generation >= self.max_episodes_per_generation:
            reproduction_possible, _ = self.check_reproduction_conditions()

            if not reproduction_possible:
                # EXTINCTION!
                avg_quality = (sum(self.path_qualities_this_generation) / len(self.path_qualities_this_generation)) if self.path_qualities_this_generation else 0.0
                best_quality = max(self.path_qualities_this_generation) if self.path_qualities_this_generation else 0.0

                stats = GenerationStats(
                    generation=self.current_generation,
                    episodes_run=self.episodes_this_generation,
                    successful_connections=self.connections_this_generation,
                    failed_connections=self.episodes_this_generation - self.connections_this_generation,
                    total_conversation_cost=self.conversation_cost_this_generation,
                    best_path_quality=best_quality,
                    average_path_quality=avg_quality,
                    reproduction_achieved=False,
                    extinction=True
                )
                self.generation_stats.append(stats)

                logger.warning("=" * 60)
                logger.warning(f"[ReproductiveRewardSystem] EXTINCTION - Generation {self.current_generation}")
                logger.warning(f"  Episodes run: {self.episodes_this_generation}/{self.max_episodes_per_generation}")
                logger.warning(f"  Connections: {self.connections_this_generation}")
                logger.warning(f"  Best quality: {best_quality:.1%} (needed: {self.reproduction_quality_threshold:.0%})")
                logger.warning("  Evolution stopped - failed to reproduce")
                logger.warning("=" * 60)

                return True

        return False

    def _reset_generation_tracking(self):
        """Reset tracking for new generation"""
        self.episodes_this_generation = 0
        self.connections_this_generation = 0
        self.path_qualities_this_generation = []
        self.conversation_cost_this_generation = 0.0

    def get_lineage_summary(self) -> Dict:
        """
        Get summary of all reproductive events (lineage)

        Returns:
            Dict with generational history
        """
        return {
            'current_generation': self.current_generation,
            'current_difficulty': self.current_difficulty,
            'total_reproductions': len(self.reproduction_events),
            'reproduction_events': [e.to_dict() for e in self.reproduction_events],
            'generation_stats': [s.to_dict() for s in self.generation_stats],
            'extinct': any(s.extinction for s in self.generation_stats)
        }


if __name__ == "__main__":
    # Test reproductive reward system
    print("=" * 80)
    print("REPRODUCTIVE REWARD SYSTEM TEST")
    print("=" * 80)

    # Create system
    system = ReproductiveRewardSystem(
        difficulty_multiplier=1.5,
        reproduction_quality_threshold=0.60,
        reproduction_success_threshold=0.60,
        max_episodes_per_generation=200
    )

    print("\n[TEST 1] Simulate Generation 0 - Successful Reproduction")
    print("-" * 80)

    # Simulate 15 episodes with improving quality
    for i in range(15):
        connected = i >= 5  # Start connecting after episode 5
        quality = min(0.95, 0.40 + i * 0.05) if connected else 0.0
        conversation_cost = -50.0 - i * 5  # Increasing conversation cost

        system.record_episode(connected, quality, conversation_cost)

        if connected and quality >= 0.80:
            reward = system.calculate_connection_reward(quality, conversation_cost)
            print(f"Episode {i+1}: Connected, quality={quality:.1%}, reward={reward:,.0f}")

    # Check reproduction
    can_reproduce, details = system.check_reproduction_conditions()
    print(f"\nReproduction check: {can_reproduce}")
    print(f"Details: {details}")

    if can_reproduce:
        next_gen, new_diff = system.reproduce()
        print(f"\nReproduction successful!")
        print(f"Next generation: {next_gen}")
        print(f"New difficulty: {new_diff:.2f}x")

    print("\n[TEST 2] Simulate Generation 1 - Extinction Scenario")
    print("-" * 80)

    # Simulate 200 episodes with poor quality (extinction)
    for i in range(50):  # Only 50 episodes, but low quality
        connected = i % 3 == 0  # Only 33% connection rate
        quality = 0.30 if connected else 0.0  # Below threshold!
        conversation_cost = -100.0

        system.record_episode(connected, quality, conversation_cost)

    # Check extinction
    system.episodes_this_generation = 200  # Force max episodes
    extinct = system.check_extinction()
    print(f"\nExtinction check: {extinct}")

    print("\n[TEST 3] Lineage Summary")
    print("-" * 80)
    lineage = system.get_lineage_summary()
    print(f"Total generations: {lineage['current_generation']}")
    print(f"Total reproductions: {lineage['total_reproductions']}")
    print(f"Extinct: {lineage['extinct']}")

    print("\nGeneration Stats:")
    for stat in lineage['generation_stats']:
        print(f"  Gen {stat['generation']}: {stat['episodes_run']} episodes, "
              f"{stat['successful_connections']} connections, "
              f"best quality {stat['best_path_quality']:.1%}, "
              f"reproduction={'YES' if stat['reproduction_achieved'] else 'NO'}, "
              f"extinct={'YES' if stat['extinction'] else 'NO'}")

    print("\n" + "=" * 80)
    print("REPRODUCTIVE REWARD SYSTEM TEST COMPLETE")
    print("=" * 80)
