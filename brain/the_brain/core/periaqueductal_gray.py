"""
Periaqueductal Gray (PAG) Module - Phase D6

The PAG is a midbrain structure surrounding the cerebral aqueduct.
It is THE defensive behavior controller, selecting between different
survival strategies based on threat proximity and escapability.

Neuroscience basis:
- Bandler & Shipley (1994): 4 functional columns in PAG
  * Dorsolateral PAG: Active defense — fight, confrontation
  * Lateral PAG: Active defense — flight, escape
  * Ventrolateral PAG: Passive defense — freezing, quiescence,
    endogenous opioid-mediated pain suppression
  * Dorsomedial PAG: Autonomic arousal, hypertension, tachycardia
- Mobbs et al. (2007): Threat proximity determines PAG column activation
  * Distant threat -> dorsolateral (fight) or lateral (flight)
  * Proximate inescapable threat -> ventrolateral (freeze)

Key functions:
- Defensive behavior selection (fight/flight/freeze)
- Pain modulation (descending inhibition via endogenous opioids)
- Autonomic control during threats
- Defensive shutdown during system threats
- Vocalization and emotional expression

Integration:
- Input: CeA (threat signal), cortex (threat evaluation), hypothalamus (internal state)
- Output: PAG -> brainstem motor (defense), medulla (autonomic),
         rostral ventromedial medulla (pain modulation)
"""

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

import numpy as np

logger = logging.getLogger('brain.pag')


@dataclass
class PAGStats:
    """PAG processing statistics."""
    total_evaluations: int = 0
    total_fight_responses: int = 0
    total_flight_responses: int = 0
    total_freeze_responses: int = 0
    total_calm_responses: int = 0
    total_pain_suppression: int = 0
    avg_threat_proximity: float = 0.0
    avg_defense_intensity: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_evaluations': self.total_evaluations,
            'total_fight_responses': self.total_fight_responses,
            'total_flight_responses': self.total_flight_responses,
            'total_freeze_responses': self.total_freeze_responses,
            'total_calm_responses': self.total_calm_responses,
            'total_pain_suppression': self.total_pain_suppression,
            'avg_threat_proximity': round(self.avg_threat_proximity, 3),
            'avg_defense_intensity': round(self.avg_defense_intensity, 3),
        }


class DorsolateralPAG:
    """
    Dorsolateral PAG — Active defense: FIGHT.

    Activated when threat is moderate and confrontation is viable.
    Generates confrontational/aggressive responses.
    In Tahlamus: aggressive error correction, forceful retry,
    escalated action when blocked.
    """

    def __init__(self, activation_threshold: float = 0.5):
        self.activation_threshold = activation_threshold
        self._activation = 0.0

    def compute(self, threat: float, escapability: float, resources: float) -> float:
        """
        Compute fight response activation.

        Fight is selected when:
        - Threat is moderate-high
        - Escape is difficult
        - Resources (energy) are sufficient

        Args:
            threat: Threat level [0, 1]
            escapability: How easy it is to escape [0, 1]
            resources: Available resources/energy [0, 1]

        Returns:
            Fight activation [0, 1]
        """
        # Fight when threat is moderate, escape is hard, and we have resources
        fight_drive = threat * (1.0 - escapability) * resources
        self._activation = min(1.0, max(0.0, fight_drive))
        return self._activation

    @property
    def activation(self) -> float:
        return self._activation


class LateralPAG:
    """
    Lateral PAG — Active defense: FLIGHT.

    Activated when threat is high and escape is possible.
    Generates escape/avoidance responses.
    In Tahlamus: task abandonment, graceful degradation,
    switching to safer alternative strategies.
    """

    def __init__(self, activation_threshold: float = 0.5):
        self.activation_threshold = activation_threshold
        self._activation = 0.0

    def compute(self, threat: float, escapability: float, resources: float) -> float:
        """
        Compute flight response activation.

        Flight is selected when:
        - Threat is high
        - Escape route is available
        - Resources may be low (doesn't need much to flee)

        Args:
            threat: Threat level [0, 1]
            escapability: How easy to escape [0, 1]
            resources: Available resources [0, 1]

        Returns:
            Flight activation [0, 1]
        """
        flight_drive = threat * escapability
        self._activation = min(1.0, max(0.0, flight_drive))
        return self._activation

    @property
    def activation(self) -> float:
        return self._activation


