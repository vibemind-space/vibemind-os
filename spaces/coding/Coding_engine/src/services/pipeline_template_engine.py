"""Pipeline template engine.

Manages reusable pipeline templates that define stage sequences,
parameter schemas, and default configurations. Templates can be
instantiated into pipeline runs with custom parameters.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Template:
    """A pipeline template."""
    template_id: str = ""
    name: str = ""
    description: str = ""
    stages: List[str] = field(default_factory=list)
    parameters: Dict = field(default_factory=dict)
    defaults: Dict = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    version: int = 1
    status: str = "draft"  # draft, published, archived
    created_at: float = 0.0
    updated_at: float = 0.0
    seq: int = 0


@dataclass
class _Instance:
    """An instantiated template run."""
    instance_id: str = ""
    template_id: str = ""
    template_name: str = ""
    parameters: Dict = field(default_factory=dict)
    status: str = "created"  # created, running, completed, failed, cancelled
    result: Dict = field(default_factory=dict)
    created_at: float = 0.0
    completed_at: float = 0.0
    seq: int = 0


class PipelineTemplateEngine:
    """Manages pipeline templates and instances."""

    TEMPLATE_STATUSES = ("draft", "published", "archived")
    INSTANCE_STATUSES = ("created", "running", "completed", "failed", "cancelled")

    def __init__(self, max_templates: int = 5000,
                 max_instances: int = 100000):
        self._max_templates = max_templates
        self._max_instances = max_instances
        self._templates: Dict[str, _Template] = {}
        self._instances: Dict[str, _Instance] = {}
        self._template_seq = 0
        self._instance_seq = 0
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_templates_created": 0,
            "total_published": 0,
            "total_archived": 0,
            "total_instances_created": 0,
            "total_completed": 0,
            "total_failed": 0,
        }

    # ------------------------------------------------------------------
    # Templates
    # ------------------------------------------------------------------

    def create_template(self, name: str, description: str = "",
                        stages: Optional[List[str]] = None,
                        parameters: Optional[Dict] = None,
                        defaults: Optional[Dict] = None,
                        tags: Optional[List[str]] = None) -> str:
        """Create a new template."""
        if not name:
            return ""
        if len(self._templates) >= self._max_templates:
            return ""

        self._template_seq += 1
        tid = "tmpl-" + hashlib.md5(
            f"{name}{time.time()}{self._template_seq}".encode()
        ).hexdigest()[:12]

        self._templates[tid] = _Template(
            template_id=tid,
            name=name,
            description=description,
            stages=stages or [],
            parameters=parameters or {},
            defaults=defaults or {},
            tags=tags or [],
            created_at=time.time(),
            updated_at=time.time(),
            seq=self._template_seq,
        )
        self._stats["total_templates_created"] += 1
        self._fire("template_created", {
            "template_id": tid, "name": name,
        })
        return tid

    def get_template(self, template_id: str) -> Optional[Dict]:
        """Get template info."""
        t = self._templates.get(template_id)
        if not t:
            return None
        return {
            "template_id": t.template_id,
            "name": t.name,
            "description": t.description,
            "stages": list(t.stages),
            "parameters": dict(t.parameters),
            "defaults": dict(t.defaults),
            "tags": list(t.tags),
            "version": t.version,
            "status": t.status,
            "instance_count": sum(
                1 for i in self._instances.values()
                if i.template_id == template_id
            ),
        }

    def publish_template(self, template_id: str) -> bool:
        """Publish a template."""
        t = self._templates.get(template_id)
        if not t or t.status != "draft":
            return False
        t.status = "published"
        t.updated_at = time.time()
        self._stats["total_published"] += 1
        return True

    def archive_template(self, template_id: str) -> bool:
        """Archive a template."""
        t = self._templates.get(template_id)
        if not t or t.status == "archived":
            return False
        t.status = "archived"
        t.updated_at = time.time()
        self._stats["total_archived"] += 1
        return True

    def update_template(self, template_id: str,
                        description: Optional[str] = None,
                        stages: Optional[List[str]] = None,
                        parameters: Optional[Dict] = None,
                        defaults: Optional[Dict] = None) -> bool:
        """Update a draft template."""
        t = self._templates.get(template_id)
        if not t or t.status != "draft":
            return False
        if description is not None:
            t.description = description
        if stages is not None:
            t.stages = stages
        if parameters is not None:
            t.parameters = parameters
        if defaults is not None:
            t.defaults = defaults
        t.version += 1
        t.updated_at = time.time()
        return True

    def remove_template(self, template_id: str) -> bool:
        """Remove a template."""
        if template_id not in self._templates:
            return False
        del self._templates[template_id]
        return True

    # ------------------------------------------------------------------
    # Instances
    # ------------------------------------------------------------------

    def instantiate(self, template_id: str,
                    parameters: Optional[Dict] = None) -> str:
        """Create an instance from a template."""
        t = self._templates.get(template_id)
        if not t or t.status != "published":
            return ""
        if len(self._instances) >= self._max_instances:
            self._prune_instances()

        self._instance_seq += 1
        iid = "inst-" + hashlib.md5(
            f"{template_id}{time.time()}{self._instance_seq}".encode()
        ).hexdigest()[:12]

        # Merge defaults with provided parameters
        merged_params = dict(t.defaults)
        if parameters:
            merged_params.update(parameters)

        self._instances[iid] = _Instance(
            instance_id=iid,
            template_id=template_id,
            template_name=t.name,
            parameters=merged_params,
            created_at=time.time(),
            seq=self._instance_seq,
        )
        self._stats["total_instances_created"] += 1
        self._fire("instance_created", {
            "instance_id": iid, "template_id": template_id,
        })
        return iid

    def get_instance(self, instance_id: str) -> Optional[Dict]:
        """Get instance info."""
        i = self._instances.get(instance_id)
        if not i:
            return None
        return {
            "instance_id": i.instance_id,
            "template_id": i.template_id,
            "template_name": i.template_name,
            "parameters": dict(i.parameters),
            "status": i.status,
            "result": dict(i.result),
            "seq": i.seq,
        }

    def start_instance(self, instance_id: str) -> bool:
        """Start an instance."""
        i = self._instances.get(instance_id)
        if not i or i.status != "created":
            return False
        i.status = "running"
        return True

    def complete_instance(self, instance_id: str,
                          result: Optional[Dict] = None) -> bool:
        """Complete an instance."""
        i = self._instances.get(instance_id)
        if not i or i.status != "running":
            return False
        i.status = "completed"
        i.result = result or {}
        i.completed_at = time.time()
        self._stats["total_completed"] += 1
        return True

    def fail_instance(self, instance_id: str,
                      error: str = "") -> bool:
        """Fail an instance."""
        i = self._instances.get(instance_id)
        if not i or i.status != "running":
            return False
        i.status = "failed"
        i.result = {"error": error}
        i.completed_at = time.time()
        self._stats["total_failed"] += 1
        return True

    def cancel_instance(self, instance_id: str) -> bool:
        """Cancel an instance."""
        i = self._instances.get(instance_id)
        if not i or i.status in ("completed", "failed", "cancelled"):
            return False
        i.status = "cancelled"
        i.completed_at = time.time()
        return True

    def remove_instance(self, instance_id: str) -> bool:
        """Remove an instance."""
        if instance_id not in self._instances:
            return False
        del self._instances[instance_id]
        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def search_templates(self, status: Optional[str] = None,
                         tag: Optional[str] = None,
                         limit: int = 100) -> List[Dict]:
        """Search templates."""
        result = []
        for t in self._templates.values():
            if status and t.status != status:
                continue
            if tag and tag not in t.tags:
                continue
            result.append({
                "template_id": t.template_id,
                "name": t.name,
                "status": t.status,
                "version": t.version,
                "stage_count": len(t.stages),
                "seq": t.seq,
            })
        result.sort(key=lambda x: -x["seq"])
        return result[:limit]

    def list_instances(self, template_id: Optional[str] = None,
                       status: Optional[str] = None,
                       limit: int = 100) -> List[Dict]:
        """List instances."""
        result = []
        for i in self._instances.values():
            if template_id and i.template_id != template_id:
                continue
            if status and i.status != status:
                continue
            result.append({
                "instance_id": i.instance_id,
                "template_id": i.template_id,
                "template_name": i.template_name,
                "status": i.status,
                "seq": i.seq,
            })
        result.sort(key=lambda x: -x["seq"])
        return result[:limit]

    def get_template_usage(self, limit: int = 10) -> List[Dict]:
        """Get most-used templates."""
        usage: Dict[str, int] = {}
        names: Dict[str, str] = {}
        for i in self._instances.values():
            usage[i.template_id] = usage.get(i.template_id, 0) + 1
            names[i.template_id] = i.template_name

        result = [
            {"template_id": tid, "name": names[tid], "instance_count": c}
            for tid, c in usage.items()
        ]
        result.sort(key=lambda x: -x["instance_count"])
        return result[:limit]

    def get_success_rate(self, template_id: Optional[str] = None) -> Dict:
        """Get instance success rate."""
        total = 0
        completed = 0
        failed = 0
        for i in self._instances.values():
            if template_id and i.template_id != template_id:
                continue
            if i.status in ("completed", "failed"):
                total += 1
                if i.status == "completed":
                    completed += 1
                else:
                    failed += 1

        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "success_rate": round(
                (completed / total * 100) if total > 0 else 0.0, 1
            ),
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _prune_instances(self) -> None:
        """Remove oldest completed/failed/cancelled instances."""
        prunable = [(k, v) for k, v in self._instances.items()
                    if v.status in ("completed", "failed", "cancelled")]
        prunable.sort(key=lambda x: x[1].seq)
        to_remove = max(len(prunable) // 2, len(self._instances) // 4)
        for k, _ in prunable[:to_remove]:
            del self._instances[k]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, data: Dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "current_templates": len(self._templates),
            "published_templates": sum(
                1 for t in self._templates.values() if t.status == "published"
            ),
            "current_instances": len(self._instances),
            "running_instances": sum(
                1 for i in self._instances.values() if i.status == "running"
            ),
        }

    def reset(self) -> None:
        self._templates.clear()
        self._instances.clear()
        self._template_seq = 0
        self._instance_seq = 0
        self._stats = {k: 0 for k in self._stats}
