"""TRAE Snapshot Management API

Provides endpoints for creating, managing, and processing desktop snapshots
for OCR zone design and automation template creation.

Author: TRAE Development Team
Version: 2.0.0
"""

import asyncio
import base64
import json
import uuid
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from PIL import Image, ImageGrab
from pydantic import BaseModel, Field, field_validator

from ..config import get_settings
from ..logger_config import get_logger
from ..services.desktop_service import DesktopService
from ..services.manager import get_service_manager
from ..services.ocr_service import OCRService as EnhancedOCRService

# ============================================================================
# CONFIGURATION
# ============================================================================

router = APIRouter(prefix="/snapshots", tags=["snapshots"])
logger = get_logger(__name__)
settings = get_settings()

# ============================================================================
# PYDANTIC MODELS
# ============================================================================


class SnapshotMetadata(BaseModel):
    """Metadata for a desktop snapshot."""

    timestamp: datetime
    resolution: Dict[str, int]  # {"width": 1920, "height": 1080}
    monitor_index: int = 0
    format: str = "png"
    file_size: Optional[int] = None
    checksum: Optional[str] = None


class OCRZoneConfig(BaseModel):
    """Configuration for an OCR zone."""

    id: str
    x: int = Field(..., ge=0, description="X coordinate of the zone")
    y: int = Field(..., ge=0, description="Y coordinate of the zone")
    width: int = Field(..., gt=0, description="Width of the zone")
    height: int = Field(..., gt=0, description="Height of the zone")
    label: str = Field(..., min_length=1, max_length=100)
    language: str = Field(default="eng", description="OCR language code")
    confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    preprocessing: Dict[str, Any] = Field(
        default_factory=lambda: {
            "grayscale": True,
            "threshold": False,
            "denoise": False,
            "scale_factor": 1.0,
        }
    )

    @field_validator("preprocessing")
    @classmethod
    def validate_preprocessing(cls, v):
        required_keys = {"grayscale", "threshold", "denoise", "scale_factor"}
        if not all(key in v for key in required_keys):
            raise ValueError(f"Preprocessing must contain keys: {required_keys}")
        if not 0.5 <= v["scale_factor"] <= 3.0:
            raise ValueError("Scale factor must be between 0.5 and 3.0")
        return v


class ClickActionConfig(BaseModel):
    """Configuration for a click action."""

    id: str
    x: int = Field(..., ge=0, description="X coordinate for the click")
    y: int = Field(..., ge=0, description="Y coordinate for the click")
    label: str = Field(..., min_length=1, max_length=100)
    action: str = Field(..., pattern="^(left|right|double|middle)$")
    wait_before: int = Field(
        default=0, ge=0, le=10000, description="Wait before click (ms)"
    )
    wait_after: int = Field(
        default=500, ge=0, le=10000, description="Wait after click (ms)"
    )
    retry_count: int = Field(default=3, ge=1, le=10)
    timeout: int = Field(default=5000, ge=1000, le=30000, description="Timeout (ms)")


class SnapshotTemplate(BaseModel):
    """Template containing OCR zones and click actions for a snapshot."""

    id: Optional[str] = None
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=500)
    snapshot_metadata: SnapshotMetadata
    ocr_zones: List[OCRZoneConfig] = Field(default_factory=list)
    click_actions: List[ClickActionConfig] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    tags: List[str] = Field(default_factory=list)

    @field_validator("ocr_zones")
    @classmethod
    def validate_ocr_zones(cls, v):
        if len(v) > 50:
            raise ValueError("Maximum 50 OCR zones allowed per template")
        zone_ids = [zone.id for zone in v]
        if len(zone_ids) != len(set(zone_ids)):
            raise ValueError("OCR zone IDs must be unique")
        return v

    @field_validator("click_actions")
    @classmethod
    def validate_click_actions(cls, v):
        if len(v) > 100:
            raise ValueError("Maximum 100 click actions allowed per template")
        action_ids = [action.id for action in v]
        if len(action_ids) != len(set(action_ids)):
            raise ValueError("Click action IDs must be unique")
        return v


