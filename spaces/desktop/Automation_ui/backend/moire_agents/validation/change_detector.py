"""
Change Detector - Precise bounding box detection for screen changes.

Uses connected component analysis to detect WHERE changes occurred,
replacing quadrant-based detection with pixel-accurate bounding boxes.

Usage:
    from validation.change_detector import ChangeDetector, ChangeRegion

    detector = ChangeDetector()
    regions = detector.detect_changes(before_bytes, after_bytes)

    for region in regions:
        print(f"Change at {region.bounds}: {region.intensity}")
"""

import io
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


class ChangeIntensity(Enum):
    """Intensity level of a detected change."""
    LOW = "low"        # < 30% pixels changed in region
    MEDIUM = "medium"  # 30-60% pixels changed
    HIGH = "high"      # > 60% pixels changed


@dataclass
class ChangeRegion:
    """Precise bounding box of a changed area."""
    id: int
    bounds: Dict[str, int]  # {x, y, width, height}
    centroid: Dict[str, int]  # {x, y}
    change_percentage: float  # Percentage of pixels changed in this region
    pixel_count: int  # Total pixels in region
    changed_pixels: int  # Number of changed pixels
    intensity: ChangeIntensity

    @property
    def area(self) -> int:
        """Total area of the bounding box."""
        return self.bounds["width"] * self.bounds["height"]

    @property
    def x(self) -> int:
        return self.bounds["x"]

    @property
    def y(self) -> int:
        return self.bounds["y"]

    @property
    def width(self) -> int:
        return self.bounds["width"]

    @property
    def height(self) -> int:
        return self.bounds["height"]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "bounds": self.bounds,
            "centroid": self.centroid,
            "change_percentage": self.change_percentage,
            "pixel_count": self.pixel_count,
            "changed_pixels": self.changed_pixels,
            "intensity": self.intensity.value,
            "area": self.area
        }


@dataclass
class ChangeDetectionResult:
    """Result of change detection between two screenshots."""
    changed: bool
    total_change_percentage: float
    regions: List[ChangeRegion] = field(default_factory=list)
    diff_image: Optional[bytes] = None  # Binary difference image
    annotated_image: Optional[bytes] = None  # Screenshot with overlays

    @property
    def region_count(self) -> int:
        return len(self.regions)

    @property
    def high_intensity_count(self) -> int:
        return sum(1 for r in self.regions if r.intensity == ChangeIntensity.HIGH)


