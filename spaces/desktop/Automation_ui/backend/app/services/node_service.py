#!/usr/bin/env python3
"""
TRAE Remote Frontend Backend Node Service
Handles node system operations and business logic

Author: TRAE Development Team
Version: 1.0.0
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiofiles
from fastapi import HTTPException

from ..core.config import settings
from ..core.websocket_manager import websocket_manager
from ..schemas.node_schemas import (ConnectionCreateRequest, ConnectionType,
                                    DataType, GraphCreateRequest,
                                    GraphExecutionResult, GraphUpdateRequest,
                                    GraphValidationResult, Node,
                                    NodeConfiguration, NodeConnection,
                                    NodeData, NodeExecutionRequest,
                                    NodeExecutionResult, NodeGraph,
                                    NodeLibrary, NodeMetadata, NodePort,
                                    NodePosition, NodeSearchRequest, NodeSize,
                                    NodeStatistics, NodeStatus, NodeTemplate,
                                    NodeType, NodeUpdateRequest,
                                    NodeValidationError)

logger = logging.getLogger(__name__)


class NodeService:
    """Service for managing nodes and node graphs"""

    def __init__(self):
        self.graphs: Dict[str, NodeGraph] = {}
        self.templates: Dict[str, NodeTemplate] = {}
        self.libraries: Dict[str, NodeLibrary] = {}
        self.execution_results: Dict[str, GraphExecutionResult] = {}
        self._execution_tasks: Dict[str, asyncio.Task] = {}

        # Initialize with built-in templates - will be called during startup
        self._initialized = False

    async def initialize(self):
        """Initialize the node service"""
        if not self._initialized:
            await self._initialize_builtin_templates()
            self._initialized = True

    async def _initialize_builtin_templates(self):
        """Initialize built-in node templates"""
        builtin_templates = [
            NodeTemplate(
                id="input_text",
                name="Text Input",
                node_type=NodeType.INPUT,
                category="Input",
                description="Text input node",
                output_ports=[
                    NodePort(id="text", name="Text", data_type=DataType.STRING)
                ],
                metadata=NodeMetadata(icon="📝", color="#4CAF50"),
            ),
            NodeTemplate(
                id="output_display",
                name="Display Output",
                node_type=NodeType.OUTPUT,
                category="Output",
                description="Display output node",
                input_ports=[
                    NodePort(
                        id="data", name="Data", data_type=DataType.ANY, required=True
                    )
                ],
                metadata=NodeMetadata(icon="📺", color="#2196F3"),
            ),
            NodeTemplate(
                id="string_process",
                name="String Processor",
                node_type=NodeType.PROCESS,
                category="Text",
                description="Process string data",
                input_ports=[
                    NodePort(
                        id="input",
                        name="Input",
                        data_type=DataType.STRING,
                        required=True,
                    ),
                    NodePort(
                        id="operation",
                        name="Operation",
                        data_type=DataType.STRING,
                        default_value="uppercase",
                    ),
                ],
                output_ports=[
                    NodePort(id="output", name="Output", data_type=DataType.STRING)
                ],
                metadata=NodeMetadata(icon="🔤", color="#FF9800"),
            ),
            NodeTemplate(
                id="condition_check",
                name="Condition",
                node_type=NodeType.CONDITION,
                category="Logic",
                description="Conditional logic node",
                input_ports=[
                    NodePort(
                        id="condition",
                        name="Condition",
                        data_type=DataType.BOOLEAN,
                        required=True,
                    )
                ],
                output_ports=[
                    NodePort(id="true", name="True", data_type=DataType.ANY),
                    NodePort(id="false", name="False", data_type=DataType.ANY),
                ],
                metadata=NodeMetadata(icon="❓", color="#9C27B0"),
            ),
            NodeTemplate(
                id="variable_store",
                name="Variable",
                node_type=NodeType.VARIABLE,
                category="Data",
                description="Store and retrieve variables",
                input_ports=[
                    NodePort(id="value", name="Value", data_type=DataType.ANY)
                ],
                output_ports=[
                    NodePort(id="value", name="Value", data_type=DataType.ANY)
                ],
                metadata=NodeMetadata(icon="📦", color="#607D8B"),
            ),
        ]

        for template in builtin_templates:
            self.templates[template.id] = template

        # Create default library
        default_library = NodeLibrary(
            id="builtin",
            name="Built-in Nodes",
            description="Default node library",
            version="1.0.0",
            templates=builtin_templates,
            categories=["Input", "Output", "Text", "Logic", "Data"],
        )
        self.libraries["builtin"] = default_library

        logger.info(f"Initialized {len(builtin_templates)} built-in node templates")

    # Graph Management
    async def create_graph(self, request: GraphCreateRequest) -> NodeGraph:
        """Create a new node graph"""
        graph_id = str(uuid.uuid4())

        graph = NodeGraph(
            id=graph_id, name=request.name, description=request.description
        )

        # If template specified, load from template
        if request.template_id and request.template_id in self.templates:
            template = self.templates[request.template_id]
            # Add template-based initialization logic here

        self.graphs[graph_id] = graph

        # Notify WebSocket clients
        await websocket_manager.publish_to_topic(
            "graph_updates",
            {"type": "graph_created", "graph_id": graph_id, "graph": graph.dict()},
        )

        logger.info(f"Created new graph: {graph.name} ({graph_id})")
        return graph

    async def get_graph(self, graph_id: str) -> Optional[NodeGraph]:
        """Get a graph by ID"""
        return self.graphs.get(graph_id)

    async def list_graphs(self) -> List[NodeGraph]:
        """List all graphs"""
        return list(self.graphs.values())

    async def update_graph(
        self, graph_id: str, request: GraphUpdateRequest
    ) -> NodeGraph:
        """Update a graph"""
        if graph_id not in self.graphs:
            raise HTTPException(status_code=404, detail="Graph not found")

        graph = self.graphs[graph_id]

        if request.name is not None:
            graph.name = request.name
        if request.description is not None:
            graph.description = request.description
        if request.viewport is not None:
            graph.viewport = request.viewport
        if request.grid_size is not None:
            graph.grid_size = request.grid_size
        if request.snap_to_grid is not None:
            graph.snap_to_grid = request.snap_to_grid

        graph.updated_at = datetime.now()

        # Notify WebSocket clients
        await websocket_manager.publish_to_topic(
            "graph_updates",
            {"type": "graph_updated", "graph_id": graph_id, "graph": graph.dict()},
        )

        return graph

    async def delete_graph(self, graph_id: str) -> bool:
        """Delete a graph"""
        if graph_id not in self.graphs:
            return False

        # Stop any running executions
        if graph_id in self._execution_tasks:
            self._execution_tasks[graph_id].cancel()
            del self._execution_tasks[graph_id]

        del self.graphs[graph_id]

        # Notify WebSocket clients
        await websocket_manager.publish_to_topic(
            "graph_updates", {"type": "graph_deleted", "graph_id": graph_id}
        )

        logger.info(f"Deleted graph: {graph_id}")
        return True

    # Node Management
    async def create_node(
        self, graph_id: str, template_id: str, position: NodePosition
    ) -> Node:
        """Create a new node in a graph"""
        if graph_id not in self.graphs:
            raise HTTPException(status_code=404, detail="Graph not found")

        if template_id not in self.templates:
            raise HTTPException(status_code=404, detail="Template not found")

        template = self.templates[template_id]
        node_id = str(uuid.uuid4())

        node = Node(
            id=node_id,
            name=template.name,
            node_type=template.node_type,
            position=position,
            input_ports=template.input_ports.copy(),
            output_ports=template.output_ports.copy(),
            configuration=template.default_configuration.copy(),
            metadata=template.metadata.copy(),
        )

        graph = self.graphs[graph_id]
        graph.nodes.append(node)
        graph.updated_at = datetime.now()

        # Notify WebSocket clients
        await websocket_manager.publish_to_topic(
            "node_updates",
            {"type": "node_created", "graph_id": graph_id, "node": node.dict()},
        )

        logger.info(f"Created node: {node.name} ({node_id}) in graph {graph_id}")
        return node

    async def get_node(self, graph_id: str, node_id: str) -> Optional[Node]:
        """Get a node by ID"""
        if graph_id not in self.graphs:
            return None

        graph = self.graphs[graph_id]
        for node in graph.nodes:
            if node.id == node_id:
                return node
        return None

    async def update_node(
        self, graph_id: str, node_id: str, request: NodeUpdateRequest
    ) -> Node:
        """Update a node"""
        node = await self.get_node(graph_id, node_id)
        if not node:
            raise HTTPException(status_code=404, detail="Node not found")

        if request.name is not None:
            node.name = request.name
        if request.position is not None:
            node.position = request.position
        if request.size is not None:
            node.size = request.size
        if request.configuration is not None:
            node.configuration = request.configuration
        if request.metadata is not None:
            node.metadata = request.metadata
        if request.data is not None:
            node.data.state.update(request.data)

        node.updated_at = datetime.now()

        graph = self.graphs[graph_id]
        graph.updated_at = datetime.now()

        # Notify WebSocket clients
        await websocket_manager.publish_to_topic(
            "node_updates",
            {"type": "node_updated", "graph_id": graph_id, "node": node.dict()},
        )

        return node

    async def delete_node(self, graph_id: str, node_id: str) -> bool:
        """Delete a node"""
        if graph_id not in self.graphs:
            return False

        graph = self.graphs[graph_id]

        # Find and remove the node
        node_index = None
        for i, node in enumerate(graph.nodes):
            if node.id == node_id:
                node_index = i
                break

        if node_index is None:
            return False

        # Remove connections involving this node
        graph.connections = [
            conn
            for conn in graph.connections
            if conn.source_node_id != node_id and conn.target_node_id != node_id
        ]

        # Remove the node
        del graph.nodes[node_index]
        graph.updated_at = datetime.now()

        # Notify WebSocket clients
        await websocket_manager.publish_to_topic(
            "node_updates",
            {"type": "node_deleted", "graph_id": graph_id, "node_id": node_id},
        )

        logger.info(f"Deleted node: {node_id} from graph {graph_id}")
        return True

    # Connection Management
    async def create_connection(
        self, graph_id: str, request: ConnectionCreateRequest
    ) -> NodeConnection:
        """Create a connection between nodes"""
        if graph_id not in self.graphs:
            raise HTTPException(status_code=404, detail="Graph not found")

        graph = self.graphs[graph_id]

        # Validate nodes exist
        source_node = await self.get_node(graph_id, request.source_node_id)
        target_node = await self.get_node(graph_id, request.target_node_id)

        if not source_node or not target_node:
            raise HTTPException(
                status_code=404, detail="Source or target node not found"
            )

        # Validate ports exist
        source_port = next(
            (p for p in source_node.output_ports if p.id == request.source_port_id),
            None,
        )
        target_port = next(
            (p for p in target_node.input_ports if p.id == request.target_port_id), None
        )

        if not source_port or not target_port:
            raise HTTPException(
                status_code=404, detail="Source or target port not found"
            )

        # Check for existing connection to target port (if not multiple)
        if not target_port.multiple:
            existing = next(
                (
                    c
                    for c in graph.connections
                    if c.target_node_id == request.target_node_id
                    and c.target_port_id == request.target_port_id
                ),
                None,
            )
            if existing:
                raise HTTPException(
                    status_code=400, detail="Target port already connected"
                )

        connection_id = str(uuid.uuid4())
        connection = NodeConnection(
            id=connection_id,
            source_node_id=request.source_node_id,
            source_port_id=request.source_port_id,
            target_node_id=request.target_node_id,
            target_port_id=request.target_port_id,
            connection_type=request.connection_type,
        )

        graph.connections.append(connection)
        graph.updated_at = datetime.now()

        # Notify WebSocket clients
        await websocket_manager.publish_to_topic(
            "connection_updates",
            {
                "type": "connection_created",
                "graph_id": graph_id,
                "connection": connection.dict(),
            },
        )

        logger.info(f"Created connection: {connection_id} in graph {graph_id}")
        return connection

    async def delete_connection(self, graph_id: str, connection_id: str) -> bool:
        """Delete a connection"""
        if graph_id not in self.graphs:
            return False

        graph = self.graphs[graph_id]

        # Find and remove the connection
        connection_index = None
        for i, conn in enumerate(graph.connections):
            if conn.id == connection_id:
                connection_index = i
                break

        if connection_index is None:
            return False

        del graph.connections[connection_index]
        graph.updated_at = datetime.now()

        # Notify WebSocket clients
        await websocket_manager.publish_to_topic(
            "connection_updates",
            {
                "type": "connection_deleted",
                "graph_id": graph_id,
                "connection_id": connection_id,
            },
        )

        logger.info(f"Deleted connection: {connection_id} from graph {graph_id}")
        return True

    # Template Management
    async def get_templates(self) -> List[NodeTemplate]:
        """Get all node templates"""
        return list(self.templates.values())

    async def get_template(self, template_id: str) -> Optional[NodeTemplate]:
        """Get a template by ID"""
        return self.templates.get(template_id)

    async def get_libraries(self) -> List[NodeLibrary]:
        """Get all node libraries"""
        return list(self.libraries.values())

    # Execution
    async def execute_node(
        self, graph_id: str, node_id: str, inputs: Dict[str, Any]
    ) -> NodeExecutionResult:
        """Execute a single node"""
        node = await self.get_node(graph_id, node_id)
        if not node:
            raise HTTPException(status_code=404, detail="Node not found")

        start_time = datetime.now()

        try:
            # Set node status to running
            node.status = NodeStatus.RUNNING
            node.data.inputs = inputs

            # Notify WebSocket clients
            await websocket_manager.publish_to_topic(
                "execution_updates",
                {
                    "type": "node_execution_started",
                    "graph_id": graph_id,
                    "node_id": node_id,
                },
            )

            # Simulate node execution based on type
            outputs = await self._execute_node_logic(node, inputs)

            # Update node data
            node.data.outputs = outputs
            node.data.last_executed = start_time
            node.status = NodeStatus.SUCCESS

            execution_time = (datetime.now() - start_time).total_seconds()
            node.data.execution_time = execution_time

            result = NodeExecutionResult(
                node_id=node_id,
                status=NodeStatus.SUCCESS,
                outputs=outputs,
                execution_time=execution_time,
                timestamp=start_time,
            )

            # Notify WebSocket clients
            await websocket_manager.publish_to_topic(
                "execution_updates",
                {
                    "type": "node_execution_completed",
                    "graph_id": graph_id,
                    "result": result.dict(),
                },
            )

            return result

        except Exception as e:
            error_message = str(e)
            node.status = NodeStatus.ERROR
            node.data.error_message = error_message

            execution_time = (datetime.now() - start_time).total_seconds()

            result = NodeExecutionResult(
                node_id=node_id,
                status=NodeStatus.ERROR,
                error_message=error_message,
                execution_time=execution_time,
                timestamp=start_time,
            )

            # Notify WebSocket clients
            await websocket_manager.publish_to_topic(
                "execution_updates",
                {
                    "type": "node_execution_failed",
                    "graph_id": graph_id,
                    "result": result.dict(),
                },
            )

            return result

    async def _execute_node_logic(
        self, node: Node, inputs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute node-specific logic"""
        # This is a simplified implementation
        # In a real system, this would dispatch to specific node handlers

        if node.node_type == NodeType.INPUT:
            # Input nodes just pass through their configured value
            return {"text": inputs.get("value", "Hello World")}

        elif node.node_type == NodeType.OUTPUT:
            # Output nodes display the input
            return {"display": inputs.get("data", "")}

        elif node.node_type == NodeType.PROCESS:
            # String processing example
            if "string_process" in node.id or "string" in node.name.lower():
                text = inputs.get("input", "")
                operation = inputs.get("operation", "uppercase")

                if operation == "uppercase":
                    result = text.upper()
                elif operation == "lowercase":
                    result = text.lower()
                elif operation == "reverse":
                    result = text[::-1]
                else:
                    result = text

                return {"output": result}

        elif node.node_type == NodeType.CONDITION:
            condition = inputs.get("condition", False)
            if condition:
                return {"true": inputs.get("data", True)}
            else:
                return {"false": inputs.get("data", False)}

        elif node.node_type == NodeType.VARIABLE:
            # Variable nodes store and retrieve values
            value = inputs.get("value", node.data.state.get("stored_value"))
            node.data.state["stored_value"] = value
            return {"value": value}

        # Default: pass through inputs as outputs
        return inputs

    async def get_statistics(self) -> NodeStatistics:
        """Get node system statistics"""
        total_nodes = sum(len(graph.nodes) for graph in self.graphs.values())
        total_executions = len(self.execution_results)
        active_executions = len(self._execution_tasks)

        node_types_count = {}
        for graph in self.graphs.values():
            for node in graph.nodes:
                node_type = node.node_type.value
                node_types_count[node_type] = node_types_count.get(node_type, 0) + 1

        return NodeStatistics(
            total_nodes=total_nodes,
            total_graphs=len(self.graphs),
            total_executions=total_executions,
            active_executions=active_executions,
            node_types_count=node_types_count,
            execution_stats={
                "success_rate": 0.95,  # Mock data
                "avg_execution_time": 0.5,
            },
            performance_metrics={"memory_usage": 50.0, "cpu_usage": 25.0},
        )


# Global service instance - will be initialized during startup
node_service = None


def get_node_service() -> NodeService:
    """Get the global node service instance"""
    global node_service
    if node_service is None:
        node_service = NodeService()
    return node_service
