"""Agent task template service for managing reusable task templates for agents."""

import time
import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentTaskTemplateState:
    """State container for the agent task template."""
    entries: dict = field(default_factory=dict)
    _seq: int = 0


class AgentTaskTemplate:
    """Manages reusable task templates for agents - predefined task configurations."""

    PREFIX = "att-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentTaskTemplateState()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Optional[Callable] = None

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _prune(self) -> None:
        while len(self._state.entries) > self.MAX_ENTRIES:
            oldest_key = next(iter(self._state.entries))
            del self._state.entries[oldest_key]
            logger.debug("Pruned entry %s", oldest_key)

    def _fire(self, event: str, data: Any = None) -> None:
        if self._on_change:
            try:
                self._on_change(event, data)
            except Exception:
                logger.exception("on_change callback error")
        for cb_id, cb in list(self._callbacks.items()):
            try:
                cb(event, data)
            except Exception:
                logger.exception("Callback %s error", cb_id)

    @property
    def on_change(self) -> Optional[Callable]:
        """Get the global change callback."""
        return self._on_change

    @on_change.setter
    def on_change(self, callback: Optional[Callable]) -> None:
        """Set the global change callback."""
        self._on_change = callback

    def register_callback(self, callback_id: str, callback: Callable) -> None:
        """Register a named callback."""
        self._callbacks[callback_id] = callback

    def remove_callback(self, callback_id: str) -> bool:
        """Remove a named callback. Returns True if it existed."""
        if callback_id in self._callbacks:
            del self._callbacks[callback_id]
            return True
        return False

    def register_template(self, name: str, task_type: str, default_params: Optional[dict] = None, metadata: Optional[dict] = None) -> str:
        """Register a task template. Returns template_id."""
        template_id = self._generate_id(name)
        self._state.entries[template_id] = {
            "template_id": template_id,
            "name": name,
            "task_type": task_type,
            "default_params": default_params or {},
            "metadata": metadata or {},
            "created_at": time.time(),
            "usage_count": 0,
        }
        self._prune()
        self._fire("template_registered", {"template_id": template_id, "name": name})
        logger.info("Registered template %s (name=%s, task_type=%s)", template_id, name, task_type)
        return template_id

    def instantiate(self, template_id: str, overrides: Optional[dict] = None) -> dict:
        """Create a task instance from a template. Returns instance dict or empty dict if not found."""
        entry = self._state.entries.get(template_id)
        if entry is None:
            logger.warning("Template %s not found", template_id)
            return {}
        merged = dict(entry["default_params"])
        if overrides:
            merged.update(overrides)
        entry["usage_count"] += 1
        instance_id = self._generate_id(template_id)
        instance = {
            "template_id": template_id,
            "task_type": entry["task_type"],
            "params": merged,
            "instance_id": instance_id,
        }
        self._fire("template_instantiated", {"template_id": template_id, "instance_id": instance_id})
        logger.info("Instantiated template %s -> instance %s", template_id, instance_id)
        return instance

    def get_template(self, template_id: str) -> dict:
        """Get a template by ID. Returns empty dict if not found."""
        entry = self._state.entries.get(template_id)
        if entry is None:
            return {}
        return dict(entry)

    def get_templates(self, task_type: str = "") -> list:
        """List templates, optionally filtered by task_type."""
        results = []
        for entry in self._state.entries.values():
            if not task_type or entry["task_type"] == task_type:
                results.append(dict(entry))
        return results

    def get_template_count(self) -> int:
        """Get the total number of templates."""
        return len(self._state.entries)

    def remove_template(self, template_id: str) -> bool:
        """Remove a template. Returns True if it existed."""
        if template_id in self._state.entries:
            del self._state.entries[template_id]
            self._fire("template_removed", {"template_id": template_id})
            logger.info("Removed template %s", template_id)
            return True
        return False

    def get_most_used(self, limit: int = 5) -> list:
        """Return templates sorted by usage_count descending."""
        sorted_entries = sorted(
            self._state.entries.values(),
            key=lambda e: e["usage_count"],
            reverse=True,
        )
        return [dict(e) for e in sorted_entries[:limit]]

    def get_stats(self) -> dict:
        """Get statistics about the template system."""
        total_instantiations = sum(e["usage_count"] for e in self._state.entries.values())
        unique_task_types = set(e["task_type"] for e in self._state.entries.values())
        return {
            "total_templates": len(self._state.entries),
            "total_instantiations": total_instantiations,
            "unique_task_types": len(unique_task_types),
        }

    def reset(self) -> None:
        """Reset all state."""
        self._state = AgentTaskTemplateState()
        self._callbacks.clear()
        self._on_change = None
        logger.info("AgentTaskTemplate reset")
