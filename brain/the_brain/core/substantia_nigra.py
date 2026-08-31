"""
Substantia Nigra — Dopaminergic Motor Control and Basal Ganglia Output

Two anatomical divisions with distinct functions:
1. SNc (pars compacta): Dense dopamine neurons projecting to dorsal striatum
   via the nigrostriatal pathway. Critical for motor initiation, action
   selection vigour, and habit formation. Degeneration causes Parkinson's.
2. SNr (pars reticulata): GABAergic output nucleus of the basal ganglia.
   Tonically inhibits thalamus and superior colliculus; the direct pathway
   disinhibits targets by suppressing SNr firing.

Distinct from VTA: SNc -> dorsal striatum (motor/habit),
                   VTA -> ventral striatum (reward/motivation).

References:
    - Schultz (1998): Dopamine neurons and reward prediction error
    - DeLong (1990): Primate models of movement disorders
    - Hikosaka et al. (2000): Role of BG in control of saccadic eye movements
    - Gerfen & Surmeier (2011): D1/D2 MSN modulation by SNc dopamine
    - Haber (2003): Nigrostriatal vs mesolimbic dopamine pathways
    - Mink (1996): Basal ganglia focused selection and inhibition model
"""

import logging
import numpy as np
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from collections import deque

logger = logging.getLogger('brain.substantia_nigra')


# ============================================================================
# Stats Dataclass
# ============================================================================

@dataclass
class SubstantiaNigraStats:
    """Accumulated statistics for the substantia nigra module."""
    total_cycles: int = 0
    avg_da_level: float = 0.0
    avg_inhibition: float = 0.0
    disinhibition_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_cycles': self.total_cycles,
            'avg_da_level': round(self.avg_da_level, 4),
            'avg_inhibition': round(self.avg_inhibition, 4),
            'disinhibition_count': self.disinhibition_count,
        }


# ============================================================================
# Sub-component Classes
# ============================================================================

class ParsCompacta:
    """
    SNc dopamine neurons for motor and habit signalling.

    Computes a dopaminergic output driven by current motor demand,
    accumulated habit strength, and an effort-discount factor.

    Mathematical model:
        raw_da   = baseline + motor_gain * motor_demand
                             + habit_rate * habit_strength
                             - effort_cost * effort
        motor_da = clip(raw_da, 0, 1)
    """

    def __init__(
        self,
        da_baseline: float = 0.5,
        motor_gain: float = 1.0,
        habit_rate: float = 0.05,
        effort_cost: float = 0.3,
    ):
        self.da_baseline = np.clip(da_baseline, 0.0, 1.0)
        self.motor_gain = motor_gain
        self.habit_rate = habit_rate
        self.effort_cost = effort_cost
        self._activation: float = self.da_baseline

    def compute_da(
        self,
        motor_demand: float,
        habit_strength: float,
        effort: float,
    ) -> Dict[str, float]:
        """Compute dopamine signal for motor/habit processing.

        Args:
            motor_demand: Current urgency of motor output [0, 1].
            habit_strength: How habitual the ongoing action is [0, 1].
            effort: Energetic cost of the action [0, 1].

        Returns:
            Dict with motor_da, habit_signal, activation_level.
        """
        motor_demand = float(np.clip(motor_demand, 0.0, 1.0))
        habit_strength = float(np.clip(habit_strength, 0.0, 1.0))
        effort = float(np.clip(effort, 0.0, 1.0))

        # Core dopamine computation
        raw_da = (
            self.da_baseline
            + self.motor_gain * motor_demand
            + self.habit_rate * habit_strength
            - self.effort_cost * effort
        )
        motor_da = float(np.clip(raw_da, 0.0, 1.0))

        # Habit signal: sustained DA ramp for well-learned actions
        habit_signal = float(np.clip(
            self.da_baseline + self.habit_rate * habit_strength, 0.0, 1.0
        ))

        # Smooth activation tracking
        self._activation += 0.15 * (motor_da - self._activation)
        self._activation = float(np.clip(self._activation, 0.0, 1.0))

        return {
            'motor_da': motor_da,
            'habit_signal': habit_signal,
            'activation_level': self._activation,
        }


