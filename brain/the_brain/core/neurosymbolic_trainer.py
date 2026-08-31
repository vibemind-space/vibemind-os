"""
NeuroSymbolic Trainer

Handles training pipeline for NeuroSymbolicBrain in evolutionary context:
- Generation 0: BFS imitation learning (pretrain heart)
- Generation 1+: PPO reinforcement learning (evolve brain)
- Bimodal perturbation for evolution (50% small, 50% large)

Training Pipeline:
1. BFS Pretraining (Heart):
   - Collect expert demonstrations via BFS
   - Supervised learning on state-action pairs
   - Save as frozen "heart" weights

2. PPO Evolution (Brain):
   - Start from random or previous generation
   - PPO updates from episode experiences
   - Bimodal weight perturbation between generations

3. Reproduction:
   - Copy heart to next generation (frozen)
   - Perturb brain weights (bimodal)
   - Increase puzzle difficulty

Usage:
    from core.neurosymbolic_trainer import NeuroSymbolicTrainer

    trainer = NeuroSymbolicTrainer(graph_file="Klotski-Webpage/data.json")

    # Generation 0: Pretrain heart with BFS
    trainer.pretrain_heart(num_demos=100, epochs=10)

    # Generation 1+: Evolve brain with PPO
    trainer.train_generation(generation=1, episodes=200)
"""

import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
from typing import Dict, List, Tuple, Optional, Any
from pathlib import Path
import logging
from collections import deque
import copy

from core.neurosymbolic_heart_brain import (
    NeuroSymbolicHeartSystem,
    NeuroSymbolicBrainSystem,
    DualSystemAgent
)

logger = logging.getLogger(__name__)


