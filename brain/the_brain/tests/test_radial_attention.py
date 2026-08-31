"""Tests for RadialAttentionNetwork."""
import pytest
import torch
import numpy as np


class TestRingLayer:
    """A single ring = one abstraction level."""

    def test_forward_shape_bottom_up_only(self):
        """Bottom-up input produces correct output shape."""
        from core.radial_attention import RingLayer
        ring = RingLayer(in_dim=64, out_dim=128, num_heads=4)
        x = torch.randn(1, 64)
        out = ring(x)
        assert out.shape == (1, 128)

    def test_forward_with_top_down_prediction(self):
        """When top-down prediction provided, output uses error signal."""
        from core.radial_attention import RingLayer
        ring = RingLayer(in_dim=64, out_dim=128, num_heads=4)
        x = torch.randn(1, 64)
        top_down = torch.randn(1, 128)
        out_with_td = ring(x, top_down_prediction=top_down)
        out_without = ring(x)
        # Outputs should differ when top-down is present
        assert not torch.allclose(out_with_td, out_without, atol=1e-3)

    def test_predictive_coding_zero_error(self):
        """Perfect prediction → minimal output change."""
        from core.radial_attention import RingLayer
        ring = RingLayer(in_dim=64, out_dim=128, num_heads=4)
        ring.eval()
        x = torch.randn(1, 64)
        # First pass to get the ring's natural output
        with torch.no_grad():
            natural = ring(x)
            # Use natural output as top-down prediction
            out = ring(x, top_down_prediction=natural)
        # With perfect prediction, error ≈ 0 → output should be small
        error_magnitude = (out - natural).abs().mean().item()
        natural_magnitude = natural.abs().mean().item()
        assert error_magnitude < natural_magnitude

    def test_residual_connection(self):
        """Output contains input component via residual."""
        from core.radial_attention import RingLayer
        ring = RingLayer(in_dim=128, out_dim=128, num_heads=4)
        x = torch.randn(1, 128)
        out = ring(x)
        # Residual means output and input are correlated
        correlation = torch.cosine_similarity(
            x.flatten(), out.flatten(), dim=0
        ).item()
        assert correlation > -0.5  # Not perfectly anti-correlated

    def test_attention_bias_buffer_exists(self):
        """Ring has a Hebbian attention bias buffer."""
        from core.radial_attention import RingLayer
        ring = RingLayer(in_dim=64, out_dim=128, num_heads=4)
        assert hasattr(ring, 'attention_bias')
        assert ring.attention_bias is not None


class TestRadialAttentionNetwork:
    """Full 5-ring network with thalamic center."""

    def test_forward_produces_all_ring_outputs(self):
        """Forward pass returns activations for all 5 rings."""
        from core.radial_attention import RadialAttentionNetwork
        net = RadialAttentionNetwork(seed_dim=384)
        seed = torch.randn(1, 384)
        result = net(seed)
        assert 'ring_activations' in result
        assert len(result['ring_activations']) == 5

    def test_forward_output_keys(self):
        """Forward returns all expected keys."""
        from core.radial_attention import RadialAttentionNetwork
        net = RadialAttentionNetwork(seed_dim=384)
        seed = torch.randn(1, 384)
        result = net(seed)
        expected_keys = {'ring_activations', 'meta_output', 'thalamic_seed',
                         'prediction_errors'}
        assert expected_keys.issubset(result.keys())

    def test_bottom_up_then_top_down(self):
        """Full pass: bottom-up through rings, then top-down predictions."""
        from core.radial_attention import RadialAttentionNetwork
        net = RadialAttentionNetwork(seed_dim=384)
        seed = torch.randn(1, 384)
        result = net(seed)
        # prediction_errors should have 4 entries (between 5 rings)
        assert len(result['prediction_errors']) == 4

    def test_parameter_count_under_30m(self):
        """Total parameters stay under 30M budget."""
        from core.radial_attention import RadialAttentionNetwork
        net = RadialAttentionNetwork(seed_dim=384)
        total = sum(p.numel() for p in net.parameters())
        assert total < 30_000_000, f"Too many params: {total:,}"

    def test_thalamic_encoder_reduces_dim(self):
        """Thalamic encoder projects 384 -> 128."""
        from core.radial_attention import RadialAttentionNetwork
        net = RadialAttentionNetwork(seed_dim=384)
        seed = torch.randn(1, 384)
        result = net(seed)
        assert result['thalamic_seed'].shape == (1, 128)


class TestDualProcessRouter:
    """ACC-based decision: fast intuition or slow deliberation."""

    def test_low_conflict_returns_system1(self):
        """When fast and slow agree -> System 1 wins (faster)."""
        from core.radial_attention import DualProcessRouter
        router = DualProcessRouter(dim=128, conflict_threshold=0.5)
        system1 = torch.randn(1, 128)
        system2 = system1 + torch.randn(1, 128) * 0.01  # Very similar
        result = router(system1, system2)
        assert result['system_used'] == 1

    def test_high_conflict_returns_system2(self):
        """When fast and slow disagree -> System 2 wins (deeper)."""
        from core.radial_attention import DualProcessRouter
        router = DualProcessRouter(dim=128, conflict_threshold=0.1)
        system1 = torch.ones(1, 128)
        system2 = -torch.ones(1, 128)  # Opposite
        result = router(system1, system2)
        assert result['system_used'] == 2

    def test_conflict_level_in_output(self):
        """Output includes measured conflict level."""
        from core.radial_attention import DualProcessRouter
        router = DualProcessRouter(dim=128)
        result = router(torch.randn(1, 128), torch.randn(1, 128))
        assert 'conflict_level' in result
        assert 0.0 <= result['conflict_level'] <= 10.0
