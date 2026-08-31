"""
JAX wrapper for ATM-R.

Functional, JIT-compiled implementation with automatic parallelization.
Integrates with Flax for neural network training.

Usage:
    from atmr_jax import ATMRModule, create_atmr_state, atmr_forward

    # Functional API
    params, state = create_atmr_state(config, rng_key)
    routed, gates, state = atmr_forward(params, state, x_batch, ctx_batch)

    # Or Flax module
    model = ATMRModule(config=config)
    routed, gates = model.apply(variables, x_batch, ctx_batch)
"""

import jax
import jax.numpy as jnp
from jax import random, vmap, jit
import flax.linen as nn
from flax.core import FrozenDict
from typing import Dict, Tuple, Any, Optional
import numpy as np
from functools import partial

try:
    from core.config_loader import load_config
except ImportError:
    from config_loader import load_config


# ============================================================================
# Pure Functional API (for advanced users, maximum performance)
# ============================================================================

def create_atmr_params(
    config: Dict,
    rng: jax.random.PRNGKey,
    adaptive: bool = False
) -> Dict:
    """
    Create ATM-R parameters (functional style).

    Args:
        config: Configuration dict
        rng: JAX random key
        adaptive: Include adaptive learning parameters

    Returns:
        params: Nested dict of parameters
    """
    modalities = config['modalities']
    dims = config['dimensions']
    M = len(modalities)
    K = config['routing']['num_targets']

    # Split RNG
    rngs = random.split(rng, M + 2)

    # Input projections W_in
    W_in = {}
    b_in = {}
    for i, m in enumerate(modalities):
        dim = dims[m]
        W_in[m] = random.normal(rngs[i], (dim, dim)) / np.sqrt(dim)
        b_in[m] = jnp.zeros(dim)

    # Feedback projections W_fb
    W_fb = {}
    for m in modalities:
        dim = dims[m]
        W_fb[m] = random.normal(rngs[M], (dim, M)) * 0.1

    # Routing matrix R
    R = random.normal(rngs[M + 1], (K, M)) * 0.1

    params = {
        'W_in': W_in,
        'b_in': b_in,
        'W_fb': W_fb,
        'R': R
    }

    if adaptive:
        # Generative models G
        G = {}
        for m in modalities:
            dim = dims[m]
            G[m] = random.normal(random.fold_in(rngs[0], hash(m)), (dim, dim)) / np.sqrt(dim)
        params['G'] = G

    return params


def create_atmr_state(
    config: Dict,
    rng: jax.random.PRNGKey,
    adaptive: bool = False
) -> Tuple[Dict, Dict]:
    """
    Create initial ATM-R state (functional style).

    Args:
        config: Configuration dict
        rng: JAX random key
        adaptive: Use adaptive parameters

    Returns:
        params: Model parameters
        state: Dynamic state (latents, priors, tau, etc.)
    """
    modalities = config['modalities']
    dims = config['dimensions']

    params = create_atmr_params(config, rng, adaptive)

    # Dynamic state
    state = {
        # Latent states
        'v': {m: jnp.zeros(dims[m]) for m in modalities},

        # Priors (learnable in adaptive mode)
        'priors': jnp.array([config['priors'][m] for m in modalities]),

        # Time constants (learnable in adaptive mode)
        'tau': jnp.array([config['tau'][m] for m in modalities]),

        # Gating temperature
        'gate_temp': jnp.array(config['gating']['temperature']),

        # TRN inhibition matrix
        'L': jnp.ones((len(modalities), len(modalities))) * config['trn']['init_uniform'],

        # Time step
        't': jnp.array(0)
    }

    # Zero diagonal of L
    state['L'] = state['L'].at[jnp.diag_indices(len(modalities))].set(0.0)

    return params, state


