"""
Message Types for MoireTracker Worker Bridge

Definiert alle Nachrichten-Typen für die Kommunikation zwischen
Host und Worker Prozessen.

NEU: Tool-Execution Message Types für Tool-Using Agents
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List


class WorkerType(str, Enum):
    """Verfügbare Worker-Typen."""
    CLASSIFICATION = "classification"
    VALIDATION = "validation"
    OCR = "ocr"
    EXECUTION = "execution"  # NEU: Tool-Execution Worker


class UICategory(str, Enum):
    """Standard UI-Element Kategorien."""
    BUTTON = "button"
    ICON = "icon"
    INPUT = "input"
    TEXT = "text"
    IMAGE = "image"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    DROPDOWN = "dropdown"
    LINK = "link"
    CONTAINER = "container"
    HEADER = "header"
    FOOTER = "footer"
    MENU = "menu"
    TOOLBAR = "toolbar"
    UNKNOWN = "unknown"
    # Extended categories
    BROWSER_ICON = "browser_icon"
    EDITOR_ICON = "editor_icon"
    SYSTEM_ICON = "system_icon"
    APP_ICON = "app_icon"
    GAME_ICON = "game_icon"
    TASKBAR_ITEM = "taskbar_item"
    TAB = "tab"
    NOTIFICATION = "notification"
    SCROLLBAR = "scrollbar"


# ==================== NEU: Tool-Execution Enums ====================

class ToolName(str, Enum):
    """Verfügbare Desktop-Automation Tools."""
    CAPTURE_SCREENSHOT_REGION = "capture_screenshot_region"
    CLICK_AT_POSITION = "click_at_position"
    TYPE_TEXT = "type_text"
    SCROLL = "scroll"
    WAIT = "wait"
    WAIT_FOR_ELEMENT = "wait_for_element"
    PRESS_KEY = "press_key"
    HOTKEY = "hotkey"
    DRAG = "drag"
    DOUBLE_CLICK = "double_click"
    RIGHT_CLICK = "right_click"


class ExecutionStatus(str, Enum):
    """Status einer Tool-Ausführung."""
    PENDING = "pending"
    EXECUTING = "executing"
    VALIDATING = "validating"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    NEEDS_REPLAN = "needs_replan"
    CANCELLED = "cancelled"


class SizeValidationResult(str, Enum):
    """Ergebnis der LLM Size-Parameter Validation."""
    APPROVED = "approved"
    ADJUSTED = "adjusted"
    REJECTED = "rejected"


@dataclass
class ClassifyIconMessage:
    """
    Anfrage zur Icon-Klassifizierung.
    
    Sent from Host to Classification Worker.
    """
    box_id: str
    crop_base64: str  # Base64-encoded PNG image
    cnn_category: Optional[str] = None  # Pre-classification from CNN
    cnn_confidence: float = 0.0
    ocr_text: Optional[str] = None  # OCR text if available
    bounds: Optional[Dict[str, int]] = None  # x, y, width, height
    request_id: Optional[str] = None  # Für Request-Tracking
    # NEU: Task-Context für Tool-Using Agents
    user_request: Optional[str] = None  # Original User-Anfrage
    task_context: Optional[Dict[str, Any]] = None  # App-Kontext, UI-State
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "boxId": self.box_id,
            "cropBase64": self.crop_base64,
            "cnnCategory": self.cnn_category,
            "cnnConfidence": self.cnn_confidence,
            "ocrText": self.ocr_text,
            "bounds": self.bounds,
            "requestId": self.request_id,
            "userRequest": self.user_request,
            "taskContext": self.task_context
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClassifyIconMessage":
        return cls(
            box_id=data.get("boxId", data.get("box_id", "")),
            crop_base64=data.get("cropBase64", data.get("crop_base64", "")),
            cnn_category=data.get("cnnCategory", data.get("cnn_category")),
            cnn_confidence=float(data.get("cnnConfidence", data.get("cnn_confidence", 0.0))),
            ocr_text=data.get("ocrText", data.get("ocr_text")),
            bounds=data.get("bounds"),
            request_id=data.get("requestId", data.get("request_id")),
            user_request=data.get("userRequest", data.get("user_request")),
            task_context=data.get("taskContext", data.get("task_context"))
        )


@dataclass
class ClassificationResult:
    """
    Ergebnis der Icon-Klassifizierung.
    
    Returned from Classification Worker to Host.
    """
    box_id: str
    llm_category: str
    llm_confidence: float = 0.0
    semantic_name: Optional[str] = None  # Human-readable name
    description: Optional[str] = None  # Brief description of element
    reasoning: Optional[str] = None  # Explanation for classification
    model_used: Optional[str] = None
    processing_time_ms: float = 0.0
    request_id: Optional[str] = None
    error: Optional[str] = None
    # NEU: Dynamic Category Support
    new_category_suggested: Optional[Dict[str, Any]] = None  # {name, description, parent}
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "boxId": self.box_id,
            "llmCategory": self.llm_category,
            "llmConfidence": self.llm_confidence,
            "semanticName": self.semantic_name,
            "description": self.description,
            "reasoning": self.reasoning,
            "modelUsed": self.model_used,
            "processingTimeMs": self.processing_time_ms,
            "requestId": self.request_id,
            "error": self.error
        }
        if self.new_category_suggested:
            result["newCategorySuggested"] = self.new_category_suggested
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClassificationResult":
        return cls(
            box_id=data.get("boxId", data.get("box_id", "")),
            llm_category=data.get("llmCategory", data.get("llm_category", "unknown")),
            llm_confidence=float(data.get("llmConfidence", data.get("llm_confidence", 0.0))),
            semantic_name=data.get("semanticName", data.get("semantic_name")),
            description=data.get("description"),
            reasoning=data.get("reasoning"),
            model_used=data.get("modelUsed", data.get("model_used")),
            processing_time_ms=float(data.get("processingTimeMs", data.get("processing_time_ms", 0.0))),
            request_id=data.get("requestId", data.get("request_id")),
            error=data.get("error"),
            new_category_suggested=data.get("newCategorySuggested", data.get("new_category_suggested"))
        )


@dataclass
class ValidationRequest:
    """
    Anfrage zur Validierung einer Klassifizierung.
    
    Sent from Host to Validation Worker.
    """
    box_id: str
    crop_base64: str
    cnn_category: str
    cnn_confidence: float
    llm_category: str
    llm_confidence: float
    ocr_text: Optional[str] = None
    request_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "boxId": self.box_id,
            "cropBase64": self.crop_base64,
            "cnnCategory": self.cnn_category,
            "cnnConfidence": self.cnn_confidence,
            "llmCategory": self.llm_category,
            "llmConfidence": self.llm_confidence,
            "ocrText": self.ocr_text,
            "requestId": self.request_id
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ValidationRequest":
        return cls(
            box_id=data.get("boxId", data.get("box_id", "")),
            crop_base64=data.get("cropBase64", data.get("crop_base64", "")),
            cnn_category=data.get("cnnCategory", data.get("cnn_category", "")),
            cnn_confidence=float(data.get("cnnConfidence", data.get("cnn_confidence", 0.0))),
            llm_category=data.get("llmCategory", data.get("llm_category", "")),
            llm_confidence=float(data.get("llmConfidence", data.get("llm_confidence", 0.0))),
            ocr_text=data.get("ocrText", data.get("ocr_text")),
            request_id=data.get("requestId", data.get("request_id"))
        )


@dataclass
class ValidationResult:
    """
    Ergebnis der Validierung.
    
    Returned from Validation Worker to Host.
    """
    box_id: str
    final_category: str
    final_confidence: float
    categories_match: bool
    validation_reasoning: Optional[str] = None
    needs_human_review: bool = False
    model_used: Optional[str] = None
    processing_time_ms: float = 0.0
    request_id: Optional[str] = None
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "boxId": self.box_id,
            "finalCategory": self.final_category,
            "finalConfidence": self.final_confidence,
            "categoriesMatch": self.categories_match,
            "validationReasoning": self.validation_reasoning,
            "needsHumanReview": self.needs_human_review,
            "modelUsed": self.model_used,
            "processingTimeMs": self.processing_time_ms,
            "requestId": self.request_id,
            "error": self.error
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ValidationResult":
        return cls(
            box_id=data.get("boxId", data.get("box_id", "")),
            final_category=data.get("finalCategory", data.get("final_category", "unknown")),
            final_confidence=float(data.get("finalConfidence", data.get("final_confidence", 0.0))),
            categories_match=data.get("categoriesMatch", data.get("categories_match", False)),
            validation_reasoning=data.get("validationReasoning", data.get("validation_reasoning")),
            needs_human_review=data.get("needsHumanReview", data.get("needs_human_review", False)),
            model_used=data.get("modelUsed", data.get("model_used")),
            processing_time_ms=float(data.get("processingTimeMs", data.get("processing_time_ms", 0.0))),
            request_id=data.get("requestId", data.get("request_id")),
            error=data.get("error")
        )


@dataclass
class BatchClassifyRequest:
    """Batch-Anfrage für mehrere Icons."""
    batch_id: str
    icons: List[ClassifyIconMessage]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "batchId": self.batch_id,
            "icons": [icon.to_dict() for icon in self.icons]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BatchClassifyRequest":
        return cls(
            batch_id=data.get("batchId", data.get("batch_id", "")),
            icons=[ClassifyIconMessage.from_dict(i) for i in data.get("icons", [])]
        )


@dataclass
class BatchClassifyResult:
    """Batch-Ergebnis für mehrere Icons."""
    batch_id: str
    results: List[ClassificationResult]
    successful: int = 0
    failed: int = 0
    processing_time_ms: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "batchId": self.batch_id,
            "results": [r.to_dict() for r in self.results],
            "successful": self.successful,
            "failed": self.failed,
            "processingTimeMs": self.processing_time_ms
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BatchClassifyResult":
        return cls(
            batch_id=data.get("batchId", data.get("batch_id", "")),
            results=[ClassificationResult.from_dict(r) for r in data.get("results", [])],
            successful=data.get("successful", 0),
            failed=data.get("failed", 0),
            processing_time_ms=float(data.get("processingTimeMs", data.get("processing_time_ms", 0.0)))
        )


# NEU: Category Management Messages

@dataclass
class CategorySuggestion:
    """Eine vom LLM vorgeschlagene neue Kategorie."""
    name: str
    description: str
    parent: Optional[str] = None
    examples: List[str] = field(default_factory=list)
    suggested_by: str = "gemini-2.0-flash"
    context: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parent": self.parent,
            "examples": self.examples,
            "suggestedBy": self.suggested_by,
            "context": self.context
        }


@dataclass
class CategoryRegistryStatus:
    """Status der CategoryRegistry."""
    total_categories: int
    leaf_categories: int
    pending_categories: int
    llm_created_categories: int
    auto_approve_threshold: int
    top_categories: List[tuple]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "totalCategories": self.total_categories,
            "leafCategories": self.leaf_categories,
            "pendingCategories": self.pending_categories,
            "llmCreatedCategories": self.llm_created_categories,
            "autoApproveThreshold": self.auto_approve_threshold,
            "topCategories": self.top_categories
        }


@dataclass
class WorkerStatus:
    """Status eines Workers."""
    worker_id: str
    worker_type: WorkerType
    is_running: bool = True
    last_active: datetime = field(default_factory=datetime.now)
    tasks_processed: int = 0
    tasks_failed: int = 0
    current_task: Optional[str] = None
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "workerId": self.worker_id,
            "workerType": self.worker_type.value if isinstance(self.worker_type, WorkerType) else self.worker_type,
            "isRunning": self.is_running,
            "lastActive": self.last_active.isoformat() if self.last_active else None,
            "tasksProcessed": self.tasks_processed,
            "tasksFailed": self.tasks_failed,
            "currentTask": self.current_task,
            "errorMessage": self.error_message
        }


# ==================== NEU: Tool-Execution Message Types ====================

@dataclass
class TaskContext:
    """
    Vollständiger Kontext für Tool-Using Agents.
    
    Wird an alle Worker propagiert für kontextbewusste Entscheidungen.
    """
    user_request: str  # Original User-Anfrage
    app_context: Dict[str, Any] = field(default_factory=dict)  # Active Window, Resolution
    ui_state: Dict[str, Any] = field(default_factory=dict)  # Detected Elements, Focus
    history: List[Dict[str, Any]] = field(default_factory=list)  # Bisherige Aktionen
    screen_bounds: Dict[str, int] = field(default_factory=lambda: {"width": 1920, "height": 1080})
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "userRequest": self.user_request,
            "appContext": self.app_context,
            "uiState": self.ui_state,
            "history": self.history,
            "screenBounds": self.screen_bounds,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskContext":
        return cls(
            user_request=data.get("userRequest", data.get("user_request", "")),
            app_context=data.get("appContext", data.get("app_context", {})),
            ui_state=data.get("uiState", data.get("ui_state", {})),
            history=data.get("history", []),
            screen_bounds=data.get("screenBounds", data.get("screen_bounds", {"width": 1920, "height": 1080})),
            metadata=data.get("metadata", {})
        )


@dataclass
class ActionStep:
    """
    Einzelne Aktion mit Tool-Call.
    
    Vom Planner generiert, vom ExecutionWorker ausgeführt.
    """
    step_id: str
    tool_name: ToolName
    tool_params: Dict[str, Any]
    expected_outcome: str
    target_element: Optional[str] = None  # Element-ID für Size-Validation
    timeout_seconds: float = 5.0
    requires_validation: bool = True
    reasoning: Optional[str] = None  # LLM-Begründung
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "stepId": self.step_id,
            "toolName": self.tool_name.value if isinstance(self.tool_name, ToolName) else self.tool_name,
            "toolParams": self.tool_params,
            "expectedOutcome": self.expected_outcome,
            "targetElement": self.target_element,
            "timeoutSeconds": self.timeout_seconds,
            "requiresValidation": self.requires_validation,
            "reasoning": self.reasoning
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ActionStep":
        tool_name = data.get("toolName", data.get("tool_name", ""))
        if isinstance(tool_name, str):
            try:
                tool_name = ToolName(tool_name)
            except ValueError:
                tool_name = ToolName.WAIT  # Fallback
        
        return cls(
            step_id=data.get("stepId", data.get("step_id", "")),
            tool_name=tool_name,
            tool_params=data.get("toolParams", data.get("tool_params", {})),
            expected_outcome=data.get("expectedOutcome", data.get("expected_outcome", "")),
            target_element=data.get("targetElement", data.get("target_element")),
            timeout_seconds=float(data.get("timeoutSeconds", data.get("timeout_seconds", 5.0))),
            requires_validation=data.get("requiresValidation", data.get("requires_validation", True)),
            reasoning=data.get("reasoning")
        )


@dataclass
class TaskExecutionRequest:
    """
    Anfrage zur Task-Ausführung mit vollem Kontext.
    
    Sent from Host/Orchestrator to ExecutionWorker.
    """
    task_id: str
    context: TaskContext
    action_plan: List[ActionStep]
    max_validation_rounds: int = 3
    validation_threshold: float = 0.02  # 2% Änderung für Erfolg
    request_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "taskId": self.task_id,
            "context": self.context.to_dict(),
            "actionPlan": [step.to_dict() for step in self.action_plan],
            "maxValidationRounds": self.max_validation_rounds,
            "validationThreshold": self.validation_threshold,
            "requestId": self.request_id
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskExecutionRequest":
        return cls(
            task_id=data.get("taskId", data.get("task_id", "")),
            context=TaskContext.from_dict(data.get("context", {})),
            action_plan=[ActionStep.from_dict(s) for s in data.get("actionPlan", data.get("action_plan", []))],
            max_validation_rounds=int(data.get("maxValidationRounds", data.get("max_validation_rounds", 3))),
            validation_threshold=float(data.get("validationThreshold", data.get("validation_threshold", 0.02))),
            request_id=data.get("requestId", data.get("request_id"))
        )


@dataclass
class SizeValidationReport:
    """
    Report der LLM Size-Parameter Validation.
    
    Vom SizeValidator erstellt, an Function Agent gesendet.
    """
    result: SizeValidationResult
    original_request: Dict[str, int]  # x, y, width, height vom LLM
    element_bounds: Dict[str, int]  # Bounds des Target-Elements
    applied_size: Dict[str, int]  # Tatsächlich verwendete Größe
    adjustments: Dict[str, Any]  # width_delta, height_delta, reasons
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "result": self.result.value if isinstance(self.result, SizeValidationResult) else self.result,
            "originalRequest": self.original_request,
            "elementBounds": self.element_bounds,
            "appliedSize": self.applied_size,
            "adjustments": self.adjustments,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SizeValidationReport":
        result = data.get("result", "approved")
        if isinstance(result, str):
            try:
                result = SizeValidationResult(result)
            except ValueError:
                result = SizeValidationResult.APPROVED
        
        return cls(
            result=result,
            original_request=data.get("originalRequest", data.get("original_request", {})),
            element_bounds=data.get("elementBounds", data.get("element_bounds", {})),
            applied_size=data.get("appliedSize", data.get("applied_size", {})),
            adjustments=data.get("adjustments", {}),
            timestamp=datetime.fromisoformat(data["timestamp"]) if data.get("timestamp") else datetime.now()
        )


@dataclass
class ToolExecutionResult:
    """
    Ergebnis einer einzelnen Tool-Ausführung.
    
    Returned from ExecutionWorker for each ActionStep.
    """
    step_id: str
    tool_name: ToolName
    status: ExecutionStatus
    screenshot_before: Optional[str] = None  # Base64
    screenshot_after: Optional[str] = None  # Base64
    change_percentage: float = 0.0
    action_result: Dict[str, Any] = field(default_factory=dict)
    size_validation: Optional[SizeValidationReport] = None  # NEU: Size-Validation Report
    error_context: Optional[str] = None
    duration_ms: float = 0.0
    validation_attempts: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "stepId": self.step_id,
            "toolName": self.tool_name.value if isinstance(self.tool_name, ToolName) else self.tool_name,
            "status": self.status.value if isinstance(self.status, ExecutionStatus) else self.status,
            "screenshotBefore": self.screenshot_before,
            "screenshotAfter": self.screenshot_after,
            "changePercentage": self.change_percentage,
            "actionResult": self.action_result,
            "sizeValidation": self.size_validation.to_dict() if self.size_validation else None,
            "errorContext": self.error_context,
            "durationMs": self.duration_ms,
            "validationAttempts": self.validation_attempts
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolExecutionResult":
        tool_name = data.get("toolName", data.get("tool_name", "wait"))
        if isinstance(tool_name, str):
            try:
                tool_name = ToolName(tool_name)
            except ValueError:
                tool_name = ToolName.WAIT
        
        status = data.get("status", "pending")
        if isinstance(status, str):
            try:
                status = ExecutionStatus(status)
            except ValueError:
                status = ExecutionStatus.PENDING
        
        size_val_data = data.get("sizeValidation", data.get("size_validation"))
        size_validation = SizeValidationReport.from_dict(size_val_data) if size_val_data else None
        
        return cls(
            step_id=data.get("stepId", data.get("step_id", "")),
            tool_name=tool_name,
            status=status,
            screenshot_before=data.get("screenshotBefore", data.get("screenshot_before")),
            screenshot_after=data.get("screenshotAfter", data.get("screenshot_after")),
            change_percentage=float(data.get("changePercentage", data.get("change_percentage", 0.0))),
            action_result=data.get("actionResult", data.get("action_result", {})),
            size_validation=size_validation,
            error_context=data.get("errorContext", data.get("error_context")),
            duration_ms=float(data.get("durationMs", data.get("duration_ms", 0.0))),
            validation_attempts=int(data.get("validationAttempts", data.get("validation_attempts", 0)))
        )


@dataclass
class TaskExecutionResult:
    """
    Endergebnis einer vollständigen Task-Ausführung.
    
    Returned from ExecutionWorker after all steps completed or failed.
    """
    task_id: str
    success: bool
    status: ExecutionStatus
    steps_executed: int
    steps_total: int
    validation_rounds: int
    results: List[ToolExecutionResult]
    final_screenshot: Optional[str] = None
    error_summary: Optional[str] = None
    total_duration_ms: float = 0.0
    request_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "taskId": self.task_id,
            "success": self.success,
            "status": self.status.value if isinstance(self.status, ExecutionStatus) else self.status,
            "stepsExecuted": self.steps_executed,
            "stepsTotal": self.steps_total,
            "validationRounds": self.validation_rounds,
            "results": [r.to_dict() for r in self.results],
            "finalScreenshot": self.final_screenshot,
            "errorSummary": self.error_summary,
            "totalDurationMs": self.total_duration_ms,
            "requestId": self.request_id
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskExecutionResult":
        status = data.get("status", "pending")
        if isinstance(status, str):
            try:
                status = ExecutionStatus(status)
            except ValueError:
                status = ExecutionStatus.PENDING
        
        return cls(
            task_id=data.get("taskId", data.get("task_id", "")),
            success=data.get("success", False),
            status=status,
            steps_executed=int(data.get("stepsExecuted", data.get("steps_executed", 0))),
            steps_total=int(data.get("stepsTotal", data.get("steps_total", 0))),
            validation_rounds=int(data.get("validationRounds", data.get("validation_rounds", 0))),
            results=[ToolExecutionResult.from_dict(r) for r in data.get("results", [])],
            final_screenshot=data.get("finalScreenshot", data.get("final_screenshot")),
            error_summary=data.get("errorSummary", data.get("error_summary")),
            total_duration_ms=float(data.get("totalDurationMs", data.get("total_duration_ms", 0.0))),
            request_id=data.get("requestId", data.get("request_id"))
        )


@dataclass
class ReplanRequest:
    """
    Anfrage für Re-Planning nach fehlgeschlagener Validation.
    
    Sent from ExecutionWorker to Planner.
    """
    task_id: str
    original_context: TaskContext
    executed_steps: List[ToolExecutionResult]
    failed_step: ToolExecutionResult
    error_context: str
    remaining_rounds: int
    request_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "taskId": self.task_id,
            "originalContext": self.original_context.to_dict(),
            "executedSteps": [s.to_dict() for s in self.executed_steps],
            "failedStep": self.failed_step.to_dict(),
            "errorContext": self.error_context,
            "remainingRounds": self.remaining_rounds,
            "requestId": self.request_id
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReplanRequest":
        return cls(
            task_id=data.get("taskId", data.get("task_id", "")),
            original_context=TaskContext.from_dict(data.get("originalContext", data.get("original_context", {}))),
            executed_steps=[ToolExecutionResult.from_dict(s) for s in data.get("executedSteps", data.get("executed_steps", []))],
            failed_step=ToolExecutionResult.from_dict(data.get("failedStep", data.get("failed_step", {}))),
            error_context=data.get("errorContext", data.get("error_context", "")),
            remaining_rounds=int(data.get("remainingRounds", data.get("remaining_rounds", 0))),
            request_id=data.get("requestId", data.get("request_id"))
        )


# ==================== Helper Functions ====================

def calculate_combined_confidence(
    cnn_confidence: float,
    llm_confidence: float,
    categories_match: bool
) -> float:
    """
    Berechnet kombinierte Konfidenz aus CNN und LLM.
    
    Wenn Kategorien übereinstimmen: höhere Konfidenz
    Wenn sie nicht übereinstimmen: niedrigere Konfidenz
    """
    if cnn_confidence == 0 or llm_confidence == 0:
        return max(cnn_confidence, llm_confidence)
    
    if categories_match:
        # Boost wenn beide übereinstimmen
        return min(1.0, (cnn_confidence + llm_confidence) / 2 * 1.2)
    else:
        # Penalty wenn sie nicht übereinstimmen
        return (cnn_confidence + llm_confidence) / 2 * 0.7


def should_trigger_active_learning(
    cnn_category: Optional[str],
    llm_category: str,
    cnn_confidence: float,
    llm_confidence: float,
    confidence_threshold: float = 0.7,
    mismatch_threshold: float = 0.5
) -> bool:
    """
    Entscheidet ob Element für Active Learning markiert werden soll.
    
    Trigger wenn:
    1. Kategorien nicht übereinstimmen
    2. Eine der Konfidenzen unter Schwellwert
    3. CNN hat keine Kategorie (neues Element?)
    """
    # CNN hat keine Kategorie - potenziell neues Element
    if not cnn_category or cnn_category == "unknown":
        return True
    
    # Kategorien stimmen nicht überein
    if cnn_category != llm_category:
        return True
    
    # Niedrige Konfidenz bei einer Quelle
    if cnn_confidence < confidence_threshold or llm_confidence < confidence_threshold:
        return True
    
    return False