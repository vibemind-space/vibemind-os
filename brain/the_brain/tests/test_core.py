"""
Unit tests for ATM-R core functionality.

Test coverage:
- Instantiation
- Gate normalization
- Determinism
- Stability
- Context switching
- Safety override
- Adaptive learning
"""

import pytest
import numpy as np
import sys
import os

# Add parent directory to path for module access
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, parent_dir)

# Import from core module
from core.thalamo_pc_live import ThalamoPC6
from core.thalamo_pc_adaptive import ThalamoPC6Adaptive
from core.config_loader import load_config, create_model_from_config


class TestThalamoPC6:
    """Test suite for ThalamoPC6."""

    def test_instantiation(self):
        """Test basic instantiation."""
        model = ThalamoPC6()
        assert model.M == 6
        assert len(model.modalities) == 6
        assert 'vision' in model.modalities
        assert 'threat' in model.modalities

    def test_gate_normalization(self):
        """Gates should sum to 1.0."""
        model = ThalamoPC6(seed=42)
        x_t = {m: np.random.randn(model.d[m]) for m in model.modalities}

        out = model.step(x_t)
        g = out['g']

        assert np.isclose(np.sum(g), 1.0), f"Gates sum to {np.sum(g)}, expected 1.0"
        assert np.all(g >= 0), "All gates should be non-negative"
        assert np.all(g <= 1), "All gates should be <= 1.0"

    def test_determinism(self):
        """Same seed should produce identical results."""
        model1 = ThalamoPC6(seed=42)
        model2 = ThalamoPC6(seed=42)

        np.random.seed(123)
        x_t = {m: np.random.randn(model1.d[m]) for m in model1.modalities}

        out1 = model1.step(x_t)
        out2 = model2.step(x_t)

        assert np.allclose(out1['g'], out2['g']), "Gates should be identical for same seed"

    def test_stability_zero_input(self):
        """Model should be stable with zero input."""
        model = ThalamoPC6(seed=42)
        x_t = {m: np.zeros(model.d[m]) for m in model.modalities}

        # Run 10 steps
        gates_history = []
        for _ in range(10):
            out = model.step(x_t)
            gates_history.append(out['g'])

        # Gates should not explode
        for g in gates_history:
            assert np.all(np.isfinite(g)), "Gates should remain finite"
            assert np.sum(g) <= 1.01, "Gates should not explode"

    def test_single_modality_dominance(self):
        """When only one modality is active, its gate should dominate."""
        model = ThalamoPC6(seed=42)

        # Only vision active
        x_t = {m: np.zeros(model.d[m]) for m in model.modalities}
        x_t['vision'] = np.ones(model.d['vision'])

        # Run for 50 steps to converge
        for _ in range(50):
            out = model.step(x_t)

        vision_idx = model.modalities.index('vision')
        assert out['g'][vision_idx] > 0.5, f"Vision gate = {out['g'][vision_idx]}, expected > 0.5"

    def test_context_switching(self):
        """Context should influence gate allocation."""
        model = ThalamoPC6(seed=42)

        # Both vision and audio active
        x_t = {m: np.zeros(model.d[m]) for m in model.modalities}
        x_t['vision'] = np.ones(model.d['vision'])
        x_t['audio'] = np.ones(model.d['audio'])

        # Context favors vision
        ctx_vision = np.zeros(model.M)
        ctx_vision[model.modalities.index('vision')] = 1.0

        # Warmup
        for _ in range(20):
            model.step(x_t, ctx=ctx_vision)

        out_vision = model.step(x_t, ctx=ctx_vision)

        # Context favors audio
        ctx_audio = np.zeros(model.M)
        ctx_audio[model.modalities.index('audio')] = 1.0

        for _ in range(20):
            model.step(x_t, ctx=ctx_audio)

        out_audio = model.step(x_t, ctx=ctx_audio)

        vision_idx = model.modalities.index('vision')
        audio_idx = model.modalities.index('audio')

        # Vision gate should be higher when context favors vision
        assert out_vision['g'][vision_idx] > out_audio['g'][vision_idx], \
            "Vision gate should be higher with vision context"

    def test_runtime_controls(self):
        """Runtime control methods should work."""
        model = ThalamoPC6(seed=42)

        # Set priority
        original_prior = model.priors['threat']
        model.set_priority('threat', 0.5)
        assert model.priors['threat'] == 0.5

        # Set tau
        original_tau = model.tau['vision']
        model.set_tau('vision', 100.0)
        assert model.tau['vision'] == 100.0

        # Set gating temp
        model.set_gating_temp(1.0)
        assert model.gate_temp == 1.0

        # Reset state
        model.reset_state()
        for m in model.modalities:
            assert np.all(model.v[m] == 0), "State should be reset to zero"