class VentrolateralPAG:
    """
    Ventrolateral PAG — Passive defense: FREEZE.

    Activated when threat is proximate and inescapable.
    Generates freezing, quiescence, and endogenous opioid release
    (pain suppression during extreme threat).

    In Tahlamus: system pause, error containment, graceful shutdown,
    pain/error suppression during crisis.
    """

    def __init__(self, activation_threshold: float = 0.6):
        self.activation_threshold = activation_threshold
        self._activation = 0.0
        self._opioid_release = 0.0

    def compute(self, threat: float, escapability: float, proximity: float) -> Tuple[float, float]:
        """
        Compute freeze response and opioid release.

        Freeze when:
        - Threat is very high
        - Escape is impossible
        - Threat is very proximate

        Args:
            threat: Threat level [0, 1]
            escapability: How easy to escape [0, 1]
            proximity: How close the threat is [0, 1]

        Returns:
            (freeze_activation, opioid_release) both [0, 1]
        """
        # Freeze when proximate, inescapable threat
        freeze_drive = threat * (1.0 - escapability) * proximity
        self._activation = min(1.0, max(0.0, freeze_drive))

        # Endogenous opioids released during extreme freeze
        self._opioid_release = max(0.0, self._activation - 0.5) * 2.0
        self._opioid_release = min(1.0, self._opioid_release)

        return self._activation, self._opioid_release

    @property
    def activation(self) -> float:
        return self._activation

    @property
    def opioid_release(self) -> float:
        return self._opioid_release


class DorsomedialPAG:
    """
    Dorsomedial PAG — Autonomic arousal response.

    Controls autonomic nervous system activation during threats:
    - Heart rate increase
    - Blood pressure increase
    - Respiratory rate increase

    In Tahlamus: system resource mobilization, emergency processing
    priority, heightened monitoring.
    """

    def __init__(self, gain: float = 0.7):
        self.gain = gain
        self._autonomic_activation = 0.0

    def compute(self, threat: float, arousal: float) -> float:
        """
        Compute autonomic arousal response.

        Args:
            threat: Threat level [0, 1]
            arousal: Current arousal from LC [0, 1]

        Returns:
            Autonomic activation [0, 1]
        """
        self._autonomic_activation = (threat * 0.6 + arousal * 0.4) * self.gain
        self._autonomic_activation = min(1.0, max(0.0, self._autonomic_activation))
        return self._autonomic_activation

    @property
    def activation(self) -> float:
        return self._autonomic_activation


