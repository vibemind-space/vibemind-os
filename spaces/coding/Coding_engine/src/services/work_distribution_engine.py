"""
Work Distribution Engine — distributes work items to agents based on capacity and skills.

Features:
- Work item creation with requirements (skills, priority, estimated effort)
- Agent registration with capacity and skill sets
- Multiple distribution strategies (round-robin, least-loaded, skill-match, priority)
- Work item lifecycle (pending, assigned, in_progress, completed, failed)
- Load balancing and rebalancing
- Work item dependencies
- Distribution history and analytics
"""

from __future__ import annotations

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
class WorkItem:
    """A unit of work to distribute."""
    work_id: str
    name: str
    priority: int  # Higher = more important
    required_skills: Set[str]
    estimated_effort: float  # Hours
    created_at: float
    status: str  # "pending", "assigned", "in_progress", "completed", "failed"
    assigned_to: str
    started_at: float
    completed_at: float
    category: str
    metadata: Dict[str, Any]
    dependencies: Set[str]  # work_ids that must complete first


@dataclass
class Worker:
    """An agent that can process work."""
    name: str
    skills: Set[str]
    capacity: float  # Max concurrent effort units
    current_load: float  # Current effort assigned
    status: str  # "available", "busy", "offline"
    registered_at: float
    total_completed: int
    total_failed: int
    metadata: Dict[str, Any]


# ---------------------------------------------------------------------------
# Work Distribution Engine
# ---------------------------------------------------------------------------