class TestThalamoPC6Adaptive:
    """Test suite for ThalamoPC6Adaptive."""

    def test_adaptive_instantiation(self):
        """Test adaptive model instantiation."""
        model = ThalamoPC6Adaptive()
        assert hasattr(model, 'G'), "Should have generative models"
        assert hasattr(model, 'lr_input'), "Should have learning rates"

    def test_adaptation_runs(self):
        """Test that adaptation runs without errors."""
        model = ThalamoPC6Adaptive(seed=42)
        x_t = {m: np.random.randn(model.d[m]) for m in model.modalities}

        out = model.step(x_t, adapt=True)

        assert 'adapted_params' in out, "Should return adapted parameters"
        assert np.sum(out['g']) <= 1.01, "Gates should remain normalized"

    def test_hazard_increases_prior(self):
        """Hazard signal should increase prior."""
        model = ThalamoPC6Adaptive(seed=42)
        x_t = {m: np.zeros(model.d[m]) for m in model.modalities}

        initial_prior = model.priors['threat']

        # Send hazard signal
        hazard = {'threat': 1.0}
        for _ in range(10):
            model.step(x_t, hazard=hazard, adapt=True)

        final_prior = model.priors['threat']
        assert final_prior > initial_prior, f"Prior should increase: {initial_prior} → {final_prior}"

    def test_parameter_bounds(self):
        """Adaptive parameters should stay within bounds."""
        model = ThalamoPC6Adaptive(seed=42)
        x_t = {m: np.random.randn(model.d[m]) for m in model.modalities}

        # Run many steps with extreme signals
        hazard = {m: 1.0 for m in model.modalities}
        for _ in range(100):
            model.step(x_t, hazard=hazard, adapt=True)

        # Check bounds
        for m in model.modalities:
            assert model.priors[m] >= model.prior_min, f"Prior {m} below min"
            assert model.priors[m] <= model.prior_max, f"Prior {m} above max"
            assert model.tau[m] >= model.tau_min, f"Tau {m} below min"
            assert model.tau[m] <= model.tau_max, f"Tau {m} above max"

        assert model.gate_temp >= model.gate_temp_min, "Gate temp below min"
        assert model.gate_temp <= model.gate_temp_max, "Gate temp above max"


class TestConfigLoader:
    """Test configuration loading."""

    def test_load_default_config(self):
        """Test loading default config."""
        config_path = os.path.join(os.path.dirname(__file__), '..', 'configs', 'default.yaml')
        config = load_config(config_path)

        assert 'modalities' in config
        assert 'dimensions' in config
        assert len(config['modalities']) == 6

    def test_create_model_from_config(self):
        """Test creating model from config."""
        config_path = os.path.join(os.path.dirname(__file__), '..', 'configs', 'default.yaml')

        # Non-adaptive
        model = create_model_from_config(config_path, adaptive=False)
        assert isinstance(model, ThalamoPC6)
        assert model.M == 6

        # Adaptive
        model_adaptive = create_model_from_config(config_path, adaptive=True)
        assert isinstance(model_adaptive, ThalamoPC6Adaptive)
        assert hasattr(model_adaptive, 'G')


class TestMetrics:
    """Test metrics computation."""

    def test_routing_purity(self):
        """Test routing purity metric."""
        from monitoring.logger_viz import ATMRMetrics

        # Sharp distribution
        g_sharp = np.array([0.9, 0.05, 0.03, 0.01, 0.005, 0.005])
        purity_sharp = ATMRMetrics.routing_purity(g_sharp)
        assert purity_sharp == 0.9

        # Uniform distribution
        g_uniform = np.ones(6) / 6
        purity_uniform = ATMRMetrics.routing_purity(g_uniform)
        assert purity_uniform < 0.2

    def test_gate_entropy(self):
        """Test gate entropy metric."""
        from monitoring.logger_viz import ATMRMetrics

        # Deterministic (zero entropy)
        g_det = np.array([1.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        entropy_det = ATMRMetrics.gate_entropy(g_det)
        assert entropy_det < 0.01, f"Deterministic entropy = {entropy_det}, expected ~0"

        # Uniform (max entropy)
        g_uniform = np.ones(6) / 6
        entropy_uniform = ATMRMetrics.gate_entropy(g_uniform)
        expected_max = np.log2(6)
        assert entropy_uniform > expected_max * 0.99, \
            f"Uniform entropy = {entropy_uniform}, expected ~{expected_max}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
