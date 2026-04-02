"""Node Configurations Router for TRAE Backend

Provides CRUD endpoints for node configurations and JSON templates
for each node type from simplifiedNodeTemplates.
"""

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..logger_config import get_logger, log_api_request

logger = get_logger("node_configs")

router = APIRouter()

# Pydantic Models for Node Configurations


class NodeConfigBase(BaseModel):
    """Base model for node configuration"""

    id: Optional[str] = None
    node_type: str
    name: Optional[str] = None
    description: Optional[str] = None
    config: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class NodeConfigCreate(NodeConfigBase):
    """Model for creating node configuration"""

    pass


class NodeConfigUpdate(BaseModel):
    """Model for updating node configuration"""

    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class NodeConfigResponse(BaseModel):
    """Response model for node configuration operations"""

    success: bool
    config: Optional[NodeConfigBase] = None
    configs: Optional[List[NodeConfigBase]] = None
    template: Optional[Dict[str, Any]] = None
    message: Optional[str] = None
    error: Optional[str] = None


# In-memory storage for node configurations (demo purposes)
node_configs_storage: Dict[str, Dict[str, NodeConfigBase]] = {}

# JSON Templates based on simplifiedNodeTemplates.ts
NODE_TEMPLATES = {
    "manual_trigger": {
        "type": "manual_trigger",
        "category": "Input",
        "configSchema": {
            "type": "object",
            "properties": {
                "triggerName": {
                    "type": "string",
                    "title": "Trigger Name",
                    "default": "Manual Start",
                },
                "description": {
                    "type": "string",
                    "title": "Description",
                    "default": "Manually triggered workflow start",
                },
            },
            "required": ["triggerName"],
        },
        "defaultConfig": {
            "triggerName": "Manual Start",
            "description": "Manually triggered workflow start",
        },
        "inputs": [],
        "outputs": ["trigger"],
    },
    "webhook_trigger": {
        "type": "webhook_trigger",
        "category": "Input",
        "configSchema": {
            "type": "object",
            "properties": {
                "webhookUrl": {
                    "type": "string",
                    "title": "Webhook URL",
                    "default": "/webhook/trigger",
                },
                "method": {
                    "type": "string",
                    "title": "HTTP Method",
                    "enum": ["GET", "POST", "PUT", "DELETE"],
                    "default": "POST",
                },
                "authentication": {
                    "type": "boolean",
                    "title": "Require Authentication",
                    "default": False,
                },
            },
            "required": ["webhookUrl", "method"],
        },
        "defaultConfig": {
            "webhookUrl": "/webhook/trigger",
            "method": "POST",
            "authentication": False,
        },
        "inputs": [],
        "outputs": ["webhook_data"],
    },
    "websocket_config": {
        "type": "websocket_config",
        "category": "Integration",
        "configSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "title": "WebSocket URL",
                    "default": "ws://localhost:8080/ws",
                },
                "autoReconnect": {
                    "type": "boolean",
                    "title": "Auto Reconnect",
                    "default": True,
                },
                "reconnectInterval": {
                    "type": "number",
                    "title": "Reconnect Interval (ms)",
                    "default": 5000,
                },
            },
            "required": ["url"],
        },
        "defaultConfig": {
            "url": "ws://localhost:8080/ws",
            "autoReconnect": True,
            "reconnectInterval": 5000,
        },
        "inputs": ["message"],
        "outputs": ["response"],
    },
    "click_action": {
        "type": "click_action",
        "category": "Automation",
        "configSchema": {
            "type": "object",
            "properties": {
                "x": {"type": "number", "title": "X Coordinate", "default": 0},
                "y": {"type": "number", "title": "Y Coordinate", "default": 0},
                "button": {
                    "type": "string",
                    "title": "Mouse Button",
                    "enum": ["left", "right", "middle"],
                    "default": "left",
                },
                "outputToFilesystem": {
                    "type": "boolean",
                    "title": "Output to Filesystem",
                    "default": False,
                },
                "commandFileName": {
                    "type": "string",
                    "title": "Command File Name",
                    "default": "click_command.json",
                },
                "waitTime": {
                    "type": "number",
                    "title": "Wait Time (ms)",
                    "default": 100,
                },
            },
            "required": ["x", "y"],
        },
        "defaultConfig": {
            "x": 0,
            "y": 0,
            "button": "left",
            "outputToFilesystem": False,
            "commandFileName": "click_command.json",
            "waitTime": 100,
        },
        "inputs": ["trigger"],
        "outputs": ["result"],
    },
    "type_text_action": {
        "type": "type_text_action",
        "category": "Automation",
        "configSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "title": "Text to Type", "default": ""},
                "delay": {
                    "type": "number",
                    "title": "Delay between characters (ms)",
                    "default": 50,
                },
                "outputToFilesystem": {
                    "type": "boolean",
                    "title": "Output to Filesystem",
                    "default": False,
                },
                "commandFileName": {
                    "type": "string",
                    "title": "Command File Name",
                    "default": "type_command.json",
                },
            },
            "required": ["text"],
        },
        "defaultConfig": {
            "text": "",
            "delay": 50,
            "outputToFilesystem": False,
            "commandFileName": "type_command.json",
        },
        "inputs": ["trigger"],
        "outputs": ["result"],
    },
    "http_request_action": {
        "type": "http_request_action",
        "category": "Integration",
        "configSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "title": "URL",
                    "default": "https://api.example.com",
                },
                "method": {
                    "type": "string",
                    "title": "HTTP Method",
                    "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"],
                    "default": "GET",
                },
                "headers": {
                    "type": "object",
                    "title": "Headers",
                    "default": {"Content-Type": "application/json"},
                },
                "body": {"type": "string", "title": "Request Body", "default": ""},
                "timeout": {
                    "type": "number",
                    "title": "Timeout (seconds)",
                    "default": 30,
                },
            },
            "required": ["url", "method"],
        },
        "defaultConfig": {
            "url": "https://api.example.com",
            "method": "GET",
            "headers": {"Content-Type": "application/json"},
            "body": "",
            "timeout": 30,
        },
        "inputs": ["trigger"],
        "outputs": ["response", "error"],
    },
    "if_condition": {
        "type": "if_condition",
        "category": "Logic",
        "configSchema": {
            "type": "object",
            "properties": {
                "condition": {
                    "type": "string",
                    "title": "Condition",
                    "default": "value > 0",
                },
                "operator": {
                    "type": "string",
                    "title": "Operator",
                    "enum": [
                        "equals",
                        "not_equals",
                        "greater_than",
                        "less_than",
                        "contains",
                        "regex",
                    ],
                    "default": "equals",
                },
                "compareValue": {
                    "type": "string",
                    "title": "Compare Value",
                    "default": "",
                },
            },
            "required": ["condition", "operator"],
        },
        "defaultConfig": {
            "condition": "value > 0",
            "operator": "equals",
            "compareValue": "",
        },
        "inputs": ["input"],
        "outputs": ["true", "false"],
    },
    "delay": {
        "type": "delay",
        "category": "Logic",
        "configSchema": {
            "type": "object",
            "properties": {
                "duration": {
                    "type": "number",
                    "title": "Delay Duration (ms)",
                    "default": 1000,
                },
                "unit": {
                    "type": "string",
                    "title": "Time Unit",
                    "enum": ["milliseconds", "seconds", "minutes"],
                    "default": "milliseconds",
                },
            },
            "required": ["duration"],
        },
        "defaultConfig": {"duration": 1000, "unit": "milliseconds"},
        "inputs": ["trigger"],
        "outputs": ["delayed"],
    },
    "n8n_webhook": {
        "type": "n8n_webhook",
        "category": "Integration",
        "configSchema": {
            "type": "object",
            "properties": {
                "webhookUrl": {
                    "type": "string",
                    "title": "N8N Webhook URL",
                    "default": "https://your-n8n-instance.com/webhook/...",
                },
                "method": {
                    "type": "string",
                    "title": "HTTP Method",
                    "enum": ["GET", "POST", "PUT", "DELETE"],
                    "default": "POST",
                },
                "headers": {
                    "type": "object",
                    "title": "Headers",
                    "default": {"Content-Type": "application/json"},
                },
                "authentication": {
                    "type": "object",
                    "title": "Authentication",
                    "default": {},
                },
            },
            "required": ["webhookUrl"],
        },
        "defaultConfig": {
            "webhookUrl": "https://your-n8n-instance.com/webhook/...",
            "method": "POST",
            "headers": {"Content-Type": "application/json"},
            "authentication": {},
        },
        "inputs": ["data"],
        "outputs": ["response"],
    },
    "send_to_filesystem": {
        "type": "send_to_filesystem",
        "category": "Integration",
        "configSchema": {
            "type": "object",
            "properties": {
                "filePath": {
                    "type": "string",
                    "title": "File Path",
                    "default": "./output/data.json",
                },
                "format": {
                    "type": "string",
                    "title": "File Format",
                    "enum": ["json", "txt", "csv", "xml"],
                    "default": "json",
                },
                "append": {
                    "type": "boolean",
                    "title": "Append to File",
                    "default": False,
                },
                "createDirectory": {
                    "type": "boolean",
                    "title": "Create Directory if not exists",
                    "default": True,
                },
            },
            "required": ["filePath"],
        },
        "defaultConfig": {
            "filePath": "./output/data.json",
            "format": "json",
            "append": False,
            "createDirectory": True,
        },
        "inputs": ["data"],
        "outputs": ["result"],
    },
    "workflow_result": {
        "type": "workflow_result",
        "category": "Workflow",
        "configSchema": {
            "type": "object",
            "properties": {
                "resultName": {
                    "type": "string",
                    "title": "Result Name",
                    "default": "workflow_output",
                },
                "format": {
                    "type": "string",
                    "title": "Output Format",
                    "enum": ["json", "string", "number", "boolean"],
                    "default": "json",
                },
                "saveToFile": {
                    "type": "boolean",
                    "title": "Save to File",
                    "default": False,
                },
                "filePath": {
                    "type": "string",
                    "title": "File Path (if saving)",
                    "default": "./results/workflow_result.json",
                },
            },
            "required": ["resultName"],
        },
        "defaultConfig": {
            "resultName": "workflow_output",
            "format": "json",
            "saveToFile": False,
            "filePath": "./results/workflow_result.json",
        },
        "inputs": ["data"],
        "outputs": [],
    },
}