class NeuroSymbolicTrainer:
    """
    Trainer for NeuroSymbolic Heart/Brain evolutionary system.

    Manages complete training lifecycle:
    - BFS pretraining (heart)
    - PPO evolution (brain)
    - Bimodal perturbation
    - Multi-generational progression
    """

    def __init__(
        self,
        graph_file: Optional[str] = None,
        save_dir: str = "data/neurosymbolic_brains",
        device: str = 'cpu',
        learning_rate: float = 1e-4,
        small_perturbation_std: float = 0.01,
        large_perturbation_std: float = 0.20
    ):
        """
        Initialize NeuroSymbolic Trainer.

        Args:
            graph_file: Path to Klotski graph (Klotski-Webpage/data.json)
            save_dir: Directory for saving trained brains
            device: 'cpu' or 'cuda'
            learning_rate: Learning rate for optimization
            small_perturbation_std: Std for small bimodal perturbations (0.01)
            large_perturbation_std: Std for large bimodal perturbations (0.20)
        """
        self.graph_file = graph_file
        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.device = torch.device(device)
        self.learning_rate = learning_rate

        # Bimodal perturbation parameters (from paper)
        self.small_perturbation_std = small_perturbation_std
        self.large_perturbation_std = large_perturbation_std

        # Training statistics
        self.generation_stats = []
        self.current_generation = 0

        # Heart system (frozen pretrained)
        self.heart_path = None

        logger.info(f"[NeuroSymbolicTrainer] Initialized with device={device}")
        logger.info(f"[NeuroSymbolicTrainer] Save directory: {self.save_dir}")

    def pretrain_heart(
        self,
        num_demos: int = 100,
        epochs: int = 10,
        batch_size: int = 32,
        save: bool = True
    ) -> Dict:
        """
        Pretrain heart using BFS expert demonstrations (Generation 0).

        This creates the frozen "heart" that provides stable guidance
        throughout all future generations.

        Args:
            num_demos: Number of BFS demonstrations to collect
            epochs: Number of training epochs
            batch_size: Batch size for training
            save: Whether to save pretrained heart

        Returns:
            Dictionary with training statistics
        """
        logger.info(f"\n{'='*80}")
        logger.info(f"[NeuroSymbolicTrainer] Pretraining Heart (Generation 0)")
        logger.info(f"{'='*80}")
        logger.info(f"  Demonstrations: {num_demos}")
        logger.info(f"  Epochs: {epochs}")
        logger.info(f"  Batch size: {batch_size}")

        # Try to import KlotskiGraphEnv for BFS demonstrations
        try:
            from learning_engine.klotski.neurosymbolic.environments.klotski_graph_env import KlotskiGraphEnv
            env = KlotskiGraphEnv(graph_file=self.graph_file) if self.graph_file else None
            logger.info("[NeuroSymbolicTrainer] Real Klotski environment loaded")
        except ImportError:
            logger.warning("[NeuroSymbolicTrainer] Could not load KlotskiGraphEnv - using synthetic demos")
            env = None

        # Create brain for pretraining
        brain = NeuroSymbolicBrainSystem(device=str(self.device), learning_rate=self.learning_rate)

        # Collect BFS demonstrations
        logger.info(f"\n[NeuroSymbolicTrainer] Collecting {num_demos} BFS demonstrations...")
        demonstrations = self._collect_bfs_demonstrations(env, num_demos)
        logger.info(f"[NeuroSymbolicTrainer] Collected {len(demonstrations)} demonstrations")

        # Train with imitation learning
        logger.info(f"\n[NeuroSymbolicTrainer] Training heart with imitation learning...")
        train_losses = []

        for epoch in range(epochs):
            epoch_losses = []

            # Shuffle demonstrations
            np.random.shuffle(demonstrations)

            # Mini-batch training
            for i in range(0, len(demonstrations), batch_size):
                batch = demonstrations[i:i+batch_size]

                # Prepare batch tensors
                states = [demo['state'] for demo in batch]
                actions = torch.LongTensor([demo['action'] for demo in batch]).to(self.device)

                # Forward pass
                state_features = torch.cat([brain._state_to_features(s) for s in states])
                output = brain.brain(state_features, return_components=True)
                action_logits = output['action_logits']

                # Cross-entropy loss
                loss = nn.functional.cross_entropy(action_logits, actions)

                # Backward pass
                brain.optimizer.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(brain.brain.parameters(), max_norm=1.0)
                brain.optimizer.step()

                epoch_losses.append(loss.item())

            avg_loss = np.mean(epoch_losses)
            train_losses.append(avg_loss)

            if (epoch + 1) % 2 == 0 or epoch == 0:
                logger.info(f"  Epoch {epoch+1}/{epochs}: Loss = {avg_loss:.4f}")

        # Save pretrained heart
        if save:
            heart_path = self.save_dir / "heart_pretrained.pth"
            torch.save({
                'model_state_dict': brain.brain.state_dict(),
                'optimizer_state_dict': brain.optimizer.state_dict(),
                'num_demos': num_demos,
                'epochs': epochs,
                'final_loss': train_losses[-1]
            }, heart_path)
            self.heart_path = str(heart_path)
            logger.info(f"\n[NeuroSymbolicTrainer] Pretrained heart saved to: {heart_path}")

        stats = {
            'generation': 0,
            'num_demos': num_demos,
            'epochs': epochs,
            'train_losses': train_losses,
            'final_loss': train_losses[-1],
            'heart_path': str(heart_path) if save else None
        }

        self.generation_stats.append(stats)

        logger.info(f"\n{'='*80}")
        logger.info(f"[NeuroSymbolicTrainer] Heart Pretraining Complete!")
        logger.info(f"  Final Loss: {stats['final_loss']:.4f}")
        logger.info(f"{'='*80}\n")

        return stats

    def _collect_bfs_demonstrations(self, env: Optional[Any], num_demos: int) -> List[Dict]:
        """
        Collect expert demonstrations using BFS.

        Args:
            env: KlotskiGraphEnv or None (fallback to synthetic)
            num_demos: Number of demonstrations to collect

        Returns:
            List of demonstration dictionaries with 'state' and 'action'
        """
        demonstrations = []

        if env is not None:
            # Real BFS demonstrations from Klotski graph
            try:
                for i in range(num_demos):
                    # Reset environment
                    state = env.reset()

                    # Get BFS optimal path
                    path = env.get_optimal_path(state)

                    if path and len(path) > 0:
                        # Sample random state-action pair from path
                        idx = np.random.randint(0, len(path))
                        state_demo = path[idx]['state']
                        action_demo = path[idx]['action']

                        demonstrations.append({
                            'state': state_demo,
                            'action': action_demo
                        })

                logger.info(f"[BFS] Collected {len(demonstrations)} real demonstrations")

            except Exception as e:
                logger.warning(f"[BFS] Failed to collect real demonstrations: {e}")
                logger.warning("[BFS] Falling back to synthetic demonstrations")
                env = None  # Fall back to synthetic

        if env is None:
            # Fallback: Synthetic demonstrations
            for i in range(num_demos):
                # Generate random state hash
                state = f"synthetic_state_{np.random.randint(0, 100000)}"

                # Random action (uniform distribution)
                action = np.random.randint(0, 40)

                demonstrations.append({
                    'state': state,
                    'action': action
                })

            logger.info(f"[BFS] Generated {len(demonstrations)} synthetic demonstrations")

        return demonstrations

    def train_generation(
        self,
        generation: int,
        episodes: int = 200,
        max_steps: int = 150,
        ppo_epochs: int = 4,
        save: bool = True
    ) -> Dict:
        """
        Train one generation using PPO reinforcement learning.

        Args:
            generation: Generation number (1+)
            episodes: Number of training episodes
            max_steps: Maximum steps per episode
            ppo_epochs: Number of PPO update epochs
            save: Whether to save trained brain

        Returns:
            Dictionary with training statistics
        """
        logger.info(f"\n{'='*80}")
        logger.info(f"[NeuroSymbolicTrainer] Training Generation {generation}")
        logger.info(f"{'='*80}")
        logger.info(f"  Episodes: {episodes}")
        logger.info(f"  Max steps: {max_steps}")
        logger.info(f"  PPO epochs: {ppo_epochs}")

        # Load or create heart
        if self.heart_path and Path(self.heart_path).exists():
            heart = NeuroSymbolicHeartSystem(
                pretrained_path=self.heart_path,
                device=str(self.device)
            )
            logger.info(f"[NeuroSymbolicTrainer] Loaded pretrained heart from {self.heart_path}")
        else:
            logger.warning("[NeuroSymbolicTrainer] No pretrained heart found - using random heart")
            heart = NeuroSymbolicHeartSystem(device=str(self.device))

        # Create or load brain
        if generation == 1:
            # Generation 1: Start from random
            brain = NeuroSymbolicBrainSystem(
                device=str(self.device),
                learning_rate=self.learning_rate
            )
            logger.info("[NeuroSymbolicTrainer] Generation 1 - Random brain initialization")
        else:
            # Generation 2+: Load previous brain and perturb
            prev_brain_path = self.save_dir / f"brain_gen{generation-1}.pth"
            if prev_brain_path.exists():
                brain = self._load_and_perturb_brain(str(prev_brain_path))
                logger.info(f"[NeuroSymbolicTrainer] Loaded and perturbed brain from gen {generation-1}")
            else:
                logger.warning(f"[NeuroSymbolicTrainer] Previous brain not found - random initialization")
                brain = NeuroSymbolicBrainSystem(
                    device=str(self.device),
                    learning_rate=self.learning_rate
                )

        # Create dual system agent
        agent = DualSystemAgent(
            heart_system=heart,
            brain_system=brain,
            heart_weight=0.7,
            brain_weight=0.3
        )

        # Load environment (if available)
        try:
            from learning_engine.klotski.neurosymbolic.environments.klotski_graph_env import KlotskiGraphEnv
            env = KlotskiGraphEnv(graph_file=self.graph_file) if self.graph_file else None
        except ImportError:
            env = None

        # Training loop
        episode_rewards = []
        episode_lengths = []
        training_losses = []

        for episode in range(episodes):
            # Reset environment or use dummy state
            if env is not None:
                state = env.reset()
            else:
                state = f"episode_{episode}_state_0"

            episode_reward = 0
            episode_length = 0

            for step in range(max_steps):
                # Select action
                action, info = agent.select_action(state, sample=True)

                # Execute action
                if env is not None:
                    next_state, reward, done, _ = env.step(action)
                else:
                    # Dummy reward (synthetic)
                    next_state = f"episode_{episode}_state_{step+1}"
                    reward = np.random.randn() * 0.1 + 0.05  # Small positive bias
                    done = (step >= max_steps - 1)

                # Store experience
                agent.update_brain(
                    state=state,
                    action=action,
                    reward=reward,
                    next_state=next_state,
                    done=done,
                    action_logits=info['brain_action_logits']
                )

                episode_reward += reward
                episode_length += 1
                state = next_state

                if done:
                    break

            # PPO update after episode
            train_result = agent.train_brain(ppo_epochs=ppo_epochs)
            training_losses.append(train_result['loss'])

            episode_rewards.append(episode_reward)
            episode_lengths.append(episode_length)

            # Log progress
            if (episode + 1) % 20 == 0 or episode == 0:
                avg_reward = np.mean(episode_rewards[-20:])
                avg_length = np.mean(episode_lengths[-20:])
                avg_loss = np.mean(training_losses[-20:]) if training_losses else 0
                logger.info(f"  Episode {episode+1}/{episodes}: "
                          f"Reward={avg_reward:.3f}, Length={avg_length:.1f}, Loss={avg_loss:.4f}")

        # Save brain
        if save:
            brain_path = self.save_dir / f"brain_gen{generation}.pth"
            torch.save({
                'model_state_dict': brain.brain.state_dict(),
                'optimizer_state_dict': brain.optimizer.state_dict(),
                'generation': generation,
                'episodes': episodes,
                'avg_reward': np.mean(episode_rewards),
                'avg_length': np.mean(episode_lengths)
            }, brain_path)
            logger.info(f"\n[NeuroSymbolicTrainer] Brain gen {generation} saved to: {brain_path}")

        # Statistics
        stats = {
            'generation': generation,
            'episodes': episodes,
            'episode_rewards': episode_rewards,
            'episode_lengths': episode_lengths,
            'training_losses': training_losses,
            'avg_reward': np.mean(episode_rewards),
            'avg_length': np.mean(episode_lengths),
            'final_loss': training_losses[-1] if training_losses else 0.0,
            'brain_path': str(brain_path) if save else None
        }

        self.generation_stats.append(stats)
        self.current_generation = generation

        logger.info(f"\n{'='*80}")
        logger.info(f"[NeuroSymbolicTrainer] Generation {generation} Complete!")
        logger.info(f"  Avg Reward: {stats['avg_reward']:.3f}")
        logger.info(f"  Avg Length: {stats['avg_length']:.1f}")
        logger.info(f"{'='*80}\n")

        return stats

    def _load_and_perturb_brain(self, brain_path: str) -> NeuroSymbolicBrainSystem:
        """
        Load previous brain and apply bimodal perturbation.

        Bimodal perturbation (from paper):
        - 50% chance: Small perturbation N(0, 0.01)
        - 50% chance: Large perturbation N(0, 0.20)

        Args:
            brain_path: Path to previous brain checkpoint

        Returns:
            New NeuroSymbolicBrainSystem with perturbed weights
        """
        # Load previous brain
        brain = NeuroSymbolicBrainSystem(
            device=str(self.device),
            learning_rate=self.learning_rate
        )

        checkpoint = torch.load(brain_path, map_location=self.device, weights_only=False)
        brain.brain.load_state_dict(checkpoint['model_state_dict'])

        # Apply bimodal perturbation to all parameters
        perturbation_count = 0
        total_params = 0

        with torch.no_grad():
            for param in brain.brain.parameters():
                # 50% small, 50% large (bimodal)
                mask = torch.rand_like(param) < 0.5
                small_noise = torch.randn_like(param) * self.small_perturbation_std
                large_noise = torch.randn_like(param) * self.large_perturbation_std

                perturbation = torch.where(mask, small_noise, large_noise)
                param.add_(perturbation)

                perturbation_count += param.numel()
                total_params += param.numel()

        logger.info(f"[Perturbation] Applied bimodal perturbation to {perturbation_count}/{total_params} parameters")
        logger.info(f"[Perturbation] Small std={self.small_perturbation_std}, Large std={self.large_perturbation_std}")

        return brain

    def get_statistics(self) -> Dict:
        """Get complete training statistics."""
        return {
            'current_generation': self.current_generation,
            'total_generations': len(self.generation_stats),
            'generation_stats': self.generation_stats,
            'heart_path': self.heart_path,
            'save_dir': str(self.save_dir)
        }


