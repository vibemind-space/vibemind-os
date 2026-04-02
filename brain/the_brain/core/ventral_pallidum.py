"""
Ventral Pallidum (VP) — Limbic Basal-Ganglia Output and Hedonic Hotspot

Primary limbic output nucleus of the basal ganglia.  Implements:
1. Hedonic "liking" hotspot — opioid-mediated pleasure amplification
2. Reward evaluation via convergence of wanting (dopamine) and liking (opioid)
3. Limbic-to-motor output conversion for approach/consummatory behaviour
4. Integration of inhibitory control over reward-driven motor output

References:
    - Smith et al. (2009): VP as hedonic "liking" hotspot (with NAc shell)
    - Berridge & Kringelbach (2015): Pleasure systems in the brain
    - Smith & Berridge (2007): Opioid limbic circuit for reward
    - Tachibana & Hikosaka (2012): VP role in reward-based eye movements
"""

import logging
import numpy as np
from typing import Dict, Any
from dataclasses import dataclass
from collections import deque

logger = logging.getLogger('brain.ventral_pallidum')


# ============================================================================
# Stats Dataclass
# ============================================================================

@dataclass
class VentralPallidumStats:
    """Accumulated statistics for the ventral pallidum module."""
    total_cycles: int = 0
    avg_liking: float = 0.0
    avg_wanting: float = 0.0
    hedonic_peaks: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_cycles': self.total_cycles,
            'avg_liking': round(self.avg_liking, 4),
            'avg_wanting': round(self.avg_wanting, 4),
            'hedonic_peaks': self.hedonic_peaks,
        }


# ============================================================================
# Sub-component Classes
# ============================================================================

class HedonicHotspot:
    """
    Computes hedonic "liking" response.

    The ventral pallidum (together with the NAc shell) contains
    opioid-sensitive hotspots where mu-opioid stimulation amplifies
    the hedonic impact of rewards.  Higher opioid tone => stronger
    pleasure amplification of incoming reward signals.
    """

    def __init__(self, liking_gain: float = 1.0):
        self.liking_gain = max(liking_gain, 0.1)

    def compute_liking(
        self,
        reward_signal: float,
        opioid_level: float,
    ) -> Dict[str, Any]:
        """Compute hedonic liking response.

        Returns dict with liking_response, hedonic_value,
        pleasure_amplification.
        """
        reward = float(np.clip(reward_signal, 0.0, 1.0))
        opioid = float(np.clip(opioid_level, 0.0, 1.0))

        # Pleasure amplification: opioid-dependent multiplicative gain
        pleasure_amplification = 1.0 + self.liking_gain * opioid
        hedonic_value = float(np.clip(reward * pleasure_amplification, 0.0, 1.0))

        # Overall liking response (saturating)
        liking_response = float(np.clip(
            hedonic_value * (0.5 + 0.5 * opioid), 0.0, 1.0,
        ))

        return {
            'liking_response': liking_response,
            'hedonic_value': hedonic_value,
            'pleasure_amplification': round(pleasure_amplification, 4),
        }


class LimbicMotorOutput:
    """
    Converts limbic evaluation into motor output signals.

    Combines hedonic "liking" with dopaminergic "wanting" to produce
    approach and consummatory motor drives, subject to inhibitory
    control from prefrontal or pallidal sources.
    """

    def __init__(self, motor_threshold: float = 0.3):
        self.motor_threshold = np.clip(motor_threshold, 0.05, 0.8)

    def compute_output(
        self,
        liking: float,
        wanting: float,
        inhibition: float,
    ) -> Dict[str, Any]:
        """Compute limbic motor output.

        Returns dict with motor_output, approach_strength,
        consummatory_drive.
        """
        liking = float(np.clip(liking, 0.0, 1.0))
        wanting = float(np.clip(wanting, 0.0, 1.0))
        inhibition = float(np.clip(inhibition, 0.0, 1.0))

        # Approach strength driven by wanting, tempered by inhibition
        approach_raw = wanting * (1.0 - 0.8 * inhibition)
        approach_strength = float(np.clip(approach_raw, 0.0, 1.0))

        # Consummatory drive driven by liking, tempered by inhibition
        consum_raw = liking * (1.0 - 0.6 * inhibition)
        consummatory_drive = float(np.clip(consum_raw, 0.0, 1.0))

        # Combined motor output
        combined = 0.6 * approach_strength + 0.4 * consummatory_drive
        motor_output = float(np.clip(combined, 0.0, 1.0))

        # Suppress below threshold
        if motor_output < self.motor_threshold:
            motor_output = 0.0

        return {
            'motor_output': motor_output,
            'approach_strength': approach_strength,
            'consummatory_drive': consummatory_drive,
        }


# ============================================================================
# Main Class
# ============================================================================

