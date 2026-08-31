# core/thought_radial_bridge.py
"""
ThoughtRadialBridge — wires ContinuousThinkingEngine <-> RadialAttentionNetwork.

On each CTE tick:
  1. Thought content -> embed via AgentLoop.radial_tick()
  2. Ring activations -> extract RingSignature
  3. RingSignature modulates thought activation + routing
  4. Reward feedback -> queued for next Hebbian update
"""
from __future__ import annotations

import logging
import threading
from collections import deque
from typing import Any, Dict, List, Optional

import torch

from core.ring_signature import RingSignature, extract_ring_signature

logger = logging.getLogger('brain.thought_radial_bridge')


class ThoughtRadialBridge:
    """Bridge between thought stream and radial attention network."""

    def __init__(self, reward_queue_size: int = 50):
        self._agent_loop = None
        self._previous_sensory: Optional[torch.Tensor] = None
        self._reward_queue: deque = deque(maxlen=reward_queue_size)
        self._lock = threading.Lock()

        # Stats
        self._total_processed = 0
        self._total_rewards = 0
        self._total_actions_triggered = 0

    def set_agent_loop(self, agent_loop) -> None:
        """Attach the AgentLoop that owns the RadialNetwork."""
        self._agent_loop = agent_loop
        logger.info("ThoughtRadialBridge connected to AgentLoop")

    def process(self, thought) -> Optional[RingSignature]:
        """Push a thought through the radial network and extract its signature.

        Args:
            thought: ContinuousThought with .content string

        Returns:
            RingSignature or None if radial network unavailable.
        """
        if self._agent_loop is None:
            return None

        content = getattr(thought, 'content', '')
        if not content:
            return None

        # TriBE neural-signature modulation (Phase 2). Reuse the thought's
        # pre-computed bridge profile if present, else compute it here — but only
        # when modulation is enabled, to avoid paying TriBE latency for nothing.
        metadata = None
        try:
            from core.modulation_context import (
                TRIBE_MODULATION_ENABLED as _TM_ON,
            )
            if _TM_ON:
                bl = getattr(thought, 'bridge_levels', None)
                if not bl:
                    from core.tribe_encoder import bridge_levels_for_text
                    bl = bridge_levels_for_text(content[:400])
                if bl:
                    metadata = {'tribe_bridges': bl}
                    pb = getattr(self, '_personal_bias', None)
                    if pb:
                        metadata['tribe_personal_bias'] = pb
        except Exception:
            metadata = None

        # Run the radial forward pass via existing AgentLoop.radial_tick()
        result = self._agent_loop.radial_tick(content[:200], metadata=metadata)
        if result is None:
            return None

        ring_activations = result.get('ring_activations', [])
        prediction_errors = result.get('prediction_errors', [])

        if not ring_activations:
            return None

        # Extract interpretable signals
        sig = extract_ring_signature(
            ring_activations,
            prediction_errors,
            previous_sensory=self._previous_sensory,
        )

        # Track sensory activation for next novelty comparison
        if ring_activations:
            self._previous_sensory = ring_activations[0].detach().clone()

        self._total_processed += 1

        if sig.should_act():
            self._total_actions_triggered += 1

        return sig

    def record_reward(self, thought_id: str, reward: float,
                      outcome: str = "unknown") -> None:
        """Queue a reward signal for Hebbian feedback."""
        with self._lock:
            self._reward_queue.append({
                'thought_id': thought_id,
                'reward': reward,
                'outcome': outcome,
            })
            self._total_rewards += 1

    def drain_rewards(self) -> List[Dict[str, Any]]:
        """Pop all pending rewards for Hebbian update."""
        with self._lock:
            rewards = list(self._reward_queue)
            self._reward_queue.clear()
        return rewards

    def get_stats(self) -> Dict[str, Any]:
        return {
            'total_processed': self._total_processed,
            'total_rewards': self._total_rewards,
            'total_actions_triggered': self._total_actions_triggered,
            'pending_rewards': len(self._reward_queue),
        }
