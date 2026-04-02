"""
gRPC Worker Pool Service

Dieser Service exponiert den Worker Pool über gRPC für:
- Verteilte Batch-Submission
- Remote Worker Control
- Async Task Monitoring
"""

import asyncio
import json
import logging
from typing import Dict, Any, List
from datetime import datetime

import grpc
from grpc import aio

# gRPC Definitions
from grpc_host_pb2 import (
    TaskRequest,
    TaskResponse,
    TaskStatus as ProtoTaskStatus,
    Empty
)
from grpc_host_pb2_grpc import (
    EventFixTeamServicer,
    add_EventFixTeamServicer_to_server
)

# Worker Pool
from worker_pool import (
    WorkerPool,
    Task,
    TaskStatus,
    get_worker_pool
)

# AutoGen Orchestrator
from autogen_orchestrator import EventFixOrchestrator

# Event Broadcasting
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
from event_server import EventServer

logger = logging.getLogger(__name__)


class WorkerPoolGRPCService(EventFixTeamServicer):
    """
    gRPC Service für Worker Pool Operationen

    Erweitert den EventFixTeamServicer um Batch-Operationen.
    """

    def __init__(
        self,
        min_workers: int = 2,
        max_workers: int = 10,
        model: str = "gpt-4o"
    ):
        self.min_workers = min_workers
        self.max_workers = max_workers
        self.model = model

        self._pool: WorkerPool = None
        self._orchestrator: EventFixOrchestrator = None
        self._event_server = EventServer()
        self._initialized = False
        self._lock = asyncio.Lock()

        # Task ID Counter
        self._task_counter = 0

    async def _ensure_initialized(self):
        """Lazy Initialization"""
        async with self._lock:
            if self._initialized:
                return

            logger.info("Initialisiere WorkerPool Service...")

            # Orchestrator erstellen
            self._orchestrator = EventFixOrchestrator(
                model=self.model,
                event_server=self._event_server
            )
            await self._orchestrator.initialize()

            # Worker Pool mit Orchestrator als Executor
            async def execute_task(task: Task) -> Dict[str, Any]:
                result = await self._orchestrator.execute_task(
                    task=task.description,
                    task_type=task.task_type,
                    context=task.parameters,
                    task_id=task.id
                )
                return {
                    "status": result.status,
                    "result": result.result,
                    "steps": result.steps,
                    "tool_calls": result.tool_calls,
                    "duration_ms": result.duration_ms
                }

            self._pool = WorkerPool(
                min_workers=self.min_workers,
                max_workers=self.max_workers,
                task_executor=execute_task
            )

            # Event Callbacks
            self._pool.on_task_complete(self._on_task_complete)
            self._pool.on_task_failed(self._on_task_failed)

            await self._pool.start()

            self._initialized = True
            logger.info(f"WorkerPool Service bereit (Workers: {self.min_workers}-{self.max_workers})")

    async def _on_task_complete(self, task: Task):
        """Callback für abgeschlossene Tasks"""
        self._event_server.broadcast("batch.task_complete", {
            "task_id": task.id,
            "task_type": task.task_type,
            "result": task.result,
            "duration_ms": (task.completed_at - task.started_at).total_seconds() * 1000
            if task.completed_at and task.started_at else 0
        })

    async def _on_task_failed(self, task: Task):
        """Callback für fehlgeschlagene Tasks"""
        self._event_server.broadcast("batch.task_failed", {
            "task_id": task.id,
            "task_type": task.task_type,
            "error": task.error,
            "retries": task.retries
        })

    # =========================================================================
    # Single Task Operations
    # =========================================================================

    async def SubmitTask(self, request: TaskRequest, context) -> TaskResponse:
        """Reicht einen einzelnen Task ein"""
        await self._ensure_initialized()

        try:
            task_id = await self._pool.submit_task(
                task_type=request.type,
                description=request.description,
                parameters=json.loads(request.parameters) if request.parameters else {},
                priority=request.priority if hasattr(request, 'priority') else 0
            )

            self._event_server.broadcast("task.submitted", {
                "task_id": task_id,
                "type": request.type
            })

            return TaskResponse(
                task_id=task_id,
                status=ProtoTaskStatus.PENDING,
                message="Task eingereicht"
            )

        except Exception as e:
            logger.error(f"Fehler bei SubmitTask: {e}")
            return TaskResponse(
                task_id="",
                status=ProtoTaskStatus.FAILED,
                message=str(e)
            )

    async def GetTaskStatus(self, request, context) -> TaskResponse:
        """Gibt den Status eines Tasks zurück"""
        await self._ensure_initialized()

        status = await self._pool.get_task_status(request.task_id)

        if not status:
            return TaskResponse(
                task_id=request.task_id,
                status=ProtoTaskStatus.FAILED,
                message="Task nicht gefunden"
            )

        # Status-Mapping
        status_map = {
            "pending": ProtoTaskStatus.PENDING,
            "queued": ProtoTaskStatus.PENDING,
            "running": ProtoTaskStatus.IN_PROGRESS,
            "completed": ProtoTaskStatus.COMPLETED,
            "failed": ProtoTaskStatus.FAILED,
            "cancelled": ProtoTaskStatus.FAILED
        }

        return TaskResponse(
            task_id=request.task_id,
            status=status_map.get(status["status"], ProtoTaskStatus.PENDING),
            message=status.get("status", ""),
            result=json.dumps(status.get("result", {}))
        )

    # =========================================================================
    # Batch Operations
    # =========================================================================

    async def SubmitBatch(self, request, context):
        """
        Reicht einen Batch von Tasks ein

        Request:
            tasks: Liste von TaskRequest-ähnlichen Objekten
            priority: Default-Priorität für alle

        Returns:
            BatchResponse mit Task IDs
        """
        await self._ensure_initialized()

        try:
            tasks = []
            for task_def in request.tasks:
                tasks.append({
                    "type": task_def.type,
                    "description": task_def.description,
                    "parameters": json.loads(task_def.parameters) if task_def.parameters else {},
                    "priority": task_def.priority if hasattr(task_def, 'priority') else request.default_priority
                })

            task_ids = await self._pool.submit_batch(tasks, priority=request.default_priority)

            self._event_server.broadcast("batch.submitted", {
                "task_count": len(task_ids),
                "task_ids": task_ids[:10]  # Erste 10 für Preview
            })

            # Rückgabe als JSON-String (da BatchResponse nicht in proto definiert)
            return TaskResponse(
                task_id=",".join(task_ids),
                status=ProtoTaskStatus.PENDING,
                message=f"{len(task_ids)} Tasks eingereicht",
                result=json.dumps({"task_ids": task_ids})
            )

        except Exception as e:
            logger.error(f"Fehler bei SubmitBatch: {e}")
            return TaskResponse(
                task_id="",
                status=ProtoTaskStatus.FAILED,
                message=str(e)
            )

    async def GetBatchStatus(self, request, context):
        """
        Gibt den Status eines Batches zurück

        Request:
            task_ids: Liste von Task IDs (komma-separiert)

        Returns:
            BatchStatusResponse
        """
        await self._ensure_initialized()

        try:
            task_ids = request.task_id.split(",")
            statuses = await self._pool.get_batch_status(task_ids)

            # Zusammenfassung
            summary = {
                "total": len(statuses),
                "completed": sum(1 for s in statuses if s["status"] == "completed"),
                "failed": sum(1 for s in statuses if s["status"] == "failed"),
                "running": sum(1 for s in statuses if s["status"] == "running"),
                "pending": sum(1 for s in statuses if s["status"] in ["pending", "queued"])
            }

            return TaskResponse(
                task_id=request.task_id,
                status=ProtoTaskStatus.IN_PROGRESS if summary["running"] > 0 else
                       ProtoTaskStatus.COMPLETED if summary["completed"] == summary["total"] else
                       ProtoTaskStatus.PENDING,
                message=f"{summary['completed']}/{summary['total']} abgeschlossen",
                result=json.dumps({
                    "summary": summary,
                    "tasks": statuses
                })
            )

        except Exception as e:
            logger.error(f"Fehler bei GetBatchStatus: {e}")
            return TaskResponse(
                task_id=request.task_id,
                status=ProtoTaskStatus.FAILED,
                message=str(e)
            )

    # =========================================================================
    # Worker Control
    # =========================================================================

    async def GetPoolStats(self, request, context):
        """Gibt Worker Pool Statistiken zurück"""
        await self._ensure_initialized()

        try:
            stats = await self._pool.get_pool_stats()

            return TaskResponse(
                task_id="pool_stats",
                status=ProtoTaskStatus.COMPLETED,
                message="Pool Statistiken",
                result=json.dumps(stats)
            )

        except Exception as e:
            logger.error(f"Fehler bei GetPoolStats: {e}")
            return TaskResponse(
                task_id="pool_stats",
                status=ProtoTaskStatus.FAILED,
                message=str(e)
            )

    async def ScaleWorkers(self, request, context):
        """
        Skaliert die Worker-Anzahl

        Request:
            parameters: JSON mit "min_workers" und/oder "max_workers"
        """
        await self._ensure_initialized()

        try:
            params = json.loads(request.parameters) if request.parameters else {}

            if "min_workers" in params:
                self._pool.min_workers = params["min_workers"]

            if "max_workers" in params:
                self._pool.max_workers = params["max_workers"]

            self._event_server.broadcast("pool.scaled", {
                "min_workers": self._pool.min_workers,
                "max_workers": self._pool.max_workers
            })

            return TaskResponse(
                task_id="scale",
                status=ProtoTaskStatus.COMPLETED,
                message=f"Workers skaliert: {self._pool.min_workers}-{self._pool.max_workers}"
            )

        except Exception as e:
            logger.error(f"Fehler bei ScaleWorkers: {e}")
            return TaskResponse(
                task_id="scale",
                status=ProtoTaskStatus.FAILED,
                message=str(e)
            )

    async def CancelTask(self, request, context):
        """Bricht einen Task ab"""
        await self._ensure_initialized()

        try:
            success = await self._pool.cancel_task(request.task_id)

            if success:
                self._event_server.broadcast("task.cancelled", {
                    "task_id": request.task_id
                })

            return TaskResponse(
                task_id=request.task_id,
                status=ProtoTaskStatus.COMPLETED if success else ProtoTaskStatus.FAILED,
                message="Task abgebrochen" if success else "Task konnte nicht abgebrochen werden"
            )

        except Exception as e:
            logger.error(f"Fehler bei CancelTask: {e}")
            return TaskResponse(
                task_id=request.task_id,
                status=ProtoTaskStatus.FAILED,
                message=str(e)
            )

    # =========================================================================
    # Standard Methods (aus EventFixTeamServicer)
    # =========================================================================

    async def ListAgents(self, request, context):
        """Listet alle Worker auf"""
        await self._ensure_initialized()

        from grpc_host_pb2 import AgentInfo, AgentListResponse

        agents = []
        stats = await self._pool.get_pool_stats()

        for i in range(stats["workers"]["total"]):
            agents.append(AgentInfo(
                id=f"worker_{i}",
                name=f"AutoGen Worker {i}",
                description="Paralleler Task-Worker mit AutoGen Orchestrator",
                status="ready",
                capabilities=["write_code", "debug_docker", "playwright_tests", "database_query"]
            ))

        return AgentListResponse(agents=agents)

    async def HealthCheck(self, request, context):
        """Gesundheitscheck"""
        from grpc_host_pb2 import HealthCheckResponse

        if not self._initialized:
            return HealthCheckResponse(
                status="starting",
                message="Worker Pool wird initialisiert",
                active_tasks=0,
                total_tasks=0
            )

        stats = await self._pool.get_pool_stats()

        return HealthCheckResponse(
            status="healthy",
            message=f"Worker Pool läuft ({stats['workers']['total']} Workers)",
            active_tasks=stats["tasks"]["by_status"].get("running", 0),
            total_tasks=stats["tasks"]["total"]
        )


