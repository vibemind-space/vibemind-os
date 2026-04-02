"""
Training Infrastructure for Temporal CTM (Phase 2 + Phase 3 + Phase 4)

Phase 2 - Synthetic Pre-Training:
- TemporalDataset: PyTorch Dataset for temporal trajectories
- TemporalCTMLoss: Multi-loss function (action, timing, regime, phase-lock, transition)
- SyntheticDataGenerator: Generate training data for each regime
- TemporalCTMTrainer: Main training loop

Phase 3 - Fine-Tuning on Real Logs:
- RegimeInference: Infer regimes from tool patterns
- LogParser: Parse session logs to trajectories
- FineTuner: Fine-tune pre-trained model on real data

Phase 4 - Expert Phase Dynamics:
- DynamicsConsistencyLoss: Phase changes follow ΔφH(r) = -λ(ωqf δ(r) + ∇·(W×E))
- ExpertDiversityLoss: Prevent expert collapse
- ExpertSpecializationLoss: Stability when no events
- ExtendedTemporalCTMLoss: Combined Phase 2 + Phase 4 losses
"""

from .temporal_dataset import (
    Regime,
    TemporalStep,
    TemporalTrajectory,
    TemporalBatch,
    TemporalDataset,
    collate_temporal_batch,
    create_dataloader
)

from .phase_locking_loss import (
    PhaseLockTarget,
    REGIME_PHASE_LOCKS,
    PhaseLockingLoss,
    RegimeClassificationLoss,
    TransitionSmoothnessLoss,
    TemporalCTMLoss,
    PHASE4_AVAILABLE
)

# Phase 4: Expert Dynamics Losses (optional)
if PHASE4_AVAILABLE:
    from .phase_locking_loss import ExtendedTemporalCTMLoss
    from .expert_dynamics_loss import (
        DynamicsConsistencyLoss,
        ExpertDiversityLoss,
        ExpertSpecializationLoss,
        CombinedExpertDynamicsLoss,
        compute_expected_phase_change
    )

from .synthetic_data_generator import (
    SyncPattern,
    REGIME_SYNC_PATTERNS,
    SyntheticDataGenerator
)

from .temporal_ctm_trainer import (
    TrainingConfig,
    TrainingMetrics,
    TemporalCTMModel,
    TemporalCTMTrainer
)

# Phase 3: Fine-Tuning on Real Logs
from .regime_inference import (
    ToolCallInfo,
    SegmentFeatures,
    RegimeInference,
    classify_tool,
    infer_session_regimes
)

from .log_parser import (
    ToolCallRecord,
    SessionTrajectory,
    LogParser
)

from .fine_tune import (
    FineTuneConfig,
    FineTuner,
    fine_tune_from_logs
)

__all__ = [
    # Dataset
    'Regime',
    'TemporalStep',
    'TemporalTrajectory',
    'TemporalBatch',
    'TemporalDataset',
    'collate_temporal_batch',
    'create_dataloader',
    # Losses
    'PhaseLockTarget',
    'REGIME_PHASE_LOCKS',
    'PhaseLockingLoss',
    'RegimeClassificationLoss',
    'TransitionSmoothnessLoss',
    'TemporalCTMLoss',
    'PHASE4_AVAILABLE',
    # Data generation
    'SyncPattern',
    'REGIME_SYNC_PATTERNS',
    'SyntheticDataGenerator',
    # Trainer
    'TrainingConfig',
    'TrainingMetrics',
    'TemporalCTMModel',
    'TemporalCTMTrainer',
    # Phase 3: Regime inference
    'ToolCallInfo',
    'SegmentFeatures',
    'RegimeInference',
    'classify_tool',
    'infer_session_regimes',
    # Phase 3: Log parsing
    'ToolCallRecord',
    'SessionTrajectory',
    'LogParser',
    # Phase 3: Fine-tuning
    'FineTuneConfig',
    'FineTuner',
    'fine_tune_from_logs'
]

# Add Phase 4 exports if available
if PHASE4_AVAILABLE:
    __all__.extend([
        # Phase 4: Expert dynamics losses
        'ExtendedTemporalCTMLoss',
        'DynamicsConsistencyLoss',
        'ExpertDiversityLoss',
        'ExpertSpecializationLoss',
        'CombinedExpertDynamicsLoss',
        'compute_expected_phase_change'
    ])
