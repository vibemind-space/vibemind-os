"""
Inferior Olive (IO) Module - Climbing Fiber Error Signal Generator

The inferior olive is a medullary nucleus that serves as the SOLE source
of climbing fiber input to the cerebellum. It plays a critical role in
motor and cognitive learning by providing error signals that drive
synaptic plasticity in cerebellar Purkinje cells via complex spikes.

Neuroscience basis:
- Llinas & Yarom (1981): IO neurons exhibit subthreshold ~10Hz oscillations
  driven by voltage-dependent calcium conductances and gap-junction coupling
- Ito (2001): Climbing fibers carry error signals that instruct cerebellar
  Purkinje cells, driving long-term depression at parallel fiber synapses
- Welsh et al. (1995): IO neurons are electrically coupled via gap junctions,
  enabling synchronized oscillatory activity across olivary populations
- Llinás (2009): IO timing signals provide a temporal framework for
  coordinating multi-joint motor sequences and cognitive action plans

Key functions:
- Error signal generation: prediction error -> complex spike probability
- Timing signal: subthreshold 10Hz oscillations provide temporal reference
- Teaching signal: climbing fiber output instructs cerebellar learning
- Error accumulation: tracks persistent vs transient error patterns

Integration:
- Input: Prediction errors from cortex/red nucleus, action timing from
         motor cortex, sensory feedback from spinal cord
- Output: Climbing fibers -> cerebellar Purkinje cells (complex spikes),
          timing reference -> cerebellum, error trend -> meta-cognition
"""

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger('brain.inferior_olive')


@dataclass
class InferiorOliveStats:
    """Inferior olive statistics."""
    total_signals: int = 0
    avg_error_magnitude: float = 0.0
    spike_count: int = 0
    avg_sync_quality: float = 0.0
    persistent_error_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_signals': self.total_signals,
            'avg_error_magnitude': round(self.avg_error_magnitude, 4),
            'spike_count': self.spike_count,
            'avg_sync_quality': round(self.avg_sync_quality, 4),
            'persistent_error_count': self.persistent_error_count,
        }


class OlivaryOscillator:
    """
    Subthreshold ~10Hz oscillations of inferior olive neurons.

    Llinas & Yarom (1981): IO neurons generate intrinsic subthreshold
    oscillations at approximately 10Hz, driven by low-threshold calcium
    conductances. These oscillations are synchronized across olivary
    populations via gap-junction (electrical) coupling.

    The oscillator provides a temporal scaffold that the climbing fiber
    system uses to time error signals and coordinate motor sequences.
    """

    def __init__(
        self,
        frequency: float = 10.0,
        coupling_strength: float = 0.3,
    ):
        self._frequency = frequency
        self._coupling_strength = coupling_strength
        self._phase = 0.0
        self._amplitude = 1.0
        self._neighbor_phases: List[float] = []

    def oscillate(self, dt: float = 0.01) -> Dict[str, float]:
        """
        Advance the oscillator by one time step.

        Args:
            dt: Time step in seconds (default 10ms).

        Returns:
            Dict with phase (0-2pi), amplitude, frequency.
        """
        # Phase advance: d(phase)/dt = 2*pi*f
        self._phase += 2.0 * np.pi * self._frequency * dt
        self._phase = self._phase % (2.0 * np.pi)

        # Gap-junction coupling: synchronisation tendency pulls phase
        # toward the mean of neighbouring olivary neurons.
        if self._neighbor_phases:
            mean_neighbor = float(np.mean(self._neighbor_phases))
            phase_diff = mean_neighbor - self._phase
            # Wrap to [-pi, pi]
            phase_diff = (phase_diff + np.pi) % (2.0 * np.pi) - np.pi
            self._phase += self._coupling_strength * phase_diff * dt
            self._phase = self._phase % (2.0 * np.pi)

        # Amplitude is modulated by coupling coherence
        if self._neighbor_phases:
            coherence = float(np.abs(np.mean(
                np.exp(1j * np.array(self._neighbor_phases))
            )))
            self._amplitude = 0.5 + 0.5 * coherence
        else:
            self._amplitude = 1.0

        return {
            'phase': round(self._phase, 4),
            'amplitude': round(self._amplitude, 4),
            'frequency': self._frequency,
        }

    def set_neighbor_phases(self, phases: List[float]):
        """Update neighbour phase list for gap-junction coupling."""
        self._neighbor_phases = phases

    def to_dict(self) -> Dict[str, Any]:
        return {
            'phase': round(self._phase, 4),
            'amplitude': round(self._amplitude, 4),
            'frequency': self._frequency,
            'coupling_strength': self._coupling_strength,
        }


