"""
Abstract Markov Chain for Phase 3

Models transitions between abstract states given actions.

P(s' | s, a) where s, s' ∈ {DMN_FAR, DMN_BLOCKED, DMN_CLEARING, DMN_NEAR, SOLVED}

This enables fast planning in abstract state space before concrete execution.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Tuple, Optional, List


class AbstractMarkovChain(nn.Module):
    """
    Markov transition model for abstract states

    Predicts next abstract state given current abstract state and action.
    """

    def __init__(
        self,
        n_states: int = 5,
        n_actions: int = 5,
        hidden_dim: int = 64,
        use_learned: bool = True
    ):
        """
        Args:
            n_states: Number of abstract states
            n_actions: Number of actions (UP, DOWN, LEFT, RIGHT, WAIT)
            hidden_dim: Hidden dimension for learned model
            use_learned: Whether to use learned transitions or heuristic rules
        """
        super().__init__()

        self.n_states = n_states
        self.n_actions = n_actions
        self.hidden_dim = hidden_dim
        self.use_learned = use_learned

        # Learned transition model
        self.transition_net = nn.Sequential(
            nn.Embedding(n_states, hidden_dim),  # Embed current state
        )

        self.action_embed = nn.Embedding(n_actions, hidden_dim)

        self.predict_net = nn.Sequential(
            nn.Linear(hidden_dim * 2, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_dim // 2, n_states)
        )

        # Heuristic transition rules (backup)
        self._init_heuristic_rules()

    def _init_heuristic_rules(self):
        """
        Initialize heuristic transition rules

        Rules based on intuitive puzzle dynamics:
        - DMN_FAR + move toward goal → DMN_NEAR (if not blocked)
        - DMN_BLOCKED + clear moves → DMN_CLEARING
        - DMN_CLEARING + continued clearing → DMN_NEAR
        - DMN_NEAR + move to goal → SOLVED
        - SOLVED is absorbing state
        """
        # Transition matrix (5 states x 5 actions x 5 next states)
        # actions: 0=UP, 1=DOWN, 2=LEFT, 3=RIGHT, 4=WAIT
        self.heuristic_transitions = torch.zeros(self.n_states, self.n_actions, self.n_states)

        # State indices
        DMN_FAR = 0
        DMN_BLOCKED = 1
        DMN_CLEARING = 2
        DMN_NEAR = 3
        SOLVED = 4

        # DMN_FAR transitions
        self.heuristic_transitions[DMN_FAR, 1, DMN_NEAR] = 0.4  # DOWN → NEAR (moving toward goal)
        self.heuristic_transitions[DMN_FAR, 1, DMN_BLOCKED] = 0.3  # DOWN → BLOCKED (hit obstacle)
        self.heuristic_transitions[DMN_FAR, 1, DMN_FAR] = 0.3  # DOWN → FAR (no progress)
        self.heuristic_transitions[DMN_FAR, 3, DMN_NEAR] = 0.3  # RIGHT → NEAR
        self.heuristic_transitions[DMN_FAR, 3, DMN_BLOCKED] = 0.4  # RIGHT → BLOCKED
        self.heuristic_transitions[DMN_FAR, 3, DMN_FAR] = 0.3  # RIGHT → FAR
        self.heuristic_transitions[DMN_FAR, 4, DMN_FAR] = 1.0  # WAIT → FAR
        self.heuristic_transitions[DMN_FAR, 0, DMN_FAR] = 0.9  # UP → FAR (wrong direction)
        self.heuristic_transitions[DMN_FAR, 0, DMN_BLOCKED] = 0.1  # UP → BLOCKED
        self.heuristic_transitions[DMN_FAR, 2, DMN_FAR] = 0.9  # LEFT → FAR (wrong direction)
        self.heuristic_transitions[DMN_FAR, 2, DMN_BLOCKED] = 0.1  # LEFT → BLOCKED

        # DMN_BLOCKED transitions
        self.heuristic_transitions[DMN_BLOCKED, 4, DMN_CLEARING] = 0.5  # WAIT → CLEARING (planning)
        self.heuristic_transitions[DMN_BLOCKED, 4, DMN_BLOCKED] = 0.5  # WAIT → BLOCKED
        self.heuristic_transitions[DMN_BLOCKED, 1, DMN_CLEARING] = 0.4  # DOWN → CLEARING (trying to clear)
        self.heuristic_transitions[DMN_BLOCKED, 1, DMN_BLOCKED] = 0.6  # DOWN → BLOCKED (still blocked)
        self.heuristic_transitions[DMN_BLOCKED, 3, DMN_CLEARING] = 0.4  # RIGHT → CLEARING
        self.heuristic_transitions[DMN_BLOCKED, 3, DMN_BLOCKED] = 0.6  # RIGHT → BLOCKED
        self.heuristic_transitions[DMN_BLOCKED, 0, DMN_FAR] = 0.3  # UP → FAR (retreating)
        self.heuristic_transitions[DMN_BLOCKED, 0, DMN_BLOCKED] = 0.7  # UP → BLOCKED
        self.heuristic_transitions[DMN_BLOCKED, 2, DMN_FAR] = 0.3  # LEFT → FAR (retreating)
        self.heuristic_transitions[DMN_BLOCKED, 2, DMN_BLOCKED] = 0.7  # LEFT → BLOCKED

        # DMN_CLEARING transitions
        self.heuristic_transitions[DMN_CLEARING, 4, DMN_NEAR] = 0.4  # WAIT → NEAR (cleared path)
        self.heuristic_transitions[DMN_CLEARING, 4, DMN_CLEARING] = 0.6  # WAIT → CLEARING
        self.heuristic_transitions[DMN_CLEARING, 1, DMN_NEAR] = 0.5  # DOWN → NEAR (progress)
        self.heuristic_transitions[DMN_CLEARING, 1, DMN_CLEARING] = 0.5  # DOWN → CLEARING
        self.heuristic_transitions[DMN_CLEARING, 3, DMN_NEAR] = 0.4  # RIGHT → NEAR
        self.heuristic_transitions[DMN_CLEARING, 3, DMN_CLEARING] = 0.6  # RIGHT → CLEARING
        self.heuristic_transitions[DMN_CLEARING, 0, DMN_BLOCKED] = 0.5  # UP → BLOCKED (wrong move)
        self.heuristic_transitions[DMN_CLEARING, 0, DMN_CLEARING] = 0.5  # UP → CLEARING
        self.heuristic_transitions[DMN_CLEARING, 2, DMN_BLOCKED] = 0.5  # LEFT → BLOCKED
        self.heuristic_transitions[DMN_CLEARING, 2, DMN_CLEARING] = 0.5  # LEFT → CLEARING

        # DMN_NEAR transitions
        self.heuristic_transitions[DMN_NEAR, 1, SOLVED] = 0.6  # DOWN → SOLVED (reaching goal)
        self.heuristic_transitions[DMN_NEAR, 1, DMN_NEAR] = 0.4  # DOWN → NEAR
        self.heuristic_transitions[DMN_NEAR, 3, SOLVED] = 0.5  # RIGHT → SOLVED
        self.heuristic_transitions[DMN_NEAR, 3, DMN_NEAR] = 0.5  # RIGHT → NEAR
        self.heuristic_transitions[DMN_NEAR, 2, SOLVED] = 0.5  # LEFT → SOLVED
        self.heuristic_transitions[DMN_NEAR, 2, DMN_NEAR] = 0.5  # LEFT → NEAR
        self.heuristic_transitions[DMN_NEAR, 4, DMN_NEAR] = 1.0  # WAIT → NEAR
        self.heuristic_transitions[DMN_NEAR, 0, DMN_NEAR] = 0.8  # UP → NEAR (wrong direction)
        self.heuristic_transitions[DMN_NEAR, 0, DMN_BLOCKED] = 0.2  # UP → BLOCKED

        # SOLVED transitions (absorbing state)
        for action in range(self.n_actions):
            self.heuristic_transitions[SOLVED, action, SOLVED] = 1.0

    def forward(
        self,
        current_state: torch.Tensor,
        action: torch.Tensor,
        use_learned: bool = None
    ) -> torch.Tensor:
        """
        Predict next abstract state distribution

        Args:
            current_state: Current abstract state indices (batch_size,)
            action: Action indices (batch_size,)
            use_learned: Override use_learned setting

        Returns:
            next_state_probs: Probability distribution over next states (batch_size, n_states)
        """
        if use_learned is None:
            use_learned = self.use_learned

        batch_size = current_state.shape[0]
        device = current_state.device

        if use_learned:
            # Learned transitions
            state_embed = self.transition_net[0](current_state)  # (batch_size, hidden_dim)
            action_embed = self.action_embed(action)  # (batch_size, hidden_dim)

            # Combine state and action
            combined = torch.cat([state_embed, action_embed], dim=1)  # (batch_size, 2*hidden_dim)

            # Predict next state logits
            logits = self.predict_net(combined)  # (batch_size, n_states)
            next_state_probs = F.softmax(logits, dim=1)
        else:
            # Heuristic transitions
            if not hasattr(self, 'heuristic_transitions'):
                self._init_heuristic_rules()

            next_state_probs = torch.zeros(batch_size, self.n_states, device=device)
            for i in range(batch_size):
                s = current_state[i].item()
                a = action[i].item()
                next_state_probs[i] = self.heuristic_transitions[s, a].to(device)

        return next_state_probs

    def compute_transition_loss(
        self,
        current_states: torch.Tensor,
        actions: torch.Tensor,
        next_states: torch.Tensor
    ) -> torch.Tensor:
        """
        Compute transition prediction loss

        Args:
            current_states: Current abstract states (batch_size,)
            actions: Actions taken (batch_size,)
            next_states: Actual next abstract states (batch_size,)

        Returns:
            loss: Cross-entropy loss
        """
        # Predict next state distribution
        next_state_probs = self.forward(current_states, actions, use_learned=True)

        # Cross-entropy loss
        loss = F.cross_entropy(next_state_probs, next_states)

        return loss

    def plan_abstract_trajectory(
        self,
        start_state: int,
        goal_state: int,
        max_steps: int = 10
    ) -> List[int]:
        """
        Plan abstract trajectory using greedy policy

        Args:
            start_state: Starting abstract state
            goal_state: Goal abstract state (typically SOLVED=4)
            max_steps: Maximum planning steps

        Returns:
            action_sequence: Sequence of actions to reach goal (approximately)
        """
        current = start_state
        trajectory = []

        for _ in range(max_steps):
            if current == goal_state:
                break

            # Try all actions, pick one that maximizes P(goal | current, action)
            best_action = None
            best_prob = 0.0

            current_tensor = torch.tensor([current], dtype=torch.long)

            for action in range(self.n_actions):
                action_tensor = torch.tensor([action], dtype=torch.long)
                next_probs = self.forward(current_tensor, action_tensor)

                # Probability of reaching goal (or getting closer)
                goal_prob = next_probs[0, goal_state].item()

                if goal_prob > best_prob:
                    best_prob = goal_prob
                    best_action = action

            if best_action is None:
                break

            trajectory.append(best_action)

            # Sample next state (for planning simulation)
            action_tensor = torch.tensor([best_action], dtype=torch.long)
            next_probs = self.forward(current_tensor, action_tensor)
            current = torch.argmax(next_probs).item()

        return trajectory

    def get_transition_accuracy(
        self,
        current_states: torch.Tensor,
        actions: torch.Tensor,
        next_states: torch.Tensor
    ) -> float:
        """
        Compute transition prediction accuracy

        Args:
            current_states: Current abstract states (batch_size,)
            actions: Actions taken (batch_size,)
            next_states: Actual next abstract states (batch_size,)

        Returns:
            accuracy: Fraction of correct predictions
        """
        next_state_probs = self.forward(current_states, actions, use_learned=True)
        predicted_states = torch.argmax(next_state_probs, dim=1)
        accuracy = (predicted_states == next_states).float().mean().item()
        return accuracy
