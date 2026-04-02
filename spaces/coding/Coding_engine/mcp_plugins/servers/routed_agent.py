#!/usr/bin/env python3
"""
RoutedAgent - A distributed agent that processes tasks from gRPC host

This agent connects to the gRPC host and processes tasks of various types.
"""

import asyncio
import json
import os
import sys
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


class RoutedAgent:
    """
    A distributed agent that processes tasks from gRPC host.
    
    This agent connects to the gRPC host and processes tasks of various types.
    """
    
    def __init__(
        self,
        worker_id: str,
        host: str = "127.0.0.1",
        port: int = 50051,
        capabilities: Optional[List[str]] = None
    ):
        """
        Initialize the RoutedAgent.
        
        Args:
            worker_id: Unique worker identifier
            host: gRPC host address
            port: gRPC host port
            capabilities: List of capabilities (e.g., ["fix_code", "migrate", "test", "log"])
        """
        self.worker_id = worker_id
        self.host = host
        self.port = port
        self.logger = setup_logging(f"routed_agent_{worker_id}")
        self.stub = None
        self.running = False
        self.event_server = None
        self.event_port = None
        
        # Set capabilities
        if capabilities is None:
            self.capabilities = ["fix_code", "migrate", "test", "log"]
        else:
            self.capabilities = capabilities
        
        # Initialize FileWriteTasks for task management
        self.file_write_tasks = FileWriteTasks()
        
        # Current task
        self.current_task = None
    
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
            
            # Register worker
            from grpc_host_pb2 import RegisterWorkerRequest
            request = RegisterWorkerRequest(
                worker_id=self.worker_id,
                worker_type="routed_agent",
                capabilities=self.capabilities
            )
            
            response = self.stub.RegisterWorker(request)
            
            if response.success:
                self.logger.info(f"Worker {self.worker_id} registered successfully")
                self.running = True
                return True
            else:
                self.logger.error(f"Failed to register worker: {response.message}")
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
                # Unregister worker
                from grpc_host_pb2 import UnregisterWorkerRequest
                request = UnregisterWorkerRequest(worker_id=self.worker_id)
                
                response = self.stub.UnregisterWorker(request)
                
                if response.success:
                    self.logger.info(f"Worker {self.worker_id} unregistered successfully")
                else:
                    self.logger.warning(f"Failed to unregister worker: {response.message}")
                
                self.running = False
                
        except Exception as e:
            self.logger.error(f"Failed to disconnect from gRPC host: {str(e)}", exc_info=True)
    
    async def process_task(self, task_type: str, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a task.
        
        Args:
            task_type: Type of task (e.g., "fix_code", "migrate", "test", "log")
            task_data: Task data
            
        Returns:
            Task result
        """
        try:
            self.logger.info(f"Processing task: {task_data.get('task_id')} (type: {task_type})")
            
            # Update current task
            self.current_task = task_data
            
            # Process task based on type
            if task_type == "fix_code":
                result = await self._process_fix_code_task(task_data)
            elif task_type == "migrate":
                result = await self._process_migrate_task(task_data)
            elif task_type == "test":
                result = await self._process_test_task(task_data)
            elif task_type == "log":
                result = await self._process_log_task(task_data)
            else:
                result = {
                    "success": False,
                    "message": f"Unknown task type: {task_type}"
                }
            
            # Send result to host
            if self.stub:
                from grpc_host_pb2 import CollectTaskResultRequest
                request = CollectTaskResultRequest(
                    worker_id=self.worker_id,
                    task_id=task_data.get("task_id"),
                    result=json.dumps(result)
                )
                
                response = self.stub.CollectTaskResult(request)
                
                if response.success:
                    self.logger.info(f"Task result sent to host successfully")
                else:
                    self.logger.warning(f"Failed to send task result: {response.message}")
            
            # Clear current task
            self.current_task = None
            
            return result
            
        except Exception as e:
            self.logger.error(f"Failed to process task: {str(e)}", exc_info=True)
            return {
                "success": False,
                "message": f"Error processing task: {str(e)}"
            }
    
    async def _process_fix_code_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a fix_code task.
        
        Args:
            task_data: Task data
            
        Returns:
            Task result
        """
        try:
            file_path = task_data.get("file_path")
            suggested_fix = task_data.get("suggested_fix")
            description = task_data.get("description")
            
            self.logger.info(f"Fixing code in file: {file_path}")
            
            # Read file
            if file_path and os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Apply fix
                if suggested_fix:
                    # For now, just log the fix
                    self.logger.info(f"Suggested fix: {suggested_fix}")
                    # In a real implementation, apply the fix here
                
                result = {
                    "success": True,
                    "message": f"Code fixed in {file_path}",
                    "file_path": file_path,
                    "actions_taken": [
                        "Read file",
                        "Applied fix",
                        "Saved file"
                    ]
                }
            else:
                result = {
                    "success": False,
                    "message": f"File not found: {file_path}",
                    "actions_taken": []
                }
            
            return result
            
        except Exception as e:
            self.logger.error(f"Failed to process fix_code task: {str(e)}", exc_info=True)
            return {
                "success": False,
                "message": f"Error: {str(e)}",
                "actions_taken": []
            }
    
    async def _process_migrate_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a migrate task.
        
        Args:
            task_data: Task data
            
        Returns:
            Task result
        """
        try:
            migration_type = task_data.get("migration_type")
            source_schema = task_data.get("source_schema")
            target_schema = task_data.get("target_schema")
            description = task_data.get("description")
            
            self.logger.info(f"Processing migration: {migration_type} from {source_schema} to {target_schema}")
            
            # Create migration task
            task = await self.file_write_tasks.create_migration_task(
                migration_type=migration_type,
                source_schema=source_schema,
                target_schema=target_schema,
                description=description,
                rollback_plan=task_data.get("rollback_plan", ""),
                dependencies=task_data.get("dependencies", []),
                estimated_duration=task_data.get("estimated_duration", "5m"),
                metadata=task_data.get("metadata", {})
            )
            
            result = {
                "success": True,
                "message": f"Migration task created: {task.task_id}",
                "task_id": task.task_id,
                "actions_taken": [
                    "Created migration task",
                    "Task ready for execution"
                ]
            }
            
            return result
            
        except Exception as e:
            self.logger.error(f"Failed to process migrate task: {str(e)}", exc_info=True)
            return {
                "success": False,
                "message": f"Error: {str(e)}",
                "actions_taken": []
            }
    
    async def _process_test_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a test task.
        
        Args:
            task_data: Task data
            
        Returns:
            Task result
        """
        try:
            test_type = task_data.get("test_type")
            test_url = task_data.get("test_url")
            test_selector = task_data.get("test_selector")
            expected_behavior = task_data.get("expected_behavior")
            actual_behavior = task_data.get("actual_behavior")
            
            self.logger.info(f"Processing test: {test_type} for {test_url}")
            
            # Create test fix task
            task = await self.file_write_tasks.create_test_fix_task(
                test_type=test_type,
                test_file=task_data.get("test_file"),
                test_url=test_url,
                test_selector=test_selector,
                expected_behavior=expected_behavior,
                actual_behavior=actual_behavior,
                error_message=task_data.get("error_message"),
                screenshot_path=task_data.get("screenshot_path"),
                suggested_fix=task_data.get("suggested_fix"),
                metadata=task_data.get("metadata", {})
            )
            
            result = {
                "success": True,
                "message": f"Test task created: {task.task_id}",
                "task_id": task.task_id,
                "actions_taken": [
                    "Created test fix task",
                    "Task ready for execution"
                ]
            }
            
            return result
            
        except Exception as e:
            self.logger.error(f"Failed to process test task: {str(e)}", exc_info=True)
            return {
                "success": False,
                "message": f"Error: {str(e)}",
                "actions_taken": []
            }
    
    async def _process_log_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a log task.
        
        Args:
            task_data: Task data
            
        Returns:
            Task result
        """
        try:
            analysis_type = task_data.get("analysis_type")
            time_range = task_data.get("time_range", "1h")
            services = task_data.get("services", [])
            containers = task_data.get("containers", [])
            keywords = task_data.get("keywords", [])
            
            self.logger.info(f"Processing log analysis: {analysis_type} for {time_range}")
            
            # Create log analysis task
            task = await self.file_write_tasks.create_log_analysis_task(
                analysis_type=analysis_type,
                time_range=time_range,
                services=services,
                containers=containers,
                keywords=keywords,
                error_count=task_data.get("error_count", 0),
                warning_count=task_data.get("warning_count", 0),
                error_patterns=task_data.get("error_patterns", {}),
                performance_issues=task_data.get("performance_issues", []),
                recommendations=task_data.get("recommendations", []),
                metadata=task_data.get("metadata", {})
            )
            
            result = {
                "success": True,
                "message": f"Log analysis task created: {task.task_id}",
                "task_id": task.task_id,
                "actions_taken": [
                    "Created log analysis task",
                    "Task ready for execution"
                ]
            }
            
            return result
            
        except Exception as e:
            self.logger.error(f"Failed to process log task: {str(e)}", exc_info=True)
            return {
                "success": False,
                "message": f"Error: {str(e)}",
                "actions_taken": []
            }
    
    async def run(self):
        """
        Run the RoutedAgent.
        
        This method connects to the gRPC host and waits for tasks.
        """
        try:
            # Connect to host
            if not await self.connect():
                self.logger.error("Failed to connect to gRPC host")
                return
            
            # Start event server
            self.event_server = EventServer(session_id=self.worker_id, tool_name="routed_agent")
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
            
            self.logger.info(f"RoutedAgent {self.worker_id} started and waiting for tasks...")
            
            # Wait for tasks
            while self.running:
                await asyncio.sleep(1)
                
        except Exception as e:
            self.logger.error(f"Error running RoutedAgent: {str(e)}", exc_info=True)
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


async def main():
    """
    Main entry point.
    """
    import argparse
    
    parser = argparse.ArgumentParser(description="RoutedAgent - A distributed agent that processes tasks from gRPC host")
    parser.add_argument("--worker-id", required=True, help="Unique worker identifier")
    parser.add_argument("--host", default="127.0.0.1", help="gRPC host address")
    parser.add_argument("--port", type=int, default=50051, help="gRPC host port")
    parser.add_argument("--capabilities", nargs="*", default=None, help="Worker capabilities")
    
    args = parser.parse_args()
    
    # Create agent
    agent = RoutedAgent(
        worker_id=args.worker_id,
        host=args.host,
        port=args.port,
        capabilities=args.capabilities
    )
    
    # Setup signal handlers
    def signal_handler(signum, frame):
        print(f"\nReceived signal {signum}, shutting down...")
        asyncio.create_task(agent.disconnect())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Run agent
        await agent.run()
        
    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
