"""
Continuous Thought Machine (CTM) Layer for Klotski

Adapted from Sakana AI's CTM (https://github.com/SakanaAI/continuous-thought-machines)

Key innovations:
1. Inner thought loop (50-100 ticks) - think before deciding
2. Synchronization matrix - pairs of neurons syncing over time
3. Certainty gating - stop thinking when confident

This allows the brain to "think longer" on difficult puzzle states.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import math
from typing import Tuple, Optional


class NeuronLevelMemory(nn.Module):
    """
    Neuron-Level Model with Memory (NLMS)

    Each neuron processes its own history of incoming signals
    with private parameters (per-neuron MLPs).

    Args:
        d_model: Number of neurons
        memory_length: How many timesteps of history to remember
        hidden_dim: Hidden dimension for deep memory
    """

    def __init__(self, d_model: int, memory_length: int, hidden_dim: int = 32):
        super().__init__()
        self.d_model = d_model
        self.memory_length = memory_length

        # Each neuron has its own 2-layer MLP to process history
        # Shape: (d_model, memory_length) -> (d_model, hidden_dim) -> (d_model, 1)
        self.mlp1 = nn.Linear(memory_length, hidden_dim, bias=True)
        self.mlp2 = nn.Linear(hidden_dim, 1, bias=True)
        self.activation = nn.GELU()

    def forward(self, trace: torch.Tensor) -> torch.Tensor:
        """
        Process neuron histories

        Args:
            trace: (batch, d_model, memory_length) - history of activations

        Returns:
            output: (batch, d_model) - post-activations
        """
        batch_size, d_model, mem_len = trace.shape

        # Process each neuron's history independently
        # (batch, d_model, mem_len) -> (batch, d_model, hidden_dim)
        x = self.mlp1(trace)
        x = self.activation(x)

        # (batch, d_model, hidden_dim) -> (batch, d_model, 1)
        x = self.mlp2(x)

        # (batch, d_model, 1) -> (batch, d_model)
        x = x.squeeze(-1)

        return x


class SynapseModel(nn.Module):
    """
    Synapse Model (simplified from CTM's U-Net)

    Processes connections between neurons.
    For simplicity, we use a small MLP instead of full U-Net.

    Args:
        d_model: Number of neurons
        depth: Number of layers (1 = linear, >1 = MLP)
    """

    def __init__(self, d_model: int, depth: int = 2):
        super().__init__()
        self.d_model = d_model

        if depth == 1:
            # Linear synapse
            self.synapse = nn.Linear(d_model, d_model)
        else:
            # MLP synapse
            hidden = d_model
            layers = []
            layers.append(nn.Linear(d_model, hidden))
            layers.append(nn.GELU())

            for _ in range(depth - 2):
                layers.append(nn.Linear(hidden, hidden))
                layers.append(nn.GELU())

            layers.append(nn.Linear(hidden, d_model))
            self.synapse = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (batch, d_model) - activated state

        Returns:
            output: (batch, d_model) - processed state
        """
        return self.synapse(x)


class CTMLayer(nn.Module):
    """
    Continuous Thought Machine Layer

    Implements inner thought loop with synchronization and certainty gating.

    Args:
        d_model: Number of neurons
        iterations: Number of inner thought ticks (50-100)
        memory_length: History length for each neuron
        n_synch: Number of neurons to use for synchronization
        certainty_threshold: Stop thinking when certainty exceeds this (0.0 = disabled)
        synapse_depth: Depth of synapse model
        action_dim: Number of actions (for per-tick predictions)
        enable_loss_selection: Enable Sakana AI loss selection strategy
    """

    def __init__(
        self,
        d_model: int = 256,
        iterations: int = 75,
        memory_length: int = 25,
        n_synch: int = 32,
        certainty_threshold: float = 0.8,
        synapse_depth: int = 2,
        memory_hidden_dim: int = 32,
        action_dim: int = 40,
        enable_loss_selection: bool = True
    ):
        super().__init__()
        self.d_model = d_model
        self.iterations = iterations
        self.memory_length = memory_length
        self.n_synch = n_synch
        self.certainty_threshold = certainty_threshold
        self.enable_loss_selection = enable_loss_selection

        # Core CTM components
        self.synapse = SynapseModel(d_model, synapse_depth)
        self.trace_processor = NeuronLevelMemory(d_model, memory_length, memory_hidden_dim)

        # Per-tick prediction head (for loss selection)
        if enable_loss_selection:
            self.tick_prediction_head = nn.Sequential(
                nn.Linear(n_synch, 128),
                nn.ReLU(),
                nn.Linear(128, action_dim)
            )

        # Start state parameters (learnable)
        self.register_parameter(
            'start_state',
            nn.Parameter(torch.zeros(d_model).uniform_(-math.sqrt(1/d_model), math.sqrt(1/d_model)))
        )
        self.register_parameter(
            'start_trace',
            nn.Parameter(torch.zeros(d_model, memory_length).uniform_(
                -math.sqrt(1/(d_model + memory_length)),
                math.sqrt(1/(d_model + memory_length))
            ))
        )

        # Synchronization: randomly select neuron pairs
        # For simplicity, we use random-pairing (each of n_synch neurons paired with another)
        self.register_buffer('synch_indices_i', torch.randperm(d_model)[:n_synch])
        self.register_buffer('synch_indices_j', torch.randperm(d_model)[:n_synch])

    def compute_synchronization(self, activated_states: torch.Tensor) -> torch.Tensor:
        """
        Compute synchronization between neuron pairs over time

        Args:
            activated_states: (batch, iterations, d_model) - all tick activations

        Returns:
            synch: (batch, n_synch) - synchronization representation
        """
        batch_size, T, d_model = activated_states.shape

        # Select neurons for synchronization
        # (batch, T, n_synch)
        neurons_i = activated_states[:, :, self.synch_indices_i]
        neurons_j = activated_states[:, :, self.synch_indices_j]

        # Compute normalized cross-correlation (synchronization measure)
        # Normalize each signal
        mean_i = neurons_i.mean(dim=1, keepdim=True)
        mean_j = neurons_j.mean(dim=1, keepdim=True)
        std_i = neurons_i.std(dim=1, keepdim=True) + 1e-8
        std_j = neurons_j.std(dim=1, keepdim=True) + 1e-8

        norm_i = (neurons_i - mean_i) / std_i
        norm_j = (neurons_j - mean_j) / std_j

        # Cross-correlation: (batch, n_synch)
        synch = (norm_i * norm_j).mean(dim=1)

        return synch

    def compute_certainty(self, synch: torch.Tensor) -> torch.Tensor:
        """
        Compute certainty from synchronization representation

        High certainty = neurons are synchronized (confident)
        Low certainty = neurons are not synchronized (uncertain)

        Args:
            synch: (batch, n_synch) - synchronization values

        Returns:
            certainty: (batch,) - certainty score [0, 1]
        """
        # Certainty = mean absolute synchronization
        # High abs sync = neurons strongly correlated or anti-correlated = certain
        certainty = synch.abs().mean(dim=-1)
        return certainty

    def forward(
        self,
        input_state: torch.Tensor,
        max_ticks: Optional[int] = None,
        return_all_ticks: bool = False
    ):
        """
        Run inner thought loop

        Args:
            input_state: (batch, d_model) - initial state from encoder
            max_ticks: Override iterations with custom max
            return_all_ticks: Return all tick states and predictions (for loss selection/visualization)

        Returns:
            If return_all_ticks=False:
                synch: (batch, n_synch) - synchronization representation
                certainty: (batch,) - certainty scores
                ticks_used: int - number of ticks actually used
            If return_all_ticks=True:
                dict with:
                    - synch: (batch, n_synch)
                    - certainty: (batch,)
                    - ticks_used: int
                    - all_predictions: (batch, ticks, action_dim) - predictions at each tick
                    - all_certainties: (batch, ticks) - certainties at each tick
                    - all_synchs: (batch, ticks, n_synch) - synch at each tick
        """
        batch_size = input_state.shape[0]
        max_ticks = max_ticks or self.iterations

        # Initialize state and trace
        activated_state = self.start_state.unsqueeze(0).expand(batch_size, -1)
        trace = self.start_trace.unsqueeze(0).expand(batch_size, -1, -1).clone()

        # Add input to initial state
        activated_state = activated_state + input_state

        # Storage for all ticks
        all_states = []
        all_predictions = [] if (return_all_ticks and self.enable_loss_selection) else None
        all_certainties = [] if return_all_ticks else None
        all_synchs = [] if return_all_ticks else None
        ticks_used = max_ticks

        # Inner thought loop with early stopping
        for tick in range(max_ticks):
            # 1. Process current activated state through synapses
            pre_activation = self.synapse(activated_state)

            # 2. Update trace (shift left and add new pre-activation)
            trace = torch.cat([trace[:, :, 1:], pre_activation.unsqueeze(-1)], dim=-1)

            # 3. Process trace with neuron-level models to get new activation
            activated_state = self.trace_processor(trace)
            activated_state = torch.tanh(activated_state)  # Keep bounded

            # Store state (always needed for synchronization)
            all_states.append(activated_state.clone())

            # Compute per-tick predictions and certainties (for loss selection)
            if return_all_ticks and tick >= 5:  # Start after warmup
                # Use recent window for synchronization
                recent_window = min(10, len(all_states))
                recent_states = torch.stack(all_states[-recent_window:], dim=1)

                synch_temp = self.compute_synchronization(recent_states)
                certainty_temp = self.compute_certainty(synch_temp)

                all_synchs.append(synch_temp)
                all_certainties.append(certainty_temp)

                if self.enable_loss_selection:
                    prediction_temp = self.tick_prediction_head(synch_temp)
                    all_predictions.append(prediction_temp)

            # Early stopping check (every 5 ticks after warmup)
            if self.certainty_threshold > 0 and tick >= 10 and (tick + 1) % 5 == 0:
                # Compute certainty from recent history (last 10 states or all available)
                recent_window = min(10, len(all_states))
                recent_states = torch.stack(all_states[-recent_window:], dim=1)

                synch_temp = self.compute_synchronization(recent_states)
                certainty_temp = self.compute_certainty(synch_temp)

                # Check if all samples in batch exceed threshold
                if (certainty_temp >= self.certainty_threshold).all():
                    ticks_used = tick + 1
                    break

        # Stack all ticks: (batch, ticks_used, d_model)
        all_states = torch.stack(all_states, dim=1)

        # Compute synchronization representation
        synch = self.compute_synchronization(all_states)

        # Compute certainty (final value)
        certainty = self.compute_certainty(synch)

        if return_all_ticks:
            result = {
                'synch': synch,
                'certainty': certainty,
                'ticks_used': ticks_used
            }
            if all_predictions:
                result['all_predictions'] = torch.stack(all_predictions, dim=1)
            if all_certainties:
                result['all_certainties'] = torch.stack(all_certainties, dim=1)
            if all_synchs:
                result['all_synchs'] = torch.stack(all_synchs, dim=1)
            return result
        else:
            return synch, certainty, ticks_used


class CTMPolicy(nn.Module):
    """
    CTM-augmented policy for Klotski

    Wraps the NeuroSymbolic brain with a CTM layer for inner thought.

    Args:
        brain: NeuroSymbolic brain (encoder + modules)
        ctm: CTM layer
        action_dim: Number of possible actions
    """

    def __init__(self, brain: nn.Module, ctm: CTMLayer, action_dim: int = 40):
        super().__init__()
        self.brain = brain
        self.ctm = ctm
        self.action_dim = action_dim

        # Output head: synch -> actions + value
        synch_dim = ctm.n_synch
        self.action_head = nn.Sequential(
            nn.Linear(synch_dim, 256),
            nn.ReLU(),
            nn.Linear(256, action_dim)
        )
        self.value_head = nn.Sequential(
            nn.Linear(synch_dim, 256),
            nn.ReLU(),
            nn.Linear(256, 1)
        )

    def forward(
        self,
        state: torch.Tensor,
        valid_actions: Optional[list] = None,
        return_components: bool = False
    ):
        """
        Forward pass with CTM thinking

        Args:
            state: (batch, features) - puzzle state
            valid_actions: List of valid action masks per batch
            return_components: Return brain components (consciousness, etc.)

        Returns:
            dict with action_logits, value, certainty, consciousness, etc.
        """
        # 1. Encode state with brain
        with torch.no_grad():  # Brain is frozen for now
            brain_output = self.brain(state, valid_actions, return_components=True)

        # Get brain's encoded representation
        # Use DMN state as the input to CTM (integrated consciousness representation)
        brain_features = brain_output['dmn_state']  # (batch, d_model)

        # 2. CTM inner thought loop
        synch, certainty, ticks_used = self.ctm(brain_features)

        # 3. Output from synchronization
        action_logits = self.action_head(synch)
        value = self.value_head(synch).squeeze(-1)

        # Apply action masking if provided
        if valid_actions is not None:
            batch_size = action_logits.shape[0]
            mask = torch.zeros(batch_size, self.action_dim, device=action_logits.device)

            for i, valid_acts in enumerate(valid_actions):
                if valid_acts is None:
                    continue

                # Handle both integer lists and Action object lists
                if isinstance(valid_acts, list):
                    if len(valid_acts) > 0:
                        # Check if it's a list of Action objects or integers
                        if hasattr(valid_acts[0], '__class__') and valid_acts[0].__class__.__name__ == 'Action':
                            # Action objects - use enumerate index
                            for action_idx, _ in enumerate(valid_acts):
                                if action_idx < self.action_dim:
                                    mask[i, action_idx] = 1.0
                        else:
                            # Integer indices
                            mask[i, valid_acts] = 1.0

            # Mask invalid actions with large negative value
            action_logits = action_logits.masked_fill(mask == 0, -1e9)

        # Build output dict
        output = {
            'action_logits': action_logits,
            'value': value,
            'certainty': certainty,
            'ticks_used': ticks_used,
            'synchronization': synch,
            # Pass through brain components (required by PPOTrainer)
            'consciousness': brain_output.get('consciousness', torch.zeros_like(certainty)),
            'dmn_energy': brain_output.get('dmn_energy', torch.zeros_like(certainty)),
            'error_magnitude': brain_output.get('error_magnitude', torch.zeros_like(certainty)),
        }

        if return_components:
            output['brain_output'] = brain_output

        return output

    def compute_loss_with_selection(
        self,
        state: torch.Tensor,
        target_actions: torch.Tensor,
        valid_actions: Optional[list] = None
    ):
        """
        Compute loss using Sakana AI's loss selection strategy

        Selects loss from two ticks:
        1. Tick with lowest cross-entropy (most accurate prediction)
        2. Tick with highest certainty (most confident)
        Averages these two losses.

        Args:
            state: (batch, features) - puzzle state
            target_actions: (batch,) - ground truth actions
            valid_actions: Optional action masks

        Returns:
            dict with:
                - loss: Selected loss value
                - min_loss_tick: Tick index with lowest loss
                - max_cert_tick: Tick index with highest certainty
                - all_losses: (batch, ticks) - losses at each tick
                - all_certainties: (batch, ticks) - certainties at each tick
        """
        # Encode state with brain
        with torch.no_grad():
            brain_output = self.brain(state, valid_actions, return_components=True)

        brain_features = brain_output['dmn_state']

        # CTM forward with per-tick tracking
        ctm_output = self.ctm(brain_features, return_all_ticks=True)

        # Get per-tick predictions and certainties
        all_predictions = ctm_output['all_predictions']  # (batch, ticks, action_dim)
        all_certainties = ctm_output['all_certainties']  # (batch, ticks)

        batch_size, num_ticks, action_dim = all_predictions.shape

        # Compute loss at each tick
        all_losses = []
        for tick in range(num_ticks):
            tick_predictions = all_predictions[:, tick, :]  # (batch, action_dim)
            tick_loss = F.cross_entropy(tick_predictions, target_actions, reduction='none')
            all_losses.append(tick_loss)

        all_losses = torch.stack(all_losses, dim=1)  # (batch, ticks)

        # Select ticks for each sample in batch
        # Tick with lowest loss (most accurate)
        min_loss_ticks = all_losses.argmin(dim=1)  # (batch,)

        # Tick with highest certainty (most confident)
        max_cert_ticks = all_certainties.argmax(dim=1)  # (batch,)

        # Gather losses from selected ticks
        min_loss_values = all_losses.gather(1, min_loss_ticks.unsqueeze(1)).squeeze(1)
        max_cert_losses = all_losses.gather(1, max_cert_ticks.unsqueeze(1)).squeeze(1)

        # Average the two selected losses
        selected_loss = (min_loss_values + max_cert_losses) / 2.0
        final_loss = selected_loss.mean()  # Average over batch

        return {
            'loss': final_loss,
            'min_loss_tick': min_loss_ticks.float().mean().item(),  # Average tick index
            'max_cert_tick': max_cert_ticks.float().mean().item(),
            'all_losses': all_losses,
            'all_certainties': all_certainties,
            'num_ticks': num_ticks
        }

    def reset_state(self):
        """Reset brain state (delegated to wrapped brain)"""
        self.brain.reset_state()


def create_ctm_policy(brain: nn.Module, config: dict) -> CTMPolicy:
    """
    Factory function to create CTM-augmented policy

    Args:
        brain: Existing NeuroSymbolic brain
        config: CTM configuration dict

    Returns:
        CTMPolicy instance
    """
    action_dim = config.get('action_dim', 40)

    ctm = CTMLayer(
        d_model=config.get('d_model', 256),
        iterations=config.get('iterations', 75),
        memory_length=config.get('memory_length', 25),
        n_synch=config.get('n_synch', 32),
        certainty_threshold=config.get('certainty_threshold', 0.8),
        synapse_depth=config.get('synapse_depth', 2),
        memory_hidden_dim=config.get('memory_hidden_dim', 32),
        action_dim=action_dim,
        enable_loss_selection=config.get('enable_loss_selection', True)
    )

    policy = CTMPolicy(brain, ctm, action_dim)

    return policy
