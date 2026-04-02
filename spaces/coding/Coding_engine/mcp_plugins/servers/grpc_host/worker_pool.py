"""
gRPC Worker Pool für parallele Batch-Verarbeitung

Dieser Worker Pool ermöglicht:
- Mehrere gRPC Worker Instanzen
- Parallele Task-Verarbeitung
- Async Batch-Submission
- Auto-Scaling basierend auf Queue-Länge
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
from collections import deque

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """Status eines Tasks"""
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkerStatus(Enum):
    """Status eines Workers"""
    IDLE = "idle"
    BUSY = "busy"
    STARTING = "starting"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass
class Task:
    """Ein Task für den Worker Pool"""
    id: str
    task_type: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 0  # Höher = wichtiger
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    worker_id: Optional[str] = None
    retries: int = 0
    max_retries: int = 3


@dataclass
class Worker:
    """Ein Worker im Pool"""
    id: str
    status: WorkerStatus = WorkerStatus.IDLE
    current_task: Optional[Task] = None
    tasks_completed: int = 0
    tasks_failed: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    last_active: datetime = field(default_factory=datetime.now)


class BatchQueue:
    """Priority Queue für Batch-Tasks"""

    def __init__(self, max_size: int = 10000):
        self.max_size = max_size
        self._queue: deque = deque()
        self._priority_queue: Dict[int, deque] = {}  # priority -> tasks
        self._lock = asyncio.Lock()

    async def enqueue(self, task: Task) -> bool:
        """Fügt einen Task zur Queue hinzu"""
        async with self._lock:
            if len(self._queue) >= self.max_size:
                return False

            # Priority-basiertes Queueing
            if task.priority not in self._priority_queue:
                self._priority_queue[task.priority] = deque()

            self._priority_queue[task.priority].append(task)
            self._queue.append(task)
            task.status = TaskStatus.QUEUED

            return True

    async def enqueue_batch(self, tasks: List[Task]) -> int:
        """Fügt mehrere Tasks zur Queue hinzu"""
        added = 0
        for task in tasks:
            if await self.enqueue(task):
                added += 1
        return added

    async def dequeue(self) -> Optional[Task]:
        """Holt den nächsten Task (höchste Priorität zuerst)"""
        async with self._lock:
            if not self._priority_queue:
                return None

            # Höchste Priorität zuerst
            max_priority = max(self._priority_queue.keys())
            priority_queue = self._priority_queue[max_priority]

            if not priority_queue:
                del self._priority_queue[max_priority]
                return await self.dequeue()

            task = priority_queue.popleft()

            # Aus Hauptqueue entfernen
            if task in self._queue:
                self._queue.remove(task)

            # Leere Priority-Queue aufräumen
            if not priority_queue:
                del self._priority_queue[max_priority]

            return task

    async def size(self) -> int:
        """Gibt die Queue-Größe zurück"""
        async with self._lock:
            return len(self._queue)

    async def get_stats(self) -> Dict[str, Any]:
        """Gibt Queue-Statistiken zurück"""
        async with self._lock:
            return {
                "total": len(self._queue),
                "by_priority": {
                    p: len(q) for p, q in self._priority_queue.items()
                },
                "max_size": self.max_size
            }


class WorkerPool:
    """
    Pool von Worker-Instanzen für parallele Task-Verarbeitung

    Features:
    - Dynamische Worker-Anzahl
    - Priority-basiertes Queueing
    - Auto-Scaling
    - Retry-Mechanismus
    - Event-Callbacks
    """

    def __init__(
        self,
        min_workers: int = 2,
        max_workers: int = 10,
        queue_size: int = 10000,
        task_executor: Optional[Callable] = None
    ):
        """
        Initialisiert den Worker Pool

        Args:
            min_workers: Minimale Anzahl Worker
            max_workers: Maximale Anzahl Worker
            queue_size: Maximale Queue-Größe
            task_executor: Callback für Task-Ausführung
        """
        self.min_workers = min_workers
        self.max_workers = max_workers
        self.queue = BatchQueue(max_size=queue_size)

        self._workers: Dict[str, Worker] = {}
        self._worker_tasks: Dict[str, asyncio.Task] = {}
        self._task_executor = task_executor
        self._running = False
        self._lock = asyncio.Lock()

        # Task-Tracking
        self._all_tasks: Dict[str, Task] = {}

        # Event Callbacks
        self._on_task_complete: Optional[Callable] = None
        self._on_task_failed: Optional[Callable] = None
        self._on_worker_scaled: Optional[Callable] = None

        logger.info(f"WorkerPool initialisiert (min={min_workers}, max={max_workers})")

    def set_task_executor(self, executor: Callable):
        """Setzt den Task-Executor Callback"""
        self._task_executor = executor

    def on_task_complete(self, callback: Callable):
        """Registriert Callback für abgeschlossene Tasks"""
        self._on_task_complete = callback

    def on_task_failed(self, callback: Callable):
        """Registriert Callback für fehlgeschlagene Tasks"""
        self._on_task_failed = callback

    async def start(self):
        """Startet den Worker Pool"""
        if self._running:
            return

        self._running = True

        # Mindestanzahl Worker starten
        for _ in range(self.min_workers):
            await self._spawn_worker()

        # Auto-Scaler starten
        asyncio.create_task(self._auto_scaler())

        logger.info(f"WorkerPool gestartet mit {len(self._workers)} Workern")

    async def stop(self):
        """Stoppt den Worker Pool"""
        self._running = False

        # Alle Worker stoppen
        for worker_id in list(self._workers.keys()):
            await self._stop_worker(worker_id)

        logger.info("WorkerPool gestoppt")

    async def submit_task(
        self,
        task_type: str,
        description: str,
        parameters: Optional[Dict[str, Any]] = None,
        priority: int = 0
    ) -> str:
        """
        Reicht einen einzelnen Task ein

        Args:
            task_type: Typ des Tasks (z.B. "write_code", "debug_docker")
            description: Beschreibung der Aufgabe
            parameters: Zusätzliche Parameter
            priority: Priorität (höher = wichtiger)

        Returns:
            Task ID
        """
        task = Task(
            id=str(uuid.uuid4()),
            task_type=task_type,
            description=description,
            parameters=parameters or {},
            priority=priority
        )

        await self.queue.enqueue(task)
        self._all_tasks[task.id] = task

        logger.debug(f"Task eingereicht: {task.id} ({task_type})")
        return task.id

    async def submit_batch(
        self,
        tasks: List[Dict[str, Any]],
        priority: int = 0
    ) -> List[str]:
        """
        Reicht mehrere Tasks als Batch ein

        Args:
            tasks: Liste von Task-Definitionen
            priority: Priorität für alle Tasks

        Returns:
            Liste von Task IDs
        """
        task_objects = []
        task_ids = []

        for task_def in tasks:
            task = Task(
                id=str(uuid.uuid4()),
                task_type=task_def.get("type", "general"),
                description=task_def.get("description", ""),
                parameters=task_def.get("parameters", {}),
                priority=task_def.get("priority", priority)
            )
            task_objects.append(task)
            task_ids.append(task.id)
            self._all_tasks[task.id] = task

        added = await self.queue.enqueue_batch(task_objects)
        logger.info(f"Batch eingereicht: {added}/{len(tasks)} Tasks")

        return task_ids

    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Gibt den Status eines Tasks zurück"""
        task = self._all_tasks.get(task_id)
        if not task:
            return None

        return {
            "id": task.id,
            "type": task.task_type,
            "status": task.status.value,
            "priority": task.priority,
            "created_at": task.created_at.isoformat(),
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "result": task.result,
            "error": task.error,
            "worker_id": task.worker_id,
            "retries": task.retries
        }

    async def get_batch_status(self, task_ids: List[str]) -> List[Dict[str, Any]]:
        """Gibt den Status mehrerer Tasks zurück"""
        return [
            await self.get_task_status(tid)
            for tid in task_ids
            if await self.get_task_status(tid) is not None
        ]

    async def cancel_task(self, task_id: str) -> bool:
        """Bricht einen Task ab"""
        task = self._all_tasks.get(task_id)
        if not task:
            return False

        if task.status in [TaskStatus.PENDING, TaskStatus.QUEUED]:
            task.status = TaskStatus.CANCELLED
            return True

        return False

    async def get_pool_stats(self) -> Dict[str, Any]:
        """Gibt Pool-Statistiken zurück"""
        queue_stats = await self.queue.get_stats()

        workers_by_status = {}
        for worker in self._workers.values():
            status = worker.status.value
            workers_by_status[status] = workers_by_status.get(status, 0) + 1

        tasks_by_status = {}
        for task in self._all_tasks.values():
            status = task.status.value
            tasks_by_status[status] = tasks_by_status.get(status, 0) + 1

        return {
            "workers": {
                "total": len(self._workers),
                "min": self.min_workers,
                "max": self.max_workers,
                "by_status": workers_by_status
            },
            "queue": queue_stats,
            "tasks": {
                "total": len(self._all_tasks),
                "by_status": tasks_by_status
            },
            "running": self._running
        }

    # =========================================================================
    # Private Methods
    # =========================================================================

    async def _spawn_worker(self) -> str:
        """Erstellt einen neuen Worker"""
        async with self._lock:
            if len(self._workers) >= self.max_workers:
                return ""

            worker_id = f"worker_{len(self._workers)}_{uuid.uuid4().hex[:8]}"
            worker = Worker(id=worker_id, status=WorkerStatus.STARTING)
            self._workers[worker_id] = worker

            # Worker-Task starten
            task = asyncio.create_task(self._worker_loop(worker_id))
            self._worker_tasks[worker_id] = task

            worker.status = WorkerStatus.IDLE
            logger.info(f"Worker gestartet: {worker_id}")

            if self._on_worker_scaled:
                await self._on_worker_scaled("scale_up", worker_id)

            return worker_id

    async def _stop_worker(self, worker_id: str):
        """Stoppt einen Worker"""
        async with self._lock:
            worker = self._workers.get(worker_id)
            if not worker:
                return

            worker.status = WorkerStatus.STOPPING

            # Task abbrechen
            if worker_id in self._worker_tasks:
                self._worker_tasks[worker_id].cancel()
                try:
                    await self._worker_tasks[worker_id]
                except asyncio.CancelledError:
                    pass
                del self._worker_tasks[worker_id]

            del self._workers[worker_id]
            logger.info(f"Worker gestoppt: {worker_id}")

            if self._on_worker_scaled:
                await self._on_worker_scaled("scale_down", worker_id)

    async def _worker_loop(self, worker_id: str):
        """Hauptschleife eines Workers"""
        worker = self._workers.get(worker_id)
        if not worker:
            return

        while self._running and worker_id in self._workers:
            try:
                # Task aus Queue holen
                task = await self.queue.dequeue()

                if task is None:
                    # Keine Tasks, kurz warten
                    await asyncio.sleep(0.1)
                    continue

                # Task verarbeiten
                worker.status = WorkerStatus.BUSY
                worker.current_task = task
                task.status = TaskStatus.RUNNING
                task.started_at = datetime.now()
                task.worker_id = worker_id

                try:
                    # Task ausführen
                    if self._task_executor:
                        result = await self._task_executor(task)
                        task.result = result
                        task.status = TaskStatus.COMPLETED
                        worker.tasks_completed += 1

                        if self._on_task_complete:
                            await self._on_task_complete(task)
                    else:
                        raise Exception("Kein Task-Executor konfiguriert")

                except Exception as e:
                    task.error = str(e)

                    if task.retries < task.max_retries:
                        task.retries += 1
                        task.status = TaskStatus.QUEUED
                        await self.queue.enqueue(task)
                        logger.warning(f"Task {task.id} wird wiederholt (Versuch {task.retries})")
                    else:
                        task.status = TaskStatus.FAILED
                        worker.tasks_failed += 1

                        if self._on_task_failed:
                            await self._on_task_failed(task)

                finally:
                    task.completed_at = datetime.now()
                    worker.current_task = None
                    worker.status = WorkerStatus.IDLE
                    worker.last_active = datetime.now()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker {worker_id} Fehler: {e}")
                await asyncio.sleep(1)

    async def _auto_scaler(self):
        """Auto-Scaling basierend auf Queue-Länge"""
        while self._running:
            try:
                queue_size = await self.queue.size()
                worker_count = len(self._workers)
                idle_workers = sum(
                    1 for w in self._workers.values()
                    if w.status == WorkerStatus.IDLE
                )

                # Scale Up: Wenn Queue groß und alle Worker busy
                if queue_size > worker_count * 5 and idle_workers == 0:
                    if worker_count < self.max_workers:
                        await self._spawn_worker()
                        logger.info(f"Auto-Scale UP: {worker_count + 1} Workers")

                # Scale Down: Wenn Queue leer und viele idle Workers
                elif queue_size == 0 and idle_workers > self.min_workers:
                    # Finde idle Worker zum Stoppen
                    for worker_id, worker in list(self._workers.items()):
                        if worker.status == WorkerStatus.IDLE and len(self._workers) > self.min_workers:
                            await self._stop_worker(worker_id)
                            logger.info(f"Auto-Scale DOWN: {len(self._workers)} Workers")
                            break

                await asyncio.sleep(5)  # Alle 5 Sekunden prüfen

            except Exception as e:
                logger.error(f"Auto-Scaler Fehler: {e}")
                await asyncio.sleep(5)


