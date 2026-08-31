# tests/test_thought_radial_bridge.py
"""Tests for ThoughtRadialBridge — CTE <-> RadialNetwork integration."""
import pytest
import time
from unittest.mock import MagicMock
from core.thought_radial_bridge import ThoughtRadialBridge


def _make_thought(content="test thought", category="reflect"):
    """Helper: create a ContinuousThought-like object."""
    from core.brain_chat import ContinuousThought
    return ContinuousThought(
        timestamp=time.time(),
        content=content,
        category=category,
        topic="test",
        relevance=0.5,
    )


class TestThoughtRadialBridge:
    def test_process_thought_returns_signature(self):
        """Processing a thought returns a RingSignature."""
        bridge = ThoughtRadialBridge()
        import torch
        mock_result = {
            'ring_activations': [torch.randn(1, d) for d in [64, 128, 256, 256, 128]],
            'prediction_errors': [0.1, 0.2, 0.15, 0.3],
            'meta_output': torch.randn(1, 128),
            'thalamic_seed': torch.randn(1, 128),
            'neuromod_state': None,
            'cortex_state': None,
            'limbic_state': None,
            'modulation_context': None,
            'consciousness_state': None,
        }
        mock_loop = MagicMock()
        mock_loop.radial_tick.return_value = mock_result
        bridge.set_agent_loop(mock_loop)

        thought = _make_thought("a novel idea about neural plasticity")
        sig = bridge.process(thought)

        assert sig is not None
        assert 0.0 <= sig.novelty <= 1.0
        assert 0.0 <= sig.activation_boost <= 1.0

    def test_process_without_agent_loop_returns_none(self):
        """No agent loop -> returns None (graceful degradation)."""
        bridge = ThoughtRadialBridge()
        thought = _make_thought()
        assert bridge.process(thought) is None

    def test_previous_sensory_tracked(self):
        """Bridge remembers last sensory activation for novelty comparison."""
        bridge = ThoughtRadialBridge()
        import torch
        mock_result = {
            'ring_activations': [torch.randn(1, d) for d in [64, 128, 256, 256, 128]],
            'prediction_errors': [0.1, 0.2, 0.15, 0.3],
            'meta_output': torch.randn(1, 128),
            'thalamic_seed': torch.randn(1, 128),
            'neuromod_state': None,
            'cortex_state': None,
            'limbic_state': None,
            'modulation_context': None,
            'consciousness_state': None,
        }
        mock_loop = MagicMock()
        mock_loop.radial_tick.return_value = mock_result
        bridge.set_agent_loop(mock_loop)

        bridge.process(_make_thought("first thought"))
        assert bridge._previous_sensory is not None

        bridge.process(_make_thought("second thought"))
        assert bridge._previous_sensory is not None

    def test_reward_feedback_stored(self):
        """Reward signals are queued for next Hebbian update."""
        bridge = ThoughtRadialBridge()
        bridge.record_reward(thought_id="abc", reward=0.8, outcome="user_confirmed")
        assert len(bridge._reward_queue) == 1
        assert bridge._reward_queue[0]['reward'] == 0.8

    def test_drain_rewards(self):
        """drain_rewards returns and clears the queue."""
        bridge = ThoughtRadialBridge()
        bridge.record_reward("a", 0.5)
        bridge.record_reward("b", 0.8)
        rewards = bridge.drain_rewards()
        assert len(rewards) == 2
        assert len(bridge._reward_queue) == 0

    def test_stats(self):
        """Stats reflect processing history."""
        bridge = ThoughtRadialBridge()
        stats = bridge.get_stats()
        assert stats['total_processed'] == 0
        assert stats['total_rewards'] == 0
