"""
Zona Incerta — Subthalamic Inhibitory Hub for Limbic-Motor Integration

A thin, enigmatic strip of grey matter beneath the thalamus that serves as a
GABAergic inhibitory gatekeeper bridging motivated states and motor action.
Despite its small size, it receives projections from nearly every major brain
system and projects inhibitory outputs to the thalamus, superior colliculus,
and brainstem motor centres. Implements:

1. Incertal inhibition — GABAergic gating of downstream targets (thalamus,
   superior colliculus, brainstem motor centres)
2. Limbic-motor integration — bridges motivational drives and motor readiness
   into a coherent action tendency signal
3. Visceral modulation — gates feeding, drinking, and autonomic functions
   based on internal state

Key functions:
    - Visceral regulation (feeding, drinking, autonomic tone)
    - Arousal modulation via thalamic inhibition
    - Attention gating through superior colliculus suppression
    - Locomotion control via brainstem motor inhibition
    - Pain modulation (analgesic gating)

References:
    - Mitrofanis (2005): "The definitive guide" — comprehensive review of ZI
      connectivity and the "odd couple" relationship with thalamus
    - Barthó et al. (2002): ZI GABAergic neurons tonically inhibit posterior
      thalamus, controlling sensory relay gain
    - Urbain & Bhatt (2020): ZI role in attention and orienting via superior
      colliculus inhibition
    - Wang et al. (2020): ZI feeding circuits — GABAergic disinhibition of
      lateral hypothalamus drives consummatory behaviour
    - Chou et al. (2018): ZI as a "hub" integrating arousal, pain, and defence
"""

import logging
import numpy as np
from typing import Any, Dict, Optional
from dataclasses import dataclass
from collections import deque

logger = logging.getLogger('brain.zona_incerta')


# ============================================================================
# Stats Dataclass
# ============================================================================

@dataclass
class ZonaIncertaStats:
    """Accumulated statistics for the Zona Incerta module."""
    total_cycles: int = 0
    avg_inhibition: float = 0.0
    integration_events: int = 0
    avg_action_tendency: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_cycles': self.total_cycles,
            'avg_inhibition': round(self.avg_inhibition, 4),
            'integration_events': self.integration_events,
            'avg_action_tendency': round(self.avg_action_tendency, 4),
        }


# ============================================================================
# Sub-component Classes
# ============================================================================

class IncertalInhibition:
    """
    GABAergic gating of downstream targets.

    The zona incerta tonically inhibits the thalamus, superior colliculus,
    and brainstem motor centres.  Higher inhibition_level suppresses target
    signals more strongly, implementing the ZI's role as a default brake
    on sensory relay and orienting behaviour (Barthó et al., 2002).
    """

    DEFAULT_TARGETS = ('thalamus', 'superior_colliculus', 'motor')

    def gate(
        self,
        target_signals: Dict[str, float],
        inhibition_level: float,
    ) -> Dict[str, float]:
        """
        Apply GABAergic inhibition to downstream target signals.

        Args:
            target_signals: Mapping of target name to signal strength [0, 1].
            inhibition_level: Global inhibition level [0, 1].

        Returns:
            Gated target signals (each scaled by 1 - inhibition_level).
        """
        inhibition_level = float(np.clip(inhibition_level, 0.0, 1.0))
        gate_factor = 1.0 - inhibition_level

        gated: Dict[str, float] = {}
        for target, signal in target_signals.items():
            signal = float(np.clip(signal, 0.0, 1.0))
            gated[target] = round(signal * gate_factor, 4)

        return gated


class LimbicMotorIntegrator:
    """
    Bridges motivational state and motor readiness into action tendency.

    The zona incerta sits at the anatomical crossroads between limbic
    (motivational) inputs and motor output pathways.  When motivation and
    motor readiness are both high, the integrator releases inhibition,
    producing a strong action tendency signal (Mitrofanis, 2005).

    integration_gain scales how strongly co-occurring motivation and motor
    readiness combine.
    """

    def __init__(self, integration_gain: float = 1.0):
        self.integration_gain = max(0.0, float(integration_gain))

    def integrate(
        self,
        motivation: float,
        motor_readiness: float,
        arousal: float,
    ) -> Dict[str, float]:
        """
        Compute action tendency from motivation, motor readiness, and arousal.

        Args:
            motivation: Motivational drive intensity [0, 1].
            motor_readiness: Motor system readiness [0, 1].
            arousal: General arousal level [0, 1].

        Returns:
            Dict with action_tendency, inhibition_release, integration_strength.
        """
        motivation = float(np.clip(motivation, 0.0, 1.0))
        motor_readiness = float(np.clip(motor_readiness, 0.0, 1.0))
        arousal = float(np.clip(arousal, 0.0, 1.0))

        # Integration strength: geometric-mean-like coupling weighted by gain
        integration_strength = (
            self.integration_gain * motivation * motor_readiness
        )
        integration_strength = float(np.clip(integration_strength, 0.0, 1.0))

        # Arousal modulates final action tendency — low arousal suppresses it
        action_tendency = integration_strength * (0.4 + 0.6 * arousal)
        action_tendency = float(np.clip(action_tendency, 0.0, 1.0))

        # Inhibition release: inverse of how much the ZI brake is engaged
        inhibition_release = action_tendency
        inhibition_release = float(np.clip(inhibition_release, 0.0, 1.0))

        return {
            'action_tendency': round(action_tendency, 4),
            'inhibition_release': round(inhibition_release, 4),
            'integration_strength': round(integration_strength, 4),
        }


