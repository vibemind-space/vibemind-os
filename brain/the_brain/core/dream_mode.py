"""
Dream Mode System (PHASE 5)

Implements offline consolidation and replay during idle time:

1. Experience Replay:
   - Replay episodic memories during idle periods
   - Prioritize high-importance and recent memories
   - Forward and backward replay (time-reversed sequences)

2. Offline Consolidation:
   - Strengthen important memories through repeated replay
   - Extract common patterns across experiences
   - Transfer learning from specific to general

3. Counterfactual Learning:
   - Generate "what-if" scenarios
   - Replay experiences with alternative decisions
   - Learn from hypothetical outcomes

4. Pattern Extraction:
   - Identify recurring task-decision patterns
   - Build schema-level knowledge
   - Generalize across similar experiences

5. Sleep/Wake Cycle:
   - Track active vs idle periods
   - Trigger consolidation during idle time
   - Balance replay with new learning

Based on neuroscience research:
- Hippocampal replay during sleep (Wilson & McNaughton, 1994)
- Memory consolidation theory (McClelland et al., 1995)
- Offline reinforcement learning (Lin, 1992)
- Schema learning and abstraction
"""

import logging
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from collections import defaultdict, Counter
import random
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class DreamState:
    """
    State of the dreaming brain
    """
    # Dream type
    dream_type: str  # 'replay', 'counterfactual', 'pattern_extraction'

    # Replayed experience
    original_task: str
    original_decision: str
    original_outcome: str

    # Counterfactual (if applicable)
    alternative_decision: Optional[str] = None
    hypothetical_outcome: Optional[str] = None

    # Consolidation metrics
    replay_count: int = 0
    memory_strength_delta: float = 0.0
    pattern_discovered: Optional[str] = None

    # Timestamp
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'dream_type': self.dream_type,
            'original_task': self.original_task,
            'original_decision': self.original_decision,
            'original_outcome': self.original_outcome,
            'alternative_decision': self.alternative_decision,
            'hypothetical_outcome': self.hypothetical_outcome,
            'replay_count': self.replay_count,
            'memory_strength_delta': self.memory_strength_delta,
            'pattern_discovered': self.pattern_discovered,
            'timestamp': self.timestamp
        }


@dataclass
class Pattern:
    """
    Discovered pattern across experiences
    """
    pattern_type: str  # Task type or feature
    decision_preference: str  # Most common decision
    success_rate: float  # Success rate for this pattern
    support: int  # Number of experiences supporting this pattern
    confidence: float  # Confidence in pattern (0-1)

    # Examples
    example_tasks: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'pattern_type': self.pattern_type,
            'decision_preference': self.decision_preference,
            'success_rate': self.success_rate,
            'support': self.support,
            'confidence': self.confidence,
            'example_tasks': self.example_tasks[:3]  # First 3 examples
        }