class CreateSnapshotRequest(BaseModel):
    """Request to create a new desktop snapshot."""

    monitor_index: int = Field(default=0, ge=0, description="Monitor index to capture")
    include_metadata: bool = Field(default=True)
    format: str = Field(default="png", pattern="^(png|jpg|jpeg)$")
    quality: int = Field(default=95, ge=1, le=100, description="Image quality for JPEG")
    region: Optional[Dict[str, int]] = Field(
        None, description="Specific region to capture"
    )

    @field_validator("region")
    @classmethod
    def validate_region(cls, v):
        if v is not None:
            required_keys = {"x", "y", "width", "height"}
            if not all(key in v for key in required_keys):
                raise ValueError(f"Region must contain keys: {required_keys}")
            if any(v[key] < 0 for key in required_keys):
                raise ValueError("Region coordinates must be non-negative")
        return v


class ProcessOCRZoneRequest(BaseModel):
    """Request to process OCR on a specific zone."""

    snapshot_id: str
    zone_config: OCRZoneConfig
    return_image: bool = Field(default=False, description="Return processed zone image")


class ExecuteClickActionRequest(BaseModel):
    """Request to execute a click action."""

    action_config: ClickActionConfig
    dry_run: bool = Field(default=False, description="Simulate without actual click")


class SnapshotResponse(BaseModel):
    """Response containing snapshot data."""

    id: str
    image_data: str  # Base64 encoded image
    metadata: SnapshotMetadata
    file_path: Optional[str] = None


class OCRZoneResult(BaseModel):
    """Result of OCR processing on a zone."""

    zone_id: str
    text: str
    confidence: float
    processing_time_ms: int
    bounding_boxes: List[Dict[str, Any]] = Field(default_factory=list)
    processed_image: Optional[str] = None  # Base64 if requested


class TemplateListResponse(BaseModel):
    """Response for template listing."""

    templates: List[SnapshotTemplate]
    total_count: int
    page: int
    page_size: int


# ============================================================================
# DEPENDENCIES
# ============================================================================


def get_ocr_service() -> EnhancedOCRService:
    """Get OCR service instance."""
    try:
        service_manager = get_service_manager()
        if service_manager._initialized and service_manager.has_service("ocr"):
            return service_manager.get_service("ocr")
    except Exception as e:
        logger.warning(f"Could not get OCR service from manager: {e}")

    # Fallback to enhanced OCR service
    return EnhancedOCRService()


def get_desktop_service() -> DesktopService:
    """Get desktop service instance."""
    try:
        service_manager = get_service_manager()
        if service_manager._initialized and service_manager.has_service(
            "click_automation"
        ):
            # Use click automation service as desktop service
            return service_manager.get_service("click_automation")
    except Exception as e:
        logger.warning(f"Could not get click automation service from manager: {e}")

    # Fallback to direct desktop service
    return DesktopService()


# ============================================================================
# STORAGE HELPERS
# ============================================================================


class SnapshotStorage:
    """Simple file-based storage for snapshots and templates."""

    def __init__(self):
        self.snapshots_dir = Path(settings.data_dir) / "snapshots"
        self.templates_dir = Path(settings.data_dir) / "templates"
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.templates_dir.mkdir(parents=True, exist_ok=True)

    def save_snapshot(
        self, snapshot_id: str, image_data: bytes, metadata: SnapshotMetadata
    ) -> str:
        """Save snapshot to disk."""
        file_path = self.snapshots_dir / f"{snapshot_id}.{metadata.format}"
        with open(file_path, "wb") as f:
            f.write(image_data)

        # Save metadata
        metadata_path = self.snapshots_dir / f"{snapshot_id}_metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(metadata.model_dump(), f, default=str, indent=2)

        return str(file_path)

    def load_snapshot(self, snapshot_id: str) -> tuple[bytes, SnapshotMetadata]:
        """Load snapshot from disk."""
        # Find snapshot file
        snapshot_files = list(self.snapshots_dir.glob(f"{snapshot_id}.*"))
        if not snapshot_files:
            raise FileNotFoundError(f"Snapshot {snapshot_id} not found")

        snapshot_file = [
            f for f in snapshot_files if not f.name.endswith("_metadata.json")
        ][0]

        with open(snapshot_file, "rb") as f:
            image_data = f.read()

        # Load metadata
        metadata_path = self.snapshots_dir / f"{snapshot_id}_metadata.json"
        with open(metadata_path, "r") as f:
            metadata_dict = json.load(f)
            metadata = SnapshotMetadata(**metadata_dict)

        return image_data, metadata

    def save_template(self, template: SnapshotTemplate) -> str:
        """Save template to disk."""
        if not template.id:
            template.id = str(uuid.uuid4())

        template.updated_at = datetime.now()
        file_path = self.templates_dir / f"{template.id}.json"

        with open(file_path, "w") as f:
            json.dump(template.model_dump(), f, default=str, indent=2)

        return template.id

    def load_template(self, template_id: str) -> SnapshotTemplate:
        """Load template from disk."""
        file_path = self.templates_dir / f"{template_id}.json"
        if not file_path.exists():
            raise FileNotFoundError(f"Template {template_id} not found")

        with open(file_path, "r") as f:
            template_dict = json.load(f)
            return SnapshotTemplate(**template_dict)

    def list_templates(
        self, page: int = 1, page_size: int = 20
    ) -> tuple[List[SnapshotTemplate], int]:
        """List all templates with pagination."""
        template_files = list(self.templates_dir.glob("*.json"))
        total_count = len(template_files)

        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size

        templates = []
        for file_path in template_files[start_idx:end_idx]:
            try:
                with open(file_path, "r") as f:
                    template_dict = json.load(f)
                    templates.append(SnapshotTemplate(**template_dict))
            except Exception as e:
                logger.warning(f"Failed to load template {file_path}: {e}")

        return templates, total_count

    def delete_template(self, template_id: str) -> bool:
        """Delete template from disk."""
        file_path = self.templates_dir / f"{template_id}.json"
        if file_path.exists():
            file_path.unlink()
            return True
        return False


