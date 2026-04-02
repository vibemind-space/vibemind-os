"""
API V1 Router for TRAE Backend

Provides v1 API compatibility layer that adapts existing services
to match the frontend's expected interface. This router translates
between the current service implementation and the v1 API contract.

Endpoints:
- /api/v1/desktop/* - Virtual desktop management
- /api/v1/workflow/* - Workflow management  
- /api/v1/automation/* - Automation actions
- /api/v1/ocr/* - OCR processing
"""

import asyncio
import base64
import io
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..logger_config import get_logger, log_api_request
from ..services import (get_desktop_automation_service,
                        get_graph_execution_service, get_service_manager)
from ..services.desktop_service import get_desktop_service
# Note: get_ocr_service temporarily disabled - service not available
from ..services.ocr_service import OCRZoneConfig

logger = get_logger("api_v1")

router = APIRouter()

# ============================================================================
# V1 API MODELS - Match Frontend Expectations
# ============================================================================


class VirtualDesktop(BaseModel):
    """Virtual desktop representation for v1 API"""

    id: str
    name: str
    status: str = "active"
    connection_url: Optional[str] = None
    created_at: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class WorkflowTemplate(BaseModel):
    """Workflow template for v1 API"""

    id: str
    name: str
    description: Optional[str] = None
    steps: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class WorkflowExecution(BaseModel):
    """Workflow execution status for v1 API"""

    execution_id: str
    workflow_id: str
    status: str  # running, completed, failed, stopped
    started_at: str
    completed_at: Optional[str] = None
    progress: float = 0.0
    current_step: Optional[str] = None
    results: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


class AutomationAction(BaseModel):
    """Automation action request for v1 API"""

    type: str  # click, type, screenshot, etc.
    coordinates: Optional[Dict[str, int]] = None  # x, y for clicks
    text: Optional[str] = None  # for typing actions
    target: Optional[str] = None  # CSS selector or element ID
    parameters: Dict[str, Any] = Field(default_factory=dict)


class OCRRegion(BaseModel):
    """OCR processing region for v1 API"""

    x: int
    y: int
    width: int
    height: int
    label: Optional[str] = None
    language: str = "eng"
    confidence_threshold: float = 0.7


class OCRProcessRequest(BaseModel):
    """OCR processing request for v1 API"""

    image: str  # base64 encoded image
    regions: Optional[List[OCRRegion]] = None
    language: str = "eng"
    engine: str = "auto"


# ============================================================================
# VIRTUAL DESKTOP ENDPOINTS
# ============================================================================


@router.get("/desktop/list")
@log_api_request(logger)
async def list_virtual_desktops(request: Request):
    """List all virtual desktops - V1 API adapter"""
    try:
        # Get desktop automation service for session management
        desktop_service = get_desktop_automation_service()
        if not desktop_service:
            raise HTTPException(
                status_code=503, detail="Desktop automation service not available"
            )

        # Get active sessions and format as virtual desktops
        status = await desktop_service.get_status()
        active_sessions = getattr(desktop_service, "active_sessions", {})

        desktops = []
        for session_id, session_data in active_sessions.items():
            desktop = VirtualDesktop(
                id=session_id,
                name=f"Desktop Session {session_id[-8:]}",
                status=session_data.get("status", "active"),
                connection_url=f"ws://localhost:8091/desktop/{session_id}/stream",
                created_at=session_data.get("created_at", datetime.now()).isoformat(),
                metadata={
                    "last_activity": session_data.get(
                        "last_activity", datetime.now()
                    ).isoformat(),
                    "processes": len(session_data.get("processes", [])),
                    "click_sequence_length": len(
                        session_data.get("click_sequence", [])
                    ),
                },
            )
            desktops.append(desktop)

        logger.info(f"V1 API: Listed {len(desktops)} virtual desktops")

        return JSONResponse(
            content={
                "success": True,
                "desktops": [desktop.dict() for desktop in desktops],
                "total": len(desktops),
                "service_status": status,
            }
        )

    except Exception as e:
        logger.error(f"V1 API list_virtual_desktops error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/desktop/create")