# Helper functions
def get_node_storage(node_type: str) -> Dict[str, NodeConfigBase]:
    """Get storage for specific node type"""
    if node_type not in node_configs_storage:
        node_configs_storage[node_type] = {}
    return node_configs_storage[node_type]


def validate_node_type(node_type: str) -> bool:
    """Validate if node type exists in templates"""
    return node_type in NODE_TEMPLATES


# Generic CRUD Routes for all Node Types


@router.get("/templates")
@log_api_request(logger)
async def get_all_node_templates(request: Request):
    """Get all available node templates"""
    try:
        logger.info("API Request: get_all_node_templates")

        return JSONResponse(
            content={
                "success": True,
                "templates": NODE_TEMPLATES,
                "node_types": list(NODE_TEMPLATES.keys()),
                "total_count": len(NODE_TEMPLATES),
            }
        )

    except Exception as e:
        logger.error(f"Get all node templates error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/templates/{node_type}")
@log_api_request(logger)
async def get_node_template(node_type: str, request: Request):
    """Get JSON template for specific node type"""
    try:
        logger.info(f"API Request: get_node_template - {node_type}")

        if not validate_node_type(node_type):
            raise HTTPException(
                status_code=404, detail=f"Node type '{node_type}' not found"
            )

        template = NODE_TEMPLATES[node_type]

        return NodeConfigResponse(
            success=True,
            template=template,
            message=f"Template for '{node_type}' retrieved successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get node template error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/configs/{node_type}")
