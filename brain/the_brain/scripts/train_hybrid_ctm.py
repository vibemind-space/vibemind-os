"""
Train HybridCTM - Training script for the Hybrid Neurosymbolic CTM

This script trains the HybridCTM that combines SakanaAI's temporal processing
with the_brain's neurosymbolic architecture.

Training approach:
1. Generate synthetic puzzle boards
2. Train to maximize certainty on target actions
3. Track convergence and consciousness metrics

Usage:
    python scripts/train_hybrid_ctm.py
"""

import os
import sys
import json
import time
from datetime import datetime
from pathlib import Path

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.hybrid_ctm import HybridNeuroSymbolicCTM, HybridCTMOutput


class HybridCTMTrainer:
    """
    Trainer for HybridNeuroSymbolicCTM.

    Training objectives:
    1. Maximize certainty (minimize entropy) on correct predictions
    2. Learn temporal processing through NLM
    3. Develop meaningful synchronisation patterns
    """

    def __init__(
        self,
        feature_dim: int = 256,
        memory_length: int = 10,
        iterations: int = 30,
        n_synch_out: int = 64,
        n_synch_action: int = 32,
        out_dims: int = 4,
        learning_rate: float = 1e-4,
        checkpoint_dir: str = "data/hybrid_ctm_checkpoints",
        device: str = 'cpu'
    ):
        self.device = device
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        # Create model
        self.model = HybridNeuroSymbolicCTM(
            feature_dim=feature_dim,
            memory_length=memory_length,
            iterations=iterations,
            n_synch_out=n_synch_out,
            n_synch_action=n_synch_action,
            out_dims=out_dims,
            consciousness_threshold=0.95,
            device=device
        ).to(device)

        # Initialize lazy modules
        print("[Trainer] Initializing lazy modules...")
        dummy_board = torch.randint(0, 11, (1, 5, 4)).to(device)
        with torch.no_grad():
            _ = self.model(dummy_board, max_iterations=1)
        print(f"[Trainer] Model initialized with {self.model.get_num_parameters():,} parameters")

        # Optimizer
        self.optimizer = optim.AdamW(
            self.model.parameters(),
            lr=learning_rate,
            weight_decay=0.01
        )

        # Learning rate scheduler
        self.scheduler = optim.lr_scheduler.CosineAnnealingLR(
            self.optimizer,
            T_max=50,
            eta_min=1e-6
        )

        # Loss function: Cross-entropy for action prediction
        self.criterion = nn.CrossEntropyLoss()

        # Training history
        self.history = {
            'loss': [],
            'accuracy': [],
            'certainty': [],
            'convergence_rate': []
        }

    def generate_training_data(
        self,
        num_samples: int = 1000,
        board_size: tuple = (5, 4)
    ) -> tuple:
        """
        Generate synthetic training data.

        Creates random puzzle boards with random target actions.
        In a real scenario, this would be replaced with actual
        puzzle states and optimal actions.
        """
        print(f"[Trainer] Generating {num_samples} training samples...")

        # Random board states (values 0-10 representing piece IDs)
        boards = torch.randint(0, 11, (num_samples, *board_size))

        # Random target actions (4 directions)
        targets = torch.randint(0, 4, (num_samples,))

        return boards, targets

    def train_epoch(
        self,
        dataloader: DataLoader,
        max_iterations: int = 20
    ) -> dict:
        """
        Train for one epoch.

        Returns dict with epoch metrics.
        """
        self.model.train()

        total_loss = 0.0
        total_correct = 0
        total_samples = 0
        total_certainty = 0.0
        total_converged = 0

        for batch_idx, (boards, targets) in enumerate(dataloader):
            boards = boards.to(self.device)
            targets = targets.to(self.device)

            # Forward pass
            self.optimizer.zero_grad()
            output = self.model(boards, max_iterations=max_iterations)

            # Use final prediction for loss
            predictions = output.final_prediction

            # Loss: Cross-entropy on action prediction
            loss = self.criterion(predictions, targets)

            # Backward pass
            loss.backward()

            # Gradient clipping
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)

            self.optimizer.step()

            # Metrics
            total_loss += loss.item() * boards.size(0)
            _, predicted = predictions.max(1)
            total_correct += predicted.eq(targets).sum().item()
            total_samples += boards.size(0)
            total_certainty += output.certainties[:, -1].mean().item() * boards.size(0)
            total_converged += int(output.converged)

        return {
            'loss': total_loss / total_samples,
            'accuracy': total_correct / total_samples,
            'certainty': total_certainty / total_samples,
            'convergence_rate': total_converged / len(dataloader)
        }

    def evaluate(
        self,
        dataloader: DataLoader,
        max_iterations: int = 30
    ) -> dict:
        """
        Evaluate on validation set.
        """
        self.model.eval()

        total_loss = 0.0
        total_correct = 0
        total_samples = 0
        total_certainty = 0.0
        total_steps = 0

        with torch.no_grad():
            for boards, targets in dataloader:
                boards = boards.to(self.device)
                targets = targets.to(self.device)

                output = self.model(boards, max_iterations=max_iterations)
                predictions = output.final_prediction

                loss = self.criterion(predictions, targets)

                total_loss += loss.item() * boards.size(0)
                _, predicted = predictions.max(1)
                total_correct += predicted.eq(targets).sum().item()
                total_samples += boards.size(0)
                total_certainty += output.certainties[:, -1].mean().item() * boards.size(0)
                total_steps += output.reasoning_steps * boards.size(0)

        return {
            'loss': total_loss / total_samples,
            'accuracy': total_correct / total_samples,
            'certainty': total_certainty / total_samples,
            'avg_steps': total_steps / total_samples
        }

    def train(
        self,
        num_epochs: int = 50,
        batch_size: int = 32,
        num_samples: int = 2000,
        val_split: float = 0.1,
        max_iterations: int = 20,
        save_every: int = 10
    ):
        """
        Full training loop.
        """
        print("=" * 60)
        print("Training HybridNeuroSymbolicCTM")
        print("=" * 60)

        # Generate data
        boards, targets = self.generate_training_data(num_samples)

        # Split train/val
        val_size = int(num_samples * val_split)
        train_boards, val_boards = boards[val_size:], boards[:val_size]
        train_targets, val_targets = targets[val_size:], targets[:val_size]

        # Create dataloaders
        train_dataset = TensorDataset(train_boards, train_targets)
        val_dataset = TensorDataset(val_boards, val_targets)

        train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
        val_loader = DataLoader(val_dataset, batch_size=batch_size)

        print(f"\nTraining samples: {len(train_dataset)}")
        print(f"Validation samples: {len(val_dataset)}")
        print(f"Batch size: {batch_size}")
        print(f"Max iterations per forward: {max_iterations}")

        best_accuracy = 0.0
        start_time = time.time()

        for epoch in range(num_epochs):
            epoch_start = time.time()

            # Train
            train_metrics = self.train_epoch(train_loader, max_iterations)

            # Evaluate
            val_metrics = self.evaluate(val_loader, max_iterations)

            # Update scheduler
            self.scheduler.step()

            # Record history
            self.history['loss'].append(train_metrics['loss'])
            self.history['accuracy'].append(train_metrics['accuracy'])
            self.history['certainty'].append(train_metrics['certainty'])
            self.history['convergence_rate'].append(train_metrics['convergence_rate'])

            epoch_time = time.time() - epoch_start

            # Print progress
            print(f"\nEpoch {epoch + 1}/{num_epochs} ({epoch_time:.1f}s)")
            print(f"  Train - Loss: {train_metrics['loss']:.4f}, "
                  f"Acc: {train_metrics['accuracy']:.2%}, "
                  f"Cert: {train_metrics['certainty']:.4f}")
            print(f"  Val   - Loss: {val_metrics['loss']:.4f}, "
                  f"Acc: {val_metrics['accuracy']:.2%}, "
                  f"Cert: {val_metrics['certainty']:.4f}, "
                  f"Steps: {val_metrics['avg_steps']:.1f}")

            # Save best model
            if val_metrics['accuracy'] > best_accuracy:
                best_accuracy = val_metrics['accuracy']
                self.save_checkpoint(f"best_model.pth", epoch, val_metrics)
                print(f"  -> New best! Accuracy: {best_accuracy:.2%}")

            # Periodic save
            if (epoch + 1) % save_every == 0:
                self.save_checkpoint(f"epoch_{epoch + 1}.pth", epoch, val_metrics)

        total_time = time.time() - start_time
        print("\n" + "=" * 60)
        print(f"Training complete in {total_time / 60:.1f} minutes")
        print(f"Best validation accuracy: {best_accuracy:.2%}")
        print("=" * 60)

        # Save final model and history
        self.save_checkpoint("final_model.pth", num_epochs - 1, val_metrics)
        self.save_history()

        return self.history

    def save_checkpoint(self, filename: str, epoch: int, metrics: dict):
        """Save model checkpoint."""
        path = self.checkpoint_dir / filename
        torch.save({
            'epoch': epoch,
            'model_state_dict': self.model.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
            'metrics': metrics,
            'history': self.history
        }, path)
        print(f"  Saved checkpoint: {path}")

    def save_history(self):
        """Save training history to JSON."""
        path = self.checkpoint_dir / "training_history.json"
        with open(path, 'w') as f:
            json.dump(self.history, f, indent=2)
        print(f"Saved history: {path}")

    def load_checkpoint(self, filename: str):
        """Load model checkpoint."""
        path = self.checkpoint_dir / filename
        if not path.exists():
            print(f"Checkpoint not found: {path}")
            return False

        checkpoint = torch.load(path, map_location=self.device, weights_only=False)
        self.model.load_state_dict(checkpoint['model_state_dict'])
        self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
        self.history = checkpoint.get('history', self.history)
        print(f"Loaded checkpoint: {path}")
        return True


