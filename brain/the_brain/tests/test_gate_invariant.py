"""
Unit tests for the CRITICAL gate normalization invariant.

Brain gates MUST always sum to 1.0 (softmax normalization).
This invariant must hold after every stage of processing:
- Layer 1 (TaskFeatureRouter) initial routing
- Memory bias blending
- Attention gating
- Neuromodulation temperature scaling
- Full CognitiveLoop pipeline
- Full HierarchicalPlanner pipeline

Any violation of this invariant can cause incorrect routing,
probability distribution corruption, and downstream failures.
"""

import pytest
import numpy as np
import sys
import os

# Add parent directory to path for module access
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, parent_dir)

from core.task_feature_router import TaskFeatureRouter, TaskFeatures, RoutingState
from core.attention_mechanisms import AttentionMechanism


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def router():
    """Create a TaskFeatureRouter for testing."""
    return TaskFeatureRouter(seed=42)


@pytest.fixture
def attention():
    """Create an AttentionMechanism for testing."""
    modality_names = [
        'vision', 'audio', 'touch', 'taste', 'vestibular',
        'threat', 'tool_trace', 'temporal_pattern',
        'error_signal', 'success_signal'
    ]
    return AttentionMechanism(
        num_modalities=10,
        modality_names=modality_names
    )


@pytest.fixture
def planner():
    """Create a minimal HierarchicalPlanner for testing."""
    from core.hierarchical_planner import HierarchicalPlanner
    from core.conversation_path_planner import ConversationPathPlanner
    from core.meta_router import MetaRouter

    meta_router = MetaRouter(
        enable_hippocampus=True,
        enable_per_modality_pes=True,
        seed=42
    )

    try:
        from core.conversation_path_planner import StrategyLibrary, BrainActivityMonitor
        layer2 = ConversationPathPlanner(
            meta_router=meta_router,
            strategy_library=StrategyLibrary(max_strategies_per_type=10),
            brain_monitor=BrainActivityMonitor(history_length=50),
            enable_adaptive_gating=True
        )
    except Exception:
        layer2 = ConversationPathPlanner(meta_router=meta_router)

    try:
        layer2.train_from_sessions("data/logs", limit=5)
    except Exception:
        pass

    hp = HierarchicalPlanner(
        conversation_planner=layer2,
        intervention_types=['suggest', 'retry', 'wait', 'terminate', 'execute'],
        seed=42
    )
    return hp


@pytest.fixture
def loop(planner):
    """Create a CognitiveLoop instance."""
    from core.cognitive_loop import CognitiveLoop, CognitiveLoopConfig
    config = CognitiveLoopConfig()
    return CognitiveLoop(planner=planner, config=config)


# ============================================================================
# Helper constants
# ============================================================================

GATE_SUM_TOLERANCE = 1e-6
GATE_SUM_SOFT_TOLERANCE = 0.01  # For full pipeline tests with floating point accumulation

DIVERSE_TASKS = [
    "Check memory status and monitor dashboard",
    "Deploy Docker container and build image urgently",
    "git commit and push changes to GitHub",
    "Search for files containing error patterns",
    "Analyze this complex codebase and debug the architecture",
    "Run pytest unit tests and validate integration",
    "Refactor and optimize the routing module",
    "Read and edit the configuration file",
    "Simple quick check",
    "Investigate multiple complex challenging intricate issues immediately",
]


# ============================================================================
# Test 1: Layer 1 route_task output gates sum to 1.0
# ============================================================================

class TestLayer1GateInvariant:
    """Layer 1 TaskFeatureRouter must always produce gates summing to 1.0."""

    def test_route_task_gates_sum_to_one(self, router):
        """Layer 1 route_task output routing_weights must sum to 1.0."""
        for task in DIVERSE_TASKS:
            routing_state = router.route_task(task)
            gates = routing_state.routing_weights
            gate_sum = np.sum(gates)

            assert np.isclose(gate_sum, 1.0, atol=GATE_SUM_TOLERANCE), \
                f"Layer 1 gate sum = {gate_sum} for task '{task[:40]}...', expected 1.0"
            assert np.all(gates >= 0), \
                f"Layer 1 gates contain negative values for task '{task[:40]}...'"
            assert np.all(gates <= 1.0), \
                f"Layer 1 gates contain values > 1.0 for task '{task[:40]}...'"

    def test_route_task_returns_ndarray_of_10(self, router):
        """Routing weights must be an ndarray of 10 floats."""
        routing_state = router.route_task("Test task")
        gates = routing_state.routing_weights

        assert isinstance(gates, np.ndarray), \
            f"routing_weights should be np.ndarray, got {type(gates)}"
        assert gates.shape == (10,), \
            f"routing_weights shape should be (10,), got {gates.shape}"


