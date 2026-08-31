"""
HookCoefficients — learnable coefficients for the 29 modulation hooks.

Each hook in ModulationContext.compute() is parameterized by (offset, scale)
coefficients. During dream cycles, these coefficients are tuned via finite-
difference gradient descent to reduce prediction error.

Coefficient names follow: h{N}_{target}_{source}_{component}
  e.g. h1_att_ne_offset = 0.5, h1_att_ne_scale = 1.0

Persistence: save/load to configs/hook_coefficients.json.
"""

import json
import logging
import os
from dataclasses import asdict, dataclass, fields
from typing import Dict, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Default coefficient file path
DEFAULT_COEFF_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'configs', 'hook_coefficients.json',
)

# Bounds for all coefficients
COEFF_MIN = 0.1
COEFF_MAX = 5.0


@dataclass
class HookCoefficients:
    """29 hooks × (offset, scale) = learnable coefficient set.

    Each pair defines: factor *= offset + scale * bridge_field
    Default values match the original hardcoded formulas exactly.

    Hook   Formula                                        Target Factor
    ─────  ─────────────────────────────────────────────  ─────────────
    H1     att *= offset + ne_gain                        attention_gain
    H2a    prec *= offset + dopamine                      precision_boost
    H2b    prec *= 1.0 - scale * anti_reward              precision_boost
    H3     ffn *= offset + acetylcholine                  ffn_throughput
    H4     ffn *= offset + scale * serotonin              ffn_throughput
    H6     thr *= offset - explore_ratio                  threshold_mod
    H8     thr *= offset - scale * conflict               threshold_mod
    H9     prec *= offset + scale * subjective_value      precision_boost
    H10    att *= offset + scale * arousal                attention_gain
    H11    prec *= offset + scale * salience              precision_boost
    H12    thr *= offset - scale * nogo_drive             threshold_mod
    H13    ffn *= offset + scale * urgency                ffn_throughput
    H14    att *= offset + arousal                        attention_gain
    H15    ffn *= offset + scale * histamine              ffn_throughput
    H16    thr *= offset + scale * melatonin              threshold_mod
    H17    ffn *= offset + scale * model_confidence       ffn_throughput
    H18    att *= offset + scale * action_tendency        attention_gain
    H19    att *= offset + scale * defense_intensity      attention_gain
    H20    ffn *= offset - scale * anxiety_level          ffn_throughput
    H21    att *= offset + scale * theta_power            attention_gain
    H22    prec *= offset + scale * consolidation         precision_boost
    H23    att *= offset + scale * binding_strength       attention_gain
    H24    ffn *= offset - scale * dmn_activation         ffn_throughput
    H25    att *= offset + scale * orienting_saliency     attention_gain
    H26    thr *= offset - scale * afferent_strength      threshold_mod
    H27    prec *= offset + scale * liking                precision_boost
    H28    att *= offset + scale * social_salience        attention_gain
    H29    prec *= offset + scale * familiarity           precision_boost
    """
    # H1: NE gain -> attention
    h1_att_ne_offset: float = 0.5
    h1_att_ne_scale: float = 1.0
    # H2a: DA -> precision
    h2a_prec_da_offset: float = 0.5
    h2a_prec_da_scale: float = 1.0
    # H2b: anti_reward -> precision (subtractive)
    h2b_prec_antirwd_scale: float = 0.3
    # H3: ACh -> FFN
    h3_ffn_ach_offset: float = 0.5
    h3_ffn_ach_scale: float = 1.0
    # H4: 5-HT -> FFN
    h4_ffn_5ht_offset: float = 0.8
    h4_ffn_5ht_scale: float = 0.4
    # H6: explore_ratio -> threshold
    h6_thr_explore_offset: float = 1.5
    h6_thr_explore_scale: float = 1.0
    # H8: ACC conflict -> threshold
    h8_thr_conflict_offset: float = 1.0
    h8_thr_conflict_scale: float = 0.3
    # H9: OFC value -> precision
    h9_prec_value_offset: float = 0.7
    h9_prec_value_scale: float = 0.6
    # H10: limbic arousal -> attention
    h10_att_arousal_offset: float = 0.7
    h10_att_arousal_scale: float = 0.6
    # H11: limbic salience -> precision
    h11_prec_salience_offset: float = 0.8
    h11_prec_salience_scale: float = 0.4
    # H12: nogo_drive -> threshold
    h12_thr_nogo_offset: float = 1.0
    h12_thr_nogo_scale: float = 0.2
    # H13: urgency -> FFN
    h13_ffn_urgency_offset: float = 0.8
    h13_ffn_urgency_scale: float = 0.4
    # H14: sleep arousal -> attention
    h14_att_sleep_offset: float = 0.5
    h14_att_sleep_scale: float = 1.0
    # H15: histamine -> FFN
    h15_ffn_hist_offset: float = 0.5
    h15_ffn_hist_scale: float = 0.5
    # H16: melatonin -> threshold
    h16_thr_mel_offset: float = 1.0
    h16_thr_mel_scale: float = 0.3
    # H17: motor confidence -> FFN
    h17_ffn_motconf_offset: float = 0.8
    h17_ffn_motconf_scale: float = 0.4
    # H18: action tendency -> attention
    h18_att_action_offset: float = 0.8
    h18_att_action_scale: float = 0.4
    # H19: defense intensity -> attention
    h19_att_defense_offset: float = 0.7
    h19_att_defense_scale: float = 0.8
    # H20: anxiety -> FFN (subtractive)
    h20_ffn_anxiety_offset: float = 1.0
    h20_ffn_anxiety_scale: float = 0.4
    # H21: theta power -> attention
    h21_att_theta_offset: float = 0.8
    h21_att_theta_scale: float = 0.4
    # H22: consolidation -> precision
    h22_prec_consol_offset: float = 0.8
    h22_prec_consol_scale: float = 0.4
    # H23: binding strength -> attention
    h23_att_binding_offset: float = 0.7
    h23_att_binding_scale: float = 0.6
    # H24: DMN activation -> FFN (subtractive)
    h24_ffn_dmn_offset: float = 1.0
    h24_ffn_dmn_scale: float = 0.3
    # H25: orienting saliency -> attention
    h25_att_orient_offset: float = 0.8
    h25_att_orient_scale: float = 0.4
    # H26: afferent strength -> threshold (subtractive)
    h26_thr_afferent_offset: float = 1.0
    h26_thr_afferent_scale: float = 0.2
    # H27: liking -> precision
    h27_prec_liking_offset: float = 0.9
    h27_prec_liking_scale: float = 0.2
    # H28: social salience -> attention
    h28_att_social_offset: float = 0.9
    h28_att_social_scale: float = 0.2
    # H29: familiarity -> precision
    h29_prec_fam_offset: float = 0.9
    h29_prec_fam_scale: float = 0.2

    def to_vector(self) -> np.ndarray:
        """Flatten all coefficients to a numpy vector."""
        return np.array([getattr(self, f.name) for f in fields(self)],
                        dtype=np.float64)

    def from_vector(self, vec: np.ndarray) -> 'HookCoefficients':
        """Load coefficients from a numpy vector (clamped to bounds)."""
        for i, f in enumerate(fields(self)):
            val = float(np.clip(vec[i], COEFF_MIN, COEFF_MAX))
            setattr(self, f.name, val)
        return self

    def clone(self) -> 'HookCoefficients':
        """Deep copy."""
        hc = HookCoefficients()
        for f in fields(self):
            setattr(hc, f.name, getattr(self, f.name))
        return hc

    @property
    def num_coefficients(self) -> int:
        """Number of learnable coefficients."""
        return len(fields(self))

    def save(self, path: Optional[str] = None) -> str:
        """Save coefficients to JSON file."""
        path = path or DEFAULT_COEFF_PATH
        data = asdict(self)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
        logger.info(f"Hook coefficients saved to {path}")
        return path

    @classmethod
    def load(cls, path: Optional[str] = None) -> 'HookCoefficients':
        """Load coefficients from JSON file. Returns defaults if file missing."""
        path = path or DEFAULT_COEFF_PATH
        if not os.path.exists(path):
            logger.info("No hook coefficients file found, using defaults")
            return cls()
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            hc = cls()
            for f_info in fields(hc):
                if f_info.name in data:
                    val = float(np.clip(data[f_info.name], COEFF_MIN, COEFF_MAX))
                    setattr(hc, f_info.name, val)
            logger.info(f"Hook coefficients loaded from {path}")
            return hc
        except Exception as e:
            logger.warning(f"Failed to load hook coefficients: {e}, using defaults")
            return cls()

    def diff(self, other: 'HookCoefficients') -> Dict[str, Tuple[float, float]]:
        """Compare with another HookCoefficients, return changed fields."""
        changes = {}
        for f in fields(self):
            a = getattr(self, f.name)
            b = getattr(other, f.name)
            if abs(a - b) > 1e-8:
                changes[f.name] = (a, b)
        return changes


