"""
Run Temporal CTM Training

Trains the Temporal CTM with:
- Synthetic data generation
- Phase 4 expert dynamics (if available)
- Multi-loss optimization
- Checkpointing

Usage:
    python run_temporal_training.py
"""

import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from training import (
    TrainingConfig,
    TemporalCTMTrainer,
    PHASE4_AVAILABLE
)


def main():
    print("=" * 70)
    print("TEMPORAL CTM TRAINING")
    print("=" * 70)
    print(f"Started at: {datetime.now().isoformat()}")
    print(f"Phase 4 available: {PHASE4_AVAILABLE}")
    print()

    # Configuration
    config = TrainingConfig(
        # Model
        hidden_dim=128,
        state_dim=192,
        num_cells=24,  # 3x8 drumpad
        num_regimes=5,

        # Training
        num_epochs=30,
        batch_size=16,
        learning_rate=1e-4,

        # Loss weights
        lambda_action=1.0,
        lambda_timing=0.5,
        lambda_regime=0.3,
        lambda_lock=0.2,
        lambda_trans=0.1,

        # Phase 4 (expert dynamics)
        enable_phase4=PHASE4_AVAILABLE,
        lambda_dyn=0.3,
        lambda_div=0.2,
        lambda_spec=0.15,

        # Checkpointing
        checkpoint_every=10,
        checkpoint_dir="data/layer4_checkpoints"
    )

    print("[CONFIG]")
    print(f"  Epochs: {config.num_epochs}")
    print(f"  Batch size: {config.batch_size}")
    print(f"  Learning rate: {config.learning_rate}")
    print(f"  Phase 4 enabled: {config.enable_phase4}")
    print()

    # Initialize trainer
    print("[1] Initializing trainer...")
    trainer = TemporalCTMTrainer(config=config)
    print(f"    Device: {trainer.device}")
    print(f"    Model parameters: {sum(p.numel() for p in trainer.model.parameters()):,}")
    print()

    # Training loop (generates synthetic data internally)
    print("[2] Starting training...")
    print("-" * 70)

    history = trainer.train(
        num_epochs=config.num_epochs,
        verbose=True
    )

    print("-" * 70)
    print()

    # Final results
    print("[3] Training complete!")
    print()
    print("Final Metrics:")
    print(f"  Train Loss: {history['total_loss'][-1]:.4f}")
    print(f"  Val Loss: {history['val_loss'][-1]:.4f}")
    print(f"  Action Accuracy: {history['action_accuracy'][-1]:.1%}")
    print(f"  Timing Accuracy: {history['timing_accuracy'][-1]:.1%}")
    print(f"  Regime Accuracy: {history['regime_accuracy'][-1]:.1%}")

    if config.enable_phase4 and 'dynamics_loss' in history:
        print()
        print("Phase 4 Metrics:")
        print(f"  Dynamics Loss: {history['dynamics_loss'][-1]:.4f}")
        print(f"  Diversity Loss: {history['diversity_loss'][-1]:.4f}")
        print(f"  Specialization Loss: {history['specialization_loss'][-1]:.4f}")

    # Save final checkpoint
    print()
    print("[4] Saving final checkpoint...")
    final_path = trainer.save_checkpoint("final")
    print(f"    Saved to: {final_path}")

    print()
    print("=" * 70)
    print("TRAINING COMPLETE")
    print(f"Finished at: {datetime.now().isoformat()}")
    print("=" * 70)

    return history


if __name__ == "__main__":
    main()
