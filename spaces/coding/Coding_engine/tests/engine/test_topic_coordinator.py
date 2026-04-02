"""
Unit Tests für den TopicCoordinator mit Fire-and-Forget Pattern.

Diese Tests sind unabhängig ausführbar:
    pytest tests/engine/test_topic_coordinator.py -v
"""
import pytest
import asyncio
from typing import Any

from src.engine.topic_coordinator import (
    TopicType,
    TopicConfig,
    Task,
    TaskResult,
    TopicWorkerConfig,
    TopicQueue,
    Worker,
    TopicCoordinator,
)


class TestTopicType:
    """Tests für TopicType Enum."""
    
    def test_frontend_topics_exist(self):
        """Alle Frontend-Topics existieren."""
        frontend_topics = [
            TopicType.FRONTEND_COMPONENTS,
            TopicType.FRONTEND_PAGES,
            TopicType.FRONTEND_HOOKS,
            TopicType.FRONTEND_SERVICES,
            TopicType.FRONTEND_STATE,
            TopicType.FRONTEND_STYLES,
            TopicType.FRONTEND_LAYOUT,
            TopicType.FRONTEND_UTILS,
        ]
        
        for topic in frontend_topics:
            assert topic.value.startswith("frontend.")
    
    def test_backend_topics_exist(self):
        """Alle Backend-Topics existieren."""
        backend_topics = [
            TopicType.BACKEND_ROUTES,
            TopicType.BACKEND_MODELS,
            TopicType.BACKEND_SERVICES,
            TopicType.BACKEND_DATABASE,
            TopicType.BACKEND_AUTH,
            TopicType.BACKEND_MIDDLEWARE,
            TopicType.BACKEND_CONFIG,
            TopicType.BACKEND_UTILS,
        ]
        
        for topic in backend_topics:
            assert topic.value.startswith("backend.")
    
    def test_database_topics_exist(self):
        """Alle Database-Topics existieren."""
        db_topics = [
            TopicType.DATABASE_SCHEMA,
            TopicType.DATABASE_MIGRATIONS,
            TopicType.DATABASE_SEEDS,
        ]
        
        for topic in db_topics:
            assert topic.value.startswith("database.")


class TestTopicWorkerConfig:
    """Tests für TopicWorkerConfig."""
    
    def test_default_values(self):
        """Standardwerte für Worker-Anzahl."""
        config = TopicWorkerConfig()
        
        # ARCH-41: 3x Frontend, 2x Backend, 1x DB
        assert config.frontend_workers == 3
        assert config.backend_workers == 2
        assert config.database_workers == 1
    
    def test_get_worker_count_frontend(self):
        """Frontend-Topics bekommen 3 Worker."""
        config = TopicWorkerConfig()
        
        assert config.get_worker_count(TopicType.FRONTEND_COMPONENTS) == 3
        assert config.get_worker_count(TopicType.FRONTEND_PAGES) == 3
        assert config.get_worker_count(TopicType.FRONTEND_HOOKS) == 3
    
    def test_get_worker_count_backend(self):
        """Backend-Topics bekommen 2 Worker."""
        config = TopicWorkerConfig()
        
        assert config.get_worker_count(TopicType.BACKEND_ROUTES) == 2
        assert config.get_worker_count(TopicType.BACKEND_MODELS) == 2
    
    def test_get_worker_count_database(self):
        """Database-Topics bekommen 1 Worker."""
        config = TopicWorkerConfig()
        
        assert config.get_worker_count(TopicType.DATABASE_SCHEMA) == 1
    
    def test_custom_worker_count(self):
        """Custom Worker-Anzahl kann gesetzt werden."""
        config = TopicWorkerConfig(frontend_workers=5, backend_workers=3)
        
        assert config.get_worker_count(TopicType.FRONTEND_COMPONENTS) == 5
        assert config.get_worker_count(TopicType.BACKEND_ROUTES) == 3
    
    def test_topic_override(self):
        """Topic-spezifische Overrides funktionieren."""
        config = TopicWorkerConfig(
            topic_overrides={
                TopicType.FRONTEND_COMPONENTS: 10,
            }
        )
        
        assert config.get_worker_count(TopicType.FRONTEND_COMPONENTS) == 10
        assert config.get_worker_count(TopicType.FRONTEND_PAGES) == 3  # Default


