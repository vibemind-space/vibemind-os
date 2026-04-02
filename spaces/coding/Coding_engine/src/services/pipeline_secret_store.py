"""Pipeline secret store.

Manages pipeline secrets — storing sensitive configuration values that
should be masked and protected. Supports per-pipeline secret namespacing,
rotation, and change callbacks.
"""

import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class _SecretEntry:
    """A single stored secret."""

    secret_id: str = ""
    pipeline_name: str = ""
    key: str = ""
    value: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    version: int = 1
    created_at: float = 0.0
    updated_at: float = 0.0
    seq: int = 0


# ---------------------------------------------------------------------------
# Pipeline Secret Store
# ---------------------------------------------------------------------------


class PipelineSecretStore:
    """Manages pipeline secrets — sensitive configuration values.

    Secrets are namespaced by pipeline name and accessed via
    ``(pipeline_name, key)`` pairs.  Values are never exposed in
    listings; only keys are returned by :meth:`list_secrets`.
    """

    def __init__(self, max_entries: int = 10000):
        self._max_entries = max_entries
        self._secrets: Dict[str, _SecretEntry] = {}
        self._lookup: Dict[str, str] = {}  # "pipeline:key" -> secret_id
        self._pipeline_index: Dict[str, List[str]] = {}  # pipeline -> [secret_id]
        self._seq: int = 0
        self._lock = threading.Lock()
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_set": 0,
            "total_updated": 0,
            "total_deleted": 0,
            "total_rotated": 0,
            "total_cleared": 0,
        }

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self, seed: str) -> str:
        """Generate a collision-free ID with prefix ``pss2-``."""
        self._seq += 1
        raw = f"{seed}:{time.time()}:{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"pss2-{digest}"

    # ------------------------------------------------------------------
    # Set / Get / Delete
    # ------------------------------------------------------------------

    def set_secret(
        self,
        pipeline_name: str,
        key: str,
        value: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Set a secret for a pipeline.

        Creates the secret if it does not exist, or updates it if it
        does.  Returns the ``secret_id`` (prefix ``pss2-``), or ``""``
        on failure.
        """
        with self._lock:
            if not pipeline_name or not key:
                logger.warning("set_secret_invalid_args")
                return ""

            lookup_key = f"{pipeline_name}:{key}"
            existing_sid = self._lookup.get(lookup_key)

            if existing_sid:
                entry = self._secrets[existing_sid]
                entry.value = value
                if metadata is not None:
                    entry.metadata = dict(metadata)
                entry.version += 1
                entry.updated_at = time.time()
                self._stats["total_updated"] += 1
                logger.info(
                    "secret_updated: secret_id=%s pipeline=%s key=%s",
                    existing_sid, pipeline_name, key,
                )
                self._fire("secret_updated", {
                    "secret_id": existing_sid,
                    "pipeline_name": pipeline_name,
                    "key": key,
                })
                return existing_sid

            if len(self._secrets) >= self._max_entries:
                logger.warning("set_secret_capacity_reached")
                return ""

            now = time.time()
            secret_id = self._next_id(lookup_key)

            entry = _SecretEntry(
                secret_id=secret_id,
                pipeline_name=pipeline_name,
                key=key,
                value=value,
                metadata=dict(metadata) if metadata else {},
                version=1,
                created_at=now,
                updated_at=now,
                seq=self._seq,
            )

            self._secrets[secret_id] = entry
            self._lookup[lookup_key] = secret_id
            self._pipeline_index.setdefault(pipeline_name, []).append(secret_id)
            self._stats["total_set"] += 1

            logger.info(
                "secret_set: secret_id=%s pipeline=%s key=%s",
                secret_id, pipeline_name, key,
            )
            self._fire("secret_set", {
                "secret_id": secret_id,
                "pipeline_name": pipeline_name,
                "key": key,
            })
            return secret_id

    def get_secret(self, pipeline_name: str, key: str) -> Any:
        """Get a secret value.  Returns ``None`` if not found."""
        with self._lock:
            lookup_key = f"{pipeline_name}:{key}"
            sid = self._lookup.get(lookup_key)
            if not sid or sid not in self._secrets:
                return None
            return self._secrets[sid].value

    def delete_secret(self, pipeline_name: str, key: str) -> bool:
        """Delete a secret.  Returns ``False`` if not found."""
        with self._lock:
            lookup_key = f"{pipeline_name}:{key}"
            sid = self._lookup.pop(lookup_key, None)
            if not sid or sid not in self._secrets:
                logger.warning(
                    "delete_secret_not_found: pipeline=%s key=%s",
                    pipeline_name, key,
                )
                return False

            del self._secrets[sid]
            pl_list = self._pipeline_index.get(pipeline_name, [])
            if sid in pl_list:
                pl_list.remove(sid)
            if not pl_list:
                self._pipeline_index.pop(pipeline_name, None)

            self._stats["total_deleted"] += 1
            logger.info(
                "secret_deleted: pipeline=%s key=%s", pipeline_name, key,
            )
            self._fire("secret_deleted", {
                "pipeline_name": pipeline_name,
                "key": key,
            })
            return True

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def has_secret(self, pipeline_name: str, key: str) -> bool:
        """Check whether a secret exists."""
        with self._lock:
            lookup_key = f"{pipeline_name}:{key}"
            return lookup_key in self._lookup

    def list_secrets(self, pipeline_name: str) -> List[str]:
        """List secret keys (NOT values) for a pipeline."""
        with self._lock:
            sids = self._pipeline_index.get(pipeline_name, [])
            keys: List[str] = []
            for sid in sids:
                entry = self._secrets.get(sid)
                if entry:
                    keys.append(entry.key)
            keys.sort()
            return keys

    def get_pipeline_secret_count(self, pipeline_name: str) -> int:
        """Return the number of secrets stored for *pipeline_name*."""
        with self._lock:
            return len(self._pipeline_index.get(pipeline_name, []))

    def clear_pipeline_secrets(self, pipeline_name: str) -> int:
        """Clear all secrets for a pipeline.  Returns the count removed."""
        with self._lock:
            sids = list(self._pipeline_index.get(pipeline_name, []))
            if not sids:
                return 0

            removed = 0
            for sid in sids:
                entry = self._secrets.pop(sid, None)
                if entry:
                    lookup_key = f"{pipeline_name}:{entry.key}"
                    self._lookup.pop(lookup_key, None)
                    removed += 1

            self._pipeline_index.pop(pipeline_name, None)
            self._stats["total_cleared"] += removed

            logger.info(
                "pipeline_secrets_cleared: pipeline=%s count=%d",
                pipeline_name, removed,
            )
            self._fire("pipeline_cleared", {
                "pipeline_name": pipeline_name,
                "count": removed,
            })
            return removed

    def list_pipelines(self) -> List[str]:
        """List all pipelines that have at least one secret."""
        with self._lock:
            return sorted(
                pn for pn, sids in self._pipeline_index.items() if sids
            )

    # ------------------------------------------------------------------
    # Rotation
    # ------------------------------------------------------------------

    def rotate_secret(
        self, pipeline_name: str, key: str, new_value: Any,
    ) -> bool:
        """Rotate (update) a secret to *new_value*.

        Returns ``False`` if the secret does not exist.
        """
        with self._lock:
            lookup_key = f"{pipeline_name}:{key}"
            sid = self._lookup.get(lookup_key)
            if not sid or sid not in self._secrets:
                logger.warning(
                    "rotate_secret_not_found: pipeline=%s key=%s",
                    pipeline_name, key,
                )
                return False

            entry = self._secrets[sid]
            entry.value = new_value
            entry.version += 1
            entry.updated_at = time.time()
            self._stats["total_rotated"] += 1

            logger.info(
                "secret_rotated: secret_id=%s pipeline=%s key=%s version=%d",
                sid, pipeline_name, key, entry.version,
            )
            self._fire("secret_rotated", {
                "secret_id": sid,
                "pipeline_name": pipeline_name,
                "key": key,
                "version": entry.version,
            })
            return True

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a change callback."""
        self._callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a change callback by name."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, detail: Dict) -> None:
        """Fire all registered callbacks."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                logger.exception("callback_error: action=%s", action)

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Return store statistics."""
        with self._lock:
            pipeline_count = sum(
                1 for sids in self._pipeline_index.values() if sids
            )
            return {
                **self._stats,
                "current_secrets": len(self._secrets),
                "current_pipelines": pipeline_count,
                "max_entries": self._max_entries,
                "callbacks_registered": len(self._callbacks),
            }

    def reset(self) -> None:
        """Clear all state."""
        with self._lock:
            self._secrets.clear()
            self._lookup.clear()
            self._pipeline_index.clear()
            self._callbacks.clear()
            self._seq = 0
            self._stats = {k: 0 for k in self._stats}
            logger.info("store_reset")