class ClimbingFiberGenerator:
    """
    Generates error-driven climbing fiber teaching signals.

    Ito (2001): Climbing fibers convey error signals from the inferior
    olive to cerebellar Purkinje cells. When a climbing fiber fires,
    it produces a distinctive "complex spike" in the target Purkinje
    cell, which triggers long-term depression of recently active
    parallel fiber synapses -- the core mechanism of cerebellar learning.

    The probability of a complex spike is proportional to the magnitude
    of the prediction error, and the teaching signal encodes the
    direction (what needs to be corrected).
    """

    def __init__(self, error_threshold: float = 0.1):
        self._error_threshold = error_threshold
        self._signal_history = deque(maxlen=200)

    def generate_signal(
        self,
        prediction: np.ndarray,
        actual: np.ndarray,
    ) -> Dict[str, Any]:
        """
        Generate a climbing fiber teaching signal from prediction error.

        Args:
            prediction: Predicted state/outcome vector.
            actual: Actual state/outcome vector.

        Returns:
            Dict with error_vector, error_magnitude, spike_probability,
            and teaching_signal.
        """
        prediction = np.asarray(prediction, dtype=np.float64)
        actual = np.asarray(actual, dtype=np.float64)

        error_vector = actual - prediction
        error_magnitude = float(np.linalg.norm(error_vector))

        # Complex spike probability saturates at large errors
        spike_probability = float(np.clip(
            1.0 - np.exp(-error_magnitude / max(self._error_threshold, 1e-8)),
            0.0,
            1.0,
        ))

        # Teaching signal: error direction gated by spike probability
        norm = error_magnitude if error_magnitude > 1e-8 else 1.0
        teaching_signal = (error_vector / norm) * spike_probability

        self._signal_history.append(error_magnitude)

        return {
            'error_vector': error_vector.tolist(),
            'error_magnitude': round(error_magnitude, 4),
            'spike_probability': round(spike_probability, 4),
            'teaching_signal': teaching_signal.tolist(),
        }

    def get_avg_error(self) -> float:
        if not self._signal_history:
            return 0.0
        return float(np.mean(list(self._signal_history)))

    def to_dict(self) -> Dict[str, Any]:
        return {
            'error_threshold': self._error_threshold,
            'avg_error': round(self.get_avg_error(), 4),
            'history_len': len(self._signal_history),
        }


class TimingSignalGenerator:
    """
    Provides a timing reference for action sequences.

    The olivary oscillation serves as an internal metronome. Each action
    step in a sequence is mapped onto a phase of the oscillation so that
    the system can detect whether actions are executed on-beat or
    off-beat, and how well the action sequence is synchronised with
    the internal clock.
    """

    def get_timing_signal(
        self,
        oscillator_phase: float,
        action_step: int,
        total_steps: int,
    ) -> Dict[str, float]:
        """
        Map an action step onto the olivary oscillation.

        Args:
            oscillator_phase: Current oscillator phase (0-2pi).
            action_step: Current step in the action sequence (0-indexed).
            total_steps: Total number of steps in the sequence (>= 1).

        Returns:
            Dict with progress_fraction, timing_error, sync_quality.
        """
        total_steps = max(total_steps, 1)
        progress_fraction = action_step / total_steps

        # Expected phase for this step in the action sequence
        expected_phase = (2.0 * np.pi * progress_fraction) % (2.0 * np.pi)

        # Timing error: circular distance between expected and actual phase
        phase_diff = oscillator_phase - expected_phase
        timing_error = abs((phase_diff + np.pi) % (2.0 * np.pi) - np.pi)

        # Sync quality: 1.0 when perfectly on-beat, 0.0 when maximally off
        sync_quality = float(np.cos(timing_error) * 0.5 + 0.5)

        return {
            'progress_fraction': round(progress_fraction, 4),
            'timing_error': round(timing_error, 4),
            'sync_quality': round(sync_quality, 4),
        }


