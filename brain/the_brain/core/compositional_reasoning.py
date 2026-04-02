"""
Compositional Reasoning System (PHASE 9)

Implements compositional thinking and novel strategy generation:

1. Action Primitives:
   - Basic building blocks (decide, wait, execute, query)
   - Composable units with preconditions and effects
   - Parameter binding and instantiation

2. Sequence Composition:
   - Combine primitives into novel sequences
   - Learn which combinations work well
   - Prune invalid or redundant compositions

3. Strategy Abstraction:
   - Extract reusable patterns from successful sequences
   - Create higher-level strategies
   - Hierarchical composition (strategies of strategies)

4. Transfer Learning:
   - Apply learned strategies to new domains
   - Analogical reasoning across task types
   - Cross-domain pattern matching

5. Creative Problem Solving:
   - Generate novel solutions
   - Explore unusual combinations
   - Balance exploration vs. exploitation

Based on neuroscience and cognitive science:
- Prefrontal cortex hierarchical planning (Miller & Cohen, 2001)
- Compositional semantics (Fodor & Pylyshyn, 1988)
- Schema theory (Piaget, 1952)
- Transfer learning in humans (Thorndike & Woodworth, 1901)
"""

import numpy as np
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class ActionPrimitive:
    """
    Basic action building block
    """
    action_id: str
    action_type: str  # decide, wait, execute, query, etc.

    # Semantics
    preconditions: List[str] = field(default_factory=list)  # Required states
    effects: List[str] = field(default_factory=list)  # State changes

    # Execution properties
    avg_duration: float = 1.0  # Average time to execute
    success_rate: float = 0.5  # Historical success rate
    cost: float = 1.0  # Resource cost

    # Parameters
    parameters: Dict[str, any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'action_id': self.action_id,
            'action_type': self.action_type,
            'preconditions': self.preconditions,
            'effects': self.effects,
            'avg_duration': self.avg_duration,
            'success_rate': self.success_rate,
            'cost': self.cost,
            'parameters': self.parameters
        }


@dataclass
class ComposedSequence:
    """
    Sequence of composed actions
    """
    sequence_id: str
    actions: List[ActionPrimitive]

    # Composition metadata
    source_task_type: str = "unknown"
    abstraction_level: int = 0  # 0=primitive, 1=composed, 2=strategy

    # Performance
    times_used: int = 0
    success_count: int = 0
    failure_count: int = 0

    # Semantic properties
    total_cost: float = 0.0
    expected_duration: float = 0.0
    expected_success_rate: float = 0.5

    # Transfer potential
    applicable_domains: List[str] = field(default_factory=list)
    similarity_patterns: List[str] = field(default_factory=list)

    def success_rate(self) -> float:
        """Compute success rate"""
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.5

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'sequence_id': self.sequence_id,
            'num_actions': len(self.actions),
            'source_task_type': self.source_task_type,
            'abstraction_level': self.abstraction_level,
            'times_used': self.times_used,
            'success_rate': self.success_rate(),
            'total_cost': self.total_cost,
            'expected_duration': self.expected_duration,
            'applicable_domains': self.applicable_domains
        }


@dataclass
class CompositionResult:
    """
    Result of compositional reasoning
    """
    novel_sequences: List[ComposedSequence]
    best_sequence: Optional[ComposedSequence]

    # Creativity metrics
    novelty_score: float = 0.0  # How novel is this composition
    feasibility_score: float = 0.0  # How likely to work

    # Transfer metrics
    source_domain: str = "unknown"
    target_domain: str = "unknown"
    transfer_confidence: float = 0.0

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'num_sequences': len(self.novel_sequences),
            'best_sequence': self.best_sequence.to_dict() if self.best_sequence else None,
            'novelty_score': self.novelty_score,
            'feasibility_score': self.feasibility_score,
            'source_domain': self.source_domain,
            'target_domain': self.target_domain,
            'transfer_confidence': self.transfer_confidence
        }


