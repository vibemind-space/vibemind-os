"""
Topic-Based Coordinator - Fire-and-Forget Pattern with Event Collection.

ARCH-35: Fire-and-Forget Pattern mit publish_message()
ARCH-36: Topic-basierte Event Collection mit asyncio.Queue
ARCH-41: Multi-Worker pro Topic (3x Frontend, 2x Backend, 1x DB)

This module implements:
1. Topics für verschiedene Domänen (frontend, backend, database)
2. Fire-and-Forget message publishing
3. asyncio.Queue für Event Collection
4. Multi-Worker pro Topic mit konfigurierbaren Counts
5. Result aggregation und Merge-Phase Vorbereitung
"""
import asyncio
from dataclasses import dataclass, field
from typing import Optional, Any, Callable, Awaitable, Generic, TypeVar
from enum import Enum
from collections import defaultdict
import structlog

logger = structlog.get_logger(__name__)

T = TypeVar('T')


class TopicType(Enum):
    """Topic-Typen für verschiedene Domänen."""
    FRONTEND_COMPONENTS = "frontend.components"
    FRONTEND_PAGES = "frontend.pages"
    FRONTEND_HOOKS = "frontend.hooks"
    FRONTEND_SERVICES = "frontend.services"
    FRONTEND_STATE = "frontend.state"
    FRONTEND_STYLES = "frontend.styles"
    FRONTEND_LAYOUT = "frontend.layout"
    FRONTEND_UTILS = "frontend.utils"
    
    BACKEND_ROUTES = "backend.routes"
    BACKEND_MODELS = "backend.models"
    BACKEND_SERVICES = "backend.services"
    BACKEND_DATABASE = "backend.database"
    BACKEND_AUTH = "backend.auth"
    BACKEND_MIDDLEWARE = "backend.middleware"
    BACKEND_CONFIG = "backend.config"
    BACKEND_UTILS = "backend.utils"
    
    DATABASE_SCHEMA = "database.schema"
    DATABASE_MIGRATIONS = "database.migrations"
    DATABASE_SEEDS = "database.seeds"
    
    TESTING = "testing"
    INFRASTRUCTURE = "infra"


@dataclass
class TopicConfig:
    """Konfiguration für einen Topic."""
    topic: TopicType
    worker_count: int = 1
    batch_size: int = 10
    priority: int = 0  # Lower = higher priority
    timeout_seconds: float = 300.0


@dataclass 
class Task:
    """Ein Task der an einen Worker gesendet wird."""
    task_id: str
    topic: TopicType
    payload: dict
    priority: int = 0
    created_at: float = field(default_factory=lambda: asyncio.get_event_loop().time())


@dataclass
class TaskResult(Generic[T]):
    """Ergebnis eines Tasks."""
    task_id: str
    topic: TopicType
    success: bool
    result: Optional[T] = None
    error: Optional[str] = None
    worker_id: str = ""
    execution_time_ms: int = 0
    
    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "topic": self.topic.value,
            "success": self.success,
            "error": self.error,
            "worker_id": self.worker_id,
            "execution_time_ms": self.execution_time_ms,
        }


@dataclass
class TopicWorkerConfig:
    """
    ARCH-41: Konfiguration für Multi-Worker pro Topic.
    
    Default: 3x Frontend, 2x Backend, 1x DB
    """
    frontend_workers: int = 3
    backend_workers: int = 2
    database_workers: int = 1
    testing_workers: int = 2
    infra_workers: int = 1
    
    # Topic-spezifische Overrides
    topic_overrides: dict[TopicType, int] = field(default_factory=dict)
    
    def get_worker_count(self, topic: TopicType) -> int:
        """Gibt die Worker-Anzahl für einen Topic zurück."""
        if topic in self.topic_overrides:
            return self.topic_overrides[topic]
        
        topic_name = topic.value
        if topic_name.startswith("frontend."):
            return self.frontend_workers
        elif topic_name.startswith("backend."):
            return self.backend_workers
        elif topic_name.startswith("database."):
            return self.database_workers
        elif topic_name == "testing":
            return self.testing_workers
        elif topic_name == "infra":
            return self.infra_workers
        return 1


