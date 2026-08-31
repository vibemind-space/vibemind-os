"""
Adaptive Thalamic Multimodal Routing (ATM-R) - Adaptive Implementation
ThalamoPC6Adaptive: Online learning thalamus with homeostatic adaptation

Extends ThalamoPC6 with:
- Predictive coding: learn G_i to reconstruct x_i from v_i → PE_i
- Hebbian input learning: adapt W_i^in
- TRN competition: adapt L based on co-activation
- Homeostatic adaptation: π_i, τ_i, τ_g
"""

import numpy as np
from typing import Dict, Optional, Union
from core.thalamo_pc_live import ThalamoPC6


class ThalamoPC6Adaptive(ThalamoPC6):
    """
    Adaptive 6-modality thalamic router with online learning.

    Additional learning:
        ΔW_i^in ∝ g_i · v_i x_i^T  (Hebbian, modulated by gate & PE)
        ΔG_i ∝ PE_i · v_i          (predictive coding)
        ΔL_ij ∝ co-activation       (TRN competition)
        Δπ_i ∝ hazard/reward        (safety/value adaptation)
        Δτ_i ∝ (‖v_i‖ - target)     (activity homeostasis)
        Δτ_g ∝ (H(g) - target)      (gate entropy homeostasis)
    """

    def __init__(
        self,
        # Base class args
        modalities=None,
        dimensions=None,
        tau=None,
        priors=None,
        beta=None,
        trn_lambda=0.5,
        trn_L=None,
        gate_temp=0.5,
        num_targets=3,
        dt=1.0,
        seed=42,
        nonlinearity="tanh",
        use_phase=False,
        omega=None,
        K_coupling=0.05,
        # Learning rates
        lr_input=0.001,
        lr_generative=0.01,
        lr_trn=0.0005,
        lr_prior=0.0001,
        lr_tau=0.0001,
        lr_gate_temp=0.0001,
        # Homeostatic targets
        target_activity=0.5,
        target_entropy=1.5,
        # Bounds
        tau_min=10.0,
        tau_max=200.0,
        prior_min=0.01,
        prior_max=2.0,
        gate_temp_min=0.1,
        gate_temp_max=2.0,
        trn_max=5.0,
        # Adaptation scales
        hazard_scale=0.1,
        reward_scale=0.05
    ):
        """
        Initialize ThalamoPC6Adaptive.

        Args:
            (See ThalamoPC6 for base args)
            lr_input: learning rate for W_i^in
            lr_generative: learning rate for G_i (generative model)
            lr_trn: learning rate for TRN inhibition L
            lr_prior: learning rate for priors π_i
            lr_tau: learning rate for time constants τ_i
            lr_gate_temp: learning rate for gate temperature τ_g
            target_activity: homeostatic target for ‖v_i‖
            target_entropy: homeostatic target for gate entropy H(g)
            tau_min, tau_max: bounds for τ_i
            prior_min, prior_max: bounds for π_i
            gate_temp_min, gate_temp_max: bounds for τ_g
            trn_max: max value for L_ij
            hazard_scale: scaling for hazard → Δπ_i
            reward_scale: scaling for reward → Δπ_i
        """
        super().__init__(
            modalities=modalities,
            dimensions=dimensions,
            tau=tau,
            priors=priors,
            beta=beta,
            trn_lambda=trn_lambda,
            trn_L=trn_L,
            gate_temp=gate_temp,
            num_targets=num_targets,
            dt=dt,
            seed=seed,
            nonlinearity=nonlinearity,
            use_phase=use_phase,
            omega=omega,
            K_coupling=K_coupling
        )

        # Learning rates
        self.lr_input = lr_input
        self.lr_generative = lr_generative
        self.lr_trn = lr_trn
        self.lr_prior = lr_prior
        self.lr_tau = lr_tau
        self.lr_gate_temp = lr_gate_temp

        # Homeostatic targets
        self.target_activity = target_activity
        self.target_entropy = target_entropy

        # Bounds
        self.tau_min = tau_min
        self.tau_max = tau_max
        self.prior_min = prior_min
        self.prior_max = prior_max
        self.gate_temp_min = gate_temp_min
        self.gate_temp_max = gate_temp_max
        self.trn_max = trn_max

        # Adaptation scales
        self.hazard_scale = hazard_scale
        self.reward_scale = reward_scale

        # Generative models G_i: latent v_i → reconstructed x_i
        self.G = {}
        for m in self.modalities:
            dim = self.d[m]
            self.G[m] = self.rng.normal(0, 1/np.sqrt(dim), (dim, dim))

        # History for adaptation
        self.last_x = {m: np.zeros(self.d[m]) for m in self.modalities}
        self.last_g = np.ones(self.M) / self.M

    def step(
        self,
        x: Dict[str, np.ndarray],
        ctx: Optional[np.ndarray] = None,
        hazard: Optional[Dict[str, float]] = None,
        reward: Optional[Dict[str, float]] = None,
        adapt: bool = True
    ) -> Dict[str, Union[Dict, np.ndarray, float]]:
        """
        Adaptive time step with online learning.

        Args:
            x: Dict mapping modality -> input vector x_i[t]
            ctx: M-dim context vector
            hazard: Optional dict mapping modality -> hazard signal (0-1)
            reward: Optional dict mapping modality -> reward signal (0-1)
            adapt: if True, perform online adaptation

        Returns:
            Dict with keys: v_next, g, pe, y, t, adapted_params (if adapt=True)
        """
        # 1) Compute prediction errors using generative models
        PE_computed = {}
        for m in self.modalities:
            x_i = x.get(m, np.zeros(self.d[m]))
            x_pred = self.G[m] @ self.v[m]
            PE_computed[m] = np.linalg.norm(x_i - x_pred)

        # 2) Call parent step with computed PE
        out = super().step(x, ctx=ctx, PE_override=PE_computed)

        g = out['g']

        # 3) Adapt if requested
        if adapt:
            adapted = self._adapt(x, g, hazard, reward)
            out['adapted_params'] = adapted

        # Update history
        self.last_x = {m: x.get(m, np.zeros(self.d[m])).copy() for m in self.modalities}
        self.last_g = g.copy()

        return out

    def _adapt(
        self,
        x: Dict[str, np.ndarray],
        g: np.ndarray,
        hazard: Optional[Dict[str, float]],
        reward: Optional[Dict[str, float]]
    ) -> Dict[str, Dict]:
        """
        Perform online adaptation.

        Returns dict of adapted parameters for logging.
        """
        adapted = {}

        # --- Predictive coding: update G_i ---
        for i, m in enumerate(self.modalities):
            x_i = x.get(m, np.zeros(self.d[m]))
            x_pred = self.G[m] @ self.v[m]
            error = x_i - x_pred

            # ΔG_i ∝ error · v_i^T
            if np.linalg.norm(self.v[m]) > 1e-6:
                dG = np.outer(error, self.v[m])
                self.G[m] += self.lr_generative * dG

        # --- Hebbian input learning: update W_in ---
        for i, m in enumerate(self.modalities):
            x_i = x.get(m, np.zeros(self.d[m]))
            # Modulate by gate strength and PE
            modulation = g[i] * (1 + self.PE[m])
            if np.linalg.norm(x_i) > 1e-6 and np.linalg.norm(self.v[m]) > 1e-6:
                dW = modulation * np.outer(self.v[m], x_i)
                self.W_in[m] += self.lr_input * dW

        # --- TRN competition: increase L_ij when i and j co-activate ---
        v_norms = np.array([np.linalg.norm(self.v[m]) for m in self.modalities])
        for i in range(self.M):
            for j in range(self.M):
                if i != j:
                    co_act = v_norms[i] * v_norms[j]
                    self.L[i, j] += self.lr_trn * co_act
                    self.L[i, j] = min(self.L[i, j], self.trn_max)

        # --- Prior adaptation: hazard/reward → π_i ---
        if hazard is not None:
            for i, m in enumerate(self.modalities):
                if m in hazard:
                    self.priors[m] += self.hazard_scale * hazard[m]
        if reward is not None:
            for i, m in enumerate(self.modalities):
                if m in reward:
                    self.priors[m] += self.reward_scale * reward[m]

        # Clip priors
        for m in self.modalities:
            self.priors[m] = np.clip(self.priors[m], self.prior_min, self.prior_max)

        adapted['priors'] = self.priors.copy()

        # --- Tau homeostasis: keep ‖v_i‖ near target ---
        for m in self.modalities:
            activity = np.linalg.norm(self.v[m])
            error_act = activity - self.target_activity
            # If too active, decrease τ (speed up decay); if too inactive, increase τ
            self.tau[m] -= self.lr_tau * error_act
            self.tau[m] = np.clip(self.tau[m], self.tau_min, self.tau_max)

        adapted['tau'] = self.tau.copy()

        # --- Gate entropy homeostasis: keep H(g) near target ---
        entropy = -np.sum(g * np.log(g + 1e-10)) / np.log(2)  # bits
        error_ent = entropy - self.target_entropy
        # If entropy too low (sharp), increase τ_g (soften); if too high, decrease τ_g
        self.gate_temp += self.lr_gate_temp * error_ent
        self.gate_temp = np.clip(self.gate_temp, self.gate_temp_min, self.gate_temp_max)

        adapted['gate_temp'] = self.gate_temp
        adapted['entropy'] = entropy

        return adapted

    def get_adaptive_state(self) -> Dict:
        """Return adaptive-specific state (generative models, learning rates, etc.)."""
        base_state = super().get_state()
        adaptive_state = {
            'G': {m: self.G[m].copy() for m in self.modalities},
            'lr_input': self.lr_input,
            'lr_generative': self.lr_generative,
            'lr_trn': self.lr_trn,
            'lr_prior': self.lr_prior,
            'lr_tau': self.lr_tau,
            'lr_gate_temp': self.lr_gate_temp,
            'target_activity': self.target_activity,
            'target_entropy': self.target_entropy,
            'bounds': {
                'tau_min': self.tau_min,
                'tau_max': self.tau_max,
                'prior_min': self.prior_min,
                'prior_max': self.prior_max,
                'gate_temp_min': self.gate_temp_min,
                'gate_temp_max': self.gate_temp_max,
                'trn_max': self.trn_max
            }
        }
        return {**base_state, **adaptive_state}

    def apply_feedback(
        self,
        prior_delta: np.ndarray,
        trn_delta: np.ndarray,
        gain: float = 1.0
    ) -> Dict[str, any]:
        """
        Apply external cortical feedback to modulate thalamic parameters.

        This implements Layer 6 corticothalamic feedback, allowing top-down
        attention and executive control to influence thalamic routing.

        Args:
            prior_delta: Per-modality prior adjustments [M]
            trn_delta: TRN inhibition matrix adjustments [M x M]
            gain: Multiplicative gain for activity (arousal modulation)

        Returns:
            Dict with applied changes for monitoring
        """
        applied = {
            'prior_changes': {},
            'trn_change_norm': 0.0,
            'gain_applied': gain
        }

        # 1) Apply prior modulation
        for i, m in enumerate(self.modalities):
            if i < len(prior_delta):
                old_prior = self.priors[m]
                self.priors[m] += prior_delta[i]
                self.priors[m] = np.clip(self.priors[m], self.prior_min, self.prior_max)
                applied['prior_changes'][m] = self.priors[m] - old_prior

        # 2) Apply TRN modulation
        if trn_delta.shape == self.L.shape:
            self.L += trn_delta
            # Ensure non-negative and bounded
            self.L = np.clip(self.L, 0, self.trn_max)
            # Keep diagonal zero (no self-inhibition)
            np.fill_diagonal(self.L, 0)
            applied['trn_change_norm'] = np.linalg.norm(trn_delta)

        # 3) Apply gain modulation to current activity
        # Gain scales the current state activity
        if gain != 1.0:
            for m in self.modalities:
                self.v[m] *= gain

        return applied
