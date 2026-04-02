"""
Workflows Router for TRAE Backend

Handles workflow management endpoints including CRUD operations
for visual node-based workflow definitions.
"""

import asyncio
import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from ..logger_config import LoggerMixin, get_logger
from ..services import get_service_manager
from ..services.click_automation_service import ClickAutomationService
from ..services.desktop_automation_service import DesktopAutomationService
from ..services.graph_execution_service import GraphExecutionService
from ..services.node_service import get_node_service
from ..services.ocr_service import OCRService as EnhancedOCRService
from ..websocket.manager import WebSocketManager

logger = get_logger("workflows")

router = APIRouter()

# Pydantic Models


class WorkflowNode(BaseModel):
    """Workflow node definition"""

    id: str
    type: str
    position: Dict[str, float] = Field(default_factory=dict)
    data: Dict[str, Any] = Field(default_factory=dict)


class WorkflowEdge(BaseModel):
    """Workflow edge definition"""

    id: str
    source: str
    target: str
    source_handle: Optional[str] = None
    target_handle: Optional[str] = None


class WorkflowDefinition(BaseModel):
    """Complete workflow definition"""

    id: Optional[str] = None
    name: str = "Untitled Workflow"
    description: Optional[str] = None
    nodes: List[WorkflowNode] = Field(default_factory=list)
    edges: List[WorkflowEdge] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class WorkflowResponse(BaseModel):
    """Workflow response model"""

    success: bool
    workflow: Optional[WorkflowDefinition] = None
    workflows: Optional[List[WorkflowDefinition]] = None
    message: Optional[str] = None


class ExecutionRequest(BaseModel):
    """Workflow execution request"""

    execution_mode: str = "sequential"  # sequential, parallel, debug
    debug_mode: bool = False
    step_by_step: bool = False
    variables: Dict[str, Any] = Field(default_factory=dict)


class ExecutionStatus(BaseModel):
    """Workflow execution status"""

    execution_id: str
    workflow_id: str
    status: str  # pending, running, paused, completed, failed
    current_node: Optional[str] = None
    progress: float = 0.0
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    error: Optional[str] = None
    variables: Dict[str, Any] = Field(default_factory=dict)
    execution_log: List[Dict[str, Any]] = Field(default_factory=list)


class NodeExecutionResult(BaseModel):
    """Individual node execution result"""

    node_id: str
    node_type: str
    status: str  # pending, running, completed, failed, skipped
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    input_data: Dict[str, Any] = Field(default_factory=dict)
    output_data: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    execution_time_ms: Optional[int] = None


# In-memory storage for demo purposes
workflows_storage: Dict[str, WorkflowDefinition] = {}
execution_storage: Dict[str, ExecutionStatus] = {}
node_results_storage: Dict[str, List[NodeExecutionResult]] = {}


# Dependency injection helper
async def _get_graph_execution_service_with_deps() -> GraphExecutionService:
    """Create GraphExecutionService with all required dependencies"""
    try:
        # Create service instances
        node_service = get_node_service()
        websocket_manager = WebSocketManager()
        click_service = ClickAutomationService()
        desktop_service = DesktopAutomationService()
        ocr_service = EnhancedOCRService()

        # Initialize node service if not already done
        await node_service.initialize()

        # Create and return graph execution service
        return GraphExecutionService(
            node_service=node_service,
            websocket_manager=websocket_manager,
            click_service=click_service,
            desktop_service=desktop_service,
            ocr_service=ocr_service,
        )
    except Exception as e:
        logger.error(f"Failed to create GraphExecutionService: {e}")
        raise


@router.get("/status")
async def get_workflows_status():
    """Get workflow service status"""
    try:
        logger.info("API Request: get_workflows_status")

        # Get service manager to check if graph execution service is available
        service_manager = get_service_manager()
        graph_service_healthy = False

        try:
            # Try to create graph execution service with dependencies
            graph_service = await _get_graph_execution_service_with_deps()
            graph_service_healthy = graph_service is not None
        except Exception as e:
            logger.warning(f"Graph execution service not available: {e}")
            graph_service_healthy = False

        workflow_count = len(workflows_storage)

        status = {
            "success": True,
            "service_healthy": True,
            "workflow_count": workflow_count,
            "graph_execution_available": graph_service_healthy,
            "features": [
                "workflow_creation",
                "workflow_editing",
                "workflow_execution",
                "workflow_management",
            ],
            "storage": "in_memory",
            "message": f"Workflow service operational with {workflow_count} workflows",
        }

        logger.info(f"API Response: get_workflows_status completed")

        return status

    except Exception as e:
        logger.error(f"Get workflows status error: {e}", exc_info=True)
        return {
            "success": False,
            "service_healthy": False,
            "error": str(e),
            "message": "Workflow service status check failed",
        }