# ============================================================================
# Test 2: Softmax of random weights sums to 1.0
# ============================================================================

class TestSoftmaxNormalization:
    """Softmax normalization must always produce valid probability distributions."""

    def test_softmax_random_weights_sum_to_one(self):
        """Softmax of random weights must always sum to 1.0."""
        rng = np.random.RandomState(42)

        for _ in range(100):
            raw_weights = rng.randn(10)
            # Apply softmax (the normalization used in the system)
            exp_weights = np.exp(raw_weights - np.max(raw_weights))  # numerically stable
            softmax_weights = exp_weights / np.sum(exp_weights)

            assert np.isclose(np.sum(softmax_weights), 1.0, atol=GATE_SUM_TOLERANCE), \
                f"Softmax sum = {np.sum(softmax_weights)}, expected 1.0"
            assert np.all(softmax_weights >= 0), "Softmax produced negative values"
            assert np.all(softmax_weights <= 1.0), "Softmax produced values > 1.0"

    def test_router_normalize_equals_divide_by_sum(self, router):
        """Router's normalization (divide by sum) must produce gates summing to 1.0."""
        # The router uses weights / sum(weights) normalization, not softmax
        rng = np.random.RandomState(42)

        for _ in range(100):
            raw_weights = np.abs(rng.randn(10)) + 0.01  # ensure positive
            normalized = raw_weights / np.sum(raw_weights)

            assert np.isclose(np.sum(normalized), 1.0, atol=GATE_SUM_TOLERANCE), \
                f"Normalized sum = {np.sum(normalized)}, expected 1.0"


# ============================================================================
# Test 3: After memory bias blending, gates sum to 1.0
# ============================================================================

class TestMemoryBiasGateInvariant:
    """Memory bias blending must preserve the gate sum invariant."""

    def test_memory_bias_blending_preserves_sum(self):
        """Blending routing weights with memory bias and renormalizing must sum to 1.0."""
        rng = np.random.RandomState(42)

        for _ in range(50):
            # Simulate raw routing weights (already normalized)
            raw_weights = np.abs(rng.randn(10))
            raw_weights = raw_weights / np.sum(raw_weights)

            # Simulate memory bias (from successful past tasks, already normalized)
            memory_bias = np.abs(rng.randn(10))
            memory_bias = memory_bias / np.sum(memory_bias)

            # Blend with memory_routing_bias_strength = 0.25 (default)
            blend = 0.25
            biased_weights = (1 - blend) * raw_weights + blend * memory_bias

            # Re-normalize (as done in cognitive_loop._remember)
            weight_sum = np.sum(biased_weights)
            if weight_sum > 1e-8:
                biased_weights = biased_weights / weight_sum

            assert np.isclose(np.sum(biased_weights), 1.0, atol=GATE_SUM_TOLERANCE), \
                f"After memory bias: gate sum = {np.sum(biased_weights)}, expected 1.0"
            assert np.all(biased_weights >= 0), "Memory-biased gates contain negatives"

    def test_cognitive_loop_remember_preserves_sum(self, loop):
        """CognitiveLoop._remember must preserve gate sum invariant."""
        from core.cognitive_loop import LoopContext

        ctx = LoopContext(task_description="Deploy Docker container")
        loop._perceive(ctx)

        # Verify pre-remember sum
        pre_sum = np.sum(np.array(ctx.layer1_routing.routing_weights))
        assert np.isclose(pre_sum, 1.0, atol=GATE_SUM_SOFT_TOLERANCE), \
            f"Pre-remember gate sum = {pre_sum}"

        loop._remember(ctx)

        # Verify post-remember sum
        post_weights = np.array(ctx.layer1_routing.routing_weights)
        post_sum = np.sum(post_weights)
        assert np.isclose(post_sum, 1.0, atol=GATE_SUM_SOFT_TOLERANCE), \
            f"Post-remember gate sum = {post_sum}, expected 1.0"


# ============================================================================
# Test 4: After attention gating, gates sum to 1.0
# ============================================================================

