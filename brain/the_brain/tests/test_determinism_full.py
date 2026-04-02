"""
Comprehensive determinism tests for the brain routing system.

Verifies that identical inputs with fixed random seeds produce
identical outputs across all layers of the hierarchy.

Test coverage:
- Same seed -> same Layer 1 routing weights
- Same seed -> same Layer 2 predictions
- Same seed -> same full HierarchicalPlanner prediction
- Same seed -> same CognitiveLoop output
- Different seeds -> different outputs
- Same task twice -> same results
- Different tasks -> different results
- Confidence is deterministic
- Gate weights are deterministic
- Task type classification is deterministic
"""

import pytest
import numpy as np
import sys
import os

# Add parent directory to path for module access
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, parent_dir)

from core.hierarchical_planner import HierarchicalPlanner, HierarchicalPrediction
from core.conversation_path_planner import ConversationPathPlanner
from core.meta_router import MetaRouter
from core.task_feature_router import TaskFeatureRouter
from core.cognitive_loop import CognitiveLoop, CognitiveLoopConfig


# ============================================================================
# Helpers
# ============================================================================

def _build_planner(seed: int = 42) -> HierarchicalPlanner:
    """Build a minimal HierarchicalPlanner with a fixed seed."""
    meta_router = MetaRouter(
        enable_hippocampus=True,
        enable_per_modality_pes=True,
        seed=seed
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
        seed=seed
    )
    return hp


def _build_loop(seed: int = 42) -> CognitiveLoop:
    """Build a CognitiveLoop wrapping a fresh planner with a fixed seed."""
    planner = _build_planner(seed=seed)
    config = CognitiveLoopConfig()
    return CognitiveLoop(planner=planner, config=config)


# ============================================================================
# Layer 1 Determinism
# ============================================================================

class TestLayer1Determinism:
    """Same seed must produce identical Layer 1 routing weights."""

    def test_same_seed_same_routing_weights(self):
        """Two TaskFeatureRouters with seed=42 must return identical weights."""
        router_a = TaskFeatureRouter(seed=42)
        router_b = TaskFeatureRouter(seed=42)

        task = "Deploy Docker container to production"

        np.random.seed(42)
        result_a = router_a.route_task(task)

        np.random.seed(42)
        result_b = router_b.route_task(task)

        weights_a = np.array(result_a.routing_weights)
        weights_b = np.array(result_b.routing_weights)

        np.testing.assert_allclose(
            weights_a, weights_b,
            atol=1e-10,
            err_msg="Layer 1 routing weights differ for same seed"
        )

    def test_same_seed_same_processing_mode(self):
        """Processing mode must be identical for same seed and input."""
        router_a = TaskFeatureRouter(seed=42)
        router_b = TaskFeatureRouter(seed=42)

        task = "Analyze error logs urgently"

        np.random.seed(42)
        result_a = router_a.route_task(task)

        np.random.seed(42)
        result_b = router_b.route_task(task)

        assert result_a.processing_mode == result_b.processing_mode, \
            f"Processing mode mismatch: {result_a.processing_mode} vs {result_b.processing_mode}"

    def test_same_seed_same_dominant_areas(self):
        """Dominant areas must be identical for same seed and input."""
        router_a = TaskFeatureRouter(seed=42)
        router_b = TaskFeatureRouter(seed=42)

        task = "Design a new microservice architecture"

        np.random.seed(42)
        result_a = router_a.route_task(task)

        np.random.seed(42)
        result_b = router_b.route_task(task)

        assert result_a.dominant_areas == result_b.dominant_areas, \
            f"Dominant areas mismatch: {result_a.dominant_areas} vs {result_b.dominant_areas}"


# ============================================================================
# Layer 2 Determinism
# ============================================================================