class PeriaqueductalGray:
    """
    Complete Periaqueductal Gray module.

    Functions:
    1. Defensive behavior selection (fight/flight/freeze)
    2. Pain modulation (opioid release)
    3. Autonomic arousal control
    4. Emergency mode activation
    5. Defensive response intensity scaling

    This is THE emergency response controller for Tahlamus.
    """

    def __init__(
        self,
        fight_threshold: float = 0.5,
        flight_threshold: float = 0.5,
        freeze_threshold: float = 0.6,
        autonomic_gain: float = 0.7,
        emergency_threshold: float = 0.8,
    ):
        self.dl_pag = DorsolateralPAG(fight_threshold)
        self.l_pag = LateralPAG(flight_threshold)
        self.vl_pag = VentrolateralPAG(freeze_threshold)
        self.dm_pag = DorsomedialPAG(autonomic_gain)
        self._emergency_threshold = emergency_threshold
        self._stats = PAGStats()
        self._threat_history = deque(maxlen=100)
        self._defense_history = deque(maxlen=100)

    def process(
        self,
        threat: float,
        escapability: float = 0.5,
        proximity: float = 0.5,
        resources: float = 0.7,
        arousal: float = 0.5,
    ) -> Dict[str, Any]:
        """
        Full PAG processing cycle.

        Selects the appropriate defensive strategy based on
        threat characteristics.

        Args:
            threat: Threat level [0, 1]
            escapability: How easy to escape [0, 1]
            proximity: How close the threat is [0, 1]
            resources: Available resources/energy [0, 1]
            arousal: Current arousal from LC [0, 1]

        Returns:
            Dict with selected defense, column activations, pain modulation
        """
        threat = max(0.0, min(1.0, threat))
        escapability = max(0.0, min(1.0, escapability))
        proximity = max(0.0, min(1.0, proximity))
        resources = max(0.0, min(1.0, resources))

        # Compute all column activations
        fight = self.dl_pag.compute(threat, escapability, resources)
        flight = self.l_pag.compute(threat, escapability, resources)
        freeze, opioid = self.vl_pag.compute(threat, escapability, proximity)
        autonomic = self.dm_pag.compute(threat, arousal)

        # Select dominant defense strategy (winner-take-all)
        activations = {
            'fight': fight,
            'flight': flight,
            'freeze': freeze,
        }

        if threat < 0.2:
            selected = 'calm'
            intensity = 0.0
        else:
            selected = max(activations, key=activations.get)
            intensity = activations[selected]

        # Emergency mode: extreme threat
        emergency = threat > self._emergency_threshold

        # Pain suppression: from vlPAG opioid release
        pain_suppression = opioid

        # Update stats
        self._stats.total_evaluations += 1
        self._threat_history.append(threat)
        self._defense_history.append(intensity)

        if selected == 'fight':
            self._stats.total_fight_responses += 1
        elif selected == 'flight':
            self._stats.total_flight_responses += 1
        elif selected == 'freeze':
            self._stats.total_freeze_responses += 1
        else:
            self._stats.total_calm_responses += 1

        if pain_suppression > 0.1:
            self._stats.total_pain_suppression += 1

        self._stats.avg_threat_proximity = float(
            np.mean(list(self._threat_history))
        )
        self._stats.avg_defense_intensity = float(
            np.mean(list(self._defense_history))
        )

        return {
            'selected_defense': selected,
            'defense_intensity': round(intensity, 3),
            'fight_activation': round(fight, 3),
            'flight_activation': round(flight, 3),
            'freeze_activation': round(freeze, 3),
            'autonomic_activation': round(autonomic, 3),
            'pain_suppression': round(pain_suppression, 3),
            'emergency_mode': emergency,
        }


    def threat_intensity_to_column(self, threat_intensity: float, escapability: float = 0.5) -> Dict[str, Any]:
        """
        Map threat intensity to primary PAG column activation.

        Mobbs et al. (2007): Threat proximity determines PAG column:
        - Low/ambiguous threat: vlPAG (freeze/vigilance)
        - Medium threat + escape available: lPAG (flight)
        - High threat + no escape: dlPAG (fight)
        - Overwhelming threat: vlPAG again (tonic immobility)

        This implements the defensive distance model where the threat-defense
        relationship is nonlinear with hysteresis.

        Args:
            threat_intensity: Threat level [0, 1]
            escapability: Ability to escape [0, 1]

        Returns:
            Dict with primary_column, column_activations, defense_phase
        """
        # Defense phases based on threat intensity
        if threat_intensity < 0.2:
            primary = 'calm'
            phase = 'safe'
            column_weights = {'dlPAG': 0.0, 'lPAG': 0.0, 'vlPAG': 0.05, 'dmPAG': 0.0}
        elif threat_intensity < 0.4:
            # Low threat: freeze/vigilance (vlPAG) - assess situation
            primary = 'vlPAG_vigilance'
            phase = 'assessment'
            column_weights = {'dlPAG': 0.05, 'lPAG': 0.1, 'vlPAG': 0.6, 'dmPAG': 0.2}
        elif threat_intensity < 0.65:
            if escapability > 0.4:
                # Medium threat + escape: flight (lPAG)
                primary = 'lPAG_flight'
                phase = 'active_avoidance'
                column_weights = {'dlPAG': 0.1, 'lPAG': 0.7, 'vlPAG': 0.1, 'dmPAG': 0.4}
            else:
                # Medium threat + no escape: fight (dlPAG)
                primary = 'dlPAG_fight'
                phase = 'active_defense'
                column_weights = {'dlPAG': 0.6, 'lPAG': 0.15, 'vlPAG': 0.1, 'dmPAG': 0.5}
        elif threat_intensity < 0.85:
            # High threat: fight if trapped, flight if possible
            if escapability > 0.3:
                primary = 'lPAG_flight'
                phase = 'urgent_escape'
                column_weights = {'dlPAG': 0.2, 'lPAG': 0.8, 'vlPAG': 0.05, 'dmPAG': 0.6}
            else:
                primary = 'dlPAG_fight'
                phase = 'desperate_defense'
                column_weights = {'dlPAG': 0.8, 'lPAG': 0.1, 'vlPAG': 0.05, 'dmPAG': 0.7}
        else:
            # Overwhelming threat: tonic immobility (vlPAG shutdown)
            primary = 'vlPAG_immobility'
            phase = 'tonic_immobility'
            column_weights = {'dlPAG': 0.05, 'lPAG': 0.05, 'vlPAG': 0.9, 'dmPAG': 0.3}

        return {
            'primary_column': primary,
            'defense_phase': phase,
            'column_weights': {k: round(v, 3) for k, v in column_weights.items()},
            'threat_intensity': round(threat_intensity, 3),
            'escapability': round(escapability, 3),
        }

    def get_defense_cascade(self) -> Dict[str, Any]:
        """
        Get the full defense cascade state.

        Returns the current state of all PAG columns, transition
        thresholds between defense modes, and historical defense
        pattern. This provides a comprehensive readout of the
        defense system for use by other modules.

        Returns:
            Dict with column_activations, transitions, history
        """
        recent_threats = list(self._threat_history)[-20:] if self._threat_history else []
        recent_defenses = list(self._defense_history)[-20:] if self._defense_history else []

        # Compute transition thresholds
        avg_threat = float(np.mean(recent_threats)) if recent_threats else 0.0
        threat_trend = 0.0
        if len(recent_threats) >= 5:
            first_half = float(np.mean(recent_threats[:len(recent_threats)//2]))
            second_half = float(np.mean(recent_threats[len(recent_threats)//2:]))
            threat_trend = second_half - first_half  # Positive = escalating

        return {
            'column_activations': {
                'dorsolateral_fight': round(self.dl_pag.activation, 3),
                'lateral_flight': round(self.l_pag.activation, 3),
                'ventrolateral_freeze': round(self.vl_pag.activation, 3),
                'dorsomedial_autonomic': round(self.dm_pag.activation, 3),
            },
            'pain_suppression': round(self.vl_pag.opioid_release, 3),
            'avg_recent_threat': round(avg_threat, 3),
            'threat_trend': round(threat_trend, 4),
            'threat_escalating': threat_trend > 0.05,
            'emergency_active': self.is_emergency(),
            'transition_thresholds': {
                'calm_to_freeze': 0.2,
                'freeze_to_flight': 0.4,
                'flight_to_fight': 0.65,
                'fight_to_immobility': 0.85,
            },
        }

    def defensive_distance_gradient(
        self,
        threat_distance: float,
        threat_magnitude: float = 0.5,
    ) -> Dict[str, Any]:
        """
        Continuous defensive distance model (Mobbs et al., 2007).

        Maps threat distance to a smooth gradient of defensive responses
        rather than discrete categories. As threat approaches, activation
        shifts from vmPFC (risk assessment) -> dACC (avoidance planning) ->
        PAG (reflexive defense). This captures the smooth transition seen
        in fMRI during virtual predator paradigms.

        Args:
            threat_distance: Distance to threat [0=contact, 1=far]
            threat_magnitude: How dangerous the threat is [0, 1]

        Returns:
            Dict with cortical_control, pag_control, defense_gradient
        """
        distance = max(0.0, min(1.0, threat_distance))
        magnitude = max(0.0, min(1.0, threat_magnitude))

        # Sigmoid transition: cortical control decays, PAG control rises
        # as threat approaches
        transition_point = 0.4  # Distance where control shifts
        steepness = 8.0
        pag_control = 1.0 / (1.0 + np.exp(steepness * (distance - transition_point)))
        cortical_control = 1.0 - pag_control

        # Scale by threat magnitude
        pag_activation = float(pag_control * magnitude)
        cortical_activation = float(cortical_control * magnitude)

        # Defense urgency: nonlinear increase at close range
        urgency = float((1.0 - distance) ** 2 * magnitude)

        # Determine primary control region
        if distance > 0.6:
            primary = 'prefrontal_assessment'
        elif distance > 0.3:
            primary = 'cingulate_planning'
        else:
            primary = 'pag_reflexive'

        return {
            'cortical_control': round(cortical_activation, 4),
            'pag_control': round(pag_activation, 4),
            'defense_urgency': round(min(1.0, urgency), 4),
            'primary_controller': primary,
            'threat_distance': round(distance, 3),
        }

    def is_emergency(self) -> bool:
        """Check if currently in emergency mode."""
        if not self._threat_history:
            return False
        return self._threat_history[-1] > self._emergency_threshold

    def get_pain_suppression(self) -> float:
        """Get current pain suppression level."""
        return self.vl_pag.opioid_release

    def get_state(self) -> Dict[str, Any]:
        return {
            'stats': self._stats.to_dict(),
            'columns': {
                'dorsolateral': round(self.dl_pag.activation, 3),
                'lateral': round(self.l_pag.activation, 3),
                'ventrolateral': round(self.vl_pag.activation, 3),
                'dorsomedial': round(self.dm_pag.activation, 3),
            },
        }

    def get_stats(self) -> PAGStats:
        return self._stats

    def reset(self):
        self._stats = PAGStats()

    def to_dict(self) -> Dict[str, Any]:
        return self.get_state()

    @classmethod
    def from_yaml(cls, config: Dict[str, Any]) -> 'PeriaqueductalGray':
        cfg = config.get('periaqueductal_gray', {})
        return cls(
            fight_threshold=cfg.get('fight_threshold', 0.5),
            flight_threshold=cfg.get('flight_threshold', 0.5),
            freeze_threshold=cfg.get('freeze_threshold', 0.6),
            autonomic_gain=cfg.get('autonomic_gain', 0.7),
            emergency_threshold=cfg.get('emergency_threshold', 0.8),
        )
