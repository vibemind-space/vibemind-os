"""Workflow Models for TRAE Backend

Defines the data models for workflow execution and management.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class NodeType(str, Enum):
    """Enumeration of available node types"""

    # Trigger Nodes
    MANUAL_TRIGGER = "manual_trigger"
    WEBHOOK_TRIGGER = "webhook_trigger"

    # Configuration Nodes
    WEBSOCKET_CONFIG = "websocket_config"

    # Interface Nodes
    LIVE_DESKTOP = "live_desktop"

    # Action Nodes
    CLICK_ACTION = "click_action"
    TYPE_TEXT_ACTION = "type_text_action"
    HTTP_REQUEST = "http_request"
    SCREENSHOT_ACTION = "screenshot_action"

    # Logic Nodes
    IF_CONDITION = "if_condition"
    DELAY = "delay"

    # Result Nodes
    OCR_REGION = "ocr_region"
    LOGGER = "logger"


class WorkflowNode(BaseModel):
    """Workflow node model"""

    id: str = Field(..., description="Unique node identifier")
    type: NodeType = Field(..., description="Node type")
    position: Dict[str, float] = Field(
        default_factory=dict, description="Node position on canvas"
    )
    config: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="Node configuration"
    )
    data: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="Node data"
    )

    class Config:
        use_enum_values = True


class WorkflowConnection(BaseModel):
    """Workflow connection/edge model"""

    id: str = Field(..., description="Unique connection identifier")
    source: str = Field(..., description="Source node ID")
    target: str = Field(..., description="Target node ID")
    source_handle: Optional[str] = Field(None, description="Source handle ID")
    target_handle: Optional[str] = Field(None, description="Target handle ID")
    data: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="Connection data"
    )


class Workflow(BaseModel):
    """Workflow model"""

    id: Optional[str] = Field(None, description="Unique workflow identifier")
    name: str = Field(..., description="Workflow name")
    description: Optional[str] = Field(None, description="Workflow description")
    nodes: List[WorkflowNode] = Field(
        default_factory=list, description="Workflow nodes"
    )
    connections: List[WorkflowConnection] = Field(
        default_factory=list, description="Workflow connections"
    )
    variables: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="Workflow variables"
    )
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")

    class Config:
        use_enum_values = True


class ExecutionStatus(str, Enum):
    """Execution status enumeration"""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class NodeExecutionResult(BaseModel):
    """Node execution result model"""

    node_id: str = Field(..., description="Node ID")
    status: ExecutionStatus = Field(..., description="Execution status")
    result: Optional[Dict[str, Any]] = Field(None, description="Execution result")
    error: Optional[str] = Field(None, description="Error message if failed")
    started_at: Optional[datetime] = Field(None, description="Execution start time")
    completed_at: Optional[datetime] = Field(
        None, description="Execution completion time"
    )
    duration_ms: Optional[int] = Field(
        None, description="Execution duration in milliseconds"
    )

    class Config:
        use_enum_values = True


class WorkflowExecution(BaseModel):
    """Workflow execution model"""

    id: str = Field(..., description="Unique execution identifier")
    workflow_id: str = Field(..., description="Workflow ID")
    status: ExecutionStatus = Field(..., description="Execution status")
    node_results: Dict[str, NodeExecutionResult] = Field(
        default_factory=dict, description="Node execution results"
    )
    variables: Dict[str, Any] = Field(
        default_factory=dict, description="Execution variables"
    )
    logs: List[str] = Field(default_factory=list, description="Execution logs")
    started_at: Optional[datetime] = Field(None, description="Execution start time")
    completed_at: Optional[datetime] = Field(
        None, description="Execution completion time"
    )
    duration_ms: Optional[int] = Field(
        None, description="Total execution duration in milliseconds"
    )
    debug_mode: bool = Field(False, description="Debug mode enabled")
    step_by_step: bool = Field(False, description="Step-by-step execution enabled")
    current_node: Optional[str] = Field(None, description="Currently executing node ID")
    progress: Optional[Dict[str, int]] = Field(None, description="Execution progress")

    class Config:
        use_enum_values = True


class ExecutionRequest(BaseModel):
    """Workflow execution request model"""

    workflow: Workflow = Field(..., description="Workflow to execute")
    debug_mode: bool = Field(False, description="Enable debug mode")
    step_by_step: bool = Field(False, description="Enable step-by-step execution")
    variables: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="Initial variables"
    )

    class Config:
        use_enum_values = True


class ExecutionControlRequest(BaseModel):
    """Execution control request model"""

    execution_id: str = Field(..., description="Execution ID to control")
    action: str = Field(..., description="Control action (pause, resume, stop, step)")

    class Config:
        use_enum_values = True