class VisceralModulator:
    """
    Modulates visceral and autonomic functions.

    ZI neurons in the ventral sector project to the lateral hypothalamus,
    gating feeding and drinking behaviour.  Disinhibition of LH drives
    consummatory actions (Wang et al., 2020).  The modulator also scales
    a general visceral output based on internal state.
    """

    def __init__(self, visceral_sensitivity: float = 0.5):
        self.visceral_sensitivity = float(np.clip(visceral_sensitivity, 0.0, 1.0))

    def modulate(
        self,
        visceral_input: float,
        state: str = 'neutral',
    ) -> Dict[str, float]:
        """
        Modulate visceral output and consummatory gates.

        Args:
            visceral_input: Raw visceral/interoceptive signal [0, 1].
            state: Descriptive state ('hungry', 'thirsty', 'neutral',
                   'satiated').

        Returns:
            Dict with visceral_output, feeding_gate, drinking_gate.
        """
        visceral_input = float(np.clip(visceral_input, 0.0, 1.0))

        visceral_output = visceral_input * self.visceral_sensitivity
        visceral_output = float(np.clip(visceral_output, 0.0, 1.0))

        # Consummatory gates opened by relevant internal state
        feeding_gate = 0.0
        drinking_gate = 0.0

        if state == 'hungry':
            feeding_gate = 0.5 + 0.5 * visceral_input
        elif state == 'thirsty':
            drinking_gate = 0.5 + 0.5 * visceral_input
        elif state == 'satiated':
            feeding_gate = max(0.0, 0.1 - 0.1 * visceral_input)
            drinking_gate = max(0.0, 0.1 - 0.1 * visceral_input)
        else:
            # neutral — moderate baseline
            feeding_gate = 0.2 * visceral_input
            drinking_gate = 0.2 * visceral_input

        feeding_gate = float(np.clip(feeding_gate, 0.0, 1.0))
        drinking_gate = float(np.clip(drinking_gate, 0.0, 1.0))

        return {
            'visceral_output': round(visceral_output, 4),
            'feeding_gate': round(feeding_gate, 4),
            'drinking_gate': round(drinking_gate, 4),
        }


# ============================================================================
# Main Class
# ============================================================================

