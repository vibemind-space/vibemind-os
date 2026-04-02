"""Pydantic models for snapshot-based OCR and automation."""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator


class SnapshotRequest(BaseModel):
    """Request model for creating snapshots."""

    monitor: int = Field(0, description="Monitor index (0 = primary)")
    region: Optional[Dict[str, int]] = Field(
        None, description="Optional region {x, y, width, height}"
    )
    quality: int = Field(85, ge=1, le=100, description="Image quality (1-100)")

    @field_validator("region")
    @classmethod
    def validate_region(cls, v):
        if v is not None:
            required_keys = {"x", "y", "width", "height"}
            if not all(key in v for key in required_keys):
                raise ValueError(f"Region must contain keys: {required_keys}")
            if any(v[key] < 0 for key in required_keys):
                raise ValueError("Region values must be non-negative")
        return v


class OCRZoneConfig(BaseModel):
    """Configuration for OCR zones."""

    id: str = Field(..., description="Unique zone identifier")
    name: str = Field(..., description="Human-readable zone name")
    x: int = Field(..., ge=0, description="X coordinate")
    y: int = Field(..., ge=0, description="Y coordinate")
    width: int = Field(..., gt=0, description="Zone width")
    height: int = Field(..., gt=0, description="Zone height")
    language: str = Field("eng", description="OCR language code")
    confidence_threshold: float = Field(
        0.8, ge=0.0, le=1.0, description="Minimum confidence threshold"
    )
    preprocessing: Optional[Dict[str, Any]] = Field(
        None, description="OCR preprocessing options"
    )


class ClickActionConfig(BaseModel):
    """Configuration for click actions."""

    id: str = Field(..., description="Unique action identifier")
    name: str = Field(..., description="Human-readable action name")
    x: int = Field(..., ge=0, description="X coordinate")
    y: int = Field(..., ge=0, description="Y coordinate")
    action_type: str = Field(
        ..., description="Action type (click, double_click, right_click)"
    )
    button: str = Field("left", description="Mouse button (left, right, middle)")
    delay_ms: int = Field(100, ge=0, description="Delay before action (milliseconds)")

    @field_validator("action_type")
    @classmethod
    def validate_action_type(cls, v):
        valid_types = {"click", "double_click", "right_click"}
        if v not in valid_types:
            raise ValueError(f"Action type must be one of: {valid_types}")
        return v

    @field_validator("button")
    @classmethod
    def validate_button(cls, v):
        valid_buttons = {"left", "right", "middle"}
        if v not in valid_buttons:
            raise ValueError(f"Button must be one of: {valid_buttons}")
        return v


class SnapshotTemplate(BaseModel):
    """Template for snapshot-based automation."""

    name: str = Field(..., description="Template name")
    description: str = Field("", description="Template description")
    snapshot_id: str = Field(..., description="Associated snapshot ID")
    ocr_zones: List[OCRZoneConfig] = Field(
        default_factory=list, description="OCR zone configurations"
    )
    click_actions: List[ClickActionConfig] = Field(
        default_factory=list, description="Click action configurations"
    )
    created_at: str = Field(..., description="Creation timestamp")
    updated_at: Optional[str] = Field(None, description="Last update timestamp")
    version: str = Field("1.0", description="Template version")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class OCRExecutionRequest(BaseModel):
    """Request model for OCR execution."""

    snapshot_id: str = Field(..., description="Snapshot to process")
    zones: List[OCRZoneConfig] = Field(..., description="OCR zones to process")
    real_time: bool = Field(False, description="Real-time processing mode")


class ClickExecutionRequest(BaseModel):
    """Request model for click execution."""

    snapshot_id: str = Field(..., description="Reference snapshot")
    actions: List[ClickActionConfig] = Field(
        ..., description="Click actions to execute"
    )
    sequential: bool = Field(True, description="Execute actions sequentially")
    delay_between_actions: int = Field(
        500, ge=0, description="Delay between actions (ms)"
    )


class OCRResult(BaseModel):
    """Result of OCR processing."""

    zone_id: str = Field(..., description="Zone identifier")
    zone_name: str = Field(..., description="Zone name")
    text: str = Field(..., description="Extracted text")
    confidence: float = Field(..., ge=0.0, le=1.0, description="OCR confidence")
    processing_time_ms: int = Field(..., description="Processing time in milliseconds")
    bounding_box: Optional[Dict[str, int]] = Field(
        None, description="Text bounding box"
    )
    error: Optional[str] = Field(None, description="Error message if processing failed")


class ClickResult(BaseModel):
    """Result of click action execution."""

    action_id: str = Field(..., description="Action identifier")
    action_name: str = Field(..., description="Action name")
    success: bool = Field(..., description="Execution success")
    execution_time_ms: int = Field(..., description="Execution time in milliseconds")
    coordinates: Dict[str, int] = Field(..., description="Actual click coordinates")
    error: Optional[str] = Field(None, description="Error message if execution failed")


class OCRExecutionResponse(BaseModel):
    """Response for OCR execution."""

    snapshot_id: str = Field(..., description="Processed snapshot ID")
    results: List[OCRResult] = Field(..., description="OCR results")
    total_processing_time_ms: int = Field(..., description="Total processing time")
    success_count: int = Field(..., description="Number of successful OCR operations")
    error_count: int = Field(..., description="Number of failed OCR operations")
    timestamp: str = Field(..., description="Execution timestamp")


class ClickExecutionResponse(BaseModel):
    """Response for click execution."""

    snapshot_id: str = Field(..., description="Reference snapshot ID")
    results: List[ClickResult] = Field(..., description="Click results")
    total_execution_time_ms: int = Field(..., description="Total execution time")
    success_count: int = Field(..., description="Number of successful clicks")
    error_count: int = Field(..., description="Number of failed clicks")
    timestamp: str = Field(..., description="Execution timestamp")


class SnapshotResponse(BaseModel):
    """Response for snapshot creation."""

    snapshot_id: str = Field(..., description="Unique snapshot identifier")
    image_data: str = Field(..., description="Base64-encoded image data")
    metadata: Dict[str, Any] = Field(..., description="Snapshot metadata")
    timestamp: str = Field(..., description="Creation timestamp")
    file_size: int = Field(..., description="Image file size in bytes")


class TemplateListResponse(BaseModel):
    """Response for template listing."""

    templates: List[str] = Field(..., description="List of template names")
    count: int = Field(..., description="Total number of templates")


class SnapshotListResponse(BaseModel):
    """Response for snapshot listing."""

    snapshots: List[str] = Field(..., description="List of snapshot IDs")
    count: int = Field(..., description="Total number of snapshots")


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str = Field(..., description="Error message")
    error_code: str = Field(..., description="Error code")
    details: Optional[Dict[str, Any]] = Field(
        None, description="Additional error details"
    )
    timestamp: str = Field(..., description="Error timestamp")


class SuccessResponse(BaseModel):
    """Standard success response."""

    success: bool = Field(True, description="Operation success")
    message: str = Field(..., description="Success message")
    data: Optional[Dict[str, Any]] = Field(None, description="Additional response data")
    timestamp: str = Field(..., description="Response timestamp")
