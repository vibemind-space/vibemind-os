"""
Cognitive Processing Modules

Implements the four cognitive/executive modules:
- DLPFC: Dorsolateral Prefrontal Cortex (Planning/Policy)
- OFC: Orbitofrontal Cortex (Value/Reward)
- ACC: Anterior Cingulate Cortex (Conflict Monitoring)
- INS: Insula (Interoception/Dynamics)
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Optional, Tuple

from neurosymbolic.modules.base_module import BrainModule


class DLPFCModule(BrainModule):
    """
    Dorsolateral Prefrontal Cortex Module (BA 9, 46)

    Implements planning and policy generation:
    - Working memory (GRU)
    - Action selection (Policy network)
    - Top-down control

    Architecture: GRU + MLP for policy π(a|s)
    """

    def __init__(
        self,
        input_dim: int = 256,
        hidden_dim: int = 256,
        output_dim: int = 256,
        num_actions: int = 10
    ):
        """
        Initialize DLPFC module

        Args:
            input_dim: Input dimension (state features)
            hidden_dim: Hidden/working memory dimension
            output_dim: Output feature dimension
            num_actions: Number of possible actions
        """
        super().__init__(
            module_id="DLPFC",
            module_name="Dorsolateral Prefrontal Cortex",
            input_dim=input_dim,
            output_dim=output_dim,
            brodmann_areas="9,46"
        )

        self.hidden_dim = hidden_dim
        self.num_actions = num_actions

        # Working memory (GRU)
        self.gru = nn.GRU(input_dim, hidden_dim, batch_first=True)

        # Policy network
        self.policy_net = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_dim, output_dim)
        )

        # Action head (for discrete action selection)
        self.action_head = nn.Linear(output_dim, num_actions)

    def forward(self, x: torch.Tensor, hidden: Optional[torch.Tensor] = None) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Generate policy and next hidden state

        Args:
            x: Input tensor [batch, input_dim] or [batch, seq_len, input_dim]
            hidden: Previous hidden state [1, batch, hidden_dim] or None

        Returns:
            Tuple of (policy_features [batch, output_dim], hidden_state)
        """
        # Add sequence dimension if needed
        if x.dim() == 2:
            x = x.unsqueeze(1)  # [batch, 1, input_dim]

        # GRU processing (working memory)
        if hidden is None:
            hidden = torch.zeros(1, x.size(0), self.hidden_dim, device=x.device)

        gru_out, hidden = self.gru(x, hidden)  # gru_out: [batch, seq_len, hidden_dim]

        # Take last timestep
        h = gru_out[:, -1, :]  # [batch, hidden_dim]

        # Policy features
        policy_features = self.policy_net(h)  # [batch, output_dim]

        # Store hidden state
        self._state = hidden

        return policy_features, hidden

    def get_action_logits(self, policy_features: torch.Tensor) -> torch.Tensor:
        """
        Get action logits from policy features

        Args:
            policy_features: Policy features [batch, output_dim]

        Returns:
            Action logits [batch, num_actions]
        """
        return self.action_head(policy_features)


class OFCModule(BrainModule):
    """
    Orbitofrontal Cortex Module (BA 10-12, 47)

    Implements value/reward estimation:
    - State value V(s)
    - Reward prediction
    - Outcome evaluation

    Architecture: MLP for value function with bounded output
    """

    def __init__(
        self,
        input_dim: int = 256,
        hidden_dim: int = 256,
        output_dim: int = 1  # Scalar value
    ):
        """
        Initialize OFC module

        Args:
            input_dim: Input dimension (state features)
            hidden_dim: Hidden dimension
            output_dim: Output dimension (1 for scalar value)
        """
        super().__init__(
            module_id="OFC",
            module_name="Orbitofrontal Cortex",
            input_dim=input_dim,
            output_dim=output_dim,
            brodmann_areas="10-12,47"
        )

        # Value network with bounded output
        self.value_net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_dim, output_dim),
            nn.Tanh()  # FIX: Bound output to [-1, +1]
        )

        # Value scaling factor (learnable parameter)
        # Starts at 100 to cover range [-100, +100]
        self.value_scale = nn.Parameter(torch.tensor(100.0))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Compute state value

        Args:
            x: Input tensor [batch, input_dim]

        Returns:
            Value estimate [batch, 1] in range [-value_scale, +value_scale]
        """
        value_normalized = self.value_net(x)  # [-1, +1]
        value = value_normalized * self.value_scale  # Scaled to appropriate range
        return value


class ACCModule(BrainModule):
    """
    Anterior Cingulate Cortex Module (BA 24, 32, 25)

    Implements conflict monitoring and error detection:
    - Prediction error |observed - predicted|²
    - Conflict detection (entropy)
    - Uncertainty monitoring

    Architecture: MLP for conflict/error computation
    """

    def __init__(
        self,
        input_dim: int = 256,
        hidden_dim: int = 256,
        output_dim: int = 256
    ):
        """
        Initialize ACC module

        Args:
            input_dim: Input dimension
            hidden_dim: Hidden dimension
            output_dim: Output dimension
        """
        super().__init__(
            module_id="ACC",
            module_name="Anterior Cingulate Cortex",
            input_dim=input_dim,
            output_dim=output_dim,
            brodmann_areas="24,32,25"
        )

        # Conflict detection network
        self.conflict_net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_dim, output_dim)
        )

        # Error magnitude prediction
        self.error_head = nn.Linear(output_dim, 1)

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Detect conflict and compute error

        Args:
            x: Input tensor [batch, input_dim]

        Returns:
            Tuple of (conflict_features [batch, output_dim], error_magnitude [batch, 1])
        """
        # Conflict features
        conflict_features = self.conflict_net(x)

        # Error magnitude (unsigned)
        error_magnitude = torch.abs(self.error_head(conflict_features))

        return conflict_features, error_magnitude

    def compute_conflict_from_distribution(self, probs: torch.Tensor) -> torch.Tensor:
        """
        Compute conflict as entropy of action distribution

        Args:
            probs: Action probabilities [batch, num_actions]

        Returns:
            Entropy (conflict) [batch]
        """
        # Avoid log(0)
        probs = torch.clamp(probs, min=1e-8)

        # Entropy = -sum(p * log(p))
        entropy = -(probs * torch.log(probs)).sum(dim=-1)

        return entropy


