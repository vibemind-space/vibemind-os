"""
Data Analyst Agent - Analysiert und strukturiert UI-Daten

Verantwortlich für:
- OCR-Daten in verständlichen Kontext umwandeln
- UI-Elemente kategorisieren und gruppieren
- Semantische Labels basierend auf Text zuweisen
- Aktionsvorschläge aus UI-Struktur ableiten
- CSV-Daten mergen und aufbereiten
- Bei Hard Cases: Vision Agent einbeziehen
"""

import logging
import os
import csv
import asyncio
from typing import Optional, Dict, Any, List, Tuple, TYPE_CHECKING
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import re
import time

if TYPE_CHECKING:
    from ..bridge.websocket_client import MoireWebSocketClient, CaptureResult, UIContext

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class UIElementType(Enum):
    """Typen von UI-Elementen basierend auf Heuristiken."""
    BUTTON = "button"
    TEXTFIELD = "textfield"
    LABEL = "label"
    ICON = "icon"
    MENU = "menu"
    MENUITEM = "menuitem"
    TAB = "tab"
    CHECKBOX = "checkbox"
    DROPDOWN = "dropdown"
    LINK = "link"
    TITLE = "title"
    TOOLBAR = "toolbar"
    STATUSBAR = "statusbar"
    UNKNOWN = "unknown"


@dataclass
class AnalyzedElement:
    """Ein analysiertes UI-Element mit semantischen Informationen."""
    id: str
    type: UIElementType
    text: Optional[str]
    bounds: Dict[str, int]
    center: Tuple[int, int]
    confidence: float
    
    # Semantische Analyse
    semantic_type: Optional[str] = None
    actionable: bool = False
    action_type: Optional[str] = None  # click, type, select, etc.
    related_elements: List[str] = field(default_factory=list)
    
    # Kontext
    region_id: Optional[int] = None
    line_id: Optional[int] = None
    probable_function: Optional[str] = None


@dataclass
class UIScreenContext:
    """Strukturierter Kontext eines Bildschirms."""
    timestamp: int
    application: Optional[str]
    window_title: Optional[str]
    current_view: Optional[str]
    
    # Bereiche
    toolbar_elements: List[AnalyzedElement]
    menu_elements: List[AnalyzedElement]
    content_elements: List[AnalyzedElement]
    statusbar_elements: List[AnalyzedElement]
    
    # Aktionen
    available_actions: List[Dict[str, Any]]
    
    # Zusammenfassung
    summary: str
    element_count: int
    text_element_count: int


@dataclass
class MergedCSVData:
    """Gemergede Daten aus allen CSV-Dateien."""
    boxes: List[Dict[str, Any]]
    regions: List[Dict[str, Any]]
    lines: List[Dict[str, Any]]
    
    # Mapping
    box_to_region: Dict[int, int]
    box_to_line: Dict[int, int]
    
    # Statistiken
    total_boxes: int
    boxes_with_text: int
    avg_confidence: float


@dataclass
class CompleteAnalysisResult:
    """Vollständiges Analyseergebnis für andere Agents."""
    # Analyse
    ui_context: UIScreenContext
    merged_data: MergedCSVData
    
    # Rohdaten
    raw_boxes: List[Dict[str, Any]]
    raw_regions: List[Dict[str, Any]]
    raw_lines: List[Dict[str, Any]]
    
    # Für Menschen/LLM lesbare Zusammenfassung
    readable_summary: str
    
    # Metadaten
    timestamp: float
    processing_time_ms: float
    ocr_quality: float  # 0-1, Anteil Elemente mit Text
    
    # Vision Recommendation
    needs_vision_fallback: bool
    vision_reason: Optional[str] = None

    def to_agent_context(self) -> str:
        """Erzeugt Kontext-String für LLM Agents."""
        lines = [
            "=== UI Analyse Ergebnis ===",
            f"Zeitstempel: {self.timestamp}",
            f"Verarbeitungszeit: {self.processing_time_ms:.0f}ms",
            f"OCR-Qualität: {self.ocr_quality:.0%}",
            "",
            self.readable_summary,
            "",
            "=== Verfügbare Aktionen ===",
        ]
        
        for action in self.ui_context.available_actions[:10]:
            desc = action.get('description', 'Unbekannte Aktion')
            coords = action.get('target_coords', (0, 0))
            lines.append(f"  • {desc} @ ({coords[0]}, {coords[1]})")
        
        if len(self.ui_context.available_actions) > 10:
            lines.append(f"  ... und {len(self.ui_context.available_actions) - 10} weitere")
        
        return "\n".join(lines)