class WorkDistributionEngine:
    """Distributes work items to agents based on capacity and skills."""

    def __init__(
        self,
        strategy: str = "skill_match",  # "round_robin", "least_loaded", "skill_match", "priority"
        max_items: int = 10000,
    ):
        self._strategy = strategy
        self._max_items = max_items
        self._workers: Dict[str, Worker] = {}
        self._items: Dict[str, WorkItem] = {}
        self._round_robin_idx = 0

        self._stats = {
            "total_created": 0,
            "total_assigned": 0,
            "total_completed": 0,
            "total_failed": 0,
            "total_rebalanced": 0,
        }

    # ------------------------------------------------------------------
    # Worker management
    # ------------------------------------------------------------------

    def register_worker(
        self,
        name: str,
        skills: Optional[Set[str]] = None,
        capacity: float = 1.0,
        metadata: Optional[Dict] = None,
    ) -> bool:
        """Register a worker."""
        if name in self._workers:
            return False
        self._workers[name] = Worker(
            name=name,
            skills=skills or set(),
            capacity=capacity,
            current_load=0.0,
            status="available",
            registered_at=time.time(),
            total_completed=0,
            total_failed=0,
            metadata=metadata or {},
        )
        return True

    def unregister_worker(self, name: str) -> bool:
        """Unregister a worker."""
        if name not in self._workers:
            return False
        del self._workers[name]
        return True

    def set_worker_status(self, name: str, status: str) -> bool:
        """Set worker online/offline status."""
        w = self._workers.get(name)
        if not w or status not in ("available", "busy", "offline"):
            return False
        w.status = status
        return True

    def get_worker(self, name: str) -> Optional[Dict]:
        """Get worker info."""
        w = self._workers.get(name)
        if not w:
            return None
        return self._worker_to_dict(w)

    def list_workers(
        self,
        status: Optional[str] = None,
        skill: Optional[str] = None,
    ) -> List[Dict]:
        """List workers with filters."""
        results = []
        for w in sorted(self._workers.values(), key=lambda x: x.name):
            if status and w.status != status:
                continue
            if skill and skill not in w.skills:
                continue
            results.append(self._worker_to_dict(w))
        return results

    # ------------------------------------------------------------------
    # Work item management
    # ------------------------------------------------------------------

    def create_item(
        self,
        name: str,
        priority: int = 50,
        required_skills: Optional[Set[str]] = None,
        estimated_effort: float = 1.0,
        category: str = "general",
        dependencies: Optional[Set[str]] = None,
        metadata: Optional[Dict] = None,
    ) -> str:
        """Create a work item. Returns work_id."""
        wid = f"work-{uuid.uuid4().hex[:8]}"
        self._items[wid] = WorkItem(
            work_id=wid,
            name=name,
            priority=priority,
            required_skills=required_skills or set(),
            estimated_effort=estimated_effort,
            created_at=time.time(),
            status="pending",
            assigned_to="",
            started_at=0.0,
            completed_at=0.0,
            category=category,
            metadata=metadata or {},
            dependencies=dependencies or set(),
        )
        self._stats["total_created"] += 1
        self._prune()
        return wid

    def get_item(self, work_id: str) -> Optional[Dict]:
        """Get work item info."""
        item = self._items.get(work_id)
        if not item:
            return None
        return self._item_to_dict(item)

    def cancel_item(self, work_id: str) -> bool:
        """Cancel a pending work item."""
        item = self._items.get(work_id)
        if not item or item.status != "pending":
            return False
        item.status = "failed"
        return True

    # ------------------------------------------------------------------
    # Distribution
    # ------------------------------------------------------------------

    def distribute(self, work_id: Optional[str] = None) -> List[Dict]:
        """Distribute pending work items. Returns list of assignments."""
        assignments = []

        if work_id:
            items = [self._items[work_id]] if work_id in self._items else []
        else:
            # Sort by priority descending
            items = sorted(
                [i for i in self._items.values() if i.status == "pending"],
                key=lambda x: x.priority, reverse=True,
            )

        for item in items:
            if item.status != "pending":
                continue
            if not self._deps_met(item):
                continue

            worker = self._select_worker(item)
            if worker:
                self._assign(item, worker)
                assignments.append({
                    "work_id": item.work_id,
                    "worker": worker.name,
                    "priority": item.priority,
                })

        return assignments

    def _select_worker(self, item: WorkItem) -> Optional[Worker]:
        """Select a worker based on strategy."""
        candidates = [
            w for w in self._workers.values()
            if w.status == "available"
            and w.current_load + item.estimated_effort <= w.capacity
            and (not item.required_skills or item.required_skills.issubset(w.skills))
        ]
        if not candidates:
            return None

        if self._strategy == "round_robin":
            self._round_robin_idx = (self._round_robin_idx) % len(candidates)
            chosen = candidates[self._round_robin_idx]
            self._round_robin_idx += 1
            return chosen
        elif self._strategy == "least_loaded":
            return min(candidates, key=lambda w: w.current_load / max(w.capacity, 0.01))
        elif self._strategy == "skill_match":
            # Prefer workers with the most matching skills
            def skill_score(w: Worker) -> int:
                return len(w.skills & item.required_skills) if item.required_skills else 0
            return max(candidates, key=lambda w: (skill_score(w), -w.current_load))
        elif self._strategy == "priority":
            # Least loaded for high priority items
            return min(candidates, key=lambda w: w.current_load)
        else:
            return candidates[0]

    def _assign(self, item: WorkItem, worker: Worker) -> None:
        """Assign a work item to a worker."""
        item.status = "assigned"
        item.assigned_to = worker.name
        worker.current_load += item.estimated_effort
        self._stats["total_assigned"] += 1

    def _deps_met(self, item: WorkItem) -> bool:
        """Check if all dependencies are completed."""
        for dep_id in item.dependencies:
            dep = self._items.get(dep_id)
            if not dep or dep.status != "completed":
                return False
        return True

    # ------------------------------------------------------------------
    # Work lifecycle
    # ------------------------------------------------------------------

    def start_work(self, work_id: str) -> bool:
        """Mark work as in progress."""
        item = self._items.get(work_id)
        if not item or item.status != "assigned":
            return False
        item.status = "in_progress"
        item.started_at = time.time()
        return True

    def complete_work(self, work_id: str) -> bool:
        """Mark work as completed."""
        item = self._items.get(work_id)
        if not item or item.status not in ("assigned", "in_progress"):
            return False
        item.status = "completed"
        item.completed_at = time.time()
        self._stats["total_completed"] += 1

        # Free up worker capacity
        w = self._workers.get(item.assigned_to)
        if w:
            w.current_load = max(0, w.current_load - item.estimated_effort)
            w.total_completed += 1
        return True

    def fail_work(self, work_id: str) -> bool:
        """Mark work as failed."""
        item = self._items.get(work_id)
        if not item or item.status not in ("assigned", "in_progress"):
            return False
        item.status = "failed"
        self._stats["total_failed"] += 1

        w = self._workers.get(item.assigned_to)
        if w:
            w.current_load = max(0, w.current_load - item.estimated_effort)
            w.total_failed += 1
        return True

    def retry_work(self, work_id: str) -> bool:
        """Retry a failed work item."""
        item = self._items.get(work_id)
        if not item or item.status != "failed":
            return False
        item.status = "pending"
        item.assigned_to = ""
        item.started_at = 0.0
        return True

    # ------------------------------------------------------------------
    # Rebalancing
    # ------------------------------------------------------------------

    def rebalance(self) -> int:
        """Rebalance assigned work from offline workers. Returns count moved."""
        moved = 0
        for item in self._items.values():
            if item.status == "assigned":
                w = self._workers.get(item.assigned_to)
                if not w or w.status == "offline":
                    item.status = "pending"
                    item.assigned_to = ""
                    if w:
                        w.current_load = max(0, w.current_load - item.estimated_effort)
                    moved += 1
        self._stats["total_rebalanced"] += moved
        return moved

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list_items(
        self,
        status: Optional[str] = None,
        category: Optional[str] = None,
        assigned_to: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """List work items with filters."""
        results = []
        for item in sorted(self._items.values(),
                           key=lambda x: x.priority, reverse=True):
            if status and item.status != status:
                continue
            if category and item.category != category:
                continue
            if assigned_to and item.assigned_to != assigned_to:
                continue
            results.append(self._item_to_dict(item))
            if len(results) >= limit:
                break
        return results

    def get_worker_load(self) -> List[Dict]:
        """Get load summary per worker."""
        return [
            {
                "name": w.name,
                "capacity": w.capacity,
                "current_load": w.current_load,
                "utilization": round(w.current_load / max(w.capacity, 0.01) * 100, 1),
                "status": w.status,
                "assigned_items": sum(
                    1 for i in self._items.values()
                    if i.assigned_to == w.name and i.status in ("assigned", "in_progress")
                ),
            }
            for w in self._workers.values()
        ]

    def pending_count(self, category: Optional[str] = None) -> int:
        """Count pending items."""
        return sum(
            1 for i in self._items.values()
            if i.status == "pending"
            and (not category or i.category == category)
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _item_to_dict(self, item: WorkItem) -> Dict:
        return {
            "work_id": item.work_id,
            "name": item.name,
            "priority": item.priority,
            "required_skills": sorted(item.required_skills),
            "estimated_effort": item.estimated_effort,
            "created_at": item.created_at,
            "status": item.status,
            "assigned_to": item.assigned_to,
            "started_at": item.started_at,
            "completed_at": item.completed_at,
            "category": item.category,
            "dependencies": sorted(item.dependencies),
        }

    def _worker_to_dict(self, w: Worker) -> Dict:
        return {
            "name": w.name,
            "skills": sorted(w.skills),
            "capacity": w.capacity,
            "current_load": w.current_load,
            "status": w.status,
            "total_completed": w.total_completed,
            "total_failed": w.total_failed,
        }

    def _prune(self) -> None:
        if len(self._items) <= self._max_items:
            return
        done = sorted(
            [i for i in self._items.values() if i.status in ("completed", "failed")],
            key=lambda x: x.created_at,
        )
        to_remove = len(self._items) - self._max_items
        for i in done[:to_remove]:
            del self._items[i.work_id]

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "total_items": len(self._items),
            "total_workers": len(self._workers),
            "pending": self.pending_count(),
            "strategy": self._strategy,
        }

    def reset(self) -> None:
        self._workers.clear()
        self._items.clear()
        self._round_robin_idx = 0
        self._stats = {k: 0 for k in self._stats}
