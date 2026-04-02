# tests/test_ring_signature.py
"""Tests for RingSignature — the per-thought radial fingerprint."""
import pytest
import torch
from core.ring_signature import RingSignature, extract_ring_signature


class TestRingSignature:
    def test_from_activations_shape(self):
        """5 ring activations -> 5 scalar signals."""
        activations = [
            torch.randn(1, 64),
            torch.randn(1, 128),
            torch.randn(1, 256),
            torch.randn(1, 256),
            torch.randn(1, 128),
        ]
        sig = extract_ring_signature(activations, prediction_errors=[0.1, 0.2, 0.3, 0.4])
        assert isinstance(sig, RingSignature)
        assert 0.0 <= sig.novelty <= 1.0
        assert 0.0 <= sig.pattern_match <= 1.0
        assert 0.0 <= sig.semantic_richness <= 1.0
        assert 0.0 <= sig.goal_alignment <= 1.0
        assert 0.0 <= sig.action_readiness <= 1.0

    def test_activation_boost(self):
        """activation_boost is a weighted combination of all signals."""
        sig = RingSignature(
            novelty=0.8, pattern_match=0.6,
            semantic_richness=0.7, goal_alignment=0.9, action_readiness=0.5,
        )
        boost = sig.activation_boost
        assert 0.0 <= boost <= 1.0

    def test_should_act(self):
        """action_readiness above threshold -> should_act True."""
        sig_high = RingSignature(action_readiness=0.8)
        sig_low = RingSignature(action_readiness=0.2)
        assert sig_high.should_act(threshold=0.6) is True
        assert sig_low.should_act(threshold=0.6) is False

    def test_zero_activations_safe(self):
        """Zero-valued activations don't crash."""
        activations = [torch.zeros(1, d) for d in [64, 128, 256, 256, 128]]
        sig = extract_ring_signature(activations, prediction_errors=[0, 0, 0, 0])
        assert sig.novelty == 0.0

    def test_to_dict(self):
        """Serializes to dict for dashboard/SSE."""
        sig = RingSignature(novelty=0.5, pattern_match=0.3)
        d = sig.to_dict()
        assert d['novelty'] == 0.5
        assert 'activation_boost' in d

    def test_previous_sensory_increases_novelty(self):
        """Different previous sensory -> higher novelty."""
        activations = [torch.randn(1, 64)] + [torch.randn(1, d) for d in [128, 256, 256, 128]]
        prev = torch.randn(1, 64) * 10  # very different
        sig = extract_ring_signature(activations, prediction_errors=[0.0, 0.0, 0.0, 0.0], previous_sensory=prev)
        assert sig.novelty > 0.0
