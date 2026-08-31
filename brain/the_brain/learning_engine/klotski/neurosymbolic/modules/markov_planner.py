"""
Markov Decision Process Planner with Value Iteration

Learns abstract state transitions from demonstrations and computes
optimal policy using Value Iteration.
"""

import torch
import torch.nn as nn
import numpy as np
from typing import Dict, Tuple, List, Optional
from collections import defaultdict


class MarkovPlanner:
    """
    MDP Planner that learns P(s'|s,a) and computes optimal policy
    using Value Iteration

    Abstract States (5):
    0: Early - Far from goal
    1: Mid - Making progress
    2: Late - Close to goal
    3: Near - Very close
    4: Goal - Solved

    Actions (5):
    0: UP, 1: DOWN, 2: LEFT, 3: RIGHT, 4: WAIT
    """

    def __init__(
        self,
        n_states: int = 5,
        n_actions: int = 5,
        gamma: float = 0.95,
        convergence_threshold: float = 0.001
    ):
        """
        Args:
            n_states: Number of abstract states
            n_actions: Number of actions
            gamma: Discount factor for value iteration
            convergence_threshold: Convergence threshold for value iteration
        """
        self.n_states = n_states
        self.n_actions = n_actions
        self.gamma = gamma
        self.convergence_threshold = convergence_threshold

        # Transition counts: [state, action, next_state]
        self.transition_counts = np.zeros((n_states, n_actions, n_states))

        # Transition probabilities: P(s' | s, a)
        self.transition_probs = np.zeros((n_states, n_actions, n_states))

        # Reward function: R(s, a)
        self.rewards = np.zeros((n_states, n_actions))
        self._initialize_rewards()

        # Value function and policy (computed by value iteration)
        self.V = np.zeros(n_states)
        self.policy = np.zeros(n_states, dtype=np.int64)

        # Training stats
        self.total_transitions = 0
        self.is_trained = False

    def _initialize_rewards(self):
        """Initialize reward function based on abstract states"""
        # Goal state gets highest reward
        self.rewards[4, :] = 10.0  # Goal state
        self.rewards[3, :] = 5.0   # Near goal
        self.rewards[2, :] = 2.0   # Late game
        self.rewards[1, :] = 0.5   # Mid game
        self.rewards[0, :] = 0.0   # Early game

        # Penalize WAIT action
        self.rewards[:, 4] = -1.0

    def add_trajectory(
        self,
        abstract_states: List[int],
        actions: List[int]
    ):
        """
        Add a demonstration trajectory to learn transitions

        Args:
            abstract_states: List of abstract state labels (including final state)
            actions: List of actions taken (length = len(abstract_states) - 1)
        """
        assert len(actions) == len(abstract_states) - 1, \
            "Actions should be one less than states"

        for i in range(len(actions)):
            s = abstract_states[i]
            a = actions[i]
            s_next = abstract_states[i + 1]

            # Increment transition count
            self.transition_counts[s, a, s_next] += 1
            self.total_transitions += 1

    def compute_transition_probabilities(self):
        """
        Compute P(s' | s, a) from transition counts
        Uses Laplace smoothing to handle unseen transitions
        """
        # Laplace smoothing: add small count to all transitions
        smoothed_counts = self.transition_counts + 0.01

        # Normalize each (s, a) pair
        for s in range(self.n_states):
            for a in range(self.n_actions):
                count_sum = smoothed_counts[s, a, :].sum()
                if count_sum > 0:
                    self.transition_probs[s, a, :] = smoothed_counts[s, a, :] / count_sum

        print(f"\n[Markov Planner] Learned transition probabilities from {self.total_transitions} transitions")

    def value_iteration(self, max_iterations: int = 1000) -> Tuple[np.ndarray, np.ndarray]:
        """
        Run value iteration to compute optimal value function and policy

        V*(s) = max_a [R(s,a) + γ * Σ P(s'|s,a) * V*(s')]
        π*(s) = argmax_a [R(s,a) + γ * Σ P(s'|s,a) * V*(s')]

        Returns:
            V: Optimal value function [n_states]
            policy: Optimal policy [n_states]
        """
        V = np.zeros(self.n_states)
        policy = np.zeros(self.n_states, dtype=np.int64)

        print(f"\n[Value Iteration] Starting with gamma={self.gamma}")

        for iteration in range(max_iterations):
            V_old = V.copy()

            for s in range(self.n_states):
                # Compute Q(s, a) for all actions
                Q = np.zeros(self.n_actions)

                for a in range(self.n_actions):
                    # Q(s, a) = R(s, a) + γ * Σ P(s'|s,a) * V(s')
                    immediate_reward = self.rewards[s, a]
                    expected_future = 0.0

                    for s_next in range(self.n_states):
                        expected_future += self.transition_probs[s, a, s_next] * V_old[s_next]

                    Q[a] = immediate_reward + self.gamma * expected_future

                # Bellman update
                V[s] = np.max(Q)
                policy[s] = np.argmax(Q)

            # Check convergence
            delta = np.max(np.abs(V - V_old))

            if (iteration + 1) % 100 == 0:
                print(f"  Iteration {iteration + 1:4d} | Delta: {delta:.6f}")

            if delta < self.convergence_threshold:
                print(f"[Value Iteration] Converged after {iteration + 1} iterations (delta={delta:.6f})")
                break

        self.V = V
        self.policy = policy
        self.is_trained = True

        return V, policy

    def get_action(self, abstract_state: int) -> int:
        """
        Get optimal action for abstract state using computed policy

        Args:
            abstract_state: Abstract state index [0-4]

        Returns:
            action: Optimal action index [0-4]
        """
        assert self.is_trained, "Must run value_iteration() before getting actions"
        return int(self.policy[abstract_state])

    def get_value(self, abstract_state: int) -> float:
        """Get value of abstract state"""
        return float(self.V[abstract_state])

    def print_policy(self):
        """Print learned policy in human-readable format"""
        action_names = ['UP', 'DOWN', 'LEFT', 'RIGHT', 'WAIT']
        state_names = ['Early', 'Mid', 'Late', 'Near', 'Goal']

        print("\n" + "="*60)
        print("OPTIMAL POLICY (from Value Iteration)")
        print("="*60)

        for s in range(self.n_states):
            state_name = state_names[s]
            action = self.policy[s]
            action_name = action_names[action]
            value = self.V[s]

            print(f"{state_name:8s} -> {action_name:6s} (V={value:.3f})")

        print("="*60)

    def get_transition_stats(self) -> Dict:
        """Get statistics about learned transitions"""
        stats = {
            'total_transitions': self.total_transitions,
            'states_visited': set(),
            'most_common_transitions': []
        }

        # Find most common transitions
        for s in range(self.n_states):
            for a in range(self.n_actions):
                if self.transition_counts[s, a, :].sum() > 0:
                    stats['states_visited'].add(s)

                    for s_next in range(self.n_states):
                        count = self.transition_counts[s, a, s_next]
                        prob = self.transition_probs[s, a, s_next]

                        if count > 0:
                            stats['most_common_transitions'].append({
                                'from': s,
                                'action': a,
                                'to': s_next,
                                'count': int(count),
                                'prob': float(prob)
                            })

        # Sort by count
        stats['most_common_transitions'].sort(key=lambda x: x['count'], reverse=True)
        stats['states_visited'] = len(stats['states_visited'])

        return stats


