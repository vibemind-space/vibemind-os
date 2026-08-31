"""
Thalamic Adapter — Input Encoding to ThalamoPC6

Maps arbitrary brain inputs (chat messages, sensor readings, internal states,
structured data, context, threats) into ThalamoPC6's 6 modalities, runs a
thalamic step, and returns gated routing results.

Encoding strategy: deterministic hash-based projection. Each key-value pair
in the data dict is hashed (SHA-256) to seed a numpy RNG that produces
vector elements. Numeric magnitudes are preserved by scaling.

Modality mapping:
    vision (128d)     <- structured data (JSON, code, files)
    audio (64d)       <- natural language text (chat, logs)
    touch (32d)       <- system sensors (CPU, memory, disk)
    taste (16d)       <- internal state (emotions, drives)
    vestibular (16d)  <- spatial/temporal context (time, session)
    threat (8d)       <- anomalies & urgency (errors, safety flags)
"""

import hashlib
import json
import numpy as np
from typing import Dict, List, Optional, Any

from core.thalamo_pc_live import ThalamoPC6


# Canonical dimensions for each modality
MODALITY_DIMS = {
    "vision": 128,
    "audio": 64,
    "touch": 32,
    "taste": 16,
    "vestibular": 16,
    "threat": 8,
}

# Which input types map to which primary modality
INPUT_TYPE_TO_MODALITY = {
    "chat": "audio",
    "sensor": "touch",
    "internal": "taste",
    "structured": "vision",
    "context": "vestibular",
    "threat": "threat",
}

# All valid modality names
ALL_MODALITIES = list(MODALITY_DIMS.keys())


def _hash_to_seed(text: str) -> int:
    """Deterministic SHA-256 hash of a string -> 32-bit seed."""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _extract_numeric(value: Any) -> float:
    """
    Pull a float magnitude from a value, returning 0.0 for non-numeric types.
    """
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, str):
        try:
            return float(value)
        except (ValueError, TypeError):
            return float(len(value)) * 0.01  # text length heuristic
    if isinstance(value, (list, tuple)):
        return float(len(value)) * 0.1
    if isinstance(value, dict):
        return float(len(value)) * 0.1
    return 0.0


def _encode_dict_to_vector(data: Dict[str, Any], dim: int, salt: str = "") -> np.ndarray:
    """
    Deterministic hash-based projection of a dict into a fixed-dimension vector.

    For each key-value pair:
      1. Hash ``f"{salt}:{key}={value}"`` with SHA-256 to get a seed.
      2. Use that seed with ``np.random.default_rng`` to fill a ``dim``-length
         sub-vector with standard-normal draws.
      3. Scale by the numeric magnitude extracted from the value.
    All sub-vectors are summed element-wise.  The result is normalised to the
    unit range [0, 1] if it has non-zero norm.

    Args:
        data: key-value pairs to encode.
        dim: target vector dimensionality.
        salt: optional prefix to differentiate modality encodings.

    Returns:
        np.ndarray of shape (dim,), values in [0, 1].
    """
    vec = np.zeros(dim, dtype=np.float64)
    if not data:
        return vec

    for key, value in data.items():
        # Serialise value for hashing
        try:
            val_str = json.dumps(value, default=str, sort_keys=True)
        except (TypeError, ValueError):
            val_str = str(value)

        seed = _hash_to_seed(f"{salt}:{key}={val_str}")
        rng = np.random.default_rng(seed)
        sub = rng.standard_normal(dim)

        magnitude = _extract_numeric(value)
        # Ensure at least a small magnitude so the key still contributes
        scale = max(abs(magnitude), 0.1)
        vec += sub * scale

    # Normalise to unit range
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec


class ThalamicAdapter:
    """
    Adapter between arbitrary brain inputs and ThalamoPC6.

    Encodes each input type into the appropriate primary modality, fills the
    remaining modalities with zeros, drives a ThalamoPC6 step, and wraps the
    result in a brain-friendly dict.
    """

    def __init__(self, thalamus: Optional[ThalamoPC6] = None):
        """
        Args:
            thalamus: an existing ThalamoPC6 instance. If *None*, a fresh
                      one is created with default parameters.
        """
        self.thalamus = thalamus if thalamus is not None else ThalamoPC6()

    # ------------------------------------------------------------------
    # Encoding
    # ------------------------------------------------------------------

    def encode_input(
        self, input_type: str, data: Dict[str, Any]
    ) -> Dict[str, np.ndarray]:
        """
        Encode *data* according to *input_type* into ThalamoPC6's 6 modality
        vectors.

        Unknown input types fall back to ``"audio"`` (natural-language catch-all).

        Args:
            input_type: one of ``"chat"``, ``"sensor"``, ``"internal"``,
                        ``"structured"``, ``"context"``, ``"threat"``.
            data: key-value payload to encode.

        Returns:
            Dict mapping each modality name to a numpy array of the correct
            dimension.  Non-primary modalities are zero vectors.
        """
        # Resolve the primary modality for this input type
        primary = INPUT_TYPE_TO_MODALITY.get(input_type, "audio")

        encoded: Dict[str, np.ndarray] = {}
        for modality, dim in MODALITY_DIMS.items():
            if modality == primary:
                encoded[modality] = _encode_dict_to_vector(
                    data, dim, salt=input_type
                )
            else:
                encoded[modality] = np.zeros(dim, dtype=np.float64)

        return encoded

    # ------------------------------------------------------------------
    # Full pipeline
    # ------------------------------------------------------------------

    def process(
        self,
        input_type: str,
        data: Dict[str, Any],
        ctx: Optional[np.ndarray] = None,
    ) -> Dict[str, Any]:
        """
        End-to-end pipeline: encode input -> ThalamoPC6 step -> wrap result.

        Args:
            input_type: type label (see ``encode_input``).
            data: payload dict.
            ctx: optional 6-dim context vector for ThalamoPC6.

        Returns:
            Dict with keys:
                ``gates``              - dict of modality -> gate weight (sum = 1.0)
                ``routed_output``      - ThalamoPC6's *y* array
                ``active_modalities``  - modalities with gate > 0.1
                ``prediction_errors``  - dict of modality -> PE float
                ``thalamic_state``     - dict of modality -> latent vector
                ``time_step``          - int
        """
        # 1) Encode
        x = self.encode_input(input_type, data)

        # 2) Thalamic step
        result = self.thalamus.step(x, ctx=ctx)

        # 3) Unpack gate vector into a named dict
        g_array: np.ndarray = result["g"]
        gates: Dict[str, float] = {
            m: float(g_array[i]) for i, m in enumerate(ALL_MODALITIES)
        }

        # 4) Determine active modalities (gate > 0.1)
        active: List[str] = [m for m, gv in gates.items() if gv > 0.1]

        # 5) Prediction errors
        pe_raw = result["pe"]
        prediction_errors: Dict[str, float] = {}
        for m in ALL_MODALITIES:
            if isinstance(pe_raw.get(m), (int, float, np.floating)):
                prediction_errors[m] = float(pe_raw[m])
            else:
                prediction_errors[m] = float(np.linalg.norm(pe_raw.get(m, 0.0)))

        # 6) Thalamic state (copy latent vectors)
        v_next = result["v_next"]
        thalamic_state: Dict[str, np.ndarray] = {
            m: np.array(v_next[m]) for m in ALL_MODALITIES
        }

        return {
            "gates": gates,
            "routed_output": result["y"],
            "active_modalities": active,
            "prediction_errors": prediction_errors,
            "thalamic_state": thalamic_state,
            "time_step": result["t"],
        }
