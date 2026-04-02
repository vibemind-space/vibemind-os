"""
Memory Bridge -- connects memory-related brain modules (SeptalNuclei,
EntorhinalCortex, MammillaryBodies, InferiorOlive) to the Radial
Attention Network.

Translates ring activations and prediction errors into memory-system
signals (theta rhythm, encoding strength, consolidation, teaching
errors) that modulate RingLayers and support memory operations.

Hook fields (clamped to [0, 1]):
    H21: theta_power   -- SeptalNuclei theta power
    H22: consolidation_strength -- MammillaryBodies relay strength

Inter-module coupling:
    - SN theta_power (tick t) -> MB importance (tick t+1)   [1-tick delay]
    - EC memory_gateway (tick t) -> MB hippocampal_signal (tick t)  [same tick]
"""
import logging
from dataclasses import dataclass
from typing import Any, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class MemoryState:
    """Snapshot of memory module outputs for one tick.

    SeptalNuclei: theta rhythm parameters.
    EntorhinalCortex: memory gateway encoding strength.
    MammillaryBodies: consolidation and relay strength.
    InferiorOlive: teaching signal and error magnitude.
    """
    # SeptalNuclei outputs
    theta_power: float = 0.5              # [0, 1] H21 hook-clamped
    theta_frequency: float = 6.0          # [4, 8] Hz
    coupling_strength: float = 0.5        # [0, 1] theta-gamma coupling

    # MammillaryBodies outputs
    consolidation_strength: float = 0.5   # [0, 1] H22 hook-clamped
    relay_strength: float = 0.5           # relay magnitude

    # InferiorOlive outputs
    teaching_signal: float = 0.0          # climbing fiber signal
    error_magnitude: float = 0.0          # error magnitude

    # EntorhinalCortex outputs
    memory_gateway: float = 0.5           # [0, 1] encoding norm


class MemoryBridge:
    """Mediates between RadialAttentionNetwork and memory-related brain modules.

    After each forward pass, call update(ring_activations, prediction_errors)
    to compute a MemoryState.  The state is used on the NEXT forward pass
    (1-tick delay, biologically correct).

    Inter-module coupling (tick t -> tick t+1):
        - SN theta_power -> MB importance  (1-tick delay)
        - EC memory_gateway -> MB hippocampal_signal (same tick)

    Args:
        septal_nuclei: SeptalNuclei instance (or None for skeleton mode)
        entorhinal_cortex: EntorhinalCortex instance (or None)
        mammillary_bodies: MammillaryBodies instance (or None)
        inferior_olive: InferiorOlive instance (or None)
    """

    def __init__(self, septal_nuclei=None, entorhinal_cortex=None,
                 mammillary_bodies=None, inferior_olive=None):
        self._septal_nuclei = septal_nuclei
        self._entorhinal_cortex = entorhinal_cortex
        self._mammillary_bodies = mammillary_bodies
        self._inferior_olive = inferior_olive
        self._state = MemoryState()
        self._tick_count = 0

        # Cache for inter-module coupling (previous tick)
        self._prev_theta_power = 0.5

        logger.info("MemoryBridge initialized (SN + EC + MB + IO)")

    def update(self, ring_activations: list, prediction_errors: list) -> MemoryState:
        """Compute MemoryState from current ring activations and prediction errors.

        Args:
            ring_activations: List of 5 numpy arrays
                [Ring1(64), Ring2(128), Ring3(256), Ring4(256), Ring5(128)]
            prediction_errors: List of 4 floats [PE1, PE2, PE3, PE4]

        Returns:
            MemoryState for use on next tick.
        """
        # If all modules are None, return default state (skeleton mode)
        if (self._septal_nuclei is None and self._entorhinal_cortex is None
                and self._mammillary_bodies is None
                and self._inferior_olive is None):
            self._tick_count += 1
            return self._state

        # Convert tensors to numpy if needed
        acts = []
        for a in ring_activations:
            if hasattr(a, 'detach'):
                acts.append(a.detach().cpu().numpy().flatten())
            else:
                acts.append(np.asarray(a).flatten())

        ring1 = acts[0]  # 64-dim
        ring2 = acts[1]  # 128-dim
        avg_pe = float(np.mean(prediction_errors)) if prediction_errors else 0.1

        # --- SeptalNuclei: theta rhythm ---
        sn_theta_power = 0.5
        sn_theta_freq = 6.0
        sn_coupling = 0.5
        if self._septal_nuclei is not None:
            try:
                sn_result = self._septal_nuclei.process(
                    arousal=0.5,
                    memory_demand=avg_pe,
                )
                sn_theta_power = sn_result.get('theta_power', 0.5)
                sn_theta_freq = sn_result.get('theta_frequency', 6.0)
                sn_coupling = sn_result.get('coupling_strength', 0.5)
            except Exception:
                logger.warning("SeptalNuclei.process() failed, using defaults")

        # --- EntorhinalCortex: memory gateway ---
        memory_gateway = 0.5
        if self._entorhinal_cortex is not None:
            try:
                ec_encoding = self._entorhinal_cortex.process_input(ring1)
                ec_norm = float(np.linalg.norm(ec_encoding))
                memory_gateway = min(1.0, ec_norm / (np.sqrt(len(ec_encoding)) + 1e-8))
            except Exception:
                logger.warning("EntorhinalCortex.process_input() failed, using defaults")

        # --- MammillaryBodies: consolidation relay ---
        mb_consolidation = 0.5
        mb_relay = 0.5
        if self._mammillary_bodies is not None:
            try:
                mb_result = self._mammillary_bodies.process(
                    hippocampal_signal=memory_gateway,
                    importance=self._prev_theta_power,
                    emotional_arousal=0.5,
                )
                mb_consolidation = mb_result.get('consolidation_strength', 0.5)
                mb_relay = mb_result.get('relay_strength', 0.5)
            except Exception:
                logger.warning("MammillaryBodies.process() failed, using defaults")

        # --- InferiorOlive: teaching signal ---
        io_teaching = 0.0
        io_error = 0.0
        if self._inferior_olive is not None:
            try:
                io_dim = min(len(ring1), len(ring2), 8)
                io_result = self._inferior_olive.process(
                    prediction=ring2[:io_dim],
                    actual=ring1[:io_dim],
                )
                # teaching_signal can be a list or scalar; take mean for state
                ts = io_result.get('teaching_signal', 0.0)
                if isinstance(ts, (list, np.ndarray)):
                    io_teaching = float(np.mean(ts))
                else:
                    io_teaching = float(ts)
                io_error = float(io_result.get('error_magnitude', 0.0))
            except Exception:
                logger.warning("InferiorOlive.process() failed, using defaults")

        # Build MemoryState (clamp hook fields to [0, 1])
        self._state = MemoryState(
            theta_power=float(np.clip(sn_theta_power, 0.0, 1.0)),
            theta_frequency=sn_theta_freq,
            coupling_strength=sn_coupling,
            consolidation_strength=float(np.clip(mb_consolidation, 0.0, 1.0)),
            relay_strength=mb_relay,
            teaching_signal=io_teaching,
            error_magnitude=io_error,
            memory_gateway=memory_gateway,
        )

        # Cache for inter-module coupling on next tick
        self._prev_theta_power = sn_theta_power

        self._tick_count += 1
        return self._state

    def get_state(self) -> 'MemoryState':
        """Return current MemoryState dataclass."""
        return self._state
