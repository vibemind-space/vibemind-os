"""
Locus Coeruleus (LC) Module - Phase D3

The LC is a small brainstem nucleus that is the SOLE source of
norepinephrine (NE) in the brain. It projects to virtually every
brain region and controls arousal, attention, and the explore/exploit
tradeoff through adaptive gain modulation.

Neuroscience basis:
- Aston-Jones & Cohen (2005): Adaptive Gain Theory
  * Tonic mode (high baseline NE): Broad, unfocused attention.
    Promotes exploration, scanning for new opportunities.
    Activated when task performance degrades.
  * Phasic mode (low baseline, sharp bursts): Focused attention.
    Promotes exploitation of known strategies.
    Activated when performing well on current task.
- NE multiplies signal-to-noise ratio in target circuits
- LC responds to: novelty, stress, pain, salience, ACC conflict signals

Key functions:
- Arousal level regulation
- Explore/exploit tradeoff control
- Adaptive gain modulation (signal-to-noise ratio)
- Network reset (phasic burst resets cortical state)
- Stress response amplification

Integration:
- Input: ACC (conflict), amygdala (threat), PAG (pain), PFC (task demands)
- Output: LC -> everywhere (cortex, hippocampus, amygdala, cerebellum, thalamus)
"""

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

import numpy as np

logger = logging.getLogger('brain.locus_coeruleus')


@dataclass
class LCStats:
    """Locus Coeruleus statistics."""
    total_cycles: int = 0
    time_in_tonic: int = 0
    time_in_phasic: int = 0
    total_resets: int = 0
    avg_ne_level: float = 0.5
    avg_arousal: float = 0.5
    explore_exploit_ratio: float = 0.5  # 0=pure exploit, 1=pure explore

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_cycles': self.total_cycles,
            'time_in_tonic': self.time_in_tonic,
            'time_in_phasic': self.time_in_phasic,
            'total_resets': self.total_resets,
            'avg_ne_level': round(self.avg_ne_level, 3),
            'avg_arousal': round(self.avg_arousal, 3),
            'explore_exploit_ratio': round(self.explore_exploit_ratio, 3),
        }


class AdaptiveGainController:
    """
    Implements the Adaptive Gain Theory (Aston-Jones & Cohen, 2005).

    NE acts as a gain multiplier on neural processing:
    - High gain (phasic): sharpens responses, narrows focus
    - Low gain (tonic): flattens responses, broadens processing

    The gain level is adapted based on task performance:
    - Good performance -> phasic mode (exploit)
    - Poor performance -> tonic mode (explore)
    """

    def __init__(
        self,
        tonic_baseline: float = 0.5,
        performance_threshold: float = 0.6,
        adaptation_rate: float = 0.05,
    ):
        self.tonic_baseline = tonic_baseline
        self.performance_threshold = performance_threshold
        self.adaptation_rate = adaptation_rate

        self._current_gain = 1.0
        self._mode = 'balanced'  # 'tonic', 'phasic', 'balanced'
        self._performance_history = deque(maxlen=50)

    def update_gain(self, task_performance: float) -> Dict[str, Any]:
        """
        Update gain based on task performance.

        Args:
            task_performance: Current task performance [0, 1]
                0 = terrible, 1 = perfect

        Returns:
            Dict with mode, gain, ne_baseline
        """
        self._performance_history.append(task_performance)
        avg_performance = float(np.mean(list(self._performance_history)))

        if avg_performance > self.performance_threshold:
            # Good performance -> phasic mode (exploit)
            target_gain = 1.5  # High gain, sharp focus
            self._mode = 'phasic'
        elif avg_performance < self.performance_threshold - 0.2:
            # Poor performance -> tonic mode (explore)
            target_gain = 0.5  # Low gain, broad scanning
            self._mode = 'tonic'
        else:
            # Intermediate -> balanced
            target_gain = 1.0
            self._mode = 'balanced'

        # Gradual adaptation
        self._current_gain += self.adaptation_rate * (target_gain - self._current_gain)
        self._current_gain = max(0.2, min(2.0, self._current_gain))

        return {
            'mode': self._mode,
            'gain': self._current_gain,
            'avg_performance': avg_performance,
        }

    def apply_gain(self, signal: np.ndarray) -> np.ndarray:
        """
        Apply gain modulation to a signal.

        High gain amplifies differences (exploitation).
        Low gain flattens signal (exploration).
        """
        signal = np.asarray(signal, dtype=np.float32)
        mean = np.mean(signal) if len(signal) > 0 else 0.0
        # Gain modulates deviation from mean
        modulated = mean + (signal - mean) * self._current_gain
        return modulated

    @property
    def current_gain(self) -> float:
        return self._current_gain

    @property
    def mode(self) -> str:
        return self._mode

    def to_dict(self) -> Dict[str, Any]:
        return {
            'gain': round(self._current_gain, 3),
            'mode': self._mode,
        }


