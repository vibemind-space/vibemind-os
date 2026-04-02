""" OCR Service for TRAE Remote Desktop

Provides advanced OCR capabilities with multiple engines, preprocessing,
and optimized performance for snapshot-based automation.

Features:
- Multiple OCR engines (Tesseract, EasyOCR, PaddleOCR)
- Advanced image preprocessing
- Parallel zone processing
- Confidence scoring and validation
- Language detection and multi-language support
- Performance optimization and caching

Author: TRAE Development Team
Version: 2.0.0
"""

import asyncio
import base64
import hashlib
import time
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
from pydantic import BaseModel, Field

try:
    import pytesseract

    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    pytesseract = None

try:
    import easyocr

    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False
    easyocr = None

try:
    import paddleocr

    PADDLEOCR_AVAILABLE = True
except ImportError:
    PADDLEOCR_AVAILABLE = False
    paddleocr = None

from ..config import get_settings
from ..logger_config import get_logger

# ============================================================================
# CONFIGURATION
# ============================================================================

logger = get_logger(__name__)
settings = get_settings()

# ============================================================================
# MODELS
# ============================================================================


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
    engine: str = Field(default="auto", description="OCR engine preference")
    preprocessing: Dict[str, Any] = Field(
        default_factory=lambda: {
            "grayscale": True,
            "threshold": False,
            "denoise": False,
            "scale_factor": 1.0,
            "contrast_enhancement": 1.0,
            "brightness_adjustment": 0,
            "blur_reduction": False,
            "deskew": False,
        }
    )


class BoundingBox(BaseModel):
    """Bounding box for detected text."""

    x: int
    y: int
    width: int
    height: int
    confidence: float


class OCRZoneResult(BaseModel):
    """Result of OCR processing on a zone."""

    zone_id: str
    text: str
    confidence: float
    processing_time_ms: int
    engine_used: str
    language_detected: Optional[str] = None
    bounding_boxes: List[BoundingBox] = Field(default_factory=list)
    processed_image: Optional[str] = None  # Base64 if requested
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class OCREngineConfig(BaseModel):
    """Configuration for OCR engines."""

    tesseract_config: Dict[str, Any] = Field(
        default_factory=lambda: {"config": "--oem 3 --psm 6", "timeout": 30, "nice": 0}
    )
    easyocr_config: Dict[str, Any] = Field(
        default_factory=lambda: {
            "gpu": False,
            "model_storage_directory": None,
            "download_enabled": True,
        }
    )
    paddleocr_config: Dict[str, Any] = Field(
        default_factory=lambda: {
            "use_angle_cls": True,
            "lang": "en",
            "use_gpu": False,
            "show_log": False,
        }
    )


# ============================================================================
#  OCR SERVICE
# ============================================================================


