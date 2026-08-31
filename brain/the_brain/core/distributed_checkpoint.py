"""
Distributed Checkpoint Manager

Extends oscillator checkpointing with distributed storage capabilities:
- Save checkpoints to multiple locations (local + remote)
- Checkpoint versioning with semantic versioning
- Checkpoint diff/merge for collaborative training
- Cloud storage integration (S3-compatible API)

Usage:
    from core.distributed_checkpoint import DistributedCheckpointManager

    manager = DistributedCheckpointManager(
        local_dir="data/checkpoints",
        remote_endpoints=["s3://bucket/checkpoints"]
    )

    # Save with version
    manager.save_versioned(router, "model", version="1.2.0")

    # Compare checkpoints
    diff = manager.diff_checkpoints("model_1.1.0", "model_1.2.0")

    # Merge learning from multiple checkpoints
    merged = manager.merge_checkpoints(["model_a", "model_b"])
"""

import os
import json
import hashlib
import shutil
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from pathlib import Path
from enum import Enum
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import base checkpoint
try:
    from .oscillator_checkpoint import OscillatorCheckpoint, CheckpointManager
except ImportError:
    from oscillator_checkpoint import OscillatorCheckpoint, CheckpointManager

# Import logger
try:
    from .brain_logger import get_logger
    logger = get_logger('checkpoint')
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

# Import exceptions
try:
    from .exceptions import CheckpointError, CheckpointNotFoundError
except ImportError:
    class CheckpointError(Exception):
        pass
    class CheckpointNotFoundError(Exception):
        pass


# =============================================================================
# VERSION MANAGEMENT
# =============================================================================

@dataclass
class SemanticVersion:
    """Semantic versioning for checkpoints"""
    major: int = 1
    minor: int = 0
    patch: int = 0
    prerelease: Optional[str] = None  # e.g., "alpha", "beta.1"

    @classmethod
    def parse(cls, version_str: str) -> 'SemanticVersion':
        """Parse version string like '1.2.3' or '1.2.3-beta.1'"""
        prerelease = None
        if '-' in version_str:
            version_str, prerelease = version_str.split('-', 1)

        parts = version_str.split('.')
        major = int(parts[0]) if len(parts) > 0 else 1
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2]) if len(parts) > 2 else 0

        return cls(major=major, minor=minor, patch=patch, prerelease=prerelease)

    def __str__(self) -> str:
        version = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            version += f"-{self.prerelease}"
        return version

    def __lt__(self, other: 'SemanticVersion') -> bool:
        if (self.major, self.minor, self.patch) != (other.major, other.minor, other.patch):
            return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)
        # Prerelease versions are less than release versions
        if self.prerelease and not other.prerelease:
            return True
        if not self.prerelease and other.prerelease:
            return False
        return (self.prerelease or "") < (other.prerelease or "")

    def increment_major(self) -> 'SemanticVersion':
        return SemanticVersion(self.major + 1, 0, 0)

    def increment_minor(self) -> 'SemanticVersion':
        return SemanticVersion(self.major, self.minor + 1, 0)

    def increment_patch(self) -> 'SemanticVersion':
        return SemanticVersion(self.major, self.minor, self.patch + 1)


class StorageBackend(Enum):
    """Supported storage backends"""
    LOCAL = "local"
    S3 = "s3"
    HTTP = "http"
    SFTP = "sftp"


# =============================================================================
# CHECKPOINT DIFF/MERGE
# =============================================================================

@dataclass
class CheckpointDiff:
    """Represents differences between two checkpoints"""
    source_name: str
    target_name: str
    source_version: str
    target_version: str

    # Oscillator state differences
    oscillator_diff: Dict[str, Dict[str, float]] = field(default_factory=dict)
    # {'A': {'amplitude': +0.15}, 'B': {'phase': -0.2}, ...}

    # Token mapping changes
    tokens_added: Dict[str, str] = field(default_factory=dict)
    tokens_removed: List[str] = field(default_factory=list)
    tokens_changed: Dict[str, Tuple[str, str]] = field(default_factory=dict)
    # {'token': ('old_class', 'new_class')}

    # Statistics changes
    statistics_diff: Dict[str, Any] = field(default_factory=dict)

    # Summary
    total_changes: int = 0
    change_magnitude: float = 0.0  # Overall change score

    def to_dict(self) -> Dict:
        return {
            'source': {'name': self.source_name, 'version': self.source_version},
            'target': {'name': self.target_name, 'version': self.target_version},
            'oscillator_diff': self.oscillator_diff,
            'tokens_added': len(self.tokens_added),
            'tokens_removed': len(self.tokens_removed),
            'tokens_changed': len(self.tokens_changed),
            'total_changes': self.total_changes,
            'change_magnitude': self.change_magnitude
        }


