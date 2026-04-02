"""
Quick Training Script for All CTMs (Logic, Temporal, Value)

Runs fast training (10 epochs, small dataset) for validation purposes.
Full training should use training/train_*_ctm.py scripts with more epochs.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.dream_mode_ctm_trainer import DreamModeCTMTrainer, TrainingConfig, CTMDomain
import torch
import json

def train_all_ctms():
    print("=" * 70)
    print("  QUICK CTM TRAINING - ALL DOMAINS")
    print("=" * 70)

    # Check CUDA
    cuda_available = torch.cuda.is_available() if torch else False
    if cuda_available:
        print(f"\n[GPU] Detected: {torch.cuda.get_device_name(0)}")
    else:
        print("\n[INFO] Using CPU")

    # Initialize trainer - use correct path within project
    trainer = DreamModeCTMTrainer(
        klotski_brain_path='learning_engine/klotski/neurosymbolic',
        checkpoint_dir='data/ctm_checkpoints',
        enable_cuda=cuda_available
    )

    # Training configs - reduced for quick validation
    configs = {
        CTMDomain.LOGIC: TrainingConfig(
            domain=CTMDomain.LOGIC,
            num_epochs=10,  # Reduced for quick training
            batch_size=32,
            learning_rate=0.001,
            target_module_routing={'LAN': 0.70, 'DLPFC': 0.20, 'ACC': 0.10},
            dataset_size=100  # Small dataset
        ),
        CTMDomain.TEMPORAL: TrainingConfig(
            domain=CTMDomain.TEMPORAL,
            num_epochs=10,
            batch_size=32,
            learning_rate=0.001,
            target_module_routing={'AUD': 0.60, 'MTL': 0.25, 'DLPFC': 0.15},
            dataset_size=100
        ),
        CTMDomain.VALUE: TrainingConfig(
            domain=CTMDomain.VALUE,
            num_epochs=10,
            batch_size=32,
            learning_rate=0.001,
            target_module_routing={'OFC': 0.70, 'ACC': 0.20, 'DLPFC': 0.10},
            dataset_size=100
        )
    }

    results = {}

    # Train each CTM
    for domain, config in configs.items():
        print(f"\n\n{'=' * 70}")
        print(f"  TRAINING {domain.value.upper()}CTM")
        print(f"{'=' * 70}")
        print(f"  Target routing: {config.target_module_routing}")
        print(f"  Epochs: {config.num_epochs}")
        print(f"  Dataset size: {config.dataset_size}")

        result = trainer.train_domain_ctm(domain=domain, config=config)
        results[domain.value] = result

        print(f"\n  Result: {result.get('status', 'unknown')}")
        if result.get('status') == 'completed':
            print(f"  Best convergence: {result.get('best_convergence', 0):.2%}")
            print(f"  Final routing: {result.get('final_routing', {})}")

    # Summary
    print("\n\n" + "=" * 70)
    print("  TRAINING SUMMARY")
    print("=" * 70)

    for domain, result in results.items():
        status = result.get('status', 'unknown')
        conv = result.get('best_convergence', 0)
        print(f"\n  {domain.upper()}CTM:")
        print(f"    Status: {status}")
        print(f"    Best convergence: {conv:.2%}")
        print(f"    Best epoch: {result.get('best_epoch', 'N/A')}")

    # Save summary
    summary_path = 'data/ctm_checkpoints/training_summary.json'
    with open(summary_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Summary saved: {summary_path}")

    print("\n" + "=" * 70)
    print("  ALL CTM TRAINING COMPLETE!")
    print("=" * 70)

    return results

if __name__ == "__main__":
    train_all_ctms()
