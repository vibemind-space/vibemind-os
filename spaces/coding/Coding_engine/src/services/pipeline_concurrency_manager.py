"""Pipeline Concurrency Manager – manages concurrent execution slots.

Provides named semaphores/locks for controlling concurrent access to
shared resources. Supports acquire/release with timeout tracking,
deadlock detection via wait chains, and fairness through FIFO ordering.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Semaphore:
    sem_id: str
    name: str
    max_permits: int
    available: int
    holders: List[str]  # who currently holds permits
    waiters: List[str]  # who is waiting (FIFO)
    tags: List[str]
    total_acquires: int
    total_releases: int
    total_timeouts: int
    created_at: float
    updated_at: float


class PipelineConcurrencyManager:
    """Manages named semaphores for pipeline concurrency control."""

    def __init__(self, max_semaphores: int = 5000):
        self._semaphores: Dict[str, _Semaphore] = {}
        self._name_index: Dict[str, str] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._max_semaphores = max_semaphores
        self._seq = 0

        # stats
        self._total_semaphores = 0
        self._total_acquires = 0
        self._total_releases = 0
        self._total_timeouts = 0
        self._total_contentions = 0

    # ------------------------------------------------------------------
    # Semaphores
    # ------------------------------------------------------------------

    def create_semaphore(
        self,
        name: str,
        max_permits: int = 1,
        tags: Optional[List[str]] = None,
    ) -> str:
        if not name or max_permits < 1:
            return ""
        if name in self._name_index:
            return ""
        if len(self._semaphores) >= self._max_semaphores:
            return ""

        self._seq += 1
        now = time.time()
        raw = f"{name}-{now}-{self._seq}"
        sid = "sem-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        sem = _Semaphore(
            sem_id=sid,
            name=name,
            max_permits=max_permits,
            available=max_permits,
            holders=[],
            waiters=[],
            tags=tags or [],
            total_acquires=0,
            total_releases=0,
            total_timeouts=0,
            created_at=now,
            updated_at=now,
        )
        self._semaphores[sid] = sem
        self._name_index[name] = sid
        self._total_semaphores += 1
        self._fire("semaphore_created", {"sem_id": sid, "name": name})
        return sid

    def get_semaphore(self, sem_id: str) -> Optional[Dict[str, Any]]:
        s = self._semaphores.get(sem_id)
        if not s:
            return None
        return {
            "sem_id": s.sem_id,
            "name": s.name,
            "max_permits": s.max_permits,
            "available": s.available,
            "holders": list(s.holders),
            "waiters": list(s.waiters),
            "tags": list(s.tags),
            "total_acquires": s.total_acquires,
            "total_releases": s.total_releases,
            "total_timeouts": s.total_timeouts,
            "created_at": s.created_at,
            "updated_at": s.updated_at,
        }

    def get_semaphore_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        sid = self._name_index.get(name)
        if not sid:
            return None
        return self.get_semaphore(sid)

    def remove_semaphore(self, sem_id: str) -> bool:
        s = self._semaphores.pop(sem_id, None)
        if not s:
            return False
        self._name_index.pop(s.name, None)
        self._fire("semaphore_removed", {"sem_id": sem_id})
        return True

    def list_semaphores(
        self,
        tag: str = "",
        has_waiters: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        results = []
        for s in self._semaphores.values():
            if tag and tag not in s.tags:
                continue
            if has_waiters is True and not s.waiters:
                continue
            if has_waiters is False and s.waiters:
                continue
            results.append(self.get_semaphore(s.sem_id))
        return results

    # ------------------------------------------------------------------
    # Acquire / Release
    # ------------------------------------------------------------------

    def try_acquire(self, sem_id: str, holder: str) -> bool:
        """Try to acquire a permit. Returns True if acquired, False if must wait."""
        s = self._semaphores.get(sem_id)
        if not s or not holder:
            return False
        # already holding?
        if holder in s.holders:
            return False

        if s.available > 0:
            s.available -= 1
            s.holders.append(holder)
            s.total_acquires += 1
            s.updated_at = time.time()
            self._total_acquires += 1
            self._fire("permit_acquired", {"sem_id": sem_id, "holder": holder})
            return True
        else:
            # add to waiters if not already
            if holder not in s.waiters:
                s.waiters.append(holder)
                self._total_contentions += 1
                self._fire("permit_contention", {"sem_id": sem_id, "holder": holder})
            return False

    def release(self, sem_id: str, holder: str) -> bool:
        """Release a permit. Returns True if released."""
        s = self._semaphores.get(sem_id)
        if not s or holder not in s.holders:
            return False

        s.holders.remove(holder)
        s.total_releases += 1
        s.updated_at = time.time()
        self._total_releases += 1

        # grant to next waiter if any
        if s.waiters:
            next_holder = s.waiters.pop(0)
            s.holders.append(next_holder)
            s.total_acquires += 1
            self._total_acquires += 1
            self._fire("permit_acquired", {"sem_id": sem_id, "holder": next_holder})
        else:
            s.available += 1

        self._fire("permit_released", {"sem_id": sem_id, "holder": holder})
        return True

    def cancel_wait(self, sem_id: str, holder: str) -> bool:
        """Remove a holder from the wait queue."""
        s = self._semaphores.get(sem_id)
        if not s or holder not in s.waiters:
            return False
        s.waiters.remove(holder)
        s.total_timeouts += 1
        s.updated_at = time.time()
        self._total_timeouts += 1
        self._fire("wait_cancelled", {"sem_id": sem_id, "holder": holder})
        return True

    def force_release_all(self, sem_id: str) -> int:
        """Force release all permits (emergency). Returns count released."""
        s = self._semaphores.get(sem_id)
        if not s:
            return 0
        count = len(s.holders)
        s.holders.clear()
        s.waiters.clear()
        s.available = s.max_permits
        s.updated_at = time.time()
        if count:
            self._fire("force_released", {"sem_id": sem_id, "count": count})
        return count

    # ------------------------------------------------------------------
    # Deadlock detection
    # ------------------------------------------------------------------

    def detect_deadlocks(self) -> List[List[str]]:
        """Detect circular wait chains. Returns list of cycles."""
        # Build wait-for graph: holder -> what they're waiting for
        # A waiter W for semaphore S is waiting for all holders of S
        wait_graph: Dict[str, List[str]] = {}
        for s in self._semaphores.values():
            for waiter in s.waiters:
                if waiter not in wait_graph:
                    wait_graph[waiter] = []
                wait_graph[waiter].extend(s.holders)

        # Find cycles using DFS
        cycles = []
        visited = set()
        path = []
        path_set = set()

        def dfs(node: str) -> None:
            if node in path_set:
                # found cycle
                idx = path.index(node)
                cycle = path[idx:] + [node]
                cycles.append(cycle)
                return
            if node in visited:
                return
            visited.add(node)
            path.append(node)
            path_set.add(node)
            for neighbor in wait_graph.get(node, []):
                dfs(neighbor)
            path.pop()
            path_set.discard(node)

        for node in wait_graph:
            if node not in visited:
                dfs(node)

        return cycles

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
            "current_semaphores": len(self._semaphores),
            "total_semaphores": self._total_semaphores,
            "total_acquires": self._total_acquires,
            "total_releases": self._total_releases,
            "total_timeouts": self._total_timeouts,
            "total_contentions": self._total_contentions,
        }

    def reset(self) -> None:
        self._semaphores.clear()
        self._name_index.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_semaphores = 0
        self._total_acquires = 0
        self._total_releases = 0
        self._total_timeouts = 0
        self._total_contentions = 0
