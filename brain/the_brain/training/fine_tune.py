"""
Fine-Tuning Script for Temporal CTM

Fine-tunes a pre-trained model on real session logs.

Usage:
    from training.fine_tune import FineTuner

    tuner = FineTuner(
        pretrained_checkpoint="data/temporal_checkpoints/best_model.pt",
        log_dir="data/logs",
        output_dir="data/finetuned_checkpoints"
    )

    # Fine-tune
    metrics = tuner.fine_tune(num_epochs=20)

    # Evaluate
    results = tuner.evaluate()
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import numpy as np

# Check for PyTorch
try:
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, ConcatDataset
    TORCH_AVAILABLE = True
except ImportError:
    print("[WARN] PyTorch not available - fine-tuning disabled")
    TORCH_AVAILABLE = False
    torch = None

# Import training infrastructure
from .temporal_dataset import TemporalDataset, create_dataloader
from .temporal_ctm_trainer import (
    TemporalCTMTrainer,
    TrainingConfig,
    TemporalCTMModel
)
from .log_parser import LogParser
from .synthetic_data_generator import SyntheticDataGenerator


@dataclass
class FineTuneConfig:
    """Configuration for fine-tuning"""
    # Model
    hidden_dim: int = 128
    state_dim: int = 192
    num_cells: int = 24
    num_regimes: int = 5

    # Fine-tuning hyperparameters
    num_epochs: int = 20
    batch_size: int = 16
    learning_rate: float = 1e-5  # Lower LR for fine-tuning
    weight_decay: float = 1e-5
    lr_scale: float = 0.1  # Scale factor relative to pre-training LR

    # Loss weights (can adjust for fine-tuning)
    lambda_action: float = 1.0
    lambda_timing: float = 0.5
    lambda_regime: float = 0.3
    lambda_lock: float = 0.2
    lambda_trans: float = 0.1

    # Data mixing
    mix_synthetic: bool = True  # Mix with synthetic data
    synthetic_ratio: float = 0.3  # Ratio of synthetic to real data

    # Early stopping
    early_stopping_patience: int = 10
    checkpoint_every: int = 5

    def to_dict(self) -> Dict:
        return {k: v for k, v in self.__dict__.items()}


class FineTuner:
    """
    Fine-tune pre-trained Temporal CTM on real logs

    Supports:
    - Loading pre-trained checkpoint
    - Parsing real session logs
    - Mixed training (synthetic + real)
    - Evaluation on held-out data
    """

    def __init__(
        self,
        pretrained_checkpoint: Optional[str] = None,
        log_dir: str = "data/logs",
        output_dir: str = "data/finetuned_checkpoints",
        config: Optional[FineTuneConfig] = None,
        device: Optional[str] = None
    ):
        """
        Initialize fine-tuner

        Args:
            pretrained_checkpoint: Path to pre-trained model checkpoint
            log_dir: Directory containing session logs
            output_dir: Directory for fine-tuned checkpoints
            config: Fine-tuning configuration
            device: Device to train on
        """
        if not TORCH_AVAILABLE:
            raise RuntimeError("PyTorch required for fine-tuning")

        self.config = config or FineTuneConfig()
        self.log_dir = Path(log_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Device
        if device is None:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)

        # Create model
        self.model = TemporalCTMModel(
            hidden_dim=self.config.hidden_dim,
            state_dim=self.config.state_dim,
            num_cells=self.config.num_cells,
            num_regimes=self.config.num_regimes
        ).to(self.device)

        # Load pre-trained weights if provided
        self.pretrained_loaded = False
        if pretrained_checkpoint and Path(pretrained_checkpoint).exists():
            self._load_pretrained(pretrained_checkpoint)
            self.pretrained_loaded = True
            print(f"[FineTuner] Loaded pre-trained model from {pretrained_checkpoint}")
        else:
            print("[FineTuner] Starting from scratch (no pre-trained checkpoint)")

        # Create trainer with fine-tuning config
        trainer_config = TrainingConfig(
            hidden_dim=self.config.hidden_dim,
            state_dim=self.config.state_dim,
            num_cells=self.config.num_cells,
            num_regimes=self.config.num_regimes,
            num_epochs=self.config.num_epochs,
            batch_size=self.config.batch_size,
            learning_rate=self.config.learning_rate,
            weight_decay=self.config.weight_decay,
            lambda_action=self.config.lambda_action,
            lambda_timing=self.config.lambda_timing,
            lambda_regime=self.config.lambda_regime,
            lambda_lock=self.config.lambda_lock,
            lambda_trans=self.config.lambda_trans,
            early_stopping_patience=self.config.early_stopping_patience,
            checkpoint_every=self.config.checkpoint_every,
            checkpoint_dir=str(self.output_dir)
        )
        self.trainer = TemporalCTMTrainer(
            config=trainer_config,
            model=self.model,
            device=str(self.device)
        )

        # Data
        self.real_dataset: Optional[TemporalDataset] = None
        self.synthetic_dataset: Optional[TemporalDataset] = None
        self.combined_dataset: Optional[TemporalDataset] = None
        self.val_dataset: Optional[TemporalDataset] = None

    def _load_pretrained(self, checkpoint_path: str):
        """Load pre-trained model weights"""
        checkpoint = torch.load(checkpoint_path, map_location=self.device, weights_only=False)

        if 'model_state_dict' in checkpoint:
            self.model.load_state_dict(checkpoint['model_state_dict'])
        else:
            # Try direct state dict
            self.model.load_state_dict(checkpoint)

    def load_real_data(self) -> int:
        """
        Load and parse real session logs

        Returns:
            Number of trajectories loaded
        """
        print(f"[FineTuner] Loading real data from {self.log_dir}")

        parser = LogParser(
            str(self.log_dir),
            state_dim=self.config.state_dim,
            num_cells=self.config.num_cells
        )

        self.real_dataset = parser.to_dataset()
        stats = self.real_dataset.get_statistics()

        if stats.get('empty', False):
            print("[FineTuner] Warning: No real data found!")
            return 0

        print(f"[FineTuner] Loaded {stats['num_trajectories']} real trajectories")
        print(f"    Total steps: {stats['total_steps']}")
        print(f"    Success rate: {stats['success_rate']:.1%}")

        return stats['num_trajectories']

    def generate_synthetic_data(
        self,
        num_trajectories: int = 100
    ) -> int:
        """
        Generate synthetic data for mixed training

        Args:
            num_trajectories: Number of synthetic trajectories

        Returns:
            Number of trajectories generated
        """
        print(f"[FineTuner] Generating {num_trajectories} synthetic trajectories")

        generator = SyntheticDataGenerator(
            state_dim=self.config.state_dim,
            num_cells=self.config.num_cells
        )

        # Distribute across regime types
        per_type = num_trajectories // 5
        self.synthetic_dataset = generator.generate_dataset(
            num_exploit=per_type,
            num_explore=per_type,
            num_repair=per_type,
            num_transition=per_type // 2,
            num_deadlock=per_type // 4,
            num_mixed=per_type
        )

        stats = self.synthetic_dataset.get_statistics()
        print(f"[FineTuner] Generated {stats['num_trajectories']} synthetic trajectories")

        return stats['num_trajectories']

    def prepare_data(
        self,
        val_split: float = 0.1
    ):
        """
        Prepare training and validation data

        Args:
            val_split: Fraction for validation
        """
        # Load real data
        num_real = self.load_real_data()

        # Generate synthetic if configured
        if self.config.mix_synthetic and num_real > 0:
            # Calculate synthetic count based on ratio
            num_synthetic = int(num_real * self.config.synthetic_ratio / (1 - self.config.synthetic_ratio))
            self.generate_synthetic_data(max(10, num_synthetic))

        # Combine datasets
        if self.real_dataset and self.synthetic_dataset:
            # Combine trajectories
            combined_trajectories = (
                self.real_dataset.trajectories +
                self.synthetic_dataset.trajectories
            )
            self.combined_dataset = TemporalDataset(
                trajectories=combined_trajectories,
                state_dim=self.config.state_dim
            )
            print(f"[FineTuner] Combined dataset: {len(combined_trajectories)} trajectories")
        elif self.real_dataset:
            self.combined_dataset = self.real_dataset
        elif self.synthetic_dataset:
            self.combined_dataset = self.synthetic_dataset
            print("[FineTuner] Warning: Using only synthetic data (no real data found)")
        else:
            raise ValueError("No data available for fine-tuning")

        # Split for validation
        total = len(self.combined_dataset)
        val_size = max(1, int(total * val_split))
        train_size = total - val_size

        # Random split
        indices = list(range(total))
        np.random.shuffle(indices)

        train_trajectories = [
            self.combined_dataset.trajectories[i]
            for i in indices[:train_size]
        ]
        val_trajectories = [
            self.combined_dataset.trajectories[i]
            for i in indices[train_size:]
        ]

        self.trainer.train_dataset = TemporalDataset(
            trajectories=train_trajectories,
            state_dim=self.config.state_dim
        )
        self.trainer.val_dataset = TemporalDataset(
            trajectories=val_trajectories,
            state_dim=self.config.state_dim
        )

        # Create dataloaders
        self.trainer.train_loader = create_dataloader(
            self.trainer.train_dataset,
            batch_size=self.config.batch_size,
            shuffle=True
        )
        self.trainer.val_loader = create_dataloader(
            self.trainer.val_dataset,
            batch_size=self.config.batch_size,
            shuffle=False
        )

        print(f"[FineTuner] Train: {train_size}, Val: {val_size}")

    def fine_tune(
        self,
        num_epochs: Optional[int] = None,
        verbose: bool = True
    ) -> Dict[str, List[float]]:
        """
        Run fine-tuning

        Args:
            num_epochs: Number of epochs (uses config if None)
            verbose: Print progress

        Returns:
            Training history
        """
        if num_epochs is None:
            num_epochs = self.config.num_epochs

        # Prepare data if not already done
        if self.trainer.train_loader is None:
            self.prepare_data()

        if verbose:
            print()
            print(f"[FineTuner] Starting fine-tuning for {num_epochs} epochs")
            print(f"    Device: {self.device}")
            print(f"    Pre-trained: {self.pretrained_loaded}")
            print(f"    Learning rate: {self.config.learning_rate}")
            print(f"    Mix synthetic: {self.config.mix_synthetic}")
            print()

        # Run training
        history = self.trainer.train(num_epochs=num_epochs, verbose=verbose)

        # Save final model
        self.trainer.save_checkpoint("finetuned_final.pt")

        return history

    def evaluate(
        self,
        test_log_dir: Optional[str] = None
    ) -> Dict:
        """
        Evaluate fine-tuned model

        Args:
            test_log_dir: Optional separate test log directory

        Returns:
            Evaluation metrics
        """
        self.model.eval()

        # Use validation set or load test data
        if test_log_dir:
            parser = LogParser(
                test_log_dir,
                state_dim=self.config.state_dim,
                num_cells=self.config.num_cells
            )
            test_dataset = parser.to_dataset()
        elif self.trainer.val_dataset:
            test_dataset = self.trainer.val_dataset
        else:
            return {'error': 'No test data available'}

        if test_dataset.get_statistics().get('empty', False):
            return {'error': 'Empty test dataset'}

        # Evaluate
        test_loader = create_dataloader(
            test_dataset,
            batch_size=self.config.batch_size,
            shuffle=False
        )

        val_metrics = self.trainer.validate()

        return {
            'val_loss': val_metrics.total_loss,
            'action_accuracy': val_metrics.action_accuracy,
            'timing_accuracy': val_metrics.timing_accuracy,
            'regime_accuracy': val_metrics.regime_accuracy,
            'num_samples': len(test_dataset)
        }

    def save_checkpoint(self, filename: str):
        """Save fine-tuned model"""
        self.trainer.save_checkpoint(filename)

    def get_model(self) -> nn.Module:
        """Get fine-tuned model"""
        return self.model


def fine_tune_from_logs(
    log_dir: str,
    pretrained_checkpoint: Optional[str] = None,
    output_dir: str = "data/finetuned_checkpoints",
    num_epochs: int = 20,
    mix_synthetic: bool = True
) -> Dict:
    """
    Convenience function to fine-tune on logs

    Args:
        log_dir: Directory with session logs
        pretrained_checkpoint: Path to pre-trained model
        output_dir: Output directory for checkpoints
        num_epochs: Number of fine-tuning epochs
        mix_synthetic: Mix with synthetic data

    Returns:
        Training history and evaluation metrics
    """
    config = FineTuneConfig(
        num_epochs=num_epochs,
        mix_synthetic=mix_synthetic
    )

    tuner = FineTuner(
        pretrained_checkpoint=pretrained_checkpoint,
        log_dir=log_dir,
        output_dir=output_dir,
        config=config
    )

    # Fine-tune
    history = tuner.fine_tune()

    # Evaluate
    eval_metrics = tuner.evaluate()

    return {
        'history': history,
        'evaluation': eval_metrics,
        'checkpoint_dir': output_dir
    }


if __name__ == "__main__":
    print("=" * 70)
    print("FINE-TUNER - Testing")
    print("=" * 70)
    print()

    import tempfile

    # Test 1: Create fine-tuner without pre-trained checkpoint
    print("[1] Creating FineTuner (no pre-trained checkpoint)...")
    config = FineTuneConfig(
        hidden_dim=32,
        num_epochs=3,
        batch_size=4,
        mix_synthetic=True,
        synthetic_ratio=0.5
    )

    with tempfile.TemporaryDirectory() as log_dir:
        with tempfile.TemporaryDirectory() as output_dir:
            # Create some mock log data
            import json
            mock_log = {
                "task": "Test task",
                "tool_calls": [
                    {"tool": "read_file", "success": True},
                    {"tool": "edit_file", "success": True},
                    {"tool": "bash_run", "success": False},
                    {"tool": "bash_run", "success": True}
                ],
                "decision": {"status": "GREEN"}
            }
            with open(os.path.join(log_dir, "test.json"), 'w') as f:
                json.dump(mock_log, f)

            tuner = FineTuner(
                pretrained_checkpoint=None,
                log_dir=log_dir,
                output_dir=output_dir,
                config=config
            )
            print(f"    Device: {tuner.device}")
            print(f"    Pre-trained loaded: {tuner.pretrained_loaded}")
            print()

            # Test 2: Load data
            print("[2] Loading data...")
            tuner.prepare_data(val_split=0.2)
            print()

            # Test 3: Fine-tune
            print("[3] Fine-tuning (3 epochs)...")
            history = tuner.fine_tune(num_epochs=3, verbose=False)
            print(f"    Final train loss: {history['total_loss'][-1]:.4f}")
            print(f"    Final val loss: {history['val_loss'][-1]:.4f}")
            print()

            # Test 4: Evaluate
            print("[4] Evaluating...")
            eval_metrics = tuner.evaluate()
            print(f"    Val loss: {eval_metrics.get('val_loss', 'N/A')}")
            print(f"    Action accuracy: {eval_metrics.get('action_accuracy', 0):.1%}")
            print(f"    Regime accuracy: {eval_metrics.get('regime_accuracy', 0):.1%}")
            print()

            # Test 5: Save checkpoint
            print("[5] Saving checkpoint...")
            tuner.save_checkpoint("test_finetuned.pt")
            checkpoint_path = os.path.join(output_dir, "test_finetuned.pt")
            assert os.path.exists(checkpoint_path), "Checkpoint should exist"
            print(f"    Saved to {checkpoint_path}")
            print()

    print("=" * 70)
    print("FINE-TUNER TESTS COMPLETE")
    print("=" * 70)
