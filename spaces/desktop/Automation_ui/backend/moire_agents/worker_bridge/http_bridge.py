"""
HTTP Bridge Server für MoireTracker gRPC

Stellt REST Endpoints für die TypeScript Bridge bereit:
- POST /classify_batch - Batch Icon Klassifizierung
- GET /status - Host Status
- POST /start - Host starten
- POST /stop - Host stoppen
- GET /active_learning/queue - Active Learning Queue
- POST /active_learning/confirm - Label bestätigen

=== NEW: Tool-Using Agent Endpoints ===
- POST /execute_task - Kompletten Task mit Validation-Loop ausführen
- POST /execute_action - Einzelne Aktion ausführen
- POST /validate_action - Action-Ergebnis validieren
- GET /get_tools - Verfügbare Desktop-Tools
- POST /plan_task - Task planen mit LLM

Läuft auf Port 8766 (separat vom gRPC Host auf 50051)
"""

import asyncio
import json
import logging
import os
import sys
import time
from typing import Optional, Dict, Any, List
from datetime import datetime
from dataclasses import asdict
import uuid

# Add parent paths
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# aiohttp for async HTTP server
try:
    from aiohttp import web
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False
    logging.warning("aiohttp not installed. Run: pip install aiohttp")

from .host import GrpcWorkerHost, get_grpc_host
from .messages import (
    ClassifyIconMessage,
    ValidationResult,
    BatchClassifyResult,
    # NEW: Tool-Using Agent Messages
    ToolName,
    ExecutionStatus,
    TaskContext,
    ActionStep,
    TaskExecutionRequest,
    ToolExecutionResult,
    TaskExecutionResult,
    SizeValidationReport,
    ReplanRequest
)
from .workers.classification_worker import ClassificationWorker
from .workers.validation_worker import VisionValidationWorker

# NEW: Execution Worker Import
try:
    from .workers.execution_worker import ExecutionWorker, get_execution_worker
    from .workers.desktop_tools import (
        get_tool_executor,
        get_tool_functions_schema,
        DESKTOP_TOOLS
    )
    HAS_EXECUTION_WORKER = True
except ImportError as e:
    logging.warning(f"Execution Worker nicht verfügbar: {e}")
    HAS_EXECUTION_WORKER = False

# NEW: Planner Worker Import
try:
    from .workers.planner_worker import PlannerWorker, get_planner_worker
    HAS_PLANNER_WORKER = True
