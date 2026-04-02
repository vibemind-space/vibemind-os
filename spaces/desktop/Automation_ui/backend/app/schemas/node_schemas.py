"""Node Configuration Schemas for TRAE Backend

Defines Pydantic schemas for validating node configurations.
"""

import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List, Union
from pydantic import BaseModel, Field, validator
from enum import Enum


class HttpMethod(str, Enum):
    """HTTP methods enumeration"""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


class ConditionOperator(str, Enum):
    """Condition operators enumeration"""

    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    GREATER_EQUAL = "greater_equal"
    LESS_EQUAL = "less_equal"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    IS_EMPTY = "is_empty"
    IS_NOT_EMPTY = "is_not_empty"


class LogLevel(str, Enum):
    """Log levels enumeration"""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class NodeConfigSchema(BaseModel):
    """Base schema for node configurations"""

    enabled: bool = Field(True, description="Whether the node is enabled")
    description: Optional[str] = Field(None, description="Node description")

    class Config:
        extra = "allow"


# Trigger Node Schemas
class ManualTriggerConfig(NodeConfigSchema):
    """Manual trigger configuration"""

    trigger_name: str = Field(..., description="Name of the trigger")
    auto_start: bool = Field(False, description="Auto-start workflow")


class WebhookTriggerConfig(NodeConfigSchema):
    """Webhook trigger configuration"""

    webhook_url: str = Field(..., description="Webhook URL path")
    method: HttpMethod = Field(HttpMethod.POST, description="HTTP method")
    authentication_required: bool = Field(False, description="Require authentication")
    response_data: Optional[Dict[str, Any]] = Field(
        None, description="Response data template"
    )


# Configuration Node Schemas
class WebsocketConfigSchema(NodeConfigSchema):
    """WebSocket configuration"""

    url: str = Field(..., description="WebSocket URL")
    auto_reconnect: bool = Field(True, description="Auto-reconnect on disconnect")
    reconnect_interval: int = Field(5000, description="Reconnect interval in ms")
    max_reconnect_attempts: int = Field(10, description="Maximum reconnect attempts")
    headers: Optional[Dict[str, str]] = Field(None, description="Connection headers")


# Interface Node Schemas
class LiveDesktopConfig(NodeConfigSchema):
    """Live desktop configuration"""

    session_name: str = Field(..., description="Desktop session name")
    resolution: Optional[str] = Field("1920x1080", description="Screen resolution")
    quality: int = Field(80, description="Stream quality (1-100)")
    frame_rate: int = Field(30, description="Frame rate")
    enable_audio: bool = Field(False, description="Enable audio streaming")


# Action Node Schemas
class ClickActionConfig(NodeConfigSchema):
    """Click action configuration"""

    x: int = Field(..., description="X coordinate")
    y: int = Field(..., description="Y coordinate")
    button: str = Field("left", description="Mouse button (left, right, middle)")
    click_count: int = Field(1, description="Number of clicks")
    delay_after: int = Field(100, description="Delay after click in ms")
    output_to_filesystem: bool = Field(
        False, description="Output command to filesystem"
    )

    @validator("button")
    def validate_button(cls, v):
        if v not in ["left", "right", "middle"]:
            raise ValueError("Button must be left, right, or middle")
        return v


class TypeTextActionConfig(NodeConfigSchema):
    """Type text action configuration"""

    text: str = Field(..., description="Text to type")
    delay_between_chars: int = Field(50, description="Delay between characters in ms")
    clear_before_typing: bool = Field(False, description="Clear field before typing")
    press_enter_after: bool = Field(False, description="Press Enter after typing")
    output_to_filesystem: bool = Field(
        False, description="Output command to filesystem"
    )


class HttpRequestConfig(NodeConfigSchema):
    """HTTP request configuration"""

    url: str = Field(..., description="Request URL")
    method: HttpMethod = Field(HttpMethod.GET, description="HTTP method")
    headers: Optional[Dict[str, str]] = Field(None, description="Request headers")
    body: Optional[Union[str, Dict[str, Any]]] = Field(None, description="Request body")
    timeout: int = Field(30, description="Request timeout in seconds")
    follow_redirects: bool = Field(True, description="Follow redirects")
    verify_ssl: bool = Field(True, description="Verify SSL certificates")
    auth: Optional[Dict[str, str]] = Field(
        None, description="Authentication credentials"
    )


class ScreenshotActionConfig(NodeConfigSchema):
    """Screenshot action configuration"""

    region: Optional[Dict[str, int]] = Field(
        None, description="Screenshot region {x, y, width, height}"
    )
    format: str = Field("png", description="Image format (png, jpg, bmp)")
    quality: int = Field(90, description="Image quality (1-100)")
    save_path: Optional[str] = Field(None, description="Save path for screenshot")

    @validator("format")
    def validate_format(cls, v):
        if v not in ["png", "jpg", "jpeg", "bmp"]:
            raise ValueError("Format must be png, jpg, jpeg, or bmp")
        return v


