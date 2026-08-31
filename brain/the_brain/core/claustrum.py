"""
Claustrum — Cross-Modal Integration & Consciousness Binding

Neuroscience basis:
  The claustrum is a thin sheet of gray matter between the insular cortex
  and the putamen.  It is the most densely connected structure per unit
  volume in the mammalian brain, with reciprocal projections to nearly
  every cortical region.

  Crick & Koch (2005, Phil. Trans. R. Soc. B) proposed the claustrum as
  the "conductor of consciousness."  Smythies, Edelstein & Ramachandran
  (2012) and Koubeissi et al. (2014) reinforced its role in:

    1. Cross-modal sensory integration
    2. Consciousness gating (what reaches awareness)
    3. Salience detection
    4. Attention coordination across cortical regions

  In Tahlamus the Claustrum sits between the sensory pipeline and the
  cognitive loops, fusing multi-modal signals and deciding what crosses
  the threshold into the cognitive workspace.
"""

import time
import logging
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from collections import deque

logger = logging.getLogger('brain.claustrum')


# ─── Stats ──────────────────────────────────────────────────────────────

@dataclass
class ClaustrumStats:
    """Aggregate statistics for the Claustrum module."""
    total_integrations: int = 0
    consciousness_access_count: int = 0
    avg_binding_strength: float = 0.0
    avg_attention_allocated: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_integrations': self.total_integrations,
            'consciousness_access_count': self.consciousness_access_count,
            'avg_binding_strength': round(self.avg_binding_strength, 4),
            'avg_attention_allocated': round(self.avg_attention_allocated, 4),
        }


# ─── Cross-Modal Integrator ────────────────────────────────────────────

class CrossModalIntegrator:
    """Binds multiple modalities into a unified representation with a
    Hebbian binding-strength matrix tracking co-activation patterns."""

    def __init__(self, n_modalities: int = 6, signal_dim: int = 16,
                 learning_rate: float = 0.01):
        self.n_modalities = n_modalities
        self.signal_dim = signal_dim
        self.learning_rate = learning_rate
        self._weights = np.ones(n_modalities, dtype=np.float64) / n_modalities
        self.binding_strength = np.eye(n_modalities, dtype=np.float64) * 0.5
        self._modality_index: Dict[str, int] = {}

    def _ensure_index(self, name: str) -> int:
        """Return (or create) a stable integer index for *name*."""
        if name not in self._modality_index:
            idx = len(self._modality_index)
            if idx >= self.n_modalities:
                logger.warning("Claustrum: modality '%s' exceeds "
                               "n_modalities=%d — ignored", name,
                               self.n_modalities)
                return -1
            self._modality_index[name] = idx
        return self._modality_index[name]

    def integrate(self, modality_signals: Dict[str, np.ndarray]) -> np.ndarray:
        """Weighted combination of modality signals into one vector."""
        integrated = np.zeros(self.signal_dim, dtype=np.float64)
        active_indices: List[int] = []

        for name, signal in modality_signals.items():
            idx = self._ensure_index(name)
            if idx < 0:
                continue
            sig = np.asarray(signal, dtype=np.float64).ravel()
            if sig.shape[0] != self.signal_dim:
                sig = np.resize(sig, self.signal_dim)
            integrated += self._weights[idx] * sig
            active_indices.append(idx)

        if len(active_indices) > 1:
            self._update_binding(active_indices)
        return integrated

    def _update_binding(self, active: List[int]) -> None:
        """Hebbian: strengthen binding between co-active modality pairs."""
        for i in range(len(active)):
            for j in range(i + 1, len(active)):
                a, b = active[i], active[j]
                delta = self.learning_rate * (1.0 - self.binding_strength[a, b])
                self.binding_strength[a, b] += delta
                self.binding_strength[b, a] += delta
        np.clip(self.binding_strength, 0.0, 1.0, out=self.binding_strength)

    def get_avg_binding_strength(self) -> float:
        """Mean off-diagonal binding strength."""
        if self.n_modalities < 2:
            return 0.0
        mask = ~np.eye(self.n_modalities, dtype=bool)
        return float(np.mean(self.binding_strength[mask]))