class OCRService:
    """OCR service with multiple engines and advanced preprocessing."""

    def __init__(self, config: Optional[OCREngineConfig] = None):
        """Initialize the OCR service.

        Args:
            config: OCR engine configuration
        """
        self.config = config or OCREngineConfig()
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.cache: Dict[str, OCRZoneResult] = {}
        self.cache_max_size = 1000

        # Initialize OCR engines
        self._init_engines()

        logger.info(f" OCR Service initialized with engines: {self.available_engines}")

    def _init_engines(self) -> None:
        """Initialize available OCR engines."""
        self.available_engines = []

        # Initialize Tesseract
        if TESSERACT_AVAILABLE:
            try:
                # Test Tesseract installation
                pytesseract.get_tesseract_version()
                self.available_engines.append("tesseract")
                logger.info("Tesseract OCR engine initialized")
            except Exception as e:
                logger.warning(f"Tesseract initialization failed: {e}")

        # Initialize EasyOCR
        if EASYOCR_AVAILABLE:
            try:
                self.easyocr_reader = easyocr.Reader(
                    ["en"], gpu=self.config.easyocr_config.get("gpu", False)
                )
                self.available_engines.append("easyocr")
                logger.info("EasyOCR engine initialized")
            except Exception as e:
                logger.warning(f"EasyOCR initialization failed: {e}")
                self.easyocr_reader = None

        # Initialize PaddleOCR
        if PADDLEOCR_AVAILABLE:
            try:
                self.paddleocr_reader = paddleocr.PaddleOCR(
                    **self.config.paddleocr_config
                )
                self.available_engines.append("paddleocr")
                logger.info("PaddleOCR engine initialized")
            except Exception as e:
                logger.warning(f"PaddleOCR initialization failed: {e}")
                self.paddleocr_reader = None

        if not self.available_engines:
            logger.error(
                "No OCR engines available! Install pytesseract, easyocr, or paddleocr."
            )

    def _get_cache_key(self, image_data: bytes, zone_config: OCRZoneConfig) -> str:
        """Generate cache key for OCR result.

        Args:
            image_data: Image data bytes
            zone_config: OCR zone configuration

        Returns:
            Cache key string
        """
        image_hash = hashlib.md5(image_data).hexdigest()[:16]
        config_str = f"{zone_config.x}_{zone_config.y}_{zone_config.width}_{zone_config.height}_{zone_config.language}_{zone_config.engine}"
        return f"{image_hash}_{config_str}"

    def _preprocess_image(
        self, image: Image.Image, preprocessing: Dict[str, Any]
    ) -> Image.Image:
        """Apply preprocessing to image.

        Args:
            image: PIL Image
            preprocessing: Preprocessing configuration

        Returns:
            Preprocessed PIL Image
        """
        processed = image.copy()

        # Convert to grayscale
        if preprocessing.get("grayscale", True):
            processed = processed.convert("L")

        # Scale image
        scale_factor = preprocessing.get("scale_factor", 1.0)
        if scale_factor != 1.0:
            new_size = (
                int(processed.width * scale_factor),
                int(processed.height * scale_factor),
            )
            processed = processed.resize(new_size, Image.Resampling.LANCZOS)

        # Enhance contrast
        contrast_factor = preprocessing.get("contrast_enhancement", 1.0)
        if contrast_factor != 1.0:
            enhancer = ImageEnhance.Contrast(processed)
            processed = enhancer.enhance(contrast_factor)

        # Adjust brightness
        brightness_adjustment = preprocessing.get("brightness_adjustment", 0)
        if brightness_adjustment != 0:
            enhancer = ImageEnhance.Brightness(processed)
            processed = enhancer.enhance(1.0 + brightness_adjustment / 100.0)

        # Apply threshold
        if preprocessing.get("threshold", False):
            # Convert to numpy array for OpenCV operations
            cv_image = cv2.cvtColor(np.array(processed), cv2.COLOR_RGB2GRAY)
            _, cv_image = cv2.threshold(
                cv_image, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
            )
            processed = Image.fromarray(cv_image)

        # Denoise
        if preprocessing.get("denoise", False):
            processed = processed.filter(ImageFilter.MedianFilter(size=3))

        # Blur reduction (sharpening)
        if preprocessing.get("blur_reduction", False):
            processed = processed.filter(
                ImageFilter.UnsharpMask(radius=1, percent=150, threshold=3)
            )

        # Deskew (basic rotation correction)
        if preprocessing.get("deskew", False):
            processed = self._deskew_image(processed)

        return processed

    def _deskew_image(self, image: Image.Image) -> Image.Image:
        """Apply basic deskewing to image.

        Args:
            image: PIL Image

        Returns:
            Deskewed PIL Image
        """
        try:
            # Convert to OpenCV format
            cv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)

            # Find contours and get skew angle
            coords = np.column_stack(np.where(cv_image > 0))
            angle = cv2.minAreaRect(coords)[-1]

            # Correct angle
            if angle < -45:
                angle = -(90 + angle)
            else:
                angle = -angle

            # Rotate image
            if abs(angle) > 0.5:  # Only rotate if angle is significant
                (h, w) = cv_image.shape[:2]
                center = (w // 2, h // 2)
                M = cv2.getRotationMatrix2D(center, angle, 1.0)
                rotated = cv2.warpAffine(
                    cv_image,
                    M,
                    (w, h),
                    flags=cv2.INTER_CUBIC,
                    borderMode=cv2.BORDER_REPLICATE,
                )
                return Image.fromarray(rotated)
        except Exception as e:
            logger.warning(f"Deskewing failed: {e}")

        return image

    def _extract_zone(
        self, image: Image.Image, zone_config: OCRZoneConfig
    ) -> Image.Image:
        """Extract zone from image.

        Args:
            image: Full image
            zone_config: Zone configuration

        Returns:
            Cropped zone image
        """
        # Ensure coordinates are within image bounds
        x = max(0, min(zone_config.x, image.width - 1))
        y = max(0, min(zone_config.y, image.height - 1))
        x2 = max(x + 1, min(zone_config.x + zone_config.width, image.width))
        y2 = max(y + 1, min(zone_config.y + zone_config.height, image.height))

        return image.crop((x, y, x2, y2))

    def _select_engine(self, zone_config: OCRZoneConfig) -> str:
        """Select best OCR engine for the zone.

        Args:
            zone_config: Zone configuration

        Returns:
            Selected engine name
        """
        preferred_engine = zone_config.engine

        if preferred_engine == "auto":
            # Auto-select based on available engines and language
            if "tesseract" in self.available_engines:
                return "tesseract"
            elif "easyocr" in self.available_engines:
                return "easyocr"
            elif "paddleocr" in self.available_engines:
                return "paddleocr"
        elif preferred_engine in self.available_engines:
            return preferred_engine

        # Fallback to first available engine
        return self.available_engines[0] if self.available_engines else "none"

    def _ocr_with_tesseract(
        self, image: Image.Image, zone_config: OCRZoneConfig
    ) -> Tuple[str, float, List[BoundingBox]]:
        """Perform OCR with Tesseract.

        Args:
            image: Zone image
            zone_config: Zone configuration

        Returns:
            Tuple of (text, confidence, bounding_boxes)
        """
        try:
            # Get OCR data with bounding boxes
            data = pytesseract.image_to_data(
                image,
                lang=zone_config.language,
                config=self.config.tesseract_config.get("config", "--oem 3 --psm 6"),
                output_type=pytesseract.Output.DICT,
            )

            # Extract text and confidence
            texts = []
            confidences = []
            bounding_boxes = []

            for i in range(len(data["text"])):
                if int(data["conf"][i]) > 0:  # Valid detection
                    text = data["text"][i].strip()
                    if text:
                        texts.append(text)
                        confidences.append(float(data["conf"][i]) / 100.0)

                        # Create bounding box
                        bbox = BoundingBox(
                            x=int(data["left"][i]),
                            y=int(data["top"][i]),
                            width=int(data["width"][i]),
                            height=int(data["height"][i]),
                            confidence=float(data["conf"][i]) / 100.0,
                        )
                        bounding_boxes.append(bbox)

            # Combine results
            full_text = " ".join(texts)
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

            return full_text, avg_confidence, bounding_boxes

        except Exception as e:
            logger.error(f"Tesseract OCR failed: {e}")
            return "", 0.0, []

    def _ocr_with_easyocr(
        self, image: Image.Image, zone_config: OCRZoneConfig
    ) -> Tuple[str, float, List[BoundingBox]]:
        """Perform OCR with EasyOCR.

        Args:
            image: Zone image
            zone_config: Zone configuration

        Returns:
            Tuple of (text, confidence, bounding_boxes)
        """
        try:
            # Convert PIL to numpy array
            image_array = np.array(image)

            # Perform OCR
            results = self.easyocr_reader.readtext(image_array)

            texts = []
            confidences = []
            bounding_boxes = []

            for bbox_coords, text, confidence in results:
                if confidence > 0.1:  # Filter low confidence
                    texts.append(text)
                    confidences.append(confidence)

                    # Convert bbox coordinates
                    x_coords = [point[0] for point in bbox_coords]
                    y_coords = [point[1] for point in bbox_coords]

                    bbox = BoundingBox(
                        x=int(min(x_coords)),
                        y=int(min(y_coords)),
                        width=int(max(x_coords) - min(x_coords)),
                        height=int(max(y_coords) - min(y_coords)),
                        confidence=confidence,
                    )
                    bounding_boxes.append(bbox)

            # Combine results
            full_text = " ".join(texts)
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

            return full_text, avg_confidence, bounding_boxes

        except Exception as e:
            logger.error(f"EasyOCR failed: {e}")
            return "", 0.0, []

    def _ocr_with_paddleocr(
        self, image: Image.Image, zone_config: OCRZoneConfig
    ) -> Tuple[str, float, List[BoundingBox]]:
        """Perform OCR with PaddleOCR.

        Args:
            image: Zone image
            zone_config: Zone configuration

        Returns:
            Tuple of (text, confidence, bounding_boxes)
        """
        try:
            # Convert PIL to numpy array
            image_array = np.array(image)

            # Perform OCR
            results = self.paddleocr_reader.ocr(image_array, cls=True)

            texts = []
            confidences = []
            bounding_boxes = []

            if results and results[0]:
                for line in results[0]:
                    if line:
                        bbox_coords, (text, confidence) = line

                        if confidence > 0.1:  # Filter low confidence
                            texts.append(text)
                            confidences.append(confidence)

                            # Convert bbox coordinates
                            x_coords = [point[0] for point in bbox_coords]
                            y_coords = [point[1] for point in bbox_coords]

                            bbox = BoundingBox(
                                x=int(min(x_coords)),
                                y=int(min(y_coords)),
                                width=int(max(x_coords) - min(x_coords)),
                                height=int(max(y_coords) - min(y_coords)),
                                confidence=confidence,
                            )
                            bounding_boxes.append(bbox)

            # Combine results
            full_text = " ".join(texts)
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

            return full_text, avg_confidence, bounding_boxes

        except Exception as e:
            logger.error(f"PaddleOCR failed: {e}")
            return "", 0.0, []

    async def process_region(
        self,
        image_data: str,
        region: Any,
        language: str = "eng+deu",
        confidence_threshold: float = 0.7,
    ) -> Dict[str, Any]:
        """Process OCR on a region (convenience method for simple API calls).

        Args:
            image_data: Base64 encoded image data (with or without data URL prefix)
            region: Region object or dict with x, y, width, height
            language: OCR language code
            confidence_threshold: Confidence threshold

        Returns:
            OCR result dict
        """
        # Convert base64 to bytes
        if image_data.startswith("data:"):
            # Remove data URL prefix
            image_data = image_data.split(",", 1)[1]

        image_bytes = base64.b64decode(image_data)

        # Extract region coordinates (handle both dict and Pydantic model)
        if hasattr(region, "x"):
            # Pydantic model
            x, y, width, height = region.x, region.y, region.width, region.height
        else:
            # Dict
            x, y, width, height = (
                region["x"],
                region["y"],
                region["width"],
                region["height"],
            )

        # Create OCRZoneConfig from simple region dict
        zone_config = OCRZoneConfig(
            id="region",
            x=int(x),
            y=int(y),
            width=int(width),
            height=int(height),
            label="extracted_region",
            language=language,
            confidence_threshold=confidence_threshold,
        )

        # Process the zone
        result = await self.process_zone(image_bytes, zone_config, return_image=False)

        # Convert to simple dict format
        return {
            "text": result.text,
            "confidence": result.confidence,
            "processing_time": result.processing_time_ms,
            "engine": result.engine_used,
            "language": language,
            "error": result.error,
        }

    async def process_zone(
        self, image_data: bytes, zone_config: OCRZoneConfig, return_image: bool = False
    ) -> OCRZoneResult:
        """Process OCR on a single zone.

        Args:
            image_data: Image data as bytes
            zone_config: Zone configuration
            return_image: Whether to return processed image

        Returns:
            OCR zone result
        """
        start_time = time.time()

        # Check cache
        cache_key = self._get_cache_key(image_data, zone_config)
        if cache_key in self.cache:
            cached_result = self.cache[cache_key]
            logger.debug(f"OCR cache hit for zone {zone_config.id}")
            return cached_result

        try:
            # Load and extract zone
            image = Image.open(BytesIO(image_data))
            zone_image = self._extract_zone(image, zone_config)

            # Preprocess image
            processed_image = self._preprocess_image(
                zone_image, zone_config.preprocessing
            )

            # Select OCR engine
            engine = self._select_engine(zone_config)

            if engine == "none":
                raise Exception("No OCR engines available")

            # Perform OCR
            if engine == "tesseract":
                (
                    text,
                    confidence,
                    bboxes,
                ) = await asyncio.get_event_loop().run_in_executor(
                    self.executor,
                    self._ocr_with_tesseract,
                    processed_image,
                    zone_config,
                )
            elif engine == "easyocr":
                (
                    text,
                    confidence,
                    bboxes,
                ) = await asyncio.get_event_loop().run_in_executor(
                    self.executor, self._ocr_with_easyocr, processed_image, zone_config
                )
            elif engine == "paddleocr":
                (
                    text,
                    confidence,
                    bboxes,
                ) = await asyncio.get_event_loop().run_in_executor(
                    self.executor,
                    self._ocr_with_paddleocr,
                    processed_image,
                    zone_config,
                )
            else:
                raise Exception(f"Unknown OCR engine: {engine}")

            # Prepare processed image data if requested
            processed_image_data = None
            if return_image:
                buffer = BytesIO()
                processed_image.save(buffer, format="PNG")
                processed_image_data = base64.b64encode(buffer.getvalue()).decode(
                    "utf-8"
                )

            # Create result
            processing_time = int((time.time() - start_time) * 1000)

            result = OCRZoneResult(
                zone_id=zone_config.id,
                text=text,
                confidence=confidence,
                processing_time_ms=processing_time,
                engine_used=engine,
                bounding_boxes=bboxes,
                processed_image=processed_image_data,
                metadata={
                    "zone_size": f"{zone_config.width}x{zone_config.height}",
                    "preprocessing_applied": list(zone_config.preprocessing.keys()),
                    "language": zone_config.language,
                },
            )

            # Cache result (without processed image to save memory)
            if len(self.cache) < self.cache_max_size:
                cache_result = result.model_copy()
                cache_result.processed_image = None  # Don't cache images
                self.cache[cache_key] = cache_result

            logger.debug(
                f"OCR completed for zone {zone_config.id}: '{text[:50]}...' (confidence: {confidence:.2f})"
            )
            return result

        except Exception as e:
            processing_time = int((time.time() - start_time) * 1000)
            error_result = OCRZoneResult(
                zone_id=zone_config.id,
                text="",
                confidence=0.0,
                processing_time_ms=processing_time,
                engine_used="none",
                error=str(e),
            )
            logger.error(f"OCR failed for zone {zone_config.id}: {e}")
            return error_result

    async def process_multiple_zones(
        self, image_data: bytes, zones: List[OCRZoneConfig], return_images: bool = False
    ) -> List[OCRZoneResult]:
        """Process OCR on multiple zones in parallel.

        Args:
            image_data: Image data as bytes
            zones: List of zone configurations
            return_images: Whether to return processed images

        Returns:
            List of OCR zone results
        """
        if not zones:
            return []

        logger.info(f"Processing OCR for {len(zones)} zones")

        # Process zones in parallel
        tasks = [self.process_zone(image_data, zone, return_images) for zone in zones]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle exceptions
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                error_result = OCRZoneResult(
                    zone_id=zones[i].id,
                    text="",
                    confidence=0.0,
                    processing_time_ms=0,
                    engine_used="none",
                    error=str(result),
                )
                final_results.append(error_result)
            else:
                final_results.append(result)

        successful_results = [r for r in final_results if not r.error]
        logger.info(
            f"OCR completed: {len(successful_results)}/{len(zones)} zones successful"
        )

        return final_results

    def get_available_engines(self) -> List[str]:
        """Get list of available OCR engines.

        Returns:
            List of available engine names
        """
        return self.available_engines.copy()

    def get_supported_languages(self, engine: str = "tesseract") -> List[str]:
        """Get supported languages for an OCR engine.

        Args:
            engine: OCR engine name

        Returns:
            List of supported language codes
        """
        if engine == "tesseract" and TESSERACT_AVAILABLE:
            try:
                return pytesseract.get_languages()
            except Exception:
                return ["eng", "deu", "fra", "spa", "ita", "por"]
        elif engine == "easyocr":
            return ["en", "de", "fr", "es", "it", "pt", "ru", "ja", "ko", "zh"]
        elif engine == "paddleocr":
            return ["en", "ch", "ta", "te", "ka", "ja", "ko"]
        else:
            return ["eng"]

    def clear_cache(self) -> None:
        """Clear OCR result cache."""
        self.cache.clear()
        logger.info("OCR cache cleared")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics.

        Returns:
            Cache statistics dictionary
        """
        return {
            "cache_size": len(self.cache),
            "cache_max_size": self.cache_max_size,
            "available_engines": self.available_engines,
        }

    async def cleanup(self) -> None:
        """Cleanup resources."""
        self.executor.shutdown(wait=True)
        self.clear_cache()
        logger.info(" OCR Service cleaned up")


# ============================================================================
# GLOBAL SERVICE INSTANCE
# ============================================================================

_ocr_service: Optional[OCRService] = None


def get_ocr_service() -> OCRService:
    """Get or create OCR service instance.

    Returns:
        OCRService instance
    """
    global _ocr_service
    if _ocr_service is None:
        _ocr_service = OCRService()
    return _ocr_service


async def cleanup_ocr_service() -> None:
    """Cleanup global OCR service."""
    global _ocr_service
    if _ocr_service:
        await _ocr_service.cleanup()
        _ocr_service = None
        logger.info("Global OCR service cleaned up")