@dataclass
class MergedCheckpoint:
    """Result of merging multiple checkpoints"""
    source_checkpoints: List[str]
    merge_strategy: str
    merged_at: str

    # Merged oscillator state (weighted average)
    oscillator_state: Dict[str, Dict[str, float]] = field(default_factory=dict)

    # Merged token mappings (majority vote or union)
    token_mappings: Dict[str, str] = field(default_factory=dict)

    # Merge statistics
    conflicts_resolved: int = 0
    merge_quality: float = 0.0  # 0-1, how consistent were the inputs


# =============================================================================
# REMOTE STORAGE ADAPTERS
# =============================================================================

class StorageAdapter:
    """Base class for storage backends"""

    def upload(self, local_path: str, remote_path: str) -> bool:
        raise NotImplementedError

    def download(self, remote_path: str, local_path: str) -> bool:
        raise NotImplementedError

    def list(self, prefix: str = "") -> List[str]:
        raise NotImplementedError

    def delete(self, remote_path: str) -> bool:
        raise NotImplementedError

    def exists(self, remote_path: str) -> bool:
        raise NotImplementedError


class S3StorageAdapter(StorageAdapter):
    """S3-compatible storage adapter"""

    def __init__(
        self,
        bucket: str,
        prefix: str = "",
        endpoint_url: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        region: str = "us-east-1"
    ):
        self.bucket = bucket
        self.prefix = prefix
        self.endpoint_url = endpoint_url
        self.region = region

        # Try to import boto3
        try:
            import boto3
            self._s3_available = True

            session_kwargs = {}
            if access_key and secret_key:
                session_kwargs['aws_access_key_id'] = access_key
                session_kwargs['aws_secret_access_key'] = secret_key

            client_kwargs = {'region_name': region}
            if endpoint_url:
                client_kwargs['endpoint_url'] = endpoint_url

            self.client = boto3.client('s3', **session_kwargs, **client_kwargs)

        except ImportError:
            self._s3_available = False
            self.client = None
            logger.warning("boto3 not available - S3 storage disabled")

    def _full_key(self, path: str) -> str:
        """Get full S3 key with prefix"""
        if self.prefix:
            return f"{self.prefix.rstrip('/')}/{path}"
        return path

    def upload(self, local_path: str, remote_path: str) -> bool:
        if not self._s3_available:
            return False

        try:
            key = self._full_key(remote_path)
            self.client.upload_file(local_path, self.bucket, key)
            logger.info(f"Uploaded to s3://{self.bucket}/{key}")
            return True
        except Exception as e:
            logger.error(f"S3 upload failed: {e}")
            return False

    def download(self, remote_path: str, local_path: str) -> bool:
        if not self._s3_available:
            return False

        try:
            key = self._full_key(remote_path)
            self.client.download_file(self.bucket, key, local_path)
            logger.info(f"Downloaded from s3://{self.bucket}/{key}")
            return True
        except Exception as e:
            logger.error(f"S3 download failed: {e}")
            return False

    def list(self, prefix: str = "") -> List[str]:
        if not self._s3_available:
            return []

        try:
            full_prefix = self._full_key(prefix)
            response = self.client.list_objects_v2(
                Bucket=self.bucket,
                Prefix=full_prefix
            )

            keys = []
            for obj in response.get('Contents', []):
                key = obj['Key']
                if self.prefix:
                    key = key[len(self.prefix) + 1:]  # Remove prefix
                keys.append(key)

            return keys
        except Exception as e:
            logger.error(f"S3 list failed: {e}")
            return []

    def delete(self, remote_path: str) -> bool:
        if not self._s3_available:
            return False

        try:
            key = self._full_key(remote_path)
            self.client.delete_object(Bucket=self.bucket, Key=key)
            return True
        except Exception as e:
            logger.error(f"S3 delete failed: {e}")
            return False

    def exists(self, remote_path: str) -> bool:
        if not self._s3_available:
            return False

        try:
            key = self._full_key(remote_path)
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False