# Logic Node Schemas
class IfConditionConfig(NodeConfigSchema):
    """If condition configuration"""

    variable_name: str = Field(..., description="Variable to check")
    operator: ConditionOperator = Field(..., description="Comparison operator")
    value: Union[str, int, float, bool] = Field(
        ..., description="Value to compare against"
    )
    case_sensitive: bool = Field(True, description="Case sensitive comparison")


class DelayConfig(NodeConfigSchema):
    """Delay configuration"""

    duration: int = Field(..., description="Delay duration in milliseconds")
    variable_duration: Optional[str] = Field(
        None, description="Variable name for dynamic duration"
    )

    @validator("duration")
    def validate_duration(cls, v):
        if v < 0:
            raise ValueError("Duration must be non-negative")
        return v


# Result Node Schemas
class OcrRegionConfig(NodeConfigSchema):
    """OCR region configuration"""

    x: int = Field(..., description="X coordinate of region")
    y: int = Field(..., description="Y coordinate of region")
    width: int = Field(..., description="Width of region")
    height: int = Field(..., description="Height of region")
    language: str = Field("eng", description="OCR language")
    confidence_threshold: float = Field(0.5, description="Minimum confidence threshold")
    output_variable: str = Field(..., description="Variable to store OCR result")

    @validator("confidence_threshold")
    def validate_confidence(cls, v):
        if not 0 <= v <= 1:
            raise ValueError("Confidence threshold must be between 0 and 1")
        return v


class LoggerConfig(NodeConfigSchema):
    """Logger configuration"""

    message: str = Field(..., description="Log message")
    level: LogLevel = Field(LogLevel.INFO, description="Log level")
    include_timestamp: bool = Field(True, description="Include timestamp in log")
    include_variables: bool = Field(False, description="Include current variables")
    output_to_console: bool = Field(True, description="Output to console")
    output_to_file: bool = Field(False, description="Output to file")
    log_file_path: Optional[str] = Field(None, description="Log file path")


# Webhook Node Schemas
class N8nWebhookConfig(NodeConfigSchema):
    """N8N webhook configuration"""

    webhook_url: str = Field(..., description="N8N webhook URL")
    method: HttpMethod = Field(HttpMethod.POST, description="HTTP method")
    headers: Optional[Dict[str, str]] = Field(None, description="Request headers")
    body_template: Optional[Dict[str, Any]] = Field(
        None, description="Request body template"
    )
    timeout: int = Field(30, description="Request timeout in seconds")
    retry_attempts: int = Field(3, description="Number of retry attempts")
    retry_delay: int = Field(1000, description="Delay between retries in ms")


# Configuration validation mapping
NODE_CONFIG_SCHEMAS = {
    "manual_trigger": ManualTriggerConfig,
    "webhook_trigger": WebhookTriggerConfig,
    "websocket_config": WebsocketConfigSchema,
    "live_desktop": LiveDesktopConfig,
    "click_action": ClickActionConfig,
    "type_text_action": TypeTextActionConfig,
    "http_request": HttpRequestConfig,
    "screenshot_action": ScreenshotActionConfig,
    "if_condition": IfConditionConfig,
    "delay": DelayConfig,
    "ocr_region": OcrRegionConfig,
    "logger": LoggerConfig,
    "n8n_webhook": N8nWebhookConfig,
}


def get_node_config_schema(node_type: str) -> Optional[type]:
    """Get configuration schema for node type"""
    return NODE_CONFIG_SCHEMAS.get(node_type)