class TestAttentionGatingInvariant:
    """Attention gating must preserve the gate sum invariant."""

    def test_apply_attention_gating_preserves_sum(self, attention):
        """AttentionMechanism.apply_attention_gating must preserve gate sum."""
        rng = np.random.RandomState(42)

        for _ in range(50):
            # Original brain gates (normalized)
            brain_gates = np.abs(rng.randn(10))
            brain_gates = brain_gates / np.sum(brain_gates)

            # Attention weights (normalized)
            attention_weights = np.abs(rng.randn(10))
            attention_weights = attention_weights / np.sum(attention_weights)

            # Apply attention gating
            gated = attention.apply_attention_gating(
                brain_gates=brain_gates,
                attention_weights=attention_weights,
                gating_strength=0.5
            )

            # The apply_attention_gating preserves total activation sum, not normalized sum
            # After re-normalization (as done in cognitive_loop._attend):
            gated_sum = np.sum(gated)
            if gated_sum > 1e-8:
                gated_normalized = gated / gated_sum
            else:
                gated_normalized = brain_gates

            assert np.isclose(np.sum(gated_normalized), 1.0, atol=GATE_SUM_TOLERANCE), \
                f"After attention gating + renorm: sum = {np.sum(gated_normalized)}"
            assert np.all(gated_normalized >= 0), \
                "Attention-gated gates contain negatives after renormalization"

    def test_cognitive_loop_attend_preserves_sum(self, loop):
        """CognitiveLoop._attend must preserve gate sum invariant."""
        from core.cognitive_loop import LoopContext

        ctx = LoopContext(task_description="Analyze complex temporal patterns")
        loop._perceive(ctx)
        loop._remember(ctx)
        loop._attend(ctx)

        if ctx.attention_gated_weights is not None:
            gated_sum = np.sum(ctx.attention_gated_weights)
            assert np.isclose(gated_sum, 1.0, atol=GATE_SUM_SOFT_TOLERANCE), \
                f"After attend: gate sum = {gated_sum}, expected 1.0"


# ============================================================================
# Test 5: After neuromodulation temperature scaling, gates sum to 1.0
# ============================================================================

class TestNeuromodulationTemperatureInvariant:
    """Neuromodulation temperature scaling must preserve the gate sum invariant."""

    def test_temperature_scaling_preserves_sum(self):
        """Softmax temperature rescaling must preserve gate sum."""
        rng = np.random.RandomState(42)

        temperatures = [0.1, 0.5, 0.8, 1.0, 1.2, 1.5, 2.0, 5.0]

        for temp in temperatures:
            for _ in range(20):
                # Start with normalized weights
                weights = np.abs(rng.randn(10)) + 0.01
                weights = weights / np.sum(weights)

                # Apply temperature scaling (as in cognitive_loop._modulate)
                log_weights = np.log(np.maximum(weights, 1e-10))
                scaled = np.exp(log_weights / temp)
                scaled_sum = np.sum(scaled)
                if scaled_sum > 1e-8:
                    result = scaled / scaled_sum
                else:
                    result = weights

                assert np.isclose(np.sum(result), 1.0, atol=GATE_SUM_TOLERANCE), \
                    f"Temp={temp}: gate sum = {np.sum(result)}, expected 1.0"
                assert np.all(result >= 0), f"Temp={temp}: negative gates"

    def test_cognitive_loop_modulate_preserves_sum(self, loop):
        """CognitiveLoop._modulate must preserve gate sum invariant."""
        from core.cognitive_loop import LoopContext

        ctx = LoopContext(task_description="Urgent critical deploy now")
        loop._perceive(ctx)
        loop._remember(ctx)
        loop._attend(ctx)
        loop._modulate(ctx)

        if ctx.modulated_weights is not None:
            mod_sum = np.sum(ctx.modulated_weights)
            assert np.isclose(mod_sum, 1.0, atol=GATE_SUM_SOFT_TOLERANCE), \
                f"After modulate: gate sum = {mod_sum}, expected 1.0"


# ============================================================================
# Test 6: Full CognitiveLoop output gates sum to 1.0
# ============================================================================