except ImportError as e:
    logging.warning(f"Planner Worker nicht verfügbar: {e}")
    HAS_PLANNER_WORKER = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class HttpBridgeServer:
    """
    HTTP Bridge Server für MoireTracker.
    
    Übersetzt REST Requests in gRPC Worker Calls.
    Unterstützt jetzt auch Tool-Using Agent Endpoints.
    """
    
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8766,
        grpc_host_address: str = "localhost:50051"
    ):
        self.host = host
        self.port = port
        self.grpc_host_address = grpc_host_address
        
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        
        # Worker instances (for development without full gRPC)
        self._classification_worker: Optional[ClassificationWorker] = None
        self._validation_worker: Optional[VisionValidationWorker] = None
        
        # NEW: Execution Worker
        self._execution_worker: Optional[ExecutionWorker] = None
        
        # NEW: Planner Worker
        self._planner_worker: Optional[PlannerWorker] = None
        
        # Active Learning Queue
        self._active_learning_queue: List[Dict[str, Any]] = []
        
        # NEW: Task Tracking
        self._active_tasks: Dict[str, TaskExecutionRequest] = {}
        self._task_results: Dict[str, TaskExecutionResult] = {}
        
        # Stats
        self._total_requests: int = 0
        self._total_classifications: int = 0
        self._total_task_executions: int = 0
        self._total_action_executions: int = 0
        self._total_plans_created: int = 0
        self._start_time: Optional[datetime] = None
        
        logger.info(f"HttpBridgeServer initialisiert: {host}:{port}")
    
    async def start(self) -> bool:
        """Startet den HTTP Server."""
        if not HAS_AIOHTTP:
            logger.error("aiohttp nicht installiert!")
            return False
        
        try:
            # Create app
            self._app = web.Application()
            self._setup_routes()
            
            # Initialize workers
            self._classification_worker = ClassificationWorker()
            self._validation_worker = VisionValidationWorker()
            
            # NEW: Initialize Execution Worker
            if HAS_EXECUTION_WORKER:
                self._execution_worker = get_execution_worker()
                logger.info("✓ Execution Worker initialisiert")
            else:
                logger.warning("⚠ Execution Worker nicht verfügbar")
            
            # NEW: Initialize Planner Worker
            if HAS_PLANNER_WORKER:
                self._planner_worker = get_planner_worker()
                logger.info("✓ Planner Worker initialisiert")
            else:
                logger.warning("⚠ Planner Worker nicht verfügbar")
            
            # Start server
            self._runner = web.AppRunner(self._app)
            await self._runner.setup()
            self._site = web.TCPSite(self._runner, self.host, self.port)
            await self._site.start()
            
            self._start_time = datetime.now()
            
            logger.info(f"✓ HTTP Bridge Server gestartet auf http://{self.host}:{self.port}")
            return True
            
        except Exception as e:
            logger.error(f"HTTP Bridge Start fehlgeschlagen: {e}")
            return False
    
    async def stop(self) -> None:
        """Stoppt den HTTP Server."""
        if self._runner:
            await self._runner.cleanup()
        self._runner = None
        self._site = None
        self._app = None
        logger.info("HTTP Bridge Server gestoppt")
    
    def _setup_routes(self) -> None:
        """Registriert die HTTP Routes."""
        # Existing routes
        self._app.router.add_get('/status', self._handle_status)
        self._app.router.add_post('/classify_batch', self._handle_classify_batch)
        self._app.router.add_post('/classify_single', self._handle_classify_single)
        self._app.router.add_post('/start', self._handle_start_host)
        self._app.router.add_post('/stop', self._handle_stop_host)
        self._app.router.add_get('/active_learning/queue', self._handle_al_queue)
        self._app.router.add_post('/active_learning/confirm', self._handle_al_confirm)
        self._app.router.add_get('/stats', self._handle_stats)
        
        # NEW: Tool-Using Agent Routes
        self._app.router.add_post('/execute_task', self._handle_execute_task)
        self._app.router.add_post('/execute_action', self._handle_execute_action)
        self._app.router.add_post('/validate_action', self._handle_validate_action)
        self._app.router.add_get('/get_tools', self._handle_get_tools)
        self._app.router.add_post('/plan_task', self._handle_plan_task)
        self._app.router.add_get('/task_status/{task_id}', self._handle_task_status)
        
        # CORS Middleware
        self._app.router.add_route('OPTIONS', '/{tail:.*}', self._handle_cors)
    
    # ==================== Request Handlers ====================
    
    async def _handle_cors(self, request: web.Request) -> web.Response:
        """Handle CORS preflight requests."""
        return web.Response(
            status=204,
            headers={
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type'
            }
        )
    
    def _cors_response(self, data: Any, status: int = 200) -> web.Response:
        """Create response with CORS headers."""
        return web.json_response(
            data,
            status=status,
            headers={
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type'
            }
        )
    
    async def _handle_status(self, request: web.Request) -> web.Response:
        """GET /status - Host Status"""
        self._total_requests += 1
        
        grpc_host = get_grpc_host(self.grpc_host_address)
        running_time = (datetime.now() - self._start_time).total_seconds() if self._start_time else 0
        
        status = {
            "address": self.grpc_host_address,
            "httpBridge": f"{self.host}:{self.port}",
            "isRunning": grpc_host.is_running() if grpc_host else False,
            "maxWorkers": 10,
            "pendingBatches": 0,
            "workers": {
                "totalWorkers": 3 if HAS_EXECUTION_WORKER else 2,  # Classification + Validation + Execution
                "byType": {
                    "classification": 1,
                    "validation": 1,
                    "execution": 1 if HAS_EXECUTION_WORKER else 0
                },
                "totalProcessed": self._total_classifications,
                "totalFailed": 0
            },
            "uptime_seconds": running_time,
            "active_learning_queue_size": len(self._active_learning_queue),
            # NEW: Tool-Using Agent Status
            "execution_worker_available": HAS_EXECUTION_WORKER,
            "active_tasks": len(self._active_tasks),
            "total_task_executions": self._total_task_executions,
            "total_action_executions": self._total_action_executions
        }
        
        return self._cors_response(status)
    
    async def _handle_classify_batch(self, request: web.Request) -> web.Response:
        """POST /classify_batch - Batch Icon Klassifizierung"""
        self._total_requests += 1
        start_time = datetime.now()
        
        try:
            data = await request.json()
            
            batch_id = data.get('batchId', f'batch_{datetime.now().strftime("%H%M%S")}')
            icons_data = data.get('icons', [])
            
            if not icons_data:
                return self._cors_response({"error": "No icons provided"}, 400)
            
            logger.info(f"[{batch_id}] Batch Classification Request: {len(icons_data)} icons")
            
            # Convert to internal format
            icons = []
            for icon_data in icons_data:
                icons.append(ClassifyIconMessage(
                    box_id=icon_data.get('boxId', ''),
                    crop_base64=icon_data.get('cropBase64', ''),
                    cnn_category=icon_data.get('cnnCategory'),
                    cnn_confidence=icon_data.get('cnnConfidence', 0.0),
                    ocr_text=icon_data.get('ocrText'),
                    bounds=icon_data.get('bounds', {})
                ))
            
            # Classify with workers
            results = await self._classify_icons(icons)
            
            # Update stats
            self._total_classifications += len(icons)
            
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            
            # Build response
            response = {
                "batchId": batch_id,
                "results": [self._validation_result_to_dict(r) for r in results],
                "totalIcons": len(icons),
                "successful": sum(1 for r in results if r.final_category != "error"),
                "failed": sum(1 for r in results if r.final_category == "error"),
                "processingTimeMs": processing_time,
                "workersUsed": 2
            }
            
            logger.info(f"[{batch_id}] Batch complete: {response['successful']}/{len(icons)} in {processing_time:.0f}ms")
            
            return self._cors_response(response)
            
        except Exception as e:
            logger.error(f"Batch classification error: {e}")
            return self._cors_response({"error": str(e)}, 500)
    
    async def _handle_classify_single(self, request: web.Request) -> web.Response:
        """POST /classify_single - Single Icon Klassifizierung"""
        self._total_requests += 1
        
        try:
            data = await request.json()
            
            icon = ClassifyIconMessage(
                box_id=data.get('boxId', ''),
                crop_base64=data.get('cropBase64', ''),
                cnn_category=data.get('cnnCategory'),
                cnn_confidence=data.get('cnnConfidence', 0.0),
                ocr_text=data.get('ocrText')
            )
            
            results = await self._classify_icons([icon])
            self._total_classifications += 1
            
            if results:
                return self._cors_response(self._validation_result_to_dict(results[0]))
            else:
                return self._cors_response({"error": "Classification failed"}, 500)
            
        except Exception as e:
            logger.error(f"Single classification error: {e}")
            return self._cors_response({"error": str(e)}, 500)
    
    async def _handle_start_host(self, request: web.Request) -> web.Response:
        """POST /start - gRPC Host starten"""
        self._total_requests += 1
        
        try:
            grpc_host = get_grpc_host(self.grpc_host_address)
            success = await grpc_host.start()
            return self._cors_response({"success": success})
        except Exception as e:
            return self._cors_response({"success": False, "error": str(e)}, 500)
    
    async def _handle_stop_host(self, request: web.Request) -> web.Response:
        """POST /stop - gRPC Host stoppen"""
        self._total_requests += 1
        
        try:
            grpc_host = get_grpc_host(self.grpc_host_address)
            await grpc_host.stop()
            return self._cors_response({"success": True})
        except Exception as e:
            return self._cors_response({"success": False, "error": str(e)}, 500)
    
    async def _handle_al_queue(self, request: web.Request) -> web.Response:
        """GET /active_learning/queue - Active Learning Queue"""
        self._total_requests += 1
        return self._cors_response({"queue": self._active_learning_queue})
    
    async def _handle_al_confirm(self, request: web.Request) -> web.Response:
        """POST /active_learning/confirm - Label bestätigen"""
        self._total_requests += 1
        
        try:
            data = await request.json()
            box_id = data.get('boxId')
            confirmed_label = data.get('confirmedLabel')
            
            # Remove from queue
            self._active_learning_queue = [
                item for item in self._active_learning_queue
                if item.get('boxId') != box_id
            ]
            
            # TODO: Save to training dataset
            logger.info(f"[ActiveLearning] Label confirmed: {box_id} → {confirmed_label}")
            
            return self._cors_response({"success": True})
        except Exception as e:
            return self._cors_response({"success": False, "error": str(e)}, 500)
    
    async def _handle_stats(self, request: web.Request) -> web.Response:
        """GET /stats - Detailed Stats"""
        self._total_requests += 1
        
        clf_stats = self._classification_worker.get_stats() if self._classification_worker else {}
        val_stats = self._validation_worker.get_stats() if self._validation_worker else {}
        exec_stats = self._execution_worker.get_stats() if self._execution_worker else {}
        planner_stats = self._planner_worker.get_stats() if self._planner_worker else {}
        
        return self._cors_response({
            "total_requests": self._total_requests,
            "total_classifications": self._total_classifications,
            "total_task_executions": self._total_task_executions,
            "total_action_executions": self._total_action_executions,
            "total_plans_created": self._total_plans_created,
            "classification_worker": clf_stats,
            "validation_worker": val_stats,
            "execution_worker": exec_stats,
            "planner_worker": planner_stats,
            "active_learning_queue_size": len(self._active_learning_queue),
            "active_tasks": len(self._active_tasks),
            "completed_tasks": len(self._task_results)
        })
    
    # ==================== NEW: Tool-Using Agent Handlers ====================
    
    async def _handle_execute_task(self, request: web.Request) -> web.Response:
        """
        POST /execute_task - Kompletten Task mit Validation-Loop ausführen
        
        Request Body:
        {
            "userRequest": "Öffne Chrome und navigiere zu google.com",
            "appContext": {"activeWindow": "Desktop"},
            "uiState": {"elements": [...]},
            "screenBounds": {"width": 1920, "height": 1080},
            "actionPlan": [
                {
                    "stepId": "step_1",
                    "toolName": "click_at_position",
                    "toolParams": {"x": 100, "y": 200},
                    "expectedOutcome": "Chrome icon clicked"
                }
            ],
            "maxValidationRounds": 3,
            "validationThreshold": 0.02
        }
        
        Response:
        {
            "taskId": "task_abc123",
            "success": true,
            "status": "success",
            "stepsExecuted": 3,
            "stepsTotal": 3,
            "validationRounds": 0,
            "results": [...],
            "totalDurationMs": 1500
        }
        """
        self._total_requests += 1
        self._total_task_executions += 1
        
        if not HAS_EXECUTION_WORKER or not self._execution_worker:
            return self._cors_response({
                "error": "Execution Worker not available",
                "hint": "Check if all dependencies are installed"
            }, 503)
        
        try:
            data = await request.json()
            
            # Parse TaskContext
            context = TaskContext(
                user_request=data.get('userRequest', ''),
                app_context=data.get('appContext', {}),
                ui_state=data.get('uiState', {}),
                screen_bounds=data.get('screenBounds', {'width': 1920, 'height': 1080})
            )
            
            # Parse Action Plan
            action_plan = []
            for step_data in data.get('actionPlan', []):
                try:
                    tool_name = ToolName(step_data.get('toolName'))
                except ValueError:
                    return self._cors_response({
                        "error": f"Unknown tool: {step_data.get('toolName')}",
                        "availableTools": [t.value for t in ToolName]
                    }, 400)
                
                action_plan.append(ActionStep(
                    step_id=step_data.get('stepId', f'step_{len(action_plan)}'),
                    tool_name=tool_name,
                    tool_params=step_data.get('toolParams', {}),
                    expected_outcome=step_data.get('expectedOutcome', ''),
                    requires_validation=step_data.get('requiresValidation', True)
                ))
            
            if not action_plan:
                return self._cors_response({"error": "No actionPlan provided"}, 400)
            
            # Create TaskExecutionRequest
            task_id = data.get('taskId', f'task_{uuid.uuid4().hex[:8]}')
            request_obj = TaskExecutionRequest(
                task_id=task_id,
                context=context,
                action_plan=action_plan,
                max_validation_rounds=data.get('maxValidationRounds', 3),
                validation_threshold=data.get('validationThreshold', 0.02),
                request_id=f'req_{uuid.uuid4().hex[:8]}'
            )
            
            # Track active task
            self._active_tasks[task_id] = request_obj
            
            logger.info(f"[{task_id}] Task Execution Request: {len(action_plan)} steps")
            logger.info(f"  User Request: {context.user_request[:100]}...")
            
            # Execute Task
            result = await self._execution_worker.execute_task(request_obj)
            
            # Store result and remove from active
            self._task_results[task_id] = result
            del self._active_tasks[task_id]
            
            # Build response
            response = self._task_execution_result_to_dict(result)
            
            logger.info(f"[{task_id}] Task complete: {result.status.value}")
            
            return self._cors_response(response)
            
        except Exception as e:
            logger.error(f"Execute task error: {e}")
            import traceback
            traceback.print_exc()
            return self._cors_response({"error": str(e)}, 500)
    
    async def _handle_execute_action(self, request: web.Request) -> web.Response:
        """
        POST /execute_action - Einzelne Aktion ausführen
        
        Request Body:
        {
            "toolName": "click_at_position",
            "toolParams": {"x": 100, "y": 200},
            "context": {
                "userRequest": "Click on button",
                "uiState": {"elements": [...]}
            }
        }
        
        Response:
        {
            "stepId": "single_123",
            "toolName": "click_at_position",
            "status": "success",
            "changePercentage": 0.05,
            "durationMs": 150,
            "screenshotAfter": "base64..."
        }
        """
        self._total_requests += 1
        self._total_action_executions += 1
        
        if not HAS_EXECUTION_WORKER or not self._execution_worker:
            return self._cors_response({
                "error": "Execution Worker not available"
            }, 503)
        
        try:
            data = await request.json()
            
            # Parse tool name
            try:
                tool_name = ToolName(data.get('toolName'))
            except ValueError:
                return self._cors_response({
                    "error": f"Unknown tool: {data.get('toolName')}",
                    "availableTools": [t.value for t in ToolName]
                }, 400)
            
            tool_params = data.get('toolParams', {})
            
            # Parse optional context
            context = None
            if 'context' in data:
                ctx_data = data['context']
                context = TaskContext(
                    user_request=ctx_data.get('userRequest', ''),
                    app_context=ctx_data.get('appContext', {}),
                    ui_state=ctx_data.get('uiState', {}),
                    screen_bounds=ctx_data.get('screenBounds', {'width': 1920, 'height': 1080})
                )
            
            logger.info(f"Execute single action: {tool_name.value}")
            
            # Execute
            result = await self._execution_worker.execute_single_action(
                tool_name=tool_name,
                params=tool_params,
                context=context
            )
            
            # Build response
            response = self._tool_execution_result_to_dict(result)
            
            return self._cors_response(response)
            
        except Exception as e:
            logger.error(f"Execute action error: {e}")
            return self._cors_response({"error": str(e)}, 500)
    
    async def _handle_validate_action(self, request: web.Request) -> web.Response:
        """
        POST /validate_action - Action-Ergebnis validieren
        
        Request Body:
        {
            "screenshotBefore": "base64...",
            "screenshotAfter": "base64...",
            "expectedOutcome": "Button was clicked",
            "threshold": 0.02
        }
        
        Response:
        {
            "valid": true,
            "changePercentage": 0.05,
            "meetsThreshold": true,
            "details": {...}
        }
        """
        self._total_requests += 1
        
        if not HAS_EXECUTION_WORKER or not self._execution_worker:
            return self._cors_response({
                "error": "Execution Worker not available"
            }, 503)
        
        try:
            data = await request.json()
            
            screenshot_before = data.get('screenshotBefore')
            screenshot_after = data.get('screenshotAfter')
            threshold = data.get('threshold', 0.02)
            
            if not screenshot_before or not screenshot_after:
                return self._cors_response({
                    "error": "Both screenshotBefore and screenshotAfter are required"
                }, 400)
            
            # Compare screenshots
            change_percentage = self._execution_worker._compare_screenshots(
                screenshot_before,
                screenshot_after
            )
            
            meets_threshold = change_percentage >= threshold
            
            return self._cors_response({
                "valid": meets_threshold,
                "changePercentage": change_percentage,
                "meetsThreshold": meets_threshold,
                "threshold": threshold,
                "details": {
                    "changePercent": f"{change_percentage * 100:.2f}%",
                    "thresholdPercent": f"{threshold * 100:.2f}%"
                }
            })
            
        except Exception as e:
            logger.error(f"Validate action error: {e}")
            return self._cors_response({"error": str(e)}, 500)
    
    async def _handle_get_tools(self, request: web.Request) -> web.Response:
        """
        GET /get_tools - Verfügbare Desktop-Tools
        
        Response:
        {
            "tools": [
                {
                    "name": "click_at_position",
                    "description": "Click at screen coordinates",
                    "parameters": {...}
                }
            ],
            "totalTools": 11
        }
        """
        self._total_requests += 1
        
        if not HAS_EXECUTION_WORKER:
            return self._cors_response({
                "tools": [],
                "totalTools": 0,
                "error": "Execution Worker not available"
            })
        
        try:
            # Get OpenAI function-calling schema
            tools_schema = get_tool_functions_schema()
            
            # Also include raw tool definitions
            tools_list = []
            for name, definition in DESKTOP_TOOLS.items():
                tools_list.append({
                    "name": name,
                    "description": definition.get("description", ""),
                    "parameters": definition.get("parameters", {}),
                    "requiresValidation": definition.get("requires_validation", True)
                })
            
            return self._cors_response({
                "tools": tools_list,
                "totalTools": len(tools_list),
                "functionCallingSchema": tools_schema
            })
            
        except Exception as e:
            logger.error(f"Get tools error: {e}")
            return self._cors_response({"error": str(e)}, 500)
    
    async def _handle_plan_task(self, request: web.Request) -> web.Response:
        """
        POST /plan_task - Task planen mit LLM
        
        Request Body:
        {
            "userRequest": "Open Chrome and navigate to google.com",
            "uiState": {"elements": [...]},
            "screenBounds": {"width": 1920, "height": 1080},
            "appContext": {"activeWindow": "Desktop"}
        }
        
        Response:
        {
            "taskId": "plan_abc123",
            "actionPlan": [...],
            "reasoning": "First I will...",
            "estimatedSteps": 3
        }
        """
        self._total_requests += 1
        self._total_plans_created += 1
        
        if not HAS_PLANNER_WORKER or not self._planner_worker:
            return self._cors_response({
                "error": "Planner Worker not available",
                "hint": "Check if all dependencies are installed"
            }, 503)
        
        try:
            data = await request.json()
            
            user_request = data.get('userRequest', '')
            if not user_request:
                return self._cors_response({"error": "userRequest is required"}, 400)
            
            ui_state = data.get('uiState', {'elements': []})
            screen_bounds = data.get('screenBounds', {'width': 1920, 'height': 1080})
            app_context = data.get('appContext')
            
            logger.info(f"[Plan] Creating plan for: {user_request[:100]}...")
            
            # Create plan using PlannerWorker
            action_steps = await self._planner_worker.create_plan(
                user_request=user_request,
                ui_state=ui_state,
                screen_bounds=screen_bounds,
                app_context=app_context
            )
            
            # Convert to JSON-serializable format
            plan_steps = []
            for step in action_steps:
                plan_steps.append({
                    "stepId": step.step_id,
                    "toolName": step.tool_name.value,
                    "toolParams": step.tool_params,
                    "expectedOutcome": step.expected_outcome,
                    "requiresValidation": step.requires_validation
                })
            
            task_id = f"plan_{uuid.uuid4().hex[:8]}"
            
            return self._cors_response({
                "taskId": task_id,
                "actionPlan": plan_steps,
                "estimatedSteps": len(plan_steps),
                "reasoning": f"Created {len(plan_steps)} step(s) to accomplish the task",
                "plannerStats": self._planner_worker.get_stats()
            })
            
        except Exception as e:
            logger.error(f"Plan task error: {e}")
            import traceback
            traceback.print_exc()
            return self._cors_response({"error": str(e)}, 500)
    
    async def _handle_task_status(self, request: web.Request) -> web.Response:
        """
        GET /task_status/{task_id} - Task Status abfragen
        """
        self._total_requests += 1
        
        task_id = request.match_info.get('task_id')
        
        if task_id in self._active_tasks:
            return self._cors_response({
                "taskId": task_id,
                "status": "running",
                "inProgress": True
            })
        
        if task_id in self._task_results:
            result = self._task_results[task_id]
            return self._cors_response(self._task_execution_result_to_dict(result))
        
        return self._cors_response({
            "error": f"Task {task_id} not found"
        }, 404)
    
    # ==================== Internal Methods ====================
    
    async def _classify_icons(
        self,
        icons: List[ClassifyIconMessage]
    ) -> List[ValidationResult]:
        """Klassifiziert Icons mit Classification + Validation Workers."""
        from .workers.validation_worker import classify_and_validate
        
        results = []
        
        # Process with semaphore for rate limiting
        semaphore = asyncio.Semaphore(5)
        
        async def process_single(icon: ClassifyIconMessage) -> ValidationResult:
            async with semaphore:
                return await classify_and_validate(
                    icon,
                    self._classification_worker,
                    self._validation_worker
                )
        
        # Parallel processing
        results = await asyncio.gather(
            *[process_single(icon) for icon in icons],
            return_exceptions=True
        )
        
        # Handle exceptions and add to AL queue if needed
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                # Create error result
                error_result = ValidationResult(
                    box_id=icons[i].box_id,
                    request_id=icons[i].request_id,
                    final_category="error",
                    final_confidence=0.0,
                    cnn_category=icons[i].cnn_category,
                    llm_category="error",
                    categories_match=False,
                    needs_human_review=True,
                    add_to_training=False,
                    validation_reasoning=f"Error: {result}"
                )
                final_results.append(error_result)
            else:
                final_results.append(result)
                
                # Add to Active Learning queue if needed
                if result.add_to_training or result.needs_human_review:
                    self._add_to_al_queue(icons[i], result)
        
        return final_results
    
    def _add_to_al_queue(
        self,
        icon: ClassifyIconMessage,
        result: ValidationResult
    ) -> None:
        """Fügt Item zur Active Learning Queue hinzu."""
        self._active_learning_queue.append({
            "boxId": icon.box_id,
            "cropBase64": icon.crop_base64[:100] + "...",  # Truncate for queue
            "cnnCategory": result.cnn_category,
            "llmCategory": result.llm_category,
            "suggestedLabel": result.final_category,
            "confidence": result.final_confidence,
            "needsReview": result.needs_human_review,
            "reasoning": result.validation_reasoning,
            "timestamp": datetime.now().isoformat()
        })
        
        # Limit queue size
        if len(self._active_learning_queue) > 100:
            self._active_learning_queue = self._active_learning_queue[-100:]
    
    def _validation_result_to_dict(self, result: ValidationResult) -> dict:
        """Konvertiert ValidationResult zu Dict für JSON Response."""
        return {
            "boxId": result.box_id,
            "finalCategory": result.final_category,
            "finalConfidence": result.final_confidence,
            "semanticName": result.semantic_name,  # NEW: Human-readable name
            "cnnCategory": result.cnn_category,
            "llmCategory": result.llm_category,
            "categoriesMatch": result.categories_match,
            "needsHumanReview": result.needs_human_review,
            "addToTraining": result.add_to_training,
            "trainingLabel": result.training_label,
            "validationReasoning": result.validation_reasoning
        }
    
    def _tool_execution_result_to_dict(self, result: ToolExecutionResult) -> dict:
        """Konvertiert ToolExecutionResult zu Dict für JSON Response."""
        response = {
            "stepId": result.step_id,
            "toolName": result.tool_name.value,
            "status": result.status.value,
            "changePercentage": result.change_percentage,
            "durationMs": result.duration_ms,
            "validationAttempts": result.validation_attempts
        }
        
        # Add optional fields
        if result.action_result:
            response["actionResult"] = result.action_result
        
        if result.error_context:
            response["errorContext"] = result.error_context
        
        if result.size_validation:
            response["sizeValidation"] = asdict(result.size_validation)
        
        # Include screenshots only if requested (they can be large)
        # response["screenshotBefore"] = result.screenshot_before
        # response["screenshotAfter"] = result.screenshot_after
        
        return response
    
    def _task_execution_result_to_dict(self, result: TaskExecutionResult) -> dict:
        """Konvertiert TaskExecutionResult zu Dict für JSON Response."""
        return {
            "taskId": result.task_id,
            "success": result.success,
            "status": result.status.value,
            "stepsExecuted": result.steps_executed,
            "stepsTotal": result.steps_total,
            "validationRounds": result.validation_rounds,
            "results": [self._tool_execution_result_to_dict(r) for r in result.results],
            "errorSummary": result.error_summary,
            "totalDurationMs": result.total_duration_ms,
            "requestId": result.request_id
        }