@log_api_request(logger)
async def get_node_configs(node_type: str, request: Request):
    """Get all configurations for specific node type"""
    try:
        logger.info(f"API Request: get_node_configs - {node_type}")

        if not validate_node_type(node_type):
            raise HTTPException(
                status_code=404, detail=f"Node type '{node_type}' not found"
            )

        storage = get_node_storage(node_type)
        configs = list(storage.values())

        return NodeConfigResponse(
            success=True,
            configs=configs,
            message=f"Found {len(configs)} configurations for '{node_type}'",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get node configs error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/configs/{node_type}")
@log_api_request(logger)
async def create_node_config(
    node_type: str, config_data: NodeConfigCreate, request: Request
):
    """Create new configuration for specific node type"""
    try:
        logger.info(f"API Request: create_node_config - {node_type}")

        if not validate_node_type(node_type):
            raise HTTPException(
                status_code=404, detail=f"Node type '{node_type}' not found"
            )

        # Generate ID if not provided
        if not config_data.id:
            config_data.id = str(uuid.uuid4())

        # Set node_type
        config_data.node_type = node_type

        # Merge with default config if config is empty
        if not config_data.config:
            config_data.config = NODE_TEMPLATES[node_type]["defaultConfig"].copy()

        # Store configuration
        storage = get_node_storage(node_type)
        storage[config_data.id] = config_data

        return NodeConfigResponse(
            success=True,
            config=config_data,
            message=f"Configuration for '{node_type}' created successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create node config error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/configs/{node_type}/{config_id}")
@log_api_request(logger)
async def get_node_config(node_type: str, config_id: str, request: Request):
    """Get specific configuration by ID"""
    try:
        logger.info(f"API Request: get_node_config - {node_type}/{config_id}")

        if not validate_node_type(node_type):
            raise HTTPException(
                status_code=404, detail=f"Node type '{node_type}' not found"
            )

        storage = get_node_storage(node_type)

        if config_id not in storage:
            raise HTTPException(
                status_code=404, detail=f"Configuration '{config_id}' not found"
            )

        config = storage[config_id]

        return NodeConfigResponse(
            success=True,
            config=config,
            message=f"Configuration '{config_id}' retrieved successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get node config error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/configs/{node_type}/{config_id}")
@log_api_request(logger)
async def update_node_config(
    node_type: str, config_id: str, update_data: NodeConfigUpdate, request: Request
):
    """Update existing configuration"""
    try:
        logger.info(f"API Request: update_node_config - {node_type}/{config_id}")

        if not validate_node_type(node_type):
            raise HTTPException(
                status_code=404, detail=f"Node type '{node_type}' not found"
            )

        storage = get_node_storage(node_type)

        if config_id not in storage:
            raise HTTPException(
                status_code=404, detail=f"Configuration '{config_id}' not found"
            )

        config = storage[config_id]

        # Update fields if provided
        if update_data.name is not None:
            config.name = update_data.name
        if update_data.description is not None:
            config.description = update_data.description
        if update_data.config is not None:
            config.config.update(update_data.config)
        if update_data.metadata is not None:
            config.metadata.update(update_data.metadata)

        storage[config_id] = config

        return NodeConfigResponse(
            success=True,
            config=config,
            message=f"Configuration '{config_id}' updated successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update node config error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/configs/{node_type}/{config_id}")
@log_api_request(logger)
async def delete_node_config(node_type: str, config_id: str, request: Request):
    """Delete configuration"""
    try:
        logger.info(f"API Request: delete_node_config - {node_type}/{config_id}")

        if not validate_node_type(node_type):
            raise HTTPException(
                status_code=404, detail=f"Node type '{node_type}' not found"
            )

        storage = get_node_storage(node_type)

        if config_id not in storage:
            raise HTTPException(
                status_code=404, detail=f"Configuration '{config_id}' not found"
            )

        del storage[config_id]

        return NodeConfigResponse(
            success=True, message=f"Configuration '{config_id}' deleted successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete node config error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# Validation endpoint
@router.post("/validate/{node_type}")
@log_api_request(logger)
async def validate_node_config(
    node_type: str, config_data: Dict[str, Any], request: Request
):
    """Validate node configuration against schema"""
    try:
        logger.info(f"API Request: validate_node_config - {node_type}")

        if not validate_node_type(node_type):
            raise HTTPException(
                status_code=404, detail=f"Node type '{node_type}' not found"
            )

        template = NODE_TEMPLATES[node_type]
        schema = template["configSchema"]

        # Basic validation (in a real implementation, use jsonschema library)
        validation_result = {"valid": True, "errors": [], "warnings": []}

        # Check required fields
        required_fields = schema.get("required", [])
        for field in required_fields:
            if field not in config_data:
                validation_result["errors"].append(
                    f"Required field '{field}' is missing"
                )
                validation_result["valid"] = False

        return JSONResponse(
            content={"success": True, "validation": validation_result, "schema": schema}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Validate node config error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
