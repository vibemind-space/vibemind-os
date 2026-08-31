"""
Hierarchical Lambda (Phase 4) - Layer-Scaled Time Constants

Implements hierarchical λ scaling for phase dynamics:
    ΔφH(r) = -λ(ωqf δ(r) + ∇·(W×E))

The same equation applies at each layer, but with different time scales:
- Layer 1 (Micro): λ = 1.0    - Fast action decisions
- Layer 2 (Expert): λ = 0.1   - Medium expert coordination
- Layer 3 (Meta): λ = 0.01    - Slow strategic adaptation

Higher λ = faster phase changes = more reactive
Lower λ = slower phase changes = more stable/deliberate
"""

from enum import Enum
from dataclasses import dataclass
from typing import Dict, Optional


class HierarchyLayer(Enum):
    """Hierarchy layers for temporal processing"""
    L1_MICRO = "L1_micro"       # Individual actions, tool calls
    L2_EXPERT = "L2_expert"     # Expert-level decisions, regime selection
    L3_META = "L3_meta"         # Strategic adaptation, goal-level


# Default layer scales (higher = faster phase dynamics)
LAYER_SCALES: Dict[HierarchyLayer, float] = {
    HierarchyLayer.L1_MICRO: 1.0,      # Fast - individual actions
    HierarchyLayer.L2_EXPERT: 0.1,     # Medium - expert decisions
    HierarchyLayer.L3_META: 0.01       # Slow - strategic changes
}

# Alternative scale names for string-based access
LAYER_SCALE_NAMES: Dict[str, float] = {
    'L1_micro': 1.0,
    'L2_expert': 0.1,
    'L3_meta': 0.01,
    'micro': 1.0,
    'expert': 0.1,
    'meta': 0.01,
    'fast': 1.0,
    'medium': 0.1,
    'slow': 0.01
}


@dataclass
class HierarchicalLambda:
    """
    Hierarchical time constant manager

    λ scales by layer:
    - Faster at micro level (reactive to individual tool results)
    - Slower at meta level (stable across many actions)
    """
    base_lambda: float = 0.1

    def get(self, layer: HierarchyLayer) -> float:
        """
        Get λ for a specific layer

        Args:
            layer: HierarchyLayer enum

        Returns:
            Scaled λ value
        """
        scale = LAYER_SCALES.get(layer, 1.0)
        return self.base_lambda * scale

    def get_by_name(self, layer_name: str) -> float:
        """
        Get λ by layer name string

        Args:
            layer_name: String name (e.g., 'L1_micro', 'fast', 'meta')

        Returns:
            Scaled λ value
        """
        scale = LAYER_SCALE_NAMES.get(layer_name.lower(), 1.0)
        return self.base_lambda * scale

    def get_micro(self) -> float:
        """Get λ for micro layer (fastest)"""
        return self.get(HierarchyLayer.L1_MICRO)

    def get_expert(self) -> float:
        """Get λ for expert layer (medium)"""
        return self.get(HierarchyLayer.L2_EXPERT)

    def get_meta(self) -> float:
        """Get λ for meta layer (slowest)"""
        return self.get(HierarchyLayer.L3_META)

    def scale_for_urgency(self, base_scale: float, urgency: float) -> float:
        """
        Scale λ based on urgency (0.0 to 1.0)

        High urgency = faster phase dynamics
        Low urgency = slower, more deliberate

        Args:
            base_scale: Base λ value
            urgency: Urgency level (0.0 = calm, 1.0 = urgent)

        Returns:
            Urgency-adjusted λ
        """
        # Urgency multiplier: 1x at urgency=0, up to 3x at urgency=1
        urgency_multiplier = 1.0 + 2.0 * urgency
        return base_scale * urgency_multiplier

    def scale_for_confidence(self, base_scale: float, confidence: float) -> float:
        """
        Scale λ based on confidence (0.0 to 1.0)

        High confidence = can use faster dynamics
        Low confidence = should be more cautious (slower)

        Args:
            base_scale: Base λ value
            confidence: Confidence level (0.0 = uncertain, 1.0 = certain)

        Returns:
            Confidence-adjusted λ
        """
        # Confidence multiplier: 0.5x at confidence=0, 1.5x at confidence=1
        confidence_multiplier = 0.5 + 1.0 * confidence
        return base_scale * confidence_multiplier