class ErrorAccumulator:
    """
    Tracks error patterns over time.

    Distinguishes persistent errors (errors that do not decrease over
    successive evaluations, indicating a systematic mismatch) from
    transient errors (brief spikes that resolve on their own).
    """

    def __init__(self, window: int = 50, persistence_threshold: int = 20):
        self._window = window
        self._persistence_threshold = persistence_threshold
        self._errors = deque(maxlen=window)

    def accumulate(self, error_magnitude: float) -> Dict[str, float]:
        """
        Accumulate an error sample and compute running statistics.

        Args:
            error_magnitude: Current error magnitude.

        Returns:
            Dict with running_mean, running_var, error_trend, is_persistent.
        """
        self._errors.append(error_magnitude)
        errors = list(self._errors)

        running_mean = float(np.mean(errors))
        running_var = float(np.var(errors)) if len(errors) > 1 else 0.0

        # Trend detection: compare first half vs second half
        if len(errors) >= 10:
            half = len(errors) // 2
            first_half_mean = float(np.mean(errors[:half]))
            second_half_mean = float(np.mean(errors[half:]))
            diff = second_half_mean - first_half_mean
            if diff > 0.02:
                error_trend = 'increasing'
            elif diff < -0.02:
                error_trend = 'decreasing'
            else:
                error_trend = 'stable'
        else:
            error_trend = 'stable'

        # Persistence: error stays above threshold for extended window
        is_persistent = False
        if len(errors) >= self._persistence_threshold:
            recent = errors[-self._persistence_threshold:]
            if all(e > 0.05 for e in recent):
                is_persistent = True

        return {
            'running_mean': round(running_mean, 4),
            'running_var': round(running_var, 4),
            'error_trend': error_trend,
            'is_persistent': is_persistent,
        }

    def to_dict(self) -> Dict[str, Any]:
        errors = list(self._errors)
        return {
            'window': self._window,
            'n_samples': len(errors),
            'running_mean': round(float(np.mean(errors)), 4) if errors else 0.0,
        }