# ─── Consciousness Gate ────────────────────────────────────────────────

class ConsciousnessGate:
    """Threshold gate: signal magnitude * salience * attention must exceed
    ``consciousness_threshold`` for a signal to reach awareness."""

    def __init__(self, consciousness_threshold: float = 0.5,
                 history_len: int = 200):
        self.threshold = consciousness_threshold
        self._history: deque = deque(maxlen=history_len)

    def gate(self, integrated_signal: np.ndarray,
             salience: float, attention: float
             ) -> Tuple[np.ndarray, bool]:
        """Return (gated_signal, reached_consciousness)."""
        magnitude = float(np.linalg.norm(integrated_signal))
        gate_score = magnitude * salience * attention
        reached = gate_score > self.threshold
        self._history.append(reached)

        if reached:
            gated = integrated_signal * (gate_score / max(magnitude, 1e-9))
        else:
            gated = np.zeros_like(integrated_signal)
        return gated, reached

    @property
    def access_ratio(self) -> float:
        """Proportion of recent signals that reached consciousness."""
        if not self._history:
            return 0.0
        return sum(self._history) / len(self._history)


# ─── Attention Coordinator ─────────────────────────────────────────────

class AttentionCoordinator:
    """Competitive softmax allocation of a finite attention budget
    across brain regions."""

    def __init__(self, attention_budget: float = 1.0,
                 temperature: float = 1.0):
        self.budget = attention_budget
        self.temperature = temperature
        self._priority_bias: Dict[str, float] = {}
        self._last_allocation: Dict[str, float] = {}

    def set_priority(self, region: str, bias: float) -> None:
        """Bias a region's attention allocation."""
        self._priority_bias[region] = float(bias)

    def coordinate(self, region_demands: Dict[str, float]
                   ) -> Dict[str, float]:
        """Softmax-normalised allocation summing to ``self.budget``."""
        if not region_demands:
            return {}
        regions = list(region_demands.keys())
        raw = np.array([region_demands[r] for r in regions], dtype=np.float64)
        for i, r in enumerate(regions):
            raw[i] += self._priority_bias.get(r, 0.0)

        shifted = raw - np.max(raw)
        exp_vals = np.exp(shifted / max(self.temperature, 1e-9))
        probs = exp_vals / np.sum(exp_vals)

        allocation = {r: float(probs[i] * self.budget)
                      for i, r in enumerate(regions)}
        self._last_allocation = allocation
        return allocation

    @property
    def last_allocation(self) -> Dict[str, float]:
        return dict(self._last_allocation)


# ─── Main Claustrum Module ─────────────────────────────────────────────

