"""
Imitation Learning (Behavioral Cloning) Trainer

Trains the NeuroSymbolic brain to imitate human demonstrations.
Uses supervised learning to match expert actions.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
from typing import List, Tuple, Dict, Optional
import numpy as np
from pathlib import Path

from ..core.neurosymbolic_brain import NeuroSymbolicBrain
from ..utils.demonstration_recorder import DemonstrationRecorder, Demonstration


class DemonstrationDataset(Dataset):
    """PyTorch dataset for demonstrations"""

    def __init__(self, states: torch.Tensor, actions: torch.Tensor):
        """
        Args:
            states: (N, 4, 5) tensor of board states
            actions: (N,) tensor of action indices
        """
        self.states = states
        self.actions = actions

    def __len__(self) -> int:
        return len(self.states)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        return self.states[idx], self.actions[idx]


class ImitationTrainer:
    """Behavioral cloning trainer for imitation learning"""

    def __init__(
        self,
        brain: NeuroSymbolicBrain,
        recorder: DemonstrationRecorder,
        learning_rate: float = 1e-4,
        batch_size: int = 32,
        device: str = 'cpu'
    ):
        """
        Args:
            brain: NeuroSymbolic brain to train
            recorder: Demonstration recorder with expert data
            learning_rate: Learning rate for optimizer
            batch_size: Batch size for training
            device: Device to train on ('cpu' or 'cuda')
        """
        self.brain = brain
        self.recorder = recorder
        self.batch_size = batch_size
        self.device = device

        # Move brain to device
        self.brain.to(device)

        # Optimizer for imitation learning
        self.optimizer = torch.optim.Adam(
            self.brain.parameters(),
            lr=learning_rate
        )

        # Loss function (cross-entropy for action classification)
        self.criterion = nn.CrossEntropyLoss()

        # Training statistics
        self.train_losses: List[float] = []
        self.val_accuracies: List[float] = []

    def train(
        self,
        num_epochs: int = 100,
        val_split: float = 0.2,
        successful_only: bool = True,
        verbose: bool = True
    ) -> Dict[str, List[float]]:
        """
        Train brain on demonstration data

        Args:
            num_epochs: Number of training epochs
            val_split: Fraction of data for validation
            successful_only: Only use successful demonstrations
            verbose: Print progress

        Returns:
            Dictionary with training history
        """
        # Get demonstration dataset
        states, actions = self.recorder.get_dataset(successful_only=successful_only)

        if len(states) == 0:
            raise ValueError("No demonstrations available for training!")

        if verbose:
            print(f"Training on {len(states)} state-action pairs")
            stats = self.recorder.get_statistics()
            print(f"  Demonstrations: {stats['total_demos']} total, {stats['successful_demos']} successful")
            print(f"  Success rate: {stats['success_rate']:.1%}")

        # Split into train/val
        num_samples = len(states)
        num_val = int(num_samples * val_split)
        num_train = num_samples - num_val

        indices = torch.randperm(num_samples)
        train_indices = indices[:num_train]
        val_indices = indices[num_train:]

        train_states = states[train_indices]
        train_actions = actions[train_indices]
        val_states = states[val_indices] if num_val > 0 else None
        val_actions = actions[val_indices] if num_val > 0 else None

        # Create datasets and dataloaders
        train_dataset = DemonstrationDataset(train_states, train_actions)
        train_loader = DataLoader(
            train_dataset,
            batch_size=self.batch_size,
            shuffle=True,
            drop_last=False
        )

        # Training loop
        for epoch in range(num_epochs):
            self.brain.train()
            epoch_loss = 0.0
            num_batches = 0

            for batch_states, batch_actions in train_loader:
                batch_states = batch_states.to(self.device)
                batch_actions = batch_actions.to(self.device)

                # Forward pass
                output = self.brain(batch_states, return_components=False)
                action_logits = output['action_logits']

                # Compute loss
                loss = self.criterion(action_logits, batch_actions)

                # Backward pass
                self.optimizer.zero_grad()
                loss.backward()
                self.optimizer.step()

                epoch_loss += loss.item()
                num_batches += 1

            avg_loss = epoch_loss / num_batches
            self.train_losses.append(avg_loss)

            # Validation
            val_acc = 0.0
            if val_states is not None:
                val_acc = self._evaluate(val_states, val_actions)
                self.val_accuracies.append(val_acc)

            # Print progress
            if verbose and (epoch + 1) % 10 == 0:
                if val_states is not None:
                    print(f"Epoch {epoch + 1}/{num_epochs} - Loss: {avg_loss:.4f}, Val Acc: {val_acc:.2%}")
                else:
                    print(f"Epoch {epoch + 1}/{num_epochs} - Loss: {avg_loss:.4f}")

        if verbose:
            print(f"\nTraining complete!")
            print(f"  Final loss: {self.train_losses[-1]:.4f}")
            if self.val_accuracies:
                print(f"  Final val accuracy: {self.val_accuracies[-1]:.2%}")

        return {
            'train_losses': self.train_losses,
            'val_accuracies': self.val_accuracies
        }

    def _evaluate(self, states: torch.Tensor, actions: torch.Tensor) -> float:
        """Evaluate accuracy on validation set"""
        self.brain.eval()
        self.brain.reset_state()  # Reset for new batch size

        with torch.no_grad():
            states = states.to(self.device)
            actions = actions.to(self.device)

            output = self.brain(states, return_components=False)
            action_logits = output['action_logits']
            predicted_actions = torch.argmax(action_logits, dim=-1)

            accuracy = (predicted_actions == actions).float().mean().item()

        self.brain.train()  # Set back to train mode
        self.brain.reset_state()  # Reset for training batch size
        return accuracy

    def evaluate_on_demonstrations(self, successful_only: bool = True) -> Dict[str, float]:
        """
        Evaluate brain on all demonstrations

        Returns:
            Dictionary with evaluation metrics
        """
        states, actions = self.recorder.get_dataset(successful_only=successful_only)

        if len(states) == 0:
            return {'accuracy': 0.0, 'num_samples': 0}

        accuracy = self._evaluate(states, actions)

        return {
            'accuracy': accuracy,
            'num_samples': len(states)
        }

    def pretrain(
        self,
        num_epochs: int = 100,
        val_split: float = 0.2,
        verbose: bool = True
    ) -> Dict[str, List[float]]:
        """
        Pretrain brain on demonstrations before RL training

        This is a convenience method that trains only on successful demonstrations
        and prepares the brain for subsequent reinforcement learning.

        Args:
            num_epochs: Number of pretraining epochs
            val_split: Validation split fraction
            verbose: Print progress

        Returns:
            Training history
        """
        if verbose:
            print("="*60)
            print("PRETRAINING BRAIN ON HUMAN DEMONSTRATIONS")
            print("="*60)

        history = self.train(
            num_epochs=num_epochs,
            val_split=val_split,
            successful_only=True,
            verbose=verbose
        )

        if verbose:
            print("="*60)
            print("Pretraining complete - brain initialized with expert knowledge!")
            print("="*60)

        return history

    def save_checkpoint(self, filepath: str):
        """Save training checkpoint"""
        checkpoint = {
            'brain_state_dict': self.brain.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
            'train_losses': self.train_losses,
            'val_accuracies': self.val_accuracies
        }
        torch.save(checkpoint, filepath)
        print(f"Checkpoint saved to {filepath}")

    def load_checkpoint(self, filepath: str):
        """Load training checkpoint"""
        checkpoint = torch.load(filepath, map_location=self.device, weights_only=False)
        self.brain.load_state_dict(checkpoint['brain_state_dict'])
        self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
        self.train_losses = checkpoint.get('train_losses', [])
        self.val_accuracies = checkpoint.get('val_accuracies', [])
        print(f"Checkpoint loaded from {filepath}")


def train_from_demonstrations(
    brain: NeuroSymbolicBrain,
    demo_dir: str = "./demonstrations",
    num_epochs: int = 100,
    learning_rate: float = 1e-4,
    batch_size: int = 32,
    device: str = 'cpu'
) -> Tuple[NeuroSymbolicBrain, Dict[str, List[float]]]:
    """
    Convenience function to train brain from demonstrations

    Args:
        brain: Brain to train
        demo_dir: Directory containing demonstrations
        num_epochs: Number of training epochs
        learning_rate: Learning rate
        batch_size: Batch size
        device: Training device

    Returns:
        Trained brain and training history
    """
    # Load demonstrations
    recorder = DemonstrationRecorder(save_dir=demo_dir)

    # Create trainer
    trainer = ImitationTrainer(
        brain=brain,
        recorder=recorder,
        learning_rate=learning_rate,
        batch_size=batch_size,
        device=device
    )

    # Train
    history = trainer.pretrain(num_epochs=num_epochs, verbose=True)

    return brain, history


if __name__ == '__main__':
    # Test imitation learning
    import sys
    sys.path.insert(0, '.')

    from neurosymbolic.brain.neurosymbolic_brain import NeuroSymbolicBrain
    from neurosymbolic.utils.demonstration_recorder import DemonstrationRecorder

    # Create test demonstrations
    print("Creating test demonstrations...")
    recorder = DemonstrationRecorder(save_dir="./test_imitation_demos")
    recorder.clear_all()

    # Simulate 3 expert demonstrations
    for demo_idx in range(3):
        recorder.start_recording(demo_id=f"expert_demo_{demo_idx}")

        for step in range(20):
            state = np.random.randint(0, 10, size=(4, 5))
            action = np.random.randint(0, 20)
            reward = 1.0 if step == 19 else 0.0
            recorder.record_step(state, action, reward)

        recorder.stop_recording(success=True)

    print(f"\nCreated {len(recorder.demonstrations)} demonstrations")

    # Create brain
    print("\nCreating NeuroSymbolic brain...")
    brain = NeuroSymbolicBrain(
        num_actions=20,
        feature_dim=64,
        device='cpu'
    )

    # Train
    print("\nTraining brain on demonstrations...")
    trainer = ImitationTrainer(
        brain=brain,
        recorder=recorder,
        learning_rate=1e-4,
        batch_size=16,
        device='cpu'
    )

    history = trainer.pretrain(num_epochs=50, verbose=True)

    # Evaluate
    print("\nEvaluating on demonstrations...")
    eval_results = trainer.evaluate_on_demonstrations()
    print(f"Final accuracy: {eval_results['accuracy']:.2%}")

    print("\n[OK] Imitation learning test passed!")
