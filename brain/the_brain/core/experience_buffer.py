"""
Experience replay buffer for Radial Attention Network.

Collects (input, ring_activations, ctm_trajectory, reward, outcome)
during waking. Sampled during sleep for Backprop training.
"""
import logging
import random
from collections import deque
from typing import Any, Dict, List, Optional

import torch

logger = logging.getLogger(__name__)


class ExperienceBuffer:
    """FIFO buffer for radial attention experiences."""

    def __init__(self, max_size: int = 5000):
        self._buffer: deque = deque(maxlen=max_size)
        self._total_added: int = 0

    def add(self, input_embedding: torch.Tensor,
            ring_activations: List[torch.Tensor],
            ctm_trajectory: List[float],
            kuro_reward: float,
            outcome: str) -> None:
        """Record one experience."""
        self._buffer.append({
            'input_embedding': input_embedding.detach().cpu(),
            'ring_activations': [a.detach().cpu() if isinstance(a, torch.Tensor)
                                 else a for a in ring_activations],
            'ctm_trajectory': list(ctm_trajectory),
            'kuro_reward': float(kuro_reward),
            'outcome': str(outcome),
        })
        self._total_added += 1

    def sample(self, batch_size: int) -> List[Dict[str, Any]]:
        """Random sample from buffer."""
        n = min(batch_size, len(self._buffer))
        return random.sample(list(self._buffer), n)

    def __len__(self) -> int:
        return len(self._buffer)

    def get_stats(self) -> dict:
        return {
            'buffer_size': len(self._buffer),
            'total_added': self._total_added,
            'max_size': self._buffer.maxlen,
        }
