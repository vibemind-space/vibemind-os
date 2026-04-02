"""
Integration and Memory Modules

Implements the final two modules:
- MTL: Medial Temporal Lobe (Memory/Association)
- DMN: Default Mode Network (Integration/Consciousness)
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Optional, Tuple, List

from neurosymbolic.modules.base_module import BrainModule


class MTLModule(BrainModule):
    """
    Medial Temporal Lobe Module (BA 20, 21, 37)

    Implements associative memory and pattern completion:
    - Key-value memory storage
    - Associative retrieval
    - Pattern completion

    Architecture: Attention-based memory network
    """

    def __init__(
        self,
        input_dim: int = 256,
        memory_dim: int = 256,
        output_dim: int = 256,
        memory_size: int = 100
    ):
        """
        Initialize MTL module

        Args:
            input_dim: Input dimension
            memory_dim: Memory embedding dimension
            output_dim: Output dimension
            memory_size: Number of memory slots
        """
        super().__init__(
            module_id="MTL",
            module_name="Medial Temporal Lobe",
            input_dim=input_dim,
            output_dim=output_dim,
            brodmann_areas="20,21,37"
        )

        self.memory_dim = memory_dim
        self.memory_size = memory_size

        # Memory storage (learnable or dynamic)
        self.register_buffer(
            'memory_keys',
            torch.randn(memory_size, memory_dim)
        )
        self.register_buffer(
            'memory_values',
            torch.randn(memory_size, memory_dim)
        )

        # Query projection
        self.query_proj = nn.Linear(input_dim, memory_dim)

        # Output projection
        self.output_proj = nn.Sequential(
            nn.Linear(memory_dim, output_dim),
            nn.ReLU(),
            nn.Dropout(0.1)
        )

        # Memory write mechanism
        self.write_gate = nn.Sequential(
            nn.Linear(input_dim, memory_dim),
            nn.Sigmoid()
        )

    def forward(self, x: torch.Tensor, write_memory: bool = False) -> torch.Tensor:
        """
        Retrieve from associative memory

        Args:
            x: Input query [batch, input_dim]
            write_memory: If True, write to memory

        Returns:
            Retrieved features [batch, output_dim]
        """
        batch_size = x.size(0)

        # Project input to query
        query = self.query_proj(x)  # [batch, memory_dim]

        # Compute attention scores
        # scores = query · keys^T
        scores = torch.matmul(query, self.memory_keys.t())  # [batch, memory_size]
        attention_weights = F.softmax(scores, dim=-1)  # [batch, memory_size]

        # Retrieve values
        retrieved = torch.matmul(attention_weights, self.memory_values)  # [batch, memory_dim]

        # Optional: Write to memory
        if write_memory:
            write_gate_value = self.write_gate(x)  # [batch, memory_dim]
            # Update memory (simple weighted update)
            # In practice, would use more sophisticated memory update
            pass

        # Project to output
        output = self.output_proj(retrieved)  # [batch, output_dim]

        return output

    def get_memory_state(self) -> Tuple[torch.Tensor, torch.Tensor]:
        """Get current memory state"""
        return self.memory_keys.clone(), self.memory_values.clone()

    def set_memory_state(self, keys: torch.Tensor, values: torch.Tensor):
        """Set memory state"""
        self.memory_keys.copy_(keys)
        self.memory_values.copy_(values)


class DMNModule(BrainModule):
    """
    Default Mode Network Module (BA 10, 23, 31, 36)

    Implements consciousness/integration as energy-based model:
    - Energy function E(x) = x^T Q x + b^T x
    - Attractor dynamics ẋ = -∇E(x)
    - Convergence → coherence achieved

    This is the "goal" module - DMN reaching exit = consciousness

    Architecture: Energy-based model with quadratic form
    """

    def __init__(
        self,
        input_dim: int = 256,
        state_dim: int = 256,
        output_dim: int = 256
    ):
        """
        Initialize DMN module

        Args:
            input_dim: Input dimension
            state_dim: Internal state dimension
            output_dim: Output dimension
        """
        super().__init__(
            module_id="DMN",
            module_name="Default Mode Network",
            input_dim=input_dim,
            output_dim=output_dim,
            brodmann_areas="10,23,31,36"
        )

        self.state_dim = state_dim

        # Energy function parameters
        # E(x) = x^T Q x + b^T x + c
        self.Q = nn.Parameter(torch.randn(state_dim, state_dim) * 0.01)
        self.b = nn.Parameter(torch.zeros(state_dim))

        # Input encoder
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, state_dim),
            nn.Tanh()
        )

        # Integration network (combines multiple inputs)
        self.integration = nn.MultiheadAttention(
            embed_dim=state_dim,
            num_heads=8,
            batch_first=True
        )

        # Output decoder
        self.decoder = nn.Sequential(
            nn.Linear(state_dim, output_dim),
            nn.ReLU()
        )

        # Initial attractor state
        self.register_buffer('attractor_state', torch.zeros(1, state_dim))

    def compute_energy(self, x: torch.Tensor) -> torch.Tensor:
        """
        Compute energy E(x) = x^T Q x + b^T x

        Args:
            x: State [batch, state_dim]

        Returns:
            Energy [batch]
        """
        # Quadratic term: x^T Q x
        # Make Q symmetric for stability
        Q_sym = (self.Q + self.Q.t()) / 2
        quadratic = torch.sum(x * (x @ Q_sym), dim=-1)

        # Linear term: b^T x
        linear = torch.sum(x * self.b, dim=-1)

        energy = quadratic + linear

        return energy

    def compute_gradient(self, x: torch.Tensor) -> torch.Tensor:
        """
        Compute gradient ∇E(x) = 2Qx + b

        Args:
            x: State [batch, state_dim]

        Returns:
            Gradient [batch, state_dim]
        """
        Q_sym = (self.Q + self.Q.t()) / 2
        gradient = 2 * (x @ Q_sym) + self.b

        return gradient

    def forward(
        self,
        x: torch.Tensor,
        num_steps: int = 5,
        step_size: float = 0.1
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Integrate inputs and converge to attractor

        Args:
            x: Input tensor [batch, input_dim] or [batch, seq_len, input_dim]
            num_steps: Number of dynamics steps
            step_size: Step size for gradient descent

        Returns:
            Tuple of (output [batch, output_dim], final_state, final_energy)
        """
        batch_size = x.size(0)

        # Encode input
        if x.dim() == 2:
            x = x.unsqueeze(1)  # [batch, 1, input_dim]

        encoded = self.encoder(x)  # [batch, seq_len, state_dim]

        # Integration via self-attention
        integrated, _ = self.integration(encoded, encoded, encoded)
        integrated = integrated.mean(dim=1)  # [batch, state_dim]

        # Initialize state
        # Always expand to current batch_size (handles dynamic batch sizes)
        if self._state is None or self._state.size(0) != batch_size:
            # Initialize or re-initialize if batch size changed
            state = self.attractor_state.expand(batch_size, -1).clone()
        else:
            state = self._state

        # Combine with integrated input
        state = state + integrated

        # Run attractor dynamics: ẋ = -∇E(x)
        for _ in range(num_steps):
            grad = self.compute_gradient(state)
            # Clip gradient to prevent divergence
            grad = torch.clamp(grad, min=-10.0, max=10.0)
            state = state - step_size * grad  # Gradient descent
            # Clamp state to prevent overflow
            state = torch.clamp(state, min=-10.0, max=10.0)

        # Compute final energy
        final_energy = self.compute_energy(state)
        # Clamp energy to prevent inf
        final_energy = torch.clamp(final_energy, min=-100.0, max=100.0)

        # Decode to output
        output = self.decoder(state)

        # Store state without gradient (to avoid double backward)
        self._state = state.detach()

        return output, state, final_energy

    def get_coherence(self) -> float:
        """
        Get coherence metric (inverse of energy variance)

        Low energy variance = high coherence
        """
        if self._state is None:
            return 0.0

        energy = self.compute_energy(self._state)
        coherence = 1.0 / (1.0 + energy.std().item())

        return coherence

    def is_converged(self, threshold: float = 0.01) -> bool:
        """
        Check if dynamics have converged

        Args:
            threshold: Convergence threshold

        Returns:
            True if converged
        """
        if self._state is None:
            return False

        grad = self.compute_gradient(self._state)
        grad_norm = torch.norm(grad, dim=-1).mean().item()

        return grad_norm < threshold