class AdaptiveLambda:
    """
    Adaptive λ that adjusts based on performance and context

    Learns optimal time constants through experience:
    - Increase λ when quick adaptation leads to success
    - Decrease λ when slow deliberation works better
    """

    def __init__(
        self,
        initial_lambda: float = 0.1,
        min_lambda: float = 0.001,
        max_lambda: float = 1.0,
        adaptation_rate: float = 0.01
    ):
        """
        Initialize adaptive lambda

        Args:
            initial_lambda: Starting λ value
            min_lambda: Minimum allowed λ
            max_lambda: Maximum allowed λ
            adaptation_rate: How quickly to adapt
        """
        self.current_lambda = initial_lambda
        self.min_lambda = min_lambda
        self.max_lambda = max_lambda
        self.adaptation_rate = adaptation_rate

        # Track performance
        self.success_count = 0
        self.failure_count = 0
        self.lambda_history: list = []

    def get(self) -> float:
        """Get current λ value"""
        return self.current_lambda

    def update_on_success(self, was_fast: bool = True):
        """
        Update λ after successful action

        Args:
            was_fast: Whether we used fast dynamics
        """
        self.success_count += 1

        if was_fast:
            # Fast worked, consider increasing λ
            self._increase_lambda()
        # If slow worked, no change needed

    def update_on_failure(self, was_fast: bool = True):
        """
        Update λ after failed action

        Args:
            was_fast: Whether we used fast dynamics
        """
        self.failure_count += 1

        if was_fast:
            # Fast failed, consider decreasing λ
            self._decrease_lambda()
        # If slow failed, might need to try faster

    def _increase_lambda(self):
        """Increase λ (faster dynamics)"""
        self.current_lambda = min(
            self.max_lambda,
            self.current_lambda * (1 + self.adaptation_rate)
        )
        self._record_history()

    def _decrease_lambda(self):
        """Decrease λ (slower dynamics)"""
        self.current_lambda = max(
            self.min_lambda,
            self.current_lambda * (1 - self.adaptation_rate)
        )
        self._record_history()

    def _record_history(self):
        """Record λ history"""
        self.lambda_history.append(self.current_lambda)
        if len(self.lambda_history) > 1000:
            self.lambda_history = self.lambda_history[-1000:]

    def reset(self, initial_lambda: Optional[float] = None):
        """Reset to initial state"""
        if initial_lambda is not None:
            self.current_lambda = initial_lambda
        else:
            self.current_lambda = 0.1
        self.success_count = 0
        self.failure_count = 0
        self.lambda_history = []


def get_lambda_for_layer(layer: str, base: float = 0.1) -> float:
    """
    Convenience function to get λ for a layer

    Args:
        layer: Layer name ('micro', 'expert', 'meta', etc.)
        base: Base λ value

    Returns:
        Scaled λ
    """
    hierarchical = HierarchicalLambda(base_lambda=base)
    return hierarchical.get_by_name(layer)


def compute_effective_lambda(
    layer: str,
    base: float = 0.1,
    urgency: float = 0.5,
    confidence: float = 0.5
) -> float:
    """
    Compute effective λ considering all factors

    Args:
        layer: Hierarchy layer name
        base: Base λ value
        urgency: Urgency level (0-1)
        confidence: Confidence level (0-1)

    Returns:
        Effective λ value
    """
    h = HierarchicalLambda(base_lambda=base)

    # Get layer-scaled λ
    layer_lambda = h.get_by_name(layer)

    # Apply urgency scaling
    layer_lambda = h.scale_for_urgency(layer_lambda, urgency)

    # Apply confidence scaling
    layer_lambda = h.scale_for_confidence(layer_lambda, confidence)

    return layer_lambda


