"""Agent Task Decomposer – decompose complex tasks into subtask trees.

Breaks down tasks recursively into subtask hierarchies, tracks
decomposition depth, estimates effort, and identifies parallelizable
subtasks for optimal scheduling.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Task:
    task_id: str
    name: str
    description: str
    complexity: int  # 1-10
    estimated_effort: float
    parent_task: str
    parallelizable: bool
    status: str  # pending, active, completed
    depth: int
    tags: List[str]
    created_at: float
    completed_at: float


@dataclass
class _DecompEvent:
    event_id: str
    task_name: str
    action: str
    data: Dict[str, Any]
    timestamp: float


class AgentTaskDecomposer:
    """Decomposes complex tasks into subtask trees."""

    STATUSES = ("pending", "active", "completed")

    def __init__(self, max_tasks: int = 5000, max_history: int = 100000):
        self._tasks: Dict[str, _Task] = {}
        self._name_index: Dict[str, str] = {}  # name -> task_id
        self._children: Dict[str, List[str]] = {}  # task_id -> [child task_ids]
        self._history: List[_DecompEvent] = []
        self._callbacks: Dict[str, Callable] = {}
        self._max_tasks = max_tasks
        self._max_history = max_history
        self._seq = 0

        # stats
        self._total_created = 0
        self._total_decomposed = 0
        self._total_completed = 0
        self._total_removed = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _gen_id(self, prefix: str, seed: str) -> str:
        self._seq += 1
        raw = f"{seed}-{time.time()}-{self._seq}"
        return prefix + hashlib.sha256(raw.encode()).hexdigest()[:12]

    def _record(self, task_name: str, action: str, data: Dict[str, Any]) -> None:
        eid = self._gen_id("evt-", f"{task_name}-{action}")
        evt = _DecompEvent(
            event_id=eid,
            task_name=task_name,
            action=action,
            data=data,
            timestamp=time.time(),
        )
        self._history.append(evt)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    # ------------------------------------------------------------------
    # Task creation
    # ------------------------------------------------------------------

    def create_task(
        self,
        name: str,
        description: str = "",
        complexity: int = 5,
        estimated_effort: float = 1.0,
        tags: Optional[List[str]] = None,
    ) -> str:
        if not name:
            return ""
        if name in self._name_index:
            return ""
        if len(self._tasks) >= self._max_tasks:
            return ""

        complexity = max(1, min(10, complexity))
        tid = self._gen_id("tsk-", name)
        now = time.time()

        task = _Task(
            task_id=tid,
            name=name,
            description=description,
            complexity=complexity,
            estimated_effort=estimated_effort,
            parent_task="",
            parallelizable=False,
            status="pending",
            depth=0,
            tags=tags or [],
            created_at=now,
            completed_at=0.0,
        )
        self._tasks[tid] = task
        self._name_index[name] = tid
        self._children[tid] = []
        self._total_created += 1
        self._record(name, "task_created", {"task_id": tid})
        self._fire("task_created", {"task_id": tid, "name": name})
        return tid

    # ------------------------------------------------------------------
    # Decomposition
    # ------------------------------------------------------------------

    def decompose(self, task_name: str, subtasks: List[Dict[str, Any]]) -> List[str]:
        tid = self._name_index.get(task_name, "")
        if not tid:
            return []
        parent = self._tasks.get(tid)
        if not parent:
            return []
        if not subtasks:
            return []

        created_ids: List[str] = []
        child_depth = parent.depth + 1

        for s in subtasks:
            sub_name = s.get("name", "")
            if not sub_name or sub_name in self._name_index:
                continue
            if len(self._tasks) >= self._max_tasks:
                break

            complexity = max(1, min(10, s.get("complexity", 5)))
            sub_id = self._gen_id("tsk-", sub_name)
            now = time.time()

            sub_task = _Task(
                task_id=sub_id,
                name=sub_name,
                description=s.get("description", ""),
                complexity=complexity,
                estimated_effort=s.get("estimated_effort", 1.0),
                parent_task=tid,
                parallelizable=False,
                status="pending",
                depth=child_depth,
                tags=list(parent.tags),
                created_at=now,
                completed_at=0.0,
            )
            self._tasks[sub_id] = sub_task
            self._name_index[sub_name] = sub_id
            self._children[sub_id] = []
            self._children[tid].append(sub_id)
            self._total_created += 1
            created_ids.append(sub_id)

        if created_ids:
            self._total_decomposed += 1
            self._record(task_name, "decomposed", {
                "parent_id": tid,
                "subtask_ids": list(created_ids),
                "count": len(created_ids),
            })
            self._fire("task_decomposed", {
                "parent_name": task_name,
                "subtask_ids": list(created_ids),
            })

        return created_ids

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_task(self, name: str) -> Optional[Dict[str, Any]]:
        tid = self._name_index.get(name, "")
        if not tid:
            return None
        t = self._tasks.get(tid)
        if not t:
            return None

        children = self._children.get(tid, [])
        total_effort = self._compute_total_effort(tid)

        return {
            "task_id": t.task_id,
            "name": t.name,
            "description": t.description,
            "complexity": t.complexity,
            "estimated_effort": t.estimated_effort,
            "parent_task": t.parent_task,
            "parallelizable": t.parallelizable,
            "status": t.status,
            "depth": t.depth,
            "tags": list(t.tags),
            "created_at": t.created_at,
            "completed_at": t.completed_at,
            "subtask_count": len(children),
            "total_effort": total_effort,
            "is_leaf": len(children) == 0,
        }

    def get_decomposition_tree(self, name: str) -> Dict[str, Any]:
        tid = self._name_index.get(name, "")
        if not tid:
            return {}
        return self._build_tree(tid)

    def _build_tree(self, tid: str) -> Dict[str, Any]:
        t = self._tasks.get(tid)
        if not t:
            return {}
        children = self._children.get(tid, [])
        return {
            "task_id": t.task_id,
            "name": t.name,
            "description": t.description,
            "complexity": t.complexity,
            "estimated_effort": t.estimated_effort,
            "parallelizable": t.parallelizable,
            "status": t.status,
            "depth": t.depth,
            "is_leaf": len(children) == 0,
            "children": [self._build_tree(cid) for cid in children],
        }

    # ------------------------------------------------------------------
    # Parallelizable marking
    # ------------------------------------------------------------------

    def mark_parallelizable(self, task_name: str, parallel: bool = True) -> bool:
        tid = self._name_index.get(task_name, "")
        if not tid:
            return False
        t = self._tasks.get(tid)
        if not t:
            return False
        t.parallelizable = parallel
        self._record(task_name, "mark_parallelizable", {"parallel": parallel})
        self._fire("task_updated", {"task_id": tid, "parallelizable": parallel})
        return True

    # ------------------------------------------------------------------
    # Critical path & effort
    # ------------------------------------------------------------------

    def get_critical_path(self, root_name: str) -> List[Dict[str, Any]]:
        tid = self._name_index.get(root_name, "")
        if not tid:
            return []
        path = self._find_critical_path(tid)
        results: List[Dict[str, Any]] = []
        for pid in path:
            t = self._tasks.get(pid)
            if t:
                results.append({
                    "task_id": t.task_id,
                    "name": t.name,
                    "estimated_effort": t.estimated_effort,
                    "depth": t.depth,
                    "parallelizable": t.parallelizable,
                })
        return results

    def _find_critical_path(self, tid: str) -> List[str]:
        children = self._children.get(tid, [])
        if not children:
            return [tid]

        # Among non-parallelizable children, find the one with the longest path
        # Parallelizable children run concurrently so we take max, not sum
        longest: List[str] = []
        longest_effort = 0.0

        sequential = [c for c in children if not self._tasks[c].parallelizable]
        parallel = [c for c in children if self._tasks[c].parallelizable]

        # For sequential children, each extends the path
        for cid in sequential:
            sub_path = self._find_critical_path(cid)
            sub_effort = sum(
                self._tasks[p].estimated_effort for p in sub_path if p in self._tasks
            )
            if sub_effort > longest_effort:
                longest_effort = sub_effort
                longest = sub_path

        # For parallel children, only the longest one matters
        for cid in parallel:
            sub_path = self._find_critical_path(cid)
            sub_effort = sum(
                self._tasks[p].estimated_effort for p in sub_path if p in self._tasks
            )
            if sub_effort > longest_effort:
                longest_effort = sub_effort
                longest = sub_path

        return [tid] + longest

    def estimate_total_effort(self, root_name: str) -> float:
        tid = self._name_index.get(root_name, "")
        if not tid:
            return 0.0
        return self._compute_total_effort(tid)

    def _compute_total_effort(self, tid: str) -> float:
        children = self._children.get(tid, [])
        if not children:
            t = self._tasks.get(tid)
            return t.estimated_effort if t else 0.0

        sequential = [c for c in children if not self._tasks[c].parallelizable]
        parallel = [c for c in children if self._tasks[c].parallelizable]

        total = 0.0
        for cid in sequential:
            total += self._compute_total_effort(cid)

        if parallel:
            total += max(self._compute_total_effort(cid) for cid in parallel)

        return total

    # ------------------------------------------------------------------
    # Leaf operations
    # ------------------------------------------------------------------

    def get_leaves(self, root_name: str) -> List[Dict[str, Any]]:
        tid = self._name_index.get(root_name, "")
        if not tid:
            return []
        leaf_ids = self._collect_leaves(tid)
        results: List[Dict[str, Any]] = []
        for lid in leaf_ids:
            t = self._tasks.get(lid)
            if t:
                results.append({
                    "task_id": t.task_id,
                    "name": t.name,
                    "estimated_effort": t.estimated_effort,
                    "status": t.status,
                    "depth": t.depth,
                    "parallelizable": t.parallelizable,
                })
        return results

    def _collect_leaves(self, tid: str) -> List[str]:
        children = self._children.get(tid, [])
        if not children:
            return [tid]
        leaves: List[str] = []
        for cid in children:
            leaves.extend(self._collect_leaves(cid))
        return leaves

    # ------------------------------------------------------------------
    # Task completion
    # ------------------------------------------------------------------

    def complete_task(self, name: str) -> bool:
        tid = self._name_index.get(name, "")
        if not tid:
            return False
        t = self._tasks.get(tid)
        if not t or t.status == "completed":
            return False
        t.status = "completed"
        t.completed_at = time.time()
        self._total_completed += 1
        self._record(name, "task_completed", {"task_id": tid})
        self._fire("task_completed", {"task_id": tid, "name": name})
        return True

    def get_completion_pct(self, root_name: str) -> float:
        tid = self._name_index.get(root_name, "")
        if not tid:
            return 0.0
        leaves = self._collect_leaves(tid)
        if not leaves:
            return 0.0
        completed = sum(
            1 for lid in leaves
            if lid in self._tasks and self._tasks[lid].status == "completed"
        )
        return (completed / len(leaves)) * 100.0

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_tasks(
        self,
        parent: str = "",
        status: str = "",
        tag: str = "",
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for t in self._tasks.values():
            if parent:
                parent_tid = self._name_index.get(parent, "")
                if t.parent_task != parent_tid:
                    continue
            if status and t.status != status:
                continue
            if tag and tag not in t.tags:
                continue
            children = self._children.get(t.task_id, [])
            results.append({
                "task_id": t.task_id,
                "name": t.name,
                "description": t.description,
                "complexity": t.complexity,
                "estimated_effort": t.estimated_effort,
                "parent_task": t.parent_task,
                "parallelizable": t.parallelizable,
                "status": t.status,
                "depth": t.depth,
                "tags": list(t.tags),
                "subtask_count": len(children),
                "is_leaf": len(children) == 0,
            })
        return results

    # ------------------------------------------------------------------
    # Removal
    # ------------------------------------------------------------------

    def remove_task(self, name: str) -> bool:
        tid = self._name_index.get(name, "")
        if not tid:
            return False
        self._remove_recursive(tid)
        self._total_removed += 1
        self._record(name, "task_removed", {"task_id": tid})
        self._fire("task_removed", {"task_id": tid, "name": name})
        return True

    def _remove_recursive(self, tid: str) -> None:
        children = self._children.get(tid, [])
        for cid in list(children):
            self._remove_recursive(cid)

        t = self._tasks.pop(tid, None)
        if t:
            self._name_index.pop(t.name, None)

        # Remove from parent's children list
        if t and t.parent_task:
            parent_children = self._children.get(t.parent_task, [])
            if tid in parent_children:
                parent_children.remove(tid)

        self._children.pop(tid, None)

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        entries = self._history[-limit:] if limit < len(self._history) else list(self._history)
        return [
            {
                "event_id": e.event_id,
                "task_name": e.task_name,
                "action": e.action,
                "data": dict(e.data),
                "timestamp": e.timestamp,
            }
            for e in reversed(entries)
        ]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        return {
            "current_tasks": len(self._tasks),
            "total_created": self._total_created,
            "total_decomposed": self._total_decomposed,
            "total_completed": self._total_completed,
            "total_removed": self._total_removed,
            "history_size": len(self._history),
            "pending_count": sum(1 for t in self._tasks.values() if t.status == "pending"),
            "completed_count": sum(1 for t in self._tasks.values() if t.status == "completed"),
            "leaf_count": sum(
                1 for tid in self._tasks if not self._children.get(tid, [])
            ),
        }

    def reset(self) -> None:
        self._tasks.clear()
        self._name_index.clear()
        self._children.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_created = 0
        self._total_decomposed = 0
        self._total_completed = 0
        self._total_removed = 0
