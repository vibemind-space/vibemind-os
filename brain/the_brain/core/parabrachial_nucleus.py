"""
Parabrachial Nucleus Module

Pontine nucleus surrounding the superior cerebellar peduncle, serving as
the brain's general alarm system for threats to homeostasis.

Neuroscience basis:
- Palmiter (2018): PBN as general alarm system for threats to homeostasis
- Carter et al. (2013): PBN CGRP neurons as aversive teaching signal
- Lateral PBN: Taste, visceral, and thermal information relay
- Medial PBN: Pain and aversive signal processing

Key functions:
- Interoceptive threat detection (pain, visceral malaise, temperature extremes)
- General alarm relay to forebrain
- Emergency signal amplification (super-additive for multi-channel threats)
- Taste aversion / aversive teaching via CGRP neurons
- Homeostatic threat relay to drive behavioral responses

Integration:
- Input: Interoceptive signals (pain, temperature, visceral, resource, error)
- Output: Alarm signal to amygdala/forebrain, teaching signal, drive outputs
"""

import logging
from collections import deque, defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger('brain.parabrachial_nucleus')


@dataclass
class ParabrachialNucleusStats:
    """Accumulated statistics for the Parabrachial Nucleus."""
    total_cycles: int = 0
    total_alarms: int = 0
    avg_alarm_level: float = 0.0
    threat_type_counts: Dict[str, int] = field(default_factory=dict)
    teaching_signals_generated: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_cycles': self.total_cycles,
            'total_alarms': self.total_alarms,
            'avg_alarm_level': round(self.avg_alarm_level, 3),
            'threat_type_counts': dict(self.threat_type_counts),
            'teaching_signals_generated': self.teaching_signals_generated,
        }


# ─── Interoceptive Threat Detector ────────────────────────────────────────

