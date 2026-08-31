"""
Pedunculopontine / Laterodorsal Tegmental Nuclei (PPN/LDT) — Cholinergic Brainstem Control

Cholinergic brainstem nuclei at the junction of midbrain and pons.  Implements:
1. Locomotion initiation via descending drive to spinal pattern generators
2. REM sleep generation through cholinergic bursting
3. Arousal modulation via ascending reticular projections
4. Gait control in coordination with basal ganglia output

References:
    - Garcia-Rill (1991): PPN and locomotion / REM sleep generation
    - Takakusaki et al. (2004): PPN role in postural-locomotor synergies
    - Mena-Segovia et al. (2004): PPN–basal ganglia interactions
    - Pahapill & Lozano (2000): PPN deep-brain stimulation for gait disorders
"""

import logging
import numpy as np
from typing import Dict, Any
from dataclasses import dataclass
from collections import deque

logger = logging.getLogger('brain.ppn')


# ============================================================================
# Stats Dataclass
# ============================================================================

@dataclass
class PPNStats:
    """Accumulated statistics for the PPN module."""
    total_cycles: int = 0
    locomotion_initiations: int = 0
    rem_episodes: int = 0
    avg_cholinergic_tone: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_cycles': self.total_cycles,
            'locomotion_initiations': self.locomotion_initiations,
            'rem_episodes': self.rem_episodes,
            'avg_cholinergic_tone': round(self.avg_cholinergic_tone, 4),
        }


# ============================================================================
# Sub-component Classes
# ============================================================================

class LocomotionInitiator:
    """
    Controls movement initiation by combining volitional intention with
    basal-ganglia disinhibition.  When the globus pallidus releases its
    tonic inhibition (bg_release high), and there is sufficient cortical
    movement intention, the PPN generates a descending locomotion drive
    and gait-initiation signal.
    """

    def __init__(self, threshold: float = 0.4):
        self.threshold = np.clip(threshold, 0.1, 0.9)

    def initiate(
        self,
        movement_intention: float,
        bg_release: float,
    ) -> Dict[str, Any]:
        """Compute locomotion drive from intention and BG release.

        Returns dict with locomotion_drive, gait_signal,
        initiation_threshold_met.
        """
        intention = float(np.clip(movement_intention, 0.0, 1.0))
        release = float(np.clip(bg_release, 0.0, 1.0))

        # Drive = product of cortical intention and BG release
        locomotion_drive = float(np.clip(intention * release, 0.0, 1.0))

        # Gait signal ramps up once drive exceeds threshold
        if locomotion_drive > self.threshold:
            gait_signal = float(np.clip(
                (locomotion_drive - self.threshold) / (1.0 - self.threshold),
                0.0, 1.0,
            ))
        else:
            gait_signal = 0.0

        threshold_met = locomotion_drive > self.threshold

        return {
            'locomotion_drive': locomotion_drive,
            'gait_signal': gait_signal,
            'initiation_threshold_met': threshold_met,
        }


class REMController:
    """
    REM sleep generation through cholinergic bursting.

    High sleep pressure combined with low arousal and sufficient
    cholinergic tone triggers REM episodes characterised by cortical
    activation, rapid eye movements, and muscle atonia.
    """

    def __init__(self, rem_threshold: float = 0.6):
        self.rem_threshold = np.clip(rem_threshold, 0.2, 0.95)

    def compute_rem(
        self,
        arousal: float,
        sleep_pressure: float,
        cholinergic_tone: float,
    ) -> Dict[str, Any]:
        """Compute REM probability and associated outputs.

        Returns dict with rem_probability, cholinergic_burst,
        muscle_atonia.
        """
        arousal = float(np.clip(arousal, 0.0, 1.0))
        pressure = float(np.clip(sleep_pressure, 0.0, 1.0))
        ach_tone = float(np.clip(cholinergic_tone, 0.0, 1.0))

        # REM probability rises with sleep pressure and ACh tone,
        # falls with arousal (wakefulness suppresses REM)
        rem_raw = pressure * ach_tone * (1.0 - 0.7 * arousal)
        rem_probability = float(np.clip(rem_raw, 0.0, 1.0))

        # Cholinergic burst occurs when rem exceeds threshold
        in_rem = rem_probability > self.rem_threshold
        cholinergic_burst = float(np.clip(
            rem_probability * 1.5, 0.0, 1.0,
        )) if in_rem else 0.0

        # Muscle atonia accompanies REM
        muscle_atonia = float(np.clip(
            rem_probability * 1.2, 0.0, 1.0,
        )) if in_rem else 0.0

        return {
            'rem_probability': rem_probability,
            'cholinergic_burst': cholinergic_burst,
            'muscle_atonia': muscle_atonia,
        }


# ============================================================================
# Main Class
# ============================================================================

