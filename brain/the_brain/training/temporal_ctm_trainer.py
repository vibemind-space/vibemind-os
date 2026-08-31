"""
Temporal CTM Trainer - Main Training Loop for Phase 2 & 4

Trains the Temporal CTM with multi-loss optimization:
- L_action: Drumpad cell selection (CrossEntropy)
- L_timing: When to act (BCE on should_act)
- L_regime: Regime classification (CrossEntropy)
- L_phase_lock: Phase synchronization (MSE on sync targets)
- L_transition: Smooth regime transitions (KL divergence)

Phase 4 Extensions (Expert Phase Dynamics):
- L_dyn: Dynamics consistency (ΔφH equation)
- L_div: Expert diversity (anti-collapse)
- L_spec: Expert specialization (stability without events)

Usage:
    from training.temporal_ctm_trainer import TemporalCTMTrainer

    trainer = TemporalCTMTrainer(
        hidden_dim=128,
        state_dim=192,
        checkpoint_dir="data/temporal_checkpoints"
    )

    # Train on synthetic data
    metrics = trainer.train(num_epochs=50)

    # Save checkpoint
    trainer.save_checkpoint("best_model.pt")
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime
import numpy as np

# Check for PyTorch
try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from torch.optim import Adam, AdamW
    from torch.optim.lr_scheduler import CosineAnnealingLR, ReduceLROnPlateau
    TORCH_AVAILABLE = True
except ImportError:
    print("[WARN] PyTorch not available - training disabled")
    TORCH_AVAILABLE = False
    torch = None

# Import training infrastructure
from .temporal_dataset import (
    TemporalDataset,
    TemporalBatch,
    TemporalTrajectory,
    collate_temporal_batch,
    create_dataloader,
    Regime
)
from .phase_locking_loss import (
    TemporalCTMLoss,
    PhaseLockingLoss,
    RegimeClassificationLoss,
    TransitionSmoothnessLoss,
    PHASE4_AVAILABLE
)
from .synthetic_data_generator import SyntheticDataGenerator

# Phase 4 imports (optional)
if PHASE4_AVAILABLE:
    from .phase_locking_loss import ExtendedTemporalCTMLoss
    from .expert_dynamics_loss import (
        DynamicsConsistencyLoss,
        ExpertDiversityLoss,
        ExpertSpecializationLoss
    )


@dataclass
class TrainingConfig:
    """Configuration for temporal CTM training"""
    # Model dimensions
    hidden_dim: int = 128
    state_dim: int = 192
    num_cells: int = 24  # 3x8 drumpad
    num_regimes: int = 5

    # Training hyperparameters
    num_epochs: int = 100
    batch_size: int = 32
    learning_rate: float = 1e-4
    weight_decay: float = 1e-5

    # Loss weights (from plan)
    lambda_action: float = 1.0
    lambda_timing: float = 0.5
    lambda_regime: float = 0.3
    lambda_lock: float = 0.2
    lambda_trans: float = 0.1

    # Phase 4 loss weights (expert dynamics)
    enable_phase4: bool = False
    lambda_dyn: float = 0.3      # Dynamics consistency
    lambda_div: float = 0.2      # Expert diversity
    lambda_spec: float = 0.15    # Expert specialization

    # Phase 4 dynamics parameters
    num_experts: int = 5
    num_channels: int = 3
    lambda_time_constant: float = 0.1
    dynamics_dt: float = 0.1

    # Scheduler
    use_scheduler: bool = True
    scheduler_type: str = "cosine"  # or "plateau"

    # Checkpointing
    checkpoint_every: int = 10
    checkpoint_dir: str = "data/temporal_checkpoints"

    # Dataset
    synthetic_exploit: int = 50
    synthetic_explore: int = 40
    synthetic_repair: int = 40
    synthetic_transition: int = 25
    synthetic_deadlock: int = 15
    synthetic_mixed: int = 30

    # Training options
    use_mamba: bool = False
    use_klotski_ctm: bool = False
    grad_clip: float = 1.0
    early_stopping_patience: int = 20

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class TrainingMetrics:
    """Metrics from a training run"""
    epoch: int
    total_loss: float
    action_loss: float
    timing_loss: float
    regime_loss: float
    phase_lock_loss: float
    transition_loss: float
    action_accuracy: float
    timing_accuracy: float
    regime_accuracy: float
    learning_rate: float
    # Phase 4 metrics (optional)
    dynamics_loss: float = 0.0
    diversity_loss: float = 0.0
    specialization_loss: float = 0.0

    def to_dict(self) -> Dict:
        return self.__dict__.copy()


class TemporalCTMModel(nn.Module):
    """
    Lightweight temporal CTM model for training

    Simplified version that focuses on the core training objectives:
    - Cell selection (action)
    - Timing gate (when to act)
    - Regime classification
    - Synchrony embedding

    Phase 4: Also includes learnable event_proj and W matrices
    """

    def __init__(
        self,
        hidden_dim: int = 128,
        state_dim: int = 192,
        num_cells: int = 24,
        num_regimes: int = 5,
        sync_dim: int = 9,
        enable_phase4: bool = False,
        num_experts: int = 5,
        num_channels: int = 3
    ):
        super().__init__()
        self.hidden_dim = hidden_dim
        self.state_dim = state_dim
        self.num_cells = num_cells
        self.num_regimes = num_regimes
        self.enable_phase4 = enable_phase4

        # State encoder
        self.state_encoder = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU()
        )

        # Synchrony encoder
        self.sync_encoder = nn.Sequential(
            nn.Linear(sync_dim, hidden_dim // 2),
            nn.LayerNorm(hidden_dim // 2),
            nn.GELU()
        )

        # Combined processing
        combined_dim = hidden_dim + hidden_dim // 2
        self.combined_processor = nn.Sequential(
            nn.Linear(combined_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
            nn.Dropout(0.1)
        )

        # Temporal dynamics (GRU for sequence modeling)
        self.temporal_gru = nn.GRU(
            input_size=hidden_dim,
            hidden_size=hidden_dim,
            num_layers=2,
            batch_first=True,
            dropout=0.1
        )

        # Output heads
        self.cell_head = nn.Linear(hidden_dim, num_cells)
        self.timing_head = nn.Linear(hidden_dim, 1)
        self.regime_head = nn.Linear(hidden_dim, num_regimes)

        # Phase 4: Learnable projection matrices
        if enable_phase4:
            # Event projection: events [5] -> channels [3]
            self.event_proj = nn.Parameter(torch.randn(num_experts, num_channels) * 0.1)
            # Coupling matrix: experts [5] -> channels [3]
            self.W = nn.Parameter(torch.randn(num_experts, num_channels) * 0.1)
            # Expert predictor (from hidden state)
            self.expert_head = nn.Linear(hidden_dim, num_experts)
            # Phase predictor (for oscillator phases)
            self.phase_head = nn.Linear(hidden_dim, num_channels)
            # Amplitude predictor
            self.amplitude_head = nn.Linear(hidden_dim, num_channels)
            # Initialize with semantic priors
            self._init_phase4_priors()
        else:
            self.event_proj = None
            self.W = None
            self.expert_head = None
            self.phase_head = None
            self.amplitude_head = None

    def _init_phase4_priors(self):
        """Initialize Phase 4 matrices with semantic structure"""
        with torch.no_grad():
            # Event projection: errors -> C (correct), goal -> A (advance), etc.
            # Event indices: error=0, goal_near=1, loop=2, novelty=3, timeout=4
            # Channel indices: A=0 (Advance), B=1 (Explore), C=2 (Correct)
            self.event_proj.data[0, :] = torch.tensor([-0.2, 0.1, 0.4])   # error -> C
            self.event_proj.data[1, :] = torch.tensor([0.4, -0.1, 0.0])   # goal -> A
            self.event_proj.data[2, :] = torch.tensor([-0.2, 0.3, 0.2])   # loop -> B
            self.event_proj.data[3, :] = torch.tensor([0.0, 0.4, 0.1])    # novelty -> B
            self.event_proj.data[4, :] = torch.tensor([-0.1, 0.1, 0.3])   # timeout -> C

            # Coupling matrix: EXPLOIT->A, EXPLORE->B, REPAIR->C, etc.
            # Expert indices: EXPLOIT=0, EXPLORE=1, REPAIR=2, TRANSITION=3, DEADLOCK=4
            self.W.data[0, :] = torch.tensor([0.3, -0.1, 0.0])   # EXPLOIT -> A
            self.W.data[1, :] = torch.tensor([-0.1, 0.3, 0.1])   # EXPLORE -> B
            self.W.data[2, :] = torch.tensor([-0.1, 0.0, 0.3])   # REPAIR -> C
            self.W.data[3, :] = torch.tensor([0.1, 0.1, 0.1])    # TRANSITION -> balanced
            self.W.data[4, :] = torch.tensor([-0.2, -0.2, -0.2]) # DEADLOCK -> suppress all

    def forward(
        self,
        state_vectors: torch.Tensor,
        sync_vectors: torch.Tensor,
        hidden: Optional[torch.Tensor] = None
    ) -> Dict[str, torch.Tensor]:
        """
        Forward pass

        Args:
            state_vectors: [batch, seq_len, state_dim]
            sync_vectors: [batch, seq_len, sync_dim]
            hidden: Optional GRU hidden state

        Returns:
            Dict with cell_logits, timing_logits, regime_logits, hidden
        """
        batch_size, seq_len, _ = state_vectors.shape

        # Encode states and sync vectors
        state_enc = self.state_encoder(state_vectors)  # [batch, seq, hidden]
        sync_enc = self.sync_encoder(sync_vectors)     # [batch, seq, hidden//2]

        # Combine
        combined = torch.cat([state_enc, sync_enc], dim=-1)  # [batch, seq, hidden + hidden//2]
        processed = self.combined_processor(combined)         # [batch, seq, hidden]

        # Temporal dynamics
        temporal_out, new_hidden = self.temporal_gru(processed, hidden)

        # Output heads
        cell_logits = self.cell_head(temporal_out)       # [batch, seq, num_cells]
        timing_logits = self.timing_head(temporal_out)   # [batch, seq, 1]
        regime_logits = self.regime_head(temporal_out)   # [batch, seq, num_regimes]

        result = {
            'cell_logits': cell_logits,
            'timing_logits': timing_logits,
            'regime_logits': regime_logits,
            'hidden': new_hidden
        }

        # Phase 4: Additional outputs
        if self.enable_phase4 and self.expert_head is not None:
            result['expert_logits'] = self.expert_head(temporal_out)     # [batch, seq, num_experts]
            result['phase_pred'] = torch.sigmoid(self.phase_head(temporal_out)) * 2 * 3.14159  # [batch, seq, 3] in [0, 2π]
            result['amplitude_pred'] = torch.sigmoid(self.amplitude_head(temporal_out))  # [batch, seq, 3] in [0, 1]
            result['event_proj'] = self.event_proj
            result['W'] = self.W

        return result


class TemporalCTMTrainer:
    """
    Main trainer for Temporal CTM

    Implements the multi-loss training loop with:
    - Action imitation (cell selection)
    - Timing prediction (when to act)
    - Regime classification
    - Phase-locking enforcement
    - Transition smoothness
    """

    def __init__(
        self,
        config: Optional[TrainingConfig] = None,
        model: Optional[nn.Module] = None,
        device: Optional[str] = None
    ):
        """
        Initialize trainer

        Args:
            config: Training configuration
            model: Optional pre-existing model
            device: Device to train on (auto-detect if None)
        """
        if not TORCH_AVAILABLE:
            raise RuntimeError("PyTorch required for training")

        self.config = config or TrainingConfig()

        # Device
        if device is None:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)

        # Check Phase 4 availability
        self.use_phase4 = self.config.enable_phase4 and PHASE4_AVAILABLE
        if self.config.enable_phase4 and not PHASE4_AVAILABLE:
            print("[WARN] Phase 4 requested but not available - falling back to Phase 2")

        # Model
        if model is not None:
            self.model = model.to(self.device)
        else:
            self.model = TemporalCTMModel(
                hidden_dim=self.config.hidden_dim,
                state_dim=self.config.state_dim,
                num_cells=self.config.num_cells,
                num_regimes=self.config.num_regimes,
                enable_phase4=self.use_phase4,
                num_experts=self.config.num_experts,
                num_channels=self.config.num_channels
            ).to(self.device)

        # Loss function (Phase 2 or Phase 4)
        if self.use_phase4:
            self.criterion = ExtendedTemporalCTMLoss(
                num_cells=self.config.num_cells,
                num_regimes=self.config.num_regimes,
                lambda_action=self.config.lambda_action,
                lambda_timing=self.config.lambda_timing,
                lambda_regime=self.config.lambda_regime,
                lambda_lock=self.config.lambda_lock,
                lambda_trans=self.config.lambda_trans,
                lambda_dyn=self.config.lambda_dyn,
                lambda_div=self.config.lambda_div,
                lambda_spec=self.config.lambda_spec
            )
        else:
            self.criterion = TemporalCTMLoss(
                num_cells=self.config.num_cells,
                num_regimes=self.config.num_regimes,
                lambda_action=self.config.lambda_action,
                lambda_timing=self.config.lambda_timing,
                lambda_regime=self.config.lambda_regime,
                lambda_lock=self.config.lambda_lock,
                lambda_trans=self.config.lambda_trans
            )

        # Optimizer
        self.optimizer = AdamW(
            self.model.parameters(),
            lr=self.config.learning_rate,
            weight_decay=self.config.weight_decay
        )

        # Scheduler
        if self.config.use_scheduler:
            if self.config.scheduler_type == "cosine":
                self.scheduler = CosineAnnealingLR(
                    self.optimizer,
                    T_max=self.config.num_epochs,
                    eta_min=1e-6
                )
            else:
                self.scheduler = ReduceLROnPlateau(
                    self.optimizer,
                    mode='min',
                    factor=0.5,
                    patience=5
                )
        else:
            self.scheduler = None

        # Training state
        self.current_epoch = 0
        self.best_loss = float('inf')
        self.epochs_without_improvement = 0
        self.training_history: List[TrainingMetrics] = []

        # Data
        self.train_dataset = None
        self.val_dataset = None
        self.train_loader = None
        self.val_loader = None

        # Ensure checkpoint directory exists
        Path(self.config.checkpoint_dir).mkdir(parents=True, exist_ok=True)

    def generate_synthetic_data(self, seed: Optional[int] = None):
        """Generate synthetic training and validation data"""
        print("[Trainer] Generating synthetic training data...")

        generator = SyntheticDataGenerator(
            state_dim=self.config.state_dim,
            num_cells=self.config.num_cells,
            noise_level=0.1,
            seed=seed
        )

        # Training data
        self.train_dataset = generator.generate_dataset(
            num_exploit=self.config.synthetic_exploit,
            num_explore=self.config.synthetic_explore,
            num_repair=self.config.synthetic_repair,
            num_transition=self.config.synthetic_transition,
            num_deadlock=self.config.synthetic_deadlock,
            num_mixed=self.config.synthetic_mixed
        )

        # Validation data (smaller)
        self.val_dataset = generator.generate_dataset(
            num_exploit=self.config.synthetic_exploit // 5,
            num_explore=self.config.synthetic_explore // 5,
            num_repair=self.config.synthetic_repair // 5,
            num_transition=self.config.synthetic_transition // 5,
            num_deadlock=self.config.synthetic_deadlock // 5,
            num_mixed=self.config.synthetic_mixed // 5
        )

        # Create dataloaders
        self.train_loader = create_dataloader(
            self.train_dataset,
            batch_size=self.config.batch_size,
            shuffle=True
        )
        self.val_loader = create_dataloader(
            self.val_dataset,
            batch_size=self.config.batch_size,
            shuffle=False
        )

        train_stats = self.train_dataset.get_statistics()
        val_stats = self.val_dataset.get_statistics()
        print(f"    Training: {train_stats['num_trajectories']} trajectories, {train_stats['total_steps']} steps")
        print(f"    Validation: {val_stats['num_trajectories']} trajectories, {val_stats['total_steps']} steps")

    def train_epoch(self) -> TrainingMetrics:
        """Run one training epoch"""
        self.model.train()

        total_loss = 0.0
        total_action_loss = 0.0
        total_timing_loss = 0.0
        total_regime_loss = 0.0
        total_phase_lock_loss = 0.0
        total_trans_loss = 0.0

        correct_actions = 0
        correct_timing = 0
        correct_regimes = 0
        total_samples = 0

        for batch_idx, batch in enumerate(self.train_loader):
            # Move to device
            state_vectors = batch.state_vectors.to(self.device)
            sync_vectors = batch.sync_vectors.to(self.device)
            target_cells = batch.target_cells.to(self.device)
            target_timing = batch.target_timing.to(self.device)
            target_regimes = batch.target_regimes.to(self.device)
            transition_mask = batch.transition_mask.to(self.device)
            padding_mask = batch.padding_mask.to(self.device)

            # Forward pass
            self.optimizer.zero_grad()
            outputs = self.model(state_vectors, sync_vectors)

            # Flatten for loss computation (only valid positions)
            batch_size, seq_len = state_vectors.shape[:2]

            # Compute losses per sequence position
            losses_list = []
            prev_regime_probs = None
            prev_valid_count = 0

            for t in range(seq_len):
                valid_mask = padding_mask[:, t]
                if not valid_mask.any():
                    continue

                cell_logits_t = outputs['cell_logits'][:, t, :][valid_mask]
                timing_logits_t = outputs['timing_logits'][:, t, :][valid_mask]
                regime_logits_t = outputs['regime_logits'][:, t, :][valid_mask]

                target_cells_t = target_cells[:, t][valid_mask]
                target_timing_t = target_timing[:, t][valid_mask]
                target_regimes_t = target_regimes[:, t][valid_mask]
                sync_t = sync_vectors[:, t, :][valid_mask]
                trans_mask_t = transition_mask[:, t][valid_mask]

                # Only pass prev_regime_probs if batch sizes match
                curr_valid_count = valid_mask.sum().item()
                use_prev = prev_regime_probs if (
                    prev_regime_probs is not None and
                    prev_valid_count == curr_valid_count
                ) else None

                # Compute losses
                losses = self.criterion(
                    cell_logits_t,
                    timing_logits_t,
                    regime_logits_t,
                    sync_t,
                    target_cells_t,
                    target_timing_t,
                    target_regimes_t,
                    prev_regime_probs=use_prev,
                    transition_expected=trans_mask_t
                )
                losses_list.append(losses)

                # Track previous regime probs for transition loss
                prev_regime_probs = F.softmax(regime_logits_t.detach(), dim=-1)
                prev_valid_count = curr_valid_count

                # Track accuracy
                pred_cells = cell_logits_t.argmax(dim=-1)
                pred_timing = (timing_logits_t.squeeze(-1) > 0).float()
                pred_regimes = regime_logits_t.argmax(dim=-1)

                correct_actions += (pred_cells == target_cells_t).sum().item()
                correct_timing += (pred_timing == target_timing_t).sum().item()
                correct_regimes += (pred_regimes == target_regimes_t).sum().item()
                total_samples += valid_mask.sum().item()

            # Average losses across sequence
            if losses_list:
                avg_losses = {
                    key: torch.stack([l[key] for l in losses_list]).mean()
                    for key in losses_list[0].keys()
                }
                loss = avg_losses['total']

                # Backward pass
                loss.backward()

                # Gradient clipping
                if self.config.grad_clip > 0:
                    torch.nn.utils.clip_grad_norm_(
                        self.model.parameters(),
                        self.config.grad_clip
                    )

                self.optimizer.step()

                # Track losses
                total_loss += loss.item()
                total_action_loss += avg_losses['action'].item()
                total_timing_loss += avg_losses['timing'].item()
                total_regime_loss += avg_losses['regime'].item()
                total_phase_lock_loss += avg_losses['phase_lock'].item()
                total_trans_loss += avg_losses['transition'].item()

        num_batches = len(self.train_loader)
        metrics = TrainingMetrics(
            epoch=self.current_epoch,
            total_loss=total_loss / num_batches,
            action_loss=total_action_loss / num_batches,
            timing_loss=total_timing_loss / num_batches,
            regime_loss=total_regime_loss / num_batches,
            phase_lock_loss=total_phase_lock_loss / num_batches,
            transition_loss=total_trans_loss / num_batches,
            action_accuracy=correct_actions / max(total_samples, 1),
            timing_accuracy=correct_timing / max(total_samples, 1),
            regime_accuracy=correct_regimes / max(total_samples, 1),
            learning_rate=self.optimizer.param_groups[0]['lr']
        )

        return metrics

    def validate(self) -> TrainingMetrics:
        """Run validation"""
        self.model.eval()

        total_loss = 0.0
        total_action_loss = 0.0
        total_timing_loss = 0.0
        total_regime_loss = 0.0
        total_phase_lock_loss = 0.0
        total_trans_loss = 0.0

        correct_actions = 0
        correct_timing = 0
        correct_regimes = 0
        total_samples = 0

        with torch.no_grad():
            for batch in self.val_loader:
                # Move to device
                state_vectors = batch.state_vectors.to(self.device)
                sync_vectors = batch.sync_vectors.to(self.device)
                target_cells = batch.target_cells.to(self.device)
                target_timing = batch.target_timing.to(self.device)
                target_regimes = batch.target_regimes.to(self.device)
                transition_mask = batch.transition_mask.to(self.device)
                padding_mask = batch.padding_mask.to(self.device)

                # Forward pass
                outputs = self.model(state_vectors, sync_vectors)

                # Compute losses (simplified - just use last timestep)
                batch_size, seq_len = state_vectors.shape[:2]

                for t in range(seq_len):
                    valid_mask = padding_mask[:, t]
                    if not valid_mask.any():
                        continue

                    cell_logits_t = outputs['cell_logits'][:, t, :][valid_mask]
                    timing_logits_t = outputs['timing_logits'][:, t, :][valid_mask]
                    regime_logits_t = outputs['regime_logits'][:, t, :][valid_mask]

                    target_cells_t = target_cells[:, t][valid_mask]
                    target_timing_t = target_timing[:, t][valid_mask]
                    target_regimes_t = target_regimes[:, t][valid_mask]
                    sync_t = sync_vectors[:, t, :][valid_mask]

                    losses = self.criterion(
                        cell_logits_t,
                        timing_logits_t,
                        regime_logits_t,
                        sync_t,
                        target_cells_t,
                        target_timing_t,
                        target_regimes_t
                    )

                    total_loss += losses['total'].item()
                    total_action_loss += losses['action'].item()
                    total_timing_loss += losses['timing'].item()
                    total_regime_loss += losses['regime'].item()
                    total_phase_lock_loss += losses['phase_lock'].item()
                    total_trans_loss += losses['transition'].item()

                    # Track accuracy
                    pred_cells = cell_logits_t.argmax(dim=-1)
                    pred_timing = (timing_logits_t.squeeze(-1) > 0).float()
                    pred_regimes = regime_logits_t.argmax(dim=-1)

                    correct_actions += (pred_cells == target_cells_t).sum().item()
                    correct_timing += (pred_timing == target_timing_t).sum().item()
                    correct_regimes += (pred_regimes == target_regimes_t).sum().item()
                    total_samples += valid_mask.sum().item()

        num_batches = max(len(self.val_loader) * seq_len, 1)
        metrics = TrainingMetrics(
            epoch=self.current_epoch,
            total_loss=total_loss / num_batches,
            action_loss=total_action_loss / num_batches,
            timing_loss=total_timing_loss / num_batches,
            regime_loss=total_regime_loss / num_batches,
            phase_lock_loss=total_phase_lock_loss / num_batches,
            transition_loss=total_trans_loss / num_batches,
            action_accuracy=correct_actions / max(total_samples, 1),
            timing_accuracy=correct_timing / max(total_samples, 1),
            regime_accuracy=correct_regimes / max(total_samples, 1),
            learning_rate=self.optimizer.param_groups[0]['lr']
        )

        return metrics

    def train(
        self,
        num_epochs: Optional[int] = None,
        verbose: bool = True
    ) -> Dict[str, List[float]]:
        """
        Run full training loop

        Args:
            num_epochs: Number of epochs (uses config if None)
            verbose: Print progress

        Returns:
            Dictionary of metric histories
        """
        if num_epochs is None:
            num_epochs = self.config.num_epochs

        # Generate data if not already done
        if self.train_loader is None:
            self.generate_synthetic_data()

        if verbose:
            print(f"\n[Trainer] Starting training for {num_epochs} epochs")
            print(f"    Device: {self.device}")
            print(f"    Model parameters: {sum(p.numel() for p in self.model.parameters()):,}")
            print(f"    Loss weights: action={self.config.lambda_action}, timing={self.config.lambda_timing}, "
                  f"regime={self.config.lambda_regime}, lock={self.config.lambda_lock}, trans={self.config.lambda_trans}")
            print()

        history = {
            'total_loss': [],
            'action_loss': [],
            'timing_loss': [],
            'regime_loss': [],
            'phase_lock_loss': [],
            'transition_loss': [],
            'action_accuracy': [],
            'timing_accuracy': [],
            'regime_accuracy': [],
            'val_loss': [],
            'val_action_acc': [],
            'val_regime_acc': []
        }

        for epoch in range(num_epochs):
            self.current_epoch = epoch

            # Training
            train_metrics = self.train_epoch()

            # Validation
            val_metrics = self.validate()

            # Update scheduler
            if self.scheduler is not None:
                if isinstance(self.scheduler, ReduceLROnPlateau):
                    self.scheduler.step(val_metrics.total_loss)
                else:
                    self.scheduler.step()

            # Track history
            history['total_loss'].append(train_metrics.total_loss)
            history['action_loss'].append(train_metrics.action_loss)
            history['timing_loss'].append(train_metrics.timing_loss)
            history['regime_loss'].append(train_metrics.regime_loss)
            history['phase_lock_loss'].append(train_metrics.phase_lock_loss)
            history['transition_loss'].append(train_metrics.transition_loss)
            history['action_accuracy'].append(train_metrics.action_accuracy)
            history['timing_accuracy'].append(train_metrics.timing_accuracy)
            history['regime_accuracy'].append(train_metrics.regime_accuracy)
            history['val_loss'].append(val_metrics.total_loss)
            history['val_action_acc'].append(val_metrics.action_accuracy)
            history['val_regime_acc'].append(val_metrics.regime_accuracy)

            self.training_history.append(train_metrics)

            # Check for improvement
            if val_metrics.total_loss < self.best_loss:
                self.best_loss = val_metrics.total_loss
                self.epochs_without_improvement = 0
                self.save_checkpoint("best_model.pt")
            else:
                self.epochs_without_improvement += 1

            # Print progress
            if verbose and (epoch % 5 == 0 or epoch == num_epochs - 1):
                print(f"Epoch {epoch+1}/{num_epochs}")
                print(f"    Train Loss: {train_metrics.total_loss:.4f} "
                      f"(action={train_metrics.action_loss:.4f}, timing={train_metrics.timing_loss:.4f}, "
                      f"regime={train_metrics.regime_loss:.4f}, lock={train_metrics.phase_lock_loss:.4f})")
                print(f"    Train Acc: action={train_metrics.action_accuracy:.1%}, "
                      f"timing={train_metrics.timing_accuracy:.1%}, regime={train_metrics.regime_accuracy:.1%}")
                print(f"    Val Loss: {val_metrics.total_loss:.4f}")
                print(f"    Val Acc: action={val_metrics.action_accuracy:.1%}, regime={val_metrics.regime_accuracy:.1%}")
                print(f"    LR: {train_metrics.learning_rate:.6f}")
                print()

            # Checkpoint
            if (epoch + 1) % self.config.checkpoint_every == 0:
                self.save_checkpoint(f"checkpoint_epoch_{epoch+1}.pt")

            # Early stopping
            if self.epochs_without_improvement >= self.config.early_stopping_patience:
                if verbose:
                    print(f"[Trainer] Early stopping at epoch {epoch+1}")
                break

        if verbose:
            print(f"[Trainer] Training complete. Best val loss: {self.best_loss:.4f}")

        return history

    def save_checkpoint(self, filename: str):
        """Save model checkpoint"""
        path = Path(self.config.checkpoint_dir) / filename
        checkpoint = {
            'epoch': self.current_epoch,
            'model_state_dict': self.model.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
            'best_loss': self.best_loss,
            'config': self.config.to_dict(),
            'training_history': [m.to_dict() for m in self.training_history]
        }
        if self.scheduler is not None:
            checkpoint['scheduler_state_dict'] = self.scheduler.state_dict()

        torch.save(checkpoint, path)

    def load_checkpoint(self, filename: str):
        """Load model checkpoint"""
        path = Path(self.config.checkpoint_dir) / filename
        checkpoint = torch.load(path, map_location=self.device, weights_only=False)

        self.model.load_state_dict(checkpoint['model_state_dict'])
        self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
        self.current_epoch = checkpoint['epoch']
        self.best_loss = checkpoint['best_loss']

        if self.scheduler is not None and 'scheduler_state_dict' in checkpoint:
            self.scheduler.load_state_dict(checkpoint['scheduler_state_dict'])

    def get_model(self) -> nn.Module:
        """Get trained model"""
        return self.model


if __name__ == "__main__":
    print("=" * 70)
    print("TEMPORAL CTM TRAINER - Testing")
    print("=" * 70)
    print()

    # Create trainer with small config for testing
    print("[1] Creating trainer...")
    config = TrainingConfig(
        hidden_dim=64,
        state_dim=192,
        num_epochs=10,
        batch_size=8,
        synthetic_exploit=10,
        synthetic_explore=8,
        synthetic_repair=8,
        synthetic_transition=5,
        synthetic_deadlock=3,
        synthetic_mixed=6,
        checkpoint_every=5
    )

    trainer = TemporalCTMTrainer(config=config)
    print(f"    Device: {trainer.device}")
    print(f"    Model: {type(trainer.model).__name__}")
    print()

    # Generate data
    print("[2] Generating synthetic data...")
    trainer.generate_synthetic_data(seed=42)
    print()

    # Train
    print("[3] Training...")
    history = trainer.train(num_epochs=10, verbose=True)
    print()

    # Check results
    print("[4] Checking results...")
    print(f"    Final train loss: {history['total_loss'][-1]:.4f}")
    print(f"    Final val loss: {history['val_loss'][-1]:.4f}")
    print(f"    Final action accuracy: {history['action_accuracy'][-1]:.1%}")
    print(f"    Final regime accuracy: {history['regime_accuracy'][-1]:.1%}")
    print()

    print("=" * 70)
    print("TEMPORAL CTM TRAINER TESTS COMPLETE")
    print("=" * 70)
