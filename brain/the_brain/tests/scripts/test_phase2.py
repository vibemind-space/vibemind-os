"""
Test Phase 2: Training Infrastructure for Temporal CTM

Tests the complete training pipeline:
- TemporalDataset and collate function
- Phase-locking loss functions
- Synthetic data generator
- Temporal CTM trainer
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 70)
print("PHASE 2 TEST: Training Infrastructure")
print("=" * 70)
print()

# Test 1: Import all training modules
print("[1] Testing imports...")
try:
    from training.temporal_dataset import (
        Regime, TemporalStep, TemporalTrajectory, TemporalDataset,
        TemporalBatch, collate_temporal_batch, create_dataloader
    )
    print("    [OK] temporal_dataset")
except ImportError as e:
    print(f"    [FAIL] temporal_dataset: {e}")
    sys.exit(1)

try:
    from training.phase_locking_loss import (
        PhaseLockingLoss, RegimeClassificationLoss,
        TransitionSmoothnessLoss, TemporalCTMLoss
    )
    print("    [OK] phase_locking_loss")
except ImportError as e:
    print(f"    [FAIL] phase_locking_loss: {e}")
    sys.exit(1)

try:
    from training.synthetic_data_generator import (
        SyncPattern, REGIME_SYNC_PATTERNS, SyntheticDataGenerator
    )
    print("    [OK] synthetic_data_generator")
except ImportError as e:
    print(f"    [FAIL] synthetic_data_generator: {e}")
    sys.exit(1)

try:
    from training.temporal_ctm_trainer import (
        TrainingConfig, TrainingMetrics, TemporalCTMModel, TemporalCTMTrainer
    )
    print("    [OK] temporal_ctm_trainer")
except ImportError as e:
    print(f"    [FAIL] temporal_ctm_trainer: {e}")
    sys.exit(1)

import torch
import numpy as np
print()

# Test 2: Synthetic data generation
print("[2] Testing synthetic data generation...")
generator = SyntheticDataGenerator(state_dim=192, num_cells=24, seed=42)

traj_exploit = generator.generate_exploit_trajectory(num_steps=5)
print(f"    EXPLOIT trajectory: {traj_exploit.num_steps} steps")
assert traj_exploit.num_steps == 5, "Wrong step count"
assert all(s.target_regime == Regime.EXPLOIT for s in traj_exploit.steps), "Wrong regime"

traj_explore = generator.generate_explore_trajectory(num_steps=6)
print(f"    EXPLORE trajectory: {traj_explore.num_steps} steps")
assert all(s.target_regime == Regime.EXPLORE for s in traj_explore.steps), "Wrong regime"

traj_repair = generator.generate_repair_trajectory(num_steps=4)
print(f"    REPAIR trajectory: {traj_repair.num_steps} steps")

traj_transition = generator.generate_transition_trajectory(
    from_regime=Regime.EXPLOIT,
    to_regime=Regime.EXPLORE
)
print(f"    TRANSITION trajectory: {traj_transition.num_steps} steps")
# Should have some transition steps
assert any(s.transition_expected for s in traj_transition.steps), "Missing transition markers"

traj_deadlock = generator.generate_deadlock_trajectory(num_steps=3)
print(f"    DEADLOCK trajectory: {traj_deadlock.num_steps} steps, success={traj_deadlock.success}")
assert traj_deadlock.success == False, "Deadlock should fail"

print("    [OK] All trajectory types generated correctly")
print()

# Test 3: Dataset and DataLoader
print("[3] Testing dataset and dataloader...")
dataset = generator.generate_dataset(
    num_exploit=10,
    num_explore=8,
    num_repair=8,
    num_transition=5,
    num_deadlock=3,
    num_mixed=6
)
stats = dataset.get_statistics()
print(f"    Dataset: {stats['num_trajectories']} trajectories, {stats['total_steps']} total steps")
print(f"    Success rate: {stats['success_rate']:.1%}")

# Test single item
item = dataset[0]
print(f"    Single item - state shape: {item['state_vectors'].shape}")
assert item['state_vectors'].shape[1] == 192, "Wrong state dim"
assert item['sync_vectors'].shape[1] == 9, "Wrong sync dim"

# Test dataloader
dataloader = create_dataloader(dataset, batch_size=4, shuffle=False)
batch = next(iter(dataloader))
print(f"    Batch - state shape: {batch.state_vectors.shape}")
assert batch.state_vectors.shape[0] == 4, "Wrong batch size"
assert batch.padding_mask.shape == batch.state_vectors.shape[:2], "Wrong mask shape"

print("    [OK] Dataset and DataLoader working")
print()

# Test 4: Loss functions
print("[4] Testing loss functions...")

# Phase-locking loss
phase_loss = PhaseLockingLoss()
sync_test = torch.randn(8, 9)
regime_test = torch.randint(0, 5, (8,))
loss_phase = phase_loss(sync_test, regime_test)
print(f"    PhaseLockingLoss: {loss_phase.item():.4f}")
assert loss_phase.item() >= 0, "Loss should be non-negative"

# Regime classification loss
regime_loss = RegimeClassificationLoss()
regime_logits = torch.randn(8, 5)
loss_regime = regime_loss(regime_logits, regime_test)
print(f"    RegimeClassificationLoss: {loss_regime.item():.4f}")

# Transition smoothness loss
trans_loss = TransitionSmoothnessLoss()
prev_probs = torch.softmax(torch.randn(8, 5), dim=-1)
curr_probs = torch.softmax(torch.randn(8, 5), dim=-1)
trans_expected = torch.zeros(8, dtype=torch.bool)
loss_trans = trans_loss(curr_probs, prev_probs, trans_expected)
print(f"    TransitionSmoothnessLoss: {loss_trans.item():.4f}")

# Combined loss
combined_loss = TemporalCTMLoss(num_cells=24, num_regimes=5)
cell_logits = torch.randn(8, 24)
timing_logits = torch.randn(8, 1)
target_cells = torch.randint(0, 24, (8,))
target_timing = torch.randint(0, 2, (8,))
losses = combined_loss(
    cell_logits, timing_logits, regime_logits, sync_test,
    target_cells, target_timing, regime_test
)
print(f"    TemporalCTMLoss total: {losses['total'].item():.4f}")
print(f"        action: {losses['action'].item():.4f}")
print(f"        timing: {losses['timing'].item():.4f}")
print(f"        regime: {losses['regime'].item():.4f}")
print(f"        phase_lock: {losses['phase_lock'].item():.4f}")
print(f"        transition: {losses['transition'].item():.4f}")

# Test gradient flow
cell_logits.requires_grad = True
losses = combined_loss(
    cell_logits, timing_logits, regime_logits, sync_test,
    target_cells, target_timing, regime_test
)
losses['total'].backward()
assert cell_logits.grad is not None, "Gradients should flow"
print("    [OK] All loss functions working with gradients")
print()

# Test 5: Model forward pass
print("[5] Testing TemporalCTMModel...")
model = TemporalCTMModel(hidden_dim=64, state_dim=192, num_cells=24, num_regimes=5)
print(f"    Model parameters: {sum(p.numel() for p in model.parameters()):,}")

# Forward pass
state_in = torch.randn(4, 10, 192)  # [batch, seq, state_dim]
sync_in = torch.randn(4, 10, 9)     # [batch, seq, sync_dim]
outputs = model(state_in, sync_in)

print(f"    cell_logits shape: {outputs['cell_logits'].shape}")
print(f"    timing_logits shape: {outputs['timing_logits'].shape}")
print(f"    regime_logits shape: {outputs['regime_logits'].shape}")

assert outputs['cell_logits'].shape == (4, 10, 24), "Wrong cell logits shape"
assert outputs['timing_logits'].shape == (4, 10, 1), "Wrong timing logits shape"
assert outputs['regime_logits'].shape == (4, 10, 5), "Wrong regime logits shape"

print("    [OK] Model forward pass working")
print()

# Test 6: Trainer (short training)
print("[6] Testing TemporalCTMTrainer (5 epochs)...")
config = TrainingConfig(
    hidden_dim=32,
    state_dim=192,
    num_epochs=5,
    batch_size=4,
    synthetic_exploit=5,
    synthetic_explore=4,
    synthetic_repair=4,
    synthetic_transition=2,
    synthetic_deadlock=1,
    synthetic_mixed=3,
    checkpoint_every=10,  # Don't checkpoint during test
    early_stopping_patience=50  # Don't early stop during test
)

trainer = TemporalCTMTrainer(config=config)
print(f"    Device: {trainer.device}")

# Generate data
trainer.generate_synthetic_data(seed=42)

# Train
history = trainer.train(num_epochs=5, verbose=False)

print(f"    Training complete!")
print(f"    Final train loss: {history['total_loss'][-1]:.4f}")
print(f"    Final val loss: {history['val_loss'][-1]:.4f}")
print(f"    Action accuracy: {history['action_accuracy'][-1]:.1%}")
print(f"    Regime accuracy: {history['regime_accuracy'][-1]:.1%}")

# Check loss decreased
assert history['total_loss'][-1] < history['total_loss'][0], "Loss should decrease"
print("    [OK] Loss decreased during training")
print()

# Test 7: Checkpoint save/load
print("[7] Testing checkpoint save/load...")
import tempfile
import os

with tempfile.TemporaryDirectory() as tmpdir:
    config.checkpoint_dir = tmpdir
    trainer2 = TemporalCTMTrainer(config=config)
    trainer2.generate_synthetic_data(seed=42)
    trainer2.train(num_epochs=3, verbose=False)

    # Save
    trainer2.save_checkpoint("test_checkpoint.pt")
    checkpoint_path = os.path.join(tmpdir, "test_checkpoint.pt")
    assert os.path.exists(checkpoint_path), "Checkpoint should exist"
    print(f"    Checkpoint saved: {os.path.getsize(checkpoint_path)} bytes")

    # Load into new trainer
    trainer3 = TemporalCTMTrainer(config=config)
    trainer3.load_checkpoint("test_checkpoint.pt")
    print(f"    Checkpoint loaded, epoch: {trainer3.current_epoch}")

print("    [OK] Checkpoint save/load working")
print()

# Summary
print("=" * 70)
print("PHASE 2 TEST COMPLETE")
print("=" * 70)
print()
print("All Phase 2 components working:")
print("  [OK] temporal_dataset.py - TemporalDataset, collate, DataLoader")
print("  [OK] phase_locking_loss.py - Multi-loss (action, timing, regime, lock, trans)")
print("  [OK] synthetic_data_generator.py - All regime patterns generated")
print("  [OK] temporal_ctm_trainer.py - Training loop with checkpointing")
print()
print("Training infrastructure ready for:")
print("  - Synthetic data pre-training")
print("  - Fine-tuning on real tool logs")
print("  - Multi-objective optimization (action + timing + regime)")
print("  - Phase-locking enforcement for oscillator synchronization")
print()
print("=" * 70)
