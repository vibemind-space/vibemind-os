"""Graph Execution Service for Workflow Node Execution

This service handles the execution of workflow graphs with real-time updates,
node validation, and filesystem integration for desktop automation.
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

# Import WebSocket broadcast functions
try:
    from app.routers.websocket import (
        broadcast_workflow_execution_update,
        broadcast_node_execution_update,
        broadcast_execution_status_update,
    )
except ImportError:
    # Fallback functions if WebSocket module is not available
    async def broadcast_workflow_execution_update(execution_id: str, update_data: Dict):
        pass

    async def broadcast_node_execution_update(
        execution_id: str, node_id: str, node_data: Dict
    ):
        pass

    async def broadcast_execution_status_update(execution_id: str, status_data: Dict):
        pass


from ..models.workflow import Workflow, WorkflowNode, WorkflowConnection
from ..websocket.manager import WebSocketManager
from .node_service import get_node_service, NodeService
from .click_automation_service import ClickAutomationService
from .desktop_automation_service import DesktopAutomationService
from .ocr_service import OCRService

# Configure logging
logger = logging.getLogger(__name__)


class NodeExecutionStatus(Enum):
    """Node execution status enumeration"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class GraphExecutionStatus(Enum):
    """Graph execution status enumeration"""

    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class NodeExecutionResult:
    """Result of node execution"""

    node_id: str
    status: NodeExecutionStatus
    output_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    execution_time: Optional[float] = None
    timestamp: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = asdict(self)
        result["status"] = self.status.value
        if self.timestamp:
            result["timestamp"] = self.timestamp.isoformat()
        return result


@dataclass
class GraphExecutionState:
    """Current state of graph execution"""

    graph_id: str
    status: GraphExecutionStatus
    current_nodes: Set[str]
    completed_nodes: Set[str]
    failed_nodes: Set[str]
    node_results: Dict[str, NodeExecutionResult]
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "graph_id": self.graph_id,
            "status": self.status.value,
            "current_nodes": list(self.current_nodes),
            "completed_nodes": list(self.completed_nodes),
            "failed_nodes": list(self.failed_nodes),
            "node_results": {k: v.to_dict() for k, v in self.node_results.items()},
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "error_message": self.error_message,
        }


