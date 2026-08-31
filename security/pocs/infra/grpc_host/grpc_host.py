#!/usr/bin/env python3
"""
GrpcWorkerAgentRuntimeHost - gRPC Host for distributed agent architecture

This host manages worker connections and distributes tasks to workers.
"""

import asyncio
import json
import os
import sys
import signal
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

# Force UTF-8 encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# gRPC imports
import grpc
from concurrent import futures

# Import generated protobuf modules
from grpc_host.grpc_host_pb2 import grpc_host_pb2
from grpc_host.grpc_host_pb2_grpc import grpc_host_pb2_grpc

# Autogen imports
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_agentchat.agents import AssistantAgent
from autogen_core.model_context import BufferedChatCompletionContext

# Shared module imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
from event_server import EventServer
from constants import (
    MCP_EVENT_SESSION_ANNOUNCE,
    MCP_EVENT_AGENT_MESSAGE,
    MCP_EVENT_AGENT_ERROR,
    MCP_EVENT_TASK_COMPLETE,
    MCP_EVENT_CONVERSATION_HISTORY,
    SESSION_STATE_CREATED,
    SESSION_STATE_RUNNING,
    SESSION_STATE_STOPPED,
    SESSION_STATE_ERROR,
)
from logging_utils import setup_logging

# Import FileWriteTasks for task management
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'teams', 'tools'))
from file_write_tasks import FileWriteTasks


