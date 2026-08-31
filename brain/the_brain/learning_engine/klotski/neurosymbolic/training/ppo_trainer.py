"""
PPO Trainer for NeuroSymbolic Brain

Implements Proximal Policy Optimization with:
- Task loss: PPO policy + value loss
- Rule loss: Symbolic rule compliance
- Conflict loss: ACC error minimization
- Energy loss: DMN energy minimization

Total loss: L = L_task + λ₁·L_rules + λ₂·L_conflict + λ₃·L_energy
"""

import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
from typing import Dict, List, Tuple, Optional
import numpy as np
from dataclasses import dataclass

from neurosymbolic.core.neurosymbolic_brain import NeuroSymbolicBrain
from neurosymbolic.training.puzzle_env import PuzzleEnv
from neurosymbolic.symbolic.allis_rules import Action, Context
from neurosymbolic.utils.quantum_rng import get_quantum_rng
from neurosymbolic.memory.dual_graph_manager import DualGraphManager


@dataclass
class Transition:
    """Single transition in trajectory"""
    state: torch.Tensor
    action: int
    log_prob: float
    value: float
    reward: float
    done: bool
    consciousness: float
    dmn_energy: float
    error_magnitude: float
    valid_actions: List[Action]


class RolloutBuffer:
    """Buffer for storing trajectories"""

    def __init__(self):
        self.states = []
        self.actions = []
        self.log_probs = []
        self.values = []
        self.rewards = []
        self.dones = []
        self.consciousness = []
        self.dmn_energies = []
        self.error_magnitudes = []
        self.valid_actions = []

    def add(self, transition: Transition):
        """Add transition to buffer"""
        self.states.append(transition.state)
        self.actions.append(transition.action)
        self.log_probs.append(transition.log_prob)
        self.values.append(transition.value)
        self.rewards.append(transition.reward)
        self.dones.append(transition.done)
        self.consciousness.append(transition.consciousness)
        self.dmn_energies.append(transition.dmn_energy)
        self.error_magnitudes.append(transition.error_magnitude)
        self.valid_actions.append(transition.valid_actions)

    def get(self) -> Dict[str, torch.Tensor]:
        """Get all transitions as tensors"""
        return {
            'states': torch.cat(self.states, dim=0),
            'actions': torch.tensor(self.actions, dtype=torch.long),
            'old_log_probs': torch.tensor(self.log_probs, dtype=torch.float32),
            'values': torch.tensor(self.values, dtype=torch.float32),
            'rewards': torch.tensor(self.rewards, dtype=torch.float32),
            'dones': torch.tensor(self.dones, dtype=torch.float32),
            'consciousness': torch.tensor(self.consciousness, dtype=torch.float32),
            'dmn_energies': torch.tensor(self.dmn_energies, dtype=torch.float32),
            'error_magnitudes': torch.tensor(self.error_magnitudes, dtype=torch.float32),
            'valid_actions': self.valid_actions,  # Keep as list of lists
        }

    def clear(self):
        """Clear buffer"""
        self.__init__()

    def __len__(self):
        return len(self.states)


