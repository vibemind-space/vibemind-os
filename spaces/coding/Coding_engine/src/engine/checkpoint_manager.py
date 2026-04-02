"""
Checkpoint Manager for Generation State Persistence

Saves and loads generation progress to enable resumption after:
- Rate limit errors
- System crashes
- Manual interruption

Checkpoint is saved to .generation_checkpoint.json in output directory.
"""

import json
import os
import tempfile
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class GenerationCheckpoint:
    """Represents a snapshot of generation progress."""

    # Job identification
    job_id: str
    started_at: str  # ISO format
    last_updated: str  # ISO format

    # Progress tracking
    current_batch: int = 0
    total_batches: int = 0
    current_iteration: int = 1
    total_iterations: int = 3

    # Completed work
    completed_slices: list[str] = field(default_factory=list)
    completed_files: list[str] = field(default_factory=list)

    # Error state
    last_error: Optional[str] = None
    rate_limit_hit_at: Optional[str] = None  # ISO format
    retry_count: int = 0

    # Metrics snapshot
    metrics: dict = field(default_factory=dict)

    # Requirements file path for validation
    requirements_file: Optional[str] = None
    output_dir: Optional[str] = None

    # Contract caching flag (for fast resume - skip Phase 1)
    contracts_cached: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "GenerationCheckpoint":
        """Create from dictionary."""
        return cls(**data)

    def mark_slice_completed(self, slice_id: str) -> None:
        """Mark a slice as completed."""
        if slice_id not in self.completed_slices:
            self.completed_slices.append(slice_id)
            self.last_updated = datetime.utcnow().isoformat() + "Z"

    def mark_file_completed(self, file_path: str) -> None:
        """Mark a file as successfully written."""
        if file_path not in self.completed_files:
            self.completed_files.append(file_path)

    def set_rate_limit_hit(self, error_msg: Optional[str] = None) -> None:
        """Record that rate limit was hit."""
        self.rate_limit_hit_at = datetime.utcnow().isoformat() + "Z"
        self.last_error = error_msg or "Rate limit exceeded"
        self.last_updated = datetime.utcnow().isoformat() + "Z"

    def increment_retry(self) -> None:
        """Increment retry count after rate limit recovery attempt."""
        self.retry_count += 1
        self.last_updated = datetime.utcnow().isoformat() + "Z"

    def clear_rate_limit(self) -> None:
        """Clear rate limit state after successful recovery."""
        self.rate_limit_hit_at = None
        self.last_error = None
        self.retry_count = 0
        self.last_updated = datetime.utcnow().isoformat() + "Z"

    def update_progress(
        self,
        batch: Optional[int] = None,
        iteration: Optional[int] = None,
        metrics: Optional[dict] = None,
    ) -> None:
        """Update progress tracking."""
        if batch is not None:
            self.current_batch = batch
        if iteration is not None:
            self.current_iteration = iteration
        if metrics is not None:
            self.metrics.update(metrics)
        self.last_updated = datetime.utcnow().isoformat() + "Z"

    def is_slice_completed(self, slice_id: str) -> bool:
        """Check if a slice has already been completed."""
        return slice_id in self.completed_slices

    @property
    def progress_percent(self) -> float:
        """Calculate overall progress percentage."""
        if self.total_batches == 0:
            return 0.0

        # Account for iterations
        total_work = self.total_batches * self.total_iterations
        completed_work = (
            (self.current_iteration - 1) * self.total_batches +
            self.current_batch
        )
        return (completed_work / total_work) * 100

    def __str__(self) -> str:
        return (
            f"Checkpoint[job={self.job_id}, "
            f"batch={self.current_batch}/{self.total_batches}, "
            f"iter={self.current_iteration}/{self.total_iterations}, "
            f"slices={len(self.completed_slices)}, "
            f"files={len(self.completed_files)}]"
        )