class GrpcWorkerAgentRuntimeHost:
    """
    gRPC Host for distributed agent architecture.
    
    This host manages worker connections and distributes tasks to workers.
    """
    
    def __init__(self, host: str = "127.0.0.1", port: int = 50051):
        """
        Initialize the gRPC host.
        
        Args:
            host: Host address to bind to
            port: Port to listen on
        """
        self.host = host
        self.port = port
        self.logger = setup_logging("grpc_host")
        self.server = None
        self.workers: Dict[str, Any] = {}
        self.worker_tasks: Dict[str, List[str]] = {}
        self.running = False
        self.event_server = None
        self.event_port = None
        
        # Initialize FileWriteTasks for task management
        self.file_write_tasks = FileWriteTasks()
    
    async def start(self):
        """
        Start the gRPC host.
        """
        try:
            # Start event server
            self.event_server = EventServer(session_id="grpc_host", tool_name="grpc_host")
            self.event_port = await self.event_server.start()
            self.logger.info(f"Event server started on port {self.event_port}")
            
            # Create gRPC server
            self.server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
            
            # Register service
            from grpc_host.grpc_host_pb2_grpc import GrpcWorkerAgentRuntimeHostServicer as BaseServicer, add_GrpcWorkerAgentRuntimeHostServicer_to_server
            
            servicer = GrpcWorkerAgentRuntimeHostServicer(self)
            add_GrpcWorkerAgentRuntimeHostServicer_to_server(servicer, self.server)
            
            # Start server
            self.server.add_insecure_port(self.port)
            self.server.start()
            self.running = True
            
            # Send SESSION_ANNOUNCE
            await self.event_server.send_event({
                "type": MCP_EVENT_SESSION_ANNOUNCE,
                "session_id": "grpc_host",
                "host": self.host,
                "port": self.port,
                "status": SESSION_STATE_CREATED,
                "timestamp": datetime.now().isoformat()
            })
            
            self.logger.info(f"gRPC host started on {self.host}:{self.port}")
            
        except Exception as e:
            self.logger.error(f"Failed to start gRPC host: {str(e)}", exc_info=True)
            await self.event_server.send_event({
                "type": MCP_EVENT_AGENT_ERROR,
                "error": str(e),
                "status": SESSION_STATE_ERROR,
                "timestamp": datetime.now().isoformat()
            })
            raise
    
    async def stop(self):
        """
        Stop the gRPC host.
        """
        try:
            self.running = False
            
            if self.server:
                self.server.stop(0)
                self.logger.info("gRPC server stopped")
            
            if self.event_server:
                await self.event_server.stop()
                self.logger.info("Event server stopped")
                
        except Exception as e:
            self.logger.error(f"Error stopping gRPC host: {str(e)}", exc_info=True)
    
    async def register_worker(self, worker_id: str, worker_type: str, capabilities: List[str]) -> bool:
        """
        Register a worker.
        
        Args:
            worker_id: Unique worker identifier
            worker_type: Type of worker (e.g., "routed_agent", "debug_agent")
            capabilities: List of capabilities (e.g., ["fix_code", "migrate", "test", "log"])
            
        Returns:
            True if successful
        """
        try:
            self.workers[worker_id] = {
                "worker_type": worker_type,
                "capabilities": capabilities,
                "status": "idle",
                "registered_at": datetime.now().isoformat()
            }
            
            self.logger.info(f"Worker registered: {worker_id} (type: {worker_type})")
            
            # Send worker registered event
            await self.event_server.send_event({
                "type": "worker_registered",
                "worker_id": worker_id,
                "worker_type": worker_type,
                "capabilities": capabilities,
                "timestamp": datetime.now().isoformat()
            })
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to register worker {worker_id}: {str(e)}", exc_info=True)
            return False
    
    async def unregister_worker(self, worker_id: str) -> bool:
        """
        Unregister a worker.
        
        Args:
            worker_id: Worker identifier
            
        Returns:
            True if successful
        """
        try:
            if worker_id in self.workers:
                del self.workers[worker_id]
                
                self.logger.info(f"Worker unregistered: {worker_id}")
                
                # Send worker unregistered event
                await self.event_server.send_event({
                    "type": "worker_unregistered",
                    "worker_id": worker_id,
                    "timestamp": datetime.now().isoformat()
                })
                
                return True
            else:
                self.logger.warning(f"Worker not found: {worker_id}")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to unregister worker {worker_id}: {str(e)}", exc_info=True)
            return False
    
    async def distribute_task(self, task_type: str, task_data: Dict[str, Any]) -> Optional[str]:
        """
        Distribute a task to an appropriate worker.
        
        Args:
            task_type: Type of task (e.g., "fix_code", "migrate", "test", "log")
            task_data: Task data
            
        Returns:
            Worker ID if task was distributed, None otherwise
        """
        try:
            # Find suitable worker
            suitable_worker = None
            
            for worker_id, worker_info in self.workers.items():
                if task_type in worker_info.get("capabilities", []):
                    if worker_info.get("status") == "idle":
                        suitable_worker = worker_id
                        break
            
            if not suitable_worker:
                self.logger.warning(f"No suitable worker found for task type: {task_type}")
                return None
            
            # Assign task to worker
            self.worker_tasks.setdefault(suitable_worker, []).append(task_data.get("task_id"))
            
            # Update worker status
            self.workers[suitable_worker]["status"] = "busy"
            self.workers[suitable_worker]["current_task"] = task_data
            
            self.logger.info(f"Task {task_data.get('task_id')} distributed to worker {suitable_worker}")
            
            # Send task distributed event
            await self.event_server.send_event({
                "type": "task_distributed",
                "task_id": task_data.get("task_id"),
                "task_type": task_type,
                "worker_id": suitable_worker,
                "timestamp": datetime.now().isoformat()
            })
            
            return suitable_worker
            
        except Exception as e:
            self.logger.error(f"Failed to distribute task: {str(e)}", exc_info=True)
            return None
    
    async def collect_task_result(self, worker_id: str, task_id: str, result: Dict[str, Any]) -> bool:
        """
        Collect task result from worker.
        
        Args:
            worker_id: Worker ID
            task_id: Task ID
            result: Task result
            
        Returns:
            True if successful
        """
        try:
            # Remove task from worker's task list
            if worker_id in self.workers:
                if task_id in self.worker_tasks.get(worker_id, []):
                    self.worker_tasks[worker_id].remove(task_id)
                
                # Update worker status
                if not self.worker_tasks.get(worker_id, []):
                    self.workers[worker_id]["status"] = "idle"
                    self.workers[worker_id]["current_task"] = None
                
                self.logger.info(f"Task {task_id} completed by worker {worker_id}")
                
                # Send task completed event
                await self.event_server.send_event({
                    "type": "task_completed",
                    "task_id": task_id,
                    "worker_id": worker_id,
                    "result": result,
                    "timestamp": datetime.now().isoformat()
                })
                
                return True
            else:
                self.logger.warning(f"Worker not found: {worker_id}")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to collect task result: {str(e)}", exc_info=True)
            return False
    
    async def get_worker_status(self, worker_id: str) -> Optional[Dict[str, Any]]:
        """
        Get worker status.
        
        Args:
            worker_id: Worker ID
            
        Returns:
            Worker status or None
        """
        return self.workers.get(worker_id)
    
    async def get_all_workers(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all workers.
        
        Returns:
            Dictionary of all workers
        """
        return self.workers.copy()
    
    async def get_task_statistics(self) -> Dict[str, Any]:
        """
        Get task statistics.
        
        Returns:
            Task statistics
        """
        try:
            # Get statistics from FileWriteTasks
            stats = await self.file_write_tasks.get_task_statistics()
            
            # Add worker statistics
            total_workers = len(self.workers)
            idle_workers = sum(1 for w in self.workers.values() if w.get("status") == "idle")
            busy_workers = sum(1 for w in self.workers.values() if w.get("status") == "busy")
            
            stats["workers"] = {
                "total": total_workers,
                "idle": idle_workers,
                "busy": busy_workers
            }
            
            return stats
            
        except Exception as e:
            self.logger.error(f"Failed to get task statistics: {str(e)}", exc_info=True)
            return {}


class GrpcWorkerAgentRuntimeHostServicer:
    """
    gRPC service implementation for GrpcWorkerAgentRuntimeHost.
    """
    
    def __init__(self, host: GrpcWorkerAgentRuntimeHost):
        """
        Initialize the servicer.
        
        Args:
            host: GrpcWorkerAgentRuntimeHost instance
        """
        self.host = host
    
    def RegisterWorker(self, request, context):
        """
        Register a worker.
        """
        worker_id = request.worker_id
        worker_type = request.worker_type
        capabilities = list(request.capabilities)
        
        # Use asyncio.run to run async function
        success = asyncio.run(self.host.register_worker(worker_id, worker_type, capabilities))
        
        return grpc_host_pb2.RegisterWorkerResponse(
            success=success,
            message=f"Worker {worker_id} registered" if success else f"Failed to register worker {worker_id}"
        )
    
    def UnregisterWorker(self, request, context):
        """
        Unregister a worker.
        """
        worker_id = request.worker_id
        
        success = asyncio.run(self.host.unregister_worker(worker_id))
        
        return grpc_host_pb2.UnregisterWorkerResponse(
            success=success,
            message=f"Worker {worker_id} unregistered" if success else f"Failed to unregister worker {worker_id}"
        )
    
    def DistributeTask(self, request, context):
        """
        Distribute a task to a worker.
        """
        task_type = request.task_type
        task_data = json.loads(request.task_data)
        
        worker_id = asyncio.run(self.host.distribute_task(task_type, task_data))
        
        return grpc_host_pb2.DistributeTaskResponse(
            success=worker_id is not None,
            worker_id=worker_id or "",
            message=f"Task distributed to {worker_id}" if worker_id else "No suitable worker found"
        )
    
    def CollectTaskResult(self, request, context):
        """
        Collect task result from worker.
        """
        worker_id = request.worker_id
        task_id = request.task_id
        result = json.loads(request.result)
        
        success = asyncio.run(self.host.collect_task_result(worker_id, task_id, result))
        
        return grpc_host_pb2.CollectTaskResultResponse(
            success=success,
            message=f"Task result collected from {worker_id}" if success else f"Failed to collect task result from {worker_id}"
        )
    
    def GetWorkerStatus(self, request, context):
        """
        Get worker status.
        """
        worker_id = request.worker_id
        
        status = asyncio.run(self.host.get_worker_status(worker_id))
        
        if status:
            return grpc_host_pb2.GetWorkerStatusResponse(
                success=True,
                worker_id=worker_id,
                worker_type=status.get("worker_type", ""),
                status=status.get("status", ""),
                capabilities=status.get("capabilities", [])
            )
        else:
            return grpc_host_pb2.GetWorkerStatusResponse(
                success=False,
                worker_id=worker_id,
                message=f"Worker not found: {worker_id}"
            )
    
    def GetAllWorkers(self, request, context):
        """
        Get all workers.
        """
        workers = asyncio.run(self.host.get_all_workers())
        
        return grpc_host_pb2.GetAllWorkersResponse(
            workers=[
                grpc_host_pb2.WorkerInfo(
                    worker_id=worker_id,
                    worker_type=worker_info.get("worker_type", ""),
                    status=worker_info.get("status", ""),
                    capabilities=worker_info.get("capabilities", [])
                )
                for worker_id, worker_info in workers.items()
            ]
        )
    
    def GetTaskStatistics(self, request, context):
        """
        Get task statistics.
        """
        stats = asyncio.run(self.host.get_task_statistics())
        
        return grpc_host_pb2.GetTaskStatisticsResponse(
            statistics=json.dumps(stats)
        )


async def main():
    """
    Main entry point.
    """
    import argparse
    
    parser = argparse.ArgumentParser(description="GrpcWorkerAgentRuntimeHost - gRPC Host for distributed agent architecture")
    parser.add_argument("--host", default="127.0.0.1", help="Host address to bind to")
    parser.add_argument("--port", type=int, default=50051, help="Port to listen on")
    parser.add_argument("--event-port", type=int, default=50050, help="Event server port")
    
    args = parser.parse_args()
    
    # Create host
    host = GrpcWorkerAgentRuntimeHost(host=args.host, port=args.port)
    
    # Setup signal handlers
    def signal_handler(signum, frame):
        print(f"\nReceived signal {signum}, shutting down...")
        asyncio.create_task(host.stop())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Start host
        await host.start()
        
        print(f"\ngRPC Host running on {args.host}:{args.port}")
        print(f"Event server running on port {args.event_port}")
        print("Press Ctrl+C to stop...")
        
        # Keep running
        while host.running:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)
    finally:
        await host.stop()


if __name__ == "__main__":
    asyncio.run(main())