class ParsReticulata:
    """
    SNr GABAergic tonic inhibition — output nucleus of the basal ganglia.

    Tonically active, maintaining inhibition on thalamus and superior
    colliculus.  The direct (Go) pathway suppresses SNr, causing
    disinhibition of downstream targets.

    Model:
        inhibition = tone + indirect_pathway - direct_pathway
        disinhibited = inhibition < disinhibition_threshold
        thalamic_gate = 1 - inhibition   (0 = fully blocked, 1 = fully open)
    """

    def __init__(
        self,
        inhibition_tone: float = 0.7,
        disinhibition_threshold: float = 0.35,
    ):
        self.inhibition_tone = np.clip(inhibition_tone, 0.0, 1.0)
        self.disinhibition_threshold = disinhibition_threshold

    def compute_inhibition(
        self,
        direct_pathway: float,
        indirect_pathway: float,
    ) -> Dict[str, Any]:
        """Compute SNr output inhibition.

        Args:
            direct_pathway: Go-pathway activity suppressing SNr [0, 1].
            indirect_pathway: NoGo-pathway activity exciting SNr [0, 1].

        Returns:
            Dict with inhibition_level, thalamic_gate, disinhibited (bool).
        """
        direct_pathway = float(np.clip(direct_pathway, 0.0, 1.0))
        indirect_pathway = float(np.clip(indirect_pathway, 0.0, 1.0))

        raw_inhibition = (
            self.inhibition_tone
            + 0.5 * indirect_pathway
            - 0.6 * direct_pathway
        )
        inhibition_level = float(np.clip(raw_inhibition, 0.0, 1.0))

        thalamic_gate = float(np.clip(1.0 - inhibition_level, 0.0, 1.0))
        disinhibited = inhibition_level < self.disinhibition_threshold

        return {
            'inhibition_level': inhibition_level,
            'thalamic_gate': thalamic_gate,
            'disinhibited': bool(disinhibited),
        }


class NigrostriatalPathway:
    """
    Dopamine modulation of striatal plasticity along the nigrostriatal axis.

    High motor_da biases the striatum toward Go (D1-MSN potentiation);
    low motor_da biases toward NoGo (D2-MSN potentiation).

    Model:
        go_nogo_balance = 2 * motor_da - 1        (range [-1, +1])
        plasticity_signal = motor_da * action_value
    """

    def __init__(self, modulation_strength: float = 1.0):
        self.modulation_strength = modulation_strength

    def modulate(
        self,
        motor_da: float,
        action_value: float,
    ) -> Dict[str, float]:
        """Compute nigrostriatal plasticity modulation.

        Args:
            motor_da: Dopamine level from SNc [0, 1].
            action_value: Estimated value of the current action [0, 1].

        Returns:
            Dict with plasticity_signal, go_nogo_balance.
        """
        motor_da = float(np.clip(motor_da, 0.0, 1.0))
        action_value = float(np.clip(action_value, 0.0, 1.0))

        go_nogo_balance = float(
            np.clip((2.0 * motor_da - 1.0) * self.modulation_strength, -1.0, 1.0)
        )
        plasticity_signal = float(
            np.clip(motor_da * action_value * self.modulation_strength, 0.0, 1.0)
        )

        return {
            'plasticity_signal': plasticity_signal,
            'go_nogo_balance': go_nogo_balance,
        }


# ============================================================================
# Main Class
# ============================================================================

