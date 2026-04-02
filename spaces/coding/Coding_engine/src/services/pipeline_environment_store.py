"""Pipeline environment store.

Manages pipeline environment configurations — storing environment-specific
settings for pipeline execution. Supports creating, cloning, comparing,
and updating named environments with per-environment config variables.
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
class EnvironmentEntry:
    """A single pipeline environment record."""

    env_id: str = ""
    name: str = ""
    config: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0


# ---------------------------------------------------------------------------
# Pipeline Environment Store
# ---------------------------------------------------------------------------


class PipelineEnvironmentStore:
    """Manages pipeline environment configurations for execution."""

    def __init__(self, max_entries: int = 10000):
        self._max_entries = max_entries
        self._environments: Dict[str, EnvironmentEntry] = {}
        self._name_index: Dict[str, str] = {}  # name -> env_id
        self._seq: int = 0
        self._lock = threading.Lock()
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_created": 0,
            "total_updated": 0,
            "total_deleted": 0,
            "total_cloned": 0,
            "total_pruned": 0,
        }

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self, seed: str) -> str:
        """Generate a collision-free ID with prefix 'pes-'."""
        self._seq += 1
        raw = f"{seed}:{time.time()}:{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"pes-{digest}"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Remove oldest entries when at capacity."""
        if len(self._environments) < self._max_entries:
            return
        sorted_envs = sorted(
            self._environments.values(), key=lambda e: e.updated_at
        )
        remove_count = len(self._environments) - self._max_entries + 1
        for entry in sorted_envs[:remove_count]:
            self._name_index.pop(entry.name, None)
            del self._environments[entry.env_id]
            self._stats["total_pruned"] += 1
            logger.debug("environment_pruned: env_id=%s", entry.env_id)

    def _entry_to_dict(self, entry: EnvironmentEntry) -> Dict:
        """Convert an EnvironmentEntry to a plain dict."""
        return {
            "env_id": entry.env_id,
            "name": entry.name,
            "config": dict(entry.config),
            "description": entry.description,
            "metadata": dict(entry.metadata),
            "created_at": entry.created_at,
            "updated_at": entry.updated_at,
        }

    # ------------------------------------------------------------------
    # Create environment
    # ------------------------------------------------------------------

    def create_environment(
        self,
        name: str,
        config: Dict[str, Any],
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a new environment.

        Returns the env_id (prefix 'pes-'), or '' if name already exists.
        """
        with self._lock:
            if not name:
                logger.warning("create_environment_invalid_name")
                return ""

            if name in self._name_index:
                logger.warning(
                    "create_environment_duplicate: name=%s", name
                )
                return ""

            self._prune_if_needed()

            now = time.time()
            env_id = self._next_id(name)

            entry = EnvironmentEntry(
                env_id=env_id,
                name=name,
                config=dict(config) if config else {},
                description=description,
                metadata=dict(metadata) if metadata else {},
                created_at=now,
                updated_at=now,
            )

            self._environments[env_id] = entry
            self._name_index[name] = env_id
            self._stats["total_created"] += 1

            logger.info(
                "environment_created: env_id=%s name=%s", env_id, name
            )
            self._fire("environment_created", self._entry_to_dict(entry))
            return env_id

    # ------------------------------------------------------------------
    # Get environment
    # ------------------------------------------------------------------

    def get_environment(self, name: str) -> Optional[Dict]:
        """Get an environment by name. Returns dict or None."""
        with self._lock:
            env_id = self._name_index.get(name)
            if not env_id or env_id not in self._environments:
                return None
            return self._entry_to_dict(self._environments[env_id])

    # ------------------------------------------------------------------
    # Update environment
    # ------------------------------------------------------------------

    def update_environment(
        self,
        name: str,
        config: Optional[Dict[str, Any]] = None,
        description: Optional[str] = None,
    ) -> bool:
        """Update an existing environment. Returns False if not found."""
        with self._lock:
            env_id = self._name_index.get(name)
            if not env_id or env_id not in self._environments:
                logger.warning(
                    "update_environment_not_found: name=%s", name
                )
                return False

            entry = self._environments[env_id]

            if config is not None:
                entry.config = dict(config)
            if description is not None:
                entry.description = description

            entry.updated_at = time.time()
            self._stats["total_updated"] += 1

            logger.info(
                "environment_updated: env_id=%s name=%s", env_id, name
            )
            self._fire("environment_updated", self._entry_to_dict(entry))
            return True

    # ------------------------------------------------------------------
    # Delete environment
    # ------------------------------------------------------------------

    def delete_environment(self, name: str) -> bool:
        """Delete an environment by name. Returns False if not found."""
        with self._lock:
            env_id = self._name_index.pop(name, None)
            if not env_id or env_id not in self._environments:
                logger.warning(
                    "delete_environment_not_found: name=%s", name
                )
                return False

            entry = self._environments.pop(env_id)
            self._stats["total_deleted"] += 1

            logger.info(
                "environment_deleted: env_id=%s name=%s", env_id, name
            )
            self._fire("environment_deleted", self._entry_to_dict(entry))
            return True

    # ------------------------------------------------------------------
    # List environments
    # ------------------------------------------------------------------

    def list_environments(self) -> List[Dict]:
        """List all environments as dicts, sorted by name."""
        with self._lock:
            results = [
                self._entry_to_dict(e) for e in self._environments.values()
            ]
            results.sort(key=lambda d: d["name"])
            return results

    # ------------------------------------------------------------------
    # Variable access helpers
    # ------------------------------------------------------------------

    def set_variable(self, env_name: str, key: str, value: Any) -> bool:
        """Set a variable in the environment's config.

        Returns False if the environment is not found.
        """
        with self._lock:
            env_id = self._name_index.get(env_name)
            if not env_id or env_id not in self._environments:
                logger.warning(
                    "set_variable_env_not_found: env_name=%s", env_name
                )
                return False

            entry = self._environments[env_id]
            entry.config[key] = value
            entry.updated_at = time.time()

            logger.info(
                "variable_set: env_name=%s key=%s", env_name, key
            )
            self._fire("variable_set", {
                "env_name": env_name,
                "key": key,
                "value": value,
            })
            return True

    def get_variable(
        self, env_name: str, key: str, default: Any = None
    ) -> Any:
        """Get a variable from an environment's config.

        Returns *default* if the environment or key is not found.
        """
        with self._lock:
            env_id = self._name_index.get(env_name)
            if not env_id or env_id not in self._environments:
                return default
            return self._environments[env_id].config.get(key, default)

    # ------------------------------------------------------------------
    # Clone environment
    # ------------------------------------------------------------------

    def clone_environment(self, source_name: str, new_name: str) -> str:
        """Clone an environment under a new name.

        Returns the new env_id, or '' if the source is not found or
        *new_name* already exists.
        """
        with self._lock:
            source_id = self._name_index.get(source_name)
            if not source_id or source_id not in self._environments:
                logger.warning(
                    "clone_environment_source_not_found: source=%s",
                    source_name,
                )
                return ""

            if new_name in self._name_index:
                logger.warning(
                    "clone_environment_target_exists: new_name=%s",
                    new_name,
                )
                return ""

            self._prune_if_needed()

            source = self._environments[source_id]
            now = time.time()
            env_id = self._next_id(new_name)

            entry = EnvironmentEntry(
                env_id=env_id,
                name=new_name,
                config=dict(source.config),
                description=source.description,
                metadata=dict(source.metadata),
                created_at=now,
                updated_at=now,
            )

            self._environments[env_id] = entry
            self._name_index[new_name] = env_id
            self._stats["total_cloned"] += 1

            logger.info(
                "environment_cloned: source=%s new=%s env_id=%s",
                source_name,
                new_name,
                env_id,
            )
            self._fire("environment_cloned", {
                "source_name": source_name,
                "new_name": new_name,
                "env_id": env_id,
            })
            return env_id

    # ------------------------------------------------------------------
    # Compare environments
    # ------------------------------------------------------------------

    def compare_environments(
        self, name1: str, name2: str
    ) -> Dict[str, Dict[str, Any]]:
        """Compare config of two environments.

        Returns a dict with keys:
          only_in_1  — keys present only in the first environment
          only_in_2  — keys present only in the second environment
          different  — keys in both but with differing values
          same       — keys in both with identical values
        Each sub-dict maps config keys to their values (or a tuple for
        *different*).
        """
        with self._lock:
            env1_id = self._name_index.get(name1)
            env2_id = self._name_index.get(name2)

            cfg1: Dict[str, Any] = {}
            cfg2: Dict[str, Any] = {}

            if env1_id and env1_id in self._environments:
                cfg1 = self._environments[env1_id].config
            if env2_id and env2_id in self._environments:
                cfg2 = self._environments[env2_id].config

            keys1 = set(cfg1.keys())
            keys2 = set(cfg2.keys())

            only_in_1 = {k: cfg1[k] for k in sorted(keys1 - keys2)}
            only_in_2 = {k: cfg2[k] for k in sorted(keys2 - keys1)}
            different: Dict[str, Any] = {}
            same: Dict[str, Any] = {}

            for k in sorted(keys1 & keys2):
                if cfg1[k] == cfg2[k]:
                    same[k] = cfg1[k]
                else:
                    different[k] = {"env1": cfg1[k], "env2": cfg2[k]}

            return {
                "only_in_1": only_in_1,
                "only_in_2": only_in_2,
                "different": different,
                "same": same,
            }

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
            return {
                **self._stats,
                "current_environments": len(self._environments),
                "max_entries": self._max_entries,
                "callbacks_registered": len(self._callbacks),
            }

    def reset(self) -> None:
        """Clear all state."""
        with self._lock:
            self._environments.clear()
            self._name_index.clear()
            self._callbacks.clear()
            self._seq = 0
            self._stats = {k: 0 for k in self._stats}
            logger.info("store_reset")