class ZonaIncerta:
    """
    Complete Zona Incerta module integrating GABAergic inhibition,
    limbic-motor integration, and visceral modulation.

    The ZI acts as a subthalamic inhibitory hub: by default it tonically
    suppresses downstream targets.  When motivational and motor signals
    converge, the inhibition is released, enabling coordinated action.

    Usage:
        zi = ZonaIncerta()
        result = zi.process(
            motivation=0.7, motor_readiness=0.6, arousal=0.5,
            visceral_input=0.3,
            target_signals={'thalamus': 0.8, 'superior_colliculus': 0.5},
        )
    """

    def __init__(
        self,
        baseline_inhibition: float = 0.6,
        integration_gain: float = 1.0,
        visceral_sensitivity: float = 0.5,
    ):
        self.baseline_inhibition = float(np.clip(baseline_inhibition, 0.0, 1.0))
        self.integration_gain = max(0.0, float(integration_gain))
        self.visceral_sensitivity = float(np.clip(visceral_sensitivity, 0.0, 1.0))

        # Sub-components
        self.inhibition = IncertalInhibition()
        self.integrator = LimbicMotorIntegrator(
            integration_gain=integration_gain,
        )
        self.visceral = VisceralModulator(
            visceral_sensitivity=visceral_sensitivity,
        )

        # Running statistics
        self._stats = ZonaIncertaStats()
        self._inhibition_history: deque = deque(maxlen=200)
        self._action_tendency_history: deque = deque(maxlen=200)

        logger.info(
            "ZonaIncerta initialised — baseline_inhibition=%.2f, "
            "integration_gain=%.1f, visceral_sensitivity=%.2f",
            baseline_inhibition, integration_gain, visceral_sensitivity,
        )

    # ------------------------------------------------------------------ core
    def process(
        self,
        motivation: float = 0.5,
        motor_readiness: float = 0.5,
        arousal: float = 0.5,
        visceral_input: float = 0.0,
        visceral_state: str = 'neutral',
        target_signals: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """
        Run one processing cycle.

        Args:
            motivation: Motivational drive intensity [0, 1].
            motor_readiness: Motor system readiness [0, 1].
            arousal: General arousal level [0, 1].
            visceral_input: Raw visceral/interoceptive signal [0, 1].
            visceral_state: Descriptive state for visceral modulation.
            target_signals: Optional downstream target signals to gate.

        Returns:
            Dict with inhibition_level, action_tendency, gated_targets,
            visceral, integration_strength, inhibition_release.
        """
        if target_signals is None:
            target_signals = {
                'thalamus': 0.5,
                'superior_colliculus': 0.5,
                'motor': 0.5,
            }

        # 1. Limbic-motor integration
        integration = self.integrator.integrate(motivation, motor_readiness, arousal)

        # 2. Compute effective inhibition: baseline reduced by inhibition release
        effective_inhibition = self.baseline_inhibition * (
            1.0 - integration['inhibition_release']
        )
        effective_inhibition = float(np.clip(effective_inhibition, 0.0, 1.0))

        # 3. Gate downstream targets
        gated = self.inhibition.gate(target_signals, effective_inhibition)

        # 4. Visceral modulation
        visc = self.visceral.modulate(visceral_input, visceral_state)

        # Update bookkeeping
        self._inhibition_history.append(effective_inhibition)
        self._action_tendency_history.append(integration['action_tendency'])
        self._stats.total_cycles += 1

        if integration['integration_strength'] > 0.3:
            self._stats.integration_events += 1

        self._stats.avg_inhibition = float(
            np.mean(list(self._inhibition_history))
        )
        self._stats.avg_action_tendency = float(
            np.mean(list(self._action_tendency_history))
        )

        logger.debug(
            "ZI cycle %d — inhibition=%.3f action_tendency=%.3f "
            "integration=%.3f visceral_out=%.3f",
            self._stats.total_cycles, effective_inhibition,
            integration['action_tendency'], integration['integration_strength'],
            visc['visceral_output'],
        )

        return {
            'inhibition_level': round(effective_inhibition, 4),
            'action_tendency': round(integration['action_tendency'], 4),
            'integration_strength': round(integration['integration_strength'], 4),
            'inhibition_release': round(integration['inhibition_release'], 4),
            'gated_targets': gated,
            'visceral': visc,
        }

    def disinhibition_gate(self, trigger_strength: float) -> Dict[str, float]:
        """
        Disinhibition gating (Mitrofanis, 2005).

        ZI provides tonic inhibition to thalamus and brainstem. When ZI
        is itself inhibited (disinhibition), it releases its targets,
        enabling behaviors that are normally suppressed. This is how
        the brain selectively enables specific motor programs.

        Args:
            trigger_strength: Strength of disinhibitory input [0, 1]

        Returns:
            Dict with gate_open, released_output, inhibition_remaining
        """
        trigger = max(0.0, min(1.0, trigger_strength))
        current_inhibition = self.baseline_inhibition

        # Disinhibition: trigger reduces ZI output
        released = trigger * current_inhibition
        remaining = max(0.0, current_inhibition - released)

        # Gate opens when sufficient disinhibition
        gate_open = released > 0.3

        return {
            'gate_open': gate_open,
            'released_output': round(released, 4),
            'inhibition_remaining': round(remaining, 4),
            'trigger_strength': round(trigger, 4),
        }

    # --------------------------------------------------------- introspection
    def get_state(self) -> Dict[str, Any]:
        """Return current internal state snapshot."""
        return {
            'baseline_inhibition': round(self.baseline_inhibition, 4),
            'total_cycles': self._stats.total_cycles,
            'avg_inhibition': round(self._stats.avg_inhibition, 4),
            'avg_action_tendency': round(self._stats.avg_action_tendency, 4),
            'integration_events': self._stats.integration_events,
        }

    def get_stats(self) -> ZonaIncertaStats:
        """Return accumulated statistics."""
        return self._stats

    def to_dict(self) -> Dict[str, Any]:
        """Serialisable dictionary of state + stats."""
        return {
            'state': self.get_state(),
            'stats': self._stats.to_dict(),
            'inhibition_history': [
                round(v, 4) for v in list(self._inhibition_history)[-20:]
            ],
            'action_tendency_history': [
                round(v, 4) for v in list(self._action_tendency_history)[-20:]
            ],
        }

    # --------------------------------------------------------------- control
    def reset(self) -> None:
        """Reset all internal state (preserve config)."""
        self._inhibition_history.clear()
        self._action_tendency_history.clear()
        self._stats = ZonaIncertaStats()
        logger.info("ZonaIncerta reset")

    # ------------------------------------------------------------ from_yaml
    @classmethod
    def from_yaml(cls, config: Dict[str, Any]) -> 'ZonaIncerta':
        """Construct from parsed YAML config dict."""
        zi = config.get('zona_incerta', {})
        return cls(
            baseline_inhibition=zi.get('baseline_inhibition', 0.6),
            integration_gain=zi.get('integration_gain', 1.0),
            visceral_sensitivity=zi.get('visceral_sensitivity', 0.5),
        )

    def __repr__(self) -> str:
        return (
            f"ZonaIncerta(cycles={self._stats.total_cycles}, "
            f"avg_inhibition={self._stats.avg_inhibition:.3f})"
        )