class PedunculopontineNucleus:
    """
    Complete PPN/LDT module integrating locomotion initiation, REM sleep
    generation, and arousal-linked cholinergic tone.

    Usage:
        ppn = PedunculopontineNucleus()
        result = ppn.process(movement_intention=0.7, bg_release=0.8)
        # result keys: cholinergic_tone, locomotion, rem, arousal_output
    """

    def __init__(
        self,
        cholinergic_baseline: float = 0.5,
        locomotion_threshold: float = 0.4,
        rem_threshold: float = 0.6,
    ):
        self.cholinergic_baseline = float(np.clip(cholinergic_baseline, 0.1, 0.9))

        # Sub-components
        self.locomotion = LocomotionInitiator(threshold=locomotion_threshold)
        self.rem_controller = REMController(rem_threshold=rem_threshold)

        # Running statistics
        self._stats = PPNStats()
        self._ach_history: deque = deque(maxlen=200)
        self._last_output: Dict[str, Any] = {}

        logger.info(
            "PPN initialised — ACh baseline=%.2f, loco_thresh=%.2f, rem_thresh=%.2f",
            self.cholinergic_baseline, locomotion_threshold, rem_threshold,
        )

    # ------------------------------------------------------------------ core
    def process(
        self,
        movement_intention: float = 0.0,
        bg_release: float = 0.5,
        arousal: float = 0.5,
        sleep_pressure: float = 0.0,
    ) -> Dict[str, Any]:
        """Run one cycle of PPN processing.

        Returns dict with cholinergic_tone, locomotion (sub-dict),
        rem (sub-dict), arousal_output.
        """
        arousal = float(np.clip(arousal, 0.0, 1.0))
        sleep_pressure = float(np.clip(sleep_pressure, 0.0, 1.0))

        # Cholinergic tone: baseline modulated by arousal
        ach_tone = float(np.clip(
            self.cholinergic_baseline * (0.6 + 0.4 * arousal),
            0.0, 1.0,
        ))

        # Locomotion
        loco = self.locomotion.initiate(movement_intention, bg_release)

        # REM sleep
        rem = self.rem_controller.compute_rem(arousal, sleep_pressure, ach_tone)

        # Ascending arousal output from PPN
        arousal_output = float(np.clip(ach_tone * 0.8 + 0.2 * arousal, 0.0, 1.0))

        # Update bookkeeping
        self._ach_history.append(ach_tone)
        self._stats.total_cycles += 1

        if loco['initiation_threshold_met']:
            self._stats.locomotion_initiations += 1

        if rem['rem_probability'] > self.rem_controller.rem_threshold:
            self._stats.rem_episodes += 1

        self._stats.avg_cholinergic_tone = float(np.mean(list(self._ach_history)))

        self._last_output = {
            'cholinergic_tone': ach_tone,
            'locomotion': loco,
            'rem': rem,
            'arousal_output': arousal_output,
        }

        logger.debug(
            "PPN cycle %d — ACh=%.3f loco_drive=%.3f rem_prob=%.3f",
            self._stats.total_cycles, ach_tone,
            loco['locomotion_drive'], rem['rem_probability'],
        )

        return dict(self._last_output)

    def locomotion_initiation_signal(self, motivation: float, threat: float = 0.0) -> Dict[str, float]:
        """
        Locomotion initiation (Takakusaki et al., 2004).

        PPN contains the mesencephalic locomotor region — stimulation
        above threshold initiates locomotion. It integrates motivation
        (approach) and threat (escape) signals to trigger movement.

        Args:
            motivation: Motivation to move/approach [0, 1]
            threat: Threat-driven escape urgency [0, 1]

        Returns:
            Dict with locomotion_drive, should_initiate, speed_command
        """
        drive = max(motivation, threat * 1.2)
        drive = min(1.0, drive)

        # Threshold for locomotion initiation
        should_initiate = drive > 0.4

        # Speed: proportional to drive above threshold
        speed = max(0.0, (drive - 0.4) / 0.6) if should_initiate else 0.0

        return {
            'locomotion_drive': round(drive, 4),
            'should_initiate': should_initiate,
            'speed_command': round(min(1.0, speed), 4),
            'drive_source': 'threat' if threat > motivation else 'motivation',
        }

    # --------------------------------------------------------- introspection
    def get_state(self) -> Dict[str, Any]:
        """Return current internal state snapshot."""
        return {
            'cholinergic_tone': float(self._ach_history[-1]) if self._ach_history else self.cholinergic_baseline,
            'total_cycles': self._stats.total_cycles,
            'locomotion_initiations': self._stats.locomotion_initiations,
            'rem_episodes': self._stats.rem_episodes,
            'last_output': self._last_output,
        }

    def get_stats(self) -> PPNStats:
        """Return accumulated statistics."""
        return self._stats

    def to_dict(self) -> Dict[str, Any]:
        """Serialisable dictionary of state + stats."""
        return {
            'state': self.get_state(),
            'stats': self._stats.to_dict(),
            'ach_history': [round(v, 4) for v in list(self._ach_history)[-20:]],
        }

    # --------------------------------------------------------------- control
    def reset(self) -> None:
        """Reset all internal state (preserve config)."""
        self._ach_history.clear()
        self._last_output = {}
        self._stats = PPNStats()
        logger.info("PPN reset")

    # ------------------------------------------------------------ from_yaml
    @classmethod
    def from_yaml(cls, config: Dict[str, Any]) -> 'PedunculopontineNucleus':
        """Construct from parsed YAML config dict."""
        ppn = config.get('pedunculopontine_nucleus', {})
        return cls(
            cholinergic_baseline=ppn.get('cholinergic_baseline', 0.5),
            locomotion_threshold=ppn.get('locomotion_threshold', 0.4),
            rem_threshold=ppn.get('rem_threshold', 0.6),
        )

    def __repr__(self) -> str:
        return (
            f"PedunculopontineNucleus(cycles={self._stats.total_cycles}, "
            f"ach={self._stats.avg_cholinergic_tone:.3f})"
        )