class HTTPStorageAdapter(StorageAdapter):
    """HTTP-based storage adapter for REST APIs"""

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None
    ):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.headers = headers or {}

        if api_key:
            self.headers['Authorization'] = f'Bearer {api_key}'

        try:
            import requests
            self._http_available = True
            self.requests = requests
        except ImportError:
            self._http_available = False
            logger.warning("requests not available - HTTP storage disabled")

    def upload(self, local_path: str, remote_path: str) -> bool:
        if not self._http_available:
            return False

        try:
            url = f"{self.base_url}/{remote_path}"
            with open(local_path, 'rb') as f:
                response = self.requests.put(url, data=f, headers=self.headers)
            return response.status_code in (200, 201)
        except Exception as e:
            logger.error(f"HTTP upload failed: {e}")
            return False

    def download(self, remote_path: str, local_path: str) -> bool:
        if not self._http_available:
            return False

        try:
            url = f"{self.base_url}/{remote_path}"
            response = self.requests.get(url, headers=self.headers)
            if response.status_code == 200:
                with open(local_path, 'wb') as f:
                    f.write(response.content)
                return True
            return False
        except Exception as e:
            logger.error(f"HTTP download failed: {e}")
            return False

    def list(self, prefix: str = "") -> List[str]:
        if not self._http_available:
            return []

        try:
            url = f"{self.base_url}/_list"
            if prefix:
                url += f"?prefix={prefix}"
            response = self.requests.get(url, headers=self.headers)
            if response.status_code == 200:
                return response.json().get('files', [])
            return []
        except Exception:
            return []

    def delete(self, remote_path: str) -> bool:
        if not self._http_available:
            return False

        try:
            url = f"{self.base_url}/{remote_path}"
            response = self.requests.delete(url, headers=self.headers)
            return response.status_code in (200, 204)
        except Exception:
            return False

    def exists(self, remote_path: str) -> bool:
        if not self._http_available:
            return False

        try:
            url = f"{self.base_url}/{remote_path}"
            response = self.requests.head(url, headers=self.headers)
            return response.status_code == 200
        except Exception:
            return False


# =============================================================================
# DISTRIBUTED CHECKPOINT MANAGER
# =============================================================================

