"""
Automatic Matrix Migration (PHASE 7: P7.97)

Handles version-aware migration of weight matrices, gate vectors,
and configuration schemas when the brain is upgraded.

Features:
1. Version tracking for weight matrices
2. Automatic resizing when dimensions change
3. Safe migration with backup
4. Migration history logging
5. Rollback capability
"""

import os
import json
import time
import shutil
import logging
import numpy as np
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime

logger = logging.getLogger('brain.matrix_migration')

MIGRATION_VERSION = "1.0.0"


@dataclass
class MigrationRecord:
    """Record of a single migration operation."""
    migration_id: str
    timestamp: str
    source_version: str
    target_version: str
    component: str
    operation: str  # 'resize', 'reshape', 'add_column', 'schema_update'
    details: Dict[str, Any] = field(default_factory=dict)
    success: bool = True
    backup_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'migration_id': self.migration_id,
            'timestamp': self.timestamp,
            'source_version': self.source_version,
            'target_version': self.target_version,
            'component': self.component,
            'operation': self.operation,
            'details': self.details,
            'success': self.success,
            'backup_path': self.backup_path,
        }


class MatrixMigrator:
    """
    Manages automatic migration of brain weight matrices and configs.

    When brain dimensions change (e.g., new modalities added, gate vector
    resized), this migrator handles safe transformation of existing data.
    """

    # Known dimension specs per version
    DIMENSION_SPECS = {
        '0.9.0': {'modalities': 6, 'gates': 6, 'features': 64},
        '1.0.0': {'modalities': 10, 'gates': 10, 'features': 128},
    }

    def __init__(self, data_dir: str = "data", backup_dir: str = "data/migration_backups"):
        self.data_dir = data_dir
        self.backup_dir = backup_dir
        os.makedirs(backup_dir, exist_ok=True)
        self._history: List[MigrationRecord] = []
        self._migration_log_path = os.path.join(data_dir, "migration_history.json")
        self._load_history()

    def _load_history(self):
        """Load migration history from disk."""
        try:
            if os.path.exists(self._migration_log_path):
                with open(self._migration_log_path, 'r') as f:
                    data = json.load(f)
                    # Just store as dicts, don't convert back to dataclass
                    self._history = data.get('migrations', [])
        except Exception as e:
            logger.warning(f"Could not load migration history: {e}")
            self._history = []

    def _save_history(self):
        """Save migration history to disk."""
        try:
            os.makedirs(os.path.dirname(self._migration_log_path), exist_ok=True)
            with open(self._migration_log_path, 'w') as f:
                json.dump({'migrations': self._history, 'version': MIGRATION_VERSION}, f, indent=2)
        except Exception as e:
            logger.error(f"Could not save migration history: {e}")

    def _record_migration(self, record: MigrationRecord):
        """Record a migration in history."""
        self._history.append(record.to_dict())
        self._save_history()

    def resize_matrix(self, matrix: np.ndarray, target_shape: Tuple[int, ...],
                      fill_value: float = 0.0, fill_strategy: str = "zero") -> np.ndarray:
        """
        Resize a matrix to target shape, preserving existing data.

        Args:
            matrix: Original matrix
            target_shape: Desired shape
            fill_value: Value for new elements (if fill_strategy='constant')
            fill_strategy: 'zero', 'constant', 'mean', 'random'

        Returns:
            Resized matrix
        """
        if matrix.shape == target_shape:
            return matrix

        result = np.full(target_shape, fill_value)

        if fill_strategy == 'mean':
            result = np.full(target_shape, np.mean(matrix))
        elif fill_strategy == 'random':
            result = np.random.randn(*target_shape) * 0.01

        # Copy existing data into the new matrix
        slices = tuple(slice(0, min(s, t)) for s, t in zip(matrix.shape, target_shape))
        result[slices] = matrix[slices]

        return result

    def resize_gate_vector(self, gates: np.ndarray, target_size: int,
                           normalize: bool = True) -> np.ndarray:
        """
        Resize a gate vector (1D), preserving values and renormalizing.

        Args:
            gates: Original gate vector
            target_size: Desired length
            normalize: If True, renormalize to sum to 1.0

        Returns:
            Resized gate vector
        """
        if len(gates) == target_size:
            return gates

        if len(gates) < target_size:
            # Expand: add uniform probability for new gates
            extra = target_size - len(gates)
            uniform_share = 1.0 / target_size
            new_gates = np.concatenate([gates, np.full(extra, uniform_share)])
        else:
            # Shrink: take first target_size gates
            new_gates = gates[:target_size]

        if normalize and np.sum(new_gates) > 0:
            new_gates = new_gates / np.sum(new_gates)

        return new_gates

    def migrate_checkpoint(self, checkpoint_path: str, source_version: str,
                           target_version: str) -> Optional[str]:
        """
        Migrate a checkpoint file from one version to another.

        Args:
            checkpoint_path: Path to checkpoint JSON file
            source_version: Current version
            target_version: Target version

        Returns:
            Path to migrated checkpoint, or None on failure
        """
        if source_version == target_version:
            return checkpoint_path

        src_spec = self.DIMENSION_SPECS.get(source_version, {})
        tgt_spec = self.DIMENSION_SPECS.get(target_version, {})

        if not src_spec or not tgt_spec:
            logger.warning(f"Unknown version specs: {source_version} → {target_version}")
            return None

        # Backup original
        backup_path = os.path.join(
            self.backup_dir,
            f"backup_{os.path.basename(checkpoint_path)}_{int(time.time())}"
        )
        try:
            shutil.copy2(checkpoint_path, backup_path)
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            return None

        try:
            with open(checkpoint_path, 'r') as f:
                data = json.load(f)

            # Migrate weight matrices
            migrated = False

            # Gate vectors
            if 'brain_gates' in data:
                old_gates = np.array(data['brain_gates'])
                new_gates = self.resize_gate_vector(old_gates, tgt_spec['gates'])
                data['brain_gates'] = new_gates.tolist()
                migrated = True

            if 'routing_weights' in data:
                old_weights = np.array(data['routing_weights'])
                new_weights = self.resize_gate_vector(old_weights, tgt_spec['gates'])
                data['routing_weights'] = new_weights.tolist()
                migrated = True

            # Weight matrices
            for key in ['weight_matrix', 'attention_weights', 'layer_weights']:
                if key in data and isinstance(data[key], list):
                    old_matrix = np.array(data[key])
                    if old_matrix.ndim == 2:
                        # Determine target shape based on key
                        if 'attention' in key:
                            target_shape = (tgt_spec['modalities'], tgt_spec['modalities'])
                        else:
                            target_shape = (tgt_spec['features'], tgt_spec['gates'])
                        new_matrix = self.resize_matrix(old_matrix, target_shape, fill_strategy='mean')
                        data[key] = new_matrix.tolist()
                        migrated = True

            # Update version
            if 'metadata' not in data:
                data['metadata'] = {}
            data['metadata']['migrated_from'] = source_version
            data['metadata']['migrated_to'] = target_version
            data['metadata']['migration_timestamp'] = datetime.now().isoformat()

            if migrated:
                with open(checkpoint_path, 'w') as f:
                    json.dump(data, f, indent=2)

            # Record migration
            record = MigrationRecord(
                migration_id=f"mig_{int(time.time())}",
                timestamp=datetime.now().isoformat(),
                source_version=source_version,
                target_version=target_version,
                component=os.path.basename(checkpoint_path),
                operation='checkpoint_migration',
                details={'gates': f"{src_spec.get('gates')}→{tgt_spec.get('gates')}"},
                success=True,
                backup_path=backup_path,
            )
            self._record_migration(record)

            logger.info(f"Migrated checkpoint: {checkpoint_path} ({source_version}→{target_version})")
            return checkpoint_path

        except Exception as e:
            logger.error(f"Migration failed, restoring backup: {e}")
            try:
                shutil.copy2(backup_path, checkpoint_path)
            except Exception:
                pass

            record = MigrationRecord(
                migration_id=f"mig_{int(time.time())}",
                timestamp=datetime.now().isoformat(),
                source_version=source_version,
                target_version=target_version,
                component=os.path.basename(checkpoint_path),
                operation='checkpoint_migration',
                details={'error': str(e)},
                success=False,
                backup_path=backup_path,
            )
            self._record_migration(record)
            return None

    def migrate_config(self, config: Dict[str, Any], source_version: str,
                       target_version: str) -> Dict[str, Any]:
        """
        Migrate a configuration dictionary to a new version.

        Adds missing keys with default values, removes deprecated keys.
        """
        if source_version == target_version:
            return config

        migrated = dict(config)

        # Version-specific migrations
        if source_version < '1.0.0' and target_version >= '1.0.0':
            # Add cognitive loop config if missing
            if 'cognitive_loop' not in migrated:
                migrated['cognitive_loop'] = {
                    'enabled': False,
                    'max_iterations': 3,
                    'memory_bias_alpha': 0.25,
                    'attention_gate_strength': 0.3,
                }

            # Add Phase 6 module flags if missing
            phase6_defaults = {
                'enable_safety_layer': True,
                'enable_theory_of_mind': True,
                'enable_causal_reasoning': True,
                'enable_intrinsic_curiosity': True,
                'enable_temporal_patterns': True,
                'enable_autonomous_goals': True,
                'enable_multimodal_fusion': False,
                'enable_formal_verifier': False,
                'enable_thought_decoder': False,
            }
            if 'cognitive_loop' in migrated:
                for key, default_val in phase6_defaults.items():
                    if key not in migrated['cognitive_loop']:
                        migrated['cognitive_loop'][key] = default_val

        record = MigrationRecord(
            migration_id=f"mig_{int(time.time())}",
            timestamp=datetime.now().isoformat(),
            source_version=source_version,
            target_version=target_version,
            component='config',
            operation='schema_update',
            success=True,
        )
        self._record_migration(record)

        return migrated

    def get_migration_history(self) -> List[Dict]:
        """Get migration history."""
        return list(self._history)

    def get_statistics(self) -> Dict[str, Any]:
        """Get migration statistics."""
        total = len(self._history)
        successful = sum(1 for m in self._history if m.get('success', False))
        return {
            'total_migrations': total,
            'successful': successful,
            'failed': total - successful,
            'data_dir': self.data_dir,
            'backup_dir': self.backup_dir,
            'version': MIGRATION_VERSION,
        }