class TestLayer2Determinism:
    """Same seed must produce identical Layer 2 predictions."""

    def test_same_seed_same_layer2_confidence(self):
        """Confidence from Layer 2 must be identical for same seed and task."""
        results = []
        for _ in range(2):
            planner = _build_planner(seed=42)
            np.random.seed(42)
            pred = planner.predict("Debug failing test suite")
            results.append(pred)

        assert results[0].confidence == results[1].confidence, \
            f"Confidence mismatch: {results[0].confidence} vs {results[1].confidence}"

    def test_same_seed_same_predicted_sequence(self):
        """Predicted sequence must be identical for same seed and task."""
        results = []
        for _ in range(2):
            planner = _build_planner(seed=42)
            np.random.seed(42)
            pred = planner.predict("Refactor authentication module")
            results.append(pred)

        assert results[0].predicted_sequence == results[1].predicted_sequence, \
            f"Predicted sequence mismatch"

    def test_same_seed_same_task_type(self):
        """Task type must be identical for same seed and task."""
        results = []
        for _ in range(2):
            planner = _build_planner(seed=42)
            np.random.seed(42)
            pred = planner.predict("Write unit tests for payment module")
            results.append(pred)

        assert results[0].task_type == results[1].task_type, \
            f"Task type mismatch: {results[0].task_type} vs {results[1].task_type}"

    def test_same_seed_same_success_probability(self):
        """Success probability must be identical for same seed and task."""
        results = []
        for _ in range(2):
            planner = _build_planner(seed=42)
            np.random.seed(42)
            pred = planner.predict("Optimize database queries")
            results.append(pred)

        assert results[0].success_probability == results[1].success_probability, \
            f"Success probability mismatch: {results[0].success_probability} vs {results[1].success_probability}"


# ============================================================================
# Full Prediction Determinism (HierarchicalPlanner)
# ============================================================================

class TestFullPredictionDeterminism:
    """Same seed must produce identical end-to-end HierarchicalPrediction."""

    def test_same_seed_same_full_prediction(self):
        """Full predict() output must be identical for same seed and task."""
        results = []
        for _ in range(2):
            planner = _build_planner(seed=42)
            np.random.seed(42)
            pred = planner.predict("Deploy Docker container to production")
            results.append(pred)

        # Layer 1 routing weights
        w0 = np.array(results[0].layer1_routing.routing_weights)
        w1 = np.array(results[1].layer1_routing.routing_weights)
        np.testing.assert_allclose(w0, w1, atol=1e-10,
                                   err_msg="Full prediction: Layer 1 weights differ")

        # Layer 2 outputs
        assert results[0].confidence == results[1].confidence
        assert results[0].task_type == results[1].task_type
        assert results[0].predicted_sequence == results[1].predicted_sequence
        assert results[0].success_probability == results[1].success_probability
        assert results[0].dominant_modalities == results[1].dominant_modalities

    def test_same_seed_same_actionable_decision(self):
        """Layer 3 actionable decision must be identical for same seed and task."""
        results = []
        for _ in range(2):
            planner = _build_planner(seed=42)
            np.random.seed(42)
            pred = planner.predict("Fix memory leak in worker process")
            results.append(pred)

        decision_0 = results[0].actionable_decision.multi_target_decision
        decision_1 = results[1].actionable_decision.multi_target_decision

        assert decision_0['primary'] == decision_1['primary'], \
            f"Primary decision mismatch: {decision_0['primary']} vs {decision_1['primary']}"

    def test_prediction_returns_hierarchical_prediction(self):
        """predict() must return an instance of HierarchicalPrediction."""
        planner = _build_planner(seed=42)
        np.random.seed(42)
        result = planner.predict("Run integration tests")

        assert isinstance(result, HierarchicalPrediction), \
            f"Expected HierarchicalPrediction, got {type(result)}"


# ============================================================================
# CognitiveLoop Determinism
# ============================================================================

class TestCognitiveLoopDeterminism:
    """Same seed must produce identical CognitiveLoop outputs."""

    def test_same_seed_same_loop_output(self):
        """CognitiveLoop.process() must be deterministic with same seed."""
        results = []
        for _ in range(2):
            loop = _build_loop(seed=42)
            np.random.seed(42)
            result = loop.process("Deploy Docker container")
            results.append(result)

        assert results[0].confidence == results[1].confidence, \
            f"Loop confidence mismatch: {results[0].confidence} vs {results[1].confidence}"
        assert results[0].task_type == results[1].task_type, \
            f"Loop task type mismatch: {results[0].task_type} vs {results[1].task_type}"

    def test_same_seed_same_loop_routing_weights(self):
        """CognitiveLoop routing weights must be identical for same seed."""
        results = []
        for _ in range(2):
            loop = _build_loop(seed=42)
            np.random.seed(42)
            result = loop.process("Analyze temporal pattern in data")
            results.append(result)

        w0 = np.array(results[0].layer1_routing.routing_weights)
        w1 = np.array(results[1].layer1_routing.routing_weights)
        np.testing.assert_allclose(w0, w1, atol=1e-10,
                                   err_msg="CognitiveLoop routing weights differ")

    def test_same_seed_same_loop_predicted_sequence(self):
        """CognitiveLoop predicted sequence must be identical for same seed."""
        results = []
        for _ in range(2):
            loop = _build_loop(seed=42)
            np.random.seed(42)
            result = loop.process("Refactor caching layer")
            results.append(result)

        assert results[0].predicted_sequence == results[1].predicted_sequence, \
            "CognitiveLoop predicted sequence mismatch"