class GraphExecutionService:
    """Service for executing workflow graphs with real-time updates"""

    def __init__(
        self,
        node_service: NodeService,
        websocket_manager: WebSocketManager,
        click_service: ClickAutomationService,
        desktop_service: DesktopAutomationService,
        ocr_service: OCRService,
    ):
        """Initialize the graph execution service"""
        self.node_service = node_service
        self.websocket_manager = websocket_manager
        self.click_service = click_service
        self.desktop_service = desktop_service
        self.ocr_service = ocr_service

        # Execution state management
        self.execution_states: Dict[str, GraphExecutionState] = {}
        self.execution_history: List[GraphExecutionState] = []

        # Filesystem integration
        self.workflow_data_path = Path("./workflow-data")
        self.ensure_filesystem_structure()

        # Node type handlers
        self.node_handlers = {
            "manual_trigger": self._execute_manual_trigger,
            "webhook_trigger": self._execute_webhook_trigger,
            "websocket_config": self._execute_websocket_config,
            "live_desktop": self._execute_live_desktop,
            "click_action": self._execute_click_action,
            "type_text_action": self._execute_type_text_action,
            "http_request_action": self._execute_http_request,
            "if_condition": self._execute_if_condition,
            "delay": self._execute_delay,
            "ocr_region": self._execute_ocr_region,
            "ocr_extract": self._execute_ocr_extract,
            "n8n_webhook": self._execute_n8n_webhook,
            "send_to_filesystem": self._execute_send_to_filesystem,
            "workflow_result": self._execute_workflow_result,
        }

    async def _execute_node_by_type(self, node: WorkflowNode) -> Dict[str, Any]:
        """Execute node based on its type"""
        node_type = node.type
        node_data = node.data if hasattr(node, "data") else {}

        # Trigger Nodes
        if node_type == "manual_trigger":
            return await self._execute_manual_trigger(node_data)
        elif node_type == "webhook_trigger":
            return await self._execute_webhook_trigger(node_data)

        # Config Nodes
        elif node_type == "websocket_config":
            return await self._execute_websocket_config(node_data)
        elif node_type == "live_desktop":
            return await self._execute_live_desktop(node_data)

        # Action Nodes
        elif node_type == "click_action":
            return await self._execute_click_action(node_data)
        elif node_type == "type_text_action":
            return await self._execute_type_text_action(node_data)
        elif node_type == "http_request_action":
            return await self._execute_http_request_action(node_data)
        elif node_type == "ocr_region":
            return await self._execute_ocr_region(node_data)
        elif node_type == "ocr_extract":
            return await self._execute_ocr_extract(node_data)
        elif node_type == "n8n_webhook":
            return await self._execute_n8n_webhook(node_data)
        elif node_type == "send_to_filesystem":
            return await self._execute_send_to_filesystem(node_data)

        # Logic Nodes
        elif node_type == "if_condition":
            return await self._execute_if_condition(node_data)
        elif node_type == "delay":
            return await self._execute_delay(node_data)

        # Result Nodes
        elif node_type == "workflow_result":
            return await self._execute_workflow_result(node_data)

        else:
            logger.warning(f"⚠️ Unknown node type: {node_type}")
            return {"status": "skipped", "message": f"Unknown node type: {node_type}"}

        logger.info("GraphExecutionService initialized")

    def ensure_filesystem_structure(self):
        """Ensure required filesystem structure exists"""
        directories = [
            self.workflow_data_path / "desktop",
            self.workflow_data_path / "actions" / "click",
            self.workflow_data_path / "actions" / "type",
            self.workflow_data_path / "results",
            self.workflow_data_path / "output",
        ]

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Ensured directory exists: {directory}")

    async def execute_graph(self, workflow: Workflow, debug_mode: bool = False) -> str:
        """Execute a workflow graph with real-time updates"""
        graph_id = f"graph_{workflow.id}_{int(time.time())}"

        # Initialize execution state
        execution_state = GraphExecutionState(
            graph_id=graph_id,
            status=GraphExecutionStatus.RUNNING,
            current_nodes=set(),
            completed_nodes=set(),
            failed_nodes=set(),
            node_results={},
            start_time=datetime.now(),
        )

        self.execution_states[graph_id] = execution_state

        # Broadcast execution start
        await broadcast_execution_status_update(
            graph_id,
            {
                "status": "running",
                "start_time": execution_state.start_time.isoformat(),
                "graph_id": graph_id,
                "debug_mode": debug_mode,
                "total_nodes": len(workflow.nodes),
            },
        )

        try:
            # Validate graph before execution
            validation_result = await self._validate_graph(workflow)
            if not validation_result["valid"]:
                execution_state.status = GraphExecutionStatus.FAILED
                execution_state.error_message = validation_result["error"]
                await self._send_execution_update(execution_state)
                return graph_id

            # Send initial execution update
            await self._send_execution_update(execution_state)

            # Perform topological sort to determine execution order
            execution_order = self._topological_sort(
                workflow.nodes, workflow.connections
            )

            # Execute nodes in order
            for node_batch in execution_order:
                if execution_state.status != GraphExecutionStatus.RUNNING:
                    break

                # Execute nodes in parallel within each batch
                tasks = []
                for node in node_batch:
                    execution_state.current_nodes.add(node.id)
                    task = asyncio.create_task(
                        self._execute_node(node, execution_state, debug_mode)
                    )
                    tasks.append(task)

                # Wait for all nodes in batch to complete
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Process results
                for i, result in enumerate(results):
                    node = node_batch[i]
                    execution_state.current_nodes.discard(node.id)

                    if isinstance(result, Exception):
                        execution_state.failed_nodes.add(node.id)
                        execution_state.node_results[node.id] = NodeExecutionResult(
                            node_id=node.id,
                            status=NodeExecutionStatus.FAILED,
                            error_message=str(result),
                            timestamp=datetime.now(),
                        )
                        logger.error(f"Node {node.id} failed: {result}")
                    else:
                        execution_state.completed_nodes.add(node.id)
                        execution_state.node_results[node.id] = result

                # Send progress update
                await self._send_execution_update(execution_state)

                # Check if any critical nodes failed
                if execution_state.failed_nodes:
                    execution_state.status = GraphExecutionStatus.FAILED
                    break

            # Finalize execution
            if execution_state.status == GraphExecutionStatus.RUNNING:
                execution_state.status = GraphExecutionStatus.COMPLETED

            execution_state.end_time = datetime.now()

            # Broadcast execution completion
            await broadcast_execution_status_update(
                graph_id,
                {
                    "status": "completed",
                    "start_time": execution_state.start_time.isoformat(),
                    "end_time": execution_state.end_time.isoformat(),
                    "graph_id": graph_id,
                    "debug_mode": debug_mode,
                    "total_nodes": len(workflow.nodes),
                    "completed_nodes": len(execution_state.completed_nodes),
                },
            )

        except Exception as e:
            logger.error(f"Graph execution failed: {e}")
            execution_state.status = GraphExecutionStatus.FAILED
            execution_state.error_message = str(e)
            execution_state.end_time = datetime.now()

            # Broadcast execution failure
            await broadcast_execution_status_update(
                graph_id,
                {
                    "status": "failed",
                    "start_time": execution_state.start_time.isoformat(),
                    "end_time": execution_state.end_time.isoformat(),
                    "graph_id": graph_id,
                    "debug_mode": debug_mode,
                    "error": str(e),
                    "total_nodes": len(workflow.nodes),
                    "completed_nodes": len(execution_state.completed_nodes),
                },
            )

        # Send final update
        await self._send_execution_update(execution_state)

        # Archive execution state
        self.execution_history.append(execution_state)
        if len(self.execution_history) > 100:  # Keep last 100 executions
            self.execution_history.pop(0)

        return graph_id

    async def _validate_graph(self, workflow: Workflow) -> Dict[str, Any]:
        """Validate graph before execution"""
        try:
            # Check for cycles
            if self._has_cycles(workflow.nodes, workflow.connections):
                return {"valid": False, "error": "Graph contains cycles"}

            # Validate node configurations
            for node in workflow.nodes:
                if not await self._validate_node_config(node):
                    return {
                        "valid": False,
                        "error": f"Invalid configuration for node {node.id}",
                    }

            # Check connectivity
            if not self._validate_connectivity(workflow.nodes, workflow.connections):
                return {"valid": False, "error": "Graph has connectivity issues"}

            return {"valid": True}

        except Exception as e:
            return {"valid": False, "error": f"Validation error: {str(e)}"}

    async def _validate_node_config(self, node: WorkflowNode) -> bool:
        """Validate individual node configuration"""
        try:
            node_type = node.type
            config = node.config or {}

            # Get node template for validation
            templates = await self.node_service.get_templates()
            template = next((t for t in templates if t["id"] == node_type), None)

            if not template:
                logger.warning(f"No template found for node type: {node_type}")
                return False

            # Validate required configuration fields
            config_schema = template.get("configSchema", {})
            for field_name, field_config in config_schema.items():
                if field_config.get("required", False) and field_name not in config:
                    logger.warning(
                        f"Required field {field_name} missing for node {node.id}"
                    )
                    return False

            return True

        except Exception as e:
            logger.error(f"Node config validation failed for {node.id}: {e}")
            return False

    def _topological_sort(
        self, nodes: List[WorkflowNode], connections: List[WorkflowConnection]
    ) -> List[List[WorkflowNode]]:
        """Perform topological sort to determine execution order"""
        # Build adjacency list and in-degree count
        node_map = {node.id: node for node in nodes}
        adjacency = {node.id: [] for node in nodes}
        in_degree = {node.id: 0 for node in nodes}

        for conn in connections:
            adjacency[conn.source_node_id].append(conn.target_node_id)
            in_degree[conn.target_node_id] += 1

        # Find nodes with no incoming edges (starting nodes)
        queue = [node_id for node_id, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            # Process all nodes at current level
            current_batch = [node_map[node_id] for node_id in queue]
            result.append(current_batch)

            # Find next level nodes
            next_queue = []
            for node_id in queue:
                for neighbor in adjacency[node_id]:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        next_queue.append(neighbor)

            queue = next_queue

        return result

    def _has_cycles(
        self, nodes: List[WorkflowNode], connections: List[WorkflowConnection]
    ) -> bool:
        """Check if graph has cycles using DFS"""
        adjacency = {node.id: [] for node in nodes}
        for conn in connections:
            adjacency[conn.source_node_id].append(conn.target_node_id)

        visited = set()
        rec_stack = set()

        def dfs(node_id: str) -> bool:
            visited.add(node_id)
            rec_stack.add(node_id)

            for neighbor in adjacency.get(node_id, []):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True

            rec_stack.remove(node_id)
            return False

        for node in nodes:
            if node.id not in visited:
                if dfs(node.id):
                    return True

        return False

    def _validate_connectivity(
        self, nodes: List[WorkflowNode], connections: List[WorkflowConnection]
    ) -> bool:
        """Validate graph connectivity"""
        # Check if all connections reference valid nodes
        node_ids = {node.id for node in nodes}

        for conn in connections:
            if (
                conn.source_node_id not in node_ids
                or conn.target_node_id not in node_ids
            ):
                return False

        return True

    async def _execute_node(
        self, node: WorkflowNode, execution_state: GraphExecutionState, debug_mode: bool
    ) -> NodeExecutionResult:
        """Execute a single node"""
        start_time = time.time()

        try:
            logger.info(f"Executing node {node.id} of type {node.type}")

            # Broadcast node execution start
            node_data = {
                "status": "running",
                "start_time": datetime.now().isoformat(),
                "node_type": node.type,
                "node_data": node.data if hasattr(node, "data") else {},
            }
            await broadcast_node_execution_update(
                execution_state.graph_id, node.id, node_data
            )

            # Get node handler
            handler = self.node_handlers.get(node.type)
            if not handler:
                raise ValueError(f"No handler found for node type: {node.type}")

            # Execute node with handler
            output_data = await handler(node, execution_state, debug_mode)

            execution_time = time.time() - start_time

            result = NodeExecutionResult(
                node_id=node.id,
                status=NodeExecutionStatus.COMPLETED,
                output_data=output_data,
                execution_time=execution_time,
                timestamp=datetime.now(),
            )

            # Broadcast node execution completion
            completed_data = {
                "status": "completed",
                "start_time": node_data["start_time"],
                "end_time": datetime.now().isoformat(),
                "result": output_data,
                "node_type": node.type,
                "node_data": node.data if hasattr(node, "data") else {},
            }
            await broadcast_node_execution_update(
                execution_state.graph_id, node.id, completed_data
            )

            logger.info(f"Node {node.id} completed in {execution_time:.2f}s")
            return result

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Node {node.id} failed after {execution_time:.2f}s: {e}")

            # Broadcast node execution failure
            failed_data = {
                "status": "failed",
                "start_time": datetime.now().isoformat(),
                "end_time": datetime.now().isoformat(),
                "error": str(e),
                "node_type": node.type,
                "node_data": node.data if hasattr(node, "data") else {},
            }
            await broadcast_node_execution_update(
                execution_state.graph_id, node.id, failed_data
            )

            return NodeExecutionResult(
                node_id=node.id,
                status=NodeExecutionStatus.FAILED,
                error_message=str(e),
                execution_time=execution_time,
                timestamp=datetime.now(),
            )

    async def _send_execution_update(self, execution_state: GraphExecutionState):
        """Send execution update via WebSocket"""
        try:
            update_data = {
                "type": "graph_execution_update",
                "data": execution_state.to_dict(),
            }

            await self.websocket_manager.broadcast_to_room(
                f"workflow_{execution_state.graph_id}", update_data
            )

        except Exception as e:
            logger.error(f"Failed to send execution update: {e}")

    def get_execution_status(self, graph_id: str) -> Optional[Dict[str, Any]]:
        """Get current execution status"""
        execution_state = self.execution_states.get(graph_id)
        if execution_state:
            return execution_state.to_dict()
        return None

    def get_execution_history(self) -> List[Dict[str, Any]]:
        """Get execution history"""
        return [state.to_dict() for state in self.execution_history]

    async def pause_execution(self, graph_id: str) -> bool:
        """Pause graph execution"""
        execution_state = self.execution_states.get(graph_id)
        if execution_state and execution_state.status == GraphExecutionStatus.RUNNING:
            execution_state.status = GraphExecutionStatus.PAUSED
            await self._send_execution_update(execution_state)
            return True
        return False

    async def resume_execution(self, graph_id: str) -> bool:
        """Resume graph execution"""
        execution_state = self.execution_states.get(graph_id)
        if execution_state and execution_state.status == GraphExecutionStatus.PAUSED:
            execution_state.status = GraphExecutionStatus.RUNNING
            await self._send_execution_update(execution_state)
            return True
        return False

    async def cancel_execution(self, graph_id: str) -> bool:
        """Cancel graph execution"""
        execution_state = self.execution_states.get(graph_id)
        if execution_state and execution_state.status in [
            GraphExecutionStatus.RUNNING,
            GraphExecutionStatus.PAUSED,
        ]:
            execution_state.status = GraphExecutionStatus.CANCELLED
            execution_state.end_time = datetime.now()
            await self._send_execution_update(execution_state)
            return True
        return False

    # Node execution handlers
    # ===== TRIGGER NODES =====
    async def _execute_manual_trigger(
        self, node: WorkflowNode, execution_state: GraphExecutionState, debug_mode: bool
    ) -> Dict[str, Any]:
        """Execute manual trigger node"""
        logger.info("🔄 Executing manual trigger")

        return {
            "trigger_type": "manual",
            "triggered_at": datetime.now().isoformat(),
            "status": "triggered",
            "data": node.config or {},
            "node_id": node.id,
        }

    async def _execute_webhook_trigger(
        self, node: WorkflowNode, execution_state: GraphExecutionState, debug_mode: bool
    ) -> Dict[str, Any]:
        """Execute webhook trigger node"""
        config = node.config or {}
        return {
            "trigger_type": "webhook",
            "webhook_url": config.get("webhook_url", ""),
            "triggered_at": datetime.now().isoformat(),
            "node_id": node.id,
        }

    async def _execute_websocket_config(
        self, node: WorkflowNode, execution_state: GraphExecutionState, debug_mode: bool
    ) -> Dict[str, Any]:
        """Execute websocket config node"""
        config = node.config or {}
        return {
            "config_type": "websocket",
            "port": config.get("port", 8080),
            "host": config.get("host", "localhost"),
            "configured_at": datetime.now().isoformat(),
            "node_id": node.id,
        }

    async def _execute_live_desktop(
        self, node: WorkflowNode, execution_state: GraphExecutionState, debug_mode: bool
    ) -> Dict[str, Any]:
        """Execute live desktop node"""
        config = node.config or {}

        # Start desktop streaming if configured
        if config.get("enable_filesystem", True):
            data_path = Path(config.get("data_output_path", "./workflow-data/desktop"))
            data_path.mkdir(parents=True, exist_ok=True)

            # Write desktop stream metadata
            metadata = {
                "fps": config.get("fps", 30),
                "quality": config.get("quality", 80),
                "width": config.get("width", 1200),
                "height": config.get("height", 900),
                "started_at": datetime.now().isoformat(),
                "node_id": node.id,
            }

            metadata_file = data_path / "stream_metadata.json"
            with open(metadata_file, "w") as f:
                json.dump(metadata, f, indent=2)

        return {
            "interface_type": "desktop_stream",
            "filesystem_bridge": True,
            "stream_active": True,
            "metadata": metadata,
            "node_id": node.id,
        }

    async def _execute_click_action(
        self, node: WorkflowNode, execution_state: GraphExecutionState, debug_mode: bool
    ) -> Dict[str, Any]:
        """Execute click action node"""
        config = node.config or {}

        x = config.get("x", 0)
        y = config.get("y", 0)
        button = config.get("button", "left")

        # Write click command to filesystem if configured
        if config.get("output_to_filesystem", True):
            action_path = Path(
                config.get(
                    "command_file", "./workflow-data/actions/click/click_command.json"
                )
            )
            action_path.parent.mkdir(parents=True, exist_ok=True)

            click_command = {
                "action": "click",
                "x": x,
                "y": y,
                "button": button,
                "timestamp": datetime.now().isoformat(),
                "node_id": node.id,
            }

            with open(action_path, "w") as f:
                json.dump(click_command, f, indent=2)

        # Execute click action via automation service
        try:
            await self.click_service.click(x, y, button)
            success = True
            error = None
        except Exception as e:
            success = False
            error = str(e)

        return {
            "action_type": "click",
            "coordinates": {"x": x, "y": y},
            "button": button,
            "success": success,
            "error": error,
            "executed_at": datetime.now().isoformat(),
            "node_id": node.id,
        }

    async def _execute_type_text_action(
        self, node: WorkflowNode, execution_state: GraphExecutionState, debug_mode: bool
    ) -> Dict[str, Any]:
        """Execute type text action node"""
        config = node.config or {}

        text = config.get("text", "")
        delay = config.get("delay", 100)

        # Write type command to filesystem if configured
        if config.get("output_to_filesystem", True):
            action_path = Path(
                config.get(
                    "command_file", "./workflow-data/actions/type/type_command.json"
                )
            )
            action_path.parent.mkdir(parents=True, exist_ok=True)

            type_command = {
                "action": "type",
                "text": text,
                "delay": delay,
                "timestamp": datetime.now().isoformat(),
                "node_id": node.id,
            }

            with open(action_path, "w") as f:
                json.dump(type_command, f, indent=2)

        # Execute type action via automation service
        try:
            await self.desktop_service.type_text(text, delay)
            success = True
            error = None
        except Exception as e:
            success = False
            error = str(e)

        return {
            "action_type": "type",
            "text": text,
            "delay": delay,
            "success": success,
            "error": error,
            "executed_at": datetime.now().isoformat(),
            "node_id": node.id,
        }

    async def _execute_http_request_action(
        self, node_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute HTTP request action node"""
        import aiohttp

        config = node_data.get("config", {})
        url = config.get("url", "")
        method = config.get("method", "POST")
        headers = config.get("headers", {})

        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(method, url, headers=headers) as response:
                    response_data = await response.text()

                    return {
                        "action_type": "http_request",
                        "url": url,
                        "method": method,
                        "status_code": response.status,
                        "response_data": response_data,
                        "success": True,
                        "executed_at": datetime.now().isoformat(),
                        "node_id": node_data.get("id"),
                    }
        except Exception as e:
            return {
                "action_type": "http_request",
                "url": url,
                "method": method,
                "success": False,
                "error": str(e),
                "executed_at": datetime.now().isoformat(),
                "node_id": node_data.get("id"),
            }

    async def _execute_http_request(
        self, node: WorkflowNode, execution_state: GraphExecutionState, debug_mode: bool
    ) -> Dict[str, Any]:
        """Execute HTTP request action node"""
        import aiohttp

        config = node.config or {}
        url = config.get("url", "")
        method = config.get("method", "POST")
        headers = config.get("headers", {})

        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(method, url, headers=headers) as response:
                    response_data = await response.text()

                    return {
                        "action_type": "http_request",
                        "url": url,
                        "method": method,
                        "status_code": response.status,
                        "response_data": response_data,
                        "success": True,
                        "executed_at": datetime.now().isoformat(),
                        "node_id": node.id,
                    }
        except Exception as e:
            return {
                "action_type": "http_request",
                "url": url,
                "method": method,
                "success": False,
                "error": str(e),
                "executed_at": datetime.now().isoformat(),
                "node_id": node.id,
            }

    async def _execute_if_condition(
        self, node: WorkflowNode, execution_state: GraphExecutionState, debug_mode: bool
    ) -> Dict[str, Any]:
        """Execute if condition logic node"""
        config = node.config or {}
        condition = config.get("condition", "")
        operator = config.get("operator", "equals")

        # Simple condition evaluation (can be extended)
        result = False
        if operator == "equals":
            result = condition == "true"
        elif operator == "contains":
            result = "true" in condition.lower()

        return {
            "logic_type": "condition",
            "condition": condition,
            "operator": operator,
            "result": result,
            "evaluated_at": datetime.now().isoformat(),
            "node_id": node.id,
        }

    async def _execute_delay(
        self, node: WorkflowNode, execution_state: GraphExecutionState, debug_mode: bool
    ) -> Dict[str, Any]:
        """Execute delay logic node"""
        config = node.config or {}
        duration = config.get("duration", 1000) / 1000  # Convert to seconds

        await asyncio.sleep(duration)

        return {
            "logic_type": "delay",
            "duration_ms": config.get("duration", 1000),
            "completed_at": datetime.now().isoformat(),
            "node_id": node.id,
        }

    async def _execute_ocr_region(
        self, node: WorkflowNode, execution_state: GraphExecutionState, debug_mode: bool
    ) -> Dict[str, Any]:
        """Execute OCR region definition node"""
        config = node.config or {}

        region_data = {
            "x": config.get("x", 100),
            "y": config.get("y", 100),
            "width": config.get("width", 200),
            "height": config.get("height", 50),
            "label": config.get("label", "Region 1"),
            "enabled": config.get("enabled", True),
        }

        return {
            "action_type": "ocr_region",
            "region_data": region_data,
            "defined_at": datetime.now().isoformat(),
            "node_id": node.id,
        }

    async def _execute_ocr_extract(
        self, node: WorkflowNode, execution_state: GraphExecutionState, debug_mode: bool
    ) -> Dict[str, Any]:
        """Execute OCR text extraction node"""
        config = node.config or {}

        try:
            # Use OCR service to extract text
            extracted_text = await self.ocr_service.extract_text_from_region(
                x=config.get("x", 100),
                y=config.get("y", 100),
                width=config.get("width", 200),
                height=config.get("height", 50),
            )

            return {
                "action_type": "ocr_extract",
                "extracted_text": extracted_text,
                "confidence": config.get("confidence_threshold", 0.7),
                "success": True,
                "extracted_at": datetime.now().isoformat(),
                "node_id": node.id,
            }
        except Exception as e:
            return {
                "action_type": "ocr_extract",
                "success": False,
                "error": str(e),
                "extracted_at": datetime.now().isoformat(),
                "node_id": node.id,
            }

    async def _execute_n8n_webhook(
        self, node: WorkflowNode, execution_state: GraphExecutionState, debug_mode: bool
    ) -> Dict[str, Any]:
        """Execute N8N webhook node"""
        import aiohttp

        config = node.config or {}
        webhook_url = config.get("webhook_url", "")

        try:
            # Get input data from previous nodes
            input_data = self._get_node_input_data(node, execution_state)

            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=input_data) as response:
                    response_data = await response.json()

                    return {
                        "action_type": "n8n_webhook",
                        "webhook_url": webhook_url,
                        "response_data": response_data,
                        "success": True,
                        "sent_at": datetime.now().isoformat(),
                        "node_id": node.id,
                    }
        except Exception as e:
            return {
                "action_type": "n8n_webhook",
                "webhook_url": webhook_url,
                "success": False,
                "error": str(e),
                "sent_at": datetime.now().isoformat(),
                "node_id": node.id,
            }

    async def _execute_send_to_filesystem(
        self, node: WorkflowNode, execution_state: GraphExecutionState, debug_mode: bool
    ) -> Dict[str, Any]:
        """Execute send to filesystem node"""
        config = node.config or {}

        # Get input data from previous nodes
        input_data = self._get_node_input_data(node, execution_state)

        output_dir = Path(config.get("output_directory", "./workflow-data/output"))
        output_dir.mkdir(parents=True, exist_ok=True)

        filename_template = config.get("filename_template", "data_{timestamp}_{type}")
        file_format = config.get("file_format", "json")

        # Generate filename
        timestamp = int(time.time())
        filename = filename_template.format(timestamp=timestamp, type=node.type)
        filepath = output_dir / f"{filename}.{file_format}"

        try:
            # Write data to filesystem
            with open(filepath, "w") as f:
                if file_format == "json":
                    json.dump(input_data, f, indent=2)
                else:
                    f.write(str(input_data))

            return {
                "action_type": "filesystem_save",
                "filepath": str(filepath),
                "file_format": file_format,
                "data_size": len(str(input_data)),
                "success": True,
                "saved_at": datetime.now().isoformat(),
                "node_id": node.id,
            }
        except Exception as e:
            return {
                "action_type": "filesystem_save",
                "success": False,
                "error": str(e),
                "saved_at": datetime.now().isoformat(),
                "node_id": node.id,
            }

    async def _execute_workflow_result(
        self, node: WorkflowNode, execution_state: GraphExecutionState, debug_mode: bool
    ) -> Dict[str, Any]:
        """Execute workflow result aggregation node"""
        config = node.config or {}

        # Aggregate all node results
        aggregated_results = {
            "workflow_id": execution_state.graph_id,
            "execution_summary": {
                "total_nodes": len(execution_state.node_results),
                "completed_nodes": len(execution_state.completed_nodes),
                "failed_nodes": len(execution_state.failed_nodes),
                "execution_status": execution_state.status.value,
            },
            "node_results": {
                k: v.to_dict() for k, v in execution_state.node_results.items()
            },
            "aggregated_at": datetime.now().isoformat(),
            "node_id": node.id,
        }

        # Save results to filesystem if configured
        if config.get("export_results", False):
            export_path = Path(config.get("export_path", "./exports"))
            export_path.mkdir(parents=True, exist_ok=True)

            result_file = (
                export_path / f"workflow_results_{execution_state.graph_id}.json"
            )
            with open(result_file, "w") as f:
                json.dump(aggregated_results, f, indent=2)

        return aggregated_results

    def _get_node_input_data(
        self, node: WorkflowNode, execution_state: GraphExecutionState
    ) -> Dict[str, Any]:
        """Get input data for a node from previous node results"""
        # This is a simplified implementation
        # In a real implementation, you would trace back through connections
        # to get the actual output data from connected nodes

        input_data = {
            "node_id": node.id,
            "node_type": node.type,
            "config": node.config or {},
            "previous_results": [],
        }

        # Add results from completed nodes
        for node_id, result in execution_state.node_results.items():
            if result.status == NodeExecutionStatus.COMPLETED and result.output_data:
                input_data["previous_results"].append(
                    {"source_node_id": node_id, "data": result.output_data}
                )

        return input_data


# Factory function for dependency injection
def get_graph_execution_service(
    websocket_manager: WebSocketManager,
    click_service: ClickAutomationService,
    desktop_service: DesktopAutomationService,
    ocr_service: OCRService,
) -> GraphExecutionService:
    """Factory function to create GraphExecutionService instance"""
    return GraphExecutionService(
        node_service=get_node_service(),
        websocket_manager=websocket_manager,
        click_service=click_service,
        desktop_service=desktop_service,
        ocr_service=ocr_service,
    )