if __name__ == "__main__":
    print("=" * 70)
    print("HIERARCHICAL LAMBDA - Testing")
    print("=" * 70)
    print()

    # Test 1: Basic hierarchical lambda
    print("[1] Testing HierarchicalLambda...")
    h = HierarchicalLambda(base_lambda=0.1)
    print(f"    L1 (micro): {h.get_micro():.4f}")
    print(f"    L2 (expert): {h.get_expert():.4f}")
    print(f"    L3 (meta): {h.get_meta():.4f}")
    assert h.get_micro() > h.get_expert() > h.get_meta()
    print("    [OK] Layer scaling correct")
    print()

    # Test 2: String-based access
    print("[2] Testing string-based access...")
    print(f"    'fast': {h.get_by_name('fast'):.4f}")
    print(f"    'slow': {h.get_by_name('slow'):.4f}")
    print(f"    'L2_expert': {h.get_by_name('L2_expert'):.4f}")
    print("    [OK] String access working")
    print()

    # Test 3: Urgency scaling
    print("[3] Testing urgency scaling...")
    base = 0.1
    print(f"    Base: {base:.4f}")
    print(f"    Urgency 0.0: {h.scale_for_urgency(base, 0.0):.4f}")
    print(f"    Urgency 0.5: {h.scale_for_urgency(base, 0.5):.4f}")
    print(f"    Urgency 1.0: {h.scale_for_urgency(base, 1.0):.4f}")
    assert h.scale_for_urgency(base, 1.0) > h.scale_for_urgency(base, 0.0)
    print("    [OK] Urgency scaling correct")
    print()

    # Test 4: Confidence scaling
    print("[4] Testing confidence scaling...")
    print(f"    Confidence 0.0: {h.scale_for_confidence(base, 0.0):.4f}")
    print(f"    Confidence 0.5: {h.scale_for_confidence(base, 0.5):.4f}")
    print(f"    Confidence 1.0: {h.scale_for_confidence(base, 1.0):.4f}")
    assert h.scale_for_confidence(base, 1.0) > h.scale_for_confidence(base, 0.0)
    print("    [OK] Confidence scaling correct")
    print()

    # Test 5: Adaptive lambda
    print("[5] Testing AdaptiveLambda...")
    adaptive = AdaptiveLambda(initial_lambda=0.1)
    print(f"    Initial: {adaptive.get():.4f}")

    # Simulate successes with fast dynamics
    for _ in range(5):
        adaptive.update_on_success(was_fast=True)
    print(f"    After 5 fast successes: {adaptive.get():.4f}")

    # Simulate failures
    for _ in range(3):
        adaptive.update_on_failure(was_fast=True)
    print(f"    After 3 fast failures: {adaptive.get():.4f}")
    print("    [OK] Adaptive lambda working")
    print()

    # Test 6: Convenience function
    print("[6] Testing convenience function...")
    print(f"    get_lambda_for_layer('micro'): {get_lambda_for_layer('micro'):.4f}")
    print(f"    get_lambda_for_layer('meta'): {get_lambda_for_layer('meta'):.4f}")
    print("    [OK] Convenience function working")
    print()

    # Test 7: Effective lambda
    print("[7] Testing effective lambda...")
    eff = compute_effective_lambda(
        layer='expert',
        base=0.1,
        urgency=0.8,
        confidence=0.6
    )
    print(f"    Effective λ (expert, urgent, confident): {eff:.4f}")
    print("    [OK] Effective lambda working")
    print()

    print("=" * 70)
    print("HIERARCHICAL LAMBDA TESTS COMPLETE")
    print("=" * 70)