class DataAnalystAgent:
    """
    Data Analyst Agent - Transformiert rohe Detection-Daten in strukturierten Kontext.
    
    Funktionen:
    - Element-Typ-Erkennung basierend auf Position, Größe, Text
    - Semantische Gruppierung (Toolbar, Menu, Content, etc.)
    - Aktions-Extraktion (was kann geklickt werden?)
    - CSV Merge-Logik für vollständige Daten
    - OCR-Wait-Logik für beste Ergebnisse
    - Vision-Fallback bei Hard Cases
"""
    
    def __init__(self, detection_results_dir: str = "./detection_results"):
        self.current_context: Optional[UIScreenContext] = None
        self.element_history: List[Dict[str, Any]] = []
        self.detection_results_dir = Path(detection_results_dir)
        
        # Vision fallback thresholds
        self.min_ocr_quality = 0.3  # Min 30% Elemente mit Text
        self.min_confidence = 0.4   # Min durchschnittliche Konfidenz
        
        # Muster für Element-Typ-Erkennung
        self.button_patterns = [
            r'^ok$', r'^cancel$', r'^yes$', r'^no$', r'^save$', r'^open$',
            r'^close$', r'^apply$', r'^next$', r'^back$', r'^submit$',
            r'^search$', r'^find$', r'^browse$', r'^send$', r'^delete$',
            r'^\+$', r'^-$', r'^x$', r'^…$', r'^\.\.\.$'
        ]
        
        self.menu_patterns = [
            r'^file$', r'^edit$', r'^view$', r'^help$', r'^tools$',
            r'^window$', r'^format$', r'^insert$', r'^datei$', r'^bearbeiten$',
            r'^ansicht$', r'^hilfe$', r'^extras$', r'^fenster$'
        ]
        
        self.input_patterns = [
            r'^search', r'^suche', r'^eingabe', r'^input', r'^type here',
            r'^enter', r'^\|$'  # Cursor
        ]
    
    # ==================== CSV Merge Logic ====================
    
    def load_csv_boxes(self) -> List[Dict[str, Any]]:
        """Lädt component_boxes.csv."""
        csv_path = self.detection_results_dir / "gradients" / "component_boxes.csv"
        boxes = []
        
        if not csv_path.exists():
            logger.warning(f"CSV not found: {csv_path}")
            return boxes
        
        try:
            with open(csv_path, 'r') as f:
                reader = csv.DictReader(
                    (row for row in f if not row.startswith('#')),
                    fieldnames=['x', 'y', 'width', 'height', 'confidence']
                )
                for i, row in enumerate(reader):
                    if row['x'] == 'x':  # Skip header
                        continue
                    boxes.append({
                        'id': i,
                        'x': int(row['x']),
                        'y': int(row['y']),
                        'width': int(row['width']),
                        'height': int(row['height']),
                        'confidence': float(row['confidence'])
                    })
        except Exception as e:
            logger.error(f"Failed to load boxes CSV: {e}")
        
        return boxes
    
    def load_csv_regions(self) -> List[Dict[str, Any]]:
        """Lädt regions.csv."""
        csv_path = self.detection_results_dir / "regions" / "regions.csv"
        regions = []
        
        if not csv_path.exists():
            return regions
        
        try:
            with open(csv_path, 'r') as f:
                reader = csv.DictReader(
                    (row for row in f if not row.startswith('#')),
                    fieldnames=['region_id', 'min_x', 'min_y', 'max_x', 'max_y', 'width', 'height', 'num_boxes']
                )
                for row in reader:
                    if row['region_id'] == 'region_id':
                        continue
                    regions.append({
                        'id': int(row['region_id']),
                        'min_x': int(row['min_x']),
                        'min_y': int(row['min_y']),
                        'max_x': int(row['max_x']),
                        'max_y': int(row['max_y']),
                        'width': int(row['width']),
                        'height': int(row['height']),
                        'num_boxes': int(row['num_boxes'])
                    })
        except Exception as e:
            logger.error(f"Failed to load regions CSV: {e}")
        
        return regions
    
    def load_csv_lines(self) -> List[Dict[str, Any]]:
        """Lädt line_groups.csv."""
        csv_path = self.detection_results_dir / "lines" / "line_groups.csv"
        lines = []
        
        if not csv_path.exists():
            return lines
        
        try:
            with open(csv_path, 'r') as f:
                reader = csv.DictReader(
                    (row for row in f if not row.startswith('#')),
                    fieldnames=['line_id', 'region_id', 'orientation', 'num_boxes', 
                               'min_x', 'min_y', 'max_x', 'max_y', 
                               'avg_width', 'avg_height', 'avg_spacing']
                )
                for row in reader:
                    if row['line_id'] == 'line_id':
                        continue
                    lines.append({
                        'id': int(row['line_id']),
                        'region_id': int(row['region_id']),
                        'orientation': row['orientation'],
                        'num_boxes': int(row['num_boxes']),
                        'min_x': int(row['min_x']),
                        'min_y': int(row['min_y']),
                        'max_x': int(row['max_x']),
                        'max_y': int(row['max_y']),
                        'avg_width': float(row['avg_width']),
                        'avg_height': float(row['avg_height']),
                        'avg_spacing': float(row['avg_spacing'])
                    })
        except Exception as e:
            logger.error(f"Failed to load lines CSV: {e}")
        
        return lines
    
    def merge_csv_results(self) -> MergedCSVData:
        """
        Merged alle CSV-Daten zu einer strukturierten Ansicht.
        
        Returns:
            MergedCSVData mit allen Informationen kombiniert
        """
        boxes = self.load_csv_boxes()
        regions = self.load_csv_regions()
        lines = self.load_csv_lines()
        
        # Box-to-Region mapping basierend auf Koordinaten
        box_to_region: Dict[int, int] = {}
        for box in boxes:
            box_center_x = box['x'] + box['width'] // 2
            box_center_y = box['y'] + box['height'] // 2
            
            for region in regions:
                if (region['min_x'] <= box_center_x <= region['max_x'] and
                    region['min_y'] <= box_center_y <= region['max_y']):
                    box_to_region[box['id']] = region['id']
                    break
        
        # Box-to-Line mapping basierend auf Koordinaten und Region
        box_to_line: Dict[int, int] = {}
        for box in boxes:
            box_region = box_to_region.get(box['id'])
            if box_region is None:
                continue
            
            box_center_x = box['x'] + box['width'] // 2
            box_center_y = box['y'] + box['height'] // 2
            
            for line in lines:
                if line['region_id'] != box_region:
                    continue
                if (line['min_x'] <= box_center_x <= line['max_x'] and
                    line['min_y'] <= box_center_y <= line['max_y']):
                    box_to_line[box['id']] = line['id']
                    break
        
        # Statistiken
        total_boxes = len(boxes)
        boxes_with_text = sum(1 for b in boxes if b.get('text'))
        avg_confidence = (
            sum(b['confidence'] for b in boxes) / total_boxes 
            if total_boxes > 0 else 0
        )
        
 
        return MergedCSVData(
            boxes=boxes,
            regions=regions,
            lines=lines,
            box_to_region=box_to_region,
            box_to_line=box_to_line,
            total_boxes=total_boxes,
            boxes_with_text=boxes_with_text,
            avg_confidence=avg_confidence
        )
    
    # ==================== Wait and Analyze ====================
    
    async def wait_and_analyze(
        self,
        client: 'MoireWebSocketClient',
        timeout: float = 60.0,
        retry_on_low_quality: bool = True
    ) -> CompleteAnalysisResult:        
        """
        Wartet auf vollständigen Capture+OCR und analysiert dann.
        
        Dies ist die Haupt-API für andere Agents.
        
        Args:
            client: MoireWebSocketClient Instanz
            timeout: Maximale Wartezeit
            retry_on_low_quality: Bei schlechter OCR-Qualität retry
        
        Returns:
            CompleteAnalysisResult mit allen Daten
        """
        start_time = time.time()
        
        # Capture mit vollständiger OCR
        if retry_on_low_quality:
            capture_result = await client.capture_with_retry(
                max_retries=3,
                timeout_per_try=timeout / 3,
                min_texts=1
            )
        else:
            capture_result = await client.capture_and_wait_for_complete(timeout=timeout)
        
        if not capture_result.success:
            return CompleteAnalysisResult(
                ui_context=UIScreenContext(
                    timestamp=int(time.time() * 1000),
                    application=None,
                    window_title=None,
                    current_view=None,
                    toolbar_elements=[],
                    menu_elements=[],
                    content_elements=[],
                    statusbar_elements=[],
                    available_actions=[],
                    summary=f"Capture failed: {capture_result.error}",
                    element_count=0,
                    text_element_count=0
                ),
                merged_data=MergedCSVData(
                    boxes=[], regions=[], lines=[],
                    box_to_region={}, box_to_line={},
                    total_boxes=0, boxes_with_text=0, avg_confidence=0
                ),
                raw_boxes=[],
                raw_regions=[],
                raw_lines=[],
                readable_summary=f"Fehler: {capture_result.error}",
                timestamp=time.time(),
                processing_time_ms=(time.time() - start_time) * 1000,
                ocr_quality=0,
                needs_vision_fallback=True,
                vision_reason="Capture failed"
            )
        
        # CSV Daten mergen
        merged_data = self.merge_csv_results()
        
        # UI Context analysieren
        if capture_result.ui_context:
            raw_context = {
                'elements': [
                    {
                        'id': e.id,
                        'type': e.type,
                        'bounds': e.bounds,
                        'center': e.center,
                        'text': e.text,
                        'confidence': e.confidence,
                        'category': e.category
                    }
                    for e in capture_result.ui_context.elements
                ],
                'regions': [
                    {
                        'id': r.id,
                        'bounds': r.bounds,
                        'elementCount': r.element_count,
                        'elementIds': r.element_ids
                    }
                    for r in capture_result.ui_context.regions
                ],
                'lines': [
                    {
                        'id': l.id,
                        'regionId': l.region_id,
                        'orientation': l.orientation,
                        'elementCount': l.element_count,
                        'elementIds': l.element_ids,
                        'avgSpacing': l.avg_spacing
                    }
                    for l in capture_result.ui_context.lines
                ],
                'timestamp': capture_result.ui_context.timestamp,
                'screenDimensions': capture_result.ui_context.screen_dimensions
            }
            
            ui_context = self.analyze_ui_context(raw_context)
        else:
            ui_context = UIScreenContext(
                timestamp=int(time.time() * 1000),
                application=None,
                window_title=None,
                current_view=None,
                toolbar_elements=[],
                menu_elements=[],
                content_elements=[],
                statusbar_elements=[],
                available_actions=[],
                summary="Kein UI-Kontext verfügbar",
                element_count=0,
                text_element_count=0
            )
        
        # OCR Qualität berechnen
        ocr_quality = (
            capture_result.texts_count / capture_result.boxes_count
            if capture_result.boxes_count > 0 else 0
        )
        
        # Vision Fallback prüfen
        needs_vision, vision_reason = self.should_use_vision(
            capture_result, merged_data, ocr_quality
        )
        
        # Lesbare Zusammenfassung erstellen
        readable_summary = self._create_readable_summary(
            ui_context, merged_data, ocr_quality
        )
        
        processing_time = (time.time() - start_time) * 1000
        
        return CompleteAnalysisResult(
            ui_context=ui_context,
            merged_data=merged_data,
            raw_boxes=merged_data.boxes,
            raw_regions=merged_data.regions,
            raw_lines=merged_data.lines,
            readable_summary=readable_summary,
            timestamp=time.time(),
            processing_time_ms=processing_time,
            ocr_quality=ocr_quality,
            needs_vision_fallback=needs_vision,
            vision_reason=vision_reason
        )
    
    def should_use_vision(
        self,
        capture_result: 'CaptureResult',
        merged_data: MergedCSVData,
        ocr_quality: float
    ) -> Tuple[bool, Optional[str]]:
        """
        Prüft ob Vision-Fallback nötig ist.
        
        Returns:
            Tuple (needs_vision, reason)
        """
        # Keine Elemente erkannt
        if capture_result.boxes_count == 0:
            return True, "Keine UI-Elemente erkannt"
        
        # Sehr niedrige OCR-Qualität
        if ocr_quality < self.min_ocr_quality:
            return True, f"Niedrige OCR-Qualität ({ocr_quality:.0%} < {self.min_ocr_quality:.0%})"
        
        # Niedrige durchschnittliche Konfidenz
        if merged_data.avg_confidence < self.min_confidence:
            return True, f"Niedrige Konfidenz ({merged_data.avg_confidence:.0%} < {self.min_confidence:.0%})"
        
        # Keine Texte erkannt obwohl viele Elemente da sind
        if capture_result.boxes_count > 10 and capture_result.texts_count == 0:
            return True, "Viele Elemente aber keine Texte erkannt"
        
        return False, None
    
    def _create_readable_summary(
        self,
        ui_context: UIScreenContext,
        merged_data: MergedCSVData,
        ocr_quality: float
    ) -> str:
        """Erstellt eine menschenlesbare Zusammenfassung."""
        lines = []
        
        # Header
        if ui_context.application:
            lines.append(f"📱 Anwendung: {ui_context.application}")
        if ui_context.window_title:
            lines.append(f"🪟 Fenster: {ui_context.window_title}")
        if ui_context.current_view:
            lines.append(f"📄 Ansicht: {ui_context.current_view}")
        
        lines.append("")
        
        # Statistiken
        lines.append(f"📊 Statistiken:")
        lines.append(f"   • {merged_data.total_boxes} UI-Elemente erkannt")
        lines.append(f"   • {merged_data.boxes_with_text} mit Text ({ocr_quality:.0%})")
        lines.append(f"   • {len(merged_data.regions)} Regionen")
        lines.append(f"   • {len(merged_data.lines)} Zeilen")
        lines.append(f"   • Durchschnittliche Konfidenz: {merged_data.avg_confidence:.0%}")
        
        lines.append("")
        
        # Bereiche
        if ui_context.toolbar_elements:
            toolbar_texts = [e.text for e in ui_context.toolbar_elements if e.text][:5]
            if toolbar_texts:
                lines.append(f"🔧 Toolbar: {', '.join(toolbar_texts)}")
        
        if ui_context.menu_elements:
            menu_texts = [e.text for e in ui_context.menu_elements if e.text]
            if menu_texts:
                lines.append(f"📋 Menü: {', '.join(menu_texts)}")
        
        if ui_context.content_elements:
            content_texts = [e.text for e in ui_context.content_elements if e.text][:5]
            if content_texts:
                lines.append(f"📝 Inhalt: {', '.join(content_texts)}...")
        
        if ui_context.statusbar_elements:
            status_texts = [e.text for e in ui_context.statusbar_elements if e.text][:2]
            if status_texts:
                lines.append(f"📊 Status: {', '.join(status_texts)}")
        
        lines.append("")
        
        # Top Aktionen
        if ui_context.available_actions:
            lines.append(f"⚡ Verfügbare Aktionen ({len(ui_context.available_actions)}):")
            for action in ui_context.available_actions[:5]:
                desc = action.get('description', 'Unbekannt')
                lines.append(f"   • {desc}")
        
        return "\n".join(lines)
    
    def analyze_ui_context(
        self,
        raw_context: Dict[str, Any]
    ) -> UIScreenContext:
        """
        Analysiert rohen UI-Kontext von MoireTracker.
        
        Args:
            raw_context: Roher UI-Kontext mit elements, regions, lines
        
        Returns:
            Strukturierter UIScreenContext
        """
        elements = raw_context.get('elements', [])
        regions = raw_context.get('regions', [])
        lines = raw_context.get('lines', [])
        
        # Analysiere jedes Element
        analyzed_elements = []
        for elem in elements:
            analyzed = self._analyze_element(elem, regions, lines)
            analyzed_elements.append(analyzed)
        
        # Gruppiere nach Bildschirmbereich
        toolbar_elems = []
        menu_elems = []
        content_elems = []
        statusbar_elems = []
        
        screen_height = raw_context.get('screenDimensions', {}).get('height', 1080)
        
        for elem in analyzed_elements:
            y = elem.bounds.get('y', 0)
            elem_type = elem.type
            
            # Position-basierte Gruppierung
            if y < 100:  # Top area
                if elem_type in [UIElementType.MENU, UIElementType.MENUITEM]:
                    menu_elems.append(elem)
                else:
                    toolbar_elems.append(elem)
            elif y > screen_height - 50:  # Bottom area
                statusbar_elems.append(elem)
            else:
                content_elems.append(elem)
        
        # Extrahiere verfügbare Aktionen
        available_actions = self._extract_actions(analyzed_elements)
        
        # Erstelle Zusammenfassung
        summary = self._create_summary(
            toolbar_elems, menu_elems, content_elems, 
            statusbar_elems, available_actions
        )
        
        context = UIScreenContext(
            timestamp=raw_context.get('timestamp', 0),
            application=self._detect_application(analyzed_elements),
            window_title=self._detect_window_title(analyzed_elements),
            current_view=self._detect_current_view(analyzed_elements),
            toolbar_elements=toolbar_elems,
            menu_elements=menu_elems,
            content_elements=content_elems,
            statusbar_elements=statusbar_elems,
            available_actions=available_actions,
            summary=summary,
            element_count=len(analyzed_elements),
            text_element_count=sum(1 for e in analyzed_elements if e.text)
        )
        
        self.current_context = context
        logger.info(f"Analyzed UI: {context.element_count} elements, {len(available_actions)} actions")
        
        return context
    
    def _analyze_element(
        self,
        elem: Dict[str, Any],
        regions: List[Dict],
        lines: List[Dict]
    ) -> AnalyzedElement:
        """Analysiert ein einzelnes Element."""
        text = elem.get('text')
        bounds = elem.get('bounds', {})
        width = bounds.get('width', 0)
        height = bounds.get('height', 0)
        confidence = elem.get('confidence', 0)
        
        # Bestimme Element-Typ
        elem_type = self._determine_element_type(text, width, height, bounds)
        
        # Bestimme ob klickbar
        actionable = elem_type in [
            UIElementType.BUTTON, UIElementType.MENU, UIElementType.MENUITEM,
            UIElementType.TAB, UIElementType.CHECKBOX, UIElementType.DROPDOWN,
            UIElementType.LINK, UIElementType.ICON
        ]
        
        # Bestimme Aktionstyp
        action_type = None
        if actionable:
            if elem_type == UIElementType.TEXTFIELD:
                action_type = "type"
            elif elem_type == UIElementType.CHECKBOX:
                action_type = "toggle"
            elif elem_type == UIElementType.DROPDOWN:
                action_type = "select"
            else:
                action_type = "click"
        
        # Finde Region und Line
        region_id = None
        line_id = None
        
        # Semantischer Typ
        semantic_type = self._determine_semantic_type(text, elem_type)
        
        # Wahrscheinliche Funktion
        probable_function = self._determine_function(text, elem_type, bounds)
        
        return AnalyzedElement(
            id=elem.get('id', ''),
            type=elem_type,
            text=text,
            bounds=bounds,
            center=(elem.get('center', {}).get('x', 0), elem.get('center', {}).get('y', 0)),
            confidence=confidence,
            semantic_type=semantic_type,
            actionable=actionable,
            action_type=action_type,
            region_id=region_id,
            line_id=line_id,
            probable_function=probable_function
        )
    
    def _determine_element_type(
        self,
        text: Optional[str],
        width: int,
        height: int,
        bounds: Dict[str, int]
    ) -> UIElementType:
        """Bestimmt den Typ eines Elements."""
        if not text:
            # Ohne Text: basierend auf Größe
            aspect_ratio = width / max(height, 1)
            
            if 16 <= width <= 48 and 16 <= height <= 48:
                return UIElementType.ICON
            elif height > width * 3:
                return UIElementType.TEXTFIELD  # Vertikaler Bereich
            else:
                return UIElementType.UNKNOWN
        
        text_lower = text.lower().strip()
        
        # Menu-Pattern
        for pattern in self.menu_patterns:
            if re.match(pattern, text_lower):
                return UIElementType.MENU
        
        # Button-Pattern
        for pattern in self.button_patterns:
            if re.match(pattern, text_lower):
                return UIElementType.BUTTON
        
        # Input-Pattern
        for pattern in self.input_patterns:
            if re.search(pattern, text_lower):
                return UIElementType.TEXTFIELD
        
        # Checkbox (enthält ☐, ☑, etc.)
        if any(c in text for c in ['☐', '☑', '☒', '□', '■']):
            return UIElementType.CHECKBOX
        
        # Link (URL-ähnlich)
        if text.startswith('http') or '@' in text:
            return UIElementType.LINK
        
        # Tab (kurzer Text, breiter als hoch)
        if len(text) < 20 and width > height * 2:
            return UIElementType.TAB
        
        # Label (Default für Text-Elemente)
        return UIElementType.LABEL
    
    def _determine_semantic_type(
        self,
        text: Optional[str],
        elem_type: UIElementType
    ) -> Optional[str]:
        """Bestimmt semantischen Typ basierend auf Text."""
        if not text:
            return None
        
        text_lower = text.lower()
        
        # Navigation
        if any(w in text_lower for w in ['back', 'forward', 'next', 'previous', 'zurück', 'weiter']):
            return "navigation"
        
        # Bestätigung
        if any(w in text_lower for w in ['ok', 'yes', 'confirm', 'apply', 'ja', 'bestätigen']):
            return "confirmation"
        
        # Abbruch
        if any(w in text_lower for w in ['cancel', 'no', 'close', 'abbrechen', 'nein', 'schließen']):
            return "cancellation"
        
        # Suche
        if any(w in text_lower for w in ['search', 'find', 'suche', 'finden']):
            return "search"
        
        # Speichern
        if any(w in text_lower for w in ['save', 'speichern', 'export']):
            return "save"
        
        # Öffnen
        if any(w in text_lower for w in ['open', 'load', 'öffnen', 'laden', 'import']):
            return "open"
        
        return None
    
    def _determine_function(
        self,
        text: Optional[str],
        elem_type: UIElementType,
        bounds: Dict[str, int]
    ) -> Optional[str]:
        """Bestimmt wahrscheinliche Funktion eines Elements."""
        if not text:
            # Icon-basierte Funktion
            if elem_type == UIElementType.ICON:
                y = bounds.get('y', 0)
                if y < 50:
                    return "toolbar_action"
            return None
        
        text_lower = text.lower()
        
        # Dateifunktionen
        if any(w in text_lower for w in ['new', 'neu', 'create', 'erstellen']):
            return "create_new"
        if any(w in text_lower for w in ['delete', 'remove', 'löschen', 'entfernen']):
            return "delete"
        if any(w in text_lower for w in ['copy', 'kopieren']):
            return "copy"
        if any(w in text_lower for w in ['paste', 'einfügen']):
            return "paste"
        if any(w in text_lower for w in ['cut', 'ausschneiden']):
            return "cut"
        
        # Ansichtsfunktionen
        if any(w in text_lower for w in ['zoom', 'vergrößern']):
            return "zoom"
        
        return None
    
    def _extract_actions(
        self,
        elements: List[AnalyzedElement]
    ) -> List[Dict[str, Any]]:
        """Extrahiert verfügbare Aktionen aus Elementen."""
        actions = []
        
        for elem in elements:
            if not elem.actionable:
                continue
            
            action = {
                'element_id': elem.id,
                'action_type': elem.action_type,
                'target_text': elem.text,
                'target_coords': elem.center,
                'semantic_type': elem.semantic_type,
                'probable_function': elem.probable_function,
                'confidence': elem.confidence
            }
            
            # Beschreibung generieren
            if elem.text:
                action['description'] = f"{elem.action_type} on '{elem.text}'"
            else:
                action['description'] = f"{elem.action_type} at ({elem.center[0]}, {elem.center[1]})"
            
            actions.append(action)
        
        # Sortiere nach Relevanz
        actions.sort(key=lambda a: (
            -a['confidence'],
            a['semantic_type'] is not None,
            a['probable_function'] is not None
        ), reverse=True)
        
        return actions
    
    def _detect_application(
        self,
        elements: List[AnalyzedElement]
    ) -> Optional[str]:
        """Versucht die Anwendung zu erkennen."""
        # Suche nach bekannten App-Namen in Titelebene
        app_patterns = {
            'chrome': ['chrome', 'google chrome'],
            'firefox': ['firefox', 'mozilla'],
            'edge': ['edge', 'microsoft edge'],
            'vscode': ['visual studio code', 'vs code', 'vscode'],
            'word': ['word', 'microsoft word', 'document'],
            'excel': ['excel', 'microsoft excel', 'spreadsheet'],
            'explorer': ['file explorer', 'explorer', 'datei-explorer'],
            'notepad': ['notepad', 'editor'],
            'terminal': ['terminal', 'cmd', 'powershell', 'command prompt'],
        }
        
        # Suche in Toolbar-Elementen
        toolbar_texts = [
            e.text.lower() for e in elements 
            if e.text and e.bounds.get('y', 1000) < 100
        ]
        
        for app, patterns in app_patterns.items():
            for pattern in patterns:
                for text in toolbar_texts:
                    if pattern in text:
                        return app
        
        return None
    
    def _detect_window_title(
        self,
        elements: List[AnalyzedElement]
    ) -> Optional[str]:
        """Versucht den Fenstertitel zu erkennen."""
        # Suche Element ganz oben in der Mitte
        candidates = []
        
        for elem in elements:
            if elem.text and elem.bounds.get('y', 1000) < 50:
                x = elem.bounds.get('x', 0)
                width = elem.bounds.get('width', 0)
                # Zentrierte Elemente bevorzugen
                if x > 200 and x + width < 1700:  # Annahme: 1920px Breite
                    candidates.append(elem)
        
        if candidates:
            # Längster Text ist wahrscheinlich der Titel
            candidates.sort(key=lambda e: len(e.text or ''), reverse=True)
            return candidates[0].text
        
        return None
    
    def _detect_current_view(
        self,
        elements: List[AnalyzedElement]
    ) -> Optional[str]:
        """Versucht die aktuelle Ansicht zu erkennen."""
        # Suche nach aktiven Tabs
        for elem in elements:
            if elem.type == UIElementType.TAB:
                # Aktive Tabs haben oft höhere Konfidenz oder sind hervorgehoben
                if elem.confidence > 0.7 and elem.text:
                    return f"Tab: {elem.text}"
        
        return None
    
    def _create_summary(
        self,
        toolbar: List[AnalyzedElement],
        menu: List[AnalyzedElement],
        content: List[AnalyzedElement],
        statusbar: List[AnalyzedElement],
        actions: List[Dict[str, Any]]
    ) -> str:
        """Erstellt eine menschenlesbare Zusammenfassung."""
        lines = []
        
        # Toolbar
        if toolbar:
            toolbar_texts = [e.text for e in toolbar if e.text][:5]
            if toolbar_texts:
                lines.append(f"Toolbar: {', '.join(toolbar_texts)}")
        
        # Menu
        if menu:
            menu_texts = [e.text for e in menu if e.text]
            if menu_texts:
                lines.append(f"Menu: {', '.join(menu_texts)}")
        
        # Content
        content_with_text = [e for e in content if e.text]
        if content_with_text:
            lines.append(f"Content: {len(content_with_text)} Textelemente")
            # Erste paar Texte
            sample_texts = [e.text for e in content_with_text[:3]]
            if sample_texts:
                lines.append(f"  Beispiele: {', '.join(sample_texts)}")
        
        # Statusbar
        if statusbar:
            statusbar_texts = [e.text for e in statusbar if e.text]
            if statusbar_texts:
                lines.append(f"Status: {', '.join(statusbar_texts[:2])}")
        
        # Aktionen
        if actions:
            top_actions = actions[:5]
            action_descs = [a['description'] for a in top_actions]
            lines.append(f"Verfügbare Aktionen ({len(actions)} total):")
            for desc in action_descs:
                lines.append(f"  - {desc}")
        
        return "\n".join(lines)
    
    # ==================== API für Orchestrator ====================
    
    async def find_element(
        self,
        description: str,
        ui_context: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Findet ein Element basierend auf Beschreibung.
        
        Args:
            description: Beschreibung des gesuchten Elements
            ui_context: Aktueller UI-Kontext
        
        Returns:
            Gefundenes Element oder Fehler
        """
        if not ui_context:
            return {'success': False, 'error': 'No UI context available'}
        
        # Analysiere Kontext falls noch nicht geschehen
        if not self.current_context or self.current_context.timestamp != ui_context.get('timestamp'):
            self.analyze_ui_context(ui_context)
        
        if not self.current_context:
            return {'success': False, 'error': 'Failed to analyze UI context'}
        
        # Suche in allen Elementen
        all_elements = (
            self.current_context.toolbar_elements +
            self.current_context.menu_elements +
            self.current_context.content_elements +
            self.current_context.statusbar_elements
        )
        
        description_lower = description.lower()
        
        # Exakte Übereinstimmung
        for elem in all_elements:
            if elem.text and elem.text.lower() == description_lower:
                return {
                    'success': True,
                    'data': {
                        'found_element': {
                            'id': elem.id,
                            'text': elem.text,
                            'center': elem.center,
                            'type': elem.type.value,
                            'actionable': elem.actionable
                        }
                    }
                }
        
        # Teilübereinstimmung
        for elem in all_elements:
            if elem.text and description_lower in elem.text.lower():
                return {
                    'success': True,
                    'data': {
                        'found_element': {
                            'id': elem.id,
                            'text': elem.text,
                            'center': elem.center,
                            'type': elem.type.value,
                            'actionable': elem.actionable
                        }
                    }
                }
        
        # Suche nach Funktion
        for elem in all_elements:
            if elem.probable_function and description_lower in elem.probable_function:
                return {
                    'success': True,
                    'data': {
                        'found_element': {
                            'id': elem.id,
                            'text': elem.text,
                            'center': elem.center,
                            'type': elem.type.value,
                            'actionable': elem.actionable
                        }
                    }
                }
        
        return {
            'success': False,
            'error': f'Element not found: {description}',
            'data': {
                'available_elements': [e.text for e in all_elements if e.text][:10]
            }
        }
    
    async def verify_state(
        self,
        condition: Optional[str],
        ui_context: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Verifiziert einen Zustand.
        
        Args:
            condition: Zu prüfende Bedingung
            ui_context: Aktueller UI-Kontext
        
        Returns:
            Verifikationsergebnis
        """
        if not ui_context:
            return {'success': True, 'data': {'verified': False, 'reason': 'No UI context'}}
        
        # Analysiere Kontext
        context = self.analyze_ui_context(ui_context)
        
        if not condition:
            return {
                'success': True,
                'data': {
                    'verified': True,
                    'summary': context.summary,
                    'element_count': context.element_count
                }
            }
        
        condition_lower = condition.lower()
        
        # Prüfe Bedingung
        all_texts = []
        for elem in (context.toolbar_elements + context.menu_elements + 
                    context.content_elements + context.statusbar_elements):
            if elem.text:
                all_texts.append(elem.text.lower())
        
        # Suche nach Bedingung in Texten
        verified = any(condition_lower in text for text in all_texts)
        
        return {
            'success': True,
            'data': {
                'verified': verified,
                'condition': condition,
                'found_in': [t for t in all_texts if condition_lower in t][:5]
            }
        }
    
    def get_summary(self) -> str:
        """Gibt aktuelle Zusammenfassung zurück."""
        if self.current_context:
            return self.current_context.summary
        return "Keine UI-Daten analysiert"
    
    def get_available_actions(self) -> List[Dict[str, Any]]:
        """Gibt verfügbare Aktionen zurück."""
        if self.current_context:
            return self.current_context.available_actions
        return []


# Singleton
_data_analyst_instance: Optional[DataAnalystAgent] = None


def get_data_analyst() -> DataAnalystAgent:
    """Gibt Singleton-Instanz des Data Analyst zurück."""
    global _data_analyst_instance
    if _data_analyst_instance is None:
        _data_analyst_instance = DataAnalystAgent()
    return _data_analyst_instance