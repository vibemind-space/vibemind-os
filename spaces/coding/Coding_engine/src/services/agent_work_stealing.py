"""Agent work stealing — allows idle agents to steal tasks from busy agents."""

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass
class WorkQueue:
    """Per-agent work queue."""
    agent_name: str
    tasks: List[str] = field(default_factory=list)
    max_size: int = 100
    stealable: bool = True  # Allow stealing from this queue
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


@dataclass
class WorkItem:
    """A stealable work item."""
    item_id: str
    name: str
    owner: str
    priority: int = 50
    stealable: bool = True
    stolen_from: str = ""
    status: str = "queued"  # queued, running, completed, stolen
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


class AgentWorkStealing:
    """Work-stealing scheduler for load balancing between agents."""

    def __init__(self, max_queues: int = 500, max_items: int = 50000,
                 steal_threshold: float = 0.7):
        self._queues: Dict[str, WorkQueue] = {}
        self._items: Dict[str, WorkItem] = {}
        self._max_queues = max_queues
        self._max_items = max_items
        self._steal_threshold = steal_threshold  # Queue fullness ratio to trigger steal
        self._callbacks: Dict[str, Any] = {}

        # Stats
        self._total_queues_created = 0
        self._total_items_added = 0
        self._total_steals = 0
        self._total_completed = 0

    # ── Queue Management ──

    def create_queue(self, agent_name: str, max_size: int = 100,
                     stealable: bool = True, metadata: Optional[Dict] = None) -> bool:
        """Create a work queue for an agent."""
        if agent_name in self._queues:
            return False
        if len(self._queues) >= self._max_queues:
            return False
        if max_size < 1:
            return False

        self._queues[agent_name] = WorkQueue(
            agent_name=agent_name,
            max_size=max_size,
            stealable=stealable,
            metadata=metadata or {},
        )
        self._total_queues_created += 1
        return True

    def remove_queue(self, agent_name: str) -> bool:
        """Remove a queue (must be empty)."""
        queue = self._queues.get(agent_name)
        if queue is None:
            return False
        if queue.tasks:
            return False
        del self._queues[agent_name]
        return True

    def get_queue(self, agent_name: str) -> Optional[Dict]:
        """Get queue info."""
        queue = self._queues.get(agent_name)
        if queue is None:
            return None
        return {
            "agent_name": queue.agent_name,
            "size": len(queue.tasks),
            "max_size": queue.max_size,
            "stealable": queue.stealable,
            "fullness": round(len(queue.tasks) / queue.max_size * 100, 1) if queue.max_size > 0 else 0.0,
            "tasks": list(queue.tasks),
            "metadata": dict(queue.metadata),
        }

    def set_stealable(self, agent_name: str, stealable: bool) -> bool:
        """Set whether a queue allows stealing."""
        queue = self._queues.get(agent_name)
        if queue is None:
            return False
        queue.stealable = stealable
        return True

    def list_queues(self, min_fullness: float = 0.0) -> List[Dict]:
        """List all queues, optionally filtered by minimum fullness."""
        result = []
        for name in self._queues:
            info = self.get_queue(name)
            if info and info["fullness"] >= min_fullness:
                result.append(info)
        return result

    # ── Work Items ──

    def add_item(self, agent_name: str, name: str, priority: int = 50,
                 stealable: bool = True, metadata: Optional[Dict] = None) -> str:
        """Add a work item to an agent's queue. Returns item_id."""
        queue = self._queues.get(agent_name)
        if queue is None:
            return ""
        if len(queue.tasks) >= queue.max_size:
            return ""
        if len(self._items) >= self._max_items:
            return ""

        item_id = f"wi-{uuid.uuid4().hex[:8]}"
        self._items[item_id] = WorkItem(
            item_id=item_id,
            name=name,
            owner=agent_name,
            priority=max(0, min(100, priority)),
            stealable=stealable,
            metadata=metadata or {},
        )
        queue.tasks.append(item_id)
        self._total_items_added += 1
        return item_id

    def get_item(self, item_id: str) -> Optional[Dict]:
        """Get work item info."""
        item = self._items.get(item_id)
        if item is None:
            return None
        return {
            "item_id": item.item_id,
            "name": item.name,
            "owner": item.owner,
            "priority": item.priority,
            "stealable": item.stealable,
            "stolen_from": item.stolen_from,
            "status": item.status,
            "created_at": item.created_at,
            "metadata": dict(item.metadata),
        }

    def complete_item(self, item_id: str) -> bool:
        """Complete a work item and remove from queue."""
        item = self._items.get(item_id)
        if item is None:
            return False
        if item.status not in ("queued", "running"):
            return False

        item.status = "completed"
        queue = self._queues.get(item.owner)
        if queue and item_id in queue.tasks:
            queue.tasks.remove(item_id)
        self._total_completed += 1
        return True

    def start_item(self, item_id: str) -> bool:
        """Start working on an item."""
        item = self._items.get(item_id)
        if item is None or item.status != "queued":
            return False
        item.status = "running"
        return True

    # ── Work Stealing ──

    def steal(self, thief: str, victim: str, count: int = 1) -> List[str]:
        """Steal work items from victim's queue to thief's queue.

        Returns list of stolen item IDs.
        """
        thief_queue = self._queues.get(thief)
        victim_queue = self._queues.get(victim)
        if thief_queue is None or victim_queue is None:
            return []
        if not victim_queue.stealable:
            return []
        if thief == victim:
            return []

        stolen = []
        # Steal lowest priority items from victim (steal from the back)
        stealable_items = [
            iid for iid in victim_queue.tasks
            if self._items.get(iid) and self._items[iid].stealable and self._items[iid].status == "queued"
        ]

        # Sort by priority ascending (steal lowest priority first)
        stealable_items.sort(key=lambda iid: self._items[iid].priority)

        for item_id in stealable_items[:count]:
            if len(thief_queue.tasks) >= thief_queue.max_size:
                break

            item = self._items[item_id]
            victim_queue.tasks.remove(item_id)
            thief_queue.tasks.append(item_id)
            item.stolen_from = item.owner
            item.owner = thief
            item.status = "queued"
            stolen.append(item_id)
            self._total_steals += 1
            self._fire_callbacks("steal", item_id, victim, thief)

        return stolen

    def auto_steal(self, thief: str) -> List[str]:
        """Auto-steal from the most loaded queue. Returns stolen item IDs."""
        thief_queue = self._queues.get(thief)
        if thief_queue is None:
            return []

        # Find the most loaded stealable queue
        best_victim = None
        best_load = 0.0
        for name, queue in self._queues.items():
            if name == thief:
                continue
            if not queue.stealable:
                continue
            if not queue.tasks:
                continue
            load = len(queue.tasks) / queue.max_size if queue.max_size > 0 else 0.0
            if load > best_load and load >= self._steal_threshold:
                best_load = load
                best_victim = name

        if best_victim is None:
            return []

        # Steal half the difference
        victim_queue = self._queues[best_victim]
        thief_size = len(thief_queue.tasks)
        victim_size = len(victim_queue.tasks)
        steal_count = max(1, (victim_size - thief_size) // 2)

        return self.steal(thief, best_victim, count=steal_count)

    def balance_all(self) -> int:
        """Balance all queues by stealing from overloaded to underloaded.

        Returns total items moved.
        """
        total_moved = 0

        # Sort queues by size
        sorted_queues = sorted(
            self._queues.values(),
            key=lambda q: len(q.tasks),
        )
        if len(sorted_queues) < 2:
            return 0

        # While imbalanced, steal from heaviest to lightest
        left = 0
        right = len(sorted_queues) - 1

        while left < right:
            light = sorted_queues[left]
            heavy = sorted_queues[right]

            light_size = len(light.tasks)
            heavy_size = len(heavy.tasks)

            if heavy_size - light_size <= 1:
                break

            if not heavy.stealable:
                right -= 1
                continue

            steal_count = max(1, (heavy_size - light_size) // 2)
            stolen = self.steal(light.agent_name, heavy.agent_name, count=steal_count)
            total_moved += len(stolen)

            if not stolen:
                right -= 1
                continue

            # Re-check pointers
            if len(light.tasks) >= len(heavy.tasks):
                left += 1
                right -= 1

        return total_moved

    # ── Queries ──

    def get_load_distribution(self) -> Dict[str, Dict]:
        """Get load info for all queues."""
        result = {}
        for name in self._queues:
            info = self.get_queue(name)
            if info:
                result[name] = {
                    "size": info["size"],
                    "max_size": info["max_size"],
                    "fullness": info["fullness"],
                }
        return result

    def get_imbalance(self) -> float:
        """Get imbalance ratio (0 = balanced, higher = more imbalanced)."""
        sizes = [len(q.tasks) for q in self._queues.values()]
        if not sizes or len(sizes) < 2:
            return 0.0
        max_size = max(sizes)
        min_size = min(sizes)
        avg_size = sum(sizes) / len(sizes)
        if avg_size == 0:
            return 0.0
        return round((max_size - min_size) / avg_size, 2)

    def get_overloaded(self) -> List[str]:
        """Get names of overloaded queues (above steal threshold)."""
        result = []
        for name, queue in self._queues.items():
            if queue.max_size > 0:
                fullness = len(queue.tasks) / queue.max_size
                if fullness >= self._steal_threshold:
                    result.append(name)
        return result

    def get_idle(self) -> List[str]:
        """Get names of empty queues."""
        return [name for name, queue in self._queues.items() if not queue.tasks]

    # ── Callbacks ──

    def on_steal(self, name: str, callback) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire_callbacks(self, action: str, item_id: str, victim: str, thief: str) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, item_id, victim, thief)
            except Exception:
                pass

    # ── Stats ──

    def get_stats(self) -> Dict:
        return {
            "total_queues": len(self._queues),
            "total_queues_created": self._total_queues_created,
            "total_items": sum(len(q.tasks) for q in self._queues.values()),
            "total_items_added": self._total_items_added,
            "total_steals": self._total_steals,
            "total_completed": self._total_completed,
            "imbalance": self.get_imbalance(),
        }

    def reset(self) -> None:
        self._queues.clear()
        self._items.clear()
        self._callbacks.clear()
        self._total_queues_created = 0
        self._total_items_added = 0
        self._total_steals = 0
        self._total_completed = 0
