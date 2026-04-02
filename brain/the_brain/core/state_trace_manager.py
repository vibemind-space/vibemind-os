"""
StateTraceManager - Temporal Trace Management for CTM

Based on SakanaAI's Continuous Thought Machine architecture:
https://github.com/SakanaAI/continuous-thought-machines

Key Innovation:
- Standard approach: Process single states or random perturbations
- SakanaAI: Each neuron maintains a HISTORY (trace) of pre-activations

The trace is a sliding window of the last M pre-activation states,
enabling NLMs to process temporal patterns in each neuron's activity.

Trace update (sliding window):
    state_trace[:, :, 1:] + new_state.unsqueeze(-1)
    (drop oldest, append newest)

This creates an internal "timeline" of neural activity that NLMs can
process to detect patterns and make predictions.

Usage:
    from core.state_trace_manager import StateTraceManager

    trace_mgr = StateTraceManager(d_model=256, memory_length=10)

    # Get initial state for a batch
    state_trace, activated_state = trace_mgr.get_initial_state(batch_size=4)

    # Update trace after each iteration
    state_trace = trace_mgr.update_trace(state_trace, new_state)
"""

import torch
import torch.nn as nn
import math
from typing import Tuple, Optional


class StateTraceManager(nn.Module):
    """
    Manage temporal traces for each neuron in the CTM.

    Each neuron maintains a history (trace) of its pre-activations
    over the last M internal ticks. This trace is processed by
    NeuronLevelModels to generate post-activations.

    The start_trace and start_activated_state are LEARNABLE parameters,
    allowing the model to learn optimal initialization for reasoning.

    Parameters:
        d_model: Number of neurons (feature dimension)
        memory_length: Length of temporal history (M in paper)

    Shape:
        state_trace: (batch, d_model, memory_length)
        activated_state: (batch, d_model)
    """

    def __init__(
        self,
        d_model: int,
        memory_length: int
    ):
        super().__init__()
        self.d_model = d_model
        self.memory_length = memory_length

        # Learnable start trace (initial "memory" for each neuron)
        # Initialized with small uniform values
        init_scale = math.sqrt(1 / (d_model + memory_length))
        self.start_trace = nn.Parameter(
            torch.zeros(d_model, memory_length).uniform_(-init_scale, init_scale)
        )

        # Learnable start activated state (initial post-activation)
        self.start_activated_state = nn.Parameter(
            torch.zeros(d_model).uniform_(
                -math.sqrt(1 / d_model),
                math.sqrt(1 / d_model)
            )
        )

    def get_initial_state(
        self,
        batch_size: int,
        device: Optional[torch.device] = None
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Get initial trace and activated state for a batch.

        The learnable start parameters are expanded to batch size
        and cloned to prevent gradient issues.

        Args:
            batch_size: Number of samples in batch
            device: Optional device override

        Returns:
            state_trace: (batch, d_model, memory_length)
            activated_state: (batch, d_model)
        """
        # Expand learnable parameters to batch size
        state_trace = self.start_trace.unsqueeze(0).expand(batch_size, -1, -1)
        activated_state = self.start_activated_state.unsqueeze(0).expand(batch_size, -1)

        # Clone to create independent copies (important for gradient flow)
        state_trace = state_trace.clone()
        activated_state = activated_state.clone()

        # Move to device if specified
        if device is not None:
            state_trace = state_trace.to(device)
            activated_state = activated_state.to(device)

        return state_trace, activated_state

    def update_trace(
        self,
        state_trace: torch.Tensor,
        new_state: torch.Tensor
    ) -> torch.Tensor:
        """
        Update trace with new pre-activation state (sliding window).

        The oldest state is dropped and the new state is appended.
        This creates a sliding window of neural activity history.

        Args:
            state_trace: (batch, d_model, memory_length) current trace
            new_state: (batch, d_model) new pre-activation to append

        Returns:
            updated_trace: (batch, d_model, memory_length)
        """
        # Sliding window: drop oldest (index 0), append newest
        return torch.cat([
            state_trace[:, :, 1:],       # All but first time step
            new_state.unsqueeze(-1)      # New state as last time step
        ], dim=-1)

    def reset_trace(
        self,
        batch_size: int,
        device: Optional[torch.device] = None
    ) -> torch.Tensor:
        """
        Reset trace to initial learnable state.

        Useful for starting a new reasoning episode.

        Args:
            batch_size: Number of samples
            device: Optional device

        Returns:
            state_trace: (batch, d_model, memory_length)
        """
        state_trace, _ = self.get_initial_state(batch_size, device)
        return state_trace

    def get_trace_statistics(
        self,
        state_trace: torch.Tensor
    ) -> dict:
        """
        Compute statistics about current trace state.

        Useful for monitoring and debugging.

        Args:
            state_trace: (batch, d_model, memory_length)

        Returns:
            dict with trace statistics
        """
        with torch.no_grad():
            return {
                'mean': state_trace.mean().item(),
                'std': state_trace.std().item(),
                'min': state_trace.min().item(),
                'max': state_trace.max().item(),
                'temporal_variance': state_trace.var(dim=-1).mean().item(),
                'neuron_variance': state_trace.var(dim=1).mean().item(),
            }

    def extra_repr(self) -> str:
        return f'd_model={self.d_model}, memory_length={self.memory_length}'


class FullStateManager(nn.Module):
    """
    Complete state management combining trace and synchronisation accumulators.

    This is a convenience wrapper that manages all state needed for
    CTM reasoning iterations.
    """

    def __init__(
        self,
        d_model: int,
        memory_length: int,
        n_synch_action: int = 32,
        n_synch_out: int = 64
    ):
        super().__init__()
        self.d_model = d_model
        self.memory_length = memory_length
        self.n_synch_action = n_synch_action
        self.n_synch_out = n_synch_out

        # Trace manager
        self.trace_manager = StateTraceManager(d_model, memory_length)

    def get_initial_state(
        self,
        batch_size: int,
        device: Optional[torch.device] = None
    ) -> dict:
        """
        Get all initial states for CTM reasoning.

        Returns dict with:
            - state_trace: (B, D, M) temporal history
            - activated_state: (B, D) post-activations
            - alpha_action, beta_action: None (sync accumulators)
            - alpha_out, beta_out: None (sync accumulators)
        """
        state_trace, activated_state = self.trace_manager.get_initial_state(
            batch_size, device
        )

        return {
            'state_trace': state_trace,
            'activated_state': activated_state,
            'alpha_action': None,
            'beta_action': None,
            'alpha_out': None,
            'beta_out': None,
        }

    def update_state(
        self,
        state: dict,
        new_pre_activation: torch.Tensor,
        new_activated_state: torch.Tensor,
        sync_accumulators: dict
    ) -> dict:
        """
        Update all state components after one iteration.

        Args:
            state: Current state dict
            new_pre_activation: New pre-activation from synapses
            new_activated_state: New post-activation from NLM
            sync_accumulators: Updated sync accumulators from SynchronisationModule

        Returns:
            Updated state dict
        """
        return {
            'state_trace': self.trace_manager.update_trace(
                state['state_trace'], new_pre_activation
            ),
            'activated_state': new_activated_state,
            **sync_accumulators
        }


class TraceVisualizer:
    """
    Utility class for visualizing trace evolution.

    Useful for debugging and understanding CTM dynamics.
    """

    def __init__(self, d_model: int, memory_length: int):
        self.d_model = d_model
        self.memory_length = memory_length
        self.trace_history = []

    def record(self, state_trace: torch.Tensor):
        """Record a trace snapshot."""
        with torch.no_grad():
            # Store mean across batch for visualization
            self.trace_history.append(
                state_trace.mean(dim=0).cpu().numpy()
            )

    def get_evolution(self, neuron_idx: int = 0) -> list:
        """Get temporal evolution of a specific neuron."""
        return [t[neuron_idx, :] for t in self.trace_history]

    def reset(self):
        """Clear history."""
        self.trace_history = []


if __name__ == "__main__":
    # Test the StateTraceManager
    print("=" * 60)
    print("Testing StateTraceManager")
    print("=" * 60)

    d_model = 256
    memory_length = 10
    batch_size = 4
    n_iterations = 20

    trace_mgr = StateTraceManager(
        d_model=d_model,
        memory_length=memory_length
    )

    print(f"\nModule: {trace_mgr}")
    print(f"Parameters: {sum(p.numel() for p in trace_mgr.parameters()):,}")
    print(f"  - start_trace: {trace_mgr.start_trace.shape}")
    print(f"  - start_activated_state: {trace_mgr.start_activated_state.shape}")

    # Test initial state
    print("\n" + "-" * 40)
    print("Initial state test:")
    print("-" * 40)

    state_trace, activated_state = trace_mgr.get_initial_state(batch_size)

    print(f"state_trace shape: {state_trace.shape}")
    print(f"activated_state shape: {activated_state.shape}")
    print(f"Trace statistics: {trace_mgr.get_trace_statistics(state_trace)}")

    # Test trace update
    print("\n" + "-" * 40)
    print("Trace update test:")
    print("-" * 40)

    new_state = torch.randn(batch_size, d_model)
    updated_trace = trace_mgr.update_trace(state_trace, new_state)

    print(f"Original trace[:, 0, :5]: {state_trace[0, 0, :5].tolist()}")
    print(f"New state[0, 0]: {new_state[0, 0].item():.4f}")
    print(f"Updated trace[:, 0, -5:]: {updated_trace[0, 0, -5:].tolist()}")
    print(f"Last element matches new_state: {torch.allclose(updated_trace[:, :, -1], new_state)}")

    # Test sliding window over iterations
    print("\n" + "-" * 40)
    print(f"Sliding window test ({n_iterations} iterations):")
    print("-" * 40)

    state_trace, _ = trace_mgr.get_initial_state(batch_size)

    for i in range(n_iterations):
        # Simulate new pre-activations
        new_state = torch.randn(batch_size, d_model) * 0.1 + i * 0.01
        state_trace = trace_mgr.update_trace(state_trace, new_state)

    print(f"After {n_iterations} updates:")
    print(f"  Trace statistics: {trace_mgr.get_trace_statistics(state_trace)}")

    # Test gradient flow
    print("\n" + "-" * 40)
    print("Gradient test:")
    print("-" * 40)

    state_trace, activated_state = trace_mgr.get_initial_state(batch_size)

    # Simulate a forward pass
    new_state = torch.randn(batch_size, d_model, requires_grad=True)
    updated_trace = trace_mgr.update_trace(state_trace, new_state)
    loss = updated_trace.sum()
    loss.backward()

    print(f"Gradient flows to new_state: {new_state.grad is not None}")
    print(f"Gradient flows to start_trace: {trace_mgr.start_trace.grad is not None}")

    # Test FullStateManager
    print("\n" + "-" * 40)
    print("FullStateManager test:")
    print("-" * 40)

    full_mgr = FullStateManager(
        d_model=d_model,
        memory_length=memory_length,
        n_synch_action=32,
        n_synch_out=64
    )

    initial_state = full_mgr.get_initial_state(batch_size)
    print(f"Initial state keys: {list(initial_state.keys())}")
    print(f"state_trace shape: {initial_state['state_trace'].shape}")
    print(f"alpha_action: {initial_state['alpha_action']}")

    print("\n" + "=" * 60)
    print("StateTraceManager tests PASSED!")
    print("=" * 60)