class TopicQueue:
    """
    ARCH-36: Topic-basierte Queue mit asyncio.Queue.
    
    Jeder Topic hat eine eigene Queue für eingehende Tasks.
    """
    
    def __init__(self, topic: TopicType, max_size: int = 1000):
        self.topic = topic
        self._queue: asyncio.Queue[Task] = asyncio.Queue(maxsize=max_size)
        self._result_queue: asyncio.Queue[TaskResult] = asyncio.Queue()
        self._pending_count = 0
        self._lock = asyncio.Lock()
    
    async def publish(self, task: Task) -> None:
        """
        ARCH-35: Fire-and-Forget - Task in Queue ohne zu warten.
        """
        async with self._lock:
            self._pending_count += 1
        await self._queue.put(task)
    
    async def receive(self, timeout: Optional[float] = None) -> Optional[Task]:
        """Empfängt einen Task aus der Queue."""
        try:
            if timeout:
                return await asyncio.wait_for(self._queue.get(), timeout=timeout)
            return await self._queue.get()
        except asyncio.TimeoutError:
            return None
    
    async def submit_result(self, result: TaskResult) -> None:
        """Submits ein Result in die Result-Queue."""
        async with self._lock:
            self._pending_count -= 1
        await self._result_queue.put(result)
    
    async def collect_results(self, timeout: Optional[float] = None) -> list[TaskResult]:
        """Sammelt alle verfügbaren Results."""
        results = []
        try:
            while True:
                if timeout:
                    result = await asyncio.wait_for(
                        self._result_queue.get(), timeout=0.1
                    )
                else:
                    result = self._result_queue.get_nowait()
                results.append(result)
        except (asyncio.TimeoutError, asyncio.QueueEmpty):
            pass
        return results
    
    @property
    def pending_count(self) -> int:
        return self._pending_count
    
    @property
    def is_empty(self) -> bool:
        return self._queue.empty()


