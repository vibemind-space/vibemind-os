"""
Bed Nucleus of the Stria Terminalis (BNST) — Sustained Anxiety and Uncertainty Processing

Extended amygdala structure mediating sustained anxiety responses to uncertain
or prolonged threats, distinct from the basolateral amygdala's acute fear
responses. Implements:

1. Sustained anxiety monitoring (slow integration, persistent activation)
2. Chronic stress accumulation with resilience erosion
3. Uncertainty-based threat amplification (core BNST function)
4. Vigilance control with scanning breadth and startle modulation

Key distinction from amygdala:
    Amygdala = acute, phasic fear to specific threats (fight-or-flight)
    BNST     = sustained, tonic anxiety to uncertain/diffuse threats (worry)

References:
    - Davis et al. (2010): BNST mediates sustained anxiety vs amygdala phasic fear
    - Walker et al. (2003): BNST lesions reduce anxiety but not conditioned fear
    - Avery et al. (2016): BNST activation correlates with anticipatory anxiety
    - Sullivan et al. (2004): BNST role in chronic stress and HPA axis regulation
"""

import logging
import numpy as np
from typing import Dict, Any
from dataclasses import dataclass
from collections import deque

logger = logging.getLogger('brain.bnst')


# ============================================================================
# Stats Dataclass
# ============================================================================

@dataclass
class BNSTStats:
    """Accumulated statistics for the BNST module."""
    total_cycles: int = 0
    avg_anxiety: float = 0.0
    peak_anxiety: float = 0.0
    chronic_stress_episodes: int = 0
    avg_vigilance: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_cycles': self.total_cycles,
            'avg_anxiety': round(self.avg_anxiety, 4),
            'peak_anxiety': round(self.peak_anxiety, 4),
            'chronic_stress_episodes': self.chronic_stress_episodes,
            'avg_vigilance': round(self.avg_vigilance, 4),
        }


# ============================================================================
# Sub-component Classes
# ============================================================================

class SustainedAnxietyMonitor:
    """
    Tracks sustained anxiety level with slow integration and persistent decay.

    Unlike the amygdala's fast phasic fear response, BNST anxiety builds
    gradually under uncertain threat and decays slowly when threat is removed.
    High uncertainty amplifies the anxiety signal (Davis et al., 2010).
    """

    def __init__(self, integration_rate: float = 0.05, decay_rate: float = 0.02):
        self.integration_rate = integration_rate
        self.decay_rate = decay_rate
        self._anxiety: float = 0.0

    def update(self, threat_level: float, uncertainty: float, dt: float = 1.0) -> float:
        """
        Update sustained anxiety based on threat and uncertainty.

        Args:
            threat_level: Current threat intensity [0, 1].
            uncertainty: Situational uncertainty [0, 1].
            dt: Time step (default 1.0).

        Returns:
            Current anxiety level [0, 1].
        """
        threat_level = float(np.clip(threat_level, 0.0, 1.0))
        uncertainty = float(np.clip(uncertainty, 0.0, 1.0))

        # Uncertainty amplifies threat — the core BNST mechanism
        effective_threat = threat_level * uncertainty

        # Slow integration toward effective threat, slow decay away from it
        delta = (effective_threat - self._anxiety) * self.integration_rate * dt

        # Additional slow decay when effective threat is low
        if effective_threat < self._anxiety:
            delta -= self._anxiety * self.decay_rate * dt

        self._anxiety += delta
        self._anxiety = float(np.clip(self._anxiety, 0.0, 1.0))
        return self._anxiety

    @property
    def anxiety(self) -> float:
        return self._anxiety

    def reset(self) -> None:
        self._anxiety = 0.0