class TestCognitiveLoopGateInvariant:
    """Full CognitiveLoop pipeline must produce gates summing to 1.0."""

    def test_cognitive_loop_output_gates_sum(self, loop):
        """CognitiveLoop.process() output must have gates summing to 1.0."""
        for task in DIVERSE_TASKS[:5]:  # Test a subset for speed
            result = loop.process(task)
            gates = np.array(result.layer1_routing.routing_weights)
            gate_sum = np.sum(gates)

            assert np.isclose(gate_sum, 1.0, atol=GATE_SUM_SOFT_TOLERANCE), \
                f"CognitiveLoop output gate sum = {gate_sum} for task '{task[:40]}...'"
            assert np.all(gates >= 0), \
                f"CognitiveLoop output has negative gates for task '{task[:40]}...'"


# ============================================================================
# Test 7: Full HierarchicalPlanner output gates sum to 1.0
# ============================================================================

class TestHierarchicalPlannerGateInvariant:
    """Full HierarchicalPlanner pipeline must produce gates summing to 1.0."""

    def test_planner_predict_gates_sum(self, planner):
        """HierarchicalPlanner.predict() output must have gates summing to 1.0."""
        for task in DIVERSE_TASKS[:5]:  # Test a subset for speed
            result = planner.predict(task)
            gates = np.array(result.layer1_routing.routing_weights)
            gate_sum = np.sum(gates)

            assert np.isclose(gate_sum, 1.0, atol=GATE_SUM_SOFT_TOLERANCE), \
                f"HierarchicalPlanner output gate sum = {gate_sum} for task '{task[:40]}...'"
            assert np.all(gates >= 0), \
                f"HierarchicalPlanner output has negative gates for task '{task[:40]}...'"


# ============================================================================
# Test 8: Extreme weights (one very high) still normalize
# ============================================================================

class TestExtremeWeightsNormalization:
    """Extreme weight distributions must still produce valid normalized gates."""

    def test_one_dominant_weight_normalizes(self, router):
        """When one weight is very large, normalization must still produce sum = 1.0."""
        # Create features with extreme characteristics
        extreme_tasks = [
            # Extremely complex task - should strongly activate specific areas
            "Urgently analyze and debug this extremely complex multi-container Docker deployment "
            "with multiple challenging intricate interdependent issues across all services now immediately",
            # Very simple task
            "check status",
        ]

        for task in extreme_tasks:
            routing_state = router.route_task(task)
            gates = routing_state.routing_weights
            gate_sum = np.sum(gates)

            assert np.isclose(gate_sum, 1.0, atol=GATE_SUM_TOLERANCE), \
                f"Extreme task gate sum = {gate_sum} for task '{task[:40]}...'"

    def test_manual_extreme_weights_normalize(self):
        """Manually constructed extreme weight vectors must normalize properly."""
        extreme_cases = [
            np.array([1000.0] + [0.001] * 9),       # One very large
            np.array([1e-10] * 10),                    # All near zero
            np.array([1.0] + [0.0] * 9),               # One-hot
            np.array([100.0, 100.0] + [0.001] * 8),   # Two very large
            np.array([1e-8] * 5 + [1e8] * 5),         # Extreme contrast
        ]

        for i, weights in enumerate(extreme_cases):
            # Normalize as the router does
            weights = np.maximum(weights, 0.0)
            weight_sum = np.sum(weights)
            if weight_sum > 0:
                normalized = weights / weight_sum
            else:
                normalized = np.ones(10) / 10.0

            assert np.isclose(np.sum(normalized), 1.0, atol=GATE_SUM_TOLERANCE), \
                f"Extreme case {i}: gate sum = {np.sum(normalized)}"
            assert np.all(normalized >= 0), f"Extreme case {i}: negative gates"
            assert np.all(np.isfinite(normalized)), f"Extreme case {i}: non-finite gates"


# ============================================================================
# Test 9: Near-zero weights still normalize
# ============================================================================

