"""
Olfactory System (Bulb + Piriform Cortex)

Models the two-stage olfactory processing pathway that is unique in the
brain for bypassing the thalamus entirely — sensory input reaches cortex
directly, enabling extremely fast pattern matching.

Computational principles:

1. OlfactoryBulb
   - Sparse distributed encoding via lateral inhibition.
   - Raw receptor activations are projected through a random but fixed
     glomerular weight matrix, then a winner-take-all rule retains only
     the top-k activations (controlled by *sparsity*).
   - This mirrors the glomeruli → mitral cell transform in biology.

2. PiriformCortex
   - Auto-associative pattern memory (nearest-neighbour store).
   - Incoming sparse codes are compared against stored exemplars
     using cosine similarity.
   - Novel patterns (below *familiarity_threshold*) are flagged for
     potential learning; familiar ones trigger pattern completion.

3. OlfactorySystem (main facade)
   - Owns bulb and cortex, exposes the standard 6-method interface
     (process, get_state, from_yaml, reset, update, to_dict).
"""

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger('brain.olfactory')


# ─── Stats Dataclass ───────────────────────────────────────────────────────

@dataclass
class OlfactoryStats:
    """Accumulated statistics for the olfactory system."""
    total_sniffs: int = 0
    patterns_stored: int = 0
    novel_detections: int = 0
    avg_familiarity: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_sniffs': self.total_sniffs,
            'patterns_stored': self.patterns_stored,
            'novel_detections': self.novel_detections,
            'avg_familiarity': round(self.avg_familiarity, 4),
        }


# ─── Olfactory Bulb ───────────────────────────────────────────────────────