class ChronicStressAccumulator:
    """
    Accumulates chronic stress over time with slow decay and resilience erosion.

    Repeated stressor exposure increases accumulated stress and gradually
    reduces stress resilience, mirroring HPA axis dysregulation under
    chronic stress (Sullivan et al., 2004).
    """

    def __init__(
        self,
        stress_threshold: float = 0.6,
        accumulation_rate: float = 0.03,
        decay_rate: float = 0.01,
        resilience_erosion_rate: float = 0.005,
        chronic_window: int = 50,
    ):
        self.stress_threshold = stress_threshold
        self.accumulation_rate = accumulation_rate
        self.decay_rate = decay_rate
        self.resilience_erosion_rate = resilience_erosion_rate

        self._stress: float = 0.0
        self._resilience: float = 1.0
        self._recovery_rate: float = 1.0
        self._above_threshold_count: int = 0
        self._chronic_window = chronic_window
        self._chronic_episodes: int = 0

    def accumulate(self, stressor_intensity: float) -> Dict[str, Any]:
        """
        Accumulate stress from a stressor and update resilience.

        Args:
            stressor_intensity: Intensity of current stressor [0, 1].

        Returns:
            Dict with stress_level, resilience, recovery_rate, is_chronic.
        """
        stressor_intensity = float(np.clip(stressor_intensity, 0.0, 1.0))

        # Accumulate stress (resilience reduces effective accumulation)
        effective_accumulation = stressor_intensity * self.accumulation_rate / max(self._resilience, 0.1)
        self._stress += effective_accumulation

        # Natural decay
        self._stress -= self._stress * self.decay_rate
        self._stress = float(np.clip(self._stress, 0.0, 1.0))

        # Track chronic stress episodes
        if self._stress > self.stress_threshold:
            self._above_threshold_count += 1
        else:
            self._above_threshold_count = max(0, self._above_threshold_count - 1)

        is_chronic = self._above_threshold_count >= self._chronic_window
        if is_chronic and self._above_threshold_count == self._chronic_window:
            self._chronic_episodes += 1

        # Resilience erodes under chronic stress, recovers otherwise
        if self._stress > self.stress_threshold:
            self._resilience -= self.resilience_erosion_rate
        else:
            self._resilience += self.resilience_erosion_rate * 0.5
        self._resilience = float(np.clip(self._resilience, 0.1, 1.0))

        # Recovery rate inversely related to chronic stress
        self._recovery_rate = self._resilience * (1.0 - 0.5 * self._stress)
        self._recovery_rate = float(np.clip(self._recovery_rate, 0.05, 1.0))

        return {
            'stress_level': round(self._stress, 4),
            'resilience': round(self._resilience, 4),
            'recovery_rate': round(self._recovery_rate, 4),
            'is_chronic': is_chronic,
        }

    @property
    def stress_level(self) -> float:
        return self._stress

    @property
    def resilience(self) -> float:
        return self._resilience

    @property
    def chronic_episodes(self) -> int:
        return self._chronic_episodes

    def reset(self) -> None:
        self._stress = 0.0
        self._resilience = 1.0
        self._recovery_rate = 1.0
        self._above_threshold_count = 0
        self._chronic_episodes = 0


class UncertaintyThreatAmplifier:
    """
    Amplifies threat responses under uncertainty — the signature BNST function.

    When situational uncertainty exceeds 0.5, threat perception is amplified.
    This models the BNST's role in making ambiguous situations feel more
    dangerous (Avery et al., 2016).
    """

    def __init__(self, uncertainty_gain: float = 1.0):
        self.uncertainty_gain = uncertainty_gain

    def amplify(self, base_threat: float, uncertainty: float) -> float:
        """
        Amplify threat based on uncertainty.

        Args:
            base_threat: Base threat level [0, 1].
            uncertainty: Situational uncertainty [0, 1].

        Returns:
            Amplified threat level [0, 1].
        """
        base_threat = float(np.clip(base_threat, 0.0, 1.0))
        uncertainty = float(np.clip(uncertainty, 0.0, 1.0))

        # Amplification only kicks in above uncertainty threshold of 0.5
        excess_uncertainty = max(0.0, uncertainty - 0.5)
        amplified = base_threat * (1.0 + self.uncertainty_gain * excess_uncertainty)

        return float(np.clip(amplified, 0.0, 1.0))


class VigilanceController:
    """
    Controls sustained vigilance driven by anxiety and chronic stress.

    High anxiety produces narrow scanning breadth (tunnel vision / rumination)
    and enhanced startle sensitivity. Chronic stress further elevates baseline
    vigilance (Walker et al., 2003).
    """

    def __init__(self, vigilance_gain: float = 1.0):
        self.vigilance_gain = vigilance_gain

    def compute_vigilance(self, anxiety: float, chronic_stress: float) -> Dict[str, float]:
        """
        Compute vigilance outputs from anxiety and chronic stress.

        Args:
            anxiety: Current sustained anxiety level [0, 1].
            chronic_stress: Current chronic stress level [0, 1].

        Returns:
            Dict with vigilance_level, scanning_breadth, startle_sensitivity.
        """
        anxiety = float(np.clip(anxiety, 0.0, 1.0))
        chronic_stress = float(np.clip(chronic_stress, 0.0, 1.0))

        # Vigilance combines anxiety and chronic stress
        vigilance = self.vigilance_gain * (0.6 * anxiety + 0.4 * chronic_stress)
        vigilance = float(np.clip(vigilance, 0.0, 1.0))

        # High anxiety narrows scanning breadth (attentional tunnelling)
        scanning_breadth = 1.0 - 0.7 * anxiety
        scanning_breadth = float(np.clip(scanning_breadth, 0.1, 1.0))

        # Startle sensitivity enhanced by anxiety
        startle_sensitivity = 0.3 + 0.7 * anxiety
        startle_sensitivity = float(np.clip(startle_sensitivity, 0.0, 1.0))

        return {
            'vigilance_level': round(vigilance, 4),
            'scanning_breadth': round(scanning_breadth, 4),
            'startle_sensitivity': round(startle_sensitivity, 4),
        }


# ============================================================================
# Main Class
# ============================================================================

class BedNucleusStriaTerminalis:
    """
    Complete BNST module integrating sustained anxiety monitoring,
    chronic stress accumulation, uncertainty-based threat amplification,
    and vigilance control.

    Distinct from the amygdala module: the amygdala handles fast, phasic
    fear responses to clear threats, while the BNST handles slow, tonic
    anxiety responses to uncertain or prolonged threats.

    Usage:
        bnst = BedNucleusStriaTerminalis()
        result = bnst.process(threat_level=0.4, uncertainty=0.8, stressor_intensity=0.3)
        # result keys: anxiety_level, vigilance, chronic_stress, amplified_threat,
        #              scanning_breadth, startle_sensitivity, is_chronic_stress
    """

    def __init__(
        self,
        integration_rate: float = 0.05,
        decay_rate: float = 0.02,
        uncertainty_gain: float = 1.0,
        stress_threshold: float = 0.6,
        vigilance_gain: float = 1.0,
    ):
        self.integration_rate = integration_rate
        self.decay_rate = decay_rate
        self.uncertainty_gain = uncertainty_gain
        self.stress_threshold = stress_threshold
        self.vigilance_gain = vigilance_gain

        # Sub-components
        self.anxiety_monitor = SustainedAnxietyMonitor(
            integration_rate=integration_rate, decay_rate=decay_rate,
        )
        self.stress_accumulator = ChronicStressAccumulator(
            stress_threshold=stress_threshold,
        )
        self.threat_amplifier = UncertaintyThreatAmplifier(
            uncertainty_gain=uncertainty_gain,
        )
        self.vigilance_controller = VigilanceController(
            vigilance_gain=vigilance_gain,
        )

        # Running statistics
        self._stats = BNSTStats()
        self._anxiety_history: deque = deque(maxlen=200)
        self._vigilance_history: deque = deque(maxlen=200)

        logger.info(
            "BNST initialised — integration_rate=%.3f, uncertainty_gain=%.1f, "
            "stress_threshold=%.2f",
            integration_rate, uncertainty_gain, stress_threshold,
        )

    # ------------------------------------------------------------------ core
    def process(
        self,
        threat_level: float,
        uncertainty: float = 0.5,
        stressor_intensity: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Run one processing cycle.

        Args:
            threat_level: Current threat intensity [0, 1].
            uncertainty: Situational uncertainty [0, 1].
            stressor_intensity: Intensity of ongoing stressor [0, 1].

        Returns:
            Dict with anxiety_level, vigilance, chronic_stress, amplified_threat,
            scanning_breadth, startle_sensitivity, is_chronic_stress.
        """
        # 1. Amplify threat based on uncertainty
        amplified_threat = self.threat_amplifier.amplify(threat_level, uncertainty)

        # 2. Update sustained anxiety
        anxiety = self.anxiety_monitor.update(threat_level, uncertainty)

        # 3. Accumulate chronic stress
        stress_info = self.stress_accumulator.accumulate(stressor_intensity)

        # 4. Compute vigilance
        vig_info = self.vigilance_controller.compute_vigilance(
            anxiety, stress_info['stress_level'],
        )

        # Update internal bookkeeping
        self._anxiety_history.append(anxiety)
        self._vigilance_history.append(vig_info['vigilance_level'])
        self._stats.total_cycles += 1

        # Update running stats
        self._stats.avg_anxiety = float(np.mean(list(self._anxiety_history)))
        if anxiety > self._stats.peak_anxiety:
            self._stats.peak_anxiety = anxiety
        self._stats.chronic_stress_episodes = self.stress_accumulator.chronic_episodes
        self._stats.avg_vigilance = float(np.mean(list(self._vigilance_history)))

        logger.debug(
            "BNST cycle %d — anxiety=%.3f threat_amp=%.3f stress=%.3f vigilance=%.3f",
            self._stats.total_cycles, anxiety, amplified_threat,
            stress_info['stress_level'], vig_info['vigilance_level'],
        )

        return {
            'anxiety_level': round(anxiety, 4),
            'vigilance': round(vig_info['vigilance_level'], 4),
            'chronic_stress': round(stress_info['stress_level'], 4),
            'amplified_threat': round(amplified_threat, 4),
            'scanning_breadth': round(vig_info['scanning_breadth'], 4),
            'startle_sensitivity': round(vig_info['startle_sensitivity'], 4),
            'is_chronic_stress': stress_info['is_chronic'],
        }

    def sustained_vs_phasic_fear(self, threat_duration: float) -> Dict[str, Any]:
        """
        BNST vs amygdala fear response (Davis et al., 2010).

        The amygdala handles phasic fear (clear, immediate threat). BNST
        handles sustained anxiety (diffuse, uncertain, long-duration threat).
        This is the neural basis of the anxiety vs fear distinction.

        Args:
            threat_duration: How long the threat has persisted [0, 1]

        Returns:
            Dict with anxiety_dominance, bnst_activation, recommended_response
        """
        anxiety = self.anxiety_monitor.anxiety
        chronic = self.stress_accumulator.stress_level

        # BNST dominance increases with threat duration
        bnst_activation = min(1.0, threat_duration * 0.7 + anxiety * 0.3)

        # Amygdala dominance for acute threats
        amygdala_dominance = max(0.0, 1.0 - threat_duration)

        # Which system should lead?
        if bnst_activation > amygdala_dominance:
            primary_system = 'bnst_anxiety'
            recommended = 'vigilance_and_avoidance'
        else:
            primary_system = 'amygdala_fear'
            recommended = 'fight_or_flight'

        return {
            'bnst_activation': round(bnst_activation, 4),
            'amygdala_dominance': round(amygdala_dominance, 4),
            'primary_system': primary_system,
            'recommended_response': recommended,
            'chronic_stress': round(chronic, 4),
        }

    # --------------------------------------------------------- introspection
    def get_state(self) -> Dict[str, Any]:
        """Return current internal state snapshot."""
        return {
            'anxiety_level': round(self.anxiety_monitor.anxiety, 4),
            'chronic_stress': round(self.stress_accumulator.stress_level, 4),
            'resilience': round(self.stress_accumulator.resilience, 4),
            'total_cycles': self._stats.total_cycles,
            'peak_anxiety': round(self._stats.peak_anxiety, 4),
            'chronic_stress_episodes': self._stats.chronic_stress_episodes,
        }

    def get_stats(self) -> BNSTStats:
        """Return accumulated statistics."""
        return self._stats

    def to_dict(self) -> Dict[str, Any]:
        """Serialisable dictionary of state + stats."""
        return {
            'state': self.get_state(),
            'stats': self._stats.to_dict(),
            'anxiety_history': [round(v, 4) for v in list(self._anxiety_history)[-20:]],
            'vigilance_history': [round(v, 4) for v in list(self._vigilance_history)[-20:]],
        }

    # --------------------------------------------------------------- control
    def reset(self) -> None:
        """Reset all internal state (preserve config)."""
        self.anxiety_monitor.reset()
        self.stress_accumulator.reset()
        self._anxiety_history.clear()
        self._vigilance_history.clear()
        self._stats = BNSTStats()
        logger.info("BNST reset")

    # ------------------------------------------------------------ from_yaml
    @classmethod
    def from_yaml(cls, config: Dict[str, Any]) -> 'BedNucleusStriaTerminalis':
        """Construct from parsed YAML config dict."""
        bnst = config.get('bnst', {})
        return cls(
            integration_rate=bnst.get('integration_rate', 0.05),
            decay_rate=bnst.get('decay_rate', 0.02),
            uncertainty_gain=bnst.get('uncertainty_gain', 1.0),
            stress_threshold=bnst.get('stress_threshold', 0.6),
            vigilance_gain=bnst.get('vigilance_gain', 1.0),
        )

    def __repr__(self) -> str:
        return (
            f"BedNucleusStriaTerminalis(cycles={self._stats.total_cycles}, "
            f"anxiety={self._stats.avg_anxiety:.3f})"
        )