class TestTask:
    """Tests für Task Dataclass."""
    
    def test_task_creation(self):
        """Task kann erstellt werden."""
        task = Task(
            task_id="task-001",
            topic=TopicType.FRONTEND_COMPONENTS,
            payload={"slice": "test_slice"},
        )
        
        assert task.task_id == "task-001"
        assert task.topic == TopicType.FRONTEND_COMPONENTS
        assert task.payload["slice"] == "test_slice"
    
    def test_task_with_priority(self):
        """Task mit Priority."""
        task = Task(
            task_id="task-002",
            topic=TopicType.BACKEND_ROUTES,
            payload={},
            priority=5,
        )
        
        assert task.priority == 5


class TestTaskResult:
    """Tests für TaskResult Dataclass."""
    
    def test_success_result(self):
        """Erfolgreches Result."""
        result = TaskResult(
            task_id="task-001",
            topic=TopicType.FRONTEND_COMPONENTS,
            success=True,
            result={"files": ["Button.tsx"]},
            worker_id="frontend.components-worker-0",
            execution_time_ms=500,
        )
        
        assert result.success is True
        assert result.error is None
        assert result.execution_time_ms == 500
    
    def test_failure_result(self):
        """Fehlerhafte Result."""
        result = TaskResult(
            task_id="task-002",
            topic=TopicType.BACKEND_ROUTES,
            success=False,
            error="Generation failed",
            worker_id="backend.routes-worker-1",
        )
        
        assert result.success is False
        assert result.error == "Generation failed"
    
    def test_to_dict(self):
        """to_dict() gibt korrektes Dict zurück."""
        result = TaskResult(
            task_id="test",
            topic=TopicType.DATABASE_SCHEMA,
            success=True,
        )
        
        d = result.to_dict()
        assert d["task_id"] == "test"
        assert d["topic"] == "database.schema"
        assert d["success"] is True


class TestTopicQueue:
    """Tests für TopicQueue mit asyncio.Queue."""
    
    @pytest.mark.asyncio
    async def test_publish_and_receive(self):
        """Task kann publiziert und empfangen werden."""
        queue = TopicQueue(TopicType.FRONTEND_COMPONENTS)
        
        task = Task(
            task_id="task-001",
            topic=TopicType.FRONTEND_COMPONENTS,
            payload={},
        )
        
        # Fire-and-Forget publish
        await queue.publish(task)
        
        # Receive
        received = await queue.receive(timeout=1.0)
        
        assert received is not None
        assert received.task_id == "task-001"
    
    @pytest.mark.asyncio
    async def test_pending_count(self):
        """pending_count wird korrekt verwaltet."""
        queue = TopicQueue(TopicType.BACKEND_ROUTES)
        
        assert queue.pending_count == 0
        
        task1 = Task(task_id="t1", topic=TopicType.BACKEND_ROUTES, payload={})
        task2 = Task(task_id="t2", topic=TopicType.BACKEND_ROUTES, payload={})
        
        await queue.publish(task1)
        await queue.publish(task2)
        
        assert queue.pending_count == 2
        
        # Submit result
        result = TaskResult(
            task_id="t1",
            topic=TopicType.BACKEND_ROUTES,
            success=True,
        )
        await queue.submit_result(result)
        
        assert queue.pending_count == 1
    
    @pytest.mark.asyncio
    async def test_collect_results(self):
        """Results können gesammelt werden."""
        queue = TopicQueue(TopicType.DATABASE_SCHEMA)
        
        # Submit some results
        for i in range(3):
            result = TaskResult(
                task_id=f"task-{i}",
                topic=TopicType.DATABASE_SCHEMA,
                success=True,
            )
            await queue.submit_result(result)
        
        # Collect
        results = await queue.collect_results()
        assert len(results) == 3
    
    @pytest.mark.asyncio
    async def test_receive_timeout(self):
        """receive() gibt None bei Timeout zurück."""
        queue = TopicQueue(TopicType.TESTING)
        
        received = await queue.receive(timeout=0.1)
        assert received is None
    
    @pytest.mark.asyncio
    async def test_is_empty(self):
        """is_empty property funktioniert."""
        queue = TopicQueue(TopicType.INFRASTRUCTURE)
        
        assert queue.is_empty is True
        
        task = Task(task_id="t1", topic=TopicType.INFRASTRUCTURE, payload={})
        await queue.publish(task)
        
        assert queue.is_empty is False