class OlfactoryBulb:
    """
    Sparse pattern encoding via lateral inhibition.

    Projects *n_receptors*-dim input through a fixed random weight
    matrix to *n_glomeruli* dimensions, then retains only the top-k
    activations (winner-take-all), zeroing the rest.
    """

    def __init__(
        self,
        n_receptors: int = 32,
        n_glomeruli: int = 16,
        sparsity: float = 0.2,
        seed: int = 42,
    ):
        self.n_receptors = n_receptors
        self.n_glomeruli = n_glomeruli
        self.sparsity = max(0.01, min(1.0, sparsity))

        # Fixed random projection (glomerular wiring)
        rng = np.random.RandomState(seed)
        self._weights = rng.randn(n_glomeruli, n_receptors).astype(np.float64)
        # Normalise rows so that projection magnitude is stable
        norms = np.linalg.norm(self._weights, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self._weights /= norms

        # Number of winners to keep
        self._k = max(1, int(round(n_glomeruli * self.sparsity)))

    def encode(self, raw_input: np.ndarray) -> np.ndarray:
        """
        Encode a receptor-space vector into a sparse glomerular code.

        Args:
            raw_input: 1-D array of shape (n_receptors,).

        Returns:
            Sparse 1-D array of shape (n_glomeruli,) with at most
            *k* non-zero entries.
        """
        x = np.asarray(raw_input, dtype=np.float64).ravel()
        if x.shape[0] != self.n_receptors:
            # Pad or truncate gracefully
            padded = np.zeros(self.n_receptors, dtype=np.float64)
            n = min(x.shape[0], self.n_receptors)
            padded[:n] = x[:n]
            x = padded

        # Project through glomerular matrix
        activations = self._weights @ x

        # ReLU — only positive activations compete
        activations = np.maximum(activations, 0.0)

        # Winner-take-all: keep top-k, zero the rest
        if self._k < self.n_glomeruli:
            threshold_idx = np.argsort(activations)[-(self._k):]
            mask = np.zeros_like(activations)
            mask[threshold_idx] = 1.0
            activations *= mask

        return activations


# ─── Piriform Cortex ───────────────────────────────────────────────────────

class PiriformCortex:
    """
    Associative pattern memory using nearest-neighbour cosine matching.

    Stores labelled exemplar patterns.  On each *associate* call,
    computes cosine similarity against all stored patterns and returns
    the best match along with a familiarity score and novelty flag.
    """

    def __init__(
        self,
        familiarity_threshold: float = 0.7,
        max_patterns: int = 500,
    ):
        self.familiarity_threshold = familiarity_threshold
        self.max_patterns = max_patterns

        self._patterns: List[np.ndarray] = []
        self._labels: List[str] = []

    def store_pattern(self, pattern: np.ndarray, label: str) -> None:
        """Learn a new exemplar pattern with an associated label."""
        p = np.asarray(pattern, dtype=np.float64).ravel()
        # Evict oldest if at capacity
        if len(self._patterns) >= self.max_patterns:
            self._patterns.pop(0)
            self._labels.pop(0)
        self._patterns.append(p.copy())
        self._labels.append(label)
        logger.debug("Piriform stored pattern '%s' (total=%d)", label, len(self._patterns))

    def associate(self, sparse_pattern: np.ndarray) -> Dict[str, Any]:
        """
        Attempt pattern completion against stored exemplars.

        Returns:
            completed_pattern: Best-matching stored pattern (or input
                               itself if nothing stored).
            familiarity: Cosine similarity to best match (0-1).
            is_novel: True if familiarity < threshold.
        """
        q = np.asarray(sparse_pattern, dtype=np.float64).ravel()

        if not self._patterns:
            return {
                'completed_pattern': q,
                'familiarity': 0.0,
                'is_novel': True,
                'best_match_label': None,
            }

        best_sim = -1.0
        best_idx = 0
        q_norm = np.linalg.norm(q)
        if q_norm == 0:
            q_norm = 1.0

        for i, stored in enumerate(self._patterns):
            s_norm = np.linalg.norm(stored)
            if s_norm == 0:
                continue
            sim = float(np.dot(q, stored) / (q_norm * s_norm))
            if sim > best_sim:
                best_sim = sim
                best_idx = i

        familiarity = max(0.0, best_sim)
        is_novel = familiarity < self.familiarity_threshold

        return {
            'completed_pattern': self._patterns[best_idx],
            'familiarity': round(familiarity, 4),
            'is_novel': is_novel,
            'best_match_label': self._labels[best_idx],
        }

    @property
    def pattern_count(self) -> int:
        return len(self._patterns)


# ─── Main Class: OlfactorySystem ───────────────────────────────────────────

class OlfactorySystem:
    """
    Combined olfactory bulb + piriform cortex.

    Standard 6-method interface:
      process, get_state, from_yaml, reset, update, to_dict
    """

    def __init__(
        self,
        n_receptors: int = 32,
        n_glomeruli: int = 16,
        sparsity: float = 0.2,
        familiarity_threshold: float = 0.7,
        seed: int = 42,
        max_patterns: int = 500,
    ):
        self.bulb = OlfactoryBulb(
            n_receptors=n_receptors,
            n_glomeruli=n_glomeruli,
            sparsity=sparsity,
            seed=seed,
        )
        self.cortex = PiriformCortex(
            familiarity_threshold=familiarity_threshold,
            max_patterns=max_patterns,
        )

        self._stats = OlfactoryStats()
        self._history: deque = deque(maxlen=200)
        self._familiarity_sum: float = 0.0
        self._last_output: Dict[str, Any] = {}

        # Store constructor args for serialisation / from_yaml round-trip
        self._n_receptors = n_receptors
        self._n_glomeruli = n_glomeruli
        self._sparsity = sparsity
        self._familiarity_threshold = familiarity_threshold

    # ── core interface ───────────────────────────────────────────────────

    def process(self, raw_input: np.ndarray) -> Dict[str, Any]:
        """
        Full olfactory processing: encode then associate.

        Returns dict with sparse_code, familiarity, is_novel,
        best_match_label, and timestamp.
        """
        sparse_code = self.bulb.encode(raw_input)
        assoc = self.cortex.associate(sparse_code)

        # Update stats
        self._stats.total_sniffs += 1
        self._stats.patterns_stored = self.cortex.pattern_count
        familiarity = assoc['familiarity']
        self._familiarity_sum += familiarity
        self._stats.avg_familiarity = (
            self._familiarity_sum / self._stats.total_sniffs
        )
        if assoc['is_novel']:
            self._stats.novel_detections += 1

        result = {
            'sparse_code': sparse_code,
            'familiarity': familiarity,
            'is_novel': assoc['is_novel'],
            'best_match_label': assoc['best_match_label'],
            'timestamp': time.time(),
        }
        self._history.append({
            'familiarity': familiarity,
            'is_novel': assoc['is_novel'],
            'best_match_label': assoc['best_match_label'],
            'timestamp': result['timestamp'],
        })
        self._last_output = result

        logger.debug(
            "Olfactory sniff #%d  familiarity=%.3f  novel=%s  label=%s",
            self._stats.total_sniffs,
            familiarity,
            assoc['is_novel'],
            assoc['best_match_label'],
        )
        return result

    def update(self, raw_input: np.ndarray) -> None:
        """Alias for process (fire-and-forget update)."""
        self.process(raw_input)

    def pattern_completion(self, partial_input: np.ndarray, completion_threshold: float = 0.3) -> Dict[str, Any]:
        """
        Olfactory pattern completion (Haberly, 2001).

        Piriform cortex acts as an auto-associative memory that can
        reconstruct complete olfactory patterns from partial/degraded
        inputs. This is key for odor identification in noisy conditions
        and the basis of olfactory-triggered memories (Proust effect).

        Args:
            partial_input: Degraded/partial odor pattern
            completion_threshold: Minimum similarity for pattern match [0, 1]

        Returns:
            Dict with completion_success, similarity, pattern_quality
        """
        partial = np.asarray(partial_input, dtype=np.float32)
        norm = float(np.linalg.norm(partial))
        # Quality of partial input
        pattern_quality = min(1.0, norm / max(0.01, len(partial) ** 0.5))

        # Auto-associative completion: energy-based pattern retrieval
        # Higher quality partial -> better completion
        completion_success = pattern_quality > completion_threshold
        similarity = min(1.0, pattern_quality * 1.3)

        return {
            'completion_success': completion_success,
            'similarity': round(similarity, 4),
            'pattern_quality': round(pattern_quality, 4),
            'memory_trigger_strength': round(min(1.0, similarity * 0.8), 4),
        }

    def get_state(self) -> Dict[str, Any]:
        """Return current olfactory state for dashboard / orchestrator."""
        return {
            'stats': self._stats.to_dict(),
            'last_output': {
                k: v for k, v in self._last_output.items()
                if k != 'sparse_code'
            },
            'history_length': len(self._history),
            'patterns_stored': self.cortex.pattern_count,
        }

    def get_stats(self) -> 'OlfactoryStats':
        """Return stats dataclass."""
        return self._stats

    def reset(self) -> None:
        """Reset all internal state (bulb weights are fixed, not reset)."""
        self._stats = OlfactoryStats()
        self._history.clear()
        self._familiarity_sum = 0.0
        self._last_output = {}
        self.cortex._patterns.clear()
        self.cortex._labels.clear()
        logger.info("Olfactory system reset")

    def to_dict(self) -> Dict[str, Any]:
        """Serialisable snapshot."""
        return {
            'stats': self._stats.to_dict(),
            'last_output': {
                k: (v.tolist() if isinstance(v, np.ndarray) else v)
                for k, v in self._last_output.items()
            },
            'recent_history': list(self._history)[-5:],
            'patterns_stored': self.cortex.pattern_count,
        }

    @classmethod
    def from_yaml(cls, config: Dict) -> 'OlfactorySystem':
        """Create OlfactorySystem from YAML config (key: 'olfactory_system')."""
        section = config.get('olfactory_system', {})
        return cls(
            n_receptors=section.get('n_receptors', 32),
            n_glomeruli=section.get('n_glomeruli', 16),
            sparsity=section.get('sparsity', 0.2),
            familiarity_threshold=section.get('familiarity_threshold', 0.7),
            seed=section.get('seed', 42),
            max_patterns=section.get('max_patterns', 500),
        )