# Global storage instance
storage = SnapshotStorage()


# ============================================================================
# API ENDPOINTS
@router.get("/", response_model=List[Dict[str, Any]])
async def list_snapshots():
    """List all available snapshots."""
    try:
        snapshots = []

        # Get all snapshot files from storage directory
        for snapshot_file in storage.snapshots_dir.glob("*.png"):
            snapshot_id = snapshot_file.stem

            # Skip metadata files
            if snapshot_id.endswith("_metadata"):
                continue

            try:
                # Load metadata if available
                metadata_path = storage.snapshots_dir / f"{snapshot_id}_metadata.json"
                if metadata_path.exists():
                    with open(metadata_path, "r") as f:
                        metadata = json.load(f)
                else:
                    # Create basic metadata if not available
                    metadata = {
                        "timestamp": snapshot_file.stat().st_mtime,
                        "resolution": {"width": 0, "height": 0},
                        "monitor_index": 0,
                        "format": "png",
                        "file_size": snapshot_file.stat().st_size,
                    }

                snapshots.append(
                    {
                        "id": snapshot_id,
                        "metadata": metadata,
                        "file_path": str(snapshot_file),
                    }
                )

            except Exception as e:
                logger.warning(
                    f"Failed to load snapshot metadata for {snapshot_id}: {e}"
                )
                # Include snapshot with minimal info
                snapshots.append(
                    {
                        "id": snapshot_id,
                        "metadata": {
                            "format": "png",
                            "file_size": snapshot_file.stat().st_size,
                            "timestamp": snapshot_file.stat().st_mtime,
                        },
                        "file_path": str(snapshot_file),
                    }
                )

        # Also check for JPEG snapshots
        for snapshot_file in storage.snapshots_dir.glob("*.jpg"):
            snapshot_id = snapshot_file.stem

            if snapshot_id.endswith("_metadata"):
                continue

            try:
                metadata_path = storage.snapshots_dir / f"{snapshot_id}_metadata.json"
                if metadata_path.exists():
                    with open(metadata_path, "r") as f:
                        metadata = json.load(f)
                else:
                    metadata = {
                        "timestamp": snapshot_file.stat().st_mtime,
                        "resolution": {"width": 0, "height": 0},
                        "monitor_index": 0,
                        "format": "jpg",
                        "file_size": snapshot_file.stat().st_size,
                    }

                snapshots.append(
                    {
                        "id": snapshot_id,
                        "metadata": metadata,
                        "file_path": str(snapshot_file),
                    }
                )

            except Exception as e:
                logger.warning(
                    f"Failed to load snapshot metadata for {snapshot_id}: {e}"
                )
                snapshots.append(
                    {
                        "id": snapshot_id,
                        "metadata": {
                            "format": "jpg",
                            "file_size": snapshot_file.stat().st_size,
                            "timestamp": snapshot_file.stat().st_mtime,
                        },
                        "file_path": str(snapshot_file),
                    }
                )

        # Sort by timestamp (newest first)
        snapshots.sort(key=lambda x: x["metadata"].get("timestamp", 0), reverse=True)

        logger.info(f"Found {len(snapshots)} snapshots")
        return snapshots

    except Exception as e:
        logger.error(f"Failed to list snapshots: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to list snapshots: {str(e)}"
        )


