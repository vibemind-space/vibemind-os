"""
Pipeline Template Registry — stores and manages reusable pipeline templates.

Features:
- Template CRUD with versioning
- Parameterized templates with variable substitution
- Template categories and tagging
- Template instantiation (create plan from template)
- Template validation
- Import/export
- Usage tracking
"""

from __future__ import annotations

import copy
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PipelineTemplate:
    """A reusable pipeline template."""
    template_id: str
    name: str
    version: int
    description: str
    category: str
    created_at: float
    updated_at: float
    author: str
    steps: List[Dict[str, Any]]  # [{name, duration, dependencies, tags, params}]
    parameters: Dict[str, Any]  # {param_name: default_value}
    tags: Set[str]
    metadata: Dict[str, Any]
    usage_count: int = 0


# ---------------------------------------------------------------------------
# Pipeline Template Registry
# ---------------------------------------------------------------------------

class PipelineTemplateRegistry:
    """Stores and manages reusable pipeline templates."""

    def __init__(self, max_templates: int = 500):
        self._max_templates = max_templates
        self._templates: Dict[str, PipelineTemplate] = {}

        self._stats = {
            "total_created": 0,
            "total_instantiated": 0,
            "total_deleted": 0,
        }

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(
        self,
        name: str,
        steps: List[Dict],
        description: str = "",
        category: str = "general",
        author: str = "",
        parameters: Optional[Dict] = None,
        tags: Optional[Set[str]] = None,
        metadata: Optional[Dict] = None,
    ) -> str:
        """Create a new template. Returns template_id."""
        tid = f"tmpl-{uuid.uuid4().hex[:8]}"
        now = time.time()

        # Auto-version
        version = 1
        for t in self._templates.values():
            if t.name == name:
                version = max(version, t.version + 1)

        self._templates[tid] = PipelineTemplate(
            template_id=tid,
            name=name,
            version=version,
            description=description,
            category=category,
            created_at=now,
            updated_at=now,
            author=author,
            steps=steps,
            parameters=parameters or {},
            tags=tags or set(),
            metadata=metadata or {},
        )
        self._stats["total_created"] += 1
        self._prune()
        return tid

    def get(self, template_id: str) -> Optional[Dict]:
        """Get a template by ID."""
        t = self._templates.get(template_id)
        if not t:
            return None
        return self._template_to_dict(t)

    def get_by_name(self, name: str, version: Optional[int] = None) -> Optional[Dict]:
        """Get a template by name (latest version or specific)."""
        matches = [t for t in self._templates.values() if t.name == name]
        if not matches:
            return None
        if version is not None:
            for t in matches:
                if t.version == version:
                    return self._template_to_dict(t)
            return None
        latest = max(matches, key=lambda t: t.version)
        return self._template_to_dict(latest)

    def update(
        self,
        template_id: str,
        steps: Optional[List[Dict]] = None,
        description: Optional[str] = None,
        category: Optional[str] = None,
        parameters: Optional[Dict] = None,
        tags: Optional[Set[str]] = None,
        metadata: Optional[Dict] = None,
    ) -> bool:
        """Update a template."""
        t = self._templates.get(template_id)
        if not t:
            return False
        if steps is not None:
            t.steps = steps
        if description is not None:
            t.description = description
        if category is not None:
            t.category = category
        if parameters is not None:
            t.parameters = parameters
        if tags is not None:
            t.tags = tags
        if metadata is not None:
            t.metadata = metadata
        t.updated_at = time.time()
        return True

    def delete(self, template_id: str) -> bool:
        """Delete a template."""
        if template_id not in self._templates:
            return False
        del self._templates[template_id]
        self._stats["total_deleted"] += 1
        return True

    # ------------------------------------------------------------------
    # Search & listing
    # ------------------------------------------------------------------

    def list_templates(
        self,
        category: Optional[str] = None,
        author: Optional[str] = None,
        tags: Optional[Set[str]] = None,
        name: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """List templates with filters."""
        results = []
        for t in sorted(self._templates.values(),
                        key=lambda x: x.updated_at, reverse=True):
            if category and t.category != category:
                continue
            if author and t.author != author:
                continue
            if name and t.name != name:
                continue
            if tags and not tags.issubset(t.tags):
                continue
            results.append(self._template_to_dict(t))
            if len(results) >= limit:
                break
        return results

    def list_categories(self) -> Dict[str, int]:
        """List categories with counts."""
        counts: Dict[str, int] = defaultdict(int)
        for t in self._templates.values():
            counts[t.category] += 1
        return dict(sorted(counts.items()))

    def list_names(self) -> List[str]:
        """List unique template names."""
        return sorted(set(t.name for t in self._templates.values()))

    def search(self, query: str, limit: int = 20) -> List[Dict]:
        """Search templates by name or description."""
        q = query.lower()
        results = []
        for t in self._templates.values():
            if q in t.name.lower() or q in t.description.lower():
                results.append(self._template_to_dict(t))
                if len(results) >= limit:
                    break
        return results

    # ------------------------------------------------------------------
    # Instantiation
    # ------------------------------------------------------------------

    def instantiate(
        self,
        template_id: str,
        params: Optional[Dict] = None,
    ) -> Optional[List[Dict]]:
        """Create a step list from a template with parameter substitution.
        Returns list of steps with params applied."""
        t = self._templates.get(template_id)
        if not t:
            return None

        # Merge defaults with provided params
        effective_params = {**t.parameters, **(params or {})}

        # Deep copy steps and substitute
        steps = copy.deepcopy(t.steps)
        for step in steps:
            for key, value in step.items():
                if isinstance(value, str):
                    for pname, pval in effective_params.items():
                        step[key] = step[key].replace(f"${{{pname}}}", str(pval))
                elif isinstance(value, list):
                    step[key] = [
                        self._substitute(item, effective_params)
                        if isinstance(item, str) else item
                        for item in value
                    ]

        t.usage_count += 1
        self._stats["total_instantiated"] += 1
        return steps

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self, template_id: str) -> Dict:
        """Validate a template."""
        t = self._templates.get(template_id)
        if not t:
            return {"valid": False, "errors": ["Template not found"]}

        errors = []
        warnings = []

        if not t.steps:
            errors.append("Template has no steps")

        # Check step names
        step_names = set()
        for i, step in enumerate(t.steps):
            name = step.get("name", "")
            if not name:
                errors.append(f"Step {i} has no name")
            elif name in step_names:
                errors.append(f"Duplicate step name: {name}")
            step_names.add(name)

        # Check dependencies
        for step in t.steps:
            for dep in step.get("dependencies", []):
                if dep not in step_names:
                    errors.append(f"Step '{step.get('name')}' depends on unknown step '{dep}'")

        if not t.description:
            warnings.append("Template has no description")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "step_count": len(t.steps),
            "parameter_count": len(t.parameters),
        }

    # ------------------------------------------------------------------
    # Export / Import
    # ------------------------------------------------------------------

    def export_template(self, template_id: str) -> Optional[Dict]:
        """Export a template as a portable dict."""
        t = self._templates.get(template_id)
        if not t:
            return None
        return {
            "name": t.name,
            "version": t.version,
            "description": t.description,
            "category": t.category,
            "author": t.author,
            "steps": t.steps,
            "parameters": t.parameters,
            "tags": sorted(t.tags),
            "metadata": t.metadata,
        }

    def import_template(self, data: Dict) -> Optional[str]:
        """Import a template from a portable dict. Returns template_id."""
        name = data.get("name", "")
        steps = data.get("steps", [])
        if not name or not steps:
            return None
        return self.create(
            name=name,
            steps=steps,
            description=data.get("description", ""),
            category=data.get("category", "general"),
            author=data.get("author", ""),
            parameters=data.get("parameters"),
            tags=set(data.get("tags", [])),
            metadata=data.get("metadata"),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _substitute(self, text: str, params: Dict[str, Any]) -> str:
        """Substitute parameters in a string."""
        for pname, pval in params.items():
            text = text.replace(f"${{{pname}}}", str(pval))
        return text

    def _template_to_dict(self, t: PipelineTemplate) -> Dict:
        return {
            "template_id": t.template_id,
            "name": t.name,
            "version": t.version,
            "description": t.description,
            "category": t.category,
            "author": t.author,
            "created_at": t.created_at,
            "updated_at": t.updated_at,
            "step_count": len(t.steps),
            "parameters": list(t.parameters.keys()),
            "tags": sorted(t.tags),
            "usage_count": t.usage_count,
        }

    def _prune(self) -> None:
        if len(self._templates) <= self._max_templates:
            return
        # Remove least-used templates
        by_usage = sorted(self._templates.values(), key=lambda t: t.usage_count)
        to_remove = len(self._templates) - self._max_templates
        for t in by_usage[:to_remove]:
            del self._templates[t.template_id]

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "total_templates": len(self._templates),
            "total_categories": len(set(t.category for t in self._templates.values())),
        }

    def reset(self) -> None:
        self._templates.clear()
        self._stats = {k: 0 for k in self._stats}