if __name__ == '__main__':
    # Test Markov Planner
    print("Testing Markov Planner...")

    planner = MarkovPlanner(n_states=5, n_actions=5, gamma=0.95)

    # Simulate some trajectories
    # Trajectory 1: Early → Mid → Late → Near → Goal
    abstract_states_1 = [0, 1, 2, 3, 4]
    actions_1 = [1, 1, 1, 1]  # DOWN, DOWN, DOWN, DOWN

    # Trajectory 2: Early → Mid → Late → Near → Goal (different path)
    abstract_states_2 = [0, 1, 2, 3, 4]
    actions_2 = [3, 3, 1, 1]  # RIGHT, RIGHT, DOWN, DOWN

    # Trajectory 3: Early → Mid → Late → Near → Goal
    abstract_states_3 = [0, 0, 1, 2, 3, 4]
    actions_3 = [2, 1, 3, 1, 1]  # LEFT, DOWN, RIGHT, DOWN, DOWN

    print("\nAdding trajectories...")
    planner.add_trajectory(abstract_states_1, actions_1)
    planner.add_trajectory(abstract_states_2, actions_2)
    planner.add_trajectory(abstract_states_3, actions_3)

    print("\nComputing transition probabilities...")
    planner.compute_transition_probabilities()

    print("\nTransition statistics:")
    stats = planner.get_transition_stats()
    print(f"  Total transitions: {stats['total_transitions']}")
    print(f"  States visited: {stats['states_visited']}")
    print(f"\nTop 5 transitions:")
    for trans in stats['most_common_transitions'][:5]:
        print(f"    State {trans['from']} --[action {trans['action']}]--> State {trans['to']}: "
              f"count={trans['count']}, prob={trans['prob']:.3f}")

    print("\nRunning value iteration...")
    V, policy = planner.value_iteration(max_iterations=1000)

    planner.print_policy()

    print("\nTesting policy inference...")
    for s in range(5):
        action = planner.get_action(s)
        value = planner.get_value(s)
        print(f"  State {s}: action={action}, value={value:.3f}")

    print("\n[OK] Markov Planner test complete!")