class InferiorOlive:
    """
    Complete Inferior Olive module.

    Combines:
    1. OlivaryOscillator - subthreshold 10Hz oscillations
    2. ClimbingFiberGenerator - error-driven teaching signals
    3. TimingSignalGenerator - action sequence timing reference
    4. ErrorAccumulator - persistent vs transient error tracking

    Usage:
        io = InferiorOlive()
        result = io.process(
            prediction=np.array([0.5, 0.5]),
            actual=np.array([0.7, 0.3]),
            action_step=2,
            total_steps=10,
        )
    """

    def __init__(
        self,
        oscillation_freq: float = 10.0,
        coupling_strength: float = 0.3,
        error_threshold: float = 0.1,
        dt: float = 0.01,
    ):
        self.oscillator = OlivaryOscillator(oscillation_freq, coupling_strength)
        self.climbing_fiber = ClimbingFiberGenerator(error_threshold)
        self.timing = TimingSignalGenerator()
        self.error_accumulator = ErrorAccumulator()
        self._dt = dt
        self._stats = InferiorOliveStats()

    def process(
        self,
        prediction: np.ndarray,
        actual: np.ndarray,
        action_step: int = 0,
        total_steps: int = 1,
    ) -> Dict[str, Any]:
        """
        Full inferior olive processing cycle.

        1. Advance oscillator
        2. Generate climbing fiber error / teaching signal
        3. Compute timing signal
        4. Accumulate error statistics

        Args:
            prediction: Predicted outcome vector.
            actual: Actual outcome vector.
            action_step: Current step in action sequence.
            total_steps: Total steps in action sequence.

        Returns:
            Dict with error_magnitude, teaching_signal, spike_probability,
            timing_signal, oscillator_phase, error_trend.
        """
        # 1. Oscillator tick
        osc = self.oscillator.oscillate(self._dt)

        # 2. Climbing fiber signal
        cf = self.climbing_fiber.generate_signal(prediction, actual)

        # 3. Timing signal
        ts = self.timing.get_timing_signal(osc['phase'], action_step, total_steps)

        # 4. Error accumulation
        ea = self.error_accumulator.accumulate(cf['error_magnitude'])

        # Update stats
        self._stats.total_signals += 1
        self._stats.avg_error_magnitude = self.climbing_fiber.get_avg_error()
        if cf['spike_probability'] > 0.5:
            self._stats.spike_count += 1
        n = self._stats.total_signals
        self._stats.avg_sync_quality = (
            self._stats.avg_sync_quality * (n - 1) + ts['sync_quality']
        ) / n
        if ea['is_persistent']:
            self._stats.persistent_error_count += 1

        return {
            'error_magnitude': cf['error_magnitude'],
            'teaching_signal': cf['teaching_signal'],
            'spike_probability': cf['spike_probability'],
            'timing_signal': ts,
            'oscillator_phase': osc['phase'],
            'error_trend': ea['error_trend'],
        }

    def temporal_error_pattern(self) -> Dict[str, Any]:
        """
        Analyze temporal pattern of errors for motor learning (Welsh et al., 1995).

        The IO's subthreshold oscillations (~10Hz) create time windows
        for error detection. Errors arriving in-phase with IO oscillations
        are transmitted as climbing fiber signals; out-of-phase errors are
        suppressed. This acts as a temporal filter on learning signals.

        Returns:
            Dict with error_rate, error_trend, learning_windows, phase_sensitivity
        """
        ea = self.error_accumulator.to_dict()
        osc = self.oscillator.to_dict()

        error_trend = ea.get('error_trend', 0.0)
        avg_error = ea.get('avg_error', 0.0)
        phase = osc.get('phase', 0.0)

        # Phase sensitivity: errors near oscillation peak are amplified
        phase_sensitivity = 0.5 + 0.5 * float(np.cos(phase))

        # Learning window: is IO in a receptive phase?
        in_learning_window = phase_sensitivity > 0.7

        # Error rate classification
        if avg_error > 0.5:
            error_regime = 'high_error_rapid_learning'
        elif avg_error > 0.2:
            error_regime = 'moderate_error_refinement'
        else:
            error_regime = 'low_error_maintenance'

        return {
            'error_regime': error_regime,
            'error_trend': round(error_trend, 4),
            'avg_error': round(avg_error, 4),
            'phase_sensitivity': round(phase_sensitivity, 4),
            'in_learning_window': in_learning_window,
        }

    def get_state(self) -> Dict[str, Any]:
        return {
            'stats': self._stats.to_dict(),
            'oscillator': self.oscillator.to_dict(),
            'climbing_fiber': self.climbing_fiber.to_dict(),
            'error_accumulator': self.error_accumulator.to_dict(),
        }

    def get_stats(self) -> InferiorOliveStats:
        return self._stats

    def reset(self):
        self._stats = InferiorOliveStats()

    def to_dict(self) -> Dict[str, Any]:
        return self.get_state()

    @classmethod
    def from_yaml(cls, config: Dict[str, Any]) -> 'InferiorOlive':
        cfg = config.get('inferior_olive', {})
        return cls(
            oscillation_freq=cfg.get('oscillation_freq', 10.0),
            coupling_strength=cfg.get('coupling_strength', 0.3),
            error_threshold=cfg.get('error_threshold', 0.1),
            dt=cfg.get('dt', 0.01),
        )
