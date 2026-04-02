"""Pipeline Template Store — manages reusable pipeline templates.

Provides facilities to define, instantiate, version, and manage
pipeline templates with tag-based filtering and change notifications.

Features:
- Create and version pipeline templates
- Instantiate templates with optional overrides
- Tag-based filtering and search
- Change callbacks for reactive integrations
- Max-entries pruning for bounded memory usage
"""

from __future__ import annotations

import copy
import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TemplateEntry:
    """Internal representation of a pipeline template."""

    template_id: str = ""
    name: str = ""
    version: str = "1.0"
    steps: List[Dict[str, Any]] = field(default_factory=list)
    description: str = ""
    tags: List[str] = field(default_factory=list)
    created_at: float = 0.0
    updated_at: float = 0.0


# ---------------------------------------------------------------------------
# Pipeline Template Store
# ---------------------------------------------------------------------------

class PipelineTemplateStore:
    """Manages reusable pipeline templates (define, instantiate, version)."""

    def __init__(self, max_entries: int = 10000):
        self._max_entries = max_entries

        # template_id -> TemplateEntry
        self._templates: Dict[str, TemplateEntry] = {}

        # (name, version) -> template_id  — fast duplicate check
        self._name_version_index: Dict[tuple, str] = {}

        self._seq: int = 0
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_created": 0,
            "total_removed": 0,
            "total_updated": 0,
            "total_instantiated": 0,
            "total_pruned": 0,
        }

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self, seed: str) -> str:
        """Generate a collision-free ID with prefix ``pts-``."""
        self._seq += 1
        raw = f"{seed}:{time.time()}:{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"pts-{digest}"

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Remove oldest entries when the store exceeds *max_entries*."""
        if len(self._templates) <= self._max_entries:
            return
        sorted_entries = sorted(
            self._templates.values(), key=lambda t: t.created_at
        )
        remove_count = len(self._templates) - self._max_entries
        for entry in sorted_entries[:remove_count]:
            self._remove_entry(entry.template_id, pruning=True)
            self._stats["total_pruned"] += 1
            logger.debug("template_pruned", template_id=entry.template_id)

    def _remove_entry(self, template_id: str, *, pruning: bool = False) -> None:
        """Low-level removal shared by delete and prune paths."""
        entry = self._templates.get(template_id)
        if entry is None:
            return
        key = (entry.name, entry.version)
        self._name_version_index.pop(key, None)
        del self._templates[template_id]
        if not pruning:
            self._stats["total_removed"] += 1

    # ------------------------------------------------------------------
    # Template CRUD
    # ------------------------------------------------------------------

    def create_template(
        self,
        name: str,
        steps: List[Dict[str, Any]],
        description: str = "",
        tags: Optional[List[str]] = None,
        version: str = "1.0",
    ) -> str:
        """Create a new pipeline template.

        Returns the *template_id* on success, or ``""`` when a template
        with the same *name* + *version* already exists.
        """
        key = (name, version)
        if key in self._name_version_index:
            logger.warning(
                "duplicate_template",
                name=name,
                version=version,
            )
            return ""

        template_id = self._next_id(name)
        now = time.time()

        entry = TemplateEntry(
            template_id=template_id,
            name=name,
            version=version,
            steps=copy.deepcopy(steps),
            description=description,
            tags=list(tags) if tags else [],
            created_at=now,
            updated_at=now,
        )

        self._templates[template_id] = entry
        self._name_version_index[key] = template_id
        self._stats["total_created"] += 1

        logger.info(
            "template_created",
            template_id=template_id,
            name=name,
            version=version,
        )

        self._prune_if_needed()
        self._fire("created", self._to_dict(entry))
        return template_id

    def get_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        """Return template data by ID, or ``None`` if not found."""
        entry = self._templates.get(template_id)
        if entry is None:
            logger.debug("template_not_found", template_id=template_id)
            return None
        return self._to_dict(entry)

    def get_template_by_name(
        self,
        name: str,
        version: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Return template data by name.

        When *version* is ``None`` the latest version (highest
        ``updated_at``) is returned.
        """
        if version is not None:
            tid = self._name_version_index.get((name, version))
            if tid is None:
                return None
            return self.get_template(tid)

        # No version specified — find the latest one for this name.
        candidates = [
            e for e in self._templates.values() if e.name == name
        ]
        if not candidates:
            return None
        latest = max(candidates, key=lambda e: e.updated_at)
        return self._to_dict(latest)

    def update_template(
        self,
        template_id: str,
        steps: Optional[List[Dict[str, Any]]] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> bool:
        """Update mutable fields of an existing template.

        Returns ``True`` on success, ``False`` if the template does
        not exist.
        """
        entry = self._templates.get(template_id)
        if entry is None:
            logger.warning("update_not_found", template_id=template_id)
            return False

        if steps is not None:
            entry.steps = copy.deepcopy(steps)
        if description is not None:
            entry.description = description
        if tags is not None:
            entry.tags = list(tags)

        entry.updated_at = time.time()
        self._stats["total_updated"] += 1

        logger.info("template_updated", template_id=template_id)
        self._fire("updated", self._to_dict(entry))
        return True

    def remove_template(self, template_id: str) -> bool:
        """Remove a template by ID.

        Returns ``True`` when the template existed and was removed.
        """
        if template_id not in self._templates:
            logger.debug("remove_not_found", template_id=template_id)
            return False

        entry = self._templates[template_id]
        self._remove_entry(template_id)

        logger.info("template_removed", template_id=template_id)
        self._fire("removed", {"template_id": template_id, "name": entry.name})
        return True

    # ------------------------------------------------------------------
    # Instantiation
    # ------------------------------------------------------------------

    def instantiate(
        self,
        template_id: str,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create an independent copy of a template with optional overrides.

        Returns a dict representing the instantiated pipeline.  If the
        template does not exist an empty dict is returned.
        """
        entry = self._templates.get(template_id)
        if entry is None:
            logger.warning("instantiate_not_found", template_id=template_id)
            return {}

        instance = self._to_dict(entry)
        instance["instantiated_at"] = time.time()

        # Merge top-level overrides.
        if overrides:
            for key, value in overrides.items():
                if key in instance:
                    instance[key] = copy.deepcopy(value)

        self._stats["total_instantiated"] += 1
        logger.info(
            "template_instantiated",
            template_id=template_id,
            has_overrides=bool(overrides),
        )
        self._fire("instantiated", instance)
        return instance

    # ------------------------------------------------------------------
    # Listing & search
    # ------------------------------------------------------------------

    def list_templates(self, tag: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return all templates, optionally filtered by *tag*.

        Results are ordered newest-first by ``created_at``.
        """
        entries = sorted(
            self._templates.values(),
            key=lambda t: t.created_at,
            reverse=True,
        )

        if tag is not None:
            entries = [e for e in entries if tag in e.tags]

        return [self._to_dict(e) for e in entries]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a named change callback.

        Returns ``True`` if registration succeeded, ``False`` when a
        callback with the same *name* already exists.
        """
        if name in self._callbacks:
            logger.debug("callback_already_registered", name=name)
            return False
        self._callbacks[name] = callback
        logger.debug("callback_registered", name=name)
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback by *name*.

        Returns ``True`` when found and removed.
        """
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        logger.debug("callback_removed", name=name)
        return True

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        """Invoke all registered callbacks with *action* and *data*."""
        for cb_name, cb in list(self._callbacks.items()):
            try:
                cb(action, data)
            except Exception:
                logger.exception(
                    "callback_error", action=action, callback=cb_name
                )

    # ------------------------------------------------------------------
    # Serialisation helper
    # ------------------------------------------------------------------

    def _to_dict(self, entry: TemplateEntry) -> Dict[str, Any]:
        """Convert a :class:`TemplateEntry` to a plain dict."""
        return {
            "template_id": entry.template_id,
            "name": entry.name,
            "version": entry.version,
            "steps": copy.deepcopy(entry.steps),
            "description": entry.description,
            "tags": list(entry.tags),
            "created_at": entry.created_at,
            "updated_at": entry.updated_at,
        }

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics."""
        return {
            **self._stats,
            "current_templates": len(self._templates),
            "registered_callbacks": len(self._callbacks),
        }

    def reset(self) -> None:
        """Clear all templates, indexes, callbacks, and counters."""
        self._templates.clear()
        self._name_version_index.clear()
        self._callbacks.clear()
        self._seq = 0
        self._stats = {k: 0 for k in self._stats}
        logger.info("template_store_reset")