class VentralPallidum:
    """
    Complete Ventral Pallidum module integrating hedonic hotspot
    evaluation with limbic motor output.

    Usage:
        vp = VentralPallidum()
        result = vp.process(reward_signal=0.7, opioid_level=0.6,
                            wanting_signal=0.5)
        # result keys: liking, motor, opioid_level, wanting_signal
    """

    def __init__(
        self,
        opioid_baseline: float = 0.5,
        liking_gain: float = 1.0,
        motor_threshold: float = 0.3,
    ):
        self.opioid_baseline = float(np.clip(opioid_baseline, 0.0, 1.0))

        # Sub-components
        self.hotspot = HedonicHotspot(liking_gain=liking_gain)
        self.motor_output = LimbicMotorOutput(motor_threshold=motor_threshold)

        # Running statistics
        self._stats = VentralPallidumStats()
        self._liking_history: deque = deque(maxlen=200)
        self._wanting_history: deque = deque(maxlen=200)
        self._last_output: Dict[str, Any] = {}

        # Hedonic peak detection
        self._peak_threshold: float = 0.8

        logger.info(
            "VentralPallidum initialised — opioid_baseline=%.2f, "
            "liking_gain=%.2f, motor_thresh=%.2f",
            self.opioid_baseline, liking_gain, motor_threshold,
        )

    # ------------------------------------------------------------------ core
    def process(
        self,
        reward_signal: float = 0.0,
        opioid_level: float = 0.5,
        wanting_signal: float = 0.5,
        inhibition: float = 0.0,
    ) -> Dict[str, Any]:
        """Run one cycle of VP processing.

        Returns dict with liking (sub-dict), motor (sub-dict),
        opioid_level, wanting_signal.
        """
        opioid = float(np.clip(opioid_level, 0.0, 1.0))
        wanting = float(np.clip(wanting_signal, 0.0, 1.0))

        # Hedonic evaluation
        liking = self.hotspot.compute_liking(reward_signal, opioid)

        # Limbic-motor conversion
        motor = self.motor_output.compute_output(
            liking=liking['liking_response'],
            wanting=wanting,
            inhibition=inhibition,
        )

        # Update bookkeeping
        self._liking_history.append(liking['liking_response'])
        self._wanting_history.append(wanting)
        self._stats.total_cycles += 1
        self._stats.avg_liking = float(np.mean(list(self._liking_history)))
        self._stats.avg_wanting = float(np.mean(list(self._wanting_history)))

        if liking['hedonic_value'] > self._peak_threshold:
            self._stats.hedonic_peaks += 1

        self._last_output = {
            'liking': liking,
            'motor': motor,
            'opioid_level': opioid,
            'wanting_signal': wanting,
        }

        logger.debug(
            "VP cycle %d — liking=%.3f wanting=%.3f motor=%.3f",
            self._stats.total_cycles,
            liking['liking_response'], wanting, motor['motor_output'],
        )

        return dict(self._last_output)

    def hedonic_hotspot_response(self, opioid_level: float, da_level: float) -> Dict[str, float]:
        """
        Hedonic hotspot computation (Berridge & Kringelbach, 2015).

        VP contains a hedonic hotspot where opioid stimulation amplifies
        'liking' reactions. DA in VP amplifies 'wanting' but not 'liking'.
        This double dissociation is key to understanding pleasure vs desire.

        Args:
            opioid_level: Endogenous opioid level [0, 1]
            da_level: Dopamine level in VP [0, 1]

        Returns:
            Dict with liking_amplification, wanting_amplification, hedonic_impact
        """
        # Opioids amplify liking (hedonic impact)
        liking_amp = min(2.0, 1.0 + opioid_level * 1.5)

        # DA amplifies wanting (incentive salience) but NOT liking
        wanting_amp = min(2.0, 1.0 + da_level * 1.2)

        # Hedonic impact = base pleasure * liking amplification
        hedonic_impact = min(1.0, opioid_level * liking_amp * 0.5)

        return {
            'liking_amplification': round(liking_amp, 4),
            'wanting_amplification': round(wanting_amp, 4),
            'hedonic_impact': round(hedonic_impact, 4),
            'wanting_without_liking': da_level > 0.5 and opioid_level < 0.2,
        }

    # --------------------------------------------------------- introspection
    def get_state(self) -> Dict[str, Any]:
        """Return current internal state snapshot."""
        return {
            'avg_liking': self._stats.avg_liking,
            'avg_wanting': self._stats.avg_wanting,
            'hedonic_peaks': self._stats.hedonic_peaks,
            'total_cycles': self._stats.total_cycles,
            'last_output': self._last_output,
        }

    def get_stats(self) -> VentralPallidumStats:
        """Return accumulated statistics."""
        return self._stats

    def to_dict(self) -> Dict[str, Any]:
        """Serialisable dictionary of state + stats."""
        return {
            'state': self.get_state(),
            'stats': self._stats.to_dict(),
            'liking_history': [round(v, 4) for v in list(self._liking_history)[-20:]],
            'wanting_history': [round(v, 4) for v in list(self._wanting_history)[-20:]],
        }

    # --------------------------------------------------------------- control
    def reset(self) -> None:
        """Reset all internal state (preserve config)."""
        self._liking_history.clear()
        self._wanting_history.clear()
        self._last_output = {}
        self._stats = VentralPallidumStats()
        logger.info("VentralPallidum reset")

    # ------------------------------------------------------------ from_yaml
    @classmethod
    def from_yaml(cls, config: Dict[str, Any]) -> 'VentralPallidum':
        """Construct from parsed YAML config dict."""
        vp = config.get('ventral_pallidum', {})
        return cls(
            opioid_baseline=vp.get('opioid_baseline', 0.5),
            liking_gain=vp.get('liking_gain', 1.0),
            motor_threshold=vp.get('motor_threshold', 0.3),
        )

    def __repr__(self) -> str:
        return (
            f"VentralPallidum(cycles={self._stats.total_cycles}, "
            f"liking={self._stats.avg_liking:.3f})"
        )