def validate_node_config(node_type: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Validate node configuration against schema"""
    schema_class = get_node_config_schema(node_type)
    if not schema_class:
        raise ValueError(f"Unknown node type: {node_type}")

    # Validate and return parsed config
    validated_config = schema_class(**config)
    return validated_config.dict()


# Additional Node System Schemas
class NodeType(str, Enum):
    """Node type enumeration"""

    INPUT = "input"
    OUTPUT = "output"
    PROCESS = "process"
    CONDITION = "condition"
    VARIABLE = "variable"
    TRIGGER = "trigger"
    ACTION = "action"
    LOGIC = "logic"
    RESULT = "result"
    CONFIG = "config"
    INTERFACE = "interface"
    WEBHOOK = "webhook"
    CUSTOM = "custom"


class NodeStatus(str, Enum):
    """Node execution status"""

    IDLE = "idle"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class ConnectionType(str, Enum):
    """Connection type enumeration"""

    DATA = "data"
    CONTROL = "control"
    EVENT = "event"


class DataType(str, Enum):
    """Data type enumeration"""

    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    OBJECT = "object"
    ARRAY = "array"
    ANY = "any"
    FILE = "file"
    IMAGE = "image"
    JSON = "json"


class NodePosition(BaseModel):
    """Node position in the graph"""

    x: float = Field(..., description="X coordinate")
    y: float = Field(..., description="Y coordinate")


class NodeSize(BaseModel):
    """Node size"""

    width: float = Field(200, description="Node width")
    height: float = Field(100, description="Node height")


class NodePort(BaseModel):
    """Node input/output port"""

    id: str = Field(..., description="Port ID")
    name: str = Field(..., description="Port display name")
    data_type: DataType = Field(..., description="Port data type")
    required: bool = Field(False, description="Whether port is required")
    default_value: Optional[Any] = Field(None, description="Default value")
    description: Optional[str] = Field(None, description="Port description")


class NodeMetadata(BaseModel):
    """Node metadata"""

    icon: Optional[str] = Field(None, description="Node icon")
    color: Optional[str] = Field(None, description="Node color")
    tags: List[str] = Field(default_factory=list, description="Node tags")
    documentation_url: Optional[str] = Field(None, description="Documentation URL")
    version: str = Field("1.0.0", description="Node version")


class NodeData(BaseModel):
    """Node data"""

    label: str = Field(..., description="Node label")
    node_type: str = Field(..., description="Node type")
    config: Dict[str, Any] = Field(
        default_factory=dict, description="Node configuration"
    )
    inputs: Dict[str, Any] = Field(default_factory=dict, description="Input values")
    outputs: Dict[str, Any] = Field(default_factory=dict, description="Output values")
    variables: Dict[str, Any] = Field(
        default_factory=dict, description="Node variables"
    )


class NodeConfiguration(BaseModel):
    """Node configuration"""

    enabled: bool = Field(True, description="Whether node is enabled")
    breakpoint: bool = Field(False, description="Whether to pause at this node")
    timeout: Optional[int] = Field(None, description="Execution timeout in seconds")
    retry_count: int = Field(0, description="Number of retries on failure")
    retry_delay: int = Field(1000, description="Delay between retries in ms")
    log_level: LogLevel = Field(LogLevel.INFO, description="Log level for this node")


class Node(BaseModel):
    """Node in the workflow graph"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Node ID")
    type: str = Field(..., description="Node type")
    position: NodePosition = Field(..., description="Node position")
    size: Optional[NodeSize] = Field(None, description="Node size")
    data: NodeData = Field(..., description="Node data")
    config: NodeConfiguration = Field(
        default_factory=NodeConfiguration, description="Node configuration"
    )
    status: NodeStatus = Field(NodeStatus.IDLE, description="Node status")
    created_at: datetime = Field(
        default_factory=datetime.now, description="Creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=datetime.now, description="Last update timestamp"
    )


class NodeConnection(BaseModel):
    """Connection between nodes"""

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), description="Connection ID"
    )
    source_node_id: str = Field(..., description="Source node ID")
    source_port: str = Field(..., description="Source port ID")
    target_node_id: str = Field(..., description="Target node ID")
    target_port: str = Field(..., description="Target port ID")
    connection_type: ConnectionType = Field(
        ConnectionType.DATA, description="Connection type"
    )
    data: Optional[Dict[str, Any]] = Field(None, description="Connection data")
    created_at: datetime = Field(
        default_factory=datetime.now, description="Creation timestamp"
    )