# ============================================================================
# Factory und Convenience Functions
# ============================================================================

_pool: Optional[WorkerPool] = None


async def get_worker_pool(
    min_workers: int = 2,
    max_workers: int = 10
) -> WorkerPool:
    """Gibt die globale WorkerPool Instanz zurück (Singleton)"""
    global _pool
    if _pool is None:
        from autogen_orchestrator import EventFixOrchestrator

        # Orchestrator als Task-Executor
        orchestrator = EventFixOrchestrator()
        await orchestrator.initialize()

        async def execute_task(task: Task) -> Dict[str, Any]:
            result = await orchestrator.execute_task(
                task=task.description,
                task_type=task.task_type,
                context=task.parameters,
                task_id=task.id
            )
            return {
                "status": result.status,
                "result": result.result,
                "steps": result.steps,
                "tool_calls": result.tool_calls
            }

        _pool = WorkerPool(
            min_workers=min_workers,
            max_workers=max_workers,
            task_executor=execute_task
        )
        await _pool.start()

    return _pool


# ============================================================================
# Test
# ============================================================================

async def test_worker_pool():
    """Test-Funktion für den Worker Pool"""
    print("=== Worker Pool Test ===\n")

    pool = await get_worker_pool(min_workers=2, max_workers=5)

    print("Pool Stats (initial):")
    print(await pool.get_pool_stats())

    # Batch einreichen
    print("\nReiche Batch ein...")
    task_ids = await pool.submit_batch([
        {"type": "general", "description": "Was ist 2+2?"},
        {"type": "general", "description": "Was ist 3+3?"},
        {"type": "general", "description": "Was ist 4+4?"},
    ])

    print(f"Tasks eingereicht: {task_ids}")

    # Warten und Status prüfen
    await asyncio.sleep(10)

    print("\nTask Status:")
    for tid in task_ids:
        status = await pool.get_task_status(tid)
        print(f"  {tid}: {status['status']}")

    print("\nPool Stats (final):")
    print(await pool.get_pool_stats())

    await pool.stop()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    asyncio.run(test_worker_pool())