@partial(jit, static_argnums=(3, 4))
def atmr_forward(
    params: Dict,
    state: Dict,
    x: Dict[str, jnp.ndarray],
    config: Dict,
    modalities: Tuple[str, ...]
) -> Tuple[jnp.ndarray, jnp.ndarray, Dict]:
    """
    Forward pass (pure functional, JIT-compiled).

    Args:
        params: Model parameters
        state: Current state
        x: Input dict (modality -> array)
        config: Configuration dict (static)
        modalities: Tuple of modality names (static)

    Returns:
        routed: Routed output [K, max_dim]
        gates: Gate weights [M]
        state: Updated state
    """
    M = len(modalities)
    dt = config['simulation']['dt']
    beta = config['beta']
    trn_lambda = config['trn']['lambda']

    # Extract state
    v_old = state['v']
    priors = state['priors']
    tau = state['tau']
    gate_temp = state['gate_temp']
    L = state['L']

    # 1) Update latent states v_i
    # Vectorized across modalities for parallel execution
    def update_modality(i, m):
        alpha_i = dt / tau[i]

        x_i = x.get(m, jnp.zeros(params['W_in'][m].shape[0]))

        # Input term
        in_term = params['W_in'][m] @ x_i

        # Feedback term (context is embedded in x for simplicity)
        ctx = jnp.zeros(M)  # Will be passed separately
        fb_term = params['W_fb'][m] @ ctx

        # TRN inhibition
        v_norms = jnp.array([jnp.linalg.norm(v_old[m2]) for m2 in modalities])
        inhib = trn_lambda * jnp.sum(L[i] * v_norms) - trn_lambda * L[i, i] * v_norms[i]

        # Update
        drive = in_term + fb_term - inhib + params['b_in'][m]
        v_update = jnp.tanh(drive)

        v_new = (1 - alpha_i) * v_old[m] + alpha_i * v_update
        return v_new

    # Parallel update using vmap
    v_indices = jnp.arange(M)
    v_new_list = vmap(lambda i: update_modality(i, modalities[i]))(v_indices)
    v_new = {modalities[i]: v_new_list[i] for i in range(M)}

    # 2) Compute prediction errors
    pe = jnp.array([jnp.linalg.norm(v_new[m]) for m in modalities])

    # 3) Relevance scores
    activity = jnp.array([jnp.linalg.norm(v_new[m]) for m in modalities])
    novelty = pe
    context_weight = jnp.zeros(M)  # Will come from ctx parameter

    s = (
        beta['activity'] * activity +
        beta['novelty'] * novelty +
        beta['prior'] * priors +
        beta['context'] * context_weight
    )

    # 4) Softmax gating (JIT-compiled)
    s_scaled = (s - jnp.max(s)) / gate_temp
    gates = jax.nn.softmax(s_scaled)

    # 5) Routing to K targets
    K = params['R'].shape[0]
    max_dim = max(config['dimensions'].values())

    # Pad all latents to max_dim
    v_padded = []
    for m in modalities:
        v_pad = jnp.zeros(max_dim)
        v_pad = v_pad.at[:config['dimensions'][m]].set(v_new[m])
        v_padded.append(v_pad)

    v_stacked = jnp.stack(v_padded)  # [M, max_dim]

    # Route: y_k = Σ_i g_i R_ki v_i
    # Vectorized: y = R @ (gates[:, None] * v_stacked)
    routed = params['R'] @ (gates[:, None] * v_stacked)  # [K, max_dim]

    # Update state
    new_state = state.copy()
    new_state['v'] = v_new
    new_state['t'] = state['t'] + 1

    return routed, gates, new_state