class DistributedCheckpointManager:
    """
    Manages distributed checkpoint storage with versioning.

    Features:
    - Multi-location storage (local + multiple remotes)
    - Semantic versioning for checkpoints
    - Diff and merge operations for collaborative training
    - Automatic sync between locations
    - Conflict resolution
    """

    def __init__(
        self,
        local_dir: str = "data/distributed_checkpoints",
        remote_adapters: Optional[Dict[str, StorageAdapter]] = None,
        max_versions: int = 10,
        sync_on_save: bool = True,
        enable_compression: bool = True
    ):
        """
        Initialize DistributedCheckpointManager.

        Args:
            local_dir: Local directory for checkpoints
            remote_adapters: Dict of name -> StorageAdapter for remote storage
            max_versions: Maximum versions to keep per checkpoint
            sync_on_save: Automatically sync to remotes on save
            enable_compression: Enable checkpoint compression
        """
        self.local_dir = Path(local_dir)
        self.local_dir.mkdir(parents=True, exist_ok=True)

        self.remote_adapters = remote_adapters or {}
        self.max_versions = max_versions
        self.sync_on_save = sync_on_save
        self.enable_compression = enable_compression

        # Version tracking
        self.version_index: Dict[str, List[SemanticVersion]] = {}
        self._load_version_index()

        # Thread pool for async sync
        self.executor = ThreadPoolExecutor(max_workers=4)

        # Lock for thread safety
        self._lock = threading.Lock()

        logger.info(f"DistributedCheckpointManager initialized at {self.local_dir}")
        logger.info(f"Remote adapters: {list(self.remote_adapters.keys())}")

    def _load_version_index(self):
        """Load version index from local storage"""
        index_path = self.local_dir / "_version_index.json"
        if index_path.exists():
            try:
                with open(index_path, 'r') as f:
                    data = json.load(f)
                for name, versions in data.items():
                    self.version_index[name] = [
                        SemanticVersion.parse(v) for v in versions
                    ]
            except Exception as e:
                logger.warning(f"Failed to load version index: {e}")

    def _save_version_index(self):
        """Save version index to local storage"""
        index_path = self.local_dir / "_version_index.json"
        data = {
            name: [str(v) for v in versions]
            for name, versions in self.version_index.items()
        }
        with open(index_path, 'w') as f:
            json.dump(data, f, indent=2)

    def _get_checkpoint_path(self, name: str, version: SemanticVersion) -> Path:
        """Get local path for a versioned checkpoint"""
        return self.local_dir / f"{name}_v{version}.json"

    def save_versioned(
        self,
        router: Any,
        name: str,
        version: Optional[str] = None,
        auto_increment: str = "patch",
        metadata: Optional[Dict] = None
    ) -> Tuple[str, SemanticVersion]:
        """
        Save checkpoint with semantic versioning.

        Args:
            router: Layer4TemporalRouter instance
            name: Base checkpoint name
            version: Explicit version string (e.g., "1.2.3")
            auto_increment: Auto-increment type if no version ("major", "minor", "patch")
            metadata: Additional metadata to store

        Returns:
            Tuple of (checkpoint_path, version)
        """
        with self._lock:
            # Determine version
            if version:
                sem_version = SemanticVersion.parse(version)
            else:
                # Auto-increment from latest
                if name in self.version_index and self.version_index[name]:
                    latest = max(self.version_index[name])
                    if auto_increment == "major":
                        sem_version = latest.increment_major()
                    elif auto_increment == "minor":
                        sem_version = latest.increment_minor()
                    else:
                        sem_version = latest.increment_patch()
                else:
                    sem_version = SemanticVersion(1, 0, 0)

            # Create base checkpoint using parent CheckpointManager logic
            base_manager = CheckpointManager(
                checkpoint_dir=str(self.local_dir),
                max_checkpoints=self.max_versions * 10  # Will manage ourselves
            )

            checkpoint_name = f"{name}_v{sem_version}"

            # Save locally first
            local_path = base_manager.save_checkpoint(router, checkpoint_name)

            # Add version metadata
            self._add_version_metadata(local_path, sem_version, metadata)

            # Update version index
            if name not in self.version_index:
                self.version_index[name] = []
            self.version_index[name].append(sem_version)
            self.version_index[name].sort()

            # Cleanup old versions
            self._cleanup_old_versions(name)

            # Save index
            self._save_version_index()

            # Sync to remotes
            if self.sync_on_save and self.remote_adapters:
                self._sync_to_remotes(checkpoint_name)

            logger.info(f"Saved versioned checkpoint: {name} v{sem_version}")
            return local_path, sem_version

    def _add_version_metadata(
        self,
        path: str,
        version: SemanticVersion,
        metadata: Optional[Dict]
    ):
        """Add version metadata to checkpoint file"""
        try:
            with open(path, 'r') as f:
                data = json.load(f)

            data['version_info'] = {
                'semantic_version': str(version),
                'major': version.major,
                'minor': version.minor,
                'patch': version.patch,
                'prerelease': version.prerelease,
                'saved_at': datetime.now().isoformat()
            }

            if metadata:
                data['custom_metadata'] = metadata

            # Add content hash for integrity
            content = json.dumps(data.get('oscillator_state', {}), sort_keys=True)
            data['content_hash'] = hashlib.sha256(content.encode()).hexdigest()[:16]

            with open(path, 'w') as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            logger.warning(f"Failed to add version metadata: {e}")

    def _cleanup_old_versions(self, name: str):
        """Remove old versions beyond max_versions"""
        if name not in self.version_index:
            return

        versions = self.version_index[name]
        if len(versions) <= self.max_versions:
            return

        # Remove oldest versions
        to_remove = versions[:-self.max_versions]
        for version in to_remove:
            path = self._get_checkpoint_path(name, version)
            if path.exists():
                try:
                    path.unlink()
                    logger.debug(f"Removed old version: {name} v{version}")
                except Exception:
                    pass

        self.version_index[name] = versions[-self.max_versions:]

    def _sync_to_remotes(self, checkpoint_name: str):
        """Sync checkpoint to all remote adapters"""
        local_path = self.local_dir / f"{checkpoint_name}.json"
        if not local_path.exists():
            return

        futures = []
        for adapter_name, adapter in self.remote_adapters.items():
            future = self.executor.submit(
                adapter.upload,
                str(local_path),
                f"{checkpoint_name}.json"
            )
            futures.append((adapter_name, future))

        # Collect results
        for adapter_name, future in futures:
            try:
                success = future.result(timeout=60)
                if success:
                    logger.debug(f"Synced to {adapter_name}: {checkpoint_name}")
                else:
                    logger.warning(f"Sync failed for {adapter_name}: {checkpoint_name}")
            except Exception as e:
                logger.error(f"Sync error for {adapter_name}: {e}")

    def load_versioned(
        self,
        name: str,
        version: Optional[str] = None
    ) -> Optional[OscillatorCheckpoint]:
        """
        Load a versioned checkpoint.

        Args:
            name: Checkpoint name
            version: Specific version to load (latest if None)

        Returns:
            OscillatorCheckpoint or None
        """
        if version:
            sem_version = SemanticVersion.parse(version)
        else:
            # Get latest version
            if name not in self.version_index or not self.version_index[name]:
                logger.warning(f"No versions found for: {name}")
                return None
            sem_version = max(self.version_index[name])

        checkpoint_name = f"{name}_v{sem_version}"
        path = self.local_dir / f"{checkpoint_name}.json"

        # Try local first
        if path.exists():
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                return OscillatorCheckpoint.from_dict(data)
            except Exception as e:
                logger.error(f"Failed to load local checkpoint: {e}")

        # Try remotes
        for adapter_name, adapter in self.remote_adapters.items():
            temp_path = self.local_dir / f"_temp_{checkpoint_name}.json"
            if adapter.download(f"{checkpoint_name}.json", str(temp_path)):
                try:
                    with open(temp_path, 'r') as f:
                        data = json.load(f)
                    # Cache locally
                    shutil.move(str(temp_path), str(path))
                    logger.info(f"Downloaded from {adapter_name}: {checkpoint_name}")
                    return OscillatorCheckpoint.from_dict(data)
                except Exception as e:
                    logger.error(f"Failed to parse remote checkpoint: {e}")
                finally:
                    if temp_path.exists():
                        temp_path.unlink()

        return None

    def diff_checkpoints(
        self,
        source_name: str,
        target_name: str,
        source_version: Optional[str] = None,
        target_version: Optional[str] = None
    ) -> Optional[CheckpointDiff]:
        """
        Compute differences between two checkpoints.

        Args:
            source_name: Source checkpoint name
            target_name: Target checkpoint name
            source_version: Source version (latest if None)
            target_version: Target version (latest if None)

        Returns:
            CheckpointDiff or None if checkpoints not found
        """
        source = self.load_versioned(source_name, source_version)
        target = self.load_versioned(target_name, target_version)

        if not source or not target:
            logger.error("Could not load checkpoints for diff")
            return None

        # Get versions
        src_ver = source_version or str(max(self.version_index.get(source_name, [SemanticVersion()])))
        tgt_ver = target_version or str(max(self.version_index.get(target_name, [SemanticVersion()])))

        diff = CheckpointDiff(
            source_name=source_name,
            target_name=target_name,
            source_version=src_ver,
            target_version=tgt_ver
        )

        # Compare oscillator states
        for channel in ['A', 'B', 'C']:
            src_state = source.oscillator_state.get(channel, {})
            tgt_state = target.oscillator_state.get(channel, {})

            channel_diff = {}
            for key in ['amplitude', 'phase']:
                src_val = src_state.get(key, 0.0)
                tgt_val = tgt_state.get(key, 0.0)
                if abs(src_val - tgt_val) > 0.001:
                    channel_diff[key] = tgt_val - src_val

            if channel_diff:
                diff.oscillator_diff[channel] = channel_diff

        # Compare token mappings
        src_tokens = set(source.token_mappings.keys())
        tgt_tokens = set(target.token_mappings.keys())

        diff.tokens_added = {
            t: target.token_mappings[t]
            for t in (tgt_tokens - src_tokens)
        }
        diff.tokens_removed = list(src_tokens - tgt_tokens)

        for token in src_tokens & tgt_tokens:
            src_class = source.token_mappings[token]
            tgt_class = target.token_mappings[token]
            if src_class != tgt_class:
                diff.tokens_changed[token] = (src_class, tgt_class)

        # Calculate total changes and magnitude
        diff.total_changes = (
            len(diff.tokens_added) +
            len(diff.tokens_removed) +
            len(diff.tokens_changed) +
            sum(len(d) for d in diff.oscillator_diff.values())
        )

        # Calculate change magnitude (0-1 scale)
        if diff.total_changes > 0:
            osc_magnitude = sum(
                sum(abs(v) for v in d.values())
                for d in diff.oscillator_diff.values()
            )
            token_magnitude = (
                len(diff.tokens_added) * 0.1 +
                len(diff.tokens_removed) * 0.1 +
                len(diff.tokens_changed) * 0.2
            )
            diff.change_magnitude = min(1.0, (osc_magnitude + token_magnitude) / 2)

        logger.info(f"Diff computed: {diff.total_changes} changes, magnitude={diff.change_magnitude:.3f}")
        return diff

    def merge_checkpoints(
        self,
        checkpoint_names: List[str],
        versions: Optional[List[str]] = None,
        strategy: str = "weighted_average",
        weights: Optional[List[float]] = None,
        output_name: str = "merged"
    ) -> Optional[Tuple[str, SemanticVersion]]:
        """
        Merge multiple checkpoints into one.

        Args:
            checkpoint_names: List of checkpoint names to merge
            versions: List of versions (latest for each if None)
            strategy: Merge strategy ("weighted_average", "majority_vote", "latest_wins")
            weights: Weights for each checkpoint (equal if None)
            output_name: Name for merged checkpoint

        Returns:
            Tuple of (path, version) for merged checkpoint
        """
        if len(checkpoint_names) < 2:
            logger.error("Need at least 2 checkpoints to merge")
            return None

        # Load all checkpoints
        checkpoints = []
        for i, name in enumerate(checkpoint_names):
            version = versions[i] if versions and i < len(versions) else None
            cp = self.load_versioned(name, version)
            if cp:
                checkpoints.append(cp)
            else:
                logger.warning(f"Could not load checkpoint: {name}")

        if len(checkpoints) < 2:
            logger.error("Not enough valid checkpoints to merge")
            return None

        # Set up weights
        if weights is None:
            weights = [1.0 / len(checkpoints)] * len(checkpoints)
        else:
            total = sum(weights)
            weights = [w / total for w in weights]

        # Merge oscillator states
        merged_state = {}
        for channel in ['A', 'B', 'C']:
            merged_state[channel] = {}
            for key in ['amplitude', 'phase']:
                if strategy == "weighted_average":
                    value = sum(
                        cp.oscillator_state.get(channel, {}).get(key, 0.5) * w
                        for cp, w in zip(checkpoints, weights)
                    )
                elif strategy == "latest_wins":
                    value = checkpoints[-1].oscillator_state.get(channel, {}).get(key, 0.5)
                else:
                    # Average
                    values = [
                        cp.oscillator_state.get(channel, {}).get(key, 0.5)
                        for cp in checkpoints
                    ]
                    value = sum(values) / len(values)

                merged_state[channel][key] = value

        # Merge token mappings
        merged_tokens = {}
        conflicts = 0

        # Collect all tokens
        all_tokens = set()
        for cp in checkpoints:
            all_tokens.update(cp.token_mappings.keys())

        for token in all_tokens:
            classes = []
            for cp in checkpoints:
                if token in cp.token_mappings:
                    classes.append(cp.token_mappings[token])

            if not classes:
                continue

            if strategy == "majority_vote":
                # Most common class wins
                from collections import Counter
                counter = Counter(classes)
                merged_tokens[token] = counter.most_common(1)[0][0]
                if len(set(classes)) > 1:
                    conflicts += 1
            elif strategy == "latest_wins":
                # Last checkpoint's value
                merged_tokens[token] = classes[-1]
            else:
                # First non-None wins
                merged_tokens[token] = classes[0]

        # Create merged checkpoint data
        merged_data = {
            'name': output_name,
            'timestamp': datetime.now().isoformat(),
            'version': '1.0',
            'oscillator_state': merged_state,
            'token_mappings': merged_tokens,
            'synchrony_vector': [],
            'dominant_channel': 'advance',
            'frequency_history': [],
            'statistics': {
                'merged_from': checkpoint_names,
                'merge_strategy': strategy,
                'conflicts_resolved': conflicts,
                'weights': weights
            }
        }

        # Save merged checkpoint
        merged_path = self.local_dir / f"{output_name}_merged.json"
        with open(merged_path, 'w') as f:
            json.dump(merged_data, f, indent=2)

        # Version the merged checkpoint
        result = self.save_versioned(
            router=None,  # We already have the data
            name=output_name,
            version="1.0.0",
            metadata={'merge_source': checkpoint_names, 'strategy': strategy}
        )

        # Copy the merged data to the versioned file
        if result:
            versioned_path = Path(result[0])
            shutil.copy(str(merged_path), str(versioned_path))
            merged_path.unlink()

        logger.info(f"Merged {len(checkpoints)} checkpoints -> {output_name}")
        return result

    def list_versions(self, name: str) -> List[str]:
        """List all versions of a checkpoint"""
        if name not in self.version_index:
            return []
        return [str(v) for v in sorted(self.version_index[name])]

    def get_latest_version(self, name: str) -> Optional[str]:
        """Get latest version of a checkpoint"""
        if name not in self.version_index or not self.version_index[name]:
            return None
        return str(max(self.version_index[name]))

    def add_remote(self, name: str, adapter: StorageAdapter):
        """Add a remote storage adapter"""
        self.remote_adapters[name] = adapter
        logger.info(f"Added remote adapter: {name}")

    def remove_remote(self, name: str) -> bool:
        """Remove a remote storage adapter"""
        if name in self.remote_adapters:
            del self.remote_adapters[name]
            logger.info(f"Removed remote adapter: {name}")
            return True
        return False

    def sync_all(self, name: Optional[str] = None):
        """
        Sync all local checkpoints to remotes.

        Args:
            name: Specific checkpoint name to sync (all if None)
        """
        if not self.remote_adapters:
            logger.warning("No remote adapters configured")
            return

        checkpoints_to_sync = []

        if name:
            if name in self.version_index:
                for version in self.version_index[name]:
                    checkpoints_to_sync.append(f"{name}_v{version}")
        else:
            for cp_name, versions in self.version_index.items():
                for version in versions:
                    checkpoints_to_sync.append(f"{cp_name}_v{version}")

        logger.info(f"Syncing {len(checkpoints_to_sync)} checkpoints...")

        for checkpoint_name in checkpoints_to_sync:
            self._sync_to_remotes(checkpoint_name)

        logger.info("Sync complete")

    def get_statistics(self) -> Dict[str, Any]:
        """Get manager statistics"""
        return {
            'local_dir': str(self.local_dir),
            'remote_adapters': list(self.remote_adapters.keys()),
            'max_versions': self.max_versions,
            'checkpoint_count': sum(len(v) for v in self.version_index.values()),
            'checkpoints': {
                name: {
                    'versions': len(versions),
                    'latest': str(max(versions)) if versions else None
                }
                for name, versions in self.version_index.items()
            }
        }

    def shutdown(self):
        """Shutdown the executor"""
        self.executor.shutdown(wait=True)

    # =========================================================================
    # FEDERATED LEARNING INTEGRATION (Phase 8B)
    # =========================================================================

    def save_federated_model(
        self,
        global_weights: Dict[str, Any],
        round_number: int,
        name: str = "federated_global",
        metadata: Optional[Dict] = None
    ) -> Tuple[str, SemanticVersion]:
        """
        Save federated learning global model.

        Args:
            global_weights: Dictionary of global model weights (tensors serialized)
            round_number: Current federated round number
            name: Base name for the checkpoint
            metadata: Additional metadata (node count, aggregation strategy, etc.)

        Returns:
            Tuple of (checkpoint_path, version)
        """
        import torch

        # Convert tensors to serializable format
        serialized_weights = {}
        for param_name, tensor in global_weights.items():
            if isinstance(tensor, torch.Tensor):
                serialized_weights[param_name] = {
                    'data': tensor.cpu().numpy().tolist(),
                    'shape': list(tensor.shape),
                    'dtype': str(tensor.dtype)
                }
            else:
                serialized_weights[param_name] = tensor

        # Create checkpoint data
        checkpoint_data = {
            'type': 'federated_global_model',
            'round_number': round_number,
            'model_weights': serialized_weights,
            'timestamp': datetime.now().isoformat(),
            'metadata': metadata or {}
        }

        # Determine version based on round number
        version = SemanticVersion(
            major=1,
            minor=round_number // 100,
            patch=round_number % 100
        )

        # Save to local path
        checkpoint_path = self.local_dir / f"{name}_v{version}.json"
        with open(checkpoint_path, 'w') as f:
            json.dump(checkpoint_data, f, indent=2)

        # Update version index
        if name not in self.version_index:
            self.version_index[name] = []
        if version not in self.version_index[name]:
            self.version_index[name].append(version)
            self.version_index[name].sort()
        self._save_version_index()

        # Sync to remotes
        if self.sync_on_save and self.remote_adapters:
            self._sync_to_remotes(f"{name}_v{version}")

        logger.info(f"Saved federated model: {name} v{version} (round {round_number})")
        return str(checkpoint_path), version

    def load_federated_model(
        self,
        name: str = "federated_global",
        version: Optional[str] = None,
        device: str = 'cpu'
    ) -> Tuple[Dict[str, Any], Dict]:
        """
        Load federated learning global model.

        Args:
            name: Base name for the checkpoint
            version: Specific version to load (latest if None)
            device: Device to load tensors to

        Returns:
            Tuple of (global_weights dict, metadata dict)
        """
        import torch

        # Get version to load
        if version is None:
            version = self.get_latest_version(name)
            if version is None:
                raise CheckpointNotFoundError(f"No federated model found: {name}")

        # Find checkpoint path
        sem_version = SemanticVersion.parse(version)
        checkpoint_path = self.local_dir / f"{name}_v{sem_version}.json"

        if not checkpoint_path.exists():
            # Try to pull from remote
            pulled = self._pull_from_remotes(f"{name}_v{sem_version}")
            if not pulled:
                raise CheckpointNotFoundError(f"Federated model not found: {name} v{version}")

        # Load checkpoint
        with open(checkpoint_path, 'r') as f:
            checkpoint_data = json.load(f)

        # Deserialize weights
        global_weights = {}
        for param_name, weight_data in checkpoint_data.get('model_weights', {}).items():
            if isinstance(weight_data, dict) and 'data' in weight_data:
                tensor = torch.tensor(weight_data['data'], device=device)
                global_weights[param_name] = tensor
            else:
                global_weights[param_name] = weight_data

        metadata = {
            'round_number': checkpoint_data.get('round_number', 0),
            'timestamp': checkpoint_data.get('timestamp'),
            'custom': checkpoint_data.get('metadata', {})
        }

        logger.info(f"Loaded federated model: {name} v{version}")
        return global_weights, metadata

    def _pull_from_remotes(self, checkpoint_name: str) -> bool:
        """Try to pull checkpoint from remote storage."""
        local_path = self.local_dir / f"{checkpoint_name}.json"

        for adapter_name, adapter in self.remote_adapters.items():
            remote_path = f"checkpoints/{checkpoint_name}.json"
            if adapter.exists(remote_path):
                try:
                    adapter.download(remote_path, str(local_path))
                    logger.info(f"Pulled {checkpoint_name} from {adapter_name}")
                    return True
                except Exception as e:
                    logger.warning(f"Failed to pull from {adapter_name}: {e}")

        return False

    def sync_federated_round(
        self,
        coordinator_stats: Dict,
        node_updates: List[Dict],
        round_number: int
    ) -> str:
        """
        Sync federated learning round results.

        Args:
            coordinator_stats: Statistics from FederatedCoordinator
            node_updates: List of node update summaries
            round_number: Round number

        Returns:
            Path to saved round summary
        """
        round_data = {
            'type': 'federated_round_summary',
            'round_number': round_number,
            'coordinator_stats': coordinator_stats,
            'node_updates': node_updates,
            'timestamp': datetime.now().isoformat()
        }

        # Save locally
        round_path = self.local_dir / f"federated_round_{round_number:04d}.json"
        with open(round_path, 'w') as f:
            json.dump(round_data, f, indent=2)

        # Sync to remotes
        if self.sync_on_save and self.remote_adapters:
            for adapter_name, adapter in self.remote_adapters.items():
                try:
                    remote_path = f"federated_rounds/round_{round_number:04d}.json"
                    adapter.upload(str(round_path), remote_path)
                except Exception as e:
                    logger.warning(f"Failed to sync round to {adapter_name}: {e}")

        logger.info(f"Synced federated round {round_number}")
        return str(round_path)

    def list_federated_rounds(self) -> List[int]:
        """List all saved federated round numbers."""
        rounds = []
        for f in self.local_dir.glob("federated_round_*.json"):
            try:
                round_num = int(f.stem.split('_')[-1])
                rounds.append(round_num)
            except ValueError:
                continue
        return sorted(rounds)

    def get_federated_round(self, round_number: int) -> Optional[Dict]:
        """Get federated round summary."""
        round_path = self.local_dir / f"federated_round_{round_number:04d}.json"
        if not round_path.exists():
            return None

        with open(round_path, 'r') as f:
            return json.load(f)


