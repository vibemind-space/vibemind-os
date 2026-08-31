"""
Default Mode Network Module - Neuroscience Architecture Extension Phase B1

Computational model of the Default Mode Network for self-referential
processing, mind-wandering, future simulation, and creative association.

Neuroscience basis:
- Raichle et al. (2001): Discovery of the "resting state" network
- Fox et al. (2005): Anti-correlation with task-positive network
- Buckner et al. (2008): DMN role in self-projection (past/future)
- mPFC: Self-referential processing
- PCC/precuneus: Autobiographic memory retrieval
- Angular gyrus: Semantic integration

Key references:
- "Enhanced functional connectivity between DMN and ECN" (PubMed)
- Raichle (2015): The brain's default mode network
- Andrews-Hanna (2012): DMN subnetworks

Integration points:
- Active when no task is running (idle), low cognitive load
- Deactivated during focused work, high attention demands
- Wiring: In cognitive_loop.py CONSOLIDATE phase
"""

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger('brain.dmn')


# ─── Data Classes ──────────────────────────────────────────────────────────────

@dataclass
class DMNStats:
    """DMN activity statistics."""
    activations: int = 0
    deactivations: int = 0
    total_mind_wandering: int = 0
    total_future_simulations: int = 0
    total_self_reflections: int = 0
    current_mode: str = "idle"  # "idle", "active", "suppressed"
    avg_creativity: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'activations': self.activations,
            'deactivations': self.deactivations,
            'total_mind_wandering': self.total_mind_wandering,
            'total_future_simulations': self.total_future_simulations,
            'total_self_reflections': self.total_self_reflections,
            'current_mode': self.current_mode,
            'avg_creativity': round(self.avg_creativity, 3),
        }


@dataclass
class DMNOutput:
    """Output from a DMN processing cycle."""
    self_reflection: np.ndarray
    future_prediction: np.ndarray
    creative_association: np.ndarray
    activation_level: float = 0.0
    mode: str = "idle"

    def to_dict(self) -> Dict[str, Any]:
        return {
            'activation_level': round(self.activation_level, 3),
            'mode': self.mode,
            'self_reflection_norm': round(float(np.linalg.norm(self.self_reflection)), 3),
            'future_prediction_norm': round(float(np.linalg.norm(self.future_prediction)), 3),
            'creative_association_norm': round(float(np.linalg.norm(self.creative_association)), 3),
        }


# ─── Self-Referential Processor (mPFC) ────────────────────────────────────────

class SelfReferentialProcessor:
    """
    Self-referential processing modeling mPFC.

    Answers "Who am I?", "What do I know?", "How am I doing?"
    by maintaining an internal self-model and comparing against
    current state.
    """

    def __init__(self, state_dim: int = 32):
        self.state_dim = state_dim
        self._self_model = np.zeros(state_dim, dtype=np.float32)
        self._self_history = deque(maxlen=50)
        self._update_count = 0

    def reflect(self, current_state: np.ndarray) -> np.ndarray:
        """
        Compare current state with self-model.

        Returns:
            Self-reflection vector (difference from self-model)
        """
        s = np.asarray(current_state, dtype=np.float32).flatten()
        padded = np.zeros(self.state_dim, dtype=np.float32)
        n = min(len(s), self.state_dim)
        padded[:n] = s[:n]

        reflection = padded - self._self_model
        self._self_history.append(padded.copy())
        self._update_count += 1
        return reflection

    def update_self_model(self, learning_rate: float = 0.05):
        """Update self-model as running average of recent states."""
        if not self._self_history:
            return
        recent = np.array(list(self._self_history), dtype=np.float32)
        avg = recent.mean(axis=0)
        self._self_model = (1 - learning_rate) * self._self_model + learning_rate * avg

    @property
    def update_count(self) -> int:
        return self._update_count

    def to_dict(self) -> Dict[str, Any]:
        return {
            'self_model_norm': round(float(np.linalg.norm(self._self_model)), 3),
            'updates': self._update_count,
        }


