"""
Train TemporalCTM with Real Klotski Neurosymbolic Brain

Trains TemporalCTM for time-series prediction and temporal pattern recognition.
Target module routing: AUD=60%, MTL=25%, DLPFC=15%
"""

from core.dream_mode_ctm_trainer import DreamModeCTMTrainer, TrainingConfig, CTMDomain
import torch

def main():
    print("="*70)
    print("TEMPORALCTM TRAINING - KLOTSKI NEUROSYMBOLIC BRAIN")
    print("="*70)

    # Initialize trainer
    print("\n[1/4] Initializing Dream Mode CTM Trainer...")
    trainer = DreamModeCTMTrainer(
        klotski_brain_path='../KlotskiPuzzle/neurosymbolic',
        checkpoint_dir='data/ctm_checkpoints',
        enable_cuda=torch.cuda.is_available()
    )

    # Check GPU
    if torch.cuda.is_available():
        print(f"[GPU] Detected: {torch.cuda.get_device_name(0)}")
        print(f"[GPU] Memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
    else:
        print("[WARN] No GPU detected, using CPU")

    # Configure training
    print("\n[2/4] Configuring training parameters...")
    config = TrainingConfig(
        domain=CTMDomain.TEMPORAL,
        num_epochs=20,
        batch_size=32,
        learning_rate=0.001,
        dataset_size=1200
    )

    print(f"  Epochs: {config.num_epochs}")
    print(f"  Batch Size: {config.batch_size}")
    print(f"  Learning Rate: {config.learning_rate}")
    print(f"  Dataset Size: {config.dataset_size} time-series tasks")
    print(f"  Target Routing: AUD=60%, MTL=25%, DLPFC=15%")

    # Train TemporalCTM
    print("\n[3/4] Starting TemporalCTM training...")
    print("This will take approximately 3-5 hours on GPU")
    print("-" * 70)

    result = trainer.train_domain_ctm(
        domain=CTMDomain.TEMPORAL,
        config=config
    )

    # Display results
    print("\n" + "="*70)
    print("TRAINING COMPLETE!")
    print("="*70)
    print(f"Best Routing Convergence: {result['best_convergence']:.2%}")
    print(f"Checkpoints Saved: {result.get('checkpoints_saved', 'N/A')}")
    print(f"Progress Files Saved: {result.get('progress_saved', 'N/A')}")
    print(f"Training Time: {result.get('training_time_seconds', 0):.1f} seconds")
    print("\n[4/4] TemporalCTM brain ready for deployment!")
    print("="*70)

if __name__ == "__main__":
    main()