class TestWorker:
    """Tests für Worker-Klasse."""
    
    @pytest.mark.asyncio
    async def test_worker_processes_task(self):
        """Worker verarbeitet Tasks korrekt."""
        queue = TopicQueue(TopicType.FRONTEND_COMPONENTS)
        processed_tasks = []
        
        async def handler(task: Task) -> dict:
            processed_tasks.append(task.task_id)
            return {"generated": True}
        
        worker = Worker(
            worker_id="test-worker-0",
            topic=TopicType.FRONTEND_COMPONENTS,
            queue=queue,
            handler=handler,
            timeout=5.0,
        )
        
        # Start worker
        await worker.start()
        
        # Publish task
        task = Task(task_id="test-task", topic=TopicType.FRONTEND_COMPONENTS, payload={})
        await queue.publish(task)
        
        # Wait for processing
        await asyncio.sleep(0.2)
        
        # Stop worker
        await worker.stop()
        
        # Check task was processed
        assert "test-task" in processed_tasks
    
    @pytest.mark.asyncio
    async def test_worker_handles_errors(self):
        """Worker behandelt Fehler im Handler."""
        queue = TopicQueue(TopicType.BACKEND_ROUTES)
        
        async def failing_handler(task: Task) -> dict:
            raise ValueError("Test error")
        
        worker = Worker(
            worker_id="error-worker",
            topic=TopicType.BACKEND_ROUTES,
            queue=queue,
            handler=failing_handler,
            timeout=5.0,
        )
        
        await worker.start()
        
        task = Task(task_id="fail-task", topic=TopicType.BACKEND_ROUTES, payload={})
        await queue.publish(task)
        
        await asyncio.sleep(0.2)
        await worker.stop()
        
        # Result should be failure
        results = await queue.collect_results()
        assert len(results) == 1
        assert results[0].success is False
        assert "Test error" in results[0].error