class DreamMode:
    """
    Dream Mode system for offline consolidation and replay

    Key features:
    - Experience replay during idle time
    - Counterfactual learning (what-if scenarios)
    - Pattern extraction and schema building
    - Memory strength adjustment
    """

    @classmethod
    def from_yaml(cls, yaml_config: dict) -> 'DreamMode':
        """Create DreamMode from YAML config dict (P5.72)."""
        dm = yaml_config.get('dream_mode', {})
        return cls(
            replay_rate=dm.get('replay_rate', 0.3),
            counterfactual_rate=dm.get('counterfactual_rate', 0.2),
            consolidation_threshold=dm.get('consolidation_threshold', 0.7),
            pattern_min_support=dm.get('pattern_min_support', 3),
            max_dreams_per_cycle=dm.get('max_dreams_per_cycle', 5),
        )

    def __init__(
        self,
        replay_rate: float = 0.3,  # Probability of replay per dream cycle
        counterfactual_rate: float = 0.2,  # Probability of counterfactual learning
        consolidation_threshold: float = 0.7,  # Min importance for consolidation
        pattern_min_support: int = 3,  # Min experiences to form pattern
        max_dreams_per_cycle: int = 5,  # Max dreams per sleep cycle
        seed: Optional[int] = None
    ):
        """
        Initialize dream mode system

        Args:
            replay_rate: Probability of replaying a memory
            counterfactual_rate: Probability of counterfactual scenario
            consolidation_threshold: Min importance to consolidate
            pattern_min_support: Min experiences needed for pattern
            max_dreams_per_cycle: Max dreams per sleep cycle
            seed: Random seed
        """
        self.replay_rate = replay_rate
        self.counterfactual_rate = counterfactual_rate
        self.consolidation_threshold = consolidation_threshold
        self.pattern_min_support = pattern_min_support
        self.max_dreams_per_cycle = max_dreams_per_cycle

        # Random state
        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)

        # Dream history
        self.dream_history: List[DreamState] = []

        # Discovered patterns
        self.patterns: Dict[str, Pattern] = {}

        # Statistics
        self.total_dreams = 0
        self.total_replays = 0
        self.total_counterfactuals = 0
        self.total_patterns_discovered = 0

        # State
        self.is_dreaming = False
        self.current_dream: Optional[DreamState] = None

    def enter_dream_state(self) -> None:
        """Enter dream/sleep state"""
        self.is_dreaming = True
        print(f"[DreamMode] Entering dream state...")

    def exit_dream_state(self) -> None:
        """Exit dream state"""
        self.is_dreaming = False
        print(f"[DreamMode] Exiting dream state. Dreams this cycle: {len([d for d in self.dream_history if d.timestamp.startswith(datetime.now().date().isoformat())])}")

    def select_memory_for_replay(
        self,
        episodic_memories: List[Any],
        prioritize_recent: bool = True,
        prioritize_important: bool = True,
        prioritize_failures: bool = False
    ) -> Optional[Any]:
        """
        Select a memory for replay

        Args:
            episodic_memories: List of episodic memory entries
            prioritize_recent: Give higher weight to recent memories
            prioritize_important: Give higher weight to important memories
            prioritize_failures: Give higher weight to failures (for learning)

        Returns:
            Selected memory or None
        """
        if not episodic_memories:
            return None

        # Compute selection weights
        weights = np.ones(len(episodic_memories))

        for i, memory in enumerate(episodic_memories):
            # Importance weighting
            if prioritize_important and hasattr(memory, 'importance'):
                weights[i] *= (memory.importance + 0.1)  # Avoid zero

            # Recency weighting (exponential decay)
            if prioritize_recent and hasattr(memory, 'retrieval_count'):
                # Less retrieved = more recent (in terms of attention)
                recency_bonus = np.exp(-0.1 * memory.retrieval_count)
                weights[i] *= (recency_bonus + 0.1)

            # Failure weighting (learn from mistakes)
            if prioritize_failures and hasattr(memory, 'outcome'):
                if memory.outcome == 'failure':
                    weights[i] *= 2.0

        # Normalize
        weights = weights / np.sum(weights)

        # Sample
        selected_idx = np.random.choice(len(episodic_memories), p=weights)
        return episodic_memories[selected_idx]

    def replay_experience(
        self,
        memory: Any,
        forward: bool = True
    ) -> DreamState:
        """
        Replay an experience

        Args:
            memory: Episodic memory to replay
            forward: If True, forward replay; if False, backward replay

        Returns:
            DreamState representing the replay
        """
        self.total_replays += 1

        # Create dream state
        dream = DreamState(
            dream_type='replay',
            original_task=memory.task,
            original_decision=memory.decision,
            original_outcome=memory.outcome,
            replay_count=1
        )

        # Strengthen memory slightly
        dream.memory_strength_delta = 0.05

        # Record dream
        self.dream_history.append(dream)
        self.total_dreams += 1

        return dream

    def generate_counterfactual(
        self,
        memory: Any,
        possible_decisions: List[str]
    ) -> DreamState:
        """
        Generate a counterfactual "what-if" scenario

        Args:
            memory: Original experience
            possible_decisions: List of possible alternative decisions

        Returns:
            DreamState with counterfactual scenario
        """
        self.total_counterfactuals += 1

        # Select alternative decision (different from original)
        alternatives = [d for d in possible_decisions if d != memory.decision]
        if not alternatives:
            alternatives = possible_decisions

        alternative_decision = random.choice(alternatives)

        # Simulate hypothetical outcome (simple heuristic)
        # In reality, this would use the planner to predict outcome
        if memory.outcome == 'failure':
            # If original failed, hypothetical has 30% chance of success
            hypothetical_outcome = 'success' if np.random.rand() < 0.3 else 'failure'
        else:
            # If original succeeded, hypothetical has 70% chance of success
            hypothetical_outcome = 'success' if np.random.rand() < 0.7 else 'failure'

        # Create counterfactual dream
        dream = DreamState(
            dream_type='counterfactual',
            original_task=memory.task,
            original_decision=memory.decision,
            original_outcome=memory.outcome,
            alternative_decision=alternative_decision,
            hypothetical_outcome=hypothetical_outcome,
            replay_count=1
        )

        # If counterfactual would have been better, strengthen alternative
        if memory.outcome == 'failure' and hypothetical_outcome == 'success':
            dream.memory_strength_delta = 0.1  # Learn from better alternative

        # Record dream
        self.dream_history.append(dream)
        self.total_dreams += 1

        return dream

    def extract_patterns(
        self,
        episodic_memories: List[Any]
    ) -> List[Pattern]:
        """
        Extract patterns from episodic memories

        Args:
            episodic_memories: List of episodic memories

        Returns:
            List of discovered patterns
        """
        if len(episodic_memories) < self.pattern_min_support:
            return []

        # Group by task type
        task_type_groups = defaultdict(list)
        for memory in episodic_memories:
            if hasattr(memory, 'task_type'):
                task_type_groups[memory.task_type].append(memory)

        new_patterns = []

        for task_type, memories in task_type_groups.items():
            if len(memories) < self.pattern_min_support:
                continue

            # Find most common decision
            decisions = [m.decision for m in memories]
            decision_counts = Counter(decisions)
            most_common_decision, count = decision_counts.most_common(1)[0]

            # Calculate success rate for this pattern
            successes = sum(1 for m in memories if m.outcome == 'success')
            success_rate = successes / len(memories)

            # Confidence based on support and consistency
            decision_consistency = count / len(memories)
            confidence = (decision_consistency + success_rate) / 2

            # Check if pattern already exists
            pattern_key = f"{task_type}_{most_common_decision}"

            if pattern_key not in self.patterns:
                # Create new pattern
                pattern = Pattern(
                    pattern_type=task_type,
                    decision_preference=most_common_decision,
                    success_rate=success_rate,
                    support=len(memories),
                    confidence=confidence,
                    example_tasks=[m.task for m in memories[:3]]
                )

                self.patterns[pattern_key] = pattern
                new_patterns.append(pattern)
                self.total_patterns_discovered += 1
            else:
                # Update existing pattern
                pattern = self.patterns[pattern_key]
                pattern.success_rate = success_rate
                pattern.support = len(memories)
                pattern.confidence = confidence
                pattern.example_tasks = [m.task for m in memories[:3]]

        return new_patterns

    def dream_cycle(
        self,
        episodic_memories: List[Any],
        possible_decisions: List[str],
        num_dreams: Optional[int] = None
    ) -> List[DreamState]:
        """
        Execute a complete dream cycle

        Args:
            episodic_memories: Episodic memories to consolidate
            possible_decisions: List of possible decisions
            num_dreams: Number of dreams to generate (default: max_dreams_per_cycle)

        Returns:
            List of dream states from this cycle
        """
        if not episodic_memories:
            return []

        self.enter_dream_state()

        if num_dreams is None:
            num_dreams = self.max_dreams_per_cycle

        cycle_dreams = []

        for _ in range(num_dreams):
            # Select memory
            memory = self.select_memory_for_replay(
                episodic_memories,
                prioritize_recent=True,
                prioritize_important=True,
                prioritize_failures=True  # Learn from mistakes
            )

            if memory is None:
                continue

            # Decide dream type
            if np.random.rand() < self.counterfactual_rate:
                # Counterfactual learning
                dream = self.generate_counterfactual(memory, possible_decisions)
            else:
                # Simple replay
                dream = self.replay_experience(memory, forward=np.random.rand() < 0.5)

            cycle_dreams.append(dream)

        # Pattern extraction
        new_patterns = self.extract_patterns(episodic_memories)

        if new_patterns:
            print(f"[DreamMode] Discovered {len(new_patterns)} new patterns")
            for pattern in new_patterns:
                print(f"  Pattern: {pattern.pattern_type} -> {pattern.decision_preference} "
                      f"(success={pattern.success_rate:.1%}, support={pattern.support})")

        # Radial Attention Network sleep training (if available)
        try:
            if hasattr(self, 'radial_trainer') and self.radial_trainer is not None:
                for epoch in range(3):  # 3 epochs per dream cycle
                    loss = self.radial_trainer.train_epoch(batch_size=32)
                    if loss > 0:
                        logger.info("Radial sleep epoch %d: loss=%.4f", epoch, loss)
        except Exception as e:
            logger.warning("Radial sleep training failed: %s", e)

        self.exit_dream_state()

        return cycle_dreams

    def get_pattern_for_task(
        self,
        task_type: str,
        min_confidence: float = 0.5
    ) -> Optional[Pattern]:
        """
        Get pattern for a task type

        Args:
            task_type: Task type
            min_confidence: Minimum confidence threshold

        Returns:
            Pattern if found, None otherwise
        """
        # Find all patterns for this task type
        matching_patterns = [
            p for p in self.patterns.values()
            if p.pattern_type == task_type and p.confidence >= min_confidence
        ]

        if not matching_patterns:
            return None

        # Return pattern with highest confidence
        return max(matching_patterns, key=lambda p: p.confidence)

    def get_statistics(self) -> Dict:
        """Get dream mode statistics"""
        return {
            'total_dreams': self.total_dreams,
            'total_replays': self.total_replays,
            'total_counterfactuals': self.total_counterfactuals,
            'total_patterns_discovered': self.total_patterns_discovered,
            'patterns': {
                key: pattern.to_dict()
                for key, pattern in self.patterns.items()
            },
            'recent_dreams': [
                d.to_dict() for d in self.dream_history[-10:]
            ]
        }

    def __repr__(self):
        return (
            f"DreamMode("
            f"dreams={self.total_dreams}, "
            f"patterns={self.total_patterns_discovered}, "
            f"dreaming={self.is_dreaming})"
        )


if __name__ == "__main__":
    print("=" * 70)
    print("DREAM MODE SYSTEM (PHASE 5)")
    print("=" * 70)
    print()
    print("This module implements offline consolidation and replay:")
    print("  - Experience replay during idle time")
    print("  - Counterfactual learning (what-if scenarios)")
    print("  - Pattern extraction and schema building")
    print("  - Memory strength adjustment")
    print()
    print("To test the complete system, run:")
    print("  python demos/test_dream_mode.py")
    print()
    print("=" * 70)
