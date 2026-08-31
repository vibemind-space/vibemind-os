"""In-memory task state store for async (fire-and-forget) mode."""

import time
from typing import Optional

from bridge.models import RoutingInfo, TaskStatus

# task_id → (TaskStatus, created_at)
_store: dict[str, tuple[TaskStatus, float]] = {}

# Evict completed tasks older than this (seconds)
_TTL = 3600


def create(task_id: str, routing: RoutingInfo, agent: str) -> TaskStatus:
    """Create a new pending task."""
    status = TaskStatus(
        task_id=task_id,
        status="pending",
        routing=routing,
        agent=agent,
    )
    _store[task_id] = (status, time.time())
    _evict_old()
    return status


def update(
    task_id: str,
    status: str,
    result: Optional[str] = None,
    error: Optional[str] = None,
):
    """Update task status."""
    if task_id not in _store:
        return
    existing, created_at = _store[task_id]
    existing.status = status
    if result is not None:
        existing.result = result
    if error is not None:
        existing.error = error
    _store[task_id] = (existing, created_at)


def get(task_id: str) -> Optional[TaskStatus]:
    """Get task status by ID."""
    entry = _store.get(task_id)
    return entry[0] if entry else None


def _evict_old():
    """Remove completed/failed tasks older than TTL."""
    now = time.time()
    to_remove = [
        tid
        for tid, (ts, created) in _store.items()
        if ts.status in ("completed", "failed") and now - created > _TTL
    ]
    for tid in to_remove:
        del _store[tid]