class Worker:
    """Ein Worker der Tasks aus einer Queue verarbeitet."""
    
    def __init__(
        self,
        worker_id: str,
        topic: TopicType,
        queue: TopicQueue,
        handler: Callable[[Task], Awaitable[Any]],
        timeout: float = 300.0,
    ):
        self.worker_id = worker_id
        self.topic = topic
        self.queue = queue
        self.handler = handler
        self.timeout = timeout
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self.logger = logger.bind(
            component="worker",
            worker_id=worker_id,
            topic=topic.value,
        )
    
    async def start(self) -> None:
        """Startet den Worker."""
        self._running = True
        self._task = asyncio.create_task(self._run())
        self.logger.info("worker_started")
    
    async def stop(self) -> None:
        """Stoppt den Worker."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self.logger.info("worker_stopped")
    
    async def _run(self) -> None:
        """Haupt-Worker-Loop."""
        while self._running:
            try:
                task = await self.queue.receive(timeout=1.0)
                if task is None:
                    continue
                
                await self._process_task(task)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("worker_loop_error", error=str(e))
    
    async def _process_task(self, task: Task) -> None:
        """Verarbeitet einen einzelnen Task."""
        import time
        start = time.time()
        
        self.logger.debug("processing_task", task_id=task.task_id)
        
        try:
            result = await asyncio.wait_for(
                self.handler(task),
                timeout=self.timeout,
            )
            
            await self.queue.submit_result(TaskResult(
                task_id=task.task_id,
                topic=task.topic,
                success=True,
                result=result,
                worker_id=self.worker_id,
                execution_time_ms=int((time.time() - start) * 1000),
            ))
            
        except asyncio.TimeoutError:
            await self.queue.submit_result(TaskResult(
                task_id=task.task_id,
                topic=task.topic,
                success=False,
                error=f"Timeout after {self.timeout}s",
                worker_id=self.worker_id,
                execution_time_ms=int((time.time() - start) * 1000),
            ))
        except Exception as e:
            self.logger.error(
                "task_processing_error",
                task_id=task.task_id,
                error=str(e),
            )
            await self.queue.submit_result(TaskResult(
                task_id=task.task_id,
                topic=task.topic,
                success=False,
                error=str(e),
                worker_id=self.worker_id,
                execution_time_ms=int((time.time() - start) * 1000),
            ))


class TopicCoordinator:
    """
    Topic-basierter Koordinator für Fire-and-Forget Code-Generierung.
    
    ARCH-35: Fire-and-Forget mit publish_message()
    ARCH-36: Topic-basierte Event Collection
    ARCH-41: Multi-Worker pro Topic
    
    Verwendung:
    
    ```python
    coordinator = TopicCoordinator(
        worker_config=TopicWorkerConfig(
            frontend_workers=3,
            backend_workers=2,
            database_workers=1,
        )
    )
    
    # Registriere Handler
    coordinator.register_handler(TopicType.FRONTEND_COMPONENTS, handle_frontend)
    coordinator.register_handler(TopicType.BACKEND_ROUTES, handle_backend)
    
    # Starte Workers
    await coordinator.start()
    
    # Fire-and-Forget: Tasks publizieren
    for slice in frontend_slices:
        await coordinator.publish(Task(
            task_id=slice.slice_id,
            topic=TopicType.FRONTEND_COMPONENTS,
            payload={"slice": slice, "contracts": contracts}
        ))
    
    # Warte auf alle Results
    results = await coordinator.wait_for_completion(expected_count=len(tasks))
    
    # Stop
    await coordinator.stop()
    ```
    """
    
    def __init__(
        self,
        worker_config: Optional[TopicWorkerConfig] = None,
        default_timeout: float = 300.0,
    ):
        self.worker_config = worker_config or TopicWorkerConfig()
        self.default_timeout = default_timeout
        
        # Topic Queues
        self._queues: dict[TopicType, TopicQueue] = {}
        
        # Workers
        self._workers: list[Worker] = []
        
        # Handlers
        self._handlers: dict[TopicType, Callable[[Task], Awaitable[Any]]] = {}
        
        # Result Collection
        self._all_results: list[TaskResult] = []
        self._result_event = asyncio.Event()
        
        self._running = False
        self.logger = logger.bind(component="topic_coordinator")
    
    def register_handler(
        self,
        topic: TopicType,
        handler: Callable[[Task], Awaitable[Any]],
    ) -> None:
        """Registriert einen Handler für einen Topic."""
        self._handlers[topic] = handler
        
        # Erstelle Queue falls nicht vorhanden
        if topic not in self._queues:
            self._queues[topic] = TopicQueue(topic)
        
        self.logger.info("handler_registered", topic=topic.value)
    
    async def start(self) -> None:
        """Startet alle Workers."""
        self._running = True
        
        for topic, handler in self._handlers.items():
            worker_count = self.worker_config.get_worker_count(topic)
            queue = self._queues[topic]
            
            for i in range(worker_count):
                worker = Worker(
                    worker_id=f"{topic.value}-worker-{i}",
                    topic=topic,
                    queue=queue,
                    handler=handler,
                    timeout=self.default_timeout,
                )
                await worker.start()
                self._workers.append(worker)
        
        self.logger.info(
            "coordinator_started",
            worker_count=len(self._workers),
            topics=len(self._handlers),
        )
    
    async def stop(self) -> None:
        """Stoppt alle Workers."""
        self._running = False
        
        for worker in self._workers:
            await worker.stop()
        
        self._workers.clear()
        self.logger.info("coordinator_stopped")
    
    async def publish(self, task: Task) -> None:
        """
        ARCH-35: Fire-and-Forget - Publiziert Task ohne zu warten.
        
        Der Task wird in die entsprechende Queue eingereiht
        und von einem freien Worker verarbeitet.
        """
        if task.topic not in self._queues:
            raise ValueError(f"No handler registered for topic: {task.topic.value}")
        
        queue = self._queues[task.topic]
        await queue.publish(task)
        
        self.logger.debug(
            "task_published",
            task_id=task.task_id,
            topic=task.topic.value,
        )
    
    async def publish_batch(self, tasks: list[Task]) -> None:
        """Publiziert mehrere Tasks auf einmal (Fire-and-Forget)."""
        for task in tasks:
            await self.publish(task)
        
        self.logger.info(
            "batch_published",
            task_count=len(tasks),
        )
    
    async def wait_for_completion(
        self,
        expected_count: int,
        timeout: Optional[float] = None,
    ) -> list[TaskResult]:
        """
        ARCH-36: Wartet auf alle Results und sammelt sie.
        
        Args:
            expected_count: Erwartete Anzahl von Results
            timeout: Optional timeout in Sekunden
            
        Returns:
            Liste aller TaskResults
        """
        import time
        start = time.time()
        effective_timeout = timeout or (self.default_timeout * expected_count)
        
        self.logger.info(
            "waiting_for_completion",
            expected_count=expected_count,
            timeout=effective_timeout,
        )
        
        results: list[TaskResult] = []
        
        while len(results) < expected_count:
            elapsed = time.time() - start
            if elapsed >= effective_timeout:
                self.logger.warning(
                    "completion_timeout",
                    collected=len(results),
                    expected=expected_count,
                )
                break
            
            # Sammle Results von allen Queues
            for queue in self._queues.values():
                new_results = await queue.collect_results(timeout=0.5)
                results.extend(new_results)
            
            # Kurze Pause um CPU zu schonen
            await asyncio.sleep(0.1)
        
        self._all_results = results
        
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful
        
        self.logger.info(
            "completion_done",
            total=len(results),
            successful=successful,
            failed=failed,
            time_ms=int((time.time() - start) * 1000),
        )
        
        return results
    
    def get_results_by_topic(self) -> dict[TopicType, list[TaskResult]]:
        """Gruppiert Results nach Topic."""
        by_topic: dict[TopicType, list[TaskResult]] = defaultdict(list)
        for result in self._all_results:
            by_topic[result.topic].append(result)
        return dict(by_topic)
    
    def get_summary(self) -> dict:
        """Gibt eine Zusammenfassung aller Results zurück."""
        by_topic = self.get_results_by_topic()
        
        summary = {
            "total_tasks": len(self._all_results),
            "successful": sum(1 for r in self._all_results if r.success),
            "failed": sum(1 for r in self._all_results if not r.success),
            "by_topic": {},
        }
        
        for topic, results in by_topic.items():
            summary["by_topic"][topic.value] = {
                "count": len(results),
                "successful": sum(1 for r in results if r.success),
                "failed": sum(1 for r in results if not r.success),
                "avg_time_ms": (
                    sum(r.execution_time_ms for r in results) // len(results)
                    if results else 0
                ),
            }
        
        return summary


# Convenience function für Feature-basierte Code-Generierung
async def generate_with_topics(
    slices: list[Any],  # TaskSlice from slicer
    handler: Callable[[Task], Awaitable[Any]],
    worker_config: Optional[TopicWorkerConfig] = None,
) -> list[TaskResult]:
    """
    Convenience function für Feature-basierte parallele Code-Generierung.
    
    Args:
        slices: Liste von TaskSlices aus dem Slicer
        handler: Handler-Funktion die Tasks verarbeitet
        worker_config: Optional Worker-Konfiguration
        
    Returns:
        Liste aller TaskResults
    """
    coordinator = TopicCoordinator(worker_config=worker_config)
    
    # Feature zu Topic Mapping
    feature_to_topic = {
        "components": TopicType.FRONTEND_COMPONENTS,
        "pages": TopicType.FRONTEND_PAGES,
        "hooks": TopicType.FRONTEND_HOOKS,
        "services": TopicType.FRONTEND_SERVICES,
        "state": TopicType.FRONTEND_STATE,
        "styles": TopicType.FRONTEND_STYLES,
        "layout": TopicType.FRONTEND_LAYOUT,
        "utils": TopicType.FRONTEND_UTILS,
        "routes": TopicType.BACKEND_ROUTES,
        "models": TopicType.BACKEND_MODELS,
        "database": TopicType.BACKEND_DATABASE,
        "auth": TopicType.BACKEND_AUTH,
        "middleware": TopicType.BACKEND_MIDDLEWARE,
        "config": TopicType.BACKEND_CONFIG,
    }
    
    # Sammle alle benötigten Topics
    topics_needed = set()
    for slice_obj in slices:
        feature = getattr(slice_obj, 'feature', None)
        agent_type = getattr(slice_obj, 'agent_type', 'general')
        
        if feature and feature in feature_to_topic:
            topics_needed.add(feature_to_topic[feature])
        elif agent_type == 'frontend':
            topics_needed.add(TopicType.FRONTEND_COMPONENTS)
        elif agent_type == 'backend':
            topics_needed.add(TopicType.BACKEND_ROUTES)
    
    # Registriere Handler für alle Topics
    for topic in topics_needed:
        coordinator.register_handler(topic, handler)
    
    # Starte Coordinator
    await coordinator.start()
    
    try:
        # Erstelle und publiziere Tasks
        tasks = []
        for slice_obj in slices:
            feature = getattr(slice_obj, 'feature', None)
            agent_type = getattr(slice_obj, 'agent_type', 'general')
            
            # Bestimme Topic
            if feature and feature in feature_to_topic:
                topic = feature_to_topic[feature]
            elif agent_type == 'frontend':
                topic = TopicType.FRONTEND_COMPONENTS
            elif agent_type == 'backend':
                topic = TopicType.BACKEND_ROUTES
            else:
                continue  # Skip unknown types
            
            task = Task(
                task_id=slice_obj.slice_id,
                topic=topic,
                payload={
                    "slice": slice_obj,
                    "requirements": slice_obj.requirements,
                    "requirement_details": slice_obj.requirement_details,
                },
            )
            tasks.append(task)
        
        # Fire-and-Forget: Alle Tasks publizieren
        await coordinator.publish_batch(tasks)
        
        # Warte auf Completion
        results = await coordinator.wait_for_completion(
            expected_count=len(tasks),
            timeout=600.0,  # 10 Minuten
        )
        
        return results
        
    finally:
        await coordinator.stop()