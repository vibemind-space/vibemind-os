"""
Monte Carlo Tree Search (MCTS) Planner - AGI Phase 4

Enables long-horizon planning (50+ steps) using tree search
with learned value/policy networks (AlphaZero-style).

Key Features:
- UCB1 selection with PUCT
- Neural network policy/value guidance
- Transposition tables
- Progressive widening
- Parallel search
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass, field
from collections import defaultdict
import numpy as np
import math
import logging
from concurrent.futures import ThreadPoolExecutor
import threading

logger = logging.getLogger(__name__)


@dataclass
class MCTSConfig:
    """Configuration for MCTS planner."""
    num_simulations: int = 100
    c_puct: float = 1.41  # Exploration constant
    dirichlet_alpha: float = 0.3
    dirichlet_epsilon: float = 0.25
    temperature: float = 1.0
    max_depth: int = 50
    discount: float = 0.99
    use_transposition: bool = True
    progressive_widening: bool = True
    pw_alpha: float = 0.5
    pw_beta: float = 0.5
    num_threads: int = 1


@dataclass
class MCTSStats:
    """Statistics for MCTS search."""
    total_simulations: int = 0
    avg_depth: float = 0.0
    max_depth_reached: int = 0
    tree_size: int = 0
    cache_hits: int = 0


class MCTSNode:
    """Node in the MCTS tree."""

    def __init__(
        self,
        state: Any,
        parent: Optional['MCTSNode'] = None,
        parent_action: Optional[int] = None,
        prior: float = 1.0
    ):
        self.state = state
        self.parent = parent
        self.parent_action = parent_action
        self.prior = prior

        # Statistics
        self.visit_count = 0
        self.value_sum = 0.0
        self.children: Dict[int, 'MCTSNode'] = {}

        # Virtual loss for parallel search
        self.virtual_loss = 0
        self.lock = threading.Lock()

    @property
    def value(self) -> float:
        """Average value of this node."""
        if self.visit_count == 0:
            return 0.0
        return self.value_sum / self.visit_count

    @property
    def is_expanded(self) -> bool:
        """Check if node has been expanded."""
        return len(self.children) > 0

    def ucb_score(self, parent_visits: int, c_puct: float) -> float:
        """
        UCB1 score with PUCT modification.

        UCB = Q(s,a) + c_puct * P(s,a) * sqrt(N(s)) / (1 + N(s,a))
        """
        exploration = c_puct * self.prior * math.sqrt(parent_visits) / (1 + self.visit_count + self.virtual_loss)
        return self.value + exploration

    def select_child(self, c_puct: float) -> Tuple[int, 'MCTSNode']:
        """Select child with highest UCB score."""
        best_score = -float('inf')
        best_action = None
        best_child = None

        for action, child in self.children.items():
            score = child.ucb_score(self.visit_count, c_puct)
            if score > best_score:
                best_score = score
                best_action = action
                best_child = child

        return best_action, best_child

    def expand(
        self,
        action_priors: Dict[int, float],
        state_fn: Callable[[Any, int], Any]
    ):
        """Expand node with given action priors."""
        for action, prior in action_priors.items():
            if action not in self.children:
                next_state = state_fn(self.state, action)
                self.children[action] = MCTSNode(
                    state=next_state,
                    parent=self,
                    parent_action=action,
                    prior=prior
                )

    def backup(self, value: float, discount: float = 0.99):
        """Backpropagate value up the tree."""
        node = self
        while node is not None:
            with node.lock:
                node.visit_count += 1
                node.value_sum += value
                node.virtual_loss = max(0, node.virtual_loss - 1)
            value = discount * value
            node = node.parent


class PolicyValueNetwork(nn.Module):
    """
    Neural network for guiding MCTS search.

    Provides policy (action probabilities) and value (state evaluation).
    """

    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        hidden_dim: int = 256,
        num_layers: int = 3
    ):
        super().__init__()
        self.state_dim = state_dim
        self.action_dim = action_dim

        # Shared trunk
        layers = [nn.Linear(state_dim, hidden_dim), nn.ReLU()]
        for _ in range(num_layers - 1):
            layers.extend([nn.Linear(hidden_dim, hidden_dim), nn.ReLU()])
        self.trunk = nn.Sequential(*layers)

        # Policy head
        self.policy_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, action_dim)
        )

        # Value head
        self.value_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),
            nn.Tanh()
        )

    def forward(self, state: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """Return policy logits and value."""
        features = self.trunk(state)
        policy_logits = self.policy_head(features)
        value = self.value_head(features)
        return policy_logits, value.squeeze(-1)

    def get_policy_value(
        self,
        state: np.ndarray,
        valid_actions: Optional[List[int]] = None
    ) -> Tuple[Dict[int, float], float]:
        """Get action probabilities and value for a state."""
        # Ensure state is 1D before adding batch dimension
        state_flat = np.asarray(state).flatten()
        state_t = torch.FloatTensor(state_flat).unsqueeze(0)

        with torch.no_grad():
            policy_logits, value = self.forward(state_t)
            policy_logits = policy_logits[0]
            value = value.item()

            # Mask invalid actions
            if valid_actions is not None:
                mask = torch.ones_like(policy_logits) * float('-inf')
                for a in valid_actions:
                    mask[a] = 0
                policy_logits = policy_logits + mask

            # Softmax to get probabilities
            probs = F.softmax(policy_logits, dim=-1)

        action_probs = {i: probs[i].item() for i in range(self.action_dim)}
        if valid_actions is not None:
            action_probs = {a: action_probs[a] for a in valid_actions}

        return action_probs, value


class MCTSPlanner:
    """
    Monte Carlo Tree Search Planner for long-horizon planning.

    Uses a neural network to guide search (AlphaZero-style).
    """

    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        config: Optional[MCTSConfig] = None,
        policy_value_net: Optional[PolicyValueNetwork] = None,
        device: str = "cpu"
    ):
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.config = config or MCTSConfig()
        self.device = torch.device(device)

        # Policy-value network
        if policy_value_net is None:
            self.pv_net = PolicyValueNetwork(state_dim, action_dim).to(self.device)
        else:
            self.pv_net = policy_value_net.to(self.device)

        # Transposition table
        self.transposition_table: Dict[str, MCTSNode] = {}

        # Statistics
        self.stats = MCTSStats()

        # Thread pool for parallel search
        if self.config.num_threads > 1:
            self.executor = ThreadPoolExecutor(max_workers=self.config.num_threads)

    def _state_to_key(self, state: Any) -> str:
        """Convert state to hashable key for transposition table."""
        if isinstance(state, np.ndarray):
            return state.tobytes()
        return str(state)

    def _get_or_create_node(self, state: Any, parent: Optional[MCTSNode] = None) -> MCTSNode:
        """Get node from transposition table or create new one."""
        if self.config.use_transposition:
            key = self._state_to_key(state)
            if key in self.transposition_table:
                self.stats.cache_hits += 1
                return self.transposition_table[key]
            node = MCTSNode(state, parent)
            self.transposition_table[key] = node
            return node
        return MCTSNode(state, parent)

    def plan(
        self,
        root_state: np.ndarray,
        world_model: 'WorldModel',
        valid_actions_fn: Optional[Callable[[Any], List[int]]] = None,
        horizon: int = 50
    ) -> Tuple[int, Dict[str, Any]]:
        """
        Plan using MCTS from the given state.

        Args:
            root_state: Current state observation
            world_model: Model for simulating state transitions
            valid_actions_fn: Function returning valid actions for a state
            horizon: Maximum planning horizon

        Returns:
            best_action: Best action to take
            info: Search statistics and information
        """
        # Create root node
        root = self._get_or_create_node(root_state)

        # Add Dirichlet noise to root for exploration
        if not root.is_expanded:
            priors, _ = self.pv_net.get_policy_value(root_state)
            if self.config.dirichlet_epsilon > 0:
                noise = np.random.dirichlet([self.config.dirichlet_alpha] * len(priors))
                priors = {
                    a: (1 - self.config.dirichlet_epsilon) * p + self.config.dirichlet_epsilon * noise[i]
                    for i, (a, p) in enumerate(priors.items())
                }
            root.expand(priors, lambda s, a: world_model.step(s, a)[0])

        # Run simulations
        depths = []
        for _ in range(self.config.num_simulations):
            depth = self._simulate(root, world_model, valid_actions_fn, horizon)
            depths.append(depth)
            self.stats.total_simulations += 1

        # Update statistics
        self.stats.avg_depth = np.mean(depths)
        self.stats.max_depth_reached = max(depths)
        self.stats.tree_size = len(self.transposition_table)

        # Select action based on visit counts
        if self.config.temperature == 0:
            # Deterministic: select most visited
            best_action = max(root.children.items(), key=lambda x: x[1].visit_count)[0]
        else:
            # Stochastic: sample proportional to visit counts
            visits = np.array([child.visit_count for child in root.children.values()])
            actions = list(root.children.keys())

            if self.config.temperature != 1.0:
                visits = visits ** (1.0 / self.config.temperature)
            probs = visits / visits.sum()
            best_action = np.random.choice(actions, p=probs)

        # Collect info
        info = {
            "root_value": root.value,
            "action_visits": {a: c.visit_count for a, c in root.children.items()},
            "action_values": {a: c.value for a, c in root.children.items()},
            "stats": self.stats
        }

        return best_action, info

    def _simulate(
        self,
        root: MCTSNode,
        world_model: 'WorldModel',
        valid_actions_fn: Optional[Callable],
        max_depth: int
    ) -> int:
        """Run single MCTS simulation."""
        node = root
        depth = 0
        path = [node]

        # Selection: traverse tree to leaf
        while node.is_expanded and depth < max_depth:
            with node.lock:
                node.virtual_loss += 1
            action, node = node.select_child(self.config.c_puct)
            path.append(node)
            depth += 1

        # Check terminal
        is_terminal, reward = world_model.is_terminal(node.state)

        if is_terminal:
            value = reward
        else:
            # Expansion and evaluation
            valid_actions = valid_actions_fn(node.state) if valid_actions_fn else list(range(self.action_dim))

            if self.config.progressive_widening:
                # Limit expansion based on visit count
                max_children = int(self.config.pw_alpha * (node.visit_count ** self.config.pw_beta)) + 1
                valid_actions = valid_actions[:max_children]

            priors, value = self.pv_net.get_policy_value(
                node.state if isinstance(node.state, np.ndarray) else np.array(node.state),
                valid_actions
            )
            node.expand(priors, lambda s, a: world_model.step(s, a)[0])

        # Backup
        node.backup(value, self.config.discount)

        return depth

    def update_network(
        self,
        states: torch.Tensor,
        target_policies: torch.Tensor,
        target_values: torch.Tensor,
        optimizer: torch.optim.Optimizer
    ) -> Dict[str, float]:
        """Update policy-value network from search results."""
        states = states.to(self.device)
        target_policies = target_policies.to(self.device)
        target_values = target_values.to(self.device)

        policy_logits, values = self.pv_net(states)

        # Policy loss (cross-entropy)
        policy_loss = F.cross_entropy(policy_logits, target_policies)

        # Value loss (MSE)
        value_loss = F.mse_loss(values, target_values)

        # Total loss
        loss = policy_loss + value_loss

        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        return {
            "policy_loss": policy_loss.item(),
            "value_loss": value_loss.item(),
            "total_loss": loss.item()
        }

    def clear_cache(self):
        """Clear transposition table."""
        self.transposition_table.clear()


class WorldModel:
    """
    Abstract world model for MCTS planning.

    Provides state transition and terminal detection.
    """

    def __init__(self, state_dim: int, action_dim: int):
        self.state_dim = state_dim
        self.action_dim = action_dim

    def step(self, state: np.ndarray, action: int) -> Tuple[np.ndarray, float, bool]:
        """
        Simulate one step in the world.

        Args:
            state: Current state
            action: Action to take

        Returns:
            next_state: Resulting state
            reward: Immediate reward
            done: Whether episode is finished
        """
        raise NotImplementedError

    def is_terminal(self, state: np.ndarray) -> Tuple[bool, float]:
        """Check if state is terminal and return final reward."""
        raise NotImplementedError


class LearnedWorldModel(WorldModel):
    """
    Neural network-based world model.

    Learns state transitions from experience.
    """

    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        hidden_dim: int = 256,
        device: str = "cpu"
    ):
        super().__init__(state_dim, action_dim)
        self.device = torch.device(device)

        # Dynamics model
        self.dynamics = nn.Sequential(
            nn.Linear(state_dim + action_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, state_dim + 1)  # next_state + reward
        ).to(self.device)

        # Terminal predictor
        self.terminal_predictor = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),
            nn.Sigmoid()
        ).to(self.device)

        self.optimizer = torch.optim.Adam(
            list(self.dynamics.parameters()) + list(self.terminal_predictor.parameters()),
            lr=1e-4
        )

    def step(self, state: np.ndarray, action: int) -> Tuple[np.ndarray, float, bool]:
        """Predict next state using learned model."""
        state_t = torch.FloatTensor(state).unsqueeze(0).to(self.device)
        action_t = F.one_hot(torch.tensor([action]), self.action_dim).float().to(self.device)

        with torch.no_grad():
            x = torch.cat([state_t, action_t], dim=-1)
            output = self.dynamics(x)
            next_state = output[0, :-1].cpu().numpy()
            reward = output[0, -1].item()

            terminal_prob = self.terminal_predictor(torch.FloatTensor(next_state).unsqueeze(0).to(self.device))
            done = terminal_prob.item() > 0.5

        return next_state, reward, done

    def is_terminal(self, state: np.ndarray) -> Tuple[bool, float]:
        """Check terminal state."""
        state_t = torch.FloatTensor(state).unsqueeze(0).to(self.device)
        with torch.no_grad():
            terminal_prob = self.terminal_predictor(state_t)
            is_term = terminal_prob.item() > 0.5
            # Estimate terminal reward (could be learned separately)
            reward = 1.0 if is_term else 0.0
        return is_term, reward

    def update(
        self,
        states: torch.Tensor,
        actions: torch.Tensor,
        rewards: torch.Tensor,
        next_states: torch.Tensor,
        dones: torch.Tensor
    ) -> Dict[str, float]:
        """Update world model from experience."""
        states = states.to(self.device)
        actions = F.one_hot(actions, self.action_dim).float().to(self.device)
        rewards = rewards.to(self.device)
        next_states = next_states.to(self.device)
        dones = dones.float().to(self.device)

        # Dynamics loss
        x = torch.cat([states, actions], dim=-1)
        output = self.dynamics(x)
        pred_next_states = output[:, :-1]
        pred_rewards = output[:, -1]

        dynamics_loss = F.mse_loss(pred_next_states, next_states) + F.mse_loss(pred_rewards, rewards)

        # Terminal loss
        terminal_probs = self.terminal_predictor(next_states).squeeze(-1)
        terminal_loss = F.binary_cross_entropy(terminal_probs, dones)

        # Total loss
        loss = dynamics_loss + terminal_loss

        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()

        return {
            "dynamics_loss": dynamics_loss.item(),
            "terminal_loss": terminal_loss.item()
        }