class TestTopicCoordinator:
    """Tests für TopicCoordinator."""
    
    @pytest.mark.asyncio
    async def test_register_handler(self):
        """Handler können registriert werden."""
        coordinator = TopicCoordinator()
        
        async def dummy_handler(task: Task) -> dict:
            return {}
        
        coordinator.register_handler(TopicType.FRONTEND_COMPONENTS, dummy_handler)
        
        assert TopicType.FRONTEND_COMPONENTS in coordinator._handlers
        assert TopicType.FRONTEND_COMPONENTS in coordinator._queues
    
    @pytest.mark.asyncio
    async def test_start_creates_workers(self):
        """start() erstellt Worker für alle registrierten Topics."""
        config = TopicWorkerConfig(frontend_workers=2, backend_workers=1)
        coordinator = TopicCoordinator(worker_config=config)
        
        async def dummy_handler(task: Task) -> dict:
            return {}
        
        coordinator.register_handler(TopicType.FRONTEND_COMPONENTS, dummy_handler)
        coordinator.register_handler(TopicType.BACKEND_ROUTES, dummy_handler)
        
        await coordinator.start()
        
        # 2 Frontend + 1 Backend = 3 Workers
        assert len(coordinator._workers) == 3
        
        await coordinator.stop()
    
    @pytest.mark.asyncio
    async def test_publish_fireandforget(self):
        """publish() ist Fire-and-Forget."""
        coordinator = TopicCoordinator()
        
        async def slow_handler(task: Task) -> dict:
            await asyncio.sleep(0.5)
            return {"done": True}
        
        coordinator.register_handler(TopicType.FRONTEND_COMPONENTS, slow_handler)
        await coordinator.start()
        
        task = Task(
            task_id="ff-task",
            topic=TopicType.FRONTEND_COMPONENTS,
            payload={},
        )
        
        # publish() should return immediately (fire-and-forget)
        import time
        start = time.time()
        await coordinator.publish(task)
        elapsed = time.time() - start
        
        # Should be much faster than the handler
        assert elapsed < 0.1
        
        await coordinator.stop()
    
    @pytest.mark.asyncio
    async def test_publish_batch(self):
        """publish_batch() publiziert mehrere Tasks."""
        coordinator = TopicCoordinator()
        processed = []
        
        async def handler(task: Task) -> dict:
            processed.append(task.task_id)
            return {}
        
        coordinator.register_handler(TopicType.FRONTEND_COMPONENTS, handler)
        await coordinator.start()
        
        tasks = [
            Task(task_id=f"batch-{i}", topic=TopicType.FRONTEND_COMPONENTS, payload={})
            for i in range(5)
        ]
        
        await coordinator.publish_batch(tasks)
        
        # Wait for processing
        await asyncio.sleep(0.5)
        
        await coordinator.stop()
        
        assert len(processed) == 5
    
    @pytest.mark.asyncio
    async def test_wait_for_completion(self):
        """wait_for_completion() sammelt alle Results."""
        coordinator = TopicCoordinator()
        
        async def handler(task: Task) -> dict:
            return {"task_id": task.task_id}
        
        coordinator.register_handler(TopicType.FRONTEND_COMPONENTS, handler)
        await coordinator.start()
        
        tasks = [
            Task(task_id=f"complete-{i}", topic=TopicType.FRONTEND_COMPONENTS, payload={})
            for i in range(3)
        ]
        
        await coordinator.publish_batch(tasks)
        
        results = await coordinator.wait_for_completion(expected_count=3, timeout=5.0)
        
        await coordinator.stop()
        
        assert len(results) == 3
        assert all(r.success for r in results)
    
    @pytest.mark.asyncio
    async def test_get_results_by_topic(self):
        """Results werden nach Topic gruppiert."""
        coordinator = TopicCoordinator()
        
        async def handler(task: Task) -> dict:
            return {}
        
        coordinator.register_handler(TopicType.FRONTEND_COMPONENTS, handler)
        coordinator.register_handler(TopicType.BACKEND_ROUTES, handler)
        
        await coordinator.start()
        
        # Publish to different topics
        await coordinator.publish(Task(
            task_id="fe-1",
            topic=TopicType.FRONTEND_COMPONENTS,
            payload={},
        ))
        await coordinator.publish(Task(
            task_id="be-1",
            topic=TopicType.BACKEND_ROUTES,
            payload={},
        ))
        
        await coordinator.wait_for_completion(expected_count=2, timeout=5.0)
        
        by_topic = coordinator.get_results_by_topic()
        
        await coordinator.stop()
        
        assert TopicType.FRONTEND_COMPONENTS in by_topic
        assert TopicType.BACKEND_ROUTES in by_topic
    
    @pytest.mark.asyncio
    async def test_get_summary(self):
        """Summary enthält alle relevanten Informationen."""
        coordinator = TopicCoordinator()
        
        async def handler(task: Task) -> dict:
            return {}
        
        coordinator.register_handler(TopicType.FRONTEND_COMPONENTS, handler)
        await coordinator.start()
        
        tasks = [
            Task(task_id=f"sum-{i}", topic=TopicType.FRONTEND_COMPONENTS, payload={})
            for i in range(3)
        ]
        
        await coordinator.publish_batch(tasks)
        await coordinator.wait_for_completion(expected_count=3, timeout=5.0)
        
        summary = coordinator.get_summary()
        
        await coordinator.stop()
        
        assert summary["total_tasks"] == 3
        assert summary["successful"] == 3
        assert summary["failed"] == 0
        assert "by_topic" in summary


class TestTopicCoordinatorErrorHandling:
    """Tests für Fehlerbehandlung im TopicCoordinator."""
    
    @pytest.mark.asyncio
    async def test_publish_unknown_topic_raises(self):
        """publish() auf unbekannten Topic wirft Exception."""
        coordinator = TopicCoordinator()
        
        task = Task(
            task_id="unknown",
            topic=TopicType.FRONTEND_COMPONENTS,
            payload={},
        )
        
        with pytest.raises(ValueError, match="No handler registered"):
            await coordinator.publish(task)
    
    @pytest.mark.asyncio
    async def test_completion_timeout(self):
        """wait_for_completion() bricht bei Timeout ab."""
        coordinator = TopicCoordinator()
        
        async def slow_handler(task: Task) -> dict:
            await asyncio.sleep(10)  # Very slow
            return {}
        
        coordinator.register_handler(TopicType.FRONTEND_COMPONENTS, slow_handler)
        await coordinator.start()
        
        task = Task(task_id="slow", topic=TopicType.FRONTEND_COMPONENTS, payload={})
        await coordinator.publish(task)
        
        # Wait with short timeout
        results = await coordinator.wait_for_completion(expected_count=1, timeout=0.5)
        
        await coordinator.stop()
        
        # Should timeout without result
        assert len(results) < 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])