# ============================================================================


@router.post("/create", response_model=SnapshotResponse)
async def create_snapshot(
    request: CreateSnapshotRequest,
    background_tasks: BackgroundTasks,
    desktop_service: DesktopService = Depends(get_desktop_service),
):
    """Create a new desktop snapshot."""
    try:
        logger.info(f"Creating snapshot for monitor {request.monitor_index}")

        # Capture screenshot
        if request.region:
            # Capture specific region
            bbox = (
                request.region["x"],
                request.region["y"],
                request.region["x"] + request.region["width"],
                request.region["y"] + request.region["height"],
            )
            screenshot = ImageGrab.grab(bbox)
        else:
            # Capture full screen
            screenshot = ImageGrab.grab()

        # Convert to desired format
        buffer = BytesIO()
        if request.format.lower() in ["jpg", "jpeg"]:
            screenshot.save(buffer, format="JPEG", quality=request.quality)
        else:
            screenshot.save(buffer, format="PNG")

        image_data = buffer.getvalue()

        # Create metadata
        metadata = SnapshotMetadata(
            timestamp=datetime.now(),
            resolution={"width": screenshot.width, "height": screenshot.height},
            monitor_index=request.monitor_index,
            format=request.format,
            file_size=len(image_data),
        )

        # Generate unique ID and save
        snapshot_id = str(uuid.uuid4())
        file_path = storage.save_snapshot(snapshot_id, image_data, metadata)

        # Encode image as base64
        image_base64 = base64.b64encode(image_data).decode("utf-8")

        logger.info(f"Snapshot {snapshot_id} created successfully")

        return SnapshotResponse(
            id=snapshot_id,
            image_data=image_base64,
            metadata=metadata,
            file_path=file_path,
        )

    except Exception as e:
        logger.error(f"Failed to create snapshot: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to create snapshot: {str(e)}"
        )


@router.post("/process-ocr", response_model=OCRZoneResult)
async def process_ocr_zone(
    request: ProcessOCRZoneRequest,
    ocr_service: EnhancedOCRService = Depends(get_ocr_service),
):
    """Process OCR on a specific zone of a snapshot."""
    try:
        # Load snapshot
        image_data, metadata = storage.load_snapshot(request.snapshot_id)

        # Convert to numpy array
        image = Image.open(BytesIO(image_data))
        image_array = np.array(image)

        # Extract zone
        zone = request.zone_config
        zone_image = image_array[
            zone.y : zone.y + zone.height, zone.x : zone.x + zone.width
        ]

        # Apply preprocessing
        if zone.preprocessing["grayscale"]:
            zone_image = cv2.cvtColor(zone_image, cv2.COLOR_RGB2GRAY)

        if zone.preprocessing["threshold"]:
            _, zone_image = cv2.threshold(
                zone_image, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
            )

        if zone.preprocessing["denoise"]:
            zone_image = cv2.medianBlur(zone_image, 3)

        if zone.preprocessing["scale_factor"] != 1.0:
            new_width = int(zone_image.shape[1] * zone.preprocessing["scale_factor"])
            new_height = int(zone_image.shape[0] * zone.preprocessing["scale_factor"])
            zone_image = cv2.resize(
                zone_image, (new_width, new_height), interpolation=cv2.INTER_CUBIC
            )

        # Perform OCR
        start_time = datetime.now()

        # Convert back to PIL Image for OCR service
        if len(zone_image.shape) == 2:  # Grayscale
            pil_image = Image.fromarray(zone_image, mode="L")
        else:
            pil_image = Image.fromarray(zone_image)

        # Convert to base64 for OCR service
        buffer = BytesIO()
        pil_image.save(buffer, format="PNG")
        zone_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

        # Process with OCR service
        ocr_result = await ocr_service.process_ocr_region(
            image_data=zone_base64,
            language=zone.language,
            confidence_threshold=zone.confidence_threshold,
        )

        processing_time = (datetime.now() - start_time).total_seconds() * 1000

        # Prepare response
        result = OCRZoneResult(
            zone_id=zone.id,
            text=ocr_result.get("text", ""),
            confidence=ocr_result.get("confidence", 0.0),
            processing_time_ms=int(processing_time),
            bounding_boxes=ocr_result.get("bounding_boxes", []),
        )

        # Include processed image if requested
        if request.return_image:
            result.processed_image = zone_base64

        logger.info(
            f"OCR processed for zone {zone.id}: '{result.text}' (confidence: {result.confidence:.2f})"
        )

        return result

    except FileNotFoundError:
        raise HTTPException(
            status_code=404, detail=f"Snapshot {request.snapshot_id} not found"
        )
    except Exception as e:
        logger.error(f"Failed to process OCR zone: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process OCR: {str(e)}")


