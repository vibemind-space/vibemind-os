"""
Adaptive Thalamic Multimodal Routing (ATM-R) - Core Implementation
ThalamoPC6: Step-based thalamus with 6 modalities

Implements:
- Thalamic state updates with TRN inhibition
- Relevance scoring & softmax gating
- Multi-target routing
- Optional Kuramoto phase coupling
"""

import numpy as np
from typing import Dict, List, Optional, Tuple, Union


class ThalamoPC6:
    """
    6-modality thalamic router with competitive gating.

    Modalities: vision, audio, touch, taste, vestibular, threat

    Math:
        v_i[t+1] = (1-α_i)v_i[t] + α_i·f(W_i^in·x_i + W_i^fb·c_i - λ·Σ_j L_ij·v_j + b_i)
        s_i = β₁‖v_i‖ + β₂·PE_i + β₃·π_i + β₄·ctx_i
        g_i = exp(s_i/τ_g) / Σ_j exp(s_j/τ_g)
        y_k = Σ_i g_i·R_ki·v_i
    """

    def __init__(
        self,
        modalities: List[str] = None,
        dimensions: Dict[str, int] = None,
        tau: Dict[str, float] = None,
        priors: Dict[str, float] = None,
        beta: Dict[str, float] = None,
        trn_lambda: float = 0.5,
        trn_L: Optional[np.ndarray] = None,
        gate_temp: float = 0.5,
        num_targets: int = 3,
        dt: float = 1.0,
        seed: int = 42,
        nonlinearity: str = "tanh",
        use_phase: bool = False,
        omega: Dict[str, float] = None,
        K_coupling: float = 0.05
    ):
        """
        Initialize ThalamoPC6.

        Args:
            modalities: List of modality names (default: vision, audio, touch, taste, vestibular, threat)
            dimensions: Dict mapping modality -> latent dimension
            tau: Dict mapping modality -> time constant τ_i
            priors: Dict mapping modality -> prior importance π_i
            beta: Dict with keys {activity, novelty, prior, context} for relevance weights
            trn_lambda: λ - TRN inhibition strength
            trn_L: M×M inhibition matrix (off-diag); if None, uniform init
            gate_temp: τ_g - gating softmax temperature
            num_targets: K - number of downstream routing targets
            dt: Δt - time step
            seed: random seed
            nonlinearity: activation function ("tanh", "relu", "sigmoid")
            use_phase: enable Kuramoto phase coupling
            omega: Dict mapping modality -> natural frequency ω_i
            K_coupling: phase coupling strength K_ij
        """
        self.rng = np.random.default_rng(seed)

        # Modalities
        self.modalities = modalities or ["vision", "audio", "touch", "taste", "vestibular", "threat"]
        self.M = len(self.modalities)

        # Dimensions
        default_dims = {"vision": 128, "audio": 64, "touch": 32, "taste": 16, "vestibular": 16, "threat": 8}
        self.d = dimensions or default_dims

        # Time constants
        default_tau = {"vision": 50.0, "audio": 40.0, "touch": 35.0, "taste": 45.0, "vestibular": 30.0, "threat": 20.0}
        self.tau = tau or default_tau
        self.dt = dt

        # Priors
        default_priors = {"vision": 0.2, "audio": 0.15, "touch": 0.15, "taste": 0.1, "vestibular": 0.15, "threat": 0.25}
        self.priors = priors or default_priors

        # Beta weights for relevance
        default_beta = {"activity": 0.3, "novelty": 0.3, "prior": 0.2, "context": 0.2}
        self.beta = beta or default_beta

        # TRN inhibition
        self.trn_lambda = trn_lambda
        if trn_L is None:
            # Uniform off-diagonal inhibition
            self.L = np.ones((self.M, self.M)) * 0.1
            np.fill_diagonal(self.L, 0.0)
        else:
            self.L = trn_L.copy()
            np.fill_diagonal(self.L, 0.0)  # ensure no self-inhibition

        # Gating
        self.gate_temp = gate_temp

        # Routing
        self.K = num_targets
        self.R = self.rng.normal(0, 0.1, (self.K, self.M))  # K×M routing matrix (each row sums modality gates)

        # Nonlinearity
        self.nonlinearity = nonlinearity
        self._set_nonlin_fn()

        # Phase coupling (Kuramoto)
        self.use_phase = use_phase
        default_omega = {"vision": 0.1, "audio": 0.12, "touch": 0.08, "taste": 0.09, "vestibular": 0.11, "threat": 0.15}
        self.omega = omega or default_omega
        self.K_coupling = K_coupling
        self.phi = self.rng.uniform(0, 2*np.pi, self.M)  # initial phases

        # Initialize weights
        self._init_weights()

        # State: latent vectors v_i
        self.v = {m: np.zeros(self.d[m]) for m in self.modalities}

        # Prediction error (for PE term; basic implementation here, overridden in adaptive)
        self.PE = {m: 0.0 for m in self.modalities}

        # Time counter
        self.t = 0

    def _set_nonlin_fn(self):
        """Set activation function."""
        if self.nonlinearity == "tanh":
            self.f = np.tanh
        elif self.nonlinearity == "relu":
            self.f = lambda x: np.maximum(0, x)
        elif self.nonlinearity == "sigmoid":
            self.f = lambda x: 1 / (1 + np.exp(-np.clip(x, -500, 500)))
        else:
            raise ValueError(f"Unknown nonlinearity: {self.nonlinearity}")

    def _init_weights(self):
        """Initialize input & feedback projection weights."""
        self.W_in = {}   # input projection W_i^in
        self.W_fb = {}   # feedback/context projection W_i^fb
        self.b = {}      # bias

        for m in self.modalities:
            dim = self.d[m]
            # Input: project sensory x_i → latent v_i
            self.W_in[m] = self.rng.normal(0, 1/np.sqrt(dim), (dim, dim))
            # Feedback: context modulation (assume context is M-dim one-hot or continuous)
            self.W_fb[m] = self.rng.normal(0, 0.1, (dim, self.M))
            self.b[m] = np.zeros(dim)

    def step(
        self,
        x: Dict[str, np.ndarray],
        ctx: Optional[np.ndarray] = None,
        PE_override: Optional[Dict[str, float]] = None
    ) -> Dict[str, Union[Dict, np.ndarray, float]]:
        """
        Single time step.

        Args:
            x: Dict mapping modality -> input vector x_i[t]
            ctx: M-dim context vector (or None → zeros)
            PE_override: Optional dict of PE values (for testing or external PE)

        Returns:
            Dict with keys:
                'v_next': updated latent states
                'g': gate weights (M-dim)
                'pe': prediction errors
                'y': routed outputs (K×dim_max)
                't': time step
        """
        if ctx is None:
            ctx = np.zeros(self.M)

        # 1) Update thalamic states v_i
        v_new = {}
        for i, m in enumerate(self.modalities):
            alpha_i = self.dt / self.tau[m]

            # Input term
            x_i = x.get(m, np.zeros(self.d[m]))
            in_term = self.W_in[m] @ x_i

            # Feedback/context term
            fb_term = self.W_fb[m] @ ctx

            # TRN inhibition: -λ Σ_j L_ij v_j
            inhib_term = np.zeros(self.d[m])
            for j, m2 in enumerate(self.modalities):
                if i != j:
                    # Broadcast: sum over all dims of v_j weighted by L_ij
                    inhib_term += self.L[i, j] * np.mean(self.v[m2])  # scalar inhibition
            inhib_term = self.trn_lambda * inhib_term

            # Combined
            drive = in_term + fb_term - inhib_term + self.b[m]
            v_update = self.f(drive)

            # Exponential moving average
            v_new[m] = (1 - alpha_i) * self.v[m] + alpha_i * v_update

        self.v = v_new

        # 2) Compute prediction errors (basic version: will be overridden in adaptive)
        if PE_override is not None:
            self.PE = PE_override
        else:
            for m in self.modalities:
                # Placeholder: PE = norm of current activity (no generative model yet)
                self.PE[m] = np.linalg.norm(self.v[m])

        # 3) Relevance scores
        s = np.zeros(self.M)
        for i, m in enumerate(self.modalities):
            activity = np.linalg.norm(self.v[m])
            novelty = self.PE[m]
            prior = self.priors[m]
            context_weight = ctx[i]

            s[i] = (
                self.beta["activity"] * activity +
                self.beta["novelty"] * novelty +
                self.beta["prior"] * prior +
                self.beta["context"] * context_weight
            )

        # 4) Softmax gating
        s_scaled = s / self.gate_temp
        s_scaled = s_scaled - np.max(s_scaled)  # numerical stability
        exp_s = np.exp(s_scaled)
        g = exp_s / np.sum(exp_s)

        # 5) Routing to K targets: y_k = Σ_i g_i R_ki v_i
        # Each v_i has different dim; we pad or project
        # Simple approach: concatenate all v_i (padded to max_dim) and weight by g
        max_dim = max(self.d.values())
        v_concat = []
        for i, m in enumerate(self.modalities):
            v_padded = np.zeros(max_dim)
            v_padded[:self.d[m]] = self.v[m]
            v_concat.append(g[i] * v_padded)

        # y: K×max_dim outputs
        y = np.array([self.R[k] @ g for k in range(self.K)])  # K scalars, expand to vectors
        # Better: route the actual weighted vectors
        y = np.zeros((self.K, max_dim))
        for k in range(self.K):
            y[k] = sum(self.R[k, i] * v_concat[i] for i in range(self.M))

        # 6) Optional phase update (Kuramoto)
        if self.use_phase:
            phi_new = self.phi.copy()
            for i in range(self.M):
                coupling = sum(
                    self.K_coupling * np.sin(self.phi[j] - self.phi[i])
                    for j in range(self.M) if j != i
                )
                omega_i = list(self.omega.values())[i]
                phi_new[i] = self.phi[i] + omega_i + coupling
            self.phi = phi_new % (2 * np.pi)

        self.t += 1

        return {
            'v_next': self.v,
            'g': g,
            'pe': self.PE.copy(),
            'y': y,
            't': self.t,
            'phi': self.phi.copy() if self.use_phase else None
        }

    # --- Runtime controls ---

    def set_priority(self, modality: str, value: float):
        """Update prior π_i."""
        if modality in self.priors:
            self.priors[modality] = value

    def set_tau(self, modality: str, value: float):
        """Update time constant τ_i."""
        if modality in self.tau:
            self.tau[modality] = value

    def set_trn(self, L_new: np.ndarray, lam: Optional[float] = None):
        """Update TRN inhibition matrix L and/or λ."""
        self.L = L_new.copy()
        np.fill_diagonal(self.L, 0.0)
        if lam is not None:
            self.trn_lambda = lam

    def set_gating_temp(self, temp: float):
        """Update gating temperature τ_g."""
        self.gate_temp = temp

    def set_phase_params(self, use_phase: bool = None, K_coup: float = None):
        """Toggle phase coupling and/or update coupling strength."""
        if use_phase is not None:
            self.use_phase = use_phase
        if K_coup is not None:
            self.K_coupling = K_coup

    def reset_state(self):
        """Reset latent states to zero."""
        self.v = {m: np.zeros(self.d[m]) for m in self.modalities}
        self.PE = {m: 0.0 for m in self.modalities}
        self.phi = self.rng.uniform(0, 2*np.pi, self.M)
        self.t = 0

    def get_state(self) -> Dict:
        """Return current internal state for inspection."""
        return {
            'v': self.v.copy(),
            'PE': self.PE.copy(),
            'phi': self.phi.copy() if self.use_phase else None,
            't': self.t,
            'priors': self.priors.copy(),
            'tau': self.tau.copy(),
            'gate_temp': self.gate_temp,
            'trn_lambda': self.trn_lambda,
            'L': self.L.copy()
        }
