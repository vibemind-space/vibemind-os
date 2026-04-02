#!/usr/bin/env python3
"""
GrpcWorkerAgentRuntime - gRPC Worker Runtime for distributed agent architecture

This runtime connects workers to the gRPC host and manages task processing.
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


class GrpcWorkerAgentRuntime:
    """
    gRPC Worker Runtime for distributed agent architecture.
    
    This runtime connects workers to the gRPC host and manages task processing.
    """
    
    def __init__(
        self,
        worker_id: str,
        host: str = "127.0.0.1",
        port: int = 50051,
        agent_instance: Optional[Any] = None
    ):
        """
        Initialize the gRPC Worker Runtime.
        
        Args:
            worker_id: Unique worker identifier
            host: gRPC host address
            port: gRPC host port
            agent_instance: Agent instance to register (e.g., RoutedAgent)
        """
        self.worker_id = worker_id
        self.host = host
        self.port = port
        self.agent_instance = agent_instance
        self.logger = setup_logging(f"grpc_worker_runtime_{worker_id}")
        self.stub = None
        self.running = False
        self.event_server = None
        self.event_port = None
        
        # Initialize FileWriteTasks for task management
        self.file_write_tasks = FileWriteTasks()
    
    async def connect(self):
        """
        Connect to the gRPC host.
        """
        try:
            # Create gRPC channel
            channel = grpc.insecure_channel(f"{self.host}:{self.port}")
            
            # Import stub
            from grpc_host_pb2 import GrpcWorkerAgentRuntimeHostStub
            self.stub = GrpcWorkerAgentRuntimeHostStub(channel)
            
            # Register agent instance
            if self.agent_instance:
                from grpc_host_pb2 import RegisterWorkerRequest
                
                # Get capabilities from agent
                capabilities = []
                if hasattr(self.agent_instance, 'capabilities'):
                    capabilities = self.agent_instance.capabilities
                
                request = RegisterWorkerRequest(
                    worker_id=self.worker_id,
                    worker_type="worker_runtime",
                    capabilities=capabilities
                )
                
                response = self.stub.RegisterWorker(request)
                
                if response.success:
                    self.logger.info(f"Agent {self.worker_id} registered successfully")
                    self.running = True
                    return True
                else:
                    self.logger.error(f"Failed to register agent: {response.message}")
                    return False
                    
        except Exception as e:
            self.logger.error(f"Failed to connect to gRPC host: {str(e)}", exc_info=True)
            return False
    
    async def disconnect(self):
        """
        Disconnect from the gRPC host.
        """
        try:
            if self.stub:
                # Unregister agent instance
                from grpc_host_pb2 import UnregisterWorkerRequest
                request = UnregisterWorkerRequest(worker_id=self.worker_id)
                
                response = self.stub.UnregisterWorker(request)
                
                if response.success:
                    self.logger.info(f"Agent {self.worker_id} unregistered successfully")
                else:
                    self.logger.warning(f"Failed to unregister agent: {response.message}")
                
                self.running = False
                
        except Exception as e:
            self.logger.error(f"Failed to disconnect from gRPC host: {str(e)}", exc_info=True)
    
    async def wait_for_tasks(self):
        """
        Wait for tasks from the gRPC host.
        
        This method polls the host for tasks assigned to this worker.
        """
        try:
            while self.running:
                # Get worker status
                from grpc_host_pb2 import GetWorkerStatusRequest
                request = GetWorkerStatusRequest(worker_id=self.worker_id)
                
                response = self.stub.GetWorkerStatus(request)
                
                if response.success and response.status == "busy":
                    # Worker has a task, process it
                    task_data = json.loads(response.current_task) if response.current_task else None
                    
                    if task_data:
                        task_type = task_data.get("task_type")
                        task_id = task_data.get("task_id")
                        
                        self.logger.info(f"Processing task: {task_id} (type: {task_type})")
                        
                        # Process task
                        if self.agent_instance and hasattr(self.agent_instance, 'process_task'):
                            result = await self.agent_instance.process_task(task_type, task_data)
                            
                            # Send result to host
                            from grpc_host_pb2 import CollectTaskResultRequest
                            collect_request = CollectTaskResultRequest(
                                worker_id=self.worker_id,
                                task_id=task_id,
                                result=json.dumps(result)
                            )
                            
                            collect_response = self.stub.CollectTaskResult(collect_request)
                            
                            if collect_response.success:
                                self.logger.info(f"Task result sent to host successfully")
                            else:
                                self.logger.warning(f"Failed to send task result: {collect_response.message}")
                
                # Wait before next poll
                await asyncio.sleep(1)
                
        except Exception as e:
            self.logger.error(f"Error waiting for tasks: {str(e)}", exc_info=True)
    
    async def run(self):
        """
        Run the gRPC Worker Runtime.
        
        This method connects to the host and waits for tasks.
        """
        try:
            # Connect to host
            if not await self.connect():
                self.logger.error("Failed to connect to gRPC host")
                return
            
            # Start event server
            self.event_server = EventServer(session_id=self.worker_id, tool_name="grpc_worker_runtime")
            self.event_port = await self.event_server.start()
            self.logger.info(f"Event server started on port {self.event_port}")
            
            # Send SESSION_ANNOUNCE
            await self.event_server.send_event({
                "type": MCP_EVENT_SESSION_ANNOUNCE,
                "session_id": self.worker_id,
                "host": self.host,
                "port": self.event_port,
                "status": SESSION_STATE_CREATED,
                "timestamp": datetime.now().isoformat()
            })
            
            self.logger.info(f"GrpcWorkerAgentRuntime {self.worker_id} started and waiting for tasks...")
            
            # Wait for tasks
            await self.wait_for_tasks()
                
        except Exception as e:
            self.logger.error(f"Error running GrpcWorkerAgentRuntime: {str(e)}", exc_info=True)
            await self.event_server.send_event({
                "type": MCP_EVENT_AGENT_ERROR,
                "error": str(e),
                "status": SESSION_STATE_ERROR,
                "timestamp": datetime.now().isoformat()
            })
        finally:
            await self.disconnect()
            if self.event_server:
                await self.event_server.stop()
                self.logger.info("Event server stopped")


async def main():
    """
    Main entry point.
    """
    import argparse
    
    parser = argparse.ArgumentParser(description="GrpcWorkerAgentRuntime - gRPC Worker Runtime for distributed agent architecture")
    parser.add_argument("--worker-id", required=True, help="Unique worker identifier")
    parser.add_argument("--host", default="127.0.0.1", help="gRPC host address")
    parser.add_argument("--port", type=int, default=50051, help="gRPC host port")
    parser.add_argument("--agent-type", default="routed_agent", help="Type of agent to wrap (e.g., routed_agent, debug_agent)")
    
    args = parser.parse_args()
    
    # Create runtime
    runtime = GrpcWorkerAgentRuntime(
        worker_id=args.worker_id,
        host=args.host,
        port=args.port
    )
    
    # Setup signal handlers
    def signal_handler(signum, frame):
        print(f"\nReceived signal {signum}, shutting down...")
        asyncio.create_task(runtime.disconnect())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Run runtime
        await runtime.run()
        
        print(f"\nGrpcWorkerAgentRuntime {args.worker_id} running...")
        print("Press Ctrl+C to stop...")
        
    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)
    finally:
        await runtime.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
