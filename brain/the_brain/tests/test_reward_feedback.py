# tests/test_reward_feedback.py
"""Tests for reward-weighted Hebbian plasticity."""
import pytest
import torch
from core.hebbian_plasticity import HebbianAttentionUpdate
from core.radial_attention import RingLayer


class TestRewardWeightedHebbian:
    def test_reward_modulates_learning_rate(self):
        """Positive reward -> larger bias change than neutral."""
        ring = RingLayer(in_dim=64, out_dim=64, num_heads=4)
        hebbian = HebbianAttentionUpdate(learning_rate=0.01)

        pre = torch.randn(1, 64)
        post = torch.randn(1, 64)

        # Neutral update
        bias_before = ring.attention_bias.clone()
        hebbian.update(ring, pre, post)
        neutral_delta = (ring.attention_bias - bias_before).abs().sum().item()

        # Reset
        ring.attention_bias.zero_()

        # Reward-weighted update
        hebbian.update_with_reward(ring, pre, post, reward=0.9)
        reward_delta = (ring.attention_bias).abs().sum().item()

        # Rewarded update should be larger
        assert reward_delta > neutral_delta * 1.3

    def test_negative_reward_reverses(self):
        """Negative reward -> bias changes in opposite direction (LTD)."""
        ring = RingLayer(in_dim=64, out_dim=64, num_heads=4)
        hebbian = HebbianAttentionUpdate(learning_rate=0.01)

        pre = torch.randn(1, 64)
        post = torch.randn(1, 64)

        # Positive reward
        ring.attention_bias.zero_()
        hebbian.update_with_reward(ring, pre, post, reward=0.8)
        positive_bias = ring.attention_bias.clone()

        # Negative reward (reward < -1.0 flips sign of effective_lr)
        ring.attention_bias.zero_()
        hebbian.update_with_reward(ring, pre, post, reward=-1.5)
        negative_bias = ring.attention_bias.clone()

        # Signs should differ (at least partially) since effective_lr flipped
        sign_diff = (positive_bias.sign() != negative_bias.sign()).float().mean().item()
        assert sign_diff > 0.3

    def test_zero_reward_still_updates(self):
        """Zero reward -> small baseline update (not zero)."""
        ring = RingLayer(in_dim=64, out_dim=64, num_heads=4)
        hebbian = HebbianAttentionUpdate(learning_rate=0.01)

        pre = torch.randn(1, 64)
        post = torch.randn(1, 64)

        hebbian.update_with_reward(ring, pre, post, reward=0.0)
        delta = ring.attention_bias.abs().sum().item()
        assert delta > 0