class InteroceptiveThreatDetector:
    """
    Detects threats to internal homeostatic state.

    Monitors multiple interoceptive channels (pain, temperature,
    visceral distress, resource depletion, error rate) against
    configurable thresholds. Any channel exceeding its threshold
    triggers an alarm condition.
    """

    def __init__(
        self,
        thresholds: Optional[Dict[str, float]] = None,
    ):
        self.thresholds: Dict[str, float] = thresholds or {
            'pain': 0.4,
            'temperature': 0.6,
            'visceral_distress': 0.5,
            'resource_depletion': 0.5,
            'error_rate': 0.5,
        }

    def detect(self, signals: Dict[str, float]) -> Dict[str, Any]:
        """
        Detect threats across interoceptive channels.

        Args:
            signals: Channel name -> signal intensity [0, 1]

        Returns:
            Dict with threat_detected, threat_channels, max_severity,
            combined_threat
        """
        threat_channels: List[str] = []
        severities: List[float] = []

        for channel, threshold in self.thresholds.items():
            value = float(signals.get(channel, 0.0))
            value = max(0.0, min(1.0, value))
            if value > threshold:
                threat_channels.append(channel)
                # Severity: how far above threshold (normalized)
                severity = (value - threshold) / (1.0 - threshold + 1e-8)
                severities.append(min(1.0, severity))

        max_severity = float(max(severities)) if severities else 0.0
        # Combined threat: RMS of severities (captures multi-channel load)
        combined = float(np.sqrt(np.mean(np.square(severities)))) if severities else 0.0

        return {
            'threat_detected': len(threat_channels) > 0,
            'threat_channels': threat_channels,
            'max_severity': round(max_severity, 4),
            'combined_threat': round(min(1.0, combined), 4),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {'thresholds': dict(self.thresholds)}


# ─── Alarm Signal Generator ──────────────────────────────────────────────

class AlarmSignalGenerator:
    """
    Generates graded alarm signals from threat information.

    Palmiter (2018): The PBN alarm system produces graded output
    proportional to threat severity. Multiple simultaneous threats
    produce super-additive alarm (non-linear amplification).
    """

    def __init__(self, gain: float = 1.0):
        self.gain = gain
        self._alarm_history = deque(maxlen=100)

    def generate_alarm(
        self,
        threat_severity: float,
        n_active_channels: int,
    ) -> Dict[str, float]:
        """
        Generate alarm output from threat severity.

        Multiple simultaneous threats produce super-additive alarm
        via a non-linear channel multiplier.

        Args:
            threat_severity: Combined threat severity [0, 1]
            n_active_channels: Number of channels currently in alarm

        Returns:
            Dict with alarm_level, urgency, broadcast_strength
        """
        threat_severity = max(0.0, min(1.0, threat_severity))
        n_active_channels = max(0, n_active_channels)

        # Super-additive: multiple channels amplify the alarm non-linearly
        channel_multiplier = 1.0 + 0.3 * (n_active_channels ** 1.5) if n_active_channels > 0 else 0.0
        raw_alarm = threat_severity * channel_multiplier * self.gain
        alarm_level = min(1.0, raw_alarm)

        # Urgency: how fast a response is needed (exponential with severity)
        urgency = min(1.0, 1.0 - np.exp(-3.0 * alarm_level))

        # Broadcast strength: how widely the alarm should propagate
        broadcast_strength = min(1.0, alarm_level * (1.0 + 0.2 * n_active_channels))

        self._alarm_history.append(alarm_level)

        return {
            'alarm_level': round(alarm_level, 4),
            'urgency': round(float(urgency), 4),
            'broadcast_strength': round(broadcast_strength, 4),
        }

    def get_avg_alarm(self) -> float:
        if not self._alarm_history:
            return 0.0
        return float(np.mean(list(self._alarm_history)))

    def to_dict(self) -> Dict[str, Any]:
        return {
            'gain': self.gain,
            'avg_alarm': round(self.get_avg_alarm(), 4),
            'history_size': len(self._alarm_history),
        }


# ─── Aversive Teaching Signal (CGRP neurons) ─────────────────────────────

class AversiveTeachingSignal:
    """
    CGRP neuron-based aversive teaching signal.

    Carter et al. (2013): PBN CGRP neurons generate a strong
    teaching signal that drives avoidance learning. The signal
    encodes "avoid this in the future" and is stronger for more
    severe and novel threats.
    """

    def __init__(self, teaching_rate: float = 0.1):
        self.teaching_rate = teaching_rate
        self._seen_threats: Dict[str, int] = defaultdict(int)

    def compute_teaching(
        self,
        threat_source: str,
        threat_severity: float,
    ) -> Dict[str, float]:
        """
        Compute aversive teaching signal from a threat.

        Stronger teaching for more severe threats and for novel
        (previously unseen) threat sources.

        Args:
            threat_source: Name of the threatening channel
            threat_severity: How severe the threat is [0, 1]

        Returns:
            Dict with teaching_strength, avoidance_drive, memory_tag_strength
        """
        threat_severity = max(0.0, min(1.0, threat_severity))

        # Novelty bonus: first encounter teaches more
        encounter_count = self._seen_threats[threat_source]
        novelty = 1.0 / (1.0 + 0.5 * encounter_count)

        # Teaching strength: severity * novelty * learning rate scaling
        teaching_strength = threat_severity * novelty * (1.0 + self.teaching_rate)
        teaching_strength = min(1.0, teaching_strength)

        # Avoidance drive: motivational signal to avoid the threat
        avoidance_drive = min(1.0, teaching_strength * 1.2)

        # Memory tag strength: how strongly to tag this in memory
        memory_tag = min(1.0, threat_severity * 0.6 + novelty * 0.4)

        self._seen_threats[threat_source] += 1

        return {
            'teaching_strength': round(teaching_strength, 4),
            'avoidance_drive': round(avoidance_drive, 4),
            'memory_tag_strength': round(memory_tag, 4),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            'teaching_rate': self.teaching_rate,
            'seen_threats': dict(self._seen_threats),
        }


# ─── Homeostatic Alert Relay ─────────────────────────────────────────────

# Mapping from threat channel to behavioral drive
_THREAT_TO_DRIVE = {
    'pain': ('pain_avoidance', 'withdraw'),
    'temperature': ('thermoregulation', 'seek_comfort'),
    'visceral_distress': ('visceral_relief', 'rest'),
    'resource_depletion': ('resource_seeking', 'forage'),
    'error_rate': ('error_correction', 'slow_down'),
}


class HomeostaticAlertRelay:
    """
    Relays homeostatic threats to forebrain structures.

    Maps internal threat types to specific behavioral drives
    (hunger, thirst, pain avoidance, temperature seeking) so that
    appropriate corrective behavior can be initiated.
    """

    def relay(
        self,
        threat_type: str,
        severity: float,
        current_state: Dict[str, float],
    ) -> Dict[str, Any]:
        """
        Relay a homeostatic threat to a behavioral drive.

        Args:
            threat_type: Which channel is threatening
            severity: Threat severity [0, 1]
            current_state: Current homeostatic values for context

        Returns:
            Dict with drive_type, drive_intensity, recommended_action_type
        """
        severity = max(0.0, min(1.0, severity))
        drive_type, action_type = _THREAT_TO_DRIVE.get(
            threat_type, ('general_alert', 'attend')
        )

        # Drive intensity: proportional to severity, modulated by
        # how far the current state is from safe baseline
        current_value = float(current_state.get(threat_type, 0.5))
        state_urgency = max(0.0, current_value - 0.5) * 2.0  # 0 if healthy
        drive_intensity = min(1.0, severity * 0.7 + state_urgency * 0.3)

        return {
            'drive_type': drive_type,
            'drive_intensity': round(drive_intensity, 4),
            'recommended_action_type': action_type,
        }


# ─── Parabrachial Nucleus (Main Class) ───────────────────────────────────

class ParabrachialNucleus:
    """
    Complete Parabrachial Nucleus module.

    Functions:
    1. Interoceptive threat detection across multiple channels
    2. Graded alarm signal generation (super-additive for multi-threat)
    3. Aversive teaching signal via CGRP neurons
    4. Homeostatic threat relay to forebrain drive systems
    """

    def __init__(
        self,
        pain_threshold: float = 0.4,
        temperature_threshold: float = 0.6,
        visceral_threshold: float = 0.5,
        alarm_gain: float = 1.0,
        teaching_rate: float = 0.1,
    ):
        thresholds = {
            'pain': pain_threshold,
            'temperature': temperature_threshold,
            'visceral_distress': visceral_threshold,
            'resource_depletion': 0.5,
            'error_rate': 0.5,
        }
        self.threat_detector = InteroceptiveThreatDetector(thresholds)
        self.alarm_generator = AlarmSignalGenerator(gain=alarm_gain)
        self.teaching_signal = AversiveTeachingSignal(teaching_rate=teaching_rate)
        self.relay = HomeostaticAlertRelay()
        self._stats = ParabrachialNucleusStats()
        self._alarm_history = deque(maxlen=200)

    def process(self, interoceptive_signals: Dict[str, float]) -> Dict[str, Any]:
        """
        Full PBN processing cycle.

        Args:
            interoceptive_signals: Channel name -> signal intensity [0, 1]

        Returns:
            Dict with alarm_level, threats_detected, teaching_signal,
            drive_outputs, urgency, n_active_threats
        """
        # 1. Detect threats
        detection = self.threat_detector.detect(interoceptive_signals)
        threat_channels = detection['threat_channels']
        n_active = len(threat_channels)

        # 2. Generate alarm
        alarm = self.alarm_generator.generate_alarm(
            detection['combined_threat'], n_active
        )
        alarm_level = alarm['alarm_level']

        # 3. Aversive teaching for each active threat
        teaching_out: Dict[str, Any] = {}
        for channel in threat_channels:
            severity = float(interoceptive_signals.get(channel, 0.0))
            teaching_out[channel] = self.teaching_signal.compute_teaching(
                channel, severity
            )

        # 4. Homeostatic relay for each active threat
        drive_outputs: List[Dict[str, Any]] = []
        for channel in threat_channels:
            severity = float(interoceptive_signals.get(channel, 0.0))
            drive = self.relay.relay(channel, severity, interoceptive_signals)
            drive_outputs.append(drive)

        # Update stats
        self._stats.total_cycles += 1
        self._alarm_history.append(alarm_level)
        self._stats.avg_alarm_level = float(np.mean(list(self._alarm_history)))
        if detection['threat_detected']:
            self._stats.total_alarms += 1
            for ch in threat_channels:
                self._stats.threat_type_counts[ch] = (
                    self._stats.threat_type_counts.get(ch, 0) + 1
                )
        if teaching_out:
            self._stats.teaching_signals_generated += len(teaching_out)

        return {
            'alarm_level': alarm_level,
            'threats_detected': threat_channels,
            'teaching_signal': teaching_out,
            'drive_outputs': drive_outputs,
            'urgency': alarm['urgency'],
            'n_active_threats': n_active,
        }

    def interoceptive_alarm_priority(
        self,
        threat_signals: Dict[str, float],
    ) -> Dict[str, Any]:
        """
        Prioritize interoceptive threats (Palmiter, 2018).

        PBN is the first relay for visceral danger signals — it prioritizes
        life-threatening interoceptive alarms (hypoxia, pain, nausea) over
        other processing, implementing a biological interrupt system.

        Args:
            threat_signals: Dict of {threat_type: intensity} e.g.
                           {'hypoxia': 0.8, 'pain': 0.5, 'nausea': 0.3}

        Returns:
            Dict with priority_threat, should_interrupt, alarm_level
        """
        if not threat_signals:
            return {'priority_threat': 'none', 'should_interrupt': False, 'alarm_level': 0.0}

        # Find highest priority threat
        priority_threat = max(threat_signals, key=threat_signals.get)
        max_intensity = threat_signals[priority_threat]

        # Should interrupt current processing?
        should_interrupt = max_intensity > 0.6

        # Overall alarm = max threat with contribution from others
        secondary_sum = sum(v for k, v in threat_signals.items() if k != priority_threat)
        alarm_level = min(1.0, max_intensity + secondary_sum * 0.2)

        return {
            'priority_threat': priority_threat,
            'max_intensity': round(max_intensity, 4),
            'alarm_level': round(alarm_level, 4),
            'should_interrupt': should_interrupt,
            'n_active_threats': sum(1 for v in threat_signals.values() if v > 0.1),
        }

    def get_state(self) -> Dict[str, Any]:
        return {
            'stats': self._stats.to_dict(),
            'threat_detector': self.threat_detector.to_dict(),
            'alarm_generator': self.alarm_generator.to_dict(),
            'teaching_signal': self.teaching_signal.to_dict(),
        }

    def get_stats(self) -> ParabrachialNucleusStats:
        return self._stats

    def reset(self):
        self._stats = ParabrachialNucleusStats()
        self._alarm_history.clear()

    def to_dict(self) -> Dict[str, Any]:
        return self.get_state()

    @classmethod
    def from_yaml(cls, config: Dict[str, Any]) -> 'ParabrachialNucleus':
        cfg = config.get('parabrachial_nucleus', {})
        return cls(
            pain_threshold=cfg.get('pain_threshold', 0.4),
            temperature_threshold=cfg.get('temperature_threshold', 0.6),
            visceral_threshold=cfg.get('visceral_threshold', 0.5),
            alarm_gain=cfg.get('alarm_gain', 1.0),
            teaching_rate=cfg.get('teaching_rate', 0.1),
        )