@partial(jit, static_argnums=(3, 4))
def atmr_forward_batch(
    params: Dict,
    state: Dict,
    x_batch: Dict[str, jnp.ndarray],
    config: Dict,
    modalities: Tuple[str, ...]
) -> Tuple[jnp.ndarray, jnp.ndarray, Dict]:
    """
    Batched forward pass using vmap.

    Args:
        params: Model parameters (shared across batch)
        state: State (will be vmapped)
        x_batch: Input batch (modality -> [B, dim])
        config: Configuration dict
        modalities: Modality names

    Returns:
        routed_batch: [B, K, max_dim]
        gates_batch: [B, M]
        state: Updated state (last in batch)
    """
    # Extract batch size
    first_mod = modalities[0]
    batch_size = x_batch[first_mod].shape[0]

    # vmap over batch dimension
    # Note: state is not vmapped (shared), only inputs
    def single_forward(x_single):
        x_dict = {m: x_single[i] for i, m in enumerate(modalities)}
        return atmr_forward(params, state, x_dict, config, modalities)[:2]  # routed, gates only

    # Stack inputs for vmap
    x_stacked = jnp.stack([x_batch[m] for m in modalities])  # [M, B, dim]
    x_stacked = jnp.transpose(x_stacked, (1, 0, 2))  # [B, M, dim]

    routed_batch, gates_batch = vmap(single_forward)(x_stacked)

    # Update state with last batch element
    x_last = {m: x_batch[m][-1] for m in modalities}
    _, _, state = atmr_forward(params, state, x_last, config, modalities)

    return routed_batch, gates_batch, state


# ============================================================================
# Flax Module (for neural network integration)
# ============================================================================

class ATMRModule(nn.Module):
    """
    Flax module for ATM-R.

    Example:
        model = ATMRModule(config=config)
        variables = model.init(rng, x_batch, ctx_batch)
        routed, gates = model.apply(variables, x_batch, ctx_batch)
    """
    config: Dict
    adaptive: bool = True

    def setup(self):
        """Initialize parameters."""
        self.modalities = tuple(self.config['modalities'])
        self.M = len(self.modalities)
        self.dims = self.config['dimensions']
        self.K = self.config['routing']['num_targets']
        self.max_dim = max(self.dims.values())

        # Input projections (learnable)
        self.input_layers = {
            m: nn.Dense(self.dims[m], name=f'input_{m}')
            for m in self.modalities
        }

        # Routing matrix (learnable)
        self.routing_proj = nn.Dense(self.K * self.max_dim, name='routing')

    @nn.compact
    def __call__(
        self,
        x: Dict[str, jnp.ndarray],
        ctx: Optional[jnp.ndarray] = None,
        training: bool = True
    ) -> Tuple[jnp.ndarray, jnp.ndarray]:
        """
        Forward pass.

        Args:
            x: Input dict (modality -> [B, dim] or [dim])
            ctx: Context [B, M] or [M]
            training: Training mode

        Returns:
            routed: [B, K, max_dim] or [K, max_dim]
            gates: [B, M] or [M]
        """
        # Detect batch mode
        first_mod = self.modalities[0]
        batched = x[first_mod].ndim == 2

        if ctx is None:
            shape = (x[first_mod].shape[0], self.M) if batched else (self.M,)
            ctx = jnp.zeros(shape)

        # Project inputs through learnable layers
        v = {}
        for m in self.modalities:
            if m in x:
                v[m] = jnp.tanh(self.input_layers[m](x[m]))
            else:
                shape = (x[first_mod].shape[0], self.dims[m]) if batched else (self.dims[m],)
                v[m] = jnp.zeros(shape)

        # Compute gates (simplified for Flax)
        activity = jnp.stack([jnp.linalg.norm(v[m], axis=-1) for m in self.modalities], axis=-1)
        pe = activity  # Simplified PE

        priors = jnp.array([self.config['priors'][m] for m in self.modalities])
        beta = self.config['beta']

        s = (
            beta['activity'] * activity +
            beta['novelty'] * pe +
            beta['prior'] * priors +
            beta['context'] * ctx
        )

        gate_temp = self.config['gating']['temperature']
        gates = jax.nn.softmax(s / gate_temp, axis=-1)

        # Route
        v_padded = []
        for m in self.modalities:
            if batched:
                v_pad = jnp.zeros((x[first_mod].shape[0], self.max_dim))
                v_pad = v_pad.at[:, :self.dims[m]].set(v[m])
            else:
                v_pad = jnp.zeros(self.max_dim)
                v_pad = v_pad.at[:self.dims[m]].set(v[m])
            v_padded.append(v_pad)

        if batched:
            v_stacked = jnp.stack(v_padded, axis=1)  # [B, M, max_dim]
            routed = jnp.einsum('bm,bmd->bd', gates, v_stacked)  # [B, max_dim]
        else:
            v_stacked = jnp.stack(v_padded)  # [M, max_dim]
            routed = jnp.einsum('m,md->d', gates, v_stacked)  # [max_dim]

        return routed, gates