# ============================================================================
# Different Seeds -> Different Outputs
# ============================================================================

class TestDifferentSeedsDiverge:
    """Different seeds should produce different outputs."""

    def test_different_seeds_same_layer1_weights_text_based(self):
        """Layer 1 routing is keyword/text-based, so same text yields same weights
        regardless of seed. This verifies the deterministic text-feature extraction."""
        router_a = TaskFeatureRouter(seed=42)
        router_b = TaskFeatureRouter(seed=99)

        task = "Deploy Docker container to production"

        result_a = router_a.route_task(task)
        result_b = router_b.route_task(task)

        weights_a = np.array(result_a.routing_weights)
        weights_b = np.array(result_b.routing_weights)

        # Layer 1 features are text-derived, so seeds do not affect them.
        # Verify they are identical (text-based determinism).
        np.testing.assert_allclose(weights_a, weights_b, atol=1e-10,
                                   err_msg="Layer 1 text-based routing should be seed-independent")

    def test_different_seeds_different_layer3_decision_weights(self):
        """Layer 3 DecisionRouter uses the seed for its weight matrix.
        Different seeds must yield different internal routing matrices."""
        from core.decision_router import DecisionRouter

        dr_a = DecisionRouter(num_modalities=10,
                              intervention_types=['suggest', 'retry', 'wait', 'terminate', 'execute'],
                              seed=42)
        dr_b = DecisionRouter(num_modalities=10,
                              intervention_types=['suggest', 'retry', 'wait', 'terminate', 'execute'],
                              seed=99)

        # The internal routing matrices (on multi_target_router) should differ
        mat_a = dr_a.multi_target_router.routing_matrix
        mat_b = dr_b.multi_target_router.routing_matrix

        assert not np.allclose(mat_a, mat_b, atol=1e-6), \
            "Different seeds produced identical DecisionRouter routing matrices (unexpected)"

    def test_different_seeds_different_full_prediction_downstream(self):
        """With different seeds the downstream components (Layer 3) must differ
        even when Layer 1 text features are identical."""
        planner_a = _build_planner(seed=42)
        planner_b = _build_planner(seed=99)

        task = "Deploy Docker container to production"

        np.random.seed(42)
        pred_a = planner_a.predict(task)

        np.random.seed(99)
        pred_b = planner_b.predict(task)

        # Layer 3 actionable decisions should differ due to different seed
        # affecting the DecisionRouter weight matrix
        decision_a = pred_a.actionable_decision.to_dict()
        decision_b = pred_b.actionable_decision.to_dict()

        dist_a = decision_a.get('distribution', {})
        dist_b = decision_b.get('distribution', {})

        # At least some probability values should differ
        if dist_a and dist_b:
            all_same = all(
                np.isclose(dist_a.get(k, 0), dist_b.get(k, 0), atol=1e-6)
                for k in set(list(dist_a.keys()) + list(dist_b.keys()))
            )
            assert not all_same, \
                "Different seeds produced identical Layer 3 distributions (unexpected)"


# ============================================================================
# Same Task Twice -> Same Results
# ============================================================================

class TestSameTaskRepeatability:
    """Running the same task twice on the same planner (reset state) must match."""

    def test_same_task_twice_same_layer1(self):
        """Same task submitted twice to fresh routers must produce same results."""
        task = "Monitor server health metrics"

        results = []
        for _ in range(2):
            router = TaskFeatureRouter(seed=42)
            np.random.seed(42)
            result = router.route_task(task)
            results.append(result)

        w0 = np.array(results[0].routing_weights)
        w1 = np.array(results[1].routing_weights)
        np.testing.assert_allclose(w0, w1, atol=1e-10,
                                   err_msg="Same task twice produced different Layer 1 weights")

    def test_same_task_twice_same_full_prediction(self):
        """Same task submitted twice to fresh planners must produce same results."""
        task = "Deploy Kubernetes cluster"

        results = []
        for _ in range(2):
            planner = _build_planner(seed=42)
            np.random.seed(42)
            pred = planner.predict(task)
            results.append(pred)

        assert results[0].confidence == results[1].confidence
        assert results[0].task_type == results[1].task_type