class FederatedCheckpointAdapter:
    """
    Adapter for integrating FederatedCoordinator with DistributedCheckpointManager.

    Provides automatic checkpointing during federated training.
    """

    def __init__(
        self,
        checkpoint_manager: DistributedCheckpointManager,
        checkpoint_every: int = 5,
        model_name: str = "federated_global"
    ):
        """
        Initialize federated checkpoint adapter.

        Args:
            checkpoint_manager: DistributedCheckpointManager instance
            checkpoint_every: Checkpoint every N rounds
            model_name: Base name for model checkpoints
        """
        self.manager = checkpoint_manager
        self.checkpoint_every = checkpoint_every
        self.model_name = model_name

    def on_round_complete(
        self,
        global_weights: Dict[str, Any],
        round_number: int,
        coordinator_stats: Dict,
        node_updates: List[Dict]
    ):
        """
        Called after each federated round completes.

        Args:
            global_weights: Current global model weights
            round_number: Completed round number
            coordinator_stats: Coordinator statistics
            node_updates: Node update summaries
        """
        # Always sync round summary
        self.manager.sync_federated_round(
            coordinator_stats=coordinator_stats,
            node_updates=node_updates,
            round_number=round_number
        )

        # Checkpoint model at intervals
        if round_number % self.checkpoint_every == 0:
            self.manager.save_federated_model(
                global_weights=global_weights,
                round_number=round_number,
                name=self.model_name,
                metadata={
                    'total_nodes': coordinator_stats.get('num_nodes', 0),
                    'total_samples': coordinator_stats.get('total_samples', 0),
                    'aggregation_strategy': coordinator_stats.get('aggregation_strategy', 'unknown')
                }
            )

    def restore_from_checkpoint(
        self,
        version: Optional[str] = None,
        device: str = 'cpu'
    ) -> Tuple[Dict[str, Any], int]:
        """
        Restore global model from checkpoint.

        Args:
            version: Specific version to load (latest if None)
            device: Device to load tensors to

        Returns:
            Tuple of (global_weights, round_number)
        """
        global_weights, metadata = self.manager.load_federated_model(
            name=self.model_name,
            version=version,
            device=device
        )
        return global_weights, metadata.get('round_number', 0)


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("  DISTRIBUTED CHECKPOINT MANAGER TEST")
    print("=" * 60)

    # Create manager
    manager = DistributedCheckpointManager(
        local_dir="data/test_distributed_checkpoints",
        max_versions=5
    )

    print(f"\nManager initialized: {manager.local_dir}")
    print(f"Remote adapters: {list(manager.remote_adapters.keys())}")

    # Test versioning
    print("\n--- Semantic Versioning Test ---")
    v1 = SemanticVersion.parse("1.2.3")
    print(f"Parsed: {v1}")
    print(f"Incremented patch: {v1.increment_patch()}")
    print(f"Incremented minor: {v1.increment_minor()}")
    print(f"Incremented major: {v1.increment_major()}")

    v2 = SemanticVersion.parse("2.0.0-beta.1")
    print(f"With prerelease: {v2}")
    print(f"v1 < v2: {v1 < v2}")

    # Test diff structure
    print("\n--- CheckpointDiff Test ---")
    diff = CheckpointDiff(
        source_name="test_a",
        target_name="test_b",
        source_version="1.0.0",
        target_version="1.1.0",
        oscillator_diff={'A': {'amplitude': 0.15}},
        tokens_added={'new_token': 'ACTION'},
        tokens_removed=['old_token']
    )
    diff.total_changes = 3
    diff.change_magnitude = 0.25
    print(f"Diff: {diff.to_dict()}")

    # Show statistics
    print("\n--- Manager Statistics ---")
    stats = manager.get_statistics()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    # Cleanup
    manager.shutdown()

    print("\n" + "=" * 60)
    print("  TEST COMPLETE")
    print("=" * 60)
