"""
OCRFallback — Capture a screen region and extract text via Tesseract OCR.

Used when UIA inspection returns no useful element (e.g. games, remote
desktop sessions, custom-rendered canvases).
"""

import logging
from typing import Optional

from .element_context import UIElementContext

logger = logging.getLogger(__name__)

try:
    import pyautogui
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False

try:
    import pytesseract
    HAS_PYTESSERACT = True
except ImportError:
    HAS_PYTESSERACT = False


class OCRFallback:
    """
    Screenshot a region around a point and run Tesseract OCR to extract text.

    Returns a simplified :class:`UIElementContext` with
    ``source="ocr_fallback"`` and ``control_type="Unknown"``.

    Usage::

        ocr = OCRFallback()
        ctx = ocr.element_at_point(500, 300)
        if ctx:
            print(ctx.text_content)
    """

    def __init__(self, tesseract_cmd: Optional[str] = None):
        """
        Parameters
        ----------
        tesseract_cmd : str, optional
            Path to the Tesseract executable. If provided, overrides the
            default pytesseract lookup.
        """
        if not HAS_PYAUTOGUI:
            raise RuntimeError("pyautogui is required for OCRFallback. Install with: pip install pyautogui")
        if not HAS_PYTESSERACT:
            raise RuntimeError("pytesseract is required for OCRFallback. Install with: pip install pytesseract")

        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    def element_at_point(
        self, x: int, y: int, radius: int = 100
    ) -> Optional[UIElementContext]:
        """Capture a square region around *(x, y)* and OCR the text.

        Parameters
        ----------
        x, y : int
            Screen coordinates (center of the capture region).
        radius : int
            Half-width of the capture square in pixels. The captured area
            will be ``2 * radius`` on each side, clamped to screen bounds.

        Returns
        -------
        UIElementContext or None
            A context with extracted text, or ``None`` if OCR produced no
            readable output.
        """
        try:
            # Determine screen size for clamping
            screen_w, screen_h = pyautogui.size()

            left = max(0, x - radius)
            top = max(0, y - radius)
            right = min(screen_w, x + radius)
            bottom = min(screen_h, y + radius)
            width = right - left
            height = bottom - top

            if width <= 0 or height <= 0:
                logger.debug("OCR region has zero area at (%s, %s)", x, y)
                return None

            # Capture the region
            screenshot = pyautogui.screenshot(region=(left, top, width, height))

            # Run Tesseract OCR
            text = pytesseract.image_to_string(screenshot).strip()

            if not text:
                logger.debug("OCR returned empty text at (%s, %s)", x, y)
                return None

            # Truncate to avoid memory issues
            text = text[:500]

            return UIElementContext(
                app_name="",
                window_title="",
                control_type="Unknown",
                element_name="",
                automation_id="",
                text_content=text,
                bounding_box=(left, top, width, height),
                source="ocr_fallback",
            )

        except Exception:
            logger.warning("OCR fallback failed at (%s, %s)", x, y, exc_info=True)
            return None
