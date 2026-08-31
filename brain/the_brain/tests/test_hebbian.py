# tests/test_hebbian.py
"""Tests for Hebbian live plasticity."""
import pytest
import torch


class TestHebbianAttentionUpdate:

    def test_correlated_activations_strengthen(self):
        """Neurons that fire together -> bias increases."""
        from core.hebbian_plasticity import HebbianAttentionUpdate
        from core.radial_attention import RingLayer
        ring = RingLayer(in_dim=64, out_dim=64, num_heads=4)
        hebb = HebbianAttentionUpdate(learning_rate=0.01, decay=0.0)
        initial_bias = ring.attention_bias.clone()

        # Correlated activations
        pre = torch.ones(1, 64) * 0.5
        post = torch.ones(1, 64) * 0.5
        hebb.update(ring, pre, post)

        delta = (ring.attention_bias - initial_bias).abs().sum().item()
        assert delta > 0, "Correlated activations should change bias"

    def test_decay_weakens_connections(self):
        """Inactive connections decay over time."""
        from core.hebbian_plasticity import HebbianAttentionUpdate
        from core.radial_attention import RingLayer
        ring = RingLayer(in_dim=64, out_dim=64, num_heads=4)
        hebb = HebbianAttentionUpdate(learning_rate=0.0, decay=0.1)

        # Set some non-zero bias
        ring.attention_bias.fill_(1.0)
        hebb.update(ring, torch.zeros(1, 64), torch.zeros(1, 64))

        assert ring.attention_bias.abs().max().item() < 1.0

    def test_clamp_prevents_explosion(self):
        """Bias stays within [-2, 2] bounds."""
        from core.hebbian_plasticity import HebbianAttentionUpdate
        from core.radial_attention import RingLayer
        ring = RingLayer(in_dim=64, out_dim=64, num_heads=4)
        hebb = HebbianAttentionUpdate(learning_rate=1.0, decay=0.0)

        # Strong correlated activations many times
        for _ in range(100):
            pre = torch.ones(1, 64)
            post = torch.ones(1, 64)
            hebb.update(ring, pre, post)

        assert ring.attention_bias.max().item() <= 2.0
        assert ring.attention_bias.min().item() >= -2.0

    def test_get_stats_returns_correct_info(self):
        """get_stats should track update count and parameters."""
        from core.hebbian_plasticity import HebbianAttentionUpdate
        from core.radial_attention import RingLayer
        ring = RingLayer(in_dim=64, out_dim=64, num_heads=4)
        hebb = HebbianAttentionUpdate(learning_rate=0.005, decay=0.001)

        assert hebb.get_stats()['total_updates'] == 0

        pre = torch.randn(2, 64)
        post = torch.randn(2, 64)
        hebb.update(ring, pre, post)
        hebb.update(ring, pre, post)

        stats = hebb.get_stats()
        assert stats['total_updates'] == 2
        assert stats['learning_rate'] == 0.005
        assert stats['decay'] == 0.001

    def test_no_grad_context(self):
        """Hebbian updates must not produce gradients."""
        from core.hebbian_plasticity import HebbianAttentionUpdate
        from core.radial_attention import RingLayer
        ring = RingLayer(in_dim=64, out_dim=64, num_heads=4)
        hebb = HebbianAttentionUpdate(learning_rate=0.01, decay=0.0)

        pre = torch.randn(1, 64, requires_grad=True)
        post = torch.randn(1, 64, requires_grad=True)
        hebb.update(ring, pre, post)

        # attention_bias is a buffer, not a parameter -- should have no grad_fn
        assert ring.attention_bias.grad_fn is None

    def test_batch_mean_aggregation(self):
        """With batched input, pre/post are averaged over batch dimension."""
        from core.hebbian_plasticity import HebbianAttentionUpdate
        from core.radial_attention import RingLayer
        ring = RingLayer(in_dim=64, out_dim=64, num_heads=4)
        hebb = HebbianAttentionUpdate(learning_rate=0.01, decay=0.0)

        # Batch of 4 samples
        pre = torch.randn(4, 64)
        post = torch.randn(4, 64)
        initial_bias = ring.attention_bias.clone()
        hebb.update(ring, pre, post)

        delta = (ring.attention_bias - initial_bias).abs().sum().item()
        assert delta > 0, "Batched correlated activations should change bias"

    def test_zero_activations_only_decay(self):
        """Zero pre/post with decay should only shrink bias."""
        from core.hebbian_plasticity import HebbianAttentionUpdate
        from core.radial_attention import RingLayer
        ring = RingLayer(in_dim=64, out_dim=64, num_heads=4)
        hebb = HebbianAttentionUpdate(learning_rate=0.01, decay=0.05)

        ring.attention_bias.fill_(0.5)
        pre = torch.zeros(1, 64)
        post = torch.zeros(1, 64)
        hebb.update(ring, pre, post)

        # Zero activations contribute 0 Hebbian term, only decay remains
        expected = 0.5 * (1.0 - 0.05)
        assert abs(ring.attention_bias[0, 0].item() - expected) < 1e-5
