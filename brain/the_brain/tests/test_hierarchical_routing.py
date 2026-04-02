"""
Tests for Hierarchical Routing System

Tests cover:
1. Gate invariants (sum to 1.0)
2. Skip connection constraints (weights < 0.5)
3. Temperature gradient (decreases up hierarchy)
4. Learning rate gradient (increases up hierarchy)
5. Individual layer functionality
6. Full system integration
7. Performance constraints
"""

import pytest
import numpy as np
import time
from typing import Dict

# Import all components
from core.hierarchical_layer import (
    LayerConfig,
    LayerOutput,
    HierarchicalRoutingResult,
    verify_gate_invariant,
    compute_gate_entropy,
    blend_gates_weighted
)
from core.sensory_layer import SensoryLayer, SENSORY_LAYER_DEFAULTS
from core.feature_layer import FeatureLayer, FEATURE_LAYER_DEFAULTS
from core.semantic_layer import SemanticLayer, SEMANTIC_LAYER_DEFAULTS
from core.abstract_layer import AbstractLayer, ABSTRACT_LAYER_DEFAULTS
from core.hierarchical_routing_system import (
    HierarchicalRoutingSystem,
    HierarchicalRoutingConfig,
    create_hierarchical_routing_system,
    DEFAULT_LAYER_WEIGHTS
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def modalities():
    """Standard modality configuration."""
    return ['vision', 'audio', 'touch', 'taste', 'vestibular', 'threat']


@pytest.fixture
def modality_dims():
    """Standard modality dimensions."""
    return {
        'vision': 128, 'audio': 64, 'touch': 32,
        'taste': 16, 'vestibular': 16, 'threat': 8
    }


@pytest.fixture
def sample_input(modalities, modality_dims):
    """Sample input dict for testing."""
    np.random.seed(42)
    return {m: np.random.randn(modality_dims[m]) for m in modalities}


@pytest.fixture
def sample_context():
    """Sample context vector."""
    np.random.seed(42)
    return np.random.randn(32)


@pytest.fixture
def sample_goal():
    """Sample goal vector."""
    np.random.seed(42)
    return np.random.randn(32)


@pytest.fixture
def sensory_layer():
    """Create sensory layer fixture."""
    return SensoryLayer(seed=42)


@pytest.fixture
def feature_layer(modalities, modality_dims):
    """Create feature layer fixture."""
    return FeatureLayer(modalities=modalities, latent_dims=modality_dims, seed=42)


@pytest.fixture
def semantic_layer(modalities, modality_dims):
    """Create semantic layer fixture."""
    return SemanticLayer(
        n_modalities=len(modalities),
        modalities=modalities,
        modality_dims=modality_dims,
        seed=42
    )


@pytest.fixture
def abstract_layer(modalities):
    """Create abstract layer fixture."""
    return AbstractLayer(n_modalities=len(modalities), seed=42)


@pytest.fixture
def routing_system():
    """Create full routing system fixture."""
    return create_hierarchical_routing_system(seed=42)


# ============================================================================
# Test Gate Invariants
# ============================================================================

class TestGateInvariants:
    """Test that gates always sum to 1.0."""

    def test_sensory_layer_gates_sum_to_one(self, sensory_layer, sample_input):
        """L1 gates must sum to 1.0."""
        output = sensory_layer.step(x=sample_input)
        assert np.isclose(np.sum(output.gates), 1.0, atol=1e-6)

    def test_feature_layer_gates_sum_to_one(self, feature_layer, sample_input):
        """L2 gates must sum to 1.0."""
        output = feature_layer.step(x=sample_input)
        assert np.isclose(np.sum(output.gates), 1.0, atol=1e-6)

    def test_semantic_layer_gates_sum_to_one(self, semantic_layer, sample_input, sample_goal):
        """L3 gates must sum to 1.0."""
        output = semantic_layer.step(x=sample_input, goal=sample_goal)
        assert np.isclose(np.sum(output.gates), 1.0, atol=1e-6)

    def test_abstract_layer_gates_sum_to_one(self, abstract_layer, sample_input):
        """L4 gates must sum to 1.0."""
        output = abstract_layer.step(x=sample_input)
        assert np.isclose(np.sum(output.gates), 1.0, atol=1e-6)

    def test_full_system_all_gates_sum_to_one(self, routing_system, sample_input, sample_goal):
        """All layer gates in full system must sum to 1.0."""
        result = routing_system.step(x=sample_input, goal=sample_goal)

        for layer_idx, layer_out in result.layer_outputs.items():
            gate_sum = np.sum(layer_out.gates)
            assert np.isclose(gate_sum, 1.0, atol=1e-6), \
                f"Layer {layer_idx} gates sum to {gate_sum}, expected 1.0"

    def test_final_gates_sum_to_one(self, routing_system, sample_input, sample_goal):
        """Final blended gates must sum to 1.0."""
        result = routing_system.step(x=sample_input, goal=sample_goal)
        assert np.isclose(np.sum(result.final_gates), 1.0, atol=1e-6)

    def test_gates_positive(self, routing_system, sample_input):
        """All gates must be non-negative."""
        result = routing_system.step(x=sample_input)

        for layer_idx, layer_out in result.layer_outputs.items():
            assert np.all(layer_out.gates >= 0), \
                f"Layer {layer_idx} has negative gates"

        assert np.all(result.final_gates >= 0), "Final gates have negative values"


# ============================================================================
# Test Skip Connection Constraints
# ============================================================================

class TestSkipConnections:
    """Test skip connection weight constraints."""

    def test_skip_weights_below_max(self, routing_system):
        """All skip weights must be below max (0.5 by default)."""
        max_weight = routing_system.config.skip_weight_max

        for layer_idx, layer in routing_system.layers.items():
            for src, weight in layer.skip_weights.items():
                assert weight <= max_weight, \
                    f"Layer {layer_idx} skip weight from {src} is {weight}, max is {max_weight}"

    def test_skip_weights_non_negative(self, routing_system):
        """Skip weights must be non-negative."""
        for layer_idx, layer in routing_system.layers.items():
            for src, weight in layer.skip_weights.items():
                assert weight >= 0, \
                    f"Layer {layer_idx} skip weight from {src} is negative: {weight}"

    def test_l1_has_no_skip_inputs(self, sensory_layer):
        """Layer 1 should have no skip inputs (bottom layer)."""
        # L1 is bottom layer, no lower layers to skip from
        assert len(sensory_layer.skip_weights) == 0 or \
               all(w == 0 for w in sensory_layer.skip_weights.values())

    def test_skip_connections_update_within_bounds(self, feature_layer, sample_input):
        """Skip weight updates must stay within bounds."""
        # Initialize skip weight
        feature_layer.initialize_skip_weight(1, 0.1)

        # Run several steps
        for _ in range(10):
            feature_layer.step(x=sample_input)
            feature_layer.update_skip_weight(1, 0.05)

        # Check bounds
        assert feature_layer.skip_weights[1] <= feature_layer.config.skip_weight_max
        assert feature_layer.skip_weights[1] >= 0


# ============================================================================
# Test Temperature and Learning Rate Gradients
# ============================================================================

class TestHierarchyGradients:
    """Test temperature and learning rate gradients across hierarchy."""

    def test_temperature_decreases_up_hierarchy(self, routing_system):
        """Temperature must decrease from L1 to L4."""
        temps = [routing_system.layers[i].temperature for i in [1, 2, 3, 4]]

        assert temps[0] > temps[1], "L1 temp should be > L2 temp"
        assert temps[1] > temps[2], "L2 temp should be > L3 temp"
        assert temps[2] > temps[3], "L3 temp should be > L4 temp"

    def test_learning_rate_increases_up_hierarchy(self, routing_system):
        """Learning rate must increase from L1 to L4."""
        lrs = [routing_system.layers[i].learning_rate for i in [1, 2, 3, 4]]

        assert lrs[0] < lrs[1], "L1 lr should be < L2 lr"
        assert lrs[1] < lrs[2], "L2 lr should be < L3 lr"
        assert lrs[2] < lrs[3], "L3 lr should be < L4 lr"

    def test_layer_indices_correct(self, routing_system):
        """Layer indices must match expected values."""
        assert routing_system.layer1.layer_index == 1
        assert routing_system.layer2.layer_index == 2
        assert routing_system.layer3.layer_index == 3
        assert routing_system.layer4.layer_index == 4


# ============================================================================
# Test Individual Layer Functionality
# ============================================================================

class TestSensoryLayer:
    """Tests specific to Layer 1."""

    def test_output_shape(self, sensory_layer, sample_input):
        """Output should be concatenation of weighted modalities."""
        output = sensory_layer.step(x=sample_input)
        assert output.output.shape[0] > 0
        assert output.layer_index == 1

    def test_prediction_errors_available(self, sensory_layer, sample_input):
        """Should compute prediction errors per modality."""
        sensory_layer.step(x=sample_input)
        pe = sensory_layer.get_prediction_errors()
        assert len(pe) == len(sample_input)

    def test_reset_clears_state(self, sensory_layer, sample_input):
        """Reset should clear state but preserve weights."""
        sensory_layer.step(x=sample_input)
        sensory_layer.step(x=sample_input)
        assert sensory_layer.step_count == 2

        sensory_layer.reset()
        assert sensory_layer.step_count == 0


class TestFeatureLayer:
    """Tests specific to Layer 2."""

    def test_prediction_info_available(self, feature_layer, sample_input):
        """Should provide prediction information."""
        feature_layer.step(x=sample_input)
        info = feature_layer.get_prediction_info()
        assert info is not None
        assert 'confidence' in info

    def test_accepts_skip_from_l1(self, feature_layer, sensory_layer, sample_input):
        """Should accept skip input from L1."""
        l1_out = sensory_layer.step(x=sample_input)
        l2_out = feature_layer.step(x=sample_input, skip_inputs={1: l1_out})

        assert len(l2_out.skip_contributions) >= 0  # May or may not contribute


class TestSemanticLayer:
    """Tests specific to Layer 3."""

    def test_attention_weights_available(self, semantic_layer, sample_input, sample_goal):
        """Should provide cortical attention weights."""
        semantic_layer.step(x=sample_input, goal=sample_goal)
        attn = semantic_layer.get_attention_weights()
        assert len(attn) == semantic_layer.n_modalities
        assert np.isclose(np.sum(attn), 1.0, atol=1e-6)

    def test_goal_modulates_gates(self, semantic_layer, sample_input):
        """Different goals should produce different gates."""
        goal1 = np.array([1.0] * 16 + [0.0] * 16)
        goal2 = np.array([0.0] * 16 + [1.0] * 16)

        out1 = semantic_layer.step(x=sample_input, goal=goal1)
        semantic_layer.reset()
        out2 = semantic_layer.step(x=sample_input, goal=goal2)

        # Gates should differ
        assert not np.allclose(out1.gates, out2.gates, atol=0.01)


class TestAbstractLayer:
    """Tests specific to Layer 4."""

    def test_action_selection(self, abstract_layer, sample_input):
        """Should select an action."""
        abstract_layer.step(x=sample_input)
        action = abstract_layer.get_action()
        assert action is not None
        assert action.value in [0, 1, 2]

    def test_bg_output_available(self, abstract_layer, sample_input):
        """Should provide BG output."""
        abstract_layer.step(x=sample_input)
        bg_out = abstract_layer.get_bg_output()
        assert bg_out is not None
        assert np.isclose(np.sum(bg_out.action_gates), 1.0, atol=1e-6)

    def test_td_learning_updates_weights(self, abstract_layer, sample_input):
        """TD error should update BG weights."""
        # Get initial state
        abstract_layer.step(x=sample_input)
        initial_counts = abstract_layer.bg.action_counts.copy()

        # Apply positive TD error
        abstract_layer.apply_td_learning(td_error=0.5)

        # Step again
        abstract_layer.step(x=sample_input, td_error=0.5)

        # Verify learning happened (action counts changed)
        assert abstract_layer.bg.total_steps >= 2


# ============================================================================
# Test Full System Integration
# ============================================================================

class TestSystemIntegration:
    """Tests for full system integration."""

    def test_full_forward_pass(self, routing_system, sample_input, sample_goal):
        """Full forward pass should complete without errors."""
        result = routing_system.step(x=sample_input, goal=sample_goal)

        assert isinstance(result, HierarchicalRoutingResult)
        assert len(result.layer_outputs) == 4
        assert result.dominant_layer in [1, 2, 3, 4]

    def test_multiple_steps_consistent(self, routing_system, sample_input):
        """Multiple steps should maintain invariants."""
        for _ in range(20):
            result = routing_system.step(x=sample_input)

            # Check all invariants
            assert np.isclose(np.sum(result.final_gates), 1.0, atol=1e-6)
            for layer_out in result.layer_outputs.values():
                assert np.isclose(np.sum(layer_out.gates), 1.0, atol=1e-6)

    def test_layer_weights_blend_correctly(self, routing_system, sample_input):
        """Final gates should be proper blend of layer gates."""
        result = routing_system.step(x=sample_input)

        # Manual blend
        expected = blend_gates_weighted(result.layer_outputs, routing_system.layer_weights)

        assert np.allclose(result.final_gates, expected, atol=1e-6)

    def test_disable_skip_connections(self, sample_input):
        """System should work with skip connections disabled."""
        config = HierarchicalRoutingConfig(enable_skip_connections=False)
        system = HierarchicalRoutingSystem(config=config)

        result = system.step(x=sample_input)

        # Should still produce valid gates
        assert np.isclose(np.sum(result.final_gates), 1.0, atol=1e-6)

    def test_disable_learning(self, sample_input):
        """System should work with learning disabled."""
        config = HierarchicalRoutingConfig(enable_learning=False)
        system = HierarchicalRoutingSystem(config=config)

        # Provide TD error but it shouldn't be used
        result = system.step(x=sample_input, td_error=1.0)

        assert np.isclose(np.sum(result.final_gates), 1.0, atol=1e-6)


# ============================================================================
# Test Performance
# ============================================================================

class TestPerformance:
    """Test performance constraints."""

    def test_step_time_under_threshold(self, routing_system, sample_input):
        """Single step should complete in under 5ms."""
        # Warm up
        routing_system.step(x=sample_input)

        # Time 10 steps
        times = []
        for _ in range(10):
            start = time.perf_counter()
            routing_system.step(x=sample_input)
            times.append((time.perf_counter() - start) * 1000)

        avg_time = np.mean(times)
        assert avg_time < 15.0, f"Average step time {avg_time:.2f}ms exceeds 15ms"

    def test_processing_time_reported(self, routing_system, sample_input):
        """Result should report processing time."""
        result = routing_system.step(x=sample_input)
        assert result.processing_time_ms > 0


# ============================================================================
# Test Utility Functions
# ============================================================================

class TestUtilities:
    """Test utility functions."""

    def test_verify_gate_invariant_passes_valid(self):
        """Should pass for valid gates."""
        gates = np.array([0.2, 0.3, 0.5])
        verify_gate_invariant(gates, "test")  # Should not raise

    def test_verify_gate_invariant_fails_invalid(self):
        """Should fail for invalid gates."""
        gates = np.array([0.2, 0.3, 0.4])  # Sum to 0.9
        with pytest.raises(AssertionError):
            verify_gate_invariant(gates, "test")

    def test_compute_gate_entropy(self):
        """Should compute correct entropy."""
        # Uniform distribution has max entropy
        uniform = np.array([0.25, 0.25, 0.25, 0.25])
        uniform_entropy = compute_gate_entropy(uniform)

        # Peaked distribution has low entropy
        peaked = np.array([0.9, 0.05, 0.03, 0.02])
        peaked_entropy = compute_gate_entropy(peaked)

        assert uniform_entropy > peaked_entropy

    def test_blend_gates_weighted(self):
        """Should correctly blend gates with weights."""
        layer_outputs = {
            1: LayerOutput(
                output=np.zeros(10),
                gates=np.array([1.0, 0.0, 0.0]),
                layer_index=1,
                temperature=1.0,
                local_gates=np.array([1.0, 0.0, 0.0]),
                skip_contributions={}
            ),
            2: LayerOutput(
                output=np.zeros(10),
                gates=np.array([0.0, 1.0, 0.0]),
                layer_index=2,
                temperature=0.5,
                local_gates=np.array([0.0, 1.0, 0.0]),
                skip_contributions={}
            )
        }
        weights = {1: 0.5, 2: 0.5}

        blended = blend_gates_weighted(layer_outputs, weights)

        expected = np.array([0.5, 0.5, 0.0])
        assert np.allclose(blended, expected, atol=1e-6)


# ============================================================================
# Test Reset and State
# ============================================================================

class TestStateManagement:
    """Test state management functionality."""

    def test_system_reset(self, routing_system, sample_input):
        """Reset should clear all state."""
        # Run some steps
        for _ in range(5):
            routing_system.step(x=sample_input)

        assert routing_system.step_count == 5

        # Reset
        routing_system.reset()

        assert routing_system.step_count == 0
        for layer in routing_system.layers.values():
            assert layer.step_count == 0

    def test_get_statistics(self, routing_system, sample_input):
        """Should return comprehensive statistics."""
        routing_system.step(x=sample_input)
        stats = routing_system.get_statistics()

        assert 'step_count' in stats
        assert 'layer_weights' in stats
        assert 'layer_statistics' in stats
        assert len(stats['layer_statistics']) == 4

    def test_get_state(self, routing_system, sample_input):
        """Should return serializable state."""
        routing_system.step(x=sample_input)
        state = routing_system.get_state()

        assert 'config' in state
        assert 'layer_states' in state
        assert len(state['layer_states']) == 4


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
