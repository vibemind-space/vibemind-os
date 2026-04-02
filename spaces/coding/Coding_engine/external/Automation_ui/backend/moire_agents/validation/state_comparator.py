"""
State Comparator - Vergleicht Bildschirmzustände

Verwendet:
- Pixel-basierte Differenz
- OCR-Text Vergleich
- Element-Position Vergleich
"""

import asyncio
import logging
import time
import hashlib
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from enum import Enum

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Optionale Imports
try:
    from PIL import Image
    import io
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logger.warning("PIL not available - image comparison limited")

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    logger.warning("NumPy not available - image comparison limited")


class ChangeType(Enum):
    """Art der Bildschirmänderung."""
    NO_CHANGE = "no_change"
    MINOR_CHANGE = "minor_change"  # < 5% der Pixel
    SIGNIFICANT_CHANGE = "significant_change"  # 5-30%
    MAJOR_CHANGE = "major_change"  # > 30%
    NEW_WINDOW = "new_window"
    WINDOW_CLOSED = "window_closed"
    TEXT_CHANGED = "text_changed"
    ELEMENT_APPEARED = "element_appeared"
    ELEMENT_DISAPPEARED = "element_disappeared"


@dataclass
class ScreenState:
    """Repräsentation eines Bildschirmzustands."""
    timestamp: float
    screenshot_hash: str
    screenshot_data: Optional[bytes] = None
    elements: List[Dict[str, Any]] = field(default_factory=list)
    ocr_text: List[str] = field(default_factory=list)
    window_title: Optional[str] = None
    dimensions: Tuple[int, int] = (1920, 1080)
    
    @classmethod
    def from_screenshot(
        cls,
        screenshot_data: bytes,
        elements: Optional[List[Dict[str, Any]]] = None,
        ocr_text: Optional[List[str]] = None,
        window_title: Optional[str] = None
    ) -> 'ScreenState':
        """Erstellt ScreenState aus Screenshot-Bytes."""
        screenshot_hash = hashlib.md5(screenshot_data).hexdigest()
        
        dimensions = (1920, 1080)
        if PIL_AVAILABLE:
            try:
                img = Image.open(io.BytesIO(screenshot_data))
                dimensions = img.size
            except:
                pass
        
        return cls(
            timestamp=time.time(),
            screenshot_hash=screenshot_hash,
            screenshot_data=screenshot_data,
            elements=elements or [],
            ocr_text=ocr_text or [],
            window_title=window_title,
            dimensions=dimensions
        )


@dataclass
class ComparisonResult:
    """Ergebnis eines Bildschirmvergleichs."""
    changed: bool
    change_type: ChangeType
    change_percentage: float
    description: str
    changed_regions: List[Dict[str, Any]] = field(default_factory=list)
    new_elements: List[Dict[str, Any]] = field(default_factory=list)
    removed_elements: List[Dict[str, Any]] = field(default_factory=list)
    text_changes: List[Tuple[str, str]] = field(default_factory=list)