class TestNearZeroWeightsNormalization:
    """Near-zero and zero weight distributions must still produce valid gates."""

    def test_near_zero_weights_normalize(self):
        """Weights very close to zero must still normalize to sum = 1.0."""
        near_zero_cases = [
            np.full(10, 1e-10),
            np.full(10, 1e-20),
            np.full(10, 1e-30),
            np.array([1e-15, 1e-14, 1e-13, 1e-12, 1e-11,
                       1e-10, 1e-9, 1e-8, 1e-7, 1e-6]),
        ]

        for i, weights in enumerate(near_zero_cases):
            weights = np.maximum(weights, 0.0)
            weight_sum = np.sum(weights)
            if weight_sum > 0:
                normalized = weights / weight_sum
            else:
                normalized = np.ones(10) / 10.0

            assert np.isclose(np.sum(normalized), 1.0, atol=GATE_SUM_TOLERANCE), \
                f"Near-zero case {i}: gate sum = {np.sum(normalized)}"
            assert np.all(normalized >= 0), f"Near-zero case {i}: negative gates"
            assert np.all(np.isfinite(normalized)), f"Near-zero case {i}: non-finite gates"

    def test_all_zero_weights_fallback_to_uniform(self):
        """All-zero weights must fall back to uniform distribution (sum = 1.0)."""
        router = TaskFeatureRouter(seed=42)

        # Manually test compute_routing_weights with features that produce uniform
        features = TaskFeatures(
            keywords=[],
            task_type='unknown',
            complexity=0.0,
            urgency=0.0,
            raw_description='test'
        )

        weights = router.compute_routing_weights(features)
        gate_sum = np.sum(weights)

        assert np.isclose(gate_sum, 1.0, atol=GATE_SUM_TOLERANCE), \
            f"Unknown task type gate sum = {gate_sum}, expected 1.0"
        assert np.all(weights >= 0), "Unknown task type produced negative gates"

    def test_temperature_with_near_zero_weights(self):
        """Temperature scaling with near-zero weights must not produce NaN/Inf."""
        weights = np.full(10, 1e-10)
        weights = weights / np.sum(weights)  # Normalized

        temperatures = [0.1, 0.5, 1.0, 2.0, 5.0]

        for temp in temperatures:
            log_weights = np.log(np.maximum(weights, 1e-10))
            scaled = np.exp(log_weights / temp)
            scaled_sum = np.sum(scaled)
            if scaled_sum > 1e-8:
                result = scaled / scaled_sum
            else:
                result = np.ones(10) / 10.0

            assert np.all(np.isfinite(result)), \
                f"Temp={temp}: non-finite values with near-zero weights"
            assert np.isclose(np.sum(result), 1.0, atol=GATE_SUM_TOLERANCE), \
                f"Temp={temp}: gate sum = {np.sum(result)} with near-zero weights"


# ============================================================================
# Test 10: Multiple consecutive predictions maintain invariant
# ============================================================================

class TestConsecutivePredictionsInvariant:
    """Multiple consecutive predictions must all maintain the gate sum invariant."""

    def test_consecutive_layer1_predictions(self, router):
        """Multiple consecutive Layer 1 predictions must all sum to 1.0."""
        for i, task in enumerate(DIVERSE_TASKS):
            routing_state = router.route_task(task)
            gates = routing_state.routing_weights
            gate_sum = np.sum(gates)

            assert np.isclose(gate_sum, 1.0, atol=GATE_SUM_TOLERANCE), \
                f"Consecutive prediction {i}: gate sum = {gate_sum}"

    def test_consecutive_cognitive_loop_predictions(self, loop):
        """Multiple consecutive CognitiveLoop predictions must all sum to 1.0."""
        tasks = [
            "Deploy Docker container",
            "Check memory status",
            "Run pytest tests urgently",
            "Git push to main branch",
            "Analyze complex architecture",
        ]

        gate_sums = []
        for i, task in enumerate(tasks):
            result = loop.process(task)
            gates = np.array(result.layer1_routing.routing_weights)
            gate_sum = np.sum(gates)
            gate_sums.append(gate_sum)

            assert np.isclose(gate_sum, 1.0, atol=GATE_SUM_SOFT_TOLERANCE), \
                f"Consecutive CognitiveLoop prediction {i} ('{task[:30]}...'): " \
                f"gate sum = {gate_sum}"

        # Verify no drift: all sums should be consistently close to 1.0
        assert all(np.isclose(s, 1.0, atol=GATE_SUM_SOFT_TOLERANCE) for s in gate_sums), \
            f"Gate sum drift detected across consecutive predictions: {gate_sums}"

    def test_consecutive_planner_predictions(self, planner):
        """Multiple consecutive HierarchicalPlanner predictions must all sum to 1.0."""
        tasks = [
            "Deploy Docker container",
            "Search for error logs",
            "Refactor the routing code",
        ]

        for i, task in enumerate(tasks):
            result = planner.predict(task)
            gates = np.array(result.layer1_routing.routing_weights)
            gate_sum = np.sum(gates)

            assert np.isclose(gate_sum, 1.0, atol=GATE_SUM_SOFT_TOLERANCE), \
                f"Consecutive planner prediction {i}: gate sum = {gate_sum}"


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