class INSModule(BrainModule):
    """
    Insula Module (BA 13, 43)

    Implements interoceptive processing and dynamics:
    - Internal state dynamics ẋ = f(x, u)
    - Bodily awareness
    - Affective processing

    Architecture: Dynamics network (ODE-like)
    """

    def __init__(
        self,
        input_dim: int = 256,
        hidden_dim: int = 256,
        output_dim: int = 256
    ):
        """
        Initialize INS module

        Args:
            input_dim: Input dimension
            hidden_dim: Hidden dimension
            output_dim: Output dimension (state space)
        """
        super().__init__(
            module_id="INS",
            module_name="Insula",
            input_dim=input_dim,
            output_dim=output_dim,
            brodmann_areas="13,43"
        )

        # Dynamics function f(x, u)
        self.dynamics = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.Tanh(),  # Non-linear dynamics
            nn.Linear(hidden_dim, hidden_dim),
            nn.Tanh(),
            nn.Linear(hidden_dim, output_dim)
        )

        # Initial state
        self.register_buffer('initial_state', torch.zeros(1, output_dim))

    def forward(self, x: torch.Tensor, dt: float = 0.1) -> torch.Tensor:
        """
        Update internal state using dynamics

        Args:
            x: Input (control/stimulation) [batch, input_dim]
            dt: Time step for integration

        Returns:
            Updated state [batch, output_dim]
        """
        batch_size = x.size(0)

        # Get or initialize state (match batch size)
        if self._state is None or self._state.size(0) != batch_size:
            self._state = self.initial_state.expand(batch_size, -1).clone()

        # Compute state derivative: ẋ = f(x)
        dx = self.dynamics(x)

        # Euler integration: x_{t+1} = x_t + dt * ẋ
        new_state = self._state + dt * dx

        # Store state without gradient (to avoid double backward)
        self._state = new_state.detach()

        return new_state


if __name__ == "__main__":
    # Test cognitive modules
    print("Testing Cognitive Modules...")
    print("="*60)

    batch_size = 4

    # Test DLPFC
    print("\n1. DLPFC Module (Planning/Policy)")
    dlpfc = DLPFCModule(input_dim=256, hidden_dim=256, output_dim=256, num_actions=10)
    print(f"   {dlpfc}")
    x_dlpfc = torch.randn(batch_size, 256)
    policy_features, hidden = dlpfc(x_dlpfc)
    action_logits = dlpfc.get_action_logits(policy_features)
    print(f"   Input: {x_dlpfc.shape}")
    print(f"   Policy features: {policy_features.shape}")
    print(f"   Action logits: {action_logits.shape}")
    print(f"   Hidden state: {hidden.shape}")
    print(f"   Parameters: {dlpfc.get_info()['num_parameters']:,}")

    # Test OFC
    print("\n2. OFC Module (Value/Reward)")
    ofc = OFCModule(input_dim=256, hidden_dim=256)
    print(f"   {ofc}")
    x_ofc = torch.randn(batch_size, 256)
    value = ofc(x_ofc)
    print(f"   Input: {x_ofc.shape} -> Value: {value.shape}")
    print(f"   Value estimates: {value.squeeze().tolist()}")
    print(f"   Parameters: {ofc.get_info()['num_parameters']:,}")

    # Test ACC
    print("\n3. ACC Module (Conflict Monitoring)")
    acc = ACCModule(input_dim=256, hidden_dim=256, output_dim=256)
    print(f"   {acc}")
    x_acc = torch.randn(batch_size, 256)
    conflict_features, error_mag = acc(x_acc)
    print(f"   Input: {x_acc.shape}")
    print(f"   Conflict features: {conflict_features.shape}")
    print(f"   Error magnitude: {error_mag.shape}")
    print(f"   Error values: {error_mag.squeeze().tolist()}")
    print(f"   Parameters: {acc.get_info()['num_parameters']:,}")

    # Test INS
    print("\n4. INS Module (Interoception)")
    ins = INSModule(input_dim=256, hidden_dim=256, output_dim=256)
    print(f"   {ins}")
    x_ins = torch.randn(batch_size, 256)
    state = ins(x_ins, dt=0.1)
    print(f"   Input: {x_ins.shape} -> State: {state.shape}")
    print(f"   Parameters: {ins.get_info()['num_parameters']:,}")

    print("\n" + "="*60)
    print("All cognitive modules working correctly!")

    total_params = sum([
        dlpfc.get_info()['num_parameters'],
        ofc.get_info()['num_parameters'],
        acc.get_info()['num_parameters'],
        ins.get_info()['num_parameters']
    ])
    print(f"Total parameters in cognitive modules: {total_params:,}")