class ArousalRegulator:
    """
    Controls arousal level based on NE release.

    Arousal is a global state variable that affects:
    - Processing speed
    - Sensitivity to stimuli
    - Memory encoding strength
    - Decision threshold

    Yerkes-Dodson law: optimal performance at intermediate arousal.
    """

    def __init__(self, optimal_arousal: float = 0.6):
        self.optimal_arousal = optimal_arousal
        self._arousal = 0.5
        self._arousal_history = deque(maxlen=100)

    def update_arousal(
        self,
        ne_level: float,
        stress: float = 0.0,
        threat: float = 0.0,
    ) -> float:
        """
        Update arousal based on NE and stress inputs.

        Args:
            ne_level: Norepinephrine level [0, 1]
            stress: Stress signal from HPA axis [0, 1]
            threat: Threat signal from amygdala [0, 1]

        Returns:
            Current arousal level [0, 1]
        """
        # Arousal = weighted combination
        raw_arousal = ne_level * 0.5 + stress * 0.3 + threat * 0.2
        raw_arousal = min(1.0, max(0.0, raw_arousal))

        # Smooth update
        self._arousal = self._arousal * 0.7 + raw_arousal * 0.3
        self._arousal_history.append(self._arousal)

        return self._arousal

    def get_performance_modifier(self) -> float:
        """
        Get performance modifier based on Yerkes-Dodson law.

        Returns ~1.0 at optimal arousal, lower at extremes.
        """
        distance = abs(self._arousal - self.optimal_arousal)
        modifier = 1.0 - distance * 1.5
        return max(0.3, min(1.0, modifier))

    @property
    def arousal(self) -> float:
        return self._arousal

    def to_dict(self) -> Dict[str, Any]:
        return {
            'arousal': round(self._arousal, 3),
            'performance_modifier': round(self.get_performance_modifier(), 3),
            'optimal': self.optimal_arousal,
        }


class NetworkResetSignal:
    """
    Phasic NE burst as a cortical reset signal.

    A strong phasic LC burst resets cortical processing state,
    allowing the brain to shift to processing a new event.
    This is critical for rapid attention switching.
    """

    def __init__(self, reset_threshold: float = 0.7, refractory_period: int = 5):
        self.reset_threshold = reset_threshold
        self.refractory_period = refractory_period
        self._cycles_since_reset = refractory_period
        self._total_resets = 0

    def check_reset(self, phasic_burst: float) -> bool:
        """
        Check if a phasic burst triggers a network reset.

        Args:
            phasic_burst: Magnitude of phasic NE burst [0, 1]

        Returns:
            True if reset is triggered
        """
        self._cycles_since_reset += 1

        if (phasic_burst > self.reset_threshold and
                self._cycles_since_reset >= self.refractory_period):
            self._cycles_since_reset = 0
            self._total_resets += 1
            logger.debug(f"Network reset triggered (burst={phasic_burst:.2f})")
            return True

        return False

    @property
    def total_resets(self) -> int:
        return self._total_resets


