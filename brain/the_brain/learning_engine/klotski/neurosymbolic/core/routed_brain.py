"""
Routed NeuroSymbolic Brain - Three-Layer Architecture

Integrates adaptive ATM-R routing with the 10-module NeuroSymbolic brain:
- Layer 1 (Sensory Router): ATM-R routes 6 sensory inputs to brain modules
- Layer 2 (Brain Processing): 10 modules with K₅/K₃,₃ connectivity
- Layer 3 (Module Router): ATM-R routes 10 module outputs to final decision

Architecture:
    6 Sensory Inputs → ATM-R₁ → 10 Brain Modules → ATM-R₂ → Output

This combines:
- Adaptive thalamic gating (ATM-R)
- Brain-inspired processing (NeuroSymbolic Brain)
- Biologically-inspired hierarchical routing
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

from neurosymbolic.core.neurosymbolic_brain import NeuroSymbolicBrain


@dataclass
class RoutingConfig:
    """Configuration for ATM-R routing layers"""
    # Sensory routing (6 inputs → 10 modules)
    sensory_modalities: List[str] = None
    sensory_dims: Dict[str, int] = None

    # Module routing (10 modules → output)
    module_names: List[str] = None
    module_dim: int = 256

    # Routing hyperparameters
    gate_temp: float = 1.5          # Softmax temperature (τ_g) - Higher = more distributed routing
    prediction_lr: float = 0.1      # Prediction learning rate (α)
    input_lr: float = 0.01          # Input weight learning rate (β)
    trn_strength: float = 0.1       # TRN inhibition strength

    # Adaptation
    adapt_gates: bool = True        # Whether to adapt gating online
    adapt_predictions: bool = True  # Whether to adapt predictions online

    def __post_init__(self):
        if self.sensory_modalities is None:
            self.sensory_modalities = ['vision', 'audio', 'touch', 'taste', 'vestibular', 'threat']

        if self.sensory_dims is None:
            # Default dimensions for each sensory modality
            self.sensory_dims = {
                'vision': 64,      # Visual features (VIS module)
                'audio': 32,       # Auditory features (AUD module)
                'touch': 32,       # Somatosensory (SOM module)
                'taste': 16,       # Internal state (INS module)
                'vestibular': 16,  # Spatial (SOM module)
                'threat': 16       # Safety/monitoring (ACC module)
            }

        if self.module_names is None:
            self.module_names = ['VIS', 'AUD', 'SOM', 'LAN', 'DLPFC',
                               'OFC', 'ACC', 'INS', 'MTL', 'DMN']


class SensoryATMRouter(nn.Module):
    """
    ATM-R Layer 1: Routes sensory inputs to brain modules

    6 sensory modalities → 10 brain modules via adaptive gating
    """

    def __init__(self, config: RoutingConfig, target_dim: int = 256):
        super().__init__()
        self.config = config
        self.target_dim = target_dim
        self.num_inputs = len(config.sensory_modalities)
        self.num_outputs = len(config.module_names)

        # Prediction vectors (v_j) for each sensory input
        # These predict the next sensory input
        self.predictions = nn.ParameterDict({
            m: nn.Parameter(torch.randn(config.sensory_dims[m]))
            for m in config.sensory_modalities
        })

        # Generative models (G_j) for each sensory input
        # These generate predictions from prediction vectors
        self.generative_models = nn.ModuleDict({
            m: nn.Linear(config.sensory_dims[m], config.sensory_dims[m], bias=False)
            for m in config.sensory_modalities
        })

        # Input weight matrices (W_j) for Hebbian learning
        self.input_weights = nn.ParameterDict({
            m: nn.Parameter(torch.randn(config.sensory_dims[m], config.sensory_dims[m]) * 0.01)
            for m in config.sensory_modalities
        })

        # Context integration for each input
        self.context_weights = nn.ParameterDict({
            m: nn.Parameter(torch.randn(config.sensory_dims[m]) * 0.01)
            for m in config.sensory_modalities
        })

        # TRN inhibition matrix (num_inputs × num_inputs)
        # Models lateral inhibition between thalamic nuclei
        self.trn_inhibition = nn.Parameter(
            torch.eye(self.num_inputs) * -config.trn_strength +
            torch.randn(self.num_inputs, self.num_inputs) * 0.01
        )

        # Projection layers: sensory dims → target_dim (for each modality)
        self.projections = nn.ModuleDict({
            m: nn.Sequential(
                nn.Linear(config.sensory_dims[m], target_dim),
                nn.LayerNorm(target_dim),
                nn.ReLU()
            )
            for m in config.sensory_modalities
        })

        # Routing matrix: maps 6 sensory channels to 10 brain modules
        # Shape: [num_inputs, num_outputs]
        self.routing_matrix = nn.Parameter(torch.randn(self.num_inputs, self.num_outputs) * 0.1)

        # Gate temperature (learnable)
        self.log_gate_temp = nn.Parameter(torch.log(torch.tensor(config.gate_temp)))

    @property
    def gate_temp(self):
        return torch.exp(self.log_gate_temp)

    def compute_prediction_errors(
        self,
        inputs: Dict[str, torch.Tensor],
        context: Optional[torch.Tensor] = None
    ) -> Dict[str, torch.Tensor]:
        """
        Compute prediction errors for each sensory input

        PE_j = ||x_j - G_j @ v_j||
        """
        batch_size = next(iter(inputs.values())).size(0)
        device = next(iter(inputs.values())).device

        prediction_errors = {}

        for m in self.config.sensory_modalities:
            x_j = inputs.get(m, torch.zeros(batch_size, self.config.sensory_dims[m], device=device))

            # Generate prediction from prediction vector
            v_j = self.predictions[m].unsqueeze(0).expand(batch_size, -1)
            x_pred = self.generative_models[m](v_j)

            # Add context influence if provided
            if context is not None:
                ctx_proj = torch.sum(context * self.context_weights[m], dim=-1, keepdim=True)
                x_pred = x_pred + ctx_proj * v_j

            # Prediction error (L2 norm)
            pe = torch.norm(x_j - x_pred, dim=-1, keepdim=True)
            prediction_errors[m] = pe

        return prediction_errors

    def compute_saliences(
        self,
        prediction_errors: Dict[str, torch.Tensor],
        hazard: Optional[Dict[str, float]] = None
    ) -> torch.Tensor:
        """
        Compute salience for each sensory input

        s_j = PE_j + λ_hazard * h_j
        """
        batch_size = prediction_errors[self.config.sensory_modalities[0]].size(0)
        device = prediction_errors[self.config.sensory_modalities[0]].device

        saliences = torch.zeros(batch_size, self.num_inputs, device=device)

        for j, m in enumerate(self.config.sensory_modalities):
            saliences[:, j] = prediction_errors[m].squeeze(-1)

            # Add hazard/threat signal
            if hazard is not None and m in hazard:
                saliences[:, j] += hazard[m]

        return saliences

    def compute_gates(
        self,
        saliences: torch.Tensor,
        apply_trn: bool = True
    ) -> torch.Tensor:
        """
        Compute gating weights using softmax with optional TRN inhibition

        With TRN: g_j = softmax((s + TRN @ s) / τ_g)
        Without: g_j = softmax(s / τ_g)
        """
        if apply_trn:
            # Apply lateral inhibition
            saliences_inhibited = saliences + torch.matmul(saliences, self.trn_inhibition)
            gates = F.softmax(saliences_inhibited / self.gate_temp, dim=-1)
        else:
            gates = F.softmax(saliences / self.gate_temp, dim=-1)

        return gates

    def forward(
        self,
        inputs: Dict[str, torch.Tensor],
        context: Optional[torch.Tensor] = None,
        hazard: Optional[Dict[str, float]] = None,
        adapt: bool = False
    ) -> Tuple[List[torch.Tensor], Dict]:
        """
        Forward pass through sensory router

        Args:
            inputs: Dict of sensory inputs {modality: [batch, dim]}
            context: Optional context vector [batch, dim]
            hazard: Optional hazard signals {modality: float}
            adapt: Whether to update predictions online

        Returns:
            routed_outputs: List of 10 tensors [batch, target_dim] for each brain module
            info: Dictionary with routing information
        """
        batch_size = next(iter(inputs.values())).size(0)
        device = next(iter(inputs.values())).device

        # 1. Compute prediction errors
        prediction_errors = self.compute_prediction_errors(inputs, context)

        # 2. Compute saliences
        saliences = self.compute_saliences(prediction_errors, hazard)

        # 3. Compute gates
        gates = self.compute_gates(saliences, apply_trn=True)

        # 4. Project inputs to common dimension
        projected_inputs = []
        for m in self.config.sensory_modalities:
            x_j = inputs.get(m, torch.zeros(batch_size, self.config.sensory_dims[m], device=device))
            x_proj = self.projections[m](x_j)  # [batch, target_dim]
            projected_inputs.append(x_proj)

        projected_inputs = torch.stack(projected_inputs, dim=1)  # [batch, num_inputs, target_dim]

        # 5. Apply gates and route to modules
        # gates: [batch, num_inputs]
        # routing_matrix: [num_inputs, num_outputs]
        # Result: [batch, num_outputs] routing weights
        routing_weights = torch.matmul(gates, self.routing_matrix)  # [batch, num_outputs]
        routing_weights = F.softmax(routing_weights, dim=-1)  # Normalize per module

        # 6. Weighted combination for each module
        routed_outputs = []
        for i in range(self.num_outputs):
            # For module i, compute weighted sum of all sensory inputs
            module_weights = routing_weights[:, i:i+1].unsqueeze(-1)  # [batch, 1, 1]
            module_input = torch.sum(projected_inputs * module_weights, dim=1)  # [batch, target_dim]
            routed_outputs.append(module_input)

        # 7. Adapt predictions if requested (online learning)
        if adapt and self.training:
            self._adapt_predictions(inputs, context)

        info = {
            'sensory_gates': gates,
            'routing_weights': routing_weights,
            'prediction_errors': {m: pe.mean().item() for m, pe in prediction_errors.items()},
            'saliences': saliences,
            'gate_temp': self.gate_temp.item()
        }

        return routed_outputs, info

    def _adapt_predictions(
        self,
        inputs: Dict[str, torch.Tensor],
        context: Optional[torch.Tensor] = None
    ):
        """
        Online adaptation of prediction vectors (Hebbian-like learning)

        v_j[t+1] = (1-α)v_j[t] + α·tanh(W_j·x_j + b_j·c)
        """
        with torch.no_grad():
            for m in self.config.sensory_modalities:
                if m not in inputs:
                    continue

                x_j = inputs[m].mean(dim=0)  # Average over batch

                # Hebbian update
                hebbian_input = torch.matmul(self.input_weights[m], x_j)

                if context is not None:
                    ctx_influence = torch.sum(context.mean(dim=0) * self.context_weights[m])
                    hebbian_input = hebbian_input + ctx_influence

                # Prediction update with learning rate
                update = torch.tanh(hebbian_input)
                self.predictions[m].data = (
                    (1 - self.config.prediction_lr) * self.predictions[m].data +
                    self.config.prediction_lr * update
                )


class ModuleATMRouter(nn.Module):
    """
    ATM-R Layer 3: Routes brain module outputs to final decision

    10 brain modules → adaptive gating → output
    """

    def __init__(self, config: RoutingConfig, output_dim: int = 5):
        super().__init__()
        self.config = config
        self.num_modules = len(config.module_names)
        self.output_dim = output_dim

        # Prediction vectors for each module output
        self.predictions = nn.ParameterDict({
            m: nn.Parameter(torch.randn(config.module_dim))
            for m in config.module_names
        })

        # Generative models for module outputs
        self.generative_models = nn.ModuleDict({
            m: nn.Linear(config.module_dim, config.module_dim, bias=False)
            for m in config.module_names
        })

        # TRN inhibition for module competition
        self.trn_inhibition = nn.Parameter(
            torch.eye(self.num_modules) * -config.trn_strength +
            torch.randn(self.num_modules, self.num_modules) * 0.01
        )

        # Gate temperature
        self.log_gate_temp = nn.Parameter(torch.log(torch.tensor(config.gate_temp)))

        # Output projection: weighted module outputs → final output
        self.output_projection = nn.Linear(config.module_dim, output_dim)

    @property
    def gate_temp(self):
        return torch.exp(self.log_gate_temp)

    def compute_prediction_errors(
        self,
        module_outputs: List[torch.Tensor]
    ) -> Dict[str, torch.Tensor]:
        """Compute prediction errors for each module output"""
        prediction_errors = {}

        for i, m in enumerate(self.config.module_names):
            z_i = module_outputs[i]  # [batch, module_dim]
            batch_size = z_i.size(0)

            # Generate prediction
            v_i = self.predictions[m].unsqueeze(0).expand(batch_size, -1)
            z_pred = self.generative_models[m](v_i)

            # Prediction error
            pe = torch.norm(z_i - z_pred, dim=-1, keepdim=True)
            prediction_errors[m] = pe

        return prediction_errors

    def compute_gates(
        self,
        prediction_errors: Dict[str, torch.Tensor],
        apply_trn: bool = True
    ) -> torch.Tensor:
        """Compute gating weights for module outputs"""
        batch_size = prediction_errors[self.config.module_names[0]].size(0)
        device = prediction_errors[self.config.module_names[0]].device

        # Saliences from prediction errors
        saliences = torch.zeros(batch_size, self.num_modules, device=device)
        for i, m in enumerate(self.config.module_names):
            saliences[:, i] = prediction_errors[m].squeeze(-1)

        # Apply TRN inhibition
        if apply_trn:
            saliences_inhibited = saliences + torch.matmul(saliences, self.trn_inhibition)
            gates = F.softmax(saliences_inhibited / self.gate_temp, dim=-1)
        else:
            gates = F.softmax(saliences / self.gate_temp, dim=-1)

        return gates

    def forward(
        self,
        module_outputs: List[torch.Tensor],
        adapt: bool = False
    ) -> Tuple[torch.Tensor, Dict]:
        """
        Forward pass through module router

        Args:
            module_outputs: List of 10 tensors [batch, module_dim]
            adapt: Whether to adapt predictions online

        Returns:
            output: Final output [batch, output_dim]
            info: Routing information
        """
        # 1. Compute prediction errors
        prediction_errors = self.compute_prediction_errors(module_outputs)

        # 2. Compute gates
        gates = self.compute_gates(prediction_errors, apply_trn=True)

        # 3. Weighted combination of module outputs
        module_stack = torch.stack(module_outputs, dim=1)  # [batch, num_modules, module_dim]
        gates_expanded = gates.unsqueeze(-1)  # [batch, num_modules, 1]

        weighted_output = torch.sum(module_stack * gates_expanded, dim=1)  # [batch, module_dim]

        # 4. Project to output dimension
        output = self.output_projection(weighted_output)  # [batch, output_dim]

        # 5. Adapt predictions if requested
        if adapt and self.training:
            self._adapt_predictions(module_outputs)

        info = {
            'module_gates': gates,
            'prediction_errors': {m: pe.mean().item() for m, pe in prediction_errors.items()},
            'gate_temp': self.gate_temp.item()
        }

        return output, info

    def _adapt_predictions(self, module_outputs: List[torch.Tensor]):
        """Online adaptation of module prediction vectors"""
        with torch.no_grad():
            for i, m in enumerate(self.config.module_names):
                z_i = module_outputs[i].mean(dim=0)  # Average over batch

                # Simple momentum update
                self.predictions[m].data = (
                    (1 - self.config.prediction_lr) * self.predictions[m].data +
                    self.config.prediction_lr * z_i
                )


class RoutedNeuroSymbolicBrain(nn.Module):
    """
    Complete Routed NeuroSymbolic Brain

    Three-layer hierarchical architecture:
    1. Sensory ATM-R: Routes 6 sensory inputs to 10 brain modules
    2. Brain Processing: 10 modules with K₅/K₃,₃ connectivity
    3. Module ATM-R: Routes 10 module outputs to final decision

    This combines adaptive thalamic routing with brain-inspired processing.
    """

    def __init__(
        self,
        feature_dim: int = 256,
        num_actions: int = 40,
        memory_size: int = 100,
        use_symbolic_rules: bool = True,
        routing_config: Optional[RoutingConfig] = None,
        use_sensory_routing: bool = True,
        use_module_routing: bool = True
    ):
        super().__init__()

        self.feature_dim = feature_dim
        self.num_actions = num_actions
        self.use_sensory_routing = use_sensory_routing
        self.use_module_routing = use_module_routing

        # Routing configuration
        if routing_config is None:
            routing_config = RoutingConfig(module_dim=feature_dim)
        self.routing_config = routing_config

        # Layer 1: Sensory Router (optional)
        if use_sensory_routing:
            self.sensory_router = SensoryATMRouter(
                config=routing_config,
                target_dim=feature_dim
            )

        # Layer 2: NeuroSymbolic Brain (10 modules)
        self.brain = NeuroSymbolicBrain(
            feature_dim=feature_dim,
            num_actions=num_actions,
            memory_size=memory_size,
            use_symbolic_rules=use_symbolic_rules
        )

        # Layer 3: Module Router (optional)
        if use_module_routing:
            self.module_router = ModuleATMRouter(
                config=routing_config,
                output_dim=num_actions
            )

    def forward(
        self,
        board_tensor: torch.Tensor,
        sensory_inputs: Optional[Dict[str, torch.Tensor]] = None,
        context: Optional[torch.Tensor] = None,
        hazard: Optional[Dict[str, float]] = None,
        valid_actions: Optional[List] = None,
        return_components: bool = False,
        adapt_routing: bool = False
    ) -> Dict[str, torch.Tensor]:
        """
        Complete forward pass through routed brain

        Args:
            board_tensor: Board state [batch, 5, 4]
            sensory_inputs: Optional dict of sensory inputs (if using sensory routing)
            context: Optional context vector
            hazard: Optional hazard signals
            valid_actions: Valid actions for symbolic masking
            return_components: Whether to return all intermediate outputs
            adapt_routing: Whether to adapt routing online

        Returns:
            Dict containing outputs and routing information
        """
        info = {}

        # === LAYER 1: SENSORY ROUTING ===
        if self.use_sensory_routing and sensory_inputs is not None:
            # Route sensory inputs to modules
            routed_inputs, routing_info = self.sensory_router(
                inputs=sensory_inputs,
                context=context,
                hazard=hazard,
                adapt=adapt_routing
            )
            info['sensory_routing'] = routing_info
        else:
            routed_inputs = None

        # === LAYER 2: BRAIN PROCESSING ===
        brain_output = self.brain(
            board_tensor=board_tensor,
            valid_actions=valid_actions,
            return_components=True  # Always get module outputs
        )

        # Extract module outputs for routing
        # Map module names to brain output keys (brain uses various naming conventions)
        module_feature_map = {
            'VIS': 'vis_features',
            'AUD': 'aud_features',
            'SOM': 'som_features',
            'LAN': 'lan_features',
            'MTL': 'mtl_features',
            'DLPFC': 'dlpfc_hidden',      # Brain uses dlpfc_hidden, not dlpfc_features
            'OFC': 'policy_features',      # OFC contributes to policy through value
            'ACC': 'conflict_features',    # ACC tracks conflict
            'INS': 'ins_state',            # INS uses state representation
            'DMN': 'dmn_state',            # DMN uses state representation
        }

        module_outputs = []
        for module_name in self.routing_config.module_names:
            # Use explicit mapping first, then try standard naming, then fallback
            feature_key = module_feature_map.get(module_name)
            if feature_key and feature_key in brain_output:
                module_outputs.append(brain_output[feature_key])
            elif f'{module_name.lower()}_features' in brain_output:
                module_outputs.append(brain_output[f'{module_name.lower()}_features'])
            else:
                # Fallback: use policy_features as shared representation
                module_outputs.append(brain_output.get('policy_features', brain_output['action_logits']))

        # === LAYER 3: MODULE ROUTING ===
        if self.use_module_routing:
            final_output, module_routing_info = self.module_router(
                module_outputs=module_outputs,
                adapt=adapt_routing
            )
            info['module_routing'] = module_routing_info

            # Use routed output as action logits
            output = {
                'action_logits': final_output,
                'value': brain_output['value'],
                'consciousness': brain_output['consciousness'],
                'dmn_energy': brain_output['dmn_energy'],
                'error_magnitude': brain_output['error_magnitude']
            }
        else:
            # Use brain's direct output
            output = {
                'action_logits': brain_output['action_logits'],
                'value': brain_output['value'],
                'consciousness': brain_output['consciousness'],
                'dmn_energy': brain_output['dmn_energy'],
                'error_magnitude': brain_output['error_magnitude']
            }

        # Add routing info
        output['routing_info'] = info

        # Add all components if requested
        if return_components:
            output.update(brain_output)

        return output

    def select_action(
        self,
        board_tensor: torch.Tensor,
        sensory_inputs: Optional[Dict[str, torch.Tensor]] = None,
        context: Optional[torch.Tensor] = None,
        hazard: Optional[Dict[str, float]] = None,
        valid_actions: Optional[List] = None,
        deterministic: bool = False,
        adapt_routing: bool = False
    ) -> Tuple[torch.Tensor, torch.Tensor, Dict]:
        """
        Select action using routed brain

        Returns:
            actions: Selected actions [batch]
            log_probs: Log probabilities [batch]
            info: Information dict
        """
        output = self.forward(
            board_tensor=board_tensor,
            sensory_inputs=sensory_inputs,
            context=context,
            hazard=hazard,
            valid_actions=valid_actions,
            return_components=False,
            adapt_routing=adapt_routing
        )

        action_logits = output['action_logits']
        action_probs = F.softmax(action_logits, dim=-1)

        if deterministic:
            actions = torch.argmax(action_probs, dim=-1)
            log_probs = torch.log(action_probs.gather(1, actions.unsqueeze(1)) + 1e-8)
        else:
            dist = torch.distributions.Categorical(probs=action_probs)
            actions = dist.sample()
            log_probs = dist.log_prob(actions)

        info = {
            'value': output['value'],
            'consciousness': output['consciousness'],
            'action_probs': action_probs,
            'routing_info': output['routing_info']
        }

        return actions, log_probs, info

    def reset_state(self):
        """Reset all brain and routing states"""
        self.brain.reset_state()

    def get_total_parameters(self) -> int:
        """Get total number of trainable parameters"""
        return sum(p.numel() for p in self.parameters())

    def __repr__(self):
        brain_params = sum(p.numel() for p in self.brain.parameters())
        sensory_params = sum(p.numel() for p in self.sensory_router.parameters()) if self.use_sensory_routing else 0
        module_params = sum(p.numel() for p in self.module_router.parameters()) if self.use_module_routing else 0

        return (
            f"RoutedNeuroSymbolicBrain(\n"
            f"  sensory_routing={'enabled' if self.use_sensory_routing else 'disabled'} ({sensory_params:,} params),\n"
            f"  brain=10 modules ({brain_params:,} params),\n"
            f"  module_routing={'enabled' if self.use_module_routing else 'disabled'} ({module_params:,} params),\n"
            f"  total_parameters={self.get_total_parameters():,}\n"
            f")"
        )


if __name__ == "__main__":
    # Test routed brain
    print("Testing Routed NeuroSymbolic Brain...")
    print("="*70)

    # Create routed brain
    routed_brain = RoutedNeuroSymbolicBrain(
        feature_dim=256,
        num_actions=40,
        memory_size=100,
        use_symbolic_rules=True,
        use_sensory_routing=True,
        use_module_routing=True
    )

    print(routed_brain)
    print()

    # Test with dummy inputs
    batch_size = 2
    board = torch.randint(0, 11, (batch_size, 5, 4))

    # Dummy sensory inputs
    sensory_inputs = {
        'vision': torch.randn(batch_size, 64),
        'audio': torch.randn(batch_size, 32),
        'touch': torch.randn(batch_size, 32),
        'taste': torch.randn(batch_size, 16),
        'vestibular': torch.randn(batch_size, 16),
        'threat': torch.randn(batch_size, 16)
    }

    print("Running forward pass...")
    output = routed_brain(
        board_tensor=board,
        sensory_inputs=sensory_inputs,
        return_components=True,
        adapt_routing=False
    )

    print("\nOutputs:")
    print(f"  action_logits: {output['action_logits'].shape}")
    print(f"  value: {output['value'].shape}")
    print(f"  consciousness: {output['consciousness'].shape}")

    print("\nSensory Routing Info:")
    if 'sensory_routing' in output['routing_info']:
        sr_info = output['routing_info']['sensory_routing']
        print(f"  sensory_gates: {sr_info['sensory_gates'].shape}")
        print(f"  routing_weights: {sr_info['routing_weights'].shape}")
        print(f"  gate_temp: {sr_info['gate_temp']:.4f}")
        print(f"  prediction_errors: {sr_info['prediction_errors']}")

    print("\nModule Routing Info:")
    if 'module_routing' in output['routing_info']:
        mr_info = output['routing_info']['module_routing']
        print(f"  module_gates: {mr_info['module_gates'].shape}")
        print(f"  gate_temp: {mr_info['gate_temp']:.4f}")
        print(f"  Top-3 modules: {torch.topk(mr_info['module_gates'][0], 3).indices.tolist()}")

    print("\n" + "="*70)
    print("Routed Brain working correctly!")