class PPOTrainer:
    """
    Proximal Policy Optimization Trainer

    Implements the complete NeuroSymbolic loss function
    """

    def __init__(
        self,
        brain: NeuroSymbolicBrain,
        env: PuzzleEnv,
        learning_rate: float = 3e-4,
        gamma: float = 0.99,
        gae_lambda: float = 0.95,
        clip_epsilon: float = 0.2,
        value_coef: float = 0.5,
        entropy_coef: float = 0.01,
        rule_coef: float = 0.3,      # λ₁
        conflict_coef: float = 0.2,  # λ₂
        energy_coef: float = 0.1,    # λ₃
        max_grad_norm: float = 0.5,
        ppo_epochs: int = 4,
        batch_size: int = 64,
        device: str = 'cpu',
        use_quantum: bool = False,    # Quantum randomness for exploration
        use_dual_graph: bool = False,  # Use dual-graph memory system
        dual_graph_manager: Optional[DualGraphManager] = None  # Custom manager
    ):
        """
        Initialize PPO trainer

        Args:
            brain: NeuroSymbolicBrain model
            env: PuzzleEnv environment
            learning_rate: Learning rate
            gamma: Discount factor
            gae_lambda: GAE lambda
            clip_epsilon: PPO clip parameter
            value_coef: Value loss coefficient
            entropy_coef: Entropy bonus coefficient
            rule_coef: Rule compliance coefficient (λ₁)
            conflict_coef: Conflict minimization coefficient (λ₂)
            energy_coef: Energy minimization coefficient (λ₃)
            max_grad_norm: Max gradient norm for clipping
            ppo_epochs: Number of PPO update epochs
            batch_size: Mini-batch size
            device: Device ('cpu' or 'cuda')
            use_quantum: Use quantum randomness for action exploration
            use_dual_graph: Enable dual-graph memory system
            dual_graph_manager: Optional custom DualGraphManager instance
        """
        self.brain = brain.to(device)
        self.env = env
        self.device = device

        # Hyperparameters
        self.gamma = gamma
        self.gae_lambda = gae_lambda
        self.clip_epsilon = clip_epsilon
        self.value_coef = value_coef
        self.entropy_coef = entropy_coef
        self.rule_coef = rule_coef
        self.conflict_coef = conflict_coef
        self.energy_coef = energy_coef
        self.max_grad_norm = max_grad_norm
        self.ppo_epochs = ppo_epochs
        self.batch_size = batch_size

        # Quantum randomness
        self.use_quantum = use_quantum
        if use_quantum:
            self.quantum_rng = get_quantum_rng(use_quantum=True)
        else:
            self.quantum_rng = None

        # Dual-graph memory
        self.use_dual_graph = use_dual_graph
        if use_dual_graph:
            self.dual_graph_manager = dual_graph_manager or DualGraphManager(
                save_dir="./memory",
                auto_mine_interval=10
            )
        else:
            self.dual_graph_manager = None

        # Optimizer
        self.optimizer = optim.Adam(self.brain.parameters(), lr=learning_rate)

        # Buffer
        self.buffer = RolloutBuffer()

        # Statistics
        self.total_steps = 0
        self.total_episodes = 0

    def compute_gae(
        self,
        rewards: torch.Tensor,
        values: torch.Tensor,
        dones: torch.Tensor,
        next_value: float = 0.0
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Compute Generalized Advantage Estimation

        Args:
            rewards: Rewards [T]
            values: Value estimates [T]
            dones: Done flags [T]
            next_value: Value of next state

        Returns:
            Tuple of (advantages [T], returns [T])
        """
        T = len(rewards)
        advantages = torch.zeros(T)
        returns = torch.zeros(T)

        gae = 0.0
        next_value_tensor = torch.tensor([next_value])

        for t in reversed(range(T)):
            if t == T - 1:
                next_val = next_value_tensor
            else:
                next_val = values[t + 1]

            delta = rewards[t] + self.gamma * next_val * (1 - dones[t]) - values[t]
            gae = delta + self.gamma * self.gae_lambda * (1 - dones[t]) * gae

            advantages[t] = gae
            returns[t] = advantages[t] + values[t]

        return advantages, returns

    def collect_rollout(self, num_steps: int, debug=False) -> Dict:
        """
        Collect rollout trajectory

        Args:
            num_steps: Number of steps to collect

        Returns:
            Dict with trajectory statistics
        """
        import sys
        # Set brain to eval mode for rollout (handles BatchNorm with batch_size=1)
        self.brain.eval()

        # Reset brain state (to handle batch size changes from training)
        self.brain.reset_state()

        episode_rewards = []
        episode_lengths = []
        episode_consciousness = []

        state, valid_actions = self.env.reset()
        state = state.to(self.device)

        episode_reward = 0.0
        episode_length = 0
        episode_consc = []

        for step in range(num_steps):
            self.total_steps += 1

            # Debug every 100 steps
            if step % 100 == 0:
                print(f"[DEBUG] Rollout step {step}/{num_steps}, episodes: {len(episode_rewards)}", flush=True)
                sys.stdout.flush()

            # Get action from brain
            with torch.no_grad():
                output = self.brain.forward(state, [valid_actions], return_components=False)

                action_logits = output['action_logits']
                value = output['value']
                consciousness = output['consciousness']
                dmn_energy = output['dmn_energy']
                error_magnitude = output['error_magnitude']

                # ACTION MASKING: Only allow valid actions
                # Create mask that sets invalid actions to large negative value
                num_valid = len(valid_actions)
                LARGE_NEGATIVE = -1e9  # Better than -inf for numerical stability
                action_mask = torch.full_like(action_logits, LARGE_NEGATIVE)
                action_mask[0, :num_valid] = 0.0  # Only first num_valid actions are valid

                # Apply mask before softmax
                masked_logits = action_logits + action_mask

                # Sample action (using quantum randomness if enabled)
                action_probs = F.softmax(masked_logits, dim=-1)
                dist = torch.distributions.Categorical(probs=action_probs)

                if self.use_quantum and self.quantum_rng is not None:
                    # Quantum random sampling (ONLY from valid actions)
                    probs_np = action_probs.squeeze().cpu().numpy()
                    try:
                        # FIX: Only pass valid action indices to quantum sampler
                        valid_probs = probs_np[:num_valid]
                        valid_probs = valid_probs / valid_probs.sum()  # Renormalize
                        action_idx = self.quantum_rng.get_random_choice(
                            list(range(num_valid)),  # Only 0 to num_valid-1
                            p=valid_probs
                        )
                        action = torch.tensor([action_idx], dtype=torch.long, device=self.device)
                    except Exception:
                        # Fallback to classical sampling if quantum fails
                        action = dist.sample()
                else:
                    # Classical pseudo-random sampling
                    action = dist.sample()

                log_prob = dist.log_prob(action)

            # Execute action in environment
            action_idx = action.item()
            next_state, reward, done, info = self.env.step(action_idx)
            next_state = next_state.to(self.device)

            # Record event to dual-graph if enabled
            if self.use_dual_graph and self.dual_graph_manager is not None:
                self.dual_graph_manager.record_event(
                    state=state.cpu().numpy().squeeze(),
                    action=action_idx,
                    next_state=next_state.cpu().numpy().squeeze(),
                    reward=reward,
                    done=done,
                    value=value.squeeze().item(),
                    policy_entropy=dist.entropy().item(),
                    consciousness=consciousness.squeeze().item(),
                    dmn_energy=dmn_energy.squeeze().item()
                )

            # Store transition
            transition = Transition(
                state=state,
                action=action_idx,
                log_prob=log_prob.item(),
                value=value.squeeze().item(),
                reward=reward,
                done=done,
                consciousness=consciousness.squeeze().item(),
                dmn_energy=dmn_energy.squeeze().item(),
                error_magnitude=error_magnitude.squeeze().item(),
                valid_actions=valid_actions
            )
            self.buffer.add(transition)

            # Update tracking
            episode_reward += reward
            episode_length += 1
            episode_consc.append(info['consciousness'])

            # Move to next state
            state = next_state
            valid_actions = self.env._get_valid_actions()

            # Episode done
            if done:
                self.total_episodes += 1
                episode_rewards.append(episode_reward)
                episode_lengths.append(episode_length)
                episode_consciousness.append(np.mean(episode_consc))

                # Reset
                state, valid_actions = self.env.reset()
                state = state.to(self.device)
                episode_reward = 0.0
                episode_length = 0
                episode_consc = []

        avg_reward = np.mean(episode_rewards) if episode_rewards else 0.0
        avg_length = np.mean(episode_lengths) if episode_lengths else 0.0
        avg_consciousness = np.mean(episode_consciousness) if episode_consciousness else 0.0

        return {
            'episode_rewards': episode_rewards,
            'episode_lengths': episode_lengths,
            'episode_consciousness': episode_consciousness,
            'avg_reward': avg_reward,
            'avg_length': avg_length,
            'avg_value': avg_consciousness,  # Use consciousness as proxy for value
        }

    def update(self) -> Dict[str, float]:
        """
        Update policy using PPO

        Returns:
            Dict with loss components
        """
        # Set brain to train mode
        self.brain.train()

        # Get buffer data
        data = self.buffer.get()

        # Compute advantages
        advantages, returns = self.compute_gae(
            data['rewards'],
            data['values'],
            data['dones'],
            next_value=0.0
        )

        # Normalize advantages
        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)

        # Convert to device
        states = data['states'].to(self.device)
        actions = data['actions'].to(self.device)
        old_log_probs = data['old_log_probs'].to(self.device)
        returns = returns.to(self.device)
        advantages = advantages.to(self.device)
        valid_actions_list = data['valid_actions']  # List of valid actions per state

        # PPO update for multiple epochs
        total_loss = 0.0
        total_policy_loss = 0.0
        total_value_loss = 0.0
        total_entropy_loss = 0.0
        total_rule_loss = 0.0
        total_conflict_loss = 0.0
        total_energy_loss = 0.0

        dataset_size = len(states)
        num_batches = max(1, dataset_size // self.batch_size)

        for epoch in range(self.ppo_epochs):
            # Shuffle data
            indices = torch.randperm(dataset_size)

            for i in range(num_batches):
                # Get mini-batch
                batch_indices = indices[i * self.batch_size:(i + 1) * self.batch_size]

                batch_states = states[batch_indices]
                batch_actions = actions[batch_indices]
                batch_old_log_probs = old_log_probs[batch_indices]
                batch_returns = returns[batch_indices]
                batch_advantages = advantages[batch_indices]
                batch_valid_actions = [valid_actions_list[i] for i in batch_indices.tolist()]

                # Forward pass (with valid_actions for masking)
                output = self.brain.forward(batch_states, batch_valid_actions, return_components=False)

                action_logits = output['action_logits']
                values = output['value'].squeeze()
                consciousness = output['consciousness']
                dmn_energy = output['dmn_energy']
                error_magnitude = output['error_magnitude'].squeeze()

                # === L_task: PPO loss ===

                # Policy loss (use log_softmax for numerical stability)
                # Check for NaN/Inf in logits
                if torch.isnan(action_logits).any() or torch.isinf(action_logits).any():
                    print(f"WARNING: NaN/Inf detected in action_logits!")
                    print(f"  NaN count: {torch.isnan(action_logits).sum().item()}")
                    print(f"  Inf count: {torch.isinf(action_logits).sum().item()}")
                    print(f"  Min: {action_logits.min().item():.2f}, Max: {action_logits.max().item():.2f}")
                    # Clip extreme values
                    action_logits = torch.clamp(action_logits, min=-10, max=10)

                # ACTION MASKING: Apply masks for each state in batch
                LARGE_NEGATIVE = -1e9  # Better than -inf for numerical stability
                masked_logits = action_logits.clone()
                for batch_idx, valid_acts in enumerate(batch_valid_actions):
                    num_valid = len(valid_acts)
                    # Set invalid actions to large negative value
                    masked_logits[batch_idx, num_valid:] = LARGE_NEGATIVE

                # Use log_softmax for better numerical stability
                log_probs_all = F.log_softmax(masked_logits, dim=-1)
                dist = torch.distributions.Categorical(logits=masked_logits)
                new_log_probs = dist.log_prob(batch_actions)

                ratio = torch.exp(new_log_probs - batch_old_log_probs)
                surr1 = ratio * batch_advantages
                surr2 = torch.clamp(ratio, 1 - self.clip_epsilon, 1 + self.clip_epsilon) * batch_advantages
                policy_loss = -torch.min(surr1, surr2).mean()

                # Value loss
                value_loss = F.mse_loss(values, batch_returns)

                # Entropy bonus
                entropy = dist.entropy().mean()
                entropy_loss = -entropy

                # Check for NaN/Inf in entropy (can happen with masked distributions)
                if torch.isnan(entropy) or torch.isinf(entropy):
                    print(f"WARNING: NaN/Inf detected in entropy!")
                    print(f"  Entropy: {entropy.item()}")
                    print(f"  Using fallback entropy = 0")
                    entropy_loss = torch.tensor(0.0, device=self.device)

                # === L_rules: Rule compliance ===
                # Penalize if consciousness doesn't improve
                # (Simplified - in full version would check each Allis rule)
                rule_loss = torch.clamp(0.5 - consciousness, min=0).mean()

                # === L_conflict: ACC error minimization ===
                conflict_loss = error_magnitude.mean()

                # === L_energy: DMN energy minimization ===
                # Want energy to converge to attractor (low magnitude)
                energy_loss = dmn_energy.abs().mean()

                # === Total loss ===
                loss = (
                    policy_loss +
                    self.value_coef * value_loss +
                    self.entropy_coef * entropy_loss +
                    self.rule_coef * rule_loss +
                    self.conflict_coef * conflict_loss +
                    self.energy_coef * energy_loss
                )

                # Optimization step
                self.optimizer.zero_grad()
                # Check for NaN in loss
                if torch.isnan(loss) or torch.isinf(loss):
                    print(f"[WARNING] NaN/Inf detected in loss! Skipping update.")
                    print(f"  policy_loss: {policy_loss.item():.4f}")
                    print(f"  value_loss: {value_loss.item():.4f}")
                    print(f"  entropy_loss: {entropy_loss.item():.4f}")
                    print(f"  rule_loss: {rule_loss.item():.4f}")
                    print(f"  conflict_loss: {conflict_loss.item():.4f}")
                    print(f"  energy_loss: {energy_loss.item():.4f}")
                    self.optimizer.zero_grad()
                    continue

                loss.backward()

                # Check for NaN in gradients before clipping
                has_nan_grad = False
                for name, param in self.brain.named_parameters():
                    if param.grad is not None and (torch.isnan(param.grad).any() or torch.isinf(param.grad).any()):
                        print(f"[WARNING] NaN/Inf gradient in {name}")
                        has_nan_grad = True
                        break

                if has_nan_grad:
                    print(f"[WARNING] Skipping optimizer step due to NaN gradients")
                    self.optimizer.zero_grad()
                    continue

                torch.nn.utils.clip_grad_norm_(self.brain.parameters(), self.max_grad_norm)
                self.optimizer.step()

                # Track losses
                total_loss += loss.item()
                total_policy_loss += policy_loss.item()
                total_value_loss += value_loss.item()
                total_entropy_loss += entropy_loss.item()
                total_rule_loss += rule_loss.item()
                total_conflict_loss += conflict_loss.item()
                total_energy_loss += energy_loss.item()

        # Average over batches and epochs
        num_updates = self.ppo_epochs * num_batches
        metrics = {
            'loss': total_loss / num_updates,
            'policy_loss': total_policy_loss / num_updates,
            'value_loss': total_value_loss / num_updates,
            'entropy_loss': total_entropy_loss / num_updates,
            'rule_loss': total_rule_loss / num_updates,
            'conflict_loss': total_conflict_loss / num_updates,
            'energy_loss': total_energy_loss / num_updates,
        }

        return metrics

    def train(self, total_timesteps: int, rollout_steps: int = 2048) -> List[Dict]:
        """
        Train the brain

        Args:
            total_timesteps: Total training timesteps
            rollout_steps: Steps per rollout

        Returns:
            List of training logs
        """
        import sys
        logs = []
        num_updates = total_timesteps // rollout_steps

        print(f"Training for {total_timesteps} timesteps ({num_updates} updates)", flush=True)
        print(f"Rollout steps: {rollout_steps}", flush=True)
        print(flush=True)
        sys.stdout.flush()

        for update in range(num_updates):
            print(f"[DEBUG] Starting update {update+1}/{num_updates}", flush=True)
            sys.stdout.flush()

            # Collect rollout
            try:
                print(f"[DEBUG] Collecting rollout...", flush=True)
                sys.stdout.flush()
                rollout_stats = self.collect_rollout(rollout_steps)
                print(f"[DEBUG] Rollout complete: {len(rollout_stats['episode_rewards'])} episodes", flush=True)
                sys.stdout.flush()
            except Exception as e:
                print(f"[ERROR] Rollout failed: {e}", flush=True)
                sys.stdout.flush()
                raise

            # Update policy
            try:
                print(f"[DEBUG] Updating policy...", flush=True)
                sys.stdout.flush()
                loss_metrics = self.update()
                print(f"[DEBUG] Policy update complete", flush=True)
                sys.stdout.flush()
            except Exception as e:
                print(f"[ERROR] Policy update failed: {e}", flush=True)
                sys.stdout.flush()
                raise

            # Log
            log_entry = {
                'update': update + 1,
                'total_steps': self.total_steps,
                'total_episodes': self.total_episodes,
                **rollout_stats,
                **loss_metrics
            }

            logs.append(log_entry)

            # Print progress
            if len(rollout_stats['episode_rewards']) > 0:
                mean_reward = np.mean(rollout_stats['episode_rewards'])
                mean_length = np.mean(rollout_stats['episode_lengths'])
                mean_consc = np.mean(rollout_stats['episode_consciousness'])

                print(f"Update {update+1}/{num_updates} | "
                      f"Episodes: {len(rollout_stats['episode_rewards'])} | "
                      f"Reward: {mean_reward:.2f} | "
                      f"Length: {mean_length:.1f} | "
                      f"Consciousness: {mean_consc:.3f} | "
                      f"Loss: {loss_metrics['loss']:.4f}", flush=True)
                sys.stdout.flush()

        print(f"[DEBUG] Training loop complete! Returning {len(logs)} log entries", flush=True)
        sys.stdout.flush()
        return logs

    def save_dual_graph_memory(self, name: str = "memory"):
        """Save dual-graph memory to disk"""
        if self.use_dual_graph and self.dual_graph_manager is not None:
            self.dual_graph_manager.save(name=name)
        else:
            print("Warning: Dual-graph memory not enabled")

    def load_dual_graph_memory(self, name: str = "memory"):
        """Load dual-graph memory from disk"""
        if self.use_dual_graph and self.dual_graph_manager is not None:
            return self.dual_graph_manager.load(name=name)
        else:
            print("Warning: Dual-graph memory not enabled")
            return False

    def get_memory_statistics(self) -> Dict:
        """Get dual-graph memory statistics"""
        if self.use_dual_graph and self.dual_graph_manager is not None:
            return self.dual_graph_manager.get_statistics()
        else:
            return {'error': 'Dual-graph memory not enabled'}

    def get_best_patterns(self, top_k: int = 10):
        """Get best learned patterns from memory"""
        if self.use_dual_graph and self.dual_graph_manager is not None:
            return self.dual_graph_manager.get_best_patterns(top_k=top_k)
        else:
            return []

    def force_pattern_mining(self):
        """Force immediate pattern mining"""
        if self.use_dual_graph and self.dual_graph_manager is not None:
            self.dual_graph_manager.force_mine()
        else:
            print("Warning: Dual-graph memory not enabled")

    def pretrain_from_demonstrations(
        self,
        demo_dir: str = "./demonstrations",
        num_epochs: int = 100,
        imitation_lr: float = 1e-4,
        batch_size: int = 32,
        val_split: float = 0.2,
        verbose: bool = True
    ) -> Dict[str, List[float]]:
        """
        Pretrain brain using imitation learning on human demonstrations

        This initializes the brain with expert knowledge before RL training.

        Args:
            demo_dir: Directory containing demonstration files
            num_epochs: Number of pretraining epochs
            imitation_lr: Learning rate for imitation learning
            batch_size: Batch size for imitation training
            val_split: Validation split fraction
            verbose: Print progress

        Returns:
            Training history dictionary
        """
        from neurosymbolic.training.imitation_trainer import ImitationTrainer
        from neurosymbolic.utils.demonstration_recorder import DemonstrationRecorder

        if verbose:
            print("="*60)
            print("PRETRAINING FROM HUMAN DEMONSTRATIONS")
            print("="*60)

        # Load demonstrations
        recorder = DemonstrationRecorder(save_dir=demo_dir)

        # Create imitation trainer (uses same brain, different optimizer)
        imitation_trainer = ImitationTrainer(
            brain=self.brain,
            recorder=recorder,
            learning_rate=imitation_lr,
            batch_size=batch_size,
            device=self.device
        )

        # Pretrain
        history = imitation_trainer.train(
            num_epochs=num_epochs,
            val_split=val_split,
            successful_only=True,
            verbose=verbose
        )

        if verbose:
            print("="*60)
            print("Pretraining complete! Brain initialized with expert policy.")
            print("Ready for reinforcement learning.")
            print("="*60)

        return history


if __name__ == "__main__":
    # Test trainer
    print("Testing PPO Trainer...")
    print("="*60)

    layout_path = r"C:\Users\User\Downloads\Klotski_NeuroLayout.json"

    # Create environment
    env = PuzzleEnv(layout_path, max_steps=50, reward_shaping=True)

    # Create brain
    brain = NeuroSymbolicBrain(
        feature_dim=128,  # Smaller for testing
        num_actions=40,
        memory_size=50,
        use_symbolic_rules=False  # Disable for faster testing
    )

    print(f"Brain: {brain.get_total_parameters():,} parameters")

    # Create trainer
    trainer = PPOTrainer(
        brain=brain,
        env=env,
        learning_rate=3e-4,
        batch_size=32,
        ppo_epochs=2,
        device='cpu'
    )

    print("Trainer created")

    # Train for short time
    print("\nTraining for 100 steps...")
    logs = trainer.train(total_timesteps=100, rollout_steps=50)

    print("\nTraining complete!")
    print(f"Total episodes: {trainer.total_episodes}")
    print(f"Total steps: {trainer.total_steps}")