# ==================== Standalone Runner ====================

async def run_http_bridge(host: str = "0.0.0.0", port: int = 8766):
    """Startet den HTTP Bridge Server standalone."""
    server = HttpBridgeServer(host=host, port=port)
    
    if not await server.start():
        print("Failed to start HTTP Bridge Server")
        return
    
    print(f"\n{'='*60}")
    print(f"HTTP Bridge Server running on http://{host}:{port}")
    print(f"{'='*60}")
    print("\nEndpoints:")
    print("  GET  /status              - Host Status")
    print("  POST /classify_batch      - Batch Classification")
    print("  POST /classify_single     - Single Classification")
    print("  GET  /active_learning/queue - AL Queue")
    print("  POST /active_learning/confirm - Confirm Label")
    print("  GET  /stats               - Detailed Stats")
    print("\n  === Tool-Using Agent Endpoints ===")
    print("  POST /execute_task        - Execute Task with Validation-Loop")
    print("  POST /execute_action      - Execute Single Action")
    print("  POST /validate_action     - Validate Action Result")
    print("  GET  /get_tools           - Available Desktop Tools")
    print("  POST /plan_task           - Plan Task with LLM")
    print("  GET  /task_status/{id}    - Get Task Status")
    print(f"{'='*60}\n")
    
    try:
        # Keep running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
        await server.stop()


if __name__ == "__main__":
    asyncio.run(run_http_bridge())

# Alias für __main__.py Kompatibilität
async def main():
    """Alias für run_http_bridge - für __main__.py Kompatibilität."""
    await run_http_bridge()