class LocusCoeruleus:
    """
    Complete Locus Coeruleus module.

    Functions:
    1. Adaptive gain control (explore/exploit)
    2. Arousal regulation (Yerkes-Dodson)
    3. NE signal generation and distribution
    4. Network reset via phasic bursts
    5. Stress and threat response amplification

    This is THE explore/exploit controller for Tahlamus.
    """

    def __init__(
        self,
        tonic_baseline: float = 0.5,
        performance_threshold: float = 0.6,
        adaptation_rate: float = 0.05,
        optimal_arousal: float = 0.6,
        reset_threshold: float = 0.7,
    ):
        self.gain_controller = AdaptiveGainController(
            tonic_baseline, performance_threshold, adaptation_rate
        )
        self.arousal_regulator = ArousalRegulator(optimal_arousal)
        self.reset_signal = NetworkResetSignal(reset_threshold)
        self._stats = LCStats()
        self._ne_level = tonic_baseline
        self._ne_history = deque(maxlen=200)

    def process(
        self,
        task_performance: float = 0.5,
        stress: float = 0.0,
        threat: float = 0.0,
        novelty: float = 0.0,
        conflict: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Full LC processing cycle.

        1. Update adaptive gain based on performance
        2. Compute NE level from multiple inputs
        3. Update arousal
        4. Check for network reset
        5. Return NE output for all target regions

        Args:
            task_performance: Current task performance [0, 1]
            stress: HPA axis stress signal [0, 1]
            threat: Amygdala threat signal [0, 1]
            novelty: Stimulus novelty [0, 1]
            conflict: ACC conflict signal [0, 1]

        Returns:
            Dict with NE level, gain, arousal, mode, reset
        """
        # 1. Update gain based on performance
        gain_state = self.gain_controller.update_gain(task_performance)

        # 2. Compute NE level
        # Base NE from gain mode
        if gain_state['mode'] == 'tonic':
            base_ne = 0.7  # High tonic = exploration
        elif gain_state['mode'] == 'phasic':
            base_ne = 0.3  # Low tonic, sharp phasic bursts
        else:
            base_ne = 0.5

        # Stress and threat boost NE
        ne_boost = stress * 0.3 + threat * 0.3 + novelty * 0.2 + conflict * 0.2
        self._ne_level = base_ne + ne_boost
        self._ne_level = min(1.0, max(0.0, self._ne_level))
        self._ne_history.append(self._ne_level)

        # 3. Update arousal
        arousal = self.arousal_regulator.update_arousal(
            self._ne_level, stress, threat
        )

        # 4. Check for network reset (phasic burst = high NE spike)
        phasic_burst = max(0, self._ne_level - 0.6)
        network_reset = self.reset_signal.check_reset(phasic_burst)

        # 5. Explore/exploit ratio
        explore_ratio = 1.0 - gain_state['gain'] / 2.0  # Higher gain = more exploit
        explore_ratio = max(0.0, min(1.0, explore_ratio))

        # Update stats
        self._stats.total_cycles += 1
        if gain_state['mode'] == 'tonic':
            self._stats.time_in_tonic += 1
        elif gain_state['mode'] == 'phasic':
            self._stats.time_in_phasic += 1
        if network_reset:
            self._stats.total_resets += 1
        self._stats.avg_ne_level = float(np.mean(list(self._ne_history)))
        self._stats.avg_arousal = arousal
        self._stats.explore_exploit_ratio = explore_ratio

        return {
            'ne_level': round(self._ne_level, 3),
            'gain': round(gain_state['gain'], 3),
            'mode': gain_state['mode'],
            'arousal': round(arousal, 3),
            'performance_modifier': round(
                self.arousal_regulator.get_performance_modifier(), 3
            ),
            'explore_ratio': round(explore_ratio, 3),
            'network_reset': network_reset,
        }


    def target_gain_modulation(self, regions: Optional[Dict[str, float]] = None) -> Dict[str, float]:
        """
        Compute target-specific NE gain modulation (Berridge & Waterhouse 2003).

        Different brain regions receive different NE modulation:
        - PFC: Inverted-U (moderate NE optimal, high NE impairs)
        - Sensory cortex: Monotonic gain increase
        - Amygdala: Enhanced threat detection at high NE
        - Hippocampus: Memory encoding boost at moderate NE

        The LC broadcasts NE globally, but receptor density and subtype
        distribution create region-specific effects.

        Args:
            regions: Optional dict of {region_name: baseline_activity}.
                     If None, uses default region set.

        Returns:
            Dict of {region_name: gain_multiplier}
        """
        ne = self._ne_level
        gain = self.gain_controller.current_gain

        # PFC: inverted-U — optimal at moderate NE, impaired at high
        pfc_gain = 1.0 - 2.0 * (ne - 0.5) ** 2  # peaks at ne=0.5
        pfc_gain = max(0.3, min(1.2, pfc_gain))

        # Sensory cortex: monotonic — higher NE = sharper responses
        sensory_gain = 0.5 + ne * 0.8
        sensory_gain = max(0.3, min(1.5, sensory_gain))

        # Amygdala: enhanced at high NE (threat sensitivity)
        amygdala_gain = 0.6 + ne * 0.6
        amygdala_gain = max(0.4, min(1.4, amygdala_gain))

        # Hippocampus: moderate NE best for encoding, high NE impairs retrieval
        hippo_gain = 1.0 - 1.5 * (ne - 0.4) ** 2
        hippo_gain = max(0.3, min(1.1, hippo_gain))

        # Cerebellum: modest modulation
        cerebellum_gain = 0.8 + ne * 0.3
        cerebellum_gain = max(0.7, min(1.2, cerebellum_gain))

        result = {
            'pfc': round(pfc_gain, 3),
            'sensory_cortex': round(sensory_gain, 3),
            'amygdala': round(amygdala_gain, 3),
            'hippocampus': round(hippo_gain, 3),
            'cerebellum': round(cerebellum_gain, 3),
        }

        # If custom regions provided, apply global gain to them
        if regions:
            for region, baseline in regions.items():
                if region not in result:
                    # Default: linear gain modulation
                    result[region] = round(max(0.3, min(1.5, baseline * gain)), 3)

        return result

    @property
    def pupil_proxy(self) -> float:
        """
        Simulated pupil diameter as LC activity proxy (Joshi et al. 2016).

        LC-NE activity correlates strongly with pupil dilation.
        This provides an observable readout of arousal state:
        - Small pupil (< 0.3): Low arousal, drowsy/disengaged
        - Medium pupil (0.3-0.6): Alert, focused (phasic mode)
        - Large pupil (> 0.6): High arousal, stressed/exploring (tonic mode)

        Returns:
            Simulated pupil diameter [0, 1]
        """
        # Pupil tracks NE level with slight nonlinearity (log-like)
        ne = self._ne_level
        pupil = 0.2 + 0.8 * (1.0 - np.exp(-2.5 * ne))
        return round(float(min(1.0, max(0.0, pupil))), 3)

    def utility_driven_mode_switch(
        self,
        current_task_utility: float,
        alternative_utility: float = 0.0,
        switch_cost: float = 0.1,
    ) -> Dict[str, Any]:
        """
        Utility-based explore/exploit mode switching (Aston-Jones & Cohen, 2005).

        The LC switches from phasic (exploit) to tonic (explore) mode when
        the utility of the current task drops below alternatives minus
        switching cost. This is the mechanistic basis for task disengagement.

        Args:
            current_task_utility: Utility of continuing current task [0, 1]
            alternative_utility: Estimated utility of switching [0, 1]
            switch_cost: Cost of switching tasks [0, 1]

        Returns:
            Dict with should_switch, utility_difference, recommended_mode
        """
        net_alternative = alternative_utility - switch_cost
        utility_diff = net_alternative - current_task_utility

        if utility_diff > 0.15:
            recommended = 'tonic'
            should_switch = True
        elif utility_diff < -0.15:
            recommended = 'phasic'
            should_switch = False
        else:
            recommended = 'balanced'
            should_switch = False

        return {
            'should_switch': should_switch,
            'utility_difference': round(utility_diff, 4),
            'current_utility': round(current_task_utility, 4),
            'alternative_utility': round(net_alternative, 4),
            'recommended_mode': recommended,
        }

    def compute_ne_snr_effect(
        self,
        signal_strength: float,
        noise_level: float,
    ) -> Dict[str, float]:
        """
        NE effect on signal-to-noise ratio in target circuits.

        Servan-Schreiber et al. (1990): NE increases the gain of neural
        responses, effectively boosting signal relative to noise. This is
        the computational mechanism for how arousal sharpens cognition.

        Args:
            signal_strength: Strength of the target signal [0, 1]
            noise_level: Background noise level [0, 1]

        Returns:
            Dict with enhanced signal, noise, and SNR
        """
        gain = self.gain_controller.current_gain
        ne = self._ne_level

        # NE boosts signal more than noise (gain modulation)
        enhanced_signal = signal_strength * (1.0 + gain * ne * 0.5)
        enhanced_noise = noise_level * (1.0 + gain * ne * 0.15)

        snr = enhanced_signal / max(0.01, enhanced_noise)

        return {
            'enhanced_signal': round(min(2.0, enhanced_signal), 4),
            'enhanced_noise': round(min(1.0, enhanced_noise), 4),
            'snr': round(snr, 4),
            'gain_applied': round(gain, 4),
        }

    def apply_gain_modulation(self, signal: np.ndarray) -> np.ndarray:
        """Apply adaptive gain to any signal vector."""
        return self.gain_controller.apply_gain(signal)

    @property
    def ne_level(self) -> float:
        return self._ne_level

    @property
    def mode(self) -> str:
        return self.gain_controller.mode

    def get_state(self) -> Dict[str, Any]:
        return {
            'stats': self._stats.to_dict(),
            'gain': self.gain_controller.to_dict(),
            'arousal': self.arousal_regulator.to_dict(),
        }

    def get_stats(self) -> LCStats:
        return self._stats

    def reset(self):
        self._stats = LCStats()

    def to_dict(self) -> Dict[str, Any]:
        return self.get_state()

    @classmethod
    def from_yaml(cls, config: Dict[str, Any]) -> 'LocusCoeruleus':
        cfg = config.get('locus_coeruleus', {})
        return cls(
            tonic_baseline=cfg.get('tonic_baseline', 0.5),
            performance_threshold=cfg.get('performance_threshold', 0.6),
            adaptation_rate=cfg.get('adaptation_rate', 0.05),
            optimal_arousal=cfg.get('optimal_arousal', 0.6),
            reset_threshold=cfg.get('reset_threshold', 0.7),
        )