class Claustrum:
    """The Claustrum — conductor of consciousness.

    Orchestrates cross-modal integration, consciousness gating, and
    attention coordination in a single ``process()`` call."""

    def __init__(self, n_modalities: int = 6, signal_dim: int = 16,
                 consciousness_threshold: float = 0.5,
                 binding_learning_rate: float = 0.01,
                 attention_budget: float = 1.0):
        self.n_modalities = n_modalities
        self.signal_dim = signal_dim

        self._integrator = CrossModalIntegrator(
            n_modalities=n_modalities, signal_dim=signal_dim,
            learning_rate=binding_learning_rate,
        )
        self._gate = ConsciousnessGate(
            consciousness_threshold=consciousness_threshold,
        )
        self._attention = AttentionCoordinator(
            attention_budget=attention_budget,
        )
        self._stats = ClaustrumStats()
        self._binding_strength_accum = 0.0
        self._attention_accum = 0.0
        logger.info("Claustrum initialised: n_modalities=%d signal_dim=%d "
                     "threshold=%.2f lr=%.4f budget=%.1f",
                     n_modalities, signal_dim, consciousness_threshold,
                     binding_learning_rate, attention_budget)

    # ── core pipeline ──

    def process(self, modality_signals: Dict[str, np.ndarray],
                salience: float = 0.5, attention: float = 0.5,
                region_demands: Optional[Dict[str, float]] = None,
                ) -> Dict[str, Any]:
        """Run the full claustrum pipeline: integrate -> gate -> attend.

        Returns dict with keys: integrated_signal, reached_consciousness,
        binding_strength, attention_allocation."""
        # 1. Cross-modal integration
        integrated = self._integrator.integrate(modality_signals)

        # 2. Consciousness gating
        gated, reached = self._gate.gate(integrated, salience, attention)

        # 3. Attention coordination
        if region_demands is None:
            region_demands = {name: salience for name in modality_signals}
        allocation = self._attention.coordinate(region_demands)

        # 4. Running stats
        self._stats.total_integrations += 1
        if reached:
            self._stats.consciousness_access_count += 1

        avg_bind = self._integrator.get_avg_binding_strength()
        self._binding_strength_accum += avg_bind
        self._stats.avg_binding_strength = (
            self._binding_strength_accum / self._stats.total_integrations
        )
        alloc_vals = list(allocation.values())
        if alloc_vals:
            self._attention_accum += float(np.mean(alloc_vals))
            self._stats.avg_attention_allocated = (
                self._attention_accum / self._stats.total_integrations
            )

        return {
            'integrated_signal': gated,
            'reached_consciousness': reached,
            'binding_strength': self._integrator.binding_strength.copy(),
            'attention_allocation': allocation,
        }

    def cross_modal_binding_strength(
        self,
        modality_activations: Dict[str, float],
    ) -> Dict[str, float]:
        """
        Compute cross-modal binding strength (Crick & Koch, 2005).

        The claustrum is proposed as the "conductor of consciousness" —
        it binds disparate cortical representations into unified percepts.
        Binding strength increases when multiple modalities are co-active
        and coherent, forming the substrate for conscious experience.

        Args:
            modality_activations: Dict of {modality_name: activation_level}

        Returns:
            Dict with binding_strength, coherence, consciousness_probability
        """
        if not modality_activations:
            return {'binding_strength': 0.0, 'coherence': 0.0, 'consciousness_probability': 0.0}

        activations = list(modality_activations.values())
        n_active = sum(1 for a in activations if a > 0.1)

        # Binding: stronger when more modalities co-active
        avg_activation = float(np.mean(activations))
        co_activation = n_active / max(1, len(activations))

        # Coherence: low variance = coherent (all modalities agree)
        variance = float(np.var(activations)) if len(activations) > 1 else 0.0
        coherence = max(0.0, 1.0 - variance * 4.0)

        # Binding = co-activation * coherence * average strength
        binding = avg_activation * co_activation * coherence
        binding = min(1.0, binding)

        # Consciousness probability: nonlinear threshold
        consciousness_prob = 1.0 / (1.0 + np.exp(-10.0 * (binding - 0.4)))

        return {
            'binding_strength': round(binding, 4),
            'coherence': round(coherence, 4),
            'consciousness_probability': round(float(consciousness_prob), 4),
            'n_modalities_active': n_active,
        }

    # ── state / stats / serialisation ──

    def get_state(self) -> Dict[str, Any]:
        """Current module state for dashboards / event bus."""
        return {
            'total_integrations': self._stats.total_integrations,
            'consciousness_access_count': self._stats.consciousness_access_count,
            'consciousness_access_ratio': round(self._gate.access_ratio, 4),
            'avg_binding_strength': round(
                self._integrator.get_avg_binding_strength(), 4),
            'known_modalities': list(self._integrator._modality_index.keys()),
            'last_attention_allocation': self._attention.last_allocation,
        }

    def get_stats(self) -> ClaustrumStats:
        """Return the stats dataclass."""
        return self._stats

    def reset(self) -> None:
        """Reset all internal state (useful in tests)."""
        self._integrator = CrossModalIntegrator(
            n_modalities=self.n_modalities, signal_dim=self.signal_dim,
            learning_rate=self._integrator.learning_rate,
        )
        self._gate = ConsciousnessGate(
            consciousness_threshold=self._gate.threshold,
        )
        self._attention = AttentionCoordinator(
            attention_budget=self._attention.budget,
        )
        self._stats = ClaustrumStats()
        self._binding_strength_accum = 0.0
        self._attention_accum = 0.0
        logger.debug("Claustrum reset")

    def to_dict(self) -> Dict[str, Any]:
        """Serialise full state to a plain dict."""
        return {
            'config': {
                'n_modalities': self.n_modalities,
                'signal_dim': self.signal_dim,
                'consciousness_threshold': self._gate.threshold,
                'binding_learning_rate': self._integrator.learning_rate,
                'attention_budget': self._attention.budget,
            },
            'state': self.get_state(),
            'stats': self._stats.to_dict(),
        }

    @classmethod
    def from_yaml(cls, config: Dict[str, Any]) -> 'Claustrum':
        """Construct a Claustrum from the global YAML config dict."""
        c = config.get('claustrum', {})
        return cls(
            n_modalities=c.get('n_modalities', 6),
            signal_dim=c.get('signal_dim', 16),
            consciousness_threshold=c.get('consciousness_threshold', 0.5),
            binding_learning_rate=c.get('binding_learning_rate', 0.01),
            attention_budget=c.get('attention_budget', 1.0),
        )