@router.post("/templates", response_model=Dict[str, str])
async def save_template(template: SnapshotTemplate):
    """Save a snapshot template."""
    try:
        template_id = storage.save_template(template)
        logger.info(f"Template {template_id} saved successfully")

        return {"template_id": template_id, "message": "Template saved successfully"}

    except Exception as e:
        logger.error(f"Failed to save template: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to save template: {str(e)}"
        )


@router.get("/templates", response_model=TemplateListResponse)
async def list_templates(page: int = 1, page_size: int = 20):
    """List all snapshot templates."""
    try:
        templates, total_count = storage.list_templates(page, page_size)

        return TemplateListResponse(
            templates=templates, total_count=total_count, page=page, page_size=page_size
        )

    except Exception as e:
        logger.error(f"Failed to list templates: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to list templates: {str(e)}"
        )


@router.get("/templates/{template_id}", response_model=SnapshotTemplate)
async def get_template(template_id: str):
    """Get a specific template."""
    try:
        template = storage.load_template(template_id)
        return template

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Template {template_id} not found")
    except Exception as e:
        logger.error(f"Failed to get template {template_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get template: {str(e)}")


@router.delete("/templates/{template_id}")
async def delete_template(template_id: str):
    """Delete a template."""
    try:
        if storage.delete_template(template_id):
            logger.info(f"Template {template_id} deleted successfully")
            return {"message": "Template deleted successfully"}
        else:
            raise HTTPException(
                status_code=404, detail=f"Template {template_id} not found"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete template {template_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to delete template: {str(e)}"
        )


@router.post("/execute-click", response_model=Dict[str, Any])
async def execute_click_action(
    request: ExecuteClickActionRequest,
    desktop_service: DesktopService = Depends(get_desktop_service),
):
    """Execute a click action."""
    try:
        action = request.action_config

        if request.dry_run:
            logger.info(
                f"Dry run: Would execute {action.action} click at ({action.x}, {action.y})"
            )
            return {
                "success": True,
                "message": f"Dry run: {action.action} click at ({action.x}, {action.y})",
                "dry_run": True,
            }

        # Wait before action
        if action.wait_before > 0:
            await asyncio.sleep(action.wait_before / 1000)

        # Execute click action
        success = await desktop_service.execute_click(
            x=action.x,
            y=action.y,
            button=action.action,
            retry_count=action.retry_count,
            timeout=action.timeout,
        )

        # Wait after action
        if action.wait_after > 0:
            await asyncio.sleep(action.wait_after / 1000)

        if success:
            logger.info(
                f"Click action executed successfully: {action.action} at ({action.x}, {action.y})"
            )
            return {
                "success": True,
                "message": f"Click action executed: {action.action} at ({action.x}, {action.y})",
                "dry_run": False,
            }
        else:
            raise Exception("Click action failed")

    except Exception as e:
        logger.error(f"Failed to execute click action: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to execute click action: {str(e)}"
        )


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "snapshot-api",
        "version": "2.0.0",
    }


@router.get("/{snapshot_id}", response_model=SnapshotResponse)
async def get_snapshot(snapshot_id: str):
    """Retrieve a specific snapshot."""
    try:
        image_data, metadata = storage.load_snapshot(snapshot_id)
        image_base64 = base64.b64encode(image_data).decode("utf-8")

        return SnapshotResponse(
            id=snapshot_id, image_data=image_base64, metadata=metadata
        )

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Snapshot {snapshot_id} not found")
    except Exception as e:
        logger.error(f"Failed to retrieve snapshot {snapshot_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve snapshot: {str(e)}"
        )