def main():
    """Main training function."""
    import argparse

    parser = argparse.ArgumentParser(description='Train HybridCTM')
    parser.add_argument('--epochs', type=int, default=30, help='Number of epochs')
    parser.add_argument('--batch-size', type=int, default=32, help='Batch size')
    parser.add_argument('--samples', type=int, default=2000, help='Number of samples')
    parser.add_argument('--lr', type=float, default=1e-4, help='Learning rate')
    parser.add_argument('--iterations', type=int, default=20, help='Max CTM iterations')
    parser.add_argument('--device', type=str, default='cpu', help='Device (cpu/cuda)')
    args = parser.parse_args()

    # Check for CUDA
    if args.device == 'cuda' and not torch.cuda.is_available():
        print("CUDA not available, using CPU")
        args.device = 'cpu'

    # Create trainer
    trainer = HybridCTMTrainer(
        feature_dim=256,
        memory_length=10,
        iterations=args.iterations,
        learning_rate=args.lr,
        device=args.device
    )

    # Train
    history = trainer.train(
        num_epochs=args.epochs,
        batch_size=args.batch_size,
        num_samples=args.samples,
        max_iterations=args.iterations
    )

    print("\nTraining Summary:")
    print(f"  Final loss: {history['loss'][-1]:.4f}")
    print(f"  Final accuracy: {history['accuracy'][-1]:.2%}")
    print(f"  Final certainty: {history['certainty'][-1]:.4f}")


if __name__ == "__main__":
    main()