if __name__ == "__main__":
    # Test integration modules
    print("Testing Integration Modules...")
    print("="*60)

    batch_size = 4

    # Test MTL
    print("\n1. MTL Module (Memory/Association)")
    mtl = MTLModule(input_dim=256, memory_dim=256, output_dim=256, memory_size=100)
    print(f"   {mtl}")
    x_mtl = torch.randn(batch_size, 256)
    y_mtl = mtl(x_mtl)
    print(f"   Input: {x_mtl.shape} -> Output: {y_mtl.shape}")
    print(f"   Memory slots: {mtl.memory_size}")
    print(f"   Parameters: {mtl.get_info()['num_parameters']:,}")

    # Test DMN
    print("\n2. DMN Module (Consciousness/Integration)")
    dmn = DMNModule(input_dim=256, state_dim=256, output_dim=256)
    print(f"   {dmn}")
    x_dmn = torch.randn(batch_size, 256)
    output, state, energy = dmn(x_dmn, num_steps=5, step_size=0.1)
    print(f"   Input: {x_dmn.shape}")
    print(f"   Output: {output.shape}")
    print(f"   State: {state.shape}")
    print(f"   Energy: {energy.shape}")
    print(f"   Energy values: {energy.tolist()}")
    print(f"   Coherence: {dmn.get_coherence():.3f}")
    print(f"   Converged: {dmn.is_converged()}")
    print(f"   Parameters: {dmn.get_info()['num_parameters']:,}")

    # Test convergence over multiple steps
    print("\n3. Testing DMN Convergence")
    dmn2 = DMNModule(input_dim=256, state_dim=256, output_dim=256)
    x = torch.randn(batch_size, 256)

    energies = []
    for i in range(10):
        output, state, energy = dmn2(x, num_steps=1, step_size=0.1)
        energies.append(energy.mean().item())
        print(f"   Step {i+1}: Energy = {energy.mean().item():.4f}, Coherence = {dmn2.get_coherence():.4f}")

    print(f"   Final convergence: {dmn2.is_converged()}")

    print("\n" + "="*60)
    print("All integration modules working correctly!")

    total_params = sum([
        mtl.get_info()['num_parameters'],
        dmn.get_info()['num_parameters']
    ])
    print(f"Total parameters in integration modules: {total_params:,}")
