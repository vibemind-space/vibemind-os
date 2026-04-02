"""
Hierarchical Policy for Phase 3

Integrates:
1. Abstract Markov Planner (high-level strategy)
2. CTM Executor (detailed reasoning)
3. Trajectory Predictor (concrete actions)

Architecture:
    State → Abstract Classifier → Markov Planner → CTM → Trajectory → Actions
"""

import torch
import torch.nn as nn
from typing import Tuple, Dict, Optional

from neurosymbolic.modules.abstract_state_classifier import AbstractStateClassifier
from neurosymbolic.modules.abstract_markov_chain import AbstractMarkovChain


class HierarchicalPolicy(nn.Module):
    """
    Hierarchical policy combining abstract planning with concrete execution

    Three-level hierarchy:
    1. Abstract Level: Markov chain over abstract states (fast planning)
    2. Middle Level: CTM thinking with memory (detailed reasoning)
    3. Concrete Level: Trajectory prediction (action sequences)
    """

    def __init__(
        self,
        abstract_classifier: AbstractStateClassifier,
        abstract_markov: AbstractMarkovChain,
        ctm_layer,
        trajectory_predictor,
        use_abstract_guidance: bool = True,
        guidance_weight: float = 0.3
    ):
        """
        Args:
            abstract_classifier: Maps states to abstract states
            abstract_markov: Markov chain for abstract transitions
            ctm_layer: CTM for detailed reasoning
            trajectory_predictor: Predicts action sequences
            use_abstract_guidance: Whether to use abstract plan to guide CTM
            guidance_weight: Weight for abstract guidance signal
        """
        super().__init__()

        self.abstract_classifier = abstract_classifier
        self.abstract_markov = abstract_markov
        self.ctm = ctm_layer
        self.trajectory_predictor = trajectory_predictor

        self.use_abstract_guidance = use_abstract_guidance
        self.guidance_weight = guidance_weight

        # Learned mapping from abstract plan to CTM guidance signal
        if use_abstract_guidance:
            self.guidance_net = nn.Sequential(
                nn.Linear(5, 64),  # 5 abstract states
                nn.ReLU(),
                nn.Linear(64, 256)  # CTM hidden dim
            )

    def forward(
        self,
        state: torch.Tensor,
        brain_features: torch.Tensor,
        return_all: bool = False
    ) -> Dict[str, torch.Tensor]:
        """
        Forward pass through hierarchical policy

        Args:
            state: Puzzle state (batch_size, 5, 4)
            brain_features: Features from brain (batch_size, feature_dim)
            return_all: Whether to return all intermediate outputs

        Returns:
            Dictionary with:
                - action_logits: Action predictions (batch_size, action_dim)
                - abstract_state: Predicted abstract state (batch_size,)
                - abstract_guidance: Guidance signal from abstract planner (batch_size, 256)
                - ctm_synch: CTM synchronization (batch_size, n_synch)
                - trajectory: Full trajectory prediction (batch_size, max_len, action_dim)
                (if return_all=True, also includes intermediate outputs)
        """
        batch_size = state.shape[0]
        device = state.device

        # Level 1: Abstract state classification
        abstract_logits, abstract_state, metadata = self.abstract_classifier(
            state,
            use_learned=True
        )

        # Level 2: Abstract guidance signal
        abstract_guidance = None
        if self.use_abstract_guidance:
            # Convert abstract state to one-hot
            abstract_onehot = torch.zeros(batch_size, 5, device=device)
            abstract_onehot.scatter_(1, abstract_state.unsqueeze(1), 1.0)

            # Generate guidance signal
            abstract_guidance = self.guidance_net(abstract_onehot)  # (batch_size, 256)

            # Add guidance to brain features
            guided_features = brain_features + self.guidance_weight * abstract_guidance
        else:
            guided_features = brain_features

        # Level 3: CTM execution
        ctm_result = self.ctm(guided_features, return_all_ticks=False)

        # Handle CTM output (tuple: synch, certainty, ticks_used)
        if isinstance(ctm_result, tuple):
            synch, certainty, ticks_used = ctm_result
        else:
            synch = ctm_result['synch']
            certainty = ctm_result.get('certainty', None)
            ticks_used = ctm_result.get('ticks_used', None)

        # Level 4: Trajectory prediction
        trajectory, _ = self.trajectory_predictor(synch)  # (batch_size, max_len, action_dim)

        # Extract action logits (first step of trajectory)
        action_logits = trajectory[:, 0, :]  # (batch_size, action_dim)

        # Prepare output
        output = {
            'action_logits': action_logits,
            'abstract_state': abstract_state,
            'abstract_logits': abstract_logits,
            'ctm_synch': synch,
            'trajectory': trajectory
        }

        if return_all:
            output.update({
                'abstract_guidance': abstract_guidance,
                'ctm_certainty': certainty,
                'ctm_ticks_used': ticks_used,
                'metadata': metadata
            })

        return output

    def compute_hierarchical_loss(
        self,
        state: torch.Tensor,
        brain_features: torch.Tensor,
        actions_true: torch.Tensor,
        abstract_states_true: torch.Tensor,
        abstract_next_states: Optional[torch.Tensor] = None
    ) -> Dict[str, torch.Tensor]:
        """
        Compute hierarchical loss with supervision at all levels

        Args:
            state: Puzzle states (batch_size, 5, 4)
            brain_features: Brain features (batch_size, feature_dim)
            actions_true: True actions (batch_size,)
            abstract_states_true: True abstract states (batch_size,)
            abstract_next_states: True next abstract states (batch_size,) [optional]

        Returns:
            Dictionary with losses:
                - total_loss: Combined loss
                - action_loss: Action prediction loss
                - abstract_loss: Abstract state classification loss
                - transition_loss: Abstract transition loss (if next states provided)
        """
        # Forward pass
        output = self.forward(state, brain_features, return_all=True)

        action_logits = output['action_logits']
        abstract_logits = output['abstract_logits']
        abstract_state_pred = output['abstract_state']

        # Loss 1: Action prediction
        action_loss = nn.functional.cross_entropy(action_logits, actions_true)

        # Loss 2: Abstract state classification
        abstract_loss = nn.functional.cross_entropy(abstract_logits, abstract_states_true)

        # Loss 3: Abstract transition (if next states provided)
        transition_loss = torch.tensor(0.0, device=state.device)
        if abstract_next_states is not None:
            # Predict next abstract state given current + action
            next_state_probs = self.abstract_markov(
                abstract_states_true,
                actions_true,
                use_learned=True
            )
            transition_loss = nn.functional.cross_entropy(next_state_probs, abstract_next_states)

        # Combined loss (weighted)
        total_loss = (
            1.0 * action_loss +
            0.3 * abstract_loss +
            0.2 * transition_loss
        )

        return {
            'total_loss': total_loss,
            'action_loss': action_loss,
            'abstract_loss': abstract_loss,
            'transition_loss': transition_loss
        }

    def plan_with_abstraction(
        self,
        state: torch.Tensor,
        goal_abstract_state: int = 4,  # SOLVED
        max_abstract_steps: int = 10
    ) -> Dict[str, any]:
        """
        Plan trajectory using abstract reasoning

        Args:
            state: Current state (1, 5, 4)
            goal_abstract_state: Goal abstract state (default: SOLVED=4)
            max_abstract_steps: Max steps in abstract space

        Returns:
            Planning results with abstract trajectory
        """
        # Classify current abstract state
        _, current_abstract, _ = self.abstract_classifier(state, use_learned=True)
        current_abstract = current_abstract.item()

        # Plan in abstract space
        abstract_trajectory = self.abstract_markov.plan_abstract_trajectory(
            start_state=current_abstract,
            goal_state=goal_abstract_state,
            max_steps=max_abstract_steps
        )

        # Get abstract state name
        current_name = self.abstract_classifier.get_state_name(current_abstract)
        goal_name = self.abstract_classifier.get_state_name(goal_abstract_state)

        return {
            'current_abstract': current_abstract,
            'current_name': current_name,
            'goal_abstract': goal_abstract_state,
            'goal_name': goal_name,
            'abstract_plan': abstract_trajectory,
            'plan_length': len(abstract_trajectory)
        }

    def get_hierarchical_metrics(
        self,
        state: torch.Tensor,
        brain_features: torch.Tensor,
        actions_true: torch.Tensor,
        abstract_states_true: torch.Tensor
    ) -> Dict[str, float]:
        """
        Get hierarchical prediction metrics

        Args:
            state: Puzzle states (batch_size, 5, 4)
            brain_features: Brain features (batch_size, feature_dim)
            actions_true: True actions (batch_size,)
            abstract_states_true: True abstract states (batch_size,)

        Returns:
            Metrics dictionary
        """
        with torch.no_grad():
            output = self.forward(state, brain_features, return_all=False)

            # Action accuracy
            action_pred = torch.argmax(output['action_logits'], dim=1)
            action_accuracy = (action_pred == actions_true).float().mean().item()

            # Abstract state accuracy
            abstract_accuracy = (output['abstract_state'] == abstract_states_true).float().mean().item()

        return {
            'action_accuracy': action_accuracy,
            'abstract_accuracy': abstract_accuracy
        }