# ─── Consciousness Gateway (Tononi 2004; Baars 2013; Pitts 2018) ───────

class ConsciousnessGateway:
    """Global Workspace broadcast + Integrated Information (Φ) measurement.

    Implements the computational core of conscious access:
    - Global Workspace: Winner-take-all competition → broadcast to all modules
    - Integrated Information: Φ as measure of how much the system is "more than
      the sum of its parts"
    - Conscious Moment: ~100-200ms binding → broadcast cycle

    Research basis:
    - Tononi (2004): Integrated Information Theory (IIT), 1617 citations
    - Baars, Franklin & Ramsøy (2013): Global Workspace Theory, 293 citations
    - Pitts, Lutsyshyna & Hillyard (2018): Attention-consciousness taxonomy, 133 citations
    """

    def __init__(self, broadcast_threshold: float = 0.5,
                 max_workspace_items: int = 4,
                 broadcast_duration_ms: float = 150.0):
        self._workspace: List[Dict[str, Any]] = []
        self._broadcast_threshold = broadcast_threshold
        self._max_items = max_workspace_items
        self._broadcast_duration_ms = broadcast_duration_ms
        self._broadcast_history: deque = deque(maxlen=200)
        self._phi: float = 0.0  # integrated information
        self._conscious_moments: int = 0
        self._competing_signals: List[Dict[str, Any]] = []
        self._last_broadcast_time: float = 0.0

    def submit_for_consciousness(self, source: str, content: str,
                                   salience: float,
                                   binding_strength: float = 0.5
                                   ) -> Dict[str, Any]:
        """Submit a signal for conscious access (workspace competition).

        Multiple modules can submit signals. Only the most salient win
        access to the global workspace (winner-take-all).
        """
        salience = max(0.0, min(1.0, salience))
        binding_strength = max(0.0, min(1.0, binding_strength))

        signal = {
            'source': source,
            'content': content[:100],
            'salience': salience,
            'binding_strength': binding_strength,
            'timestamp': time.time(),
            'conscious': False
        }
        self._competing_signals.append(signal)

        if len(self._competing_signals) > 20:
            self._competing_signals = sorted(
                self._competing_signals,
                key=lambda s: s['salience'],
                reverse=True
            )[:10]

        return {
            'submitted': True,
            'source': source,
            'salience': round(salience, 4),
            'competitors': len(self._competing_signals)
        }

    def resolve_competition(self) -> Dict[str, Any]:
        """Winner-take-all competition → conscious access.

        The most salient signals (up to max_workspace_items) win access
        to the global workspace and get broadcast to all modules.
        """
        if not self._competing_signals:
            return {
                'conscious_contents': [],
                'broadcast': False,
                'phi': round(self._phi, 4)
            }

        sorted_signals = sorted(
            self._competing_signals,
            key=lambda s: s['salience'] * (0.5 + 0.5 * s['binding_strength']),
            reverse=True
        )

        winners = []
        for s in sorted_signals[:self._max_items]:
            if s['salience'] >= self._broadcast_threshold:
                s['conscious'] = True
                winners.append(s)

        self._workspace = winners
        self._competing_signals = []

        if winners:
            self._conscious_moments += 1
            self._last_broadcast_time = time.time()

            self._phi = self._compute_phi(winners)

            broadcast = {
                'time': time.time(),
                'contents': [{'source': w['source'],
                              'content': w['content'],
                              'salience': w['salience']}
                             for w in winners],
                'phi': round(self._phi, 4),
                'duration_ms': self._broadcast_duration_ms
            }
            self._broadcast_history.append(broadcast)

        return {
            'conscious_contents': [{'source': w['source'],
                                   'content': w['content'],
                                   'salience': round(w['salience'], 4)}
                                  for w in winners],
            'broadcast': len(winners) > 0,
            'items_in_workspace': len(winners),
            'phi': round(self._phi, 4),
            'conscious_moments_total': self._conscious_moments
        }

    def _compute_phi(self, workspace_items: List[Dict]) -> float:
        """Compute integrated information (Φ) — simplified.

        True Φ requires computing information across all possible partitions.
        This is a practical approximation based on:
        - Number of sources contributing (diversity)
        - Binding strength (integration)
        - Cross-modal signals (information beyond parts)
        """
        if not workspace_items:
            return 0.0

        n = len(workspace_items)
        sources = set(w['source'] for w in workspace_items)
        diversity = len(sources) / max(1, n)

        avg_binding = sum(w.get('binding_strength', 0.5)
                         for w in workspace_items) / n
        avg_salience = sum(w['salience'] for w in workspace_items) / n

        phi = diversity * 0.4 + avg_binding * 0.3 + avg_salience * 0.3
        integration_bonus = min(0.2, (n - 1) * 0.05) if n > 1 else 0
        phi = min(1.0, phi + integration_bonus)

        return phi

    def get_conscious_state(self) -> Dict[str, Any]:
        """What is currently in consciousness?"""
        time_since_broadcast = time.time() - self._last_broadcast_time if self._last_broadcast_time else float('inf')
        is_conscious = (time_since_broadcast < self._broadcast_duration_ms / 1000.0
                       and len(self._workspace) > 0)

        if self._phi > 0.7:
            consciousness_level = 'vivid'
        elif self._phi > 0.4:
            consciousness_level = 'aware'
        elif self._phi > 0.2:
            consciousness_level = 'dim'
        else:
            consciousness_level = 'minimal'

        return {
            'is_conscious': is_conscious,
            'consciousness_level': consciousness_level,
            'phi': round(self._phi, 4),
            'workspace_contents': [{'source': w['source'],
                                   'content': w['content']}
                                  for w in self._workspace],
            'workspace_capacity': f'{len(self._workspace)}/{self._max_items}',
            'total_conscious_moments': self._conscious_moments,
            'time_since_last_broadcast_ms': round(time_since_broadcast * 1000, 1)
        }

    def get_state(self) -> Dict[str, Any]:
        return self.get_conscious_state()