# ─── Future Simulator ─────────────────────────────────────────────────────────

class FutureSimulator:
    """
    Mental time travel: simulates possible future states.

    Buckner et al. (2008): DMN enables "self-projection" -
    imagining oneself in different times and places.
    Uses simple auto-regressive prediction from recent state history.
    """

    def __init__(self, state_dim: int = 32, horizon: int = 5):
        self.state_dim = state_dim
        self.horizon = horizon
        self._state_history = deque(maxlen=20)
        self._simulation_count = 0

    def record_state(self, state: np.ndarray):
        """Record a state for building predictive model."""
        s = np.asarray(state, dtype=np.float32).flatten()
        padded = np.zeros(self.state_dim, dtype=np.float32)
        n = min(len(s), self.state_dim)
        padded[:n] = s[:n]
        self._state_history.append(padded)

    def simulate_future(self, n_steps: int = 3) -> np.ndarray:
        """
        Simulate future state using linear extrapolation.

        Returns:
            Predicted future state vector
        """
        if len(self._state_history) < 2:
            return np.zeros(self.state_dim, dtype=np.float32)

        history = np.array(list(self._state_history), dtype=np.float32)
        # Linear trend
        trend = history[-1] - history[-2]
        predicted = history[-1] + trend * n_steps

        # Add noise for exploration
        noise = np.random.randn(self.state_dim).astype(np.float32) * 0.05
        predicted += noise

        self._simulation_count += 1
        return predicted

    @property
    def simulation_count(self) -> int:
        return self._simulation_count

    def to_dict(self) -> Dict[str, Any]:
        return {
            'history_size': len(self._state_history),
            'simulations': self._simulation_count,
        }


# ─── Mind Wandering Generator ─────────────────────────────────────────────────

class MindWanderingGenerator:
    """
    Generates creative associations through stochastic exploration.

    Mind-wandering in the DMN supports creative thinking by making
    distant semantic associations (Beaty et al., 2016).
    """

    def __init__(self, state_dim: int = 32, creativity_temperature: float = 1.5):
        self.state_dim = state_dim
        self.temperature = creativity_temperature
        self._association_count = 0
        self._memory_bank = deque(maxlen=100)

    def store_experience(self, state: np.ndarray):
        """Store an experience for later association."""
        s = np.asarray(state, dtype=np.float32).flatten()
        padded = np.zeros(self.state_dim, dtype=np.float32)
        n = min(len(s), self.state_dim)
        padded[:n] = s[:n]
        self._memory_bank.append(padded)

    def generate_association(self, seed: Optional[np.ndarray] = None) -> np.ndarray:
        """
        Generate a creative association.

        Combines random memories with noise to create novel patterns.
        """
        if not self._memory_bank:
            return np.random.randn(self.state_dim).astype(np.float32) * 0.1

        # Pick 2-3 random memories and blend
        n_blend = min(3, len(self._memory_bank))
        indices = np.random.choice(len(self._memory_bank), n_blend, replace=False)
        memories = [list(self._memory_bank)[i] for i in indices]

        # Weighted blend with randomness
        weights = np.random.dirichlet(np.ones(n_blend) * self.temperature)
        blended = sum(w * m for w, m in zip(weights, memories))

        # Add creative noise
        noise = np.random.randn(self.state_dim).astype(np.float32) * 0.1 * self.temperature
        result = blended + noise

        if seed is not None:
            s = np.asarray(seed, dtype=np.float32).flatten()[:self.state_dim]
            padded_seed = np.zeros(self.state_dim, dtype=np.float32)
            padded_seed[:len(s)] = s
            result = 0.5 * result + 0.5 * padded_seed

        self._association_count += 1
        return result.astype(np.float32)

    @property
    def association_count(self) -> int:
        return self._association_count

    def to_dict(self) -> Dict[str, Any]:
        return {
            'temperature': self.temperature,
            'memory_bank_size': len(self._memory_bank),
            'associations': self._association_count,
        }


# ─── DMN-TPN Switch ───────────────────────────────────────────────────────────

class DMN_TPN_Switch:
    """
    Switch between Default Mode Network and Task-Positive Network.

    Fox et al. (2005): DMN and TPN are anti-correlated -
    when one is active, the other is suppressed.
    """

    def __init__(self, switch_threshold: float = 0.3):
        self.switch_threshold = switch_threshold
        self._dmn_active = True
        self._task_load = 0.0
        self._switch_count = 0

    def update(self, task_load: float) -> bool:
        """
        Update the DMN/TPN switch based on current task load.

        Args:
            task_load: Current cognitive load [0, 1]
                       0 = no task, 1 = maximum focus

        Returns:
            True if DMN is active
        """
        self._task_load = max(0.0, min(1.0, task_load))
        was_active = self._dmn_active

        # DMN active when task load is below threshold
        self._dmn_active = self._task_load < self.switch_threshold

        if was_active != self._dmn_active:
            self._switch_count += 1

        return self._dmn_active

    @property
    def is_dmn_active(self) -> bool:
        return self._dmn_active

    @property
    def switch_count(self) -> int:
        return self._switch_count

    def to_dict(self) -> Dict[str, Any]:
        return {
            'dmn_active': self._dmn_active,
            'task_load': round(self._task_load, 3),
            'switch_count': self._switch_count,
            'threshold': self.switch_threshold,
        }


# ─── Main Default Mode Network ────────────────────────────────────────────────