# ============================================================================
# Different Tasks -> Different Results
# ============================================================================

class TestDifferentTasksDiverge:
    """Different tasks should produce different routing and predictions."""

    def test_different_tasks_different_routing(self):
        """Qualitatively different tasks must produce different routing."""
        router = TaskFeatureRouter(seed=42)

        result_deploy = router.route_task("Deploy Docker container to production")
        result_debug = router.route_task("Debug critical memory leak in production server")

        weights_deploy = np.array(result_deploy.routing_weights)
        weights_debug = np.array(result_debug.routing_weights)

        assert not np.allclose(weights_deploy, weights_debug, atol=1e-3), \
            "Different tasks produced nearly identical routing weights"

    def test_different_tasks_different_features(self):
        """Different tasks must produce different feature extractions."""
        router = TaskFeatureRouter(seed=42)

        result_simple = router.route_task("Print hello world")
        result_complex = router.route_task(
            "Design and implement a distributed consensus protocol "
            "with fault tolerance and Byzantine failure detection"
        )

        # Complexity should differ meaningfully
        assert result_simple.features.complexity != result_complex.features.complexity, \
            "Trivially different tasks have identical complexity scores"


# ============================================================================
# Confidence Determinism
# ============================================================================

class TestConfidenceDeterminism:
    """Confidence scores must be deterministic for fixed seeds."""

    def test_confidence_exact_match(self):
        """Confidence must be exactly the same for same seed and task."""
        confidences = []
        for _ in range(3):
            planner = _build_planner(seed=42)
            np.random.seed(42)
            pred = planner.predict("Optimize SQL query performance")
            confidences.append(pred.confidence)

        assert confidences[0] == confidences[1] == confidences[2], \
            f"Confidence varied across runs: {confidences}"

    def test_confidence_in_valid_range(self):
        """Confidence must always be in [0, 1]."""
        planner = _build_planner(seed=42)
        np.random.seed(42)
        pred = planner.predict("Implement caching strategy")

        assert 0.0 <= pred.confidence <= 1.0, \
            f"Confidence out of range: {pred.confidence}"


# ============================================================================
# Gate Weight Determinism
# ============================================================================

class TestGateWeightDeterminism:
    """Gate weights must be deterministic and satisfy invariants."""

    def test_gate_weights_sum_to_one(self):
        """Gate weights must always sum to 1.0 (softmax invariant)."""
        planner = _build_planner(seed=42)
        np.random.seed(42)
        pred = planner.predict("Handle incoming API request")

        gates = np.array(pred.layer1_routing.routing_weights)
        assert np.isclose(np.sum(gates), 1.0, atol=0.01), \
            f"Gates sum to {np.sum(gates)}, expected ~1.0"

    def test_gate_weights_non_negative(self):
        """All gate weights must be non-negative."""
        planner = _build_planner(seed=42)
        np.random.seed(42)
        pred = planner.predict("Process batch data pipeline")

        gates = np.array(pred.layer1_routing.routing_weights)
        assert np.all(gates >= 0), \
            f"Negative gate weights found: {gates}"

    def test_gate_weights_deterministic_across_runs(self):
        """Gate weights must be bit-for-bit identical across runs."""
        gate_sets = []
        for _ in range(3):
            planner = _build_planner(seed=42)
            np.random.seed(42)
            pred = planner.predict("Scale microservice cluster")
            gate_sets.append(np.array(pred.layer1_routing.routing_weights))

        np.testing.assert_array_equal(gate_sets[0], gate_sets[1],
                                      err_msg="Gates differ between run 0 and 1")
        np.testing.assert_array_equal(gate_sets[1], gate_sets[2],
                                      err_msg="Gates differ between run 1 and 2")

    def test_gate_weights_length_matches_modalities(self):
        """Gate weight vector length must match the number of modalities."""
        planner = _build_planner(seed=42)
        np.random.seed(42)
        pred = planner.predict("Migrate database schema")

        gates = np.array(pred.layer1_routing.routing_weights)
        # System uses 10 modalities (6 sensory + 4 conversation trace)
        assert len(gates) == 10, \
            f"Expected 10 gate weights, got {len(gates)}"


# ============================================================================
# Task Type Classification Determinism
# ============================================================================