class HookCoefficientOptimizer:
    """Finite-difference gradient descent on HookCoefficients.

    During sleep, we evaluate the training loss at the current coefficients
    and at small perturbations. The numerical gradient drives SGD updates.

    Parameters
    ----------
    coefficients : HookCoefficients
        The coefficient set to optimize.
    lr : float
        Learning rate (default 0.001).
    momentum : float
        SGD momentum (default 0.9).
    epsilon : float
        Finite difference step size (default 0.01).
    ewc_lambda : float
        EWC regularization strength (default 10.0).
    """

    def __init__(
        self,
        coefficients: HookCoefficients,
        lr: float = 0.001,
        momentum: float = 0.9,
        epsilon: float = 0.01,
        ewc_lambda: float = 10.0,
    ):
        self.coefficients = coefficients
        self.lr = lr
        self.momentum = momentum
        self.epsilon = epsilon
        self.ewc_lambda = ewc_lambda

        n = coefficients.num_coefficients
        self._velocity = np.zeros(n, dtype=np.float64)
        self._anchor: Optional[np.ndarray] = None
        self._fisher: Optional[np.ndarray] = None
        self._update_count = 0

    def compute_gradient(
        self,
        loss_fn,
    ) -> np.ndarray:
        """Compute numerical gradient via central finite differences.

        Parameters
        ----------
        loss_fn : callable
            loss_fn(coefficients: HookCoefficients) -> float
            Evaluates the loss for a given coefficient set.

        Returns
        -------
        np.ndarray
            Gradient vector (same length as coefficients).
        """
        base_vec = self.coefficients.to_vector()
        n = len(base_vec)
        grad = np.zeros(n, dtype=np.float64)

        for i in range(n):
            # Forward perturbation
            vec_plus = base_vec.copy()
            vec_plus[i] += self.epsilon
            hc_plus = self.coefficients.clone().from_vector(vec_plus)
            loss_plus = loss_fn(hc_plus)

            # Backward perturbation
            vec_minus = base_vec.copy()
            vec_minus[i] -= self.epsilon
            hc_minus = self.coefficients.clone().from_vector(vec_minus)
            loss_minus = loss_fn(hc_minus)

            grad[i] = (loss_plus - loss_minus) / (2 * self.epsilon)

        return grad

    def step(self, gradient: np.ndarray) -> None:
        """One SGD+momentum step, clamped to bounds.

        Parameters
        ----------
        gradient : np.ndarray
            Gradient from compute_gradient().
        """
        # Add EWC penalty gradient if anchor exists
        if self._anchor is not None and self._fisher is not None:
            current = self.coefficients.to_vector()
            ewc_grad = self.ewc_lambda * self._fisher * (current - self._anchor)
            gradient = gradient + ewc_grad

        # SGD with momentum
        self._velocity = self.momentum * self._velocity - self.lr * gradient
        current = self.coefficients.to_vector()
        new_vec = current + self._velocity

        # Clamp
        new_vec = np.clip(new_vec, COEFF_MIN, COEFF_MAX)
        self.coefficients.from_vector(new_vec)
        self._update_count += 1

    def register_anchor(self) -> None:
        """Snapshot current coefficients as EWC anchor.

        Fisher is approximated as uniform (all 1s) since we don't have
        per-coefficient importance from the finite-difference approach.
        A more sophisticated version could accumulate squared gradients.
        """
        self._anchor = self.coefficients.to_vector().copy()
        self._fisher = np.ones_like(self._anchor)
        logger.info("Hook coefficient EWC anchor registered")

    def register_fisher(self, gradient_history: list) -> None:
        """Compute Fisher from accumulated gradients (squared mean).

        Parameters
        ----------
        gradient_history : list of np.ndarray
            Past gradients from compute_gradient().
        """
        if not gradient_history:
            return
        stacked = np.stack(gradient_history)
        self._fisher = np.mean(stacked ** 2, axis=0)
        # Normalize so max = 1
        max_f = self._fisher.max()
        if max_f > 0:
            self._fisher /= max_f
        logger.info("Hook coefficient Fisher computed from %d gradients",
                     len(gradient_history))

    def get_stats(self) -> Dict[str, any]:
        """Return optimizer statistics."""
        return {
            'update_count': self._update_count,
            'has_anchor': self._anchor is not None,
            'lr': self.lr,
            'momentum': self.momentum,
            'velocity_norm': float(np.linalg.norm(self._velocity)),
            'num_coefficients': self.coefficients.num_coefficients,
        }
