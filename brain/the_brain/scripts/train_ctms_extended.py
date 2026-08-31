"""
Extended CTM Training Script - Train to 85-90%+ Convergence

Trains Logic, Temporal, and Value CTMs with extended epochs and larger datasets.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.dream_mode_ctm_trainer import DreamModeCTMTrainer, TrainingConfig
from core.shared_enums import CTMDomain
import json
from datetime import datetime

def train_all_ctms():
    """Train all 3 specialized CTMs to higher convergence."""

    print("=" * 70)
    print("  EXTENDED CTM TRAINING - Target 85-90%+ Convergence")
    print("=" * 70)

    # Check for CUDA
    try:
        import torch
        cuda_available = torch.cuda.is_available()
        if cuda_available:
            print(f"\n[GPU] {torch.cuda.get_device_name(0)}")
            print(f"[GPU] CUDA {torch.version.cuda}")
        else:
            print("\n[CPU] Training on CPU (no CUDA)")
    except ImportError:
        cuda_available = False
        print("\n[CPU] PyTorch not available with CUDA")

    # Initialize trainer
    trainer = DreamModeCTMTrainer(
        klotski_brain_path='learning_engine/klotski/neurosymbolic',
        checkpoint_dir='data/ctm_checkpoints',
        enable_cuda=cuda_available
    )

    # Training configurations for 90%+ convergence
    configs = {
        CTMDomain.LOGIC: TrainingConfig(
            domain=CTMDomain.LOGIC,
            num_epochs=50,
            batch_size=32,
            learning_rate=1e-4,
            target_module_routing={'LAN': 0.70, 'DLPFC': 0.20, 'ACC': 0.10},
            dataset_size=2000,
            early_stopping_patience=15,
            checkpoint_interval=5
        ),
        CTMDomain.TEMPORAL: TrainingConfig(
            domain=CTMDomain.TEMPORAL,
            num_epochs=60,
            batch_size=32,
            learning_rate=1e-4,
            target_module_routing={'AUD': 0.60, 'MTL': 0.25, 'DLPFC': 0.15},
            dataset_size=2500,
            early_stopping_patience=15,
            checkpoint_interval=5
        ),
        CTMDomain.VALUE: TrainingConfig(
            domain=CTMDomain.VALUE,
            num_epochs=50,
            batch_size=32,
            learning_rate=1e-4,
            target_module_routing={'OFC': 0.70, 'ACC': 0.20, 'DLPFC': 0.10},
            dataset_size=2000,
            early_stopping_patience=15,
            checkpoint_interval=5
        )
    }

    results = {}

    # Train each CTM
    for domain, config in configs.items():
        print(f"\n\n{'=' * 70}")
        print(f"  TRAINING {domain.value.upper()}CTM")
        print(f"  Epochs: {config.num_epochs}, Dataset: {config.dataset_size}")
        print(f"{'=' * 70}\n")

        result = trainer.train_domain_ctm(domain=domain, config=config)
        results[domain.value] = result

        print(f"\n[{domain.value}] Result: {result['status']}")
        if result['status'] == 'completed':
            print(f"[{domain.value}] Best convergence: {result['best_convergence']:.2%}")
            print(f"[{domain.value}] Best epoch: {result['best_epoch']}")

    # Save summary
    summary_path = 'data/ctm_checkpoints/extended_training_summary.json'
    summary = {
        'timestamp': datetime.now().isoformat(),
        'results': results,
        'cuda_used': cuda_available
    }

    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2)

    print(f"\n\n{'=' * 70}")
    print("  TRAINING COMPLETE")
    print(f"{'=' * 70}")
    print(f"\nSummary saved to: {summary_path}")

    for domain, result in results.items():
        status = result.get('status', 'unknown')
        conv = result.get('best_convergence', 0)
        print(f"  {domain}: {status} ({conv:.2%} convergence)")

    return results


if __name__ == "__main__":
    train_all_ctms()