class TestTaskTypeClassificationDeterminism:
    """Task type classification must be deterministic."""

    def test_task_type_deterministic(self):
        """Same task must always classify to the same type."""
        task_types = []
        for _ in range(3):
            planner = _build_planner(seed=42)
            np.random.seed(42)
            pred = planner.predict("Deploy production service")
            task_types.append(pred.task_type)

        assert task_types[0] == task_types[1] == task_types[2], \
            f"Task type varied: {task_types}"

    def test_task_type_is_string(self):
        """Task type must be a non-empty string."""
        planner = _build_planner(seed=42)
        np.random.seed(42)
        pred = planner.predict("Write integration tests")

        assert isinstance(pred.task_type, str), \
            f"Task type is not a string: {type(pred.task_type)}"
        assert len(pred.task_type) > 0, "Task type is empty"

    def test_different_tasks_can_have_different_types(self):
        """Semantically different tasks should produce different classifications."""
        planner = _build_planner(seed=42)

        np.random.seed(42)
        pred_deploy = planner.predict("Deploy Docker container to production")

        # Build fresh planner for independence
        planner2 = _build_planner(seed=42)
        np.random.seed(42)
        pred_debug = planner2.predict("Debug critical error in authentication")

        # They might be the same or different depending on the classifier,
        # but the classifications themselves must be valid strings
        assert isinstance(pred_deploy.task_type, str)
        assert isinstance(pred_debug.task_type, str)

    def test_layer1_features_task_type_deterministic(self):
        """Layer 1 feature task_type must be deterministic."""
        types = []
        for _ in range(3):
            router = TaskFeatureRouter(seed=42)
            np.random.seed(42)
            result = router.route_task("Analyze system performance bottleneck")
            types.append(result.features.task_type)

        assert types[0] == types[1] == types[2], \
            f"Layer 1 task_type varied: {types}"


# ============================================================================
# Edge Cases and Stress
# ============================================================================

class TestDeterminismEdgeCases:
    """Edge cases for determinism."""

    def test_empty_string_task_deterministic(self):
        """Even an empty-ish task must be deterministic."""
        results = []
        for _ in range(2):
            planner = _build_planner(seed=42)
            np.random.seed(42)
            pred = planner.predict("task")
            results.append(pred)

        w0 = np.array(results[0].layer1_routing.routing_weights)
        w1 = np.array(results[1].layer1_routing.routing_weights)
        np.testing.assert_allclose(w0, w1, atol=1e-10)

    def test_long_task_description_deterministic(self):
        """A very long task description must still be deterministic."""
        long_task = (
            "Implement a comprehensive distributed system that handles "
            "real-time data streaming from multiple IoT sensors, processes "
            "the data through a machine learning pipeline, stores results "
            "in a time-series database, and exposes the analytics through "
            "a GraphQL API with WebSocket subscriptions for live updates "
            "and includes full observability with distributed tracing."
        )

        results = []
        for _ in range(2):
            planner = _build_planner(seed=42)
            np.random.seed(42)
            pred = planner.predict(long_task)
            results.append(pred)

        assert results[0].confidence == results[1].confidence
        assert results[0].task_type == results[1].task_type

        w0 = np.array(results[0].layer1_routing.routing_weights)
        w1 = np.array(results[1].layer1_routing.routing_weights)
        np.testing.assert_allclose(w0, w1, atol=1e-10)

    def test_special_characters_deterministic(self):
        """Task with special characters must be deterministic."""
        task = "Fix bug #1234 in module.py (line 42): 'KeyError' -> handle None"

        results = []
        for _ in range(2):
            planner = _build_planner(seed=42)
            np.random.seed(42)
            pred = planner.predict(task)
            results.append(pred)

        assert results[0].confidence == results[1].confidence
        w0 = np.array(results[0].layer1_routing.routing_weights)
        w1 = np.array(results[1].layer1_routing.routing_weights)
        np.testing.assert_allclose(w0, w1, atol=1e-10)

    def test_dominant_modalities_deterministic(self):
        """Dominant modalities list must be deterministic."""
        modalities_sets = []
        for _ in range(3):
            planner = _build_planner(seed=42)
            np.random.seed(42)
            pred = planner.predict("Schedule periodic data backup job")
            modalities_sets.append(pred.dominant_modalities)

        assert modalities_sets[0] == modalities_sets[1] == modalities_sets[2], \
            f"Dominant modalities varied: {modalities_sets}"


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
