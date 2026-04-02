"""Pipeline variable store.

Manages pipeline variables and environment with scoping and inheritance.
Supports pipeline-level and global scopes, secret redaction, and
change notification callbacks.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

VALID_SCOPES = {"pipeline", "global"}
SECRET_REDACTED = "***REDACTED***"


@dataclass
class VariableEntry:
    """A single pipeline variable record."""
    var_id: str = ""
    pipeline_name: str = ""
    scope: str = "pipeline"
    key: str = ""
    value: Any = None
    is_secret: bool = False
    created_at: float = 0.0
    updated_at: float = 0.0
    tags: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pipeline Variable Store
# ---------------------------------------------------------------------------

class PipelineVariableStore:
    """Manages pipeline variables with scoping, inheritance, and secret handling."""

    def __init__(self, max_entries: int = 10000):
        self._max_entries = max_entries
        self._variables: Dict[str, VariableEntry] = {}
        self._index: Dict[str, str] = {}  # (pipeline, scope, key) -> var_id
        self._seq: int = 0
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_set": 0,
            "total_get": 0,
            "total_deleted": 0,
            "total_pruned": 0,
            "total_secrets": 0,
        }

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self, seed: str) -> str:
        """Generate a collision-free ID with prefix 'pvr-'."""
        self._seq += 1
        raw = f"{seed}:{time.time()}:{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"pvr-{digest}"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_index_key(self, pipeline_name: str, scope: str, key: str) -> str:
        """Build a composite lookup key for the index."""
        return f"{pipeline_name}||{scope}||{key}"

    def _prune_if_needed(self) -> None:
        """Remove oldest entries when at capacity."""
        if len(self._variables) < self._max_entries:
            return
        sorted_vars = sorted(
            self._variables.values(), key=lambda v: v.updated_at
        )
        remove_count = len(self._variables) - self._max_entries + 1
        for entry in sorted_vars[:remove_count]:
            idx_key = self._make_index_key(
                entry.pipeline_name, entry.scope, entry.key
            )
            self._index.pop(idx_key, None)
            del self._variables[entry.var_id]
            self._stats["total_pruned"] += 1
            logger.debug("variable_pruned", var_id=entry.var_id)

    def _entry_to_dict(self, entry: VariableEntry, redact: bool = False) -> Dict:
        """Convert a VariableEntry to a plain dict."""
        value = SECRET_REDACTED if (redact and entry.is_secret) else entry.value
        return {
            "var_id": entry.var_id,
            "pipeline_name": entry.pipeline_name,
            "scope": entry.scope,
            "key": entry.key,
            "value": value,
            "is_secret": entry.is_secret,
            "created_at": entry.created_at,
            "updated_at": entry.updated_at,
            "tags": list(entry.tags),
        }

    # ------------------------------------------------------------------
    # Set / update variables
    # ------------------------------------------------------------------

    def set_variable(
        self,
        pipeline_name: str,
        key: str,
        value: Any,
        scope: str = "pipeline",
        is_secret: bool = False,
        tags: Optional[List[str]] = None,
    ) -> str:
        """Set or update a variable. Returns the var_id.

        If the variable already exists for the given pipeline/scope/key,
        its value and metadata are updated in place.
        """
        if not pipeline_name or not key:
            logger.warning(
                "set_variable_invalid_input",
                pipeline_name=pipeline_name,
                key=key,
            )
            return ""

        if scope not in VALID_SCOPES:
            scope = "pipeline"

        idx_key = self._make_index_key(pipeline_name, scope, key)
        now = time.time()

        existing_id = self._index.get(idx_key)
        if existing_id and existing_id in self._variables:
            entry = self._variables[existing_id]
            entry.value = value
            entry.is_secret = is_secret
            entry.updated_at = now
            entry.tags = list(tags) if tags else entry.tags
            self._stats["total_set"] += 1
            if is_secret:
                self._stats["total_secrets"] += 1

            logger.info(
                "variable_updated",
                var_id=existing_id,
                pipeline_name=pipeline_name,
                key=key,
                scope=scope,
            )
            self._fire("variable_updated", self._entry_to_dict(entry))
            return existing_id

        self._prune_if_needed()

        var_id = self._next_id(f"{pipeline_name}:{scope}:{key}")

        entry = VariableEntry(
            var_id=var_id,
            pipeline_name=pipeline_name,
            scope=scope,
            key=key,
            value=value,
            is_secret=is_secret,
            created_at=now,
            updated_at=now,
            tags=list(tags) if tags else [],
        )

        self._variables[var_id] = entry
        self._index[idx_key] = var_id
        self._stats["total_set"] += 1
        if is_secret:
            self._stats["total_secrets"] += 1

        logger.info(
            "variable_set",
            var_id=var_id,
            pipeline_name=pipeline_name,
            key=key,
            scope=scope,
        )
        self._fire("variable_set", self._entry_to_dict(entry))
        return var_id

    # ------------------------------------------------------------------
    # Get variables
    # ------------------------------------------------------------------

    def get_variable(
        self, pipeline_name: str, key: str, scope: str = "pipeline"
    ) -> Optional[Any]:
        """Get the value of a variable. Returns None if not found.

        Scope inheritance: if *scope* is 'pipeline' and the variable is
        not found there, falls back to 'global' scope.
        """
        self._stats["total_get"] += 1

        idx_key = self._make_index_key(pipeline_name, scope, key)
        var_id = self._index.get(idx_key)

        if var_id and var_id in self._variables:
            return self._variables[var_id].value

        # Scope inheritance: pipeline -> global fallback
        if scope == "pipeline":
            global_idx = self._make_index_key(pipeline_name, "global", key)
            global_id = self._index.get(global_idx)
            if global_id and global_id in self._variables:
                return self._variables[global_id].value

        return None

    # ------------------------------------------------------------------
    # Delete variables
    # ------------------------------------------------------------------

    def delete_variable(
        self, pipeline_name: str, key: str, scope: str = "pipeline"
    ) -> bool:
        """Delete a variable. Returns True if it existed and was removed."""
        if not pipeline_name or not key:
            return False

        idx_key = self._make_index_key(pipeline_name, scope, key)
        var_id = self._index.pop(idx_key, None)

        if not var_id or var_id not in self._variables:
            logger.warning(
                "delete_variable_not_found",
                pipeline_name=pipeline_name,
                key=key,
                scope=scope,
            )
            return False

        entry = self._variables.pop(var_id)
        self._stats["total_deleted"] += 1

        logger.info(
            "variable_deleted",
            var_id=var_id,
            pipeline_name=pipeline_name,
            key=key,
            scope=scope,
        )
        self._fire("variable_deleted", self._entry_to_dict(entry))
        return True

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def has_variable(
        self, pipeline_name: str, key: str, scope: str = "pipeline"
    ) -> bool:
        """Check whether a variable exists for the given pipeline/scope/key."""
        idx_key = self._make_index_key(pipeline_name, scope, key)
        var_id = self._index.get(idx_key)
        return var_id is not None and var_id in self._variables

    def list_variables(
        self, pipeline_name: str, scope: Optional[str] = None
    ) -> List[Dict]:
        """List variables for a pipeline, optionally filtered by scope.

        Secret values are redacted in the returned dicts.
        """
        self._stats["total_get"] += 1
        results = []
        for entry in self._variables.values():
            if entry.pipeline_name != pipeline_name:
                continue
            if scope is not None and entry.scope != scope:
                continue
            results.append(self._entry_to_dict(entry, redact=True))
        results.sort(key=lambda d: d["key"])
        return results

    def get_all_variables(self, pipeline_name: str) -> Dict[str, Any]:
        """Return a flat key->value map for a pipeline (all scopes).

        Global-scoped variables are included first, then overridden by
        pipeline-scoped variables. Secret values are redacted.
        """
        self._stats["total_get"] += 1
        result: Dict[str, Any] = {}

        # Global scope first (lower priority)
        for entry in self._variables.values():
            if entry.pipeline_name != pipeline_name:
                continue
            if entry.scope == "global":
                val = SECRET_REDACTED if entry.is_secret else entry.value
                result[entry.key] = val

        # Pipeline scope overrides global
        for entry in self._variables.values():
            if entry.pipeline_name != pipeline_name:
                continue
            if entry.scope == "pipeline":
                val = SECRET_REDACTED if entry.is_secret else entry.value
                result[entry.key] = val

        return result

    # ------------------------------------------------------------------
    # Secret convenience
    # ------------------------------------------------------------------

    def set_secret(self, pipeline_name: str, key: str, value: Any) -> str:
        """Convenience wrapper to set a secret variable at pipeline scope."""
        return self.set_variable(
            pipeline_name, key, value, scope="pipeline", is_secret=True
        )

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a change callback. Returns False if name already exists."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a change callback by name."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, data: Dict) -> None:
        """Fire all registered callbacks."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("callback_error", action=action)

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Return store statistics."""
        scope_counts: Dict[str, int] = {}
        secret_count = 0
        for entry in self._variables.values():
            scope_counts[entry.scope] = scope_counts.get(entry.scope, 0) + 1
            if entry.is_secret:
                secret_count += 1

        return {
            **self._stats,
            "current_variables": len(self._variables),
            "current_secrets": secret_count,
            "by_scope": dict(sorted(scope_counts.items())),
            "max_entries": self._max_entries,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._variables.clear()
        self._index.clear()
        self._callbacks.clear()
        self._seq = 0
        self._stats = {k: 0 for k in self._stats}
        logger.info("store_reset")
