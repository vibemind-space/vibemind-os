"""Pipeline Workflow Template – manages reusable workflow templates.

Templates define step sequences with conditions, timeouts, and retry
policies.  Instances are created from templates and track execution.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Template:
    template_id: str
    name: str
    description: str
    steps: List[Dict[str, Any]]
    tags: List[str]
    version: int
    created_at: float
    updated_at: float


@dataclass
class _Instance:
    instance_id: str
    template_name: str
    status: str  # pending, running, completed, failed
    current_step: int
    step_results: List[Dict[str, Any]]
    context: Dict[str, Any]
    created_at: float
    updated_at: float


class PipelineWorkflowTemplate:
    """Manages reusable workflow templates."""

    def __init__(self, max_templates: int = 5000, max_instances: int = 50000, max_history: int = 100000):
        self._templates: Dict[str, _Template] = {}
        self._name_index: Dict[str, str] = {}
        self._instances: Dict[str, _Instance] = {}
        self._history: List[Dict[str, Any]] = []
        self._callbacks: Dict[str, Callable] = {}
        self._max_templates = max_templates
        self._max_instances = max_instances
        self._max_history = max_history
        self._seq = 0
        self._total_templates = 0
        self._total_instances = 0

    def create_template(self, name: str, steps: List[Dict[str, Any]], description: str = "", tags: Optional[List[str]] = None) -> str:
        if not name or not steps:
            return ""
        if name in self._name_index or len(self._templates) >= self._max_templates:
            return ""
        self._seq += 1
        now = time.time()
        raw = f"{name}-{now}-{self._seq}"
        tid = "tmpl-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        tmpl = _Template(template_id=tid, name=name, description=description, steps=list(steps), tags=tags or [], version=1, created_at=now, updated_at=now)
        self._templates[tid] = tmpl
        self._name_index[name] = tid
        self._total_templates += 1
        self._fire("template_created", {"name": name, "steps": len(steps)})
        return tid

    def update_template(self, name: str, steps: List[Dict[str, Any]], description: str = "") -> bool:
        tid = self._name_index.get(name)
        if not tid or not steps:
            return False
        tmpl = self._templates[tid]
        tmpl.steps = list(steps)
        if description:
            tmpl.description = description
        tmpl.version += 1
        tmpl.updated_at = time.time()
        return True

    def get_template(self, name: str) -> Optional[Dict[str, Any]]:
        tid = self._name_index.get(name)
        if not tid:
            return None
        t = self._templates[tid]
        return {"template_id": t.template_id, "name": t.name, "description": t.description, "steps": list(t.steps), "tags": list(t.tags), "version": t.version, "created_at": t.created_at, "updated_at": t.updated_at}

    def remove_template(self, name: str) -> bool:
        tid = self._name_index.pop(name, None)
        if not tid:
            return False
        self._templates.pop(tid, None)
        return True

    def instantiate(self, template_name: str, context: Optional[Dict[str, Any]] = None) -> str:
        tid = self._name_index.get(template_name)
        if not tid or len(self._instances) >= self._max_instances:
            return ""
        self._seq += 1
        now = time.time()
        raw = f"{template_name}-{now}-{self._seq}"
        iid = "wfi-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        inst = _Instance(instance_id=iid, template_name=template_name, status="pending", current_step=0, step_results=[], context=context or {}, created_at=now, updated_at=now)
        self._instances[iid] = inst
        self._total_instances += 1
        self._fire("instance_created", {"instance_id": iid, "template": template_name})
        return iid

    def advance_step(self, instance_id: str, result: Any = None) -> bool:
        inst = self._instances.get(instance_id)
        if not inst or inst.status not in ("pending", "running"):
            return False
        tid = self._name_index.get(inst.template_name)
        if not tid:
            return False
        tmpl = self._templates[tid]
        inst.step_results.append({"step": inst.current_step, "result": result, "timestamp": time.time()})
        inst.current_step += 1
        inst.status = "running"
        inst.updated_at = time.time()
        if inst.current_step >= len(tmpl.steps):
            inst.status = "completed"
            self._fire("instance_completed", {"instance_id": instance_id})
        return True

    def fail_instance(self, instance_id: str, error: str = "") -> bool:
        inst = self._instances.get(instance_id)
        if not inst or inst.status not in ("pending", "running"):
            return False
        inst.status = "failed"
        inst.updated_at = time.time()
        self._fire("instance_failed", {"instance_id": instance_id, "error": error})
        return True

    def get_instance(self, instance_id: str) -> Optional[Dict[str, Any]]:
        inst = self._instances.get(instance_id)
        if not inst:
            return None
        return {"instance_id": inst.instance_id, "template_name": inst.template_name, "status": inst.status, "current_step": inst.current_step, "step_results": list(inst.step_results), "context": dict(inst.context), "created_at": inst.created_at, "updated_at": inst.updated_at}

    def list_templates(self, tag: str = "") -> List[Dict[str, Any]]:
        results = []
        for t in self._templates.values():
            if tag and tag not in t.tags:
                continue
            results.append(self.get_template(t.name))
        return [r for r in results if r]

    def list_instances(self, template_name: str = "", status: str = "") -> List[Dict[str, Any]]:
        results = []
        for inst in self._instances.values():
            if template_name and inst.template_name != template_name:
                continue
            if status and inst.status != status:
                continue
            results.append(self.get_instance(inst.instance_id))
        return [r for r in results if r]

    def on_change(self, name: str, callback: Callable) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        return self._callbacks.pop(name, None) is not None

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    def get_stats(self) -> Dict[str, Any]:
        running = sum(1 for i in self._instances.values() if i.status == "running")
        return {"current_templates": len(self._templates), "current_instances": len(self._instances), "running_instances": running, "total_templates": self._total_templates, "total_instances": self._total_instances}

    def reset(self) -> None:
        self._templates.clear()
        self._name_index.clear()
        self._instances.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_templates = 0
        self._total_instances = 0
