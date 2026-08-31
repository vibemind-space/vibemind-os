"""
Strategy Library for Successful Pattern Storage

Stores successful conversation strategies in hippocampus-like memory.
Retrieves similar successful strategies when faced with new tasks.
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from collections import defaultdict


class Strategy:
    """
    Single successful strategy.

    Stores the pattern that led to success and context in which it worked.
    """

    def __init__(
        self,
        task_type: str,
        tool_sequence: List[str],
        duration: float,
        success_rate: float = 1.0
    ):
        """
        Initialize strategy.

        Args:
            task_type: Type of task (github, docker, memory, etc.)
            tool_sequence: Sequence of tools used
            duration: Time taken
            success_rate: Success rate of this strategy
        """
        self.task_type = task_type
        self.tool_sequence = tool_sequence
        self.duration = duration
        self.success_rate = success_rate
        self.usage_count = 1
        self.last_used = 0

    def update(self, success: bool):
        """Update strategy with new outcome."""
        self.usage_count += 1
        # Exponential moving average
        alpha = 0.3
        self.success_rate = (1 - alpha) * self.success_rate + alpha * (1.0 if success else 0.0)

    def get_quality_score(self, recency_weight: float = 0.1) -> float:
        """
        Compute quality score for strategy ranking.

        Args:
            recency_weight: Weight for recency vs success rate

        Returns:
            Quality score (higher is better)
        """
        # Combine success rate with usage count (more used = more trusted)
        usage_factor = min(self.usage_count / 10.0, 1.0)
        recency_factor = np.exp(-recency_weight * self.last_used)

        return self.success_rate * 0.6 + usage_factor * 0.3 + recency_factor * 0.1


class StrategyLibrary:
    """
    Library of successful strategies indexed by task type.

    Stores, retrieves, and recommends strategies based on context.
    """

    def __init__(self, max_strategies_per_type: int = 20):
        """
        Initialize strategy library.

        Args:
            max_strategies_per_type: Maximum strategies to keep per task type
        """
        self.max_strategies_per_type = max_strategies_per_type

        # Strategies indexed by task type
        self.strategies: Dict[str, List[Strategy]] = defaultdict(list)

        # Statistics
        self.total_strategies = 0
        self.total_retrievals = 0
        self.successful_retrievals = 0

    def add_strategy(
        self,
        task_type: str,
        tool_sequence: List[str],
        duration: float,
        success: bool = True
    ):
        """
        Add a strategy to the library.

        Args:
            task_type: Task type
            tool_sequence: Tools used in sequence
            duration: Time taken
            success: Whether it succeeded
        """
        if not success:
            return  # Only store successful strategies

        # Check if similar strategy already exists
        for strategy in self.strategies[task_type]:
            if strategy.tool_sequence == tool_sequence:
                strategy.update(success)
                return

        # Create new strategy
        strategy = Strategy(task_type, tool_sequence, duration)
        self.strategies[task_type].append(strategy)
        self.total_strategies += 1

        # Prune if too many
        if len(self.strategies[task_type]) > self.max_strategies_per_type:
            # Remove lowest quality strategy
            self.strategies[task_type].sort(key=lambda s: s.get_quality_score())
            self.strategies[task_type] = self.strategies[task_type][-self.max_strategies_per_type:]
            self.total_strategies = sum(len(strategies) for strategies in self.strategies.values())

    def retrieve_strategies(
        self,
        task_type: str,
        top_k: int = 3
    ) -> List[Strategy]:
        """
        Retrieve best strategies for a task type.

        Args:
            task_type: Task type to retrieve strategies for
            top_k: Number of strategies to retrieve

        Returns:
            List of top-k strategies
        """
        self.total_retrievals += 1

        if task_type not in self.strategies:
            return []

        # Sort by quality score
        strategies = sorted(
            self.strategies[task_type],
            key=lambda s: s.get_quality_score(),
            reverse=True
        )

        # Update last_used
        for i, strategy in enumerate(strategies[:top_k]):
            strategy.last_used = i

        return strategies[:top_k]

    def get_recommendation(
        self,
        task_type: str,
        current_errors: int = 0
    ) -> Optional[Dict]:
        """
        Get strategic recommendation for a task.

        Args:
            task_type: Task type
            current_errors: Current error count (for urgency)

        Returns:
            Recommendation dict or None
        """
        strategies = self.retrieve_strategies(task_type, top_k=3)

        if not strategies:
            return None

        # Best strategy
        best = strategies[0]

        recommendation = {
            'strategy': best.tool_sequence,
            'expected_duration': best.duration,
            'success_rate': best.success_rate,
            'confidence': best.get_quality_score(),
            'alternatives': [
                {
                    'tools': s.tool_sequence,
                    'success_rate': s.success_rate
                }
                for s in strategies[1:]
            ]
        }

        # Add urgency if errors
        if current_errors > 5:
            recommendation['urgency'] = 'high'
            recommendation['message'] = 'High error count! Recommend trying proven strategy.'
        elif current_errors > 3:
            recommendation['urgency'] = 'medium'
            recommendation['message'] = 'Errors accumulating. Consider alternative approach.'

        return recommendation

    def get_statistics(self) -> Dict:
        """Get library statistics."""
        return {
            'total_strategies': self.total_strategies,
            'task_types': len(self.strategies),
            'total_retrievals': self.total_retrievals,
            'successful_retrievals': self.successful_retrievals,
            'strategies_by_type': {
                task_type: len(strategies)
                for task_type, strategies in self.strategies.items()
            }
        }

    def visualize(self) -> str:
        """Create ASCII visualization of strategy library."""
        lines = []
        lines.append("="*80)
        lines.append("STRATEGY LIBRARY")
        lines.append("="*80)
        lines.append("")

        stats = self.get_statistics()
        lines.append(f"Total Strategies: {stats['total_strategies']}")
        lines.append(f"Task Types: {stats['task_types']}")
        lines.append(f"Total Retrievals: {stats['total_retrievals']}")
        lines.append("")

        lines.append("STRATEGIES BY TASK TYPE:")
        lines.append("-"*80)

        for task_type, strategies in self.strategies.items():
            lines.append(f"\n{task_type.upper()} ({len(strategies)} strategies):")

            # Show top 3
            top_strategies = sorted(strategies, key=lambda s: s.get_quality_score(), reverse=True)[:3]

            for i, strategy in enumerate(top_strategies, 1):
                tools_str = " -> ".join(strategy.tool_sequence[:5])  # First 5 tools
                if len(strategy.tool_sequence) > 5:
                    tools_str += f" ... (+{len(strategy.tool_sequence)-5} more)"

                lines.append(f"  {i}. {tools_str}")
                lines.append(f"     Success Rate: {strategy.success_rate:.1%}")
                lines.append(f"     Duration: {strategy.duration:.1f}s")
                lines.append(f"     Used: {strategy.usage_count}x")
                lines.append(f"     Quality Score: {strategy.get_quality_score():.3f}")

        lines.append("")
        lines.append("="*80)

        return "\n".join(lines)