class ChangeDetector:
    """
    Detects precise change regions using connected components.

    Replaces quadrant-based detection with pixel-accurate bounding boxes.
    Uses scipy.ndimage for connected component labeling when available,
    falls back to pure numpy implementation otherwise.
    """

    def __init__(
        self,
        threshold: int = 30,
        min_region_size: int = 100,
        merge_distance: int = 20
    ):
        """
        Initialize the ChangeDetector.

        Args:
            threshold: Pixel difference threshold (0-255) to consider as changed
            min_region_size: Minimum pixels for a region to be included
            merge_distance: Merge regions closer than this distance
        """
        self.threshold = threshold
        self.min_region_size = min_region_size
        self.merge_distance = merge_distance

        # Try to import scipy for connected components
        try:
            from scipy import ndimage
            self._label_func = ndimage.label
            self._find_objects = ndimage.find_objects
            self._has_scipy = True
            logger.debug("Using scipy for connected component analysis")
        except ImportError:
            self._has_scipy = False
            logger.debug("scipy not available, using fallback implementation")

    def detect_changes(
        self,
        before: bytes,
        after: bytes,
        return_diff_image: bool = False
    ) -> ChangeDetectionResult:
        """
        Detect precise change regions between two screenshots.

        Args:
            before: Screenshot bytes before action
            after: Screenshot bytes after action
            return_diff_image: If True, include binary diff image in result

        Returns:
            ChangeDetectionResult with list of ChangeRegion objects
        """
        try:
            # Convert bytes to PIL Images
            before_img = Image.open(io.BytesIO(before)).convert("RGB")
            after_img = Image.open(io.BytesIO(after)).convert("RGB")

            # Ensure same size
            if before_img.size != after_img.size:
                logger.warning(f"Image size mismatch: {before_img.size} vs {after_img.size}")
                # Resize to smaller
                min_size = (
                    min(before_img.size[0], after_img.size[0]),
                    min(before_img.size[1], after_img.size[1])
                )
                before_img = before_img.resize(min_size)
                after_img = after_img.resize(min_size)

            # Convert to numpy arrays
            before_arr = np.array(before_img, dtype=np.int16)
            after_arr = np.array(after_img, dtype=np.int16)

            # Compute absolute difference per channel
            diff = np.abs(after_arr - before_arr)

            # Max difference across channels
            max_diff = np.max(diff, axis=2)

            # Create binary mask (changed = 1, unchanged = 0)
            binary_mask = (max_diff > self.threshold).astype(np.uint8)

            # Calculate total change percentage
            total_pixels = binary_mask.size
            changed_pixels = np.sum(binary_mask)
            total_change_pct = (changed_pixels / total_pixels) * 100

            # If no significant change, return early
            if changed_pixels < self.min_region_size:
                return ChangeDetectionResult(
                    changed=False,
                    total_change_percentage=total_change_pct,
                    regions=[]
                )

            # Find connected components
            regions = self._find_regions(binary_mask, max_diff)

            # Create diff image if requested
            diff_image = None
            if return_diff_image:
                diff_image = self._create_diff_image(binary_mask)

            return ChangeDetectionResult(
                changed=len(regions) > 0,
                total_change_percentage=total_change_pct,
                regions=regions,
                diff_image=diff_image
            )

        except Exception as e:
            logger.error(f"Error detecting changes: {e}")
            return ChangeDetectionResult(
                changed=False,
                total_change_percentage=0,
                regions=[]
            )

    def _find_regions(
        self,
        binary_mask: np.ndarray,
        intensity_map: np.ndarray
    ) -> List[ChangeRegion]:
        """
        Find connected components and create ChangeRegion objects.

        Args:
            binary_mask: Binary mask of changed pixels
            intensity_map: Grayscale intensity of changes

        Returns:
            List of ChangeRegion objects
        """
        if self._has_scipy:
            return self._find_regions_scipy(binary_mask, intensity_map)
        else:
            return self._find_regions_fallback(binary_mask, intensity_map)

    def _find_regions_scipy(
        self,
        binary_mask: np.ndarray,
        intensity_map: np.ndarray
    ) -> List[ChangeRegion]:
        """Find regions using scipy connected components."""
        from scipy import ndimage

        # Label connected components
        labeled, num_features = ndimage.label(binary_mask)

        if num_features == 0:
            return []

        regions = []

        # Find bounding box for each component
        slices = ndimage.find_objects(labeled)

        for i, slc in enumerate(slices):
            if slc is None:
                continue

            region_id = i + 1

            # Extract region mask
            region_mask = (labeled[slc] == region_id)
            changed_pixels = np.sum(region_mask)

            # Skip small regions
            if changed_pixels < self.min_region_size:
                continue

            # Calculate bounds
            y_slice, x_slice = slc
            x = x_slice.start
            y = y_slice.start
            width = x_slice.stop - x_slice.start
            height = y_slice.stop - y_slice.start

            # Calculate centroid
            y_coords, x_coords = np.where(region_mask)
            centroid_x = int(x + np.mean(x_coords))
            centroid_y = int(y + np.mean(y_coords))

            # Calculate intensity
            region_intensity = intensity_map[slc][region_mask]
            avg_intensity = np.mean(region_intensity)
            change_pct = (avg_intensity / 255) * 100

            # Classify intensity
            if change_pct > 60:
                intensity = ChangeIntensity.HIGH
            elif change_pct > 30:
                intensity = ChangeIntensity.MEDIUM
            else:
                intensity = ChangeIntensity.LOW

            regions.append(ChangeRegion(
                id=region_id,
                bounds={"x": x, "y": y, "width": width, "height": height},
                centroid={"x": centroid_x, "y": centroid_y},
                change_percentage=change_pct,
                pixel_count=width * height,
                changed_pixels=int(changed_pixels),
                intensity=intensity
            ))

        # Sort by area (largest first)
        regions.sort(key=lambda r: r.area, reverse=True)

        return regions

    def _find_regions_fallback(
        self,
        binary_mask: np.ndarray,
        intensity_map: np.ndarray
    ) -> List[ChangeRegion]:
        """
        Fallback region detection without scipy.

        Uses simple row/column scanning to find rectangular regions.
        Less accurate than connected components but works without scipy.
        """
        regions = []
        height, width = binary_mask.shape

        # Find rows and columns with changes
        row_changes = np.any(binary_mask, axis=1)
        col_changes = np.any(binary_mask, axis=0)

        # Find contiguous blocks of changed rows
        row_blocks = self._find_contiguous_blocks(row_changes)
        col_blocks = self._find_contiguous_blocks(col_changes)

        region_id = 0
        for row_start, row_end in row_blocks:
            for col_start, col_end in col_blocks:
                # Check if this block actually has changes
                block_mask = binary_mask[row_start:row_end, col_start:col_end]
                changed_pixels = np.sum(block_mask)

                if changed_pixels < self.min_region_size:
                    continue

                region_id += 1
                x = col_start
                y = row_start
                w = col_end - col_start
                h = row_end - row_start

                # Calculate intensity
                block_intensity = intensity_map[row_start:row_end, col_start:col_end]
                avg_intensity = np.mean(block_intensity[block_mask > 0])
                change_pct = (avg_intensity / 255) * 100

                if change_pct > 60:
                    intensity = ChangeIntensity.HIGH
                elif change_pct > 30:
                    intensity = ChangeIntensity.MEDIUM
                else:
                    intensity = ChangeIntensity.LOW

                regions.append(ChangeRegion(
                    id=region_id,
                    bounds={"x": x, "y": y, "width": w, "height": h},
                    centroid={"x": x + w // 2, "y": y + h // 2},
                    change_percentage=change_pct,
                    pixel_count=w * h,
                    changed_pixels=int(changed_pixels),
                    intensity=intensity
                ))

        # Sort by area
        regions.sort(key=lambda r: r.area, reverse=True)

        return regions

    def _find_contiguous_blocks(
        self,
        arr: np.ndarray
    ) -> List[Tuple[int, int]]:
        """Find contiguous blocks of True values in a 1D array."""
        blocks = []
        in_block = False
        start = 0

        for i, val in enumerate(arr):
            if val and not in_block:
                # Start of new block
                start = i
                in_block = True
            elif not val and in_block:
                # End of block
                blocks.append((start, i))
                in_block = False

        # Handle block at end
        if in_block:
            blocks.append((start, len(arr)))

        return blocks

    def _create_diff_image(self, binary_mask: np.ndarray) -> bytes:
        """Create a binary difference image."""
        diff_img = Image.fromarray((binary_mask * 255).astype(np.uint8), mode="L")
        buffer = io.BytesIO()
        diff_img.save(buffer, format="PNG")
        return buffer.getvalue()

    def annotate_screenshot(
        self,
        screenshot: bytes,
        regions: List[ChangeRegion],
        style: str = "boxes"
    ) -> bytes:
        """
        Draw bounding boxes on screenshot for visual feedback.

        Args:
            screenshot: Screenshot bytes to annotate
            regions: List of ChangeRegion objects
            style: Annotation style ("boxes", "fill", "outline")

        Returns:
            Annotated screenshot as PNG bytes
        """
        try:
            img = Image.open(io.BytesIO(screenshot)).convert("RGBA")
            draw = ImageDraw.Draw(img, "RGBA")

            # Color map based on intensity
            colors = {
                ChangeIntensity.HIGH: (255, 0, 0, 180),     # Red
                ChangeIntensity.MEDIUM: (255, 165, 0, 150), # Orange
                ChangeIntensity.LOW: (255, 255, 0, 120),    # Yellow
            }

            for region in regions:
                color = colors.get(region.intensity, (128, 128, 128, 100))
                x, y = region.x, region.y
                x2, y2 = x + region.width, y + region.height

                if style == "fill":
                    # Semi-transparent fill
                    draw.rectangle([x, y, x2, y2], fill=color)
                elif style == "outline":
                    # Thick outline only
                    outline_color = color[:3] + (255,)  # Solid outline
                    draw.rectangle([x, y, x2, y2], outline=outline_color, width=3)
                else:  # boxes (default)
                    # Semi-transparent fill with solid outline
                    fill_color = color[:3] + (60,)  # Light fill
                    outline_color = color[:3] + (255,)  # Solid outline
                    draw.rectangle([x, y, x2, y2], fill=fill_color, outline=outline_color, width=2)

                # Add region label
                label = f"R{region.id}: {region.change_percentage:.0f}%"
                draw.text((x + 5, y + 5), label, fill=(255, 255, 255, 255))

            # Convert back to bytes
            buffer = io.BytesIO()
            img.convert("RGB").save(buffer, format="PNG")
            return buffer.getvalue()

        except Exception as e:
            logger.error(f"Error annotating screenshot: {e}")
            return screenshot  # Return original on error

    def generate_diff_overlay(
        self,
        before: bytes,
        after: bytes,
        regions: List[ChangeRegion]
    ) -> bytes:
        """
        Generate visual overlay showing change intensity.

        Creates a heatmap-style overlay where:
        - Red = High intensity change
        - Orange = Medium intensity
        - Yellow = Low intensity
        - Green = No change
        """
        try:
            # Load after image as base
            after_img = Image.open(io.BytesIO(after)).convert("RGBA")
            before_img = Image.open(io.BytesIO(before)).convert("RGB")

            # Create difference heatmap
            before_arr = np.array(before_img, dtype=np.int16)
            after_arr = np.array(Image.open(io.BytesIO(after)).convert("RGB"), dtype=np.int16)

            diff = np.abs(after_arr - before_arr)
            max_diff = np.max(diff, axis=2)

            # Create heatmap overlay
            heatmap = np.zeros((max_diff.shape[0], max_diff.shape[1], 4), dtype=np.uint8)

            # Color based on intensity
            heatmap[max_diff > 150] = [255, 0, 0, 150]      # High = Red
            heatmap[(max_diff > 50) & (max_diff <= 150)] = [255, 165, 0, 120]  # Medium = Orange
            heatmap[(max_diff > self.threshold) & (max_diff <= 50)] = [255, 255, 0, 80]  # Low = Yellow

            # Create overlay image
            overlay = Image.fromarray(heatmap, mode="RGBA")

            # Composite
            result = Image.alpha_composite(after_img, overlay)

            # Convert to bytes
            buffer = io.BytesIO()
            result.convert("RGB").save(buffer, format="PNG")
            return buffer.getvalue()

        except Exception as e:
            logger.error(f"Error generating diff overlay: {e}")
            return after


# Convenience function
def detect_changes(
    before: bytes,
    after: bytes,
    threshold: int = 30,
    min_region_size: int = 100
) -> ChangeDetectionResult:
    """
    Convenience function to detect changes between screenshots.

    Args:
        before: Screenshot bytes before action
        after: Screenshot bytes after action
        threshold: Pixel difference threshold
        min_region_size: Minimum region size in pixels

    Returns:
        ChangeDetectionResult with regions
    """
    detector = ChangeDetector(threshold=threshold, min_region_size=min_region_size)
    return detector.detect_changes(before, after)
