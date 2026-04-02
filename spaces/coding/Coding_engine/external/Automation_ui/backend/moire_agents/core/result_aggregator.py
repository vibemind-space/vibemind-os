"""
Result Aggregator - Strategies for merging parallel subagent results.

When multiple subagents work in parallel (e.g., 3 planning approaches),
the aggregator decides how to combine or select the best result.

Strategies:
- BEST_CONFIDENCE: Pick the result with highest confidence
- CONSENSUS: Require multiple subagents to agree
- WEIGHTED_MERGE: Combine results with weights based on confidence
- FIRST_SUCCESS: Return the first successful result
"""

import logging
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, TypeVar

logger = logging.getLogger(__name__)


class AggregationStrategy(Enum):
    """Strategies for aggregating parallel results."""
    BEST_CONFIDENCE = "best_confidence"
    CONSENSUS = "consensus"
    WEIGHTED_MERGE = "weighted_merge"
    FIRST_SUCCESS = "first_success"


# Generic type for result objects
T = TypeVar('T')


@dataclass
class AggregationMetrics:
    """Metrics about the aggregation process."""
    total_results: int
    successful_results: int
    strategy_used: str
    confidence_scores: List[float]
    selected_index: Optional[int] = None
    consensus_agreement: Optional[float] = None


class ResultAggregator:
    """
    Aggregates results from parallel subagent executions.

    Different strategies can be used depending on the use case:
    - Planning: BEST_CONFIDENCE (pick the most confident plan)
    - Vision: WEIGHTED_MERGE (combine all region analyses)
    - Validation: CONSENSUS (require agreement)
    """

    def __init__(
        self,
        strategy: AggregationStrategy = AggregationStrategy.BEST_CONFIDENCE,
        min_confidence: float = 0.3,
        consensus_threshold: float = 0.6
    ):
        """
        Initialize the aggregator.

        Args:
            strategy: Default aggregation strategy
            min_confidence: Minimum confidence to consider a result valid
            consensus_threshold: Required agreement ratio for CONSENSUS strategy
        """
        self.strategy = strategy
        self.min_confidence = min_confidence
        self.consensus_threshold = consensus_threshold

    def aggregate_planning_results(
        self,
        results: List[Any],
        strategy: Optional[AggregationStrategy] = None
    ) -> Any:
        """
        Aggregate planning subagent results.

        Args:
            results: List of PlanningResult objects
            strategy: Override default strategy

        Returns:
            Best PlanningResult based on strategy
        """
        strategy = strategy or self.strategy

        # Filter to successful results with minimum confidence
        valid_results = [
            r for r in results
            if getattr(r, 'success', False) and
               getattr(r, 'confidence', 0) >= self.min_confidence
        ]

        if not valid_results:
            logger.warning("No valid planning results to aggregate")
            # Return first result even if failed
            return results[0] if results else None

        if strategy == AggregationStrategy.BEST_CONFIDENCE:
            return self._select_best_confidence(valid_results)

        elif strategy == AggregationStrategy.FIRST_SUCCESS:
            return valid_results[0]

        elif strategy == AggregationStrategy.CONSENSUS:
            return self._select_consensus(valid_results)

        elif strategy == AggregationStrategy.WEIGHTED_MERGE:
            # For planning, weighted merge doesn't make sense
            # Fall back to best confidence
            return self._select_best_confidence(valid_results)

        return self._select_best_confidence(valid_results)

    def aggregate_vision_results(
        self,
        results: List[Any],
        strategy: Optional[AggregationStrategy] = None
    ) -> Dict[str, Any]:
        """
        Aggregate vision subagent results.

        Vision results are typically merged rather than selected,
        as each covers a different screen region.

        Args:
            results: List of VisionResult objects
            strategy: Override default strategy

        Returns:
            Dict with merged analysis by region name
        """
        merged = {}

        for r in results:
            region_name = getattr(r, 'region_name', 'unknown')
            merged[region_name] = {
                "elements": getattr(r, 'elements', []),
                "analysis": getattr(r, 'analysis', ''),
                "confidence": getattr(r, 'confidence', 0.0),
                "success": getattr(r, 'success', False),
                "error": getattr(r, 'error', None)
            }

        return merged

    def aggregate_specialist_results(
        self,
        results: List[Any],
        strategy: Optional[AggregationStrategy] = None
    ) -> Any:
        """
        Aggregate specialist subagent results.

        Usually only one specialist is queried at a time, but if multiple
        are queried (e.g., for cross-domain tasks), we merge their knowledge.

        Args:
            results: List of SpecialistResult objects
            strategy: Override default strategy

        Returns:
            Merged SpecialistResult
        """
        strategy = strategy or self.strategy

        valid_results = [
            r for r in results
            if getattr(r, 'success', False)
        ]

        if not valid_results:
            return results[0] if results else None

        if len(valid_results) == 1:
            return valid_results[0]

        # Merge multiple specialist results
        merged_shortcuts = {}
        merged_workflows = []

        for r in valid_results:
            if hasattr(r, 'shortcuts') and r.shortcuts:
                merged_shortcuts.update(r.shortcuts)
            if hasattr(r, 'workflow') and r.workflow:
                merged_workflows.extend(r.workflow)

        # Return first result with merged data
        best = valid_results[0]
        if hasattr(best, 'shortcuts'):
            best.shortcuts = merged_shortcuts
        if hasattr(best, 'workflow'):
            best.workflow = merged_workflows

        return best

    def _select_best_confidence(self, results: List[Any]) -> Any:
        """Select the result with highest confidence."""
        if not results:
            return None

        best = max(results, key=lambda r: getattr(r, 'confidence', 0))
        logger.debug(
            f"Selected best confidence: {getattr(best, 'confidence', 0):.2f}"
        )
        return best

    def _select_first_success(self, results: List[Any]) -> Any:
        """Select the first successful result."""
        for r in results:
            if getattr(r, 'success', False):
                return r
        return results[0] if results else None

    def _select_consensus(self, results: List[Any]) -> Any:
        """
        Select based on consensus among results.

        For planning, this checks if multiple approaches suggest
        similar action sequences.
        """
        if len(results) < 2:
            return results[0] if results else None

        # Extract action signatures for comparison
        signatures = []
        for r in results:
            actions = getattr(r, 'actions', [])
            # Create a simplified signature of the action sequence
            sig = tuple(
                action.get('action', 'unknown') if isinstance(action, dict) else 'unknown'
                for action in actions[:5]  # First 5 actions
            )
            signatures.append(sig)

        # Count signature occurrences
        sig_counts = Counter(signatures)
        most_common_sig, count = sig_counts.most_common(1)[0]

        agreement = count / len(results)
        logger.debug(f"Consensus agreement: {agreement:.2f}")

        if agreement >= self.consensus_threshold:
            # Return the result matching the consensus signature
            for r, sig in zip(results, signatures):
                if sig == most_common_sig:
                    return r

        # No consensus, fall back to best confidence
        logger.warning(
            f"No consensus reached (agreement: {agreement:.2f}), "
            "falling back to best confidence"
        )
        return self._select_best_confidence(results)

    def compute_metrics(
        self,
        results: List[Any],
        selected: Any
    ) -> AggregationMetrics:
        """
        Compute metrics about the aggregation.

        Args:
            results: All results
            selected: The selected/aggregated result

        Returns:
            AggregationMetrics
        """
        successful = [r for r in results if getattr(r, 'success', False)]
        confidences = [
            getattr(r, 'confidence', 0) for r in results
        ]

        selected_idx = None
        if selected:
            for i, r in enumerate(results):
                if r is selected:
                    selected_idx = i
                    break

        return AggregationMetrics(
            total_results=len(results),
            successful_results=len(successful),
            strategy_used=self.strategy.value,
            confidence_scores=confidences,
            selected_index=selected_idx
        )


# Helper functions for common aggregation patterns

def select_best_plan(results: List[Any]) -> Any:
    """Convenience function to select best planning result."""
    aggregator = ResultAggregator(AggregationStrategy.BEST_CONFIDENCE)
    return aggregator.aggregate_planning_results(results)


def merge_vision_regions(results: List[Any]) -> Dict[str, Any]:
    """Convenience function to merge vision results."""
    aggregator = ResultAggregator()
    return aggregator.aggregate_vision_results(results)


def require_consensus(
    results: List[Any],
    threshold: float = 0.6
) -> Any:
    """Convenience function for consensus-based selection."""
    aggregator = ResultAggregator(
        AggregationStrategy.CONSENSUS,
        consensus_threshold=threshold
    )
    return aggregator.aggregate_planning_results(results)