class SubstantiaNigra:
    """
    Complete Substantia Nigra module integrating SNc (dopamine), SNr
    (GABAergic output), and the nigrostriatal plasticity pathway.

    Usage:
        sn = SubstantiaNigra()
        result = sn.process(
            motor_demand=0.7, habit_strength=0.3, effort=0.4,
            direct_pathway=0.6, indirect_pathway=0.3,
        )
        # result keys: motor_da, habit_signal, activation_level,
        #              inhibition_level, thalamic_gate, disinhibited,
        #              plasticity_signal, go_nogo_balance
    """

    def __init__(
        self,
        da_baseline: float = 0.5,
        inhibition_tone: float = 0.7,
        motor_gain: float = 1.0,
        habit_rate: float = 0.05,
    ):
        self.da_baseline = da_baseline
        self.inhibition_tone = inhibition_tone
        self.motor_gain = motor_gain
        self.habit_rate = habit_rate

        # Sub-components
        self.snc = ParsCompacta(
            da_baseline=da_baseline,
            motor_gain=motor_gain,
            habit_rate=habit_rate,
        )
        self.snr = ParsReticulata(inhibition_tone=inhibition_tone)
        self.nigrostriatal = NigrostriatalPathway()

        # Running statistics
        self._stats = SubstantiaNigraStats()
        self._da_history: deque = deque(maxlen=200)
        self._inhibition_history: deque = deque(maxlen=200)

        logger.info(
            "SubstantiaNigra initialised — DA baseline=%.2f, "
            "inhibition tone=%.2f, motor_gain=%.1f",
            da_baseline, inhibition_tone, motor_gain,
        )

    # ------------------------------------------------------------------ core
    def process(
        self,
        motor_demand: float,
        habit_strength: float = 0.0,
        effort: float = 0.5,
        direct_pathway: float = 0.5,
        indirect_pathway: float = 0.5,
        action_value: float = 0.5,
    ) -> Dict[str, Any]:
        """Run one processing cycle through the substantia nigra.

        Args:
            motor_demand: Urgency of motor output [0, 1].
            habit_strength: Degree of habitual action [0, 1].
            effort: Energetic cost of the action [0, 1].
            direct_pathway: Go-pathway activity [0, 1].
            indirect_pathway: NoGo-pathway activity [0, 1].
            action_value: Estimated value of current action [0, 1].

        Returns:
            Combined dict of SNc, SNr, and nigrostriatal outputs.
        """
        # 1. SNc dopamine computation
        da_result = self.snc.compute_da(motor_demand, habit_strength, effort)

        # 2. SNr inhibition computation
        snr_result = self.snr.compute_inhibition(direct_pathway, indirect_pathway)

        # 3. Nigrostriatal plasticity modulation
        ns_result = self.nigrostriatal.modulate(
            da_result['motor_da'], action_value,
        )

        # Update internal bookkeeping
        self._da_history.append(da_result['motor_da'])
        self._inhibition_history.append(snr_result['inhibition_level'])
        self._stats.total_cycles += 1

        if snr_result['disinhibited']:
            self._stats.disinhibition_count += 1

        self._stats.avg_da_level = float(np.mean(list(self._da_history)))
        self._stats.avg_inhibition = float(np.mean(list(self._inhibition_history)))

        logger.debug(
            "SN cycle %d — DA=%.3f inhib=%.3f gate=%.3f disinhibited=%s",
            self._stats.total_cycles,
            da_result['motor_da'],
            snr_result['inhibition_level'],
            snr_result['thalamic_gate'],
            snr_result['disinhibited'],
        )

        # Merge all sub-results
        result: Dict[str, Any] = {}
        result.update(da_result)
        result.update(snr_result)
        result.update(ns_result)
        return result

    def direct_indirect_pathway_balance(self) -> Dict[str, float]:
        """
        Direct vs indirect pathway balance (Albin et al., 1989).

        SNc DA modulates basal ganglia pathways: D1-direct (GO) vs
        D2-indirect (NOGO). DA depletion (Parkinson's) shifts balance
        toward NOGO, causing akinesia. This balance determines whether
        actions are facilitated or suppressed.

        Returns:
            Dict with go_drive, nogo_drive, action_selection_bias
        """
        da = float(self._da_history[-1]) if self._da_history else self.da_baseline
        inh = float(self._inhibition_history[-1]) if self._inhibition_history else self.inhibition_tone

        # D1 direct pathway: DA excites -> GO
        go_drive = min(1.0, da * 1.2)
        # D2 indirect pathway: DA inhibits -> less NOGO
        nogo_drive = max(0.0, 1.0 - da * 0.8)
        # SNr tonic inhibition modulates both
        thalamic_gate = max(0.0, 1.0 - inh)
        action_bias = (go_drive - nogo_drive) * thalamic_gate

        return {
            'go_drive': round(go_drive, 4),
            'nogo_drive': round(nogo_drive, 4),
            'thalamic_gate': round(thalamic_gate, 4),
            'action_selection_bias': round(max(-1.0, min(1.0, action_bias)), 4),
        }

    # --------------------------------------------------------- introspection
    def get_state(self) -> Dict[str, Any]:
        """Return current internal state snapshot."""
        return {
            'da_level': float(self._da_history[-1]) if self._da_history else self.da_baseline,
            'activation_level': self.snc._activation,
            'inhibition_level': float(self._inhibition_history[-1]) if self._inhibition_history else self.inhibition_tone,
            'thalamic_gate': float(1.0 - (self._inhibition_history[-1] if self._inhibition_history else self.inhibition_tone)),
            'total_cycles': self._stats.total_cycles,
            'disinhibition_count': self._stats.disinhibition_count,
        }

    def get_stats(self) -> SubstantiaNigraStats:
        """Return accumulated statistics."""
        return self._stats

    def to_dict(self) -> Dict[str, Any]:
        """Serialisable dictionary of state + stats."""
        return {
            'state': self.get_state(),
            'stats': self._stats.to_dict(),
            'da_history': [round(v, 4) for v in list(self._da_history)[-20:]],
            'inhibition_history': [round(v, 4) for v in list(self._inhibition_history)[-20:]],
        }

    # --------------------------------------------------------------- control
    def reset(self) -> None:
        """Reset all internal state (preserve config)."""
        self.snc = ParsCompacta(
            da_baseline=self.da_baseline,
            motor_gain=self.motor_gain,
            habit_rate=self.habit_rate,
        )
        self.snr = ParsReticulata(inhibition_tone=self.inhibition_tone)
        self.nigrostriatal = NigrostriatalPathway()
        self._da_history.clear()
        self._inhibition_history.clear()
        self._stats = SubstantiaNigraStats()
        logger.info("SubstantiaNigra reset")

    # ------------------------------------------------------------ from_yaml
    @classmethod
    def from_yaml(cls, config: Dict[str, Any]) -> 'SubstantiaNigra':
        """Construct from parsed YAML config dict."""
        sn = config.get('substantia_nigra', {})
        return cls(
            da_baseline=sn.get('da_baseline', 0.5),
            inhibition_tone=sn.get('inhibition_tone', 0.7),
            motor_gain=sn.get('motor_gain', 1.0),
            habit_rate=sn.get('habit_rate', 0.05),
        )

    def __repr__(self) -> str:
        return (
            f"SubstantiaNigra(cycles={self._stats.total_cycles}, "
            f"da={self._stats.avg_da_level:.3f}, "
            f"inhib={self._stats.avg_inhibition:.3f})"
        )
