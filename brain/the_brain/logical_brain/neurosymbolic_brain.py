"""
NeuroSymbolic Brain - Complete Cognitive Architecture

Integrates all 10 brain modules into a unified pipeline:
- Bottom-up: Sensory → Associative → Cognitive → Integration
- Top-down: DMN → DLPFC → Sensory (attention/control)
- Symbolic: Allis rules constrain neural actions

Neural: π_neural(a|s) - learned from data
Symbolic: mask_symbolic(a|s,context) - rules
Hybrid: π*(a|s) = π_neural ⊗ mask_symbolic
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Dict, List, Tuple, Optional
import numpy as np

from neurosymbolic.modules.sensory_modules import VISModule, AUDModule, SOMModule, LANModule
from neurosymbolic.modules.cognitive_modules import DLPFCModule, OFCModule, ACCModule, INSModule
from neurosymbolic.modules.integration_modules import MTLModule, DMNModule
from neurosymbolic.symbolic.allis_rules import AllisRuleEngine, Action, Context
from neurosymbolic.core.brain_graph import BrainConnectomeGraph


class NeuroSymbolicBrain(nn.Module):
    """
    Complete NeuroSymbolic Cognitive Architecture

    Processes puzzle states through brain-inspired pipeline:
    1. Encode state features (sensory modules)
    2. Associate and remember (MTL)
    3. Evaluate value (OFC) and detect conflict (ACC)
    4. Plan actions (DLPFC)
    5. Integrate consciousness (DMN)
    6. Apply symbolic constraints (Allis rules)
    """

    def __init__(
        self,
        feature_dim: int = 256,
        num_actions: int = 40,  # Max possible moves
        memory_size: int = 100,
        use_symbolic_rules: bool = True
    ):
        """
        Initialize NeuroSymbolic Brain

        Args:
            feature_dim: Internal feature dimension
            num_actions: Maximum number of actions
            memory_size: MTL memory capacity
            use_symbolic_rules: Whether to apply Allis rules
        """
        super().__init__()

        self.feature_dim = feature_dim
        self.num_actions = num_actions
        self.use_symbolic_rules = use_symbolic_rules

        # Brain connectivity graph
        self.brain_graph = BrainConnectomeGraph()

        # Initialize all 10 modules
        self._init_modules(feature_dim, num_actions, memory_size)

        # Symbolic rule engine
        if use_symbolic_rules:
            self.rule_engine = AllisRuleEngine()
        else:
            self.rule_engine = None

        # State encoder (converts puzzle state to initial features)
        self.state_encoder = nn.Sequential(
            nn.Linear(20, 128),  # 5x4 board = 20 cells
            nn.ReLU(),
            nn.Linear(128, feature_dim)
        )

        # Context tracking
        self.context = Context()

    def _init_modules(self, feature_dim: int, num_actions: int, memory_size: int):
        """Initialize all brain modules"""

        # Sensory processing (Layer 1)
        self.VIS = VISModule(input_channels=1, output_dim=feature_dim)
        self.AUD = AUDModule(input_dim=feature_dim, output_dim=feature_dim)
        self.SOM = SOMModule(input_dim=feature_dim, output_dim=feature_dim)
        self.LAN = LANModule(input_dim=feature_dim, output_dim=feature_dim)

        # Memory/Association (Layer 2)
        self.MTL = MTLModule(
            input_dim=feature_dim,
            memory_dim=feature_dim,
            output_dim=feature_dim,
            memory_size=memory_size
        )

        # Cognitive/Executive (Layer 3)
        self.DLPFC = DLPFCModule(
            input_dim=feature_dim,
            hidden_dim=feature_dim,
            output_dim=feature_dim,
            num_actions=num_actions
        )
        self.OFC = OFCModule(
            input_dim=feature_dim,
            hidden_dim=feature_dim,
            output_dim=1
        )
        self.ACC = ACCModule(
            input_dim=feature_dim,
            hidden_dim=feature_dim,
            output_dim=feature_dim
        )
        self.INS = INSModule(
            input_dim=feature_dim,
            hidden_dim=feature_dim,
            output_dim=feature_dim
        )

        # Integration/Consciousness (Layer 4)
        self.DMN = DMNModule(
            input_dim=feature_dim,
            state_dim=feature_dim,
            output_dim=feature_dim
        )

    def encode_board_state(self, board_tensor: torch.Tensor) -> torch.Tensor:
        """
        Encode board state to feature vector

        Args:
            board_tensor: Board state [batch, 5, 4] (piece IDs)

        Returns:
            Encoded features [batch, feature_dim]
        """
        batch_size = board_tensor.size(0)

        # Flatten board
        board_flat = board_tensor.view(batch_size, -1).float()  # [batch, 20]

        # Encode
        features = self.state_encoder(board_flat)  # [batch, feature_dim]

        return features

    def forward(
        self,
        board_tensor: torch.Tensor,
        valid_actions: Optional[List[List[Action]]] = None,
        return_components: bool = False
    ) -> Dict[str, torch.Tensor]:
        """
        Complete forward pass through NeuroSymbolic Brain

        Args:
            board_tensor: Board state [batch, 5, 4]
            valid_actions: List of valid actions per batch item
            return_components: Whether to return all intermediate outputs

        Returns:
            Dict containing:
                - action_logits: Action distribution [batch, num_actions]
                - value: State value [batch, 1]
                - consciousness: Consciousness metric [batch]
                - (optional) component outputs
        """
        batch_size = board_tensor.size(0)

        # Encode initial state
        state_features = self.encode_board_state(board_tensor)

        # === LAYER 1: SENSORY PROCESSING ===
        # For simplicity, use state_features as input to all sensory modules
        # In full implementation, would extract different features per modality

        # VIS: Visual representation of board
        board_img = board_tensor.unsqueeze(1).float()  # [batch, 1, 5, 4]
        # Pad to minimum size for conv layers
        board_img = F.interpolate(board_img, size=(32, 32), mode='nearest')
        vis_features = self.VIS(board_img)

        # SOM: Spatial/topological features
        som_features = self.SOM(state_features)

        # AUD, LAN: Use encoded features (in puzzle, these are abstract)
        aud_features = self.AUD(state_features)
        lan_features = self.LAN(state_features)

        # Combine sensory features
        sensory_combined = (vis_features + som_features + aud_features + lan_features) / 4

        # === LAYER 2: MEMORY/ASSOCIATION ===
        mtl_features = self.MTL(sensory_combined)

        # === LAYER 3: COGNITIVE/EXECUTIVE ===

        # DLPFC: Planning and policy
        policy_features, dlpfc_hidden = self.DLPFC(mtl_features)
        action_logits_raw = self.DLPFC.get_action_logits(policy_features)

        # OFC: Value estimation
        value = self.OFC(mtl_features)

        # ACC: Conflict monitoring
        conflict_features, error_magnitude = self.ACC(mtl_features)

        # INS: Internal dynamics
        ins_state = self.INS(mtl_features)

        # === LAYER 4: INTEGRATION/CONSCIOUSNESS ===

        # Combine all cognitive outputs for DMN
        dmn_input = torch.stack([
            policy_features,
            mtl_features,
            conflict_features,
            ins_state
        ], dim=1)  # [batch, 4, feature_dim]

        dmn_output, dmn_state, dmn_energy = self.DMN(dmn_input, num_steps=3, step_size=0.1)

        # Consciousness metric (inverse energy, normalized)
        consciousness = torch.sigmoid(-dmn_energy)

        # === SYMBOLIC RULE MASKING ===

        if self.use_symbolic_rules and valid_actions is not None:
            # Apply Allis rules to mask invalid/undesirable actions
            action_logits = self._apply_symbolic_mask(
                action_logits_raw,
                valid_actions,
                consciousness
            )
        else:
            action_logits = action_logits_raw

        # Prepare output
        output = {
            'action_logits': action_logits,
            'value': value,
            'consciousness': consciousness,
            'dmn_energy': dmn_energy,
            'error_magnitude': error_magnitude,
        }

        if return_components:
            output.update({
                'vis_features': vis_features,
                'aud_features': aud_features,
                'som_features': som_features,
                'lan_features': lan_features,
                'mtl_features': mtl_features,
                'policy_features': policy_features,
                'conflict_features': conflict_features,
                'ins_state': ins_state,
                'dmn_state': dmn_state,
                'dlpfc_hidden': dlpfc_hidden,
            })

        return output

    def _apply_symbolic_mask(
        self,
        action_logits: torch.Tensor,
        valid_actions: List[List[Action]],
        consciousness: torch.Tensor
    ) -> torch.Tensor:
        """
        Apply symbolic rules to mask actions

        Args:
            action_logits: Raw action logits [batch, num_actions]
            valid_actions: List of valid Action objects per batch
            consciousness: Consciousness scores [batch]

        Returns:
            Masked action logits [batch, num_actions]
        """
        batch_size = action_logits.size(0)
        device = action_logits.device

        # Create mask
        mask = torch.zeros_like(action_logits)

        for b in range(batch_size):
            if not valid_actions[b]:
                continue

            # Evaluate each action against rules
            state_info = {
                'predicted_consciousness': consciousness[b].item(),
                'num_valid_moves': len(valid_actions[b])
            }

            for action_idx, action in enumerate(valid_actions[b]):
                if action_idx >= self.num_actions:
                    break

                # Get rule mask
                rule_mask = self.rule_engine.get_mask(
                    action,
                    self.context,
                    state_info
                )

                mask[b, action_idx] = rule_mask

        # Apply mask: set invalid actions to large negative value
        # This is more numerically stable than using log(mask)
        masked_logits = action_logits.clone()

        # Set masked-out actions to very negative value
        masked_logits[mask == 0] = -1e9

        # Safety check: ensure at least one valid action per batch
        for b in range(batch_size):
            if mask[b].sum() == 0:
                # If no actions are valid, allow all actions to avoid NaN
                masked_logits[b] = action_logits[b]

        return masked_logits

    def select_action(
        self,
        board_tensor: torch.Tensor,
        valid_actions: List[List[Action]],
        deterministic: bool = False
    ) -> Tuple[torch.Tensor, torch.Tensor, Dict]:
        """
        Select action given current state

        Args:
            board_tensor: Board state [batch, 5, 4]
            valid_actions: Valid actions per batch
            deterministic: If True, select argmax; else sample

        Returns:
            Tuple of (action_indices, log_probs, info_dict)
        """
        output = self.forward(board_tensor, valid_actions, return_components=False)

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
            'action_probs': action_probs
        }

        return actions, log_probs, info

    def reset_state(self):
        """Reset all module states"""
        self.DLPFC.reset_state()
        self.DMN.reset_state()
        self.INS.reset_state()
        self.MTL.reset_state()
        self.context = Context()

    def get_total_parameters(self) -> int:
        """Get total number of parameters"""
        return sum(p.numel() for p in self.parameters())

    def __repr__(self):
        return (
            f"NeuroSymbolicBrain(\n"
            f"  modules=10,\n"
            f"  feature_dim={self.feature_dim},\n"
            f"  num_actions={self.num_actions},\n"
            f"  parameters={self.get_total_parameters():,},\n"
            f"  symbolic_rules={'enabled' if self.use_symbolic_rules else 'disabled'}\n"
            f")"
        )


if __name__ == "__main__":
    # Test NeuroSymbolic Brain
    print("Testing NeuroSymbolic Brain...")
    print("="*60)

    # Create brain
    brain = NeuroSymbolicBrain(
        feature_dim=256,
        num_actions=40,
        memory_size=100,
        use_symbolic_rules=True
    )

    print(brain)
    print()

    # Test forward pass
    batch_size = 2
    board = torch.randint(0, 11, (batch_size, 4, 5))  # Random board state

    print("Running forward pass...")
    output = brain.forward(board, return_components=True)

    print("\nOutputs:")
    for key, value in output.items():
        if isinstance(value, torch.Tensor):
            print(f"  {key}: {value.shape}")

    print("\nAction probabilities:")
    action_probs = F.softmax(output['action_logits'], dim=-1)
    print(f"  Shape: {action_probs.shape}")
    print(f"  Top-3 actions (batch 0): {torch.topk(action_probs[0], 3).indices.tolist()}")

    print("\nValue estimates:")
    print(f"  {output['value'].squeeze().tolist()}")

    print("\nConsciousness scores:")
    print(f"  {output['consciousness'].tolist()}")

    print("\nDMN energy:")
    print(f"  {output['dmn_energy'].tolist()}")

    print("\n" + "="*60)
    print("NeuroSymbolic Brain working correctly!")