class NodeGraph(BaseModel):
    """Node graph/workflow"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Graph ID")
    name: str = Field(..., description="Graph name")
    description: Optional[str] = Field(None, description="Graph description")
    nodes: List[Node] = Field(default_factory=list, description="Graph nodes")
    connections: List[NodeConnection] = Field(
        default_factory=list, description="Node connections"
    )
    variables: Dict[str, Any] = Field(
        default_factory=dict, description="Graph variables"
    )
    viewport: Optional[Dict[str, float]] = Field(None, description="Viewport settings")
    grid_size: int = Field(20, description="Grid size")
    snap_to_grid: bool = Field(True, description="Snap to grid")
    created_at: datetime = Field(
        default_factory=datetime.now, description="Creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=datetime.now, description="Last update timestamp"
    )


class NodeTemplate(BaseModel):
    """Node template"""

    id: str = Field(..., description="Template ID")
    name: str = Field(..., description="Template name")
    node_type: NodeType = Field(..., description="Node type")
    category: str = Field(..., description="Template category")
    description: str = Field(..., description="Template description")
    input_ports: List[NodePort] = Field(default_factory=list, description="Input ports")
    output_ports: List[NodePort] = Field(
        default_factory=list, description="Output ports"
    )
    default_config: Dict[str, Any] = Field(
        default_factory=dict, description="Default configuration"
    )
    metadata: NodeMetadata = Field(
        default_factory=NodeMetadata, description="Template metadata"
    )


class NodeLibrary(BaseModel):
    """Node library"""

    id: str = Field(..., description="Library ID")
    name: str = Field(..., description="Library name")
    description: str = Field(..., description="Library description")
    version: str = Field(..., description="Library version")
    templates: List[NodeTemplate] = Field(
        default_factory=list, description="Node templates"
    )
    categories: List[str] = Field(
        default_factory=list, description="Available categories"
    )


# Request/Response Schemas
class NodeExecutionRequest(BaseModel):
    """Node execution request"""

    node_id: str = Field(..., description="Node ID to execute")
    inputs: Dict[str, Any] = Field(default_factory=dict, description="Input values")
    variables: Dict[str, Any] = Field(
        default_factory=dict, description="Workflow variables"
    )
    debug_mode: bool = Field(False, description="Enable debug mode")


class NodeExecutionResult(BaseModel):
    """Node execution result"""

    node_id: str = Field(..., description="Node ID")
    status: NodeStatus = Field(..., description="Execution status")
    outputs: Dict[str, Any] = Field(default_factory=dict, description="Output values")
    variables: Dict[str, Any] = Field(
        default_factory=dict, description="Updated variables"
    )
    logs: List[str] = Field(default_factory=list, description="Execution logs")
    error: Optional[str] = Field(None, description="Error message if failed")
    execution_time: float = Field(..., description="Execution time in seconds")
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Execution timestamp"
    )


class GraphExecutionResult(BaseModel):
    """Graph execution result"""

    graph_id: str = Field(..., description="Graph ID")
    execution_id: str = Field(..., description="Execution ID")
    status: NodeStatus = Field(..., description="Overall execution status")
    node_results: List[NodeExecutionResult] = Field(
        default_factory=list, description="Node results"
    )
    variables: Dict[str, Any] = Field(
        default_factory=dict, description="Final variables"
    )
    start_time: datetime = Field(..., description="Execution start time")
    end_time: Optional[datetime] = Field(None, description="Execution end time")
    total_time: Optional[float] = Field(None, description="Total execution time")


class NodeSearchRequest(BaseModel):
    """Node search request"""

    query: str = Field(..., description="Search query")
    category: Optional[str] = Field(None, description="Filter by category")
    node_type: Optional[NodeType] = Field(None, description="Filter by node type")
    library_id: Optional[str] = Field(None, description="Filter by library")


class NodeUpdateRequest(BaseModel):
    """Node update request"""

    position: Optional[NodePosition] = Field(None, description="New position")
    size: Optional[NodeSize] = Field(None, description="New size")
    data: Optional[NodeData] = Field(None, description="New data")
    config: Optional[NodeConfiguration] = Field(None, description="New configuration")


class ConnectionCreateRequest(BaseModel):
    """Connection create request"""

    source_node_id: str = Field(..., description="Source node ID")
    source_port: str = Field(..., description="Source port ID")
    target_node_id: str = Field(..., description="Target node ID")
    target_port: str = Field(..., description="Target port ID")
    connection_type: ConnectionType = Field(
        ConnectionType.DATA, description="Connection type"
    )


class GraphCreateRequest(BaseModel):
    """Graph create request"""

    name: str = Field(..., description="Graph name")
    description: Optional[str] = Field(None, description="Graph description")
    template_id: Optional[str] = Field(None, description="Template to use")


class GraphUpdateRequest(BaseModel):
    """Graph update request"""

    name: Optional[str] = Field(None, description="New name")
    description: Optional[str] = Field(None, description="New description")
    viewport: Optional[Dict[str, float]] = Field(None, description="New viewport")
    grid_size: Optional[int] = Field(None, description="New grid size")
    snap_to_grid: Optional[bool] = Field(None, description="New snap to grid setting")


class NodeValidationError(BaseModel):
    """Node validation error"""

    node_id: str = Field(..., description="Node ID with error")
    field: str = Field(..., description="Field with error")
    message: str = Field(..., description="Error message")
    severity: str = Field(..., description="Error severity (error, warning, info)")


class GraphValidationResult(BaseModel):
    """Graph validation result"""

    is_valid: bool = Field(..., description="Whether graph is valid")
    errors: List[NodeValidationError] = Field(
        default_factory=list, description="Validation errors"
    )
    warnings: List[NodeValidationError] = Field(
        default_factory=list, description="Validation warnings"
    )


class NodeStatistics(BaseModel):
    """Node execution statistics"""

    node_id: str = Field(..., description="Node ID")
    execution_count: int = Field(0, description="Number of executions")
    success_count: int = Field(0, description="Number of successful executions")
    error_count: int = Field(0, description="Number of failed executions")
    average_execution_time: float = Field(0.0, description="Average execution time")
    last_execution: Optional[datetime] = Field(None, description="Last execution time")