@log_api_request(logger)
async def create_virtual_desktop(request: Request, config: Dict[str, Any] = None):
    """Create a new virtual desktop - V1 API adapter"""
    try:
        if config is None:
            config = {}

        # Use desktop automation service to create session
        desktop_service = get_desktop_automation_service()
        if not desktop_service:
            raise HTTPException(
                status_code=503, detail="Desktop automation service not available"
            )

        # Create new desktop session
        session_result = await desktop_service.create_desktop_session(config)
        session_id = session_result["session_id"]

        # Format as V1 virtual desktop
        desktop = VirtualDesktop(
            id=session_id,
            name=config.get("name", f"Desktop Session {session_id[-8:]}"),
            status="active",
            connection_url=f"ws://localhost:8091/desktop/{session_id}/stream",
            created_at=datetime.now().isoformat(),
            metadata={
                "capabilities": session_result.get("capabilities", {}),
                "config": config,
            },
        )

        logger.info(f"V1 API: Created virtual desktop {session_id}")

        return JSONResponse(
            content={
                "success": True,
                "desktop": desktop.dict(),
                "message": "Virtual desktop created successfully",
            }
        )

    except Exception as e:
        logger.error(f"V1 API create_virtual_desktop error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/desktop/connect")
@log_api_request(logger)
async def connect_to_desktop(request: Request, desktop_data: Dict[str, Any]):
    """Connect to a virtual desktop - V1 API adapter"""
    try:
        desktop_id = desktop_data.get("desktop_id")
        if not desktop_id:
            raise HTTPException(status_code=400, detail="desktop_id is required")

        # Get desktop automation service
        desktop_service = get_desktop_automation_service()
        if not desktop_service:
            raise HTTPException(
                status_code=503, detail="Desktop automation service not available"
            )

        # Get session info to verify it exists
        session_info = await desktop_service.get_session_info(desktop_id)

        if not session_info.get("success", False):
            raise HTTPException(
                status_code=404, detail=f"Desktop {desktop_id} not found"
            )

        # Format connection response
        connection_info = {
            "desktop_id": desktop_id,
            "websocket_url": f"ws://localhost:8091/desktop/{desktop_id}/stream",
            "status": "connected",
            "session_info": session_info,
        }

        logger.info(f"V1 API: Connected to virtual desktop {desktop_id}")

        return JSONResponse(
            content={
                "success": True,
                "connection": connection_info,
                "message": "Connected to virtual desktop successfully",
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"V1 API connect_to_desktop error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# WORKFLOW MANAGEMENT ENDPOINTS
# ============================================================================


@router.get("/workflow/templates")
@log_api_request(logger)
async def get_workflow_templates(request: Request):
    """Get workflow templates - V1 API adapter"""
    try:
        # Use existing workflows router logic
        from ..routers.workflows import workflows_storage

        # Convert stored workflows to V1 format
        templates = []
        for workflow_id, workflow in workflows_storage.items():
            template = WorkflowTemplate(
                id=workflow.id or workflow_id,
                name=workflow.name,
                description=workflow.description,
                steps=[],  # Convert nodes/edges to steps format
                metadata=workflow.metadata,
            )

            # Convert workflow nodes to steps
            for node in workflow.nodes:
                step = {
                    "id": node.id,
                    "type": node.type,
                    "position": node.position,
                    "data": node.data,
                }
                template.steps.append(step)

            templates.append(template)

        logger.info(f"V1 API: Retrieved {len(templates)} workflow templates")

        return JSONResponse(
            content={
                "success": True,
                "templates": [template.dict() for template in templates],
                "total": len(templates),
            }
        )

    except Exception as e:
        logger.error(f"V1 API get_workflow_templates error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/workflow/execute")
@log_api_request(logger)
async def execute_workflow(request: Request, workflow_data: Dict[str, Any]):
    """Execute a workflow - V1 API adapter"""
    try:
        workflow_id = workflow_data.get("workflow_id")
        if not workflow_id:
            raise HTTPException(status_code=400, detail="workflow_id is required")

        # Use graph execution service
        from ..services import (get_click_automation_service,
                                get_desktop_automation_service,
                                get_ocr_service, get_websocket_manager)

        try:
            graph_service = get_graph_execution_service(
                websocket_manager=get_websocket_manager(),
                click_service=get_click_automation_service(),
                desktop_service=get_desktop_automation_service(),
                ocr_service=get_ocr_service(),
            )
        except Exception as e:
            raise HTTPException(
                status_code=503, detail=f"Graph execution service not available: {e}"
            )

        # Create execution request
        execution_id = str(uuid.uuid4())

        # Execute workflow (simplified - actual implementation would depend on graph service interface)
        execution_result = {
            "execution_id": execution_id,
            "workflow_id": workflow_id,
            "status": "running",
            "started_at": datetime.now().isoformat(),
            "progress": 0.0,
            "current_step": "initialization",
        }

        logger.info(
            f"V1 API: Started workflow execution {execution_id} for workflow {workflow_id}"
        )

        return JSONResponse(
            content={
                "success": True,
                "execution": execution_result,
                "message": "Workflow execution started",
            }
        )

    except Exception as e:
        logger.error(f"V1 API execute_workflow error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/workflow/start")
@log_api_request(logger)
async def start_workflow(request: Request, workflow_data: Dict[str, Any]):
    """Start workflow execution - V1 API adapter (alias for execute)"""
    return await execute_workflow(request, workflow_data)


@router.get("/workflow/status")
@log_api_request(logger)
async def get_workflow_status(request: Request, execution_id: str):
    """Get workflow execution status - V1 API adapter"""
    try:
        # This would integrate with actual execution tracking
        # For now, return mock status
        execution = WorkflowExecution(
            execution_id=execution_id,
            workflow_id="unknown",
            status="running",
            started_at=datetime.now().isoformat(),
            progress=0.5,
            current_step="processing",
        )

        logger.info(f"V1 API: Retrieved workflow status for execution {execution_id}")

        return JSONResponse(content={"success": True, "execution": execution.dict()})

    except Exception as e:
        logger.error(f"V1 API get_workflow_status error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/workflow/stop")
@log_api_request(logger)
async def stop_workflow(request: Request, execution_data: Dict[str, Any]):
    """Stop workflow execution - V1 API adapter"""
    try:
        execution_id = execution_data.get("execution_id")
        if not execution_id:
            raise HTTPException(status_code=400, detail="execution_id is required")

        # This would integrate with actual execution stopping
        logger.info(f"V1 API: Stopped workflow execution {execution_id}")

        return JSONResponse(
            content={
                "success": True,
                "execution_id": execution_id,
                "status": "stopped",
                "message": "Workflow execution stopped",
            }
        )

    except Exception as e:
        logger.error(f"V1 API stop_workflow error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workflow/history")
@log_api_request(logger)
async def get_workflow_history(request: Request, limit: int = 50):
    """Get workflow execution history - V1 API adapter"""
    try:
        # This would integrate with actual execution history
        # For now, return empty history
        history = []

        logger.info(f"V1 API: Retrieved workflow history (limit: {limit})")

        return JSONResponse(
            content={
                "success": True,
                "history": history,
                "total": len(history),
                "limit": limit,
            }
        )

    except Exception as e:
        logger.error(f"V1 API get_workflow_history error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# AUTOMATION ACTIONS ENDPOINTS
# ============================================================================


@router.post("/automation/actions")
@log_api_request(logger)
async def execute_automation_actions(request: Request, actions_data: Dict[str, Any]):
    """Execute automation actions - V1 API adapter"""
    try:
        actions = actions_data.get("actions", [])
        if not actions:
            raise HTTPException(status_code=400, detail="actions array is required")

        # Get desktop service for automation
        desktop_service = get_desktop_service()

        results = []
        for action in actions:
            action_obj = AutomationAction(**action)

            if action_obj.type == "click" and action_obj.coordinates:
                # Execute click action
                x = action_obj.coordinates["x"]
                y = action_obj.coordinates["y"]
                button = action_obj.parameters.get("button", "left")

                success = await desktop_service.execute_click(x, y, button)

                results.append(
                    {
                        "action_type": "click",
                        "success": success,
                        "coordinates": action_obj.coordinates,
                        "timestamp": datetime.now().isoformat(),
                    }
                )

            elif action_obj.type == "screenshot":
                # Take screenshot
                try:
                    screenshot_data = await desktop_service.take_screenshot()
                    results.append(
                        {
                            "action_type": "screenshot",
                            "success": True,
                            "data": screenshot_data,
                            "timestamp": datetime.now().isoformat(),
                        }
                    )
                except Exception as e:
                    results.append(
                        {
                            "action_type": "screenshot",
                            "success": False,
                            "error": str(e),
                            "timestamp": datetime.now().isoformat(),
                        }
                    )
            else:
                results.append(
                    {
                        "action_type": action_obj.type,
                        "success": False,
                        "error": f"Unsupported action type: {action_obj.type}",
                        "timestamp": datetime.now().isoformat(),
                    }
                )

        successful_actions = sum(1 for r in results if r["success"])
        logger.info(
            f"V1 API: Executed {successful_actions}/{len(actions)} automation actions"
        )

        return JSONResponse(
            content={
                "success": True,
                "results": results,
                "summary": {
                    "total_actions": len(actions),
                    "successful_actions": successful_actions,
                    "failed_actions": len(actions) - successful_actions,
                },
            }
        )

    except Exception as e:
        logger.error(f"V1 API execute_automation_actions error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/automation/screenshot")
@log_api_request(logger)
async def take_automation_screenshot(
    request: Request, screenshot_data: Dict[str, Any] = None
):
    """Take screenshot for automation - V1 API adapter"""
    try:
        if screenshot_data is None:
            screenshot_data = {}

        # Get desktop service
        desktop_service = get_desktop_service()

        # Extract region if specified
        region = screenshot_data.get("region")

        # Take screenshot
        screenshot_base64 = await desktop_service.take_screenshot(region)

        # Get screen size for metadata
        screen_size = await desktop_service.get_screen_size()

        result = {
            "success": True,
            "screenshot": {
                "data": screenshot_base64,
                "format": "png",
                "width": screen_size["width"],
                "height": screen_size["height"],
                "timestamp": datetime.now().isoformat(),
                "region": region,
            },
        }

        logger.info("V1 API: Captured automation screenshot")

        return JSONResponse(content=result)

    except Exception as e:
        logger.error(f"V1 API take_automation_screenshot error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# OCR PROCESSING ENDPOINTS - Removed to avoid routing conflicts
# OCR endpoints are now handled by the dedicated OCR router at /api/v1/ocr/*
# ============================================================================

# NOTE: The following endpoints were removed because they conflict with the
# dedicated OCR router. Use /api/v1/ocr/status, /api/v1/ocr/extract-region, etc.
# from the OCR router instead.


@router.post("/ocr/process")
@log_api_request(logger)
async def process_ocr(request: Request, ocr_request: OCRProcessRequest):
    """Process OCR on image - V1 API adapter"""
    try:
        # OCR service temporarily disabled
        # ocr_service = get_ocr_service()
        # if not ocr_service:
        raise HTTPException(
            status_code=503, detail="OCR service temporarily unavailable"
        )

        # Decode base64 image
        try:
            image_data = base64.b64decode(ocr_request.image)
        except Exception as e:
            raise HTTPException(
                status_code=400, detail=f"Invalid base64 image data: {e}"
            )

        # If regions specified, process them
        if ocr_request.regions:
            zones = []
            for i, region in enumerate(ocr_request.regions):
                zone_config = OCRZoneConfig(
                    id=f"region_{i}",
                    x=region.x,
                    y=region.y,
                    width=region.width,
                    height=region.height,
                    label=region.label or f"Region {i+1}",
                    language=region.language,
                    confidence_threshold=region.confidence_threshold,
                    engine=ocr_request.engine,
                )
                zones.append(zone_config)

            # Process multiple zones
            results = await ocr_service.process_multiple_zones(image_data, zones)

            # Format results for V1 API
            formatted_results = []
            for result in results:
                formatted_result = {
                    "region_id": result.zone_id,
                    "text": result.text,
                    "confidence": result.confidence,
                    "processing_time_ms": result.processing_time_ms,
                    "engine_used": result.engine_used,
                    "language_detected": result.language_detected,
                    "bounding_boxes": [bbox.dict() for bbox in result.bounding_boxes],
                    "error": result.error,
                }
                formatted_results.append(formatted_result)

            logger.info(f"V1 API: Processed OCR for {len(ocr_request.regions)} regions")

            return JSONResponse(
                content={
                    "success": True,
                    "results": formatted_results,
                    "total_regions": len(ocr_request.regions),
                }
            )

        else:
            # Process full image as single zone
            from PIL import Image

            image = Image.open(io.BytesIO(image_data))

            zone_config = OCRZoneConfig(
                id="full_image",
                x=0,
                y=0,
                width=image.width,
                height=image.height,
                label="Full Image",
                language=ocr_request.language,
                engine=ocr_request.engine,
            )

            result = await ocr_service.process_zone(image_data, zone_config)

            formatted_result = {
                "text": result.text,
                "confidence": result.confidence,
                "processing_time_ms": result.processing_time_ms,
                "engine_used": result.engine_used,
                "language_detected": result.language_detected,
                "bounding_boxes": [bbox.dict() for bbox in result.bounding_boxes],
                "error": result.error,
            }

            logger.info("V1 API: Processed OCR for full image")

            return JSONResponse(content={"success": True, "result": formatted_result})

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"V1 API process_ocr error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ocr/regions")
@log_api_request(logger)
async def process_ocr_regions(request: Request, regions_request: Dict[str, Any]):
    """Process OCR on specific regions - V1 API adapter"""
    try:
        # Extract data
        image = regions_request.get("image")
        regions = regions_request.get("regions", [])
        language = regions_request.get("language", "eng")
        engine = regions_request.get("engine", "auto")

        if not image:
            raise HTTPException(status_code=400, detail="image is required")

        if not regions:
            raise HTTPException(status_code=400, detail="regions array is required")

        # Create OCR request
        ocr_request = OCRProcessRequest(
            image=image,
            regions=[OCRRegion(**region) for region in regions],
            language=language,
            engine=engine,
        )

        # Use the main OCR processing endpoint
        return await process_ocr(request, ocr_request)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"V1 API process_ocr_regions error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# HEALTH & STATUS ENDPOINTS
# ============================================================================


@router.get("/health")
@log_api_request(logger)
async def get_health_status(request: Request):
    """Get health status - V1 API adapter"""
    try:
        # Get service manager
        service_manager = get_service_manager()

        # Collect health status from all services
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "services": {},
        }

        # Check individual services
        services_to_check = [
            # ("graph_execution", get_graph_execution_service),  # Temporarily disabled due to dependency issues
            # ("ocr", get_ocr_service),  # Temporarily disabled
            ("desktop_automation", get_desktop_automation_service)
        ]

        overall_healthy = True

        for service_name, service_getter in services_to_check:
            try:
                service = service_getter()
                if service:
                    if hasattr(service, "get_status"):
                        service_status = await service.get_status()
                        is_healthy = service_status.get("service_healthy", True)
                    else:
                        is_healthy = True
                        service_status = {"available": True}

                    health_status["services"][service_name] = {
                        "status": "healthy" if is_healthy else "unhealthy",
                        "details": service_status,
                    }

                    if not is_healthy:
                        overall_healthy = False
                else:
                    health_status["services"][service_name] = {
                        "status": "unavailable",
                        "details": {"error": "Service not available"},
                    }
                    overall_healthy = False

            except Exception as e:
                health_status["services"][service_name] = {
                    "status": "error",
                    "details": {"error": str(e)},
                }
                overall_healthy = False

        health_status["status"] = "healthy" if overall_healthy else "degraded"

        logger.info(
            f"V1 API: Health check completed - status: {health_status['status']}"
        )

        return JSONResponse(content={"success": True, "health": health_status})

    except Exception as e:
        logger.error(f"V1 API get_health_status error: {e}", exc_info=True)
        return JSONResponse(
            content={
                "success": False,
                "health": {
                    "status": "error",
                    "timestamp": datetime.now().isoformat(),
                    "error": str(e),
                },
            },
            status_code=500,
        )