class CheckpointManager:
    """
    Manages checkpoint persistence for generation resumption.

    Usage:
        manager = CheckpointManager(output_dir)

        # Create new checkpoint
        checkpoint = manager.create(job_id, requirements_file)

        # Save after each batch
        checkpoint.mark_slice_completed("dom-general-001")
        await manager.save(checkpoint)

        # Resume from checkpoint
        existing = await manager.load()
        if existing:
            # Skip completed slices
            ...

        # Contract caching (skip Phase 1 on resume)
        await manager.save_contracts(contracts)
        cached = await manager.load_contracts()
    """

    CHECKPOINT_FILENAME = ".generation_checkpoint.json"
    CONTRACTS_CACHE_FILENAME = ".contracts_cache.json"

    def __init__(self, output_dir: Path | str):
        self.output_dir = Path(output_dir)
        self.checkpoint_file = self.output_dir / self.CHECKPOINT_FILENAME
        self.contracts_cache_file = self.output_dir / self.CONTRACTS_CACHE_FILENAME

    def create(
        self,
        job_id: str,
        requirements_file: Optional[str] = None,
        total_batches: int = 0,
        total_iterations: int = 3,
    ) -> GenerationCheckpoint:
        """Create a new checkpoint for a generation job."""
        now = datetime.utcnow().isoformat() + "Z"

        checkpoint = GenerationCheckpoint(
            job_id=job_id,
            started_at=now,
            last_updated=now,
            total_batches=total_batches,
            total_iterations=total_iterations,
            requirements_file=requirements_file,
            output_dir=str(self.output_dir),
        )

        logger.info(
            "checkpoint_created",
            job_id=job_id,
            output_dir=str(self.output_dir),
        )

        return checkpoint

    async def save(self, checkpoint: GenerationCheckpoint) -> None:
        """
        Save checkpoint to disk atomically.

        Uses atomic write (write to temp, then rename) to prevent
        corruption if interrupted during write.
        """
        checkpoint.last_updated = datetime.utcnow().isoformat() + "Z"

        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Atomic write: write to temp file, then rename
        temp_fd, temp_path = tempfile.mkstemp(
            suffix=".json",
            prefix="checkpoint_",
            dir=self.output_dir,
        )

        try:
            with os.fdopen(temp_fd, 'w') as f:
                json.dump(checkpoint.to_dict(), f, indent=2)

            # Atomic rename (on POSIX) / replace (on Windows)
            temp_path_obj = Path(temp_path)
            temp_path_obj.replace(self.checkpoint_file)

            logger.debug(
                "checkpoint_saved",
                job_id=checkpoint.job_id,
                batch=checkpoint.current_batch,
                slices_completed=len(checkpoint.completed_slices),
                path=str(self.checkpoint_file),
            )

        except Exception as e:
            # Clean up temp file on error
            try:
                os.unlink(temp_path)
            except OSError:
                pass

            logger.error(
                "checkpoint_save_failed",
                error=str(e),
                path=str(self.checkpoint_file),
            )
            raise

    async def load(self) -> Optional[GenerationCheckpoint]:
        """
        Load existing checkpoint if present.

        Returns None if no checkpoint exists or if it's corrupted.
        """
        if not self.checkpoint_file.exists():
            logger.debug(
                "no_checkpoint_found",
                path=str(self.checkpoint_file),
            )
            return None

        try:
            with open(self.checkpoint_file, 'r') as f:
                data = json.load(f)

            checkpoint = GenerationCheckpoint.from_dict(data)

            logger.info(
                "checkpoint_loaded",
                job_id=checkpoint.job_id,
                progress=f"{checkpoint.progress_percent:.1f}%",
                slices_completed=len(checkpoint.completed_slices),
                batch=f"{checkpoint.current_batch}/{checkpoint.total_batches}",
                iteration=f"{checkpoint.current_iteration}/{checkpoint.total_iterations}",
            )

            return checkpoint

        except json.JSONDecodeError as e:
            logger.warning(
                "checkpoint_corrupted",
                error=str(e),
                path=str(self.checkpoint_file),
            )
            return None
        except Exception as e:
            logger.error(
                "checkpoint_load_failed",
                error=str(e),
                path=str(self.checkpoint_file),
            )
            return None

    async def clear(self) -> None:
        """Remove checkpoint after successful completion."""
        if self.checkpoint_file.exists():
            try:
                self.checkpoint_file.unlink()
                logger.info(
                    "checkpoint_cleared",
                    path=str(self.checkpoint_file),
                )
            except OSError as e:
                logger.warning(
                    "checkpoint_clear_failed",
                    error=str(e),
                    path=str(self.checkpoint_file),
                )

    def exists(self) -> bool:
        """Check if a checkpoint exists."""
        return self.checkpoint_file.exists()

    async def validate(
        self,
        checkpoint: GenerationCheckpoint,
        requirements_file: Optional[str] = None,
    ) -> bool:
        """
        Validate checkpoint is still valid for resumption.

        Checks:
        - Output directory matches
        - Requirements file matches (if provided)
        - Files in completed_files still exist
        """
        # Check output directory
        if checkpoint.output_dir and checkpoint.output_dir != str(self.output_dir):
            logger.warning(
                "checkpoint_output_dir_mismatch",
                checkpoint_dir=checkpoint.output_dir,
                current_dir=str(self.output_dir),
            )
            return False

        # Check requirements file
        if requirements_file and checkpoint.requirements_file:
            if checkpoint.requirements_file != requirements_file:
                logger.warning(
                    "checkpoint_requirements_mismatch",
                    checkpoint_file=checkpoint.requirements_file,
                    current_file=requirements_file,
                )
                return False

        # Verify some completed files still exist
        if checkpoint.completed_files:
            missing_count = 0
            sample_size = min(10, len(checkpoint.completed_files))

            for file_path in checkpoint.completed_files[:sample_size]:
                full_path = self.output_dir / file_path
                if not full_path.exists():
                    missing_count += 1

            if missing_count > sample_size // 2:
                logger.warning(
                    "checkpoint_files_missing",
                    missing=missing_count,
                    sample_size=sample_size,
                )
                return False

        logger.info(
            "checkpoint_validated",
            job_id=checkpoint.job_id,
        )
        return True

    # =========================================================================
    # Contract Caching Methods (Fast Resume - Skip Phase 1)
    # =========================================================================

    async def save_contracts(self, contracts) -> None:
        """
        Save contracts to cache file for fast resume.

        This allows skipping Phase 1 (Architect) on resume,
        saving ~2-5 minutes of contract regeneration.

        Args:
            contracts: InterfaceContracts object to cache
        """
        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Atomic write: write to temp file, then rename
        temp_fd, temp_path = tempfile.mkstemp(
            suffix=".json",
            prefix="contracts_",
            dir=self.output_dir,
        )

        try:
            with os.fdopen(temp_fd, 'w') as f:
                # Use contracts.to_dict() for serialization
                json.dump(contracts.to_dict(), f, indent=2)

            # Atomic rename
            temp_path_obj = Path(temp_path)
            temp_path_obj.replace(self.contracts_cache_file)

            logger.info(
                "contracts_cached",
                path=str(self.contracts_cache_file),
                types=len(contracts.types),
                endpoints=len(contracts.endpoints),
                components=len(contracts.components),
                services=len(contracts.services),
            )

            # Update checkpoint to mark contracts as cached (for fast resume)
            existing_checkpoint = await self.load()
            if existing_checkpoint:
                existing_checkpoint.contracts_cached = True
                await self.save(existing_checkpoint)
                logger.debug(
                    "checkpoint_contracts_cached_flag_set",
                    job_id=existing_checkpoint.job_id,
                )

        except Exception as e:
            # Clean up temp file on error
            try:
                os.unlink(temp_path)
            except OSError:
                pass

            logger.error(
                "contracts_cache_save_failed",
                error=str(e),
                path=str(self.contracts_cache_file),
            )
            raise

    async def load_contracts(self):
        """
        Load cached contracts if present and valid.

        Returns:
            InterfaceContracts if cache exists and is valid, None otherwise
        """
        if not self.contracts_cache_file.exists():
            logger.debug(
                "no_contracts_cache_found",
                path=str(self.contracts_cache_file),
            )
            return None

        try:
            with open(self.contracts_cache_file, 'r') as f:
                data = json.load(f)

            # Lazy import to avoid circular dependency
            from src.engine.contracts import InterfaceContracts

            contracts = InterfaceContracts.from_dict(data)

            logger.info(
                "contracts_cache_loaded",
                path=str(self.contracts_cache_file),
                types=len(contracts.types),
                endpoints=len(contracts.endpoints),
                components=len(contracts.components),
                services=len(contracts.services),
            )

            return contracts

        except json.JSONDecodeError as e:
            logger.warning(
                "contracts_cache_corrupted",
                error=str(e),
                path=str(self.contracts_cache_file),
            )
            return None
        except Exception as e:
            logger.error(
                "contracts_cache_load_failed",
                error=str(e),
                path=str(self.contracts_cache_file),
            )
            return None

    def contracts_cache_exists(self) -> bool:
        """Check if a contracts cache exists."""
        return self.contracts_cache_file.exists()

    async def clear_contracts_cache(self) -> None:
        """Remove contracts cache."""
        if self.contracts_cache_file.exists():
            try:
                self.contracts_cache_file.unlink()
                logger.info(
                    "contracts_cache_cleared",
                    path=str(self.contracts_cache_file),
                )
            except OSError as e:
                logger.warning(
                    "contracts_cache_clear_failed",
                    error=str(e),
                    path=str(self.contracts_cache_file),
                )