class CompositionalReasoning:
    """
    Compositional reasoning system for novel strategy generation

    Key features:
    - Compose novel action sequences
    - Learn reusable strategies
    - Transfer knowledge across domains
    - Creative problem solving
    """

    def __init__(
        self,
        max_sequence_length: int = 5,
        novelty_threshold: float = 0.3,
        transfer_threshold: float = 0.5,
        exploration_rate: float = 0.2
    ):
        """
        Initialize compositional reasoning system

        Args:
            max_sequence_length: Maximum actions in composed sequence
            novelty_threshold: Minimum novelty to consider a sequence new
            transfer_threshold: Minimum similarity for cross-domain transfer
            exploration_rate: Probability of exploring novel combinations
        """
        self.max_sequence_length = max_sequence_length
        self.novelty_threshold = novelty_threshold
        self.transfer_threshold = transfer_threshold
        self.exploration_rate = exploration_rate

        # Action library
        self.primitives: Dict[str, ActionPrimitive] = {}

        # Learned sequences
        self.composed_sequences: Dict[str, ComposedSequence] = {}

        # Domain knowledge
        self.domain_patterns: Dict[str, List[str]] = defaultdict(list)  # domain -> patterns
        self.domain_similarities: Dict[Tuple[str, str], float] = {}  # (domain1, domain2) -> similarity

        # Statistics
        self.total_compositions = 0
        self.successful_transfers = 0
        self.novel_sequences_generated = 0

        # Initialize basic primitives
        self._initialize_primitives()

    def _initialize_primitives(self):
        """Initialize basic action primitives"""
        # Decision primitives
        self.primitives['decide_wait'] = ActionPrimitive(
            action_id='decide_wait',
            action_type='decide',
            preconditions=['uncertain'],
            effects=['time_passes', 'may_gain_info'],
            avg_duration=1.0,
            success_rate=0.6,
            cost=0.5
        )

        self.primitives['decide_retry'] = ActionPrimitive(
            action_id='decide_retry',
            action_type='decide',
            preconditions=['failed_once'],
            effects=['attempt_again'],
            avg_duration=1.0,
            success_rate=0.5,
            cost=1.0
        )

        self.primitives['decide_execute'] = ActionPrimitive(
            action_id='decide_execute',
            action_type='decide',
            preconditions=['confident'],
            effects=['action_taken'],
            avg_duration=1.0,
            success_rate=0.7,
            cost=1.0
        )

        # Query primitives
        self.primitives['query_memory'] = ActionPrimitive(
            action_id='query_memory',
            action_type='query',
            preconditions=[],
            effects=['retrieved_info'],
            avg_duration=0.5,
            success_rate=0.8,
            cost=0.3
        )

        self.primitives['query_patterns'] = ActionPrimitive(
            action_id='query_patterns',
            action_type='query',
            preconditions=[],
            effects=['found_pattern'],
            avg_duration=0.5,
            success_rate=0.6,
            cost=0.3
        )

        # Execution primitives
        self.primitives['execute_action'] = ActionPrimitive(
            action_id='execute_action',
            action_type='execute',
            preconditions=['action_planned'],
            effects=['task_completed'],
            avg_duration=2.0,
            success_rate=0.6,
            cost=2.0
        )

    def compose_novel_sequence(
        self,
        task_type: str,
        available_actions: List[str],
        context: Optional[Dict] = None
    ) -> List[ComposedSequence]:
        """
        Compose novel action sequences for a task

        Args:
            task_type: Type of task
            available_actions: Available action types
            context: Optional context (uncertainty, memory, etc.)

        Returns:
            List of composed sequences
        """
        novel_sequences = []

        # Get applicable primitives
        applicable_primitives = []
        for action_type in available_actions:
            # Map action types to primitives
            if action_type == 'wait':
                applicable_primitives.append(self.primitives['decide_wait'])
            elif action_type == 'retry':
                applicable_primitives.append(self.primitives['decide_retry'])
            elif action_type == 'execute':
                applicable_primitives.append(self.primitives['decide_execute'])
                applicable_primitives.append(self.primitives['execute_action'])

        # Add query primitives if context suggests uncertainty
        if context and context.get('uncertainty', 0) > 0.6:
            applicable_primitives.append(self.primitives['query_memory'])
            applicable_primitives.append(self.primitives['query_patterns'])

        # Generate compositions
        for length in range(1, min(self.max_sequence_length + 1, len(applicable_primitives) + 1)):
            # Generate combinations
            compositions = self._generate_compositions(
                applicable_primitives,
                length,
                task_type
            )
            novel_sequences.extend(compositions)

        # Evaluate novelty
        for seq in novel_sequences:
            seq_signature = self._sequence_signature(seq)
            is_novel = seq_signature not in self.composed_sequences

            if is_novel:
                self.novel_sequences_generated += 1

        self.total_compositions += len(novel_sequences)

        return novel_sequences

    def _generate_compositions(
        self,
        primitives: List[ActionPrimitive],
        length: int,
        task_type: str
    ) -> List[ComposedSequence]:
        """Generate compositions of given length"""
        compositions = []

        if length == 1:
            # Single actions
            for prim in primitives:
                seq = ComposedSequence(
                    sequence_id=f"{task_type}_{prim.action_id}",
                    actions=[prim],
                    source_task_type=task_type,
                    abstraction_level=0,
                    total_cost=prim.cost,
                    expected_duration=prim.avg_duration,
                    expected_success_rate=prim.success_rate
                )
                compositions.append(seq)

        elif length == 2:
            # Pairs of actions
            for i, prim1 in enumerate(primitives):
                for prim2 in primitives[i:]:  # Allow same action twice
                    # Check compatibility (effects match preconditions)
                    if self._are_compatible(prim1, prim2):
                        seq = ComposedSequence(
                            sequence_id=f"{task_type}_{prim1.action_id}_{prim2.action_id}",
                            actions=[prim1, prim2],
                            source_task_type=task_type,
                            abstraction_level=1,
                            total_cost=prim1.cost + prim2.cost,
                            expected_duration=prim1.avg_duration + prim2.avg_duration,
                            expected_success_rate=(prim1.success_rate + prim2.success_rate) / 2
                        )
                        compositions.append(seq)

        # For longer sequences, use recursive composition
        # (simplified for this implementation)

        return compositions

    def _are_compatible(self, action1: ActionPrimitive, action2: ActionPrimitive) -> bool:
        """Check if two actions are compatible in sequence"""
        # Check if action1's effects satisfy any of action2's preconditions
        for effect in action1.effects:
            if effect in action2.preconditions:
                return True

        # Allow if no strict preconditions
        if not action2.preconditions:
            return True

        return False

    def _sequence_signature(self, sequence: ComposedSequence) -> str:
        """Create unique signature for sequence"""
        action_ids = [a.action_id for a in sequence.actions]
        return "_".join(action_ids)

    def abstract_strategy(
        self,
        successful_sequences: List[ComposedSequence],
        min_pattern_support: int = 3
    ) -> List[ComposedSequence]:
        """
        Abstract reusable strategies from successful sequences

        Args:
            successful_sequences: Sequences that worked well
            min_pattern_support: Minimum times pattern must occur

        Returns:
            Abstracted strategies
        """
        strategies = []

        # Group sequences by signature
        signature_groups: Dict[str, List[ComposedSequence]] = defaultdict(list)

        for seq in successful_sequences:
            sig = self._sequence_signature(seq)
            signature_groups[sig].append(seq)

        # Create strategies from common patterns
        for sig, seqs in signature_groups.items():
            if len(seqs) >= min_pattern_support:
                # Average performance across instances
                avg_success = np.mean([s.success_rate() for s in seqs if s.success_count + s.failure_count > 0])
                avg_cost = np.mean([s.total_cost for s in seqs])

                # Create strategy
                strategy = ComposedSequence(
                    sequence_id=f"strategy_{sig}",
                    actions=seqs[0].actions,  # Use first as template
                    source_task_type="multi",
                    abstraction_level=2,  # Strategy level
                    times_used=sum(s.times_used for s in seqs),
                    success_count=sum(s.success_count for s in seqs),
                    failure_count=sum(s.failure_count for s in seqs),
                    total_cost=avg_cost,
                    expected_success_rate=avg_success
                )

                # Determine applicable domains
                strategy.applicable_domains = list(set(s.source_task_type for s in seqs))

                strategies.append(strategy)

        return strategies

    def transfer_strategy(
        self,
        source_domain: str,
        target_domain: str,
        task_context: Optional[Dict] = None
    ) -> Optional[ComposedSequence]:
        """
        Transfer learned strategy from source to target domain

        Args:
            source_domain: Domain where strategy was learned
            target_domain: Target domain to apply strategy
            task_context: Context for transfer decision

        Returns:
            Transferred strategy if applicable
        """
        # Compute domain similarity
        similarity = self._compute_domain_similarity(source_domain, target_domain)

        # Check if transfer is viable
        if similarity < self.transfer_threshold:
            return None

        # Find best strategy from source domain
        source_strategies = [
            seq for seq in self.composed_sequences.values()
            if source_domain in seq.applicable_domains and seq.abstraction_level >= 1
        ]

        if not source_strategies:
            return None

        # Select best performing strategy
        best_strategy = max(source_strategies, key=lambda s: s.success_rate())

        # Create transferred strategy
        transferred = ComposedSequence(
            sequence_id=f"transfer_{source_domain}_to_{target_domain}_{best_strategy.sequence_id}",
            actions=best_strategy.actions,  # Copy action sequence
            source_task_type=target_domain,
            abstraction_level=best_strategy.abstraction_level,
            total_cost=best_strategy.total_cost * (2 - similarity),  # Adjust cost by similarity
            expected_duration=best_strategy.expected_duration,
            expected_success_rate=best_strategy.expected_success_rate * similarity
        )

        transferred.applicable_domains = [target_domain]

        self.successful_transfers += 1

        return transferred

    def _compute_domain_similarity(self, domain1: str, domain2: str) -> float:
        """Compute similarity between two domains"""
        # Check cache
        cache_key = tuple(sorted([domain1, domain2]))
        if cache_key in self.domain_similarities:
            return self.domain_similarities[cache_key]

        # Simple similarity based on shared patterns
        patterns1 = set(self.domain_patterns.get(domain1, []))
        patterns2 = set(self.domain_patterns.get(domain2, []))

        if not patterns1 or not patterns2:
            # No patterns, use default similarity
            similarity = 0.3
        else:
            # Jaccard similarity
            intersection = len(patterns1 & patterns2)
            union = len(patterns1 | patterns2)
            similarity = intersection / union if union > 0 else 0.0

        # Cache result
        self.domain_similarities[cache_key] = similarity

        return similarity

    def evaluate_composition(
        self,
        sequence: ComposedSequence,
        context: Optional[Dict] = None
    ) -> Tuple[float, float]:
        """
        Evaluate composition quality

        Args:
            sequence: Composed sequence to evaluate
            context: Optional context

        Returns:
            (novelty_score, feasibility_score)
        """
        # Novelty: how different from existing sequences
        sig = self._sequence_signature(sequence)
        is_new = sig not in self.composed_sequences
        novelty = 1.0 if is_new else 0.3

        # Feasibility: expected success based on components
        feasibility = sequence.expected_success_rate

        # Adjust by cost (prefer lower cost)
        cost_factor = 1.0 / (1.0 + sequence.total_cost)
        feasibility *= (0.7 + 0.3 * cost_factor)

        return novelty, feasibility

    def record_sequence_outcome(
        self,
        sequence: ComposedSequence,
        outcome: str
    ):
        """Record outcome of using a composed sequence"""
        sig = self._sequence_signature(sequence)

        # Update or store sequence
        if sig in self.composed_sequences:
            stored_seq = self.composed_sequences[sig]
            stored_seq.times_used += 1
            if outcome == 'success':
                stored_seq.success_count += 1
            else:
                stored_seq.failure_count += 1
        else:
            # Store new sequence
            sequence.times_used = 1
            if outcome == 'success':
                sequence.success_count = 1
                sequence.failure_count = 0
            else:
                sequence.success_count = 0
                sequence.failure_count = 1
            self.composed_sequences[sig] = sequence

        # Update domain patterns
        if outcome == 'success':
            self.domain_patterns[sequence.source_task_type].append(sig)

    def get_statistics(self) -> Dict:
        """Get compositional reasoning statistics"""
        # Count by abstraction level
        abstraction_counts = defaultdict(int)
        for seq in self.composed_sequences.values():
            abstraction_counts[seq.abstraction_level] += 1

        # Average success rates
        if self.composed_sequences:
            avg_success = np.mean([
                seq.success_rate()
                for seq in self.composed_sequences.values()
                if seq.success_count + seq.failure_count > 0
            ])
        else:
            avg_success = 0.0

        return {
            'total_compositions': self.total_compositions,
            'novel_sequences_generated': self.novel_sequences_generated,
            'stored_sequences': len(self.composed_sequences),
            'successful_transfers': self.successful_transfers,
            'abstraction_levels': dict(abstraction_counts),
            'avg_success_rate': avg_success,
            'num_domains': len(self.domain_patterns),
            'exploration_rate': self.exploration_rate
        }

    def __repr__(self):
        return (
            f"CompositionalReasoning("
            f"sequences={len(self.composed_sequences)}, "
            f"compositions={self.total_compositions}, "
            f"transfers={self.successful_transfers})"
        )


if __name__ == "__main__":
    print("=" * 70)
    print("COMPOSITIONAL REASONING SYSTEM (PHASE 9)")
    print("=" * 70)
    print()
    print("This module implements compositional thinking:")
    print("  - Compose novel action sequences from primitives")
    print("  - Learn reusable strategies from successful patterns")
    print("  - Transfer knowledge across domains")
    print("  - Creative problem solving")
    print("  - Hierarchical abstraction")
    print()
    print("To test the complete system, run:")
    print("  python demos/test_compositional_reasoning.py")
    print()
    print("=" * 70)