# ============================================================================
# Server Entry Point
# ============================================================================

async def serve(
    port: int = 50051,
    min_workers: int = 2,
    max_workers: int = 10,
    model: str = "gpt-4o"
):
    """
    Startet den Worker Pool gRPC Server

    Args:
        port: gRPC Port
        min_workers: Minimale Worker-Anzahl
        max_workers: Maximale Worker-Anzahl
        model: LLM Model für Orchestrator
    """
    server = aio.server()

    service = WorkerPoolGRPCService(
        min_workers=min_workers,
        max_workers=max_workers,
        model=model
    )
    add_EventFixTeamServicer_to_server(service, server)

    listen_addr = f'[::]:{port}'
    server.add_insecure_port(listen_addr)

    logger.info(f"Worker Pool gRPC Server startet auf Port {port}")
    logger.info(f"Workers: {min_workers}-{max_workers}, Model: {model}")

    await server.start()

    # Pre-initialize
    await service._ensure_initialized()

    logger.info("Server bereit für Anfragen")

    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Server wird heruntergefahren...")
        if service._pool:
            await service._pool.stop()
        await server.stop(0)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Worker Pool gRPC Server')
    parser.add_argument('--port', type=int, default=50051, help='gRPC Port')
    parser.add_argument('--min-workers', type=int, default=2, help='Minimale Worker')
    parser.add_argument('--max-workers', type=int, default=10, help='Maximale Worker')
    parser.add_argument('--model', type=str, default='gpt-4o', help='LLM Model')
    parser.add_argument('--log-level', type=str, default='INFO', help='Log Level')

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    asyncio.run(serve(
        port=args.port,
        min_workers=args.min_workers,
        max_workers=args.max_workers,
        model=args.model
    ))
