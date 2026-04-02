"""
Amygdala Complex Module - Phase D1

The amygdala is the brain's primary emotional processing center,
located bilaterally in the medial temporal lobes. It evaluates the
emotional significance of stimuli, assigns valence (positive/negative),
and orchestrates emotional responses.

Neuroscience basis:
- Basolateral Amygdala (BLA): Sensory input hub, cortical/thalamic inputs,
  evaluates emotional significance, fear conditioning, valence assignment
  (LeDoux, 1996; Phelps & LeDoux, 2005)
- Central Amygdala (CeA): Primary output hub, projects to hypothalamus,
  PAG, LC, NTS. Orchestrates fear/defensive responses (freeze/fight/flight)
  (Ciocchi et al., 2010)
- Medial Amygdala (MeA): Social/pheromonal processing, innate behaviors,
  species-specific responses

Key functions:
- Valence tagging (positive/negative) on all incoming stimuli
- Threat detection and fear conditioning
- Fear extinction learning (BLA plasticity)
- Emotional memory formation (BLA <-> hippocampus)
- Social signal processing

Integration:
- Input: BLA <- cortex, thalamus (sensory), hippocampus (context)
- Output: CeA -> hypothalamus (HPA), PAG (defense), LC (arousal), NTS (autonomic)
- Bidirectional: BLA <-> PFC (regulation), BLA <-> hippocampus (memory)
"""

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger('brain.amygdala')


@dataclass
class AmygdalaStats:
    """Amygdala processing statistics."""
    total_evaluations: int = 0
    total_threats_detected: int = 0
    total_positive_valence: int = 0
    total_negative_valence: int = 0
    total_fear_conditioned: int = 0
    total_fear_extinctions: int = 0
    avg_threat_level: float = 0.0
    avg_valence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_evaluations': self.total_evaluations,
            'total_threats_detected': self.total_threats_detected,
            'total_positive_valence': self.total_positive_valence,
            'total_negative_valence': self.total_negative_valence,
            'total_fear_conditioned': self.total_fear_conditioned,
            'total_fear_extinctions': self.total_fear_extinctions,
            'avg_threat_level': round(self.avg_threat_level, 3),
            'avg_valence': round(self.avg_valence, 3),
        }


class BasolateralAmygdala:
    """
    Basolateral Amygdala (BLA) — Primary sensory INPUT hub.

    Receives cortical and thalamic inputs. Evaluates emotional significance
    of stimuli through learned associations. Core site for:
    - Fear conditioning (CS-US association)
    - Valence assignment (positive/negative)
    - Extinction learning (new safety associations)

    LeDoux (1996): Two pathways to BLA:
    - Low road: Thalamus -> BLA (fast, crude threat detection)
    - High road: Thalamus -> Cortex -> BLA (slow, detailed evaluation)
    """

    def __init__(
        self,
        n_features: int = 10,
        learning_rate: float = 0.05,
        extinction_rate: float = 0.02,
        threat_threshold: float = 0.6,
    ):
        self.n_features = n_features
        self.learning_rate = learning_rate
        self.extinction_rate = extinction_rate
        self.threat_threshold = threat_threshold

        # Association weights: feature -> valence mapping
        # Positive weights = aversive, negative weights = appetitive
        self._association_weights = np.zeros(n_features, dtype=np.float32)

        # Fear conditioning memory: maps stimulus hash -> (strength, timestamp)
        self._fear_associations: Dict[str, Tuple[float, float]] = {}

        # Valence history for running statistics
        self._valence_history = deque(maxlen=200)
        self._threat_history = deque(maxlen=200)

    def evaluate_stimulus(
        self,
        features: np.ndarray,
        context: Optional[np.ndarray] = None,
    ) -> Dict[str, float]:
        """
        Evaluate emotional significance of a stimulus.

        Two pathways:
        - Fast (thalamic): raw feature-based threat detection
        - Slow (cortical): context-modulated detailed evaluation

        Args:
            features: Stimulus feature vector [n_features]
            context: Optional contextual information (hippocampal input)

        Returns:
            Dict with valence, arousal, threat_level, dominance
        """
        feat = np.asarray(features, dtype=np.float32).flatten()
        padded = np.zeros(self.n_features, dtype=np.float32)
        n = min(len(feat), self.n_features)
        padded[:n] = feat[:n]

        # Fast pathway: raw feature-weight dot product
        raw_valence = float(np.dot(padded, self._association_weights))

        # Slow pathway: context-modulated evaluation
        if context is not None:
            ctx = np.asarray(context, dtype=np.float32).flatten()
            ctx_padded = np.zeros(self.n_features, dtype=np.float32)
            cn = min(len(ctx), self.n_features)
            ctx_padded[:cn] = ctx[:cn]
            # Context modulates valence (safety context reduces threat)
            context_modulation = float(np.mean(ctx_padded)) * 0.3
            valence = raw_valence - context_modulation
        else:
            valence = raw_valence

        # Normalize valence to [-1, 1]
        valence = float(np.clip(valence, -1.0, 1.0))

        # Arousal: magnitude of emotional response
        arousal = float(min(1.0, abs(valence) * 1.5))

        # Threat level: derived from negative valence
        threat_level = float(max(0.0, valence) if valence > 0 else 0.0)
        # Also check feature intensity for fast-path threat
        feature_intensity = float(np.mean(np.abs(padded)))
        threat_level = max(threat_level, feature_intensity * 0.3)
        threat_level = min(1.0, threat_level)

        # Dominance: inverse of threat (high threat = low dominance/control)
        dominance = 1.0 - threat_level * 0.7

        self._valence_history.append(valence)
        self._threat_history.append(threat_level)

        return {
            'valence': valence,
            'arousal': arousal,
            'threat_level': threat_level,
            'dominance': dominance,
            'pathway': 'dual' if context is not None else 'fast',
        }

    def condition_fear(self, stimulus_id: str, features: np.ndarray, strength: float = 1.0):
        """
        Form a fear association (classical conditioning).

        BLA plasticity: strengthens association weights for threatening stimuli.

        Args:
            stimulus_id: Identifier for the conditioned stimulus
            features: Feature vector of the CS
            strength: Strength of the unconditioned stimulus [0, 1]
        """
        feat = np.asarray(features, dtype=np.float32).flatten()
        padded = np.zeros(self.n_features, dtype=np.float32)
        n = min(len(feat), self.n_features)
        padded[:n] = feat[:n]

        # Strengthen aversive associations
        update = padded * strength * self.learning_rate
        self._association_weights += update

        # Store explicit association
        self._fear_associations[stimulus_id] = (strength, time.time())
        logger.debug(f"Fear conditioned: {stimulus_id} (strength={strength:.2f})")

    def extinguish_fear(self, stimulus_id: str, features: np.ndarray):
        """
        Extinction learning — form a new safety association.

        Note: Extinction doesn't erase the original fear memory;
        it creates a competing inhibitory association (Bouton, 2004).

        Args:
            stimulus_id: Identifier of the conditioned stimulus
            features: Feature vector of the CS
        """
        feat = np.asarray(features, dtype=np.float32).flatten()
        padded = np.zeros(self.n_features, dtype=np.float32)
        n = min(len(feat), self.n_features)
        padded[:n] = feat[:n]

        # Weaken aversive associations (slowly)
        update = padded * self.extinction_rate
        self._association_weights -= update

        # Reduce but don't fully remove the association
        if stimulus_id in self._fear_associations:
            old_strength, ts = self._fear_associations[stimulus_id]
            new_strength = max(0.0, old_strength - self.extinction_rate * 5)
            self._fear_associations[stimulus_id] = (new_strength, time.time())

    def is_fear_conditioned(self, stimulus_id: str, threshold: float = 0.1) -> bool:
        """Check if a stimulus has a fear association."""
        if stimulus_id not in self._fear_associations:
            return False
        strength, _ = self._fear_associations[stimulus_id]
        return strength > threshold

    def get_avg_valence(self) -> float:
        if not self._valence_history:
            return 0.0
        return float(np.mean(list(self._valence_history)))

    def get_avg_threat(self) -> float:
        if not self._threat_history:
            return 0.0
        return float(np.mean(list(self._threat_history)))

    def to_dict(self) -> Dict[str, Any]:
        return {
            'n_fear_associations': len(self._fear_associations),
            'avg_valence': round(self.get_avg_valence(), 3),
            'avg_threat': round(self.get_avg_threat(), 3),
            'association_norm': round(float(np.linalg.norm(self._association_weights)), 3),
        }


class CentralAmygdala:
    """
    Central Amygdala (CeA) — Primary OUTPUT hub.

    Receives processed signals from BLA and generates
    coordinated emotional responses via projections to:
    - Hypothalamus: HPA axis activation (cortisol)
    - PAG: Defensive behaviors (freeze/fight/flight)
    - LC: Arousal/norepinephrine release
    - NTS: Autonomic responses (heart rate, respiration)

    Ciocchi et al. (2010): CeA contains distinct cell populations
    for different defensive responses (CeL on/off cells).
    """

    def __init__(self, output_gain: float = 1.0):
        self.output_gain = output_gain
        self._last_output = {}

    def generate_response(
        self,
        threat_level: float,
        valence: float,
        arousal: float,
    ) -> Dict[str, float]:
        """
        Generate coordinated emotional response outputs.

        Args:
            threat_level: Current threat assessment [0, 1]
            valence: Emotional valence [-1, 1]
            arousal: Emotional arousal [0, 1]

        Returns:
            Dict of output signals to downstream targets
        """
        threat = max(0.0, min(1.0, threat_level))
        val = max(-1.0, min(1.0, valence))
        ar = max(0.0, min(1.0, arousal))

        # HPA axis activation: scales with threat
        hpa_activation = threat * self.output_gain * 0.8 + ar * 0.2
        hpa_activation = min(1.0, hpa_activation)

        # PAG defensive signal: strong with high threat
        pag_signal = threat * self.output_gain
        pag_signal = min(1.0, pag_signal)

        # LC arousal signal: threat + general arousal
        lc_signal = threat * 0.6 + ar * 0.4
        lc_signal = min(1.0, lc_signal * self.output_gain)

        # Autonomic arousal: heart rate, respiration
        autonomic_arousal = ar * 0.7 + threat * 0.3
        autonomic_arousal = min(1.0, autonomic_arousal)

        # Behavioral inhibition: freeze response when threat is moderate
        freeze_signal = 0.0
        if 0.3 < threat < 0.7:
            freeze_signal = (1.0 - abs(threat - 0.5) * 4) * self.output_gain

        self._last_output = {
            'hpa_activation': round(hpa_activation, 3),
            'pag_signal': round(pag_signal, 3),
            'lc_signal': round(lc_signal, 3),
            'autonomic_arousal': round(autonomic_arousal, 3),
            'freeze_signal': round(freeze_signal, 3),
        }
        return self._last_output

    def to_dict(self) -> Dict[str, Any]:
        return self._last_output.copy() if self._last_output else {}


class MedialAmygdala:
    """
    Medial Amygdala (MeA) — Social and innate behavior processing.

    Processes social signals, species-specific behaviors, and
    innate threat responses (e.g., predator odor in rodents).
    In Tahlamus: processes agent reputation, social trust signals,
    and innate safety heuristics.
    """

    def __init__(self, social_sensitivity: float = 0.5):
        self.social_sensitivity = social_sensitivity
        self._social_memory: Dict[str, float] = {}  # agent_id -> trust_valence

    def evaluate_social_signal(
        self,
        agent_id: str,
        signal_type: str,
        intensity: float = 0.5,
    ) -> Dict[str, float]:
        """
        Evaluate a social signal from another agent.

        Args:
            agent_id: Identifier of the social partner
            signal_type: Type of signal (cooperative, competitive, neutral, threatening)
            intensity: Signal intensity [0, 1]

        Returns:
            Dict with social_valence, approach_tendency, social_arousal
        """
        # Base valence from signal type
        type_valence_map = {
            'cooperative': 0.7,
            'neutral': 0.0,
            'competitive': -0.3,
            'threatening': -0.8,
        }
        base_valence = type_valence_map.get(signal_type, 0.0) * intensity

        # Modulate by prior social memory
        prior = self._social_memory.get(agent_id, 0.0)
        social_valence = base_valence * 0.7 + prior * 0.3
        social_valence = max(-1.0, min(1.0, social_valence))

        # Update social memory (slow learning)
        alpha = 0.1 * self.social_sensitivity
        self._social_memory[agent_id] = prior * (1 - alpha) + social_valence * alpha

        # Approach tendency: positive valence -> approach
        approach_tendency = (social_valence + 1.0) / 2.0

        # Social arousal
        social_arousal = abs(social_valence) * intensity * self.social_sensitivity

        return {
            'social_valence': round(social_valence, 3),
            'approach_tendency': round(approach_tendency, 3),
            'social_arousal': round(social_arousal, 3),
        }

    def get_social_trust(self, agent_id: str) -> float:
        """Get accumulated trust valence for an agent."""
        return self._social_memory.get(agent_id, 0.0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'n_social_memories': len(self._social_memory),
            'social_sensitivity': self.social_sensitivity,
        }


class AmygdalaComplex:
    """
    Complete Amygdala Complex module.

    Integrates BLA (input/evaluation), CeA (output/response),
    and MeA (social processing) into a unified emotional processing
    center. This is THE emotional valence assigner for Tahlamus.

    Functions:
    1. Stimulus valence evaluation (BLA)
    2. Fear conditioning and extinction (BLA)
    3. Coordinated emotional response generation (CeA)
    4. Social signal processing (MeA)
    5. Threat detection and alerting
    """

    def __init__(
        self,
        n_features: int = 10,
        learning_rate: float = 0.05,
        extinction_rate: float = 0.02,
        threat_threshold: float = 0.6,
        output_gain: float = 1.0,
        social_sensitivity: float = 0.5,
    ):
        self.bla = BasolateralAmygdala(
            n_features=n_features,
            learning_rate=learning_rate,
            extinction_rate=extinction_rate,
            threat_threshold=threat_threshold,
        )
        self.cea = CentralAmygdala(output_gain=output_gain)
        self.mea = MedialAmygdala(social_sensitivity=social_sensitivity)
        self._stats = AmygdalaStats()
        self._threat_threshold = threat_threshold

    def process_stimulus(
        self,
        features: np.ndarray,
        context: Optional[np.ndarray] = None,
    ) -> Dict[str, Any]:
        """
        Full amygdala processing cycle for a stimulus.

        1. BLA evaluates emotional significance
        2. CeA generates coordinated response
        3. Returns unified emotional assessment

        Args:
            features: Stimulus feature vector
            context: Optional contextual information

        Returns:
            Dict with valence, arousal, threat, response outputs
        """
        # BLA evaluation
        evaluation = self.bla.evaluate_stimulus(features, context)

        # CeA response generation
        response = self.cea.generate_response(
            threat_level=evaluation['threat_level'],
            valence=evaluation['valence'],
            arousal=evaluation['arousal'],
        )

        # Update stats
        self._stats.total_evaluations += 1
        if evaluation['threat_level'] > self._threat_threshold:
            self._stats.total_threats_detected += 1
        if evaluation['valence'] > 0.1:
            self._stats.total_negative_valence += 1  # positive weights = aversive
        elif evaluation['valence'] < -0.1:
            self._stats.total_positive_valence += 1  # negative weights = appetitive
        self._stats.avg_threat_level = self.bla.get_avg_threat()
        self._stats.avg_valence = self.bla.get_avg_valence()

        return {
            'evaluation': evaluation,
            'response': response,
            'is_threat': evaluation['threat_level'] > self._threat_threshold,
        }

    def condition_fear(self, stimulus_id: str, features: np.ndarray, strength: float = 1.0):
        """Form a fear association."""
        self.bla.condition_fear(stimulus_id, features, strength)
        self._stats.total_fear_conditioned += 1

    def extinguish_fear(self, stimulus_id: str, features: np.ndarray):
        """Begin extinction of a fear association."""
        self.bla.extinguish_fear(stimulus_id, features)
        self._stats.total_fear_extinctions += 1

    def evaluate_social(
        self,
        agent_id: str,
        signal_type: str,
        intensity: float = 0.5,
    ) -> Dict[str, float]:
        """Evaluate a social signal via MeA."""
        return self.mea.evaluate_social_signal(agent_id, signal_type, intensity)

    def dual_route_threat_assessment(
        self,
        stimulus_features: np.ndarray,
        cortical_evaluation: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Dual-route threat processing (LeDoux, 2000).

        The amygdala has two processing routes:
        - Low road (thalamo-amygdala): Fast, coarse, subcortical.
          Reaches BLA in ~12ms. Good for survival but false-alarm prone.
        - High road (thalamo-cortical-amygdala): Slow, precise, cortical.
          Reaches BLA in ~30-40ms. Accurate but delayed.

        The fast route generates a preliminary threat response that can be
        overridden by the slow cortical evaluation.

        Args:
            stimulus_features: Feature vector of the stimulus
            cortical_evaluation: Cortical threat evaluation [0=safe, 1=threat]

        Returns:
            Dict with fast_threat, slow_threat, final_threat, override
        """
        features = np.asarray(stimulus_features, dtype=np.float32)

        # Low road: fast, coarse — based on raw feature magnitude
        feature_energy = float(np.mean(np.abs(features))) if len(features) > 0 else 0.0
        fast_threat = min(1.0, feature_energy * 1.5)

        # High road: slow, accurate — cortical evaluation
        slow_threat = cortical_evaluation

        # If cortical says safe but subcortical flagged threat, cortex can override
        override = fast_threat > 0.4 and slow_threat < 0.2

        # Final threat: blend, with cortex having veto power
        if slow_threat < 0.15 and fast_threat < 0.5:
            final_threat = slow_threat * 0.7 + fast_threat * 0.3
        else:
            final_threat = max(fast_threat, slow_threat)

        return {
            'fast_threat_low_road': round(fast_threat, 4),
            'slow_threat_high_road': round(slow_threat, 4),
            'final_threat': round(min(1.0, final_threat), 4),
            'cortical_override': override,
            'processing_route': 'low_road' if fast_threat > slow_threat else 'high_road',
        }

    def get_state(self) -> Dict[str, Any]:
        return {
            'stats': self._stats.to_dict(),
            'bla': self.bla.to_dict(),
            'cea': self.cea.to_dict(),
            'mea': self.mea.to_dict(),
        }

    def get_stats(self) -> AmygdalaStats:
        return self._stats

    def reset(self):
        self._stats = AmygdalaStats()

    def to_dict(self) -> Dict[str, Any]:
        return self.get_state()

    @classmethod
    def from_yaml(cls, config: Dict[str, Any]) -> 'AmygdalaComplex':
        cfg = config.get('amygdala', {})
        return cls(
            n_features=cfg.get('n_features', 10),
            learning_rate=cfg.get('learning_rate', 0.05),
            extinction_rate=cfg.get('extinction_rate', 0.02),
            threat_threshold=cfg.get('threat_threshold', 0.6),
            output_gain=cfg.get('output_gain', 1.0),
            social_sensitivity=cfg.get('social_sensitivity', 0.5),
        )