@router.get("/list", response_model=WorkflowResponse)
async def list_workflows():
    """List all workflows (alias for GET /)"""
    return await get_workflows()


@router.get("/", response_model=WorkflowResponse)
async def get_workflows():
    """Get all workflows"""
    try:
        logger.info("API Request: get_workflows")

        workflows_list = list(workflows_storage.values())

        logger.info(
            f"API Response: get_workflows completed, found {len(workflows_list)} workflows"
        )

        return WorkflowResponse(
            success=True,
            workflows=workflows_list,
            message=f"Found {len(workflows_list)} workflows",
        )

    except Exception as e:
        logger.error(f"Get workflows error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", response_model=WorkflowResponse)
async def create_workflow(workflow: WorkflowDefinition):
    """Create a new workflow"""
    try:
        logger.info(f"API Request: create_workflow - {workflow.name}")

        # Generate ID if not provided
        if not workflow.id:
            import uuid

            workflow.id = str(uuid.uuid4())

        # Store workflow
        workflows_storage[workflow.id] = workflow

        logger.info(f"API Response: create_workflow completed - {workflow.id}")

        return WorkflowResponse(
            success=True,
            workflow=workflow,
            message=f"Workflow '{workflow.name}' created successfully",
        )

    except Exception as e:
        logger.error(f"Create workflow error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(workflow_id: str):
    """Get a specific workflow by ID"""
    try:
        logger.info(f"API Request: get_workflow - {workflow_id}")

        if workflow_id not in workflows_storage:
            raise HTTPException(
                status_code=404, detail=f"Workflow {workflow_id} not found"
            )

        workflow = workflows_storage[workflow_id]

        logger.info(f"API Response: get_workflow completed - {workflow_id}")

        return WorkflowResponse(
            success=True,
            workflow=workflow,
            message=f"Workflow '{workflow.name}' retrieved successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get workflow error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(workflow_id: str, workflow: WorkflowDefinition):
    """Update an existing workflow"""
    try:
        logger.info(f"API Request: update_workflow - {workflow_id}")

        if workflow_id not in workflows_storage:
            raise HTTPException(
                status_code=404, detail=f"Workflow {workflow_id} not found"
            )

        # Ensure ID matches
        workflow.id = workflow_id
        workflows_storage[workflow_id] = workflow

        logger.info(f"API Response: update_workflow completed - {workflow_id}")

        return WorkflowResponse(
            success=True,
            workflow=workflow,
            message=f"Workflow '{workflow.name}' updated successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update workflow error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{workflow_id}", response_model=WorkflowResponse)
async def delete_workflow(workflow_id: str):
    """Delete a workflow"""
    try:
        logger.info(f"API Request: delete_workflow - {workflow_id}")

        if workflow_id not in workflows_storage:
            raise HTTPException(
                status_code=404, detail=f"Workflow {workflow_id} not found"
            )

        deleted_workflow = workflows_storage.pop(workflow_id)

        logger.info(f"API Response: delete_workflow completed - {workflow_id}")

        return WorkflowResponse(
            success=True,
            message=f"Workflow '{deleted_workflow.name}' deleted successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete workflow error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workflow_id}/execute")
async def execute_workflow(workflow_id: str):
    """Execute a workflow"""
    try:
        logger.info(f"API Request: execute_workflow - {workflow_id}")

        if workflow_id not in workflows_storage:
            raise HTTPException(
                status_code=404, detail=f"Workflow {workflow_id} not found"
            )

        workflow = workflows_storage[workflow_id]

        # Get graph execution service with dependencies
        try:
            graph_service = _get_graph_execution_service_with_deps()
        except Exception as e:
            logger.error(f"Failed to create graph execution service: {e}")
            raise HTTPException(
                status_code=503, detail="Graph execution service not available"
            )

        # Convert workflow to execution format
        import uuid

        execution_id = str(uuid.uuid4())

        # Execute the workflow
        result = await graph_service.execute_graph(workflow=workflow, debug_mode=False)

        logger.info(f"API Response: execute_workflow completed - {workflow_id}")

        return {
            "success": True,
            "execution_id": execution_id,
            "workflow_id": workflow_id,
            "result": result,
            "message": f"Workflow '{workflow.name}' execution started",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Execute workflow error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workflow_id}/execute/advanced")
async def execute_workflow_advanced(
    workflow_id: str,
    execution_request: ExecutionRequest,
    background_tasks: BackgroundTasks,
):
    """Execute a workflow with advanced options (debug mode, step-by-step, etc.)"""
    try:
        logger.info(f"API Request: execute_workflow_advanced - {workflow_id}")

        if workflow_id not in workflows_storage:
            raise HTTPException(
                status_code=404, detail=f"Workflow {workflow_id} not found"
            )

        workflow = workflows_storage[workflow_id]

        # Get graph execution service with dependencies
        try:
            graph_service = _get_graph_execution_service_with_deps()
        except Exception as e:
            logger.error(f"Failed to create graph execution service: {e}")
            raise HTTPException(
                status_code=503, detail="Graph execution service not available"
            )

        # Generate execution ID
        execution_id = str(uuid.uuid4())

        # Create execution status
        from datetime import datetime

        execution_status = ExecutionStatus(
            execution_id=execution_id,
            workflow_id=workflow_id,
            status="pending",
            start_time=datetime.now().isoformat(),
            variables=execution_request.variables,
        )

        # Store execution status
        execution_storage[execution_id] = execution_status
        node_results_storage[execution_id] = []

        # Execute workflow in background if not in debug mode
        if execution_request.debug_mode or execution_request.step_by_step:
            # For debug mode, return immediately and let frontend control execution
            execution_status.status = "paused"
            execution_storage[execution_id] = execution_status
        else:
            # Execute in background
            background_tasks.add_task(
                _execute_workflow_background,
                execution_id,
                workflow,
                execution_request.debug_mode,
            )
            execution_status.status = "running"
            execution_storage[execution_id] = execution_status

        logger.info(
            f"API Response: execute_workflow_advanced completed - {workflow_id}"
        )

        return {
            "success": True,
            "execution_id": execution_id,
            "workflow_id": workflow_id,
            "status": execution_status.status,
            "debug_mode": execution_request.debug_mode,
            "step_by_step": execution_request.step_by_step,
            "message": f"Workflow '{workflow.name}' execution initialized",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Execute workflow advanced error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/executions/{execution_id}/status")
async def get_execution_status(execution_id: str):
    """Get execution status and progress"""
    try:
        logger.info(f"API Request: get_execution_status - {execution_id}")

        if execution_id not in execution_storage:
            raise HTTPException(
                status_code=404, detail=f"Execution {execution_id} not found"
            )

        execution_status = execution_storage[execution_id]
        node_results = node_results_storage.get(execution_id, [])

        logger.info(f"API Response: get_execution_status completed - {execution_id}")

        return {
            "success": True,
            "execution_status": execution_status.dict(),
            "node_results": [result.dict() for result in node_results],
            "message": "Execution status retrieved successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get execution status error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/executions/{execution_id}/control")
async def control_execution(execution_id: str, action: str):
    """Control execution (pause, resume, stop, step)"""
    try:
        logger.info(
            f"API Request: control_execution - {execution_id}, action: {action}"
        )

        if execution_id not in execution_storage:
            raise HTTPException(
                status_code=404, detail=f"Execution {execution_id} not found"
            )

        execution_status = execution_storage[execution_id]

        if action == "pause":
            if execution_status.status == "running":
                execution_status.status = "paused"
                execution_storage[execution_id] = execution_status
                message = "Execution paused"
            else:
                message = f"Cannot pause execution in status: {execution_status.status}"

        elif action == "resume":
            if execution_status.status == "paused":
                execution_status.status = "running"
                execution_storage[execution_id] = execution_status
                message = "Execution resumed"
            else:
                message = (
                    f"Cannot resume execution in status: {execution_status.status}"
                )

        elif action == "stop":
            if execution_status.status in ["running", "paused"]:
                execution_status.status = "failed"
                execution_status.error = "Execution stopped by user"
                from datetime import datetime

                execution_status.end_time = datetime.now().isoformat()
                execution_storage[execution_id] = execution_status
                message = "Execution stopped"
            else:
                message = f"Cannot stop execution in status: {execution_status.status}"

        elif action == "step":
            if execution_status.status == "paused":
                # Execute next node
                try:
                    graph_service = _get_graph_execution_service_with_deps()
                    # This would need to be implemented in the graph service
                    # For now, just simulate stepping
                    message = "Stepped to next node"
                except Exception as e:
                    logger.error(f"Failed to create graph execution service: {e}")
                    message = "Graph execution service not available"
            else:
                message = f"Cannot step execution in status: {execution_status.status}"
        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {action}")

        logger.info(f"API Response: control_execution completed - {execution_id}")

        return {
            "success": True,
            "execution_id": execution_id,
            "action": action,
            "new_status": execution_status.status,
            "message": message,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Control execution error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/executions/{execution_id}/variables")
async def get_execution_variables(execution_id: str):
    """Get current execution variables for debugging"""
    try:
        logger.info(f"API Request: get_execution_variables - {execution_id}")

        if execution_id not in execution_storage:
            raise HTTPException(
                status_code=404, detail=f"Execution {execution_id} not found"
            )

        execution_status = execution_storage[execution_id]

        logger.info(f"API Response: get_execution_variables completed - {execution_id}")

        return {
            "success": True,
            "execution_id": execution_id,
            "variables": execution_status.variables,
            "message": "Execution variables retrieved successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get execution variables error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/executions")
async def list_executions():
    """List all executions"""
    try:
        logger.info("API Request: list_executions")

        executions = [
            {
                "execution_id": exec_id,
                "workflow_id": status.workflow_id,
                "status": status.status,
                "start_time": status.start_time,
                "end_time": status.end_time,
                "progress": status.progress,
            }
            for exec_id, status in execution_storage.items()
        ]

        logger.info(
            f"API Response: list_executions completed, found {len(executions)} executions"
        )

        return {
            "success": True,
            "executions": executions,
            "message": f"Found {len(executions)} executions",
        }

    except Exception as e:
        logger.error(f"List executions error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def _execute_workflow_background(
    execution_id: str, workflow: WorkflowDefinition, debug_mode: bool = False
):
    """Background task for workflow execution"""
    try:
        logger.info(f"Background execution started - {execution_id}")

        # Get execution status
        execution_status = execution_storage.get(execution_id)
        if not execution_status:
            logger.error(f"Execution status not found for {execution_id}")
            return

        # Update status to running
        execution_status.status = "running"
        execution_storage[execution_id] = execution_status

        # Get graph execution service with dependencies
        try:
            graph_service = _get_graph_execution_service_with_deps()
        except Exception as e:
            logger.error(f"Failed to create graph execution service: {e}")
            execution_status.status = "failed"
            execution_status.error = "Graph execution service not available"
            from datetime import datetime

            execution_status.end_time = datetime.now().isoformat()
            execution_storage[execution_id] = execution_status
            return

        # Execute the workflow
        result = await graph_service.execute_graph(
            workflow=workflow, debug_mode=debug_mode
        )

        # Update execution status
        execution_status.status = (
            "completed" if result.get("success", False) else "failed"
        )
        execution_status.progress = 100.0
        from datetime import datetime

        execution_status.end_time = datetime.now().isoformat()

        if not result.get("success", False):
            execution_status.error = result.get("error", "Unknown error")

        execution_storage[execution_id] = execution_status

        logger.info(f"Background execution completed - {execution_id}")

    except Exception as e:
        logger.error(f"Background execution error - {execution_id}: {e}", exc_info=True)

        # Update execution status with error
        execution_status = execution_storage.get(execution_id)
        if execution_status:
            execution_status.status = "failed"
            execution_status.error = str(e)
            from datetime import datetime

            execution_status.end_time = datetime.now().isoformat()
            execution_storage[execution_id] = execution_status