if __name__ == "__main__":
    # Test trainer
    print("\n" + "=" * 80)
    print("Testing NeuroSymbolic Trainer")
    print("=" * 80)

    # Create trainer
    trainer = NeuroSymbolicTrainer(
        graph_file=None,  # No real graph for test
        save_dir="data/test_neurosymbolic_brains"
    )

    # Test BFS pretraining
    print("\n[Test] Pretraining heart with BFS demonstrations...")
    heart_stats = trainer.pretrain_heart(
        num_demos=50,
        epochs=5,
        batch_size=16
    )
    print(f"Heart pretrained! Final loss: {heart_stats['final_loss']:.4f}")

    # Test PPO training (Generation 1)
    print("\n[Test] Training Generation 1 with PPO...")
    gen1_stats = trainer.train_generation(
        generation=1,
        episodes=10,
        max_steps=20,
        ppo_epochs=2
    )
    print(f"Generation 1 complete! Avg reward: {gen1_stats['avg_reward']:.3f}")

    # Test PPO training (Generation 2 with perturbation)
    print("\n[Test] Training Generation 2 with bimodal perturbation...")
    gen2_stats = trainer.train_generation(
        generation=2,
        episodes=10,
        max_steps=20,
        ppo_epochs=2
    )
    print(f"Generation 2 complete! Avg reward: {gen2_stats['avg_reward']:.3f}")

    # Statistics
    stats = trainer.get_statistics()
    print("\n" + "=" * 80)
    print("Training Statistics:")
    print(f"  Total Generations: {stats['total_generations']}")
    print(f"  Current Generation: {stats['current_generation']}")
    print(f"  Heart Path: {stats['heart_path']}")
    print("=" * 80)