class DefaultModeNetwork:
    """
    Complete Default Mode Network module.

    Functions:
    1. Self-referential processing (mPFC)
    2. Mental time travel / future simulation (PCC)
    3. Creative association / mind-wandering (angular gyrus)
    4. DMN/TPN anti-correlation switching
    5. Idle-state consolidation
    """

    def __init__(
        self,
        state_dim: int = 32,
        activation_threshold: float = 0.3,
        creativity_temperature: float = 1.5,
        mind_wandering_rate: float = 0.1,
    ):
        self.state_dim = state_dim

        self.self_processor = SelfReferentialProcessor(state_dim)
        self.future_simulator = FutureSimulator(state_dim)
        self.mind_wandering = MindWanderingGenerator(state_dim, creativity_temperature)
        self.switch = DMN_TPN_Switch(activation_threshold)

        self._mind_wandering_rate = mind_wandering_rate
        self._stats = DMNStats()
        self._creativity_scores = deque(maxlen=100)

    def process(self, state: np.ndarray, task_load: float = 0.0) -> DMNOutput:
        """
        Run DMN processing cycle.

        If task_load is low, DMN activates and produces:
        - Self-reflection
        - Future predictions
        - Creative associations

        If task_load is high, DMN is suppressed.

        Args:
            state: Current brain state
            task_load: Current cognitive load [0, 1]

        Returns:
            DMNOutput with all processing results
        """
        s = np.asarray(state, dtype=np.float32).flatten()

        # Store experience regardless of mode
        self.future_simulator.record_state(s)
        self.mind_wandering.store_experience(s)

        # Check if DMN should be active
        dmn_active = self.switch.update(task_load)
        activation_level = max(0.0, 1.0 - task_load)

        if dmn_active:
            # DMN active: full processing
            self._stats.activations += 1
            self._stats.current_mode = "active"

            # Self-reflection
            self_ref = self.self_processor.reflect(s)
            self.self_processor.update_self_model()
            self._stats.total_self_reflections += 1

            # Future simulation
            future = self.future_simulator.simulate_future(n_steps=3)
            self._stats.total_future_simulations += 1

            # Mind wandering (probabilistic)
            if np.random.random() < self._mind_wandering_rate:
                creative = self.mind_wandering.generate_association(seed=s)
                self._stats.total_mind_wandering += 1
                creativity = float(np.linalg.norm(creative))
                self._creativity_scores.append(creativity)
            else:
                creative = np.zeros(self.state_dim, dtype=np.float32)

        else:
            # DMN suppressed
            self._stats.deactivations += 1
            self._stats.current_mode = "suppressed"
            self_ref = np.zeros(self.state_dim, dtype=np.float32)
            future = np.zeros(self.state_dim, dtype=np.float32)
            creative = np.zeros(self.state_dim, dtype=np.float32)

        # Update avg creativity
        if self._creativity_scores:
            self._stats.avg_creativity = float(np.mean(list(self._creativity_scores)))

        return DMNOutput(
            self_reflection=self_ref,
            future_prediction=future,
            creative_association=creative,
            activation_level=activation_level,
            mode="active" if dmn_active else "suppressed",
        )

    def mental_time_travel(
        self,
        state: np.ndarray,
        direction: str = 'future',
        emotional_valence: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Mental time travel — DMN's core function (Buckner & Carroll, 2007).

        The DMN enables both episodic memory retrieval (past) and
        prospection (future simulation). Both share neural substrate in
        DMN, explaining why damage impairs both memory and imagination.

        Args:
            state: Current state vector
            direction: 'past' for retrieval, 'future' for prospection
            emotional_valence: Emotional coloring [-1=negative, 1=positive]

        Returns:
            Dict with simulation result, vividness, self_relevance
        """
        state = np.asarray(state, dtype=np.float32)

        if direction == 'future':
            simulated = self.future_simulator.simulate_future(n_steps=3)
        else:
            # Past retrieval: reflect using self-model
            simulated = self.self_processor.reflect(state)

        # Self-relevance: how much the simulation relates to self-model
        self_vec = self.self_processor._self_model
        if np.linalg.norm(self_vec) > 0 and np.linalg.norm(simulated) > 0:
            self_relevance = float(np.dot(self_vec, simulated) / (
                np.linalg.norm(self_vec) * np.linalg.norm(simulated)
            ))
        else:
            self_relevance = 0.0
        self_relevance = max(0.0, min(1.0, (self_relevance + 1.0) / 2.0))

        # Vividness: affected by emotional valence (emotion enhances simulation)
        base_vividness = float(np.std(simulated)) if len(simulated) > 0 else 0.0
        vividness = min(1.0, base_vividness * (1.0 + abs(emotional_valence) * 0.5))

        return {
            'direction': direction,
            'vividness': round(vividness, 4),
            'self_relevance': round(self_relevance, 4),
            'emotional_coloring': round(emotional_valence, 3),
            'simulation_norm': round(float(np.linalg.norm(simulated)), 4),
        }

    def get_state(self) -> Dict[str, Any]:
        return {
            'stats': self._stats.to_dict(),
            'self_processor': self.self_processor.to_dict(),
            'future_simulator': self.future_simulator.to_dict(),
            'mind_wandering': self.mind_wandering.to_dict(),
            'switch': self.switch.to_dict(),
        }

    def get_stats(self) -> DMNStats:
        return self._stats

    def reset(self):
        self._stats = DMNStats()
        self._creativity_scores.clear()

    def to_dict(self) -> Dict[str, Any]:
        return self.get_state()

    @classmethod
    def from_yaml(cls, config: Dict[str, Any]) -> 'DefaultModeNetwork':
        """
        Create DefaultModeNetwork from YAML configuration.

        Expected config:
            default_mode_network:
              activation_threshold: 0.3
              creativity_temperature: 1.5
              mind_wandering_rate: 0.1
        """
        dmn = config.get('default_mode_network', {})
        state_dim = config.get('state_dim',
                    config.get('model', {}).get('input_dim', 32))

        return cls(
            state_dim=state_dim,
            activation_threshold=dmn.get('activation_threshold', 0.3),
            creativity_temperature=dmn.get('creativity_temperature', 1.5),
            mind_wandering_rate=dmn.get('mind_wandering_rate', 0.1),
        )