class ATMRClassifier(nn.Module):
    """
    ATM-R + Classifier for end-to-end training.

    Example:
        model = ATMRClassifier(config=config, num_classes=10)
        logits = model.apply(variables, x_batch, ctx_batch)
    """
    config: Dict
    num_classes: int
    hidden_dim: Optional[int] = None

    @nn.compact
    def __call__(
        self,
        x: Dict[str, jnp.ndarray],
        ctx: Optional[jnp.ndarray] = None,
        training: bool = True
    ) -> jnp.ndarray:
        """
        Forward pass.

        Returns:
            logits: [B, num_classes]
        """
        # Route through ATM-R
        atmr = ATMRModule(config=self.config)
        routed, gates = atmr(x, ctx, training)

        # Flatten
        routed_flat = routed.reshape(routed.shape[0], -1)

        # Classify
        if self.hidden_dim is not None:
            h = nn.Dense(self.hidden_dim)(routed_flat)
            h = nn.relu(h)
            h = nn.Dropout(0.3, deterministic=not training)(h)
            logits = nn.Dense(self.num_classes)(h)
        else:
            logits = nn.Dense(self.num_classes)(routed_flat)

        return logits


# Example usage
if __name__ == "__main__":
    print("=" * 60)
    print("ATM-R JAX Wrapper Demo")
    print("=" * 60)

    # Load config
    config = load_config('configs/default.yaml')
    modalities = tuple(config['modalities'])

    # Create params & state
    rng = random.PRNGKey(42)
    params, state = create_atmr_state(config, rng, adaptive=False)

    print(f"\nCreated ATM-R with {len(modalities)} modalities")
    print(f"  Modalities: {modalities}")

    # Test functional API
    print("\n1. Testing functional API (single sample)...")
    x_single = {m: random.normal(rng, (config['dimensions'][m],)) for m in modalities}
    routed, gates, state = atmr_forward(params, state, x_single, config, modalities)

    print(f"  Routed shape: {routed.shape}")
    print(f"  Gates: {gates}")
    print(f"  Gate sum: {jnp.sum(gates):.6f}")

    # Test batched API
    print("\n2. Testing batched API (vmap)...")
    batch_size = 16
    x_batch = {m: random.normal(rng, (batch_size, config['dimensions'][m])) for m in modalities}
    routed_batch, gates_batch, state = atmr_forward_batch(params, state, x_batch, config, modalities)

    print(f"  Routed batch shape: {routed_batch.shape}")
    print(f"  Gates batch shape: {gates_batch.shape}")

    # Test Flax module
    print("\n3. Testing Flax module...")
    model = ATMRModule(config=config)
    variables = model.init(rng, x_batch)
    routed_flax, gates_flax = model.apply(variables, x_batch)

    print(f"  Flax routed shape: {routed_flax.shape}")
    print(f"  Flax gates shape: {gates_flax.shape}")

    # Test classifier
    print("\n4. Testing ATMRClassifier...")
    classifier = ATMRClassifier(config=config, num_classes=10, hidden_dim=128)
    variables_clf = classifier.init(rng, x_batch)
    logits = classifier.apply(variables_clf, x_batch)

    print(f"  Logits shape: {logits.shape}")

    print("\n" + "=" * 60)
    print("JAX wrapper ready!")
    print("  - JIT compilation: ✓")
    print("  - vmap parallelization: ✓")
    print("  - Flax integration: ✓")
    print("=" * 60)