class StateComparator:
    """
    Vergleicht zwei Bildschirmzustände.
    
    Methoden:
    - Pixel-basierte Differenz (schnell)
    - Element-Vergleich (semantisch)
    - OCR-Text Vergleich
    """
    
    def __init__(
        self,
        minor_threshold: float = 0.05,  # 5% für minor change
        significant_threshold: float = 0.30,  # 30% für major change
        use_gpu: bool = False
    ):
        self.minor_threshold = minor_threshold
        self.significant_threshold = significant_threshold
        self.use_gpu = use_gpu
        
        # State History
        self.state_history: List[ScreenState] = []
        self.max_history = 50
    
    def compare(
        self,
        state1: ScreenState,
        state2: ScreenState
    ) -> ComparisonResult:
        """
        Vergleicht zwei Bildschirmzustände.
        
        Args:
            state1: Vorheriger Zustand
            state2: Aktueller Zustand
        
        Returns:
            ComparisonResult
        """
        # Schneller Hash-Vergleich
        if state1.screenshot_hash == state2.screenshot_hash:
            return ComparisonResult(
                changed=False,
                change_type=ChangeType.NO_CHANGE,
                change_percentage=0.0,
                description="Keine Änderung erkannt (identische Screenshots)"
            )
        
        # Pixel-basierter Vergleich
        change_percentage = 0.0
        changed_regions = []
        
        if state1.screenshot_data and state2.screenshot_data and PIL_AVAILABLE and NUMPY_AVAILABLE:
            change_percentage, changed_regions = self._compare_pixels(
                state1.screenshot_data,
                state2.screenshot_data
            )
        
        # Element-Vergleich
        new_elements, removed_elements = self._compare_elements(
            state1.elements,
            state2.elements
        )
        
        # Text-Vergleich
        text_changes = self._compare_text(
            state1.ocr_text,
            state2.ocr_text
        )
        
        # Bestimme Change-Type
        change_type = self._determine_change_type(
            change_percentage,
            new_elements,
            removed_elements,
            text_changes,
            state1.window_title,
            state2.window_title
        )
        
        # Erstelle Beschreibung
        description = self._create_description(
            change_type,
            change_percentage,
            new_elements,
            removed_elements,
            text_changes
        )
        
        return ComparisonResult(
            changed=change_type != ChangeType.NO_CHANGE,
            change_type=change_type,
            change_percentage=change_percentage,
            description=description,
            changed_regions=changed_regions,
            new_elements=new_elements,
            removed_elements=removed_elements,
            text_changes=text_changes
        )
    
    def _compare_pixels(
        self,
        data1: bytes,
        data2: bytes
    ) -> Tuple[float, List[Dict[str, Any]]]:
        """Pixel-basierter Vergleich."""
        try:
            img1 = Image.open(io.BytesIO(data1)).convert('RGB')
            img2 = Image.open(io.BytesIO(data2)).convert('RGB')
            
            # Gleiche Größe sicherstellen
            if img1.size != img2.size:
                img2 = img2.resize(img1.size)
            
            # Zu NumPy Arrays
            arr1 = np.array(img1)
            arr2 = np.array(img2)
            
            # Differenz berechnen
            diff = np.abs(arr1.astype(np.int16) - arr2.astype(np.int16))
            
            # Threshold für signifikante Änderung (> 30 pro Kanal)
            significant_diff = (diff > 30).any(axis=2)
            
            # Prozent der geänderten Pixel
            change_percentage = significant_diff.mean()
            
            # Finde geänderte Regionen (vereinfacht)
            changed_regions = []
            if change_percentage > 0.01:  # Mindestens 1% Änderung
                # Teile Bild in Quadranten
                h, w = significant_diff.shape
                quadrants = [
                    ("top_left", 0, 0, h//2, w//2),
                    ("top_right", 0, w//2, h//2, w),
                    ("bottom_left", h//2, 0, h, w//2),
                    ("bottom_right", h//2, w//2, h, w)
                ]
                
                for name, y1, x1, y2, x2 in quadrants:
                    quadrant_change = significant_diff[y1:y2, x1:x2].mean()
                    if quadrant_change > 0.05:  # 5% Änderung im Quadrant
                        changed_regions.append({
                            "region": name,
                            "change_percentage": float(quadrant_change),
                            "bounds": {"x": x1, "y": y1, "width": x2-x1, "height": y2-y1}
                        })
            
            return float(change_percentage), changed_regions

        except Exception as e:
            logger.error(f"Pixel comparison failed: {e}")
            return 0.5, []  # Assume change on error

    def _crop_to_roi(self, screenshot_data: bytes, roi: Dict[str, Any]) -> bytes:
        """
        Croppt Screenshot auf ROI-Bereich.

        Args:
            screenshot_data: Screenshot als bytes
            roi: ROI dict mit origin_x, origin_y, base_width, base_height, zoom

        Returns:
            Gecroppter Screenshot als bytes
        """
        if not PIL_AVAILABLE:
            logger.warning("PIL not available for ROI cropping")
            return screenshot_data

        try:
            # Berechne Bounds mit Zoom
            zoom = roi.get("zoom", 1.5)
            base_w = roi.get("base_width", 150)
            base_h = roi.get("base_height", 60)
            origin_x = roi.get("origin_x", 0)
            origin_y = roi.get("origin_y", 0)

            scaled_w = int(base_w * zoom)
            scaled_h = int(base_h * zoom)

            x1 = max(0, origin_x - scaled_w // 2)
            y1 = max(0, origin_y - scaled_h // 2)
            x2 = x1 + scaled_w
            y2 = y1 + scaled_h

            # Bild öffnen und croppen
            img = Image.open(io.BytesIO(screenshot_data))

            # Bounds an Bildgröße anpassen
            x2 = min(x2, img.width)
            y2 = min(y2, img.height)

            cropped = img.crop((x1, y1, x2, y2))

            # Als bytes zurückgeben
            buffer = io.BytesIO()
            cropped.save(buffer, format='PNG')
            return buffer.getvalue()

        except Exception as e:
            logger.error(f"ROI cropping failed: {e}")
            return screenshot_data

    def compare_with_roi(
        self,
        before_data: bytes,
        after_data: bytes,
        roi: Dict[str, Any]
    ) -> ComparisonResult:
        """
        Vergleicht nur ROI-Bereiche zweier Screenshots.

        Args:
            before_data: Screenshot vor der Aktion
            after_data: Screenshot nach der Aktion
            roi: ROI dict mit origin_x, origin_y, base_width, base_height, zoom

        Returns:
            ComparisonResult
        """
        # Croppe beide Screenshots auf ROI
        before_roi = self._crop_to_roi(before_data, roi)
        after_roi = self._crop_to_roi(after_data, roi)

        # Erstelle States für Vergleich
        before_state = ScreenState.from_screenshot(before_roi)
        after_state = ScreenState.from_screenshot(after_roi)

        # Nutze bestehende compare() Methode mit angepassten Thresholds
        # Speichere alte Thresholds
        old_minor = self.minor_threshold
        old_significant = self.significant_threshold

        # Niedrigere Schwellwerte für kleine ROI-Bereiche
        # (kleine Änderungen sind in ROIs signifikanter)
        self.minor_threshold = 0.01  # 1% statt 5%
        self.significant_threshold = 0.10  # 10% statt 30%

        try:
            result = self.compare(before_state, after_state)

            # ROI-Info zur Beschreibung hinzufügen
            roi_desc = f"ROI({roi.get('origin_x', 0)}, {roi.get('origin_y', 0)}) zoom={roi.get('zoom', 1.5)}"
            result.description = f"[{roi_desc}] {result.description}"

            return result
        finally:
            # Thresholds wiederherstellen
            self.minor_threshold = old_minor
            self.significant_threshold = old_significant

    def _compare_elements(
        self,
        elements1: List[Dict[str, Any]],
        elements2: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Vergleicht UI-Elemente."""
        # Erstelle Sets basierend auf Text und ungefährer Position
        def element_key(el: Dict[str, Any]) -> str:
            text = el.get('text', '')
            x = el.get('x', 0) // 50  # Gruppiere in 50px Buckets
            y = el.get('y', 0) // 50
            return f"{text}_{x}_{y}"
        
        keys1 = {element_key(el): el for el in elements1}
        keys2 = {element_key(el): el for el in elements2}
        
        new_elements = [keys2[k] for k in keys2 if k not in keys1]
        removed_elements = [keys1[k] for k in keys1 if k not in keys2]
        
        return new_elements, removed_elements
    
    def _compare_text(
        self,
        text1: List[str],
        text2: List[str]
    ) -> List[Tuple[str, str]]:
        """Vergleicht OCR-Text."""
        changes = []
        
        set1 = set(text1)
        set2 = set(text2)
        
        # Neuer Text
        for t in set2 - set1:
            changes.append(("", t))  # Neu erschienen
        
        # Verschwundener Text
        for t in set1 - set2:
            changes.append((t, ""))  # Verschwunden
        
        return changes
    
    def _determine_change_type(
        self,
        change_percentage: float,
        new_elements: List[Dict[str, Any]],
        removed_elements: List[Dict[str, Any]],
        text_changes: List[Tuple[str, str]],
        title1: Optional[str],
        title2: Optional[str]
    ) -> ChangeType:
        """Bestimmt den Typ der Änderung."""
        # Fenster-Änderungen
        if title1 != title2:
            if title2 and not title1:
                return ChangeType.NEW_WINDOW
            if title1 and not title2:
                return ChangeType.WINDOW_CLOSED
        
        # Element-basierte Änderungen
        if len(new_elements) > 5:
            return ChangeType.ELEMENT_APPEARED
        if len(removed_elements) > 5:
            return ChangeType.ELEMENT_DISAPPEARED
        
        # Text-Änderungen
        if len(text_changes) > 3:
            return ChangeType.TEXT_CHANGED
        
        # Pixel-basierte Änderungen
        if change_percentage < 0.01:
            return ChangeType.NO_CHANGE
        elif change_percentage < self.minor_threshold:
            return ChangeType.MINOR_CHANGE
        elif change_percentage < self.significant_threshold:
            return ChangeType.SIGNIFICANT_CHANGE
        else:
            return ChangeType.MAJOR_CHANGE
    
    def _create_description(
        self,
        change_type: ChangeType,
        change_percentage: float,
        new_elements: List[Dict[str, Any]],
        removed_elements: List[Dict[str, Any]],
        text_changes: List[Tuple[str, str]]
    ) -> str:
        """Erstellt eine lesbare Beschreibung der Änderungen."""
        parts = []
        
        if change_type == ChangeType.NO_CHANGE:
            return "Keine sichtbare Änderung"
        
        if change_type == ChangeType.NEW_WINDOW:
            return "Neues Fenster geöffnet"
        
        if change_type == ChangeType.WINDOW_CLOSED:
            return "Fenster geschlossen"
        
        parts.append(f"{change_percentage*100:.1f}% des Bildschirms geändert")
        
        if new_elements:
            texts = [el.get('text', 'Element') for el in new_elements[:3]]
            parts.append(f"Neue Elemente: {', '.join(texts)}")
        
        if removed_elements:
            texts = [el.get('text', 'Element') for el in removed_elements[:3]]
            parts.append(f"Entfernte Elemente: {', '.join(texts)}")
        
        if text_changes:
            new_texts = [t[1] for t in text_changes if t[1]][:3]
            if new_texts:
                parts.append(f"Neuer Text: {', '.join(new_texts)}")
        
        return "; ".join(parts)
    
    def add_to_history(self, state: ScreenState):
        """Fügt Zustand zur Historie hinzu."""
        self.state_history.append(state)
        if len(self.state_history) > self.max_history:
            self.state_history = self.state_history[-self.max_history:]
    
    def get_last_state(self) -> Optional[ScreenState]:
        """Gibt letzten Zustand zurück."""
        return self.state_history[-1] if self.state_history else None
    
    def has_state_changed_since(
        self,
        reference_state: ScreenState,
        current_data: bytes,
        current_elements: Optional[List[Dict[str, Any]]] = None
    ) -> ComparisonResult:
        """Prüft ob sich der Zustand seit einem Referenzzustand geändert hat."""
        current_state = ScreenState.from_screenshot(
            current_data,
            elements=current_elements
        )
        return self.compare(reference_state, current_state)


# Singleton
_comparator_instance: Optional[StateComparator] = None


def get_state_comparator() -> StateComparator:
    """Gibt Singleton-Instanz des StateComparators zurück."""
    global _comparator_instance
    if _comparator_instance is None:
        _comparator_instance = StateComparator()
    return _comparator_instance