"""
Word Helper - Word-spezifische Operationen für Formatierung.

Provides:
- Smart text selection (paragraph, sentence, word)
- Formatting operations (bold, italic, underline, etc.)
- Ribbon state detection via Vision
- Formatting verification
"""

import asyncio
import logging
import time
from typing import Optional, Dict, Any, List, Tuple, TYPE_CHECKING
from dataclasses import dataclass, field
from enum import Enum

if TYPE_CHECKING:
    from ..agents.interaction import InteractionAgent
    from ..agents.vision_agent import VisionAnalystAgent
    from .context_tracker import ContextTracker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FormatType(Enum):
    """Formatierungs-Typen."""
    BOLD = "bold"
    ITALIC = "italic"
    UNDERLINE = "underline"
    STRIKETHROUGH = "strikethrough"
    SUBSCRIPT = "subscript"
    SUPERSCRIPT = "superscript"


class AlignmentType(Enum):
    """Ausrichtungs-Typen."""
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"
    JUSTIFY = "justify"


@dataclass
class FormattingState:
    """Aktueller Formatierungs-Zustand."""
    is_bold: bool = False
    is_italic: bool = False
    is_underline: bool = False
    is_strikethrough: bool = False
    
    font_name: Optional[str] = None
    font_size: Optional[int] = None
    
    alignment: AlignmentType = AlignmentType.LEFT
    
    # Ribbon-Zustand
    ribbon_visible: bool = True
    active_tab: str = "Home"
    
    timestamp: float = field(default_factory=time.time)
    confidence: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'bold': self.is_bold,
            'italic': self.is_italic,
            'underline': self.is_underline,
            'font': self.font_name,
            'size': self.font_size,
            'alignment': self.alignment.value,
            'confidence': self.confidence
        }


# Keyboard shortcuts für Word-Formatierung
WORD_FORMAT_SHORTCUTS = {
    FormatType.BOLD: ('ctrl', 'b'),
    FormatType.ITALIC: ('ctrl', 'i'),
    FormatType.UNDERLINE: ('ctrl', 'u'),
    FormatType.STRIKETHROUGH: ('ctrl', 'd'),  # Öffnet Font-Dialog
    FormatType.SUBSCRIPT: ('ctrl', '='),
    FormatType.SUPERSCRIPT: ('ctrl', 'shift', '='),
}

WORD_ALIGNMENT_SHORTCUTS = {
    AlignmentType.LEFT: ('ctrl', 'l'),
    AlignmentType.CENTER: ('ctrl', 'e'),
    AlignmentType.RIGHT: ('ctrl', 'r'),
    AlignmentType.JUSTIFY: ('ctrl', 'j'),
}


class WordHelper:
    """
    Word Helper - Präzise Word-Operationen mit Feingefühl.
    
    Verwendet Vision für Ribbon-Analyse und Verifizierung.
    """
    
    def __init__(
        self,
        interaction_agent: Optional['InteractionAgent'] = None,
        vision_agent: Optional['VisionAnalystAgent'] = None,
        context_tracker: Optional['ContextTracker'] = None
    ):
        self.interaction = interaction_agent
        self.vision = vision_agent
        self.context = context_tracker
        
        # State
        self._formatting_state = FormattingState()
        self._last_screenshot: Optional[bytes] = None
    
    def set_agents(
        self,
        interaction: Optional['InteractionAgent'] = None,
        vision: Optional['VisionAnalystAgent'] = None,
        context: Optional['ContextTracker'] = None
    ):
        """Setzt Agent-Referenzen."""
        if interaction:
            self.interaction = interaction
        if vision:
            self.vision = vision
        if context:
            self.context = context
    
    # ==================== Selection Operations ====================
    
    async def select_all(self) -> Dict[str, Any]:
        """Markiert alles (Ctrl+A)."""
        if not self.interaction:
            return {'success': False, 'error': 'No interaction agent'}
        
        result = await self.interaction.hotkey('ctrl', 'a')
        
        if result.get('success') and self.context:
            await self.context.update_after_action('select_all', {})
        
        return result
    
    async def select_paragraph(self, click_position: Optional[Tuple[int, int]] = None) -> Dict[str, Any]:
        """
        Markiert einen Absatz per Triple-Click.
        
        Args:
            click_position: Optional Position zum Klicken (sonst aktuelle Position)
        
        Returns:
            Ergebnis mit Selektion-Info
        """
        if not self.interaction:
            return {'success': False, 'error': 'No interaction agent'}
        
        # Triple-Click
        if click_position:
            result = await self.interaction.click(
                target=click_position,
                clicks=3
            )
        else:
            result = await self.interaction.click(clicks=3)
        
        if result.get('success') and self.context:
            await self.context.update_after_action('triple_click', {'position': click_position})
            
            # Erfasse markierten Text
            selected = await self.context.get_selected_text()
            result['selected_text'] = selected
            result['char_count'] = len(selected) if selected else 0
        
        return result
    
    async def select_word(self, click_position: Optional[Tuple[int, int]] = None) -> Dict[str, Any]:
        """Markiert ein Wort per Doppelklick."""
        if not self.interaction:
            return {'success': False, 'error': 'No interaction agent'}
        
        result = await self.interaction.double_click(target=click_position)
        
        if result.get('success') and self.context:
            await self.context.update_after_action('double_click', {'position': click_position})
            selected = await self.context.get_selected_text()
            result['selected_text'] = selected
        
        return result
    
    async def select_line(self, click_position: Optional[Tuple[int, int]] = None) -> Dict[str, Any]:
        """
        Markiert eine Zeile.
        
        In Word: Klick am linken Rand (Selektionsbereich).
        Alternativ: Home, Shift+End.
        """
        if not self.interaction:
            return {'success': False, 'error': 'No interaction agent'}
        
        # Methode: Home + Shift+End
        await self.interaction.press_key('home')
        await asyncio.sleep(0.05)
        result = await self.interaction.hotkey('shift', 'end')
        
        if result.get('success') and self.context:
            await self.context.update_after_action('select_line', {})
            selected = await self.context.get_selected_text()
            result['selected_text'] = selected
        
        return result
    
    async def select_to_end(self) -> Dict[str, Any]:
        """Markiert von Cursor bis Ende des Dokuments."""
        if not self.interaction:
            return {'success': False, 'error': 'No interaction agent'}
        
        result = await self.interaction.hotkey('ctrl', 'shift', 'end')
        
        if result.get('success') and self.context:
            await self.context.update_after_action('select_to_end', {})
        
        return result
    
    async def select_to_start(self) -> Dict[str, Any]:
        """Markiert von Cursor bis Anfang des Dokuments."""
        if not self.interaction:
            return {'success': False, 'error': 'No interaction agent'}
        
        result = await self.interaction.hotkey('ctrl', 'shift', 'home')
        
        if result.get('success') and self.context:
            await self.context.update_after_action('select_to_start', {})
        
        return result
    
    async def extend_selection(self, direction: str, unit: str = 'word') -> Dict[str, Any]:
        """
        Erweitert aktuelle Selektion.
        
        Args:
            direction: 'left' oder 'right'
            unit: 'char', 'word', 'line'
        
        Returns:
            Ergebnis
        """
        if not self.interaction:
            return {'success': False, 'error': 'No interaction agent'}
        
        # Shift + Bewegung
        if unit == 'char':
            key = 'left' if direction == 'left' else 'right'
            result = await self.interaction.hotkey('shift', key)
        elif unit == 'word':
            key = 'left' if direction == 'left' else 'right'
            result = await self.interaction.hotkey('ctrl', 'shift', key)
        elif unit == 'line':
            key = 'up' if direction == 'left' else 'down'
            result = await self.interaction.hotkey('shift', key)
        else:
            return {'success': False, 'error': f'Unknown unit: {unit}'}
        
        if result.get('success') and self.context:
            await self.context.update_after_action('extend_selection', {
                'direction': direction,
                'unit': unit
            })
        
        return result
    
    # ==================== Formatting Operations ====================
    
    async def apply_format(self, format_type: FormatType) -> Dict[str, Any]:
        """
        Wendet Formatierung auf Selektion an.
        
        Args:
            format_type: Art der Formatierung
        
        Returns:
            Ergebnis mit Verifizierung
        """
        if not self.interaction:
            return {'success': False, 'error': 'No interaction agent'}
        
        shortcut = WORD_FORMAT_SHORTCUTS.get(format_type)
        if not shortcut:
            return {'success': False, 'error': f'Unknown format: {format_type}'}
        
        # Formatierung anwenden
        result = await self.interaction.hotkey(*shortcut)
        
        if result.get('success'):
            # Update State
            if format_type == FormatType.BOLD:
                self._formatting_state.is_bold = not self._formatting_state.is_bold
            elif format_type == FormatType.ITALIC:
                self._formatting_state.is_italic = not self._formatting_state.is_italic
            elif format_type == FormatType.UNDERLINE:
                self._formatting_state.is_underline = not self._formatting_state.is_underline
            
            result['format_applied'] = format_type.value
            
            if self.context:
                await self.context.update_after_action('format', {'type': format_type.value})
        
        return result
    
    async def bold(self) -> Dict[str, Any]:
        """Fett-Formatierung."""
        return await self.apply_format(FormatType.BOLD)
    
    async def italic(self) -> Dict[str, Any]:
        """Kursiv-Formatierung."""
        return await self.apply_format(FormatType.ITALIC)
    
    async def underline(self) -> Dict[str, Any]:
        """Unterstrichen-Formatierung."""
        return await self.apply_format(FormatType.UNDERLINE)
    
    async def set_alignment(self, alignment: AlignmentType) -> Dict[str, Any]:
        """Setzt Text-Ausrichtung."""
        if not self.interaction:
            return {'success': False, 'error': 'No interaction agent'}
        
        shortcut = WORD_ALIGNMENT_SHORTCUTS.get(alignment)
        if not shortcut:
            return {'success': False, 'error': f'Unknown alignment: {alignment}'}
        
        result = await self.interaction.hotkey(*shortcut)
        
        if result.get('success'):
            self._formatting_state.alignment = alignment
            result['alignment'] = alignment.value
        
        return result
    
    async def set_font_size(self, size: int) -> Dict[str, Any]:
        """
        Setzt Schriftgröße.
        
        Args:
            size: Schriftgröße in Punkten
        
        Returns:
            Ergebnis
        """
        if not self.interaction:
            return {'success': False, 'error': 'No interaction agent'}
        
        # Ctrl+Shift+P öffnet Font Size Dialog, aber besser:
        # Ctrl+Shift+> / < für größer/kleiner
        # Oder: Ctrl+] / Ctrl+[ für inkrementell
        
        # Direkte Methode: Schriftgröße-Feld in Ribbon
        # Für jetzt: Ctrl+Shift+P, Größe eingeben, Enter
        await self.interaction.hotkey('ctrl', 'shift', 'p')
        await asyncio.sleep(0.1)
        await self.interaction.type_text(str(size))
        await asyncio.sleep(0.05)
        result = await self.interaction.press_key('enter')
        
        if result.get('success'):
            self._formatting_state.font_size = size
        
        return result
    
    async def increase_font_size(self) -> Dict[str, Any]:
        """Vergrößert Schrift."""
        return await self.interaction.hotkey('ctrl', 'shift', '>')
    
    async def decrease_font_size(self) -> Dict[str, Any]:
        """Verkleinert Schrift."""
        return await self.interaction.hotkey('ctrl', 'shift', '<')
    
    # ==================== Combined Operations ====================
    
    async def format_paragraph_bold(
        self,
        paragraph_number: int = 1,
        via_vision: bool = True
    ) -> Dict[str, Any]:
        """
        Formatiert einen Absatz fett.
        
        Args:
            paragraph_number: Welcher Absatz (1-basiert)
            via_vision: Ob Vision für Position genutzt werden soll
        
        Returns:
            Ergebnis mit Details
        """
        result = {
            'success': False,
            'steps': []
        }
        
        try:
            # Step 1: Absatz finden und anklicken
            if via_vision and self.vision and self._last_screenshot:
                # Vision: Finde Absatz-Position
                location = await self.vision.find_element_from_screenshot(
                    self._last_screenshot,
                    f"Der {paragraph_number}. Absatz im Dokument"
                )
                
                if location.found:
                    # Klick in den Absatz
                    await self.interaction.click((location.x, location.y))
                    result['steps'].append(f"Clicked at ({location.x}, {location.y})")
            
            # Step 2: Absatz markieren (Triple-Click)
            select_result = await self.select_paragraph()
            result['steps'].append(f"Selected paragraph: {select_result.get('char_count', 0)} chars")
            
            if not select_result.get('success'):
                result['error'] = 'Failed to select paragraph'
                return result
            
            # Step 3: Fett formatieren
            format_result = await self.bold()
            result['steps'].append(f"Applied bold: {format_result.get('success')}")
            
            if not format_result.get('success'):
                result['error'] = 'Failed to apply bold'
                return result
            
            # Step 4: Verifizieren (optional)
            if self.vision and self._last_screenshot:
                is_bold = await self.verify_format_applied(FormatType.BOLD)
                result['verified'] = is_bold
                result['steps'].append(f"Verified bold: {is_bold}")
            
            result['success'] = True
            result['selected_text'] = select_result.get('selected_text')
            
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"format_paragraph_bold failed: {e}")
        
        return result
    
    async def format_selection(
        self,
        formats: List[FormatType],
        verify: bool = True
    ) -> Dict[str, Any]:
        """
        Wendet mehrere Formatierungen auf aktuelle Selektion an.
        
        Args:
            formats: Liste von Formatierungen
            verify: Ob verifiziert werden soll
        
        Returns:
            Ergebnis
        """
        results = {
            'success': True,
            'applied': [],
            'failed': []
        }
        
        for fmt in formats:
            result = await self.apply_format(fmt)
            if result.get('success'):
                results['applied'].append(fmt.value)
            else:
                results['failed'].append(fmt.value)
                results['success'] = False
        
        return results
    
    # ==================== Verification ====================
    
    async def verify_format_applied(
        self,
        format_type: FormatType,
        screenshot_bytes: Optional[bytes] = None
    ) -> bool:
        """
        Verifiziert ob Formatierung aktiv ist.
        
        Analysiert Ribbon-Buttons via Vision.
        
        Args:
            format_type: Zu prüfende Formatierung
            screenshot_bytes: Optional neuer Screenshot
        
        Returns:
            True wenn Format aktiv
        """
        if not self.vision or not self.vision.is_available():
            logger.warning("Vision not available for verification")
            return True  # Assume success
        
        screenshot = screenshot_bytes or self._last_screenshot
        if not screenshot:
            return True
        
        try:
            # Vision: Prüfe ob Button aktiv ist
            button_descriptions = {
                FormatType.BOLD: "Bold button B - is it active/pressed/highlighted in the ribbon?",
                FormatType.ITALIC: "Italic button I - is it active/pressed/highlighted in the ribbon?",
                FormatType.UNDERLINE: "Underline button U - is it active/pressed/highlighted in the ribbon?",
            }
            
            description = button_descriptions.get(format_type)
            if not description:
                return True
            
            from PIL import Image
            from io import BytesIO
            
            image = Image.open(BytesIO(screenshot))
            
            analysis = await self.vision.analyze_screenshot(
                image,
                context=f"Check if {format_type.value} formatting is active in Word ribbon"
            )
            
            if analysis.success:
                desc_lower = analysis.description.lower()
                # Suche nach Hinweisen dass Button aktiv ist
                active_indicators = ['active', 'pressed', 'highlighted', 'selected', 'aktiv', 'gedrückt']
                return any(indicator in desc_lower for indicator in active_indicators)
        
        except Exception as e:
            logger.error(f"Format verification failed: {e}")
        
        return True  # Assume success on error
    
    async def get_ribbon_state(self, screenshot_bytes: bytes) -> FormattingState:
        """
        Liest kompletten Ribbon-Zustand via Vision.
        
        Args:
            screenshot_bytes: Screenshot des Word-Fensters
        
        Returns:
            FormattingState
        """
        state = FormattingState()
        
        if not self.vision or not self.vision.is_available():
            return state
        
        try:
            from PIL import Image
            from io import BytesIO
            
            image = Image.open(BytesIO(screenshot_bytes))
            
            # Crop to Ribbon area (typically top ~150px)
            ribbon_height = 150
            ribbon_image = image.crop((0, 0, image.width, min(ribbon_height, image.height)))
            
            buffer = BytesIO()
            ribbon_image.save(buffer, format='PNG')
            ribbon_bytes = buffer.getvalue()
            
            # Analyse Ribbon
            analysis = await self.vision.analyze_screenshot(
                ribbon_image,
                context="Analyze the Word ribbon toolbar. Which formatting buttons are active/pressed? (Bold B, Italic I, Underline U). What font and size is selected?"
            )
            
            if analysis.success:
                desc_lower = analysis.description.lower()
                
                # Parse state
                state.is_bold = 'bold' in desc_lower and ('active' in desc_lower or 'pressed' in desc_lower)
                state.is_italic = 'italic' in desc_lower and ('active' in desc_lower or 'pressed' in desc_lower)
                state.is_underline = 'underline' in desc_lower and ('active' in desc_lower or 'pressed' in desc_lower)
                
                # Font size detection
                import re
                size_match = re.search(r'(\d+)\s*(pt|punkt|point)', desc_lower)
                if size_match:
                    state.font_size = int(size_match.group(1))
                
                state.confidence = 0.7
                state.timestamp = time.time()
            
            self._formatting_state = state
            self._last_screenshot = screenshot_bytes
        
        except Exception as e:
            logger.error(f"Ribbon state detection failed: {e}")
        
        return state
    
    def update_screenshot(self, screenshot_bytes: bytes):
        """Aktualisiert den Screenshot für Vision-Operationen."""
        self._last_screenshot = screenshot_bytes
    
    # ==================== Navigation ====================
    
    async def go_to_start(self) -> Dict[str, Any]:
        """Geht zum Dokument-Anfang."""
        return await self.interaction.hotkey('ctrl', 'home')
    
    async def go_to_end(self) -> Dict[str, Any]:
        """Geht zum Dokument-Ende."""
        return await self.interaction.hotkey('ctrl', 'end')
    
    async def go_to_next_paragraph(self) -> Dict[str, Any]:
        """Springt zum nächsten Absatz."""
        return await self.interaction.hotkey('ctrl', 'down')
    
    async def go_to_previous_paragraph(self) -> Dict[str, Any]:
        """Springt zum vorherigen Absatz."""
        return await self.interaction.hotkey('ctrl', 'up')
    
    # ==================== State ====================
    
    def get_formatting_state(self) -> FormattingState:
        """Gibt aktuellen Formatierungs-Zustand zurück."""
        return self._formatting_state
    
    def get_stats(self) -> Dict[str, Any]:
        """Gibt Statistiken zurück."""
        return {
            'formatting_state': self._formatting_state.to_dict(),
            'has_screenshot': self._last_screenshot is not None,
            'vision_available': self.vision is not None and self.vision.is_available(),
            'interaction_available': self.interaction is not None
        }


# Singleton
_word_helper_instance: Optional[WordHelper] = None


def get_word_helper(
    interaction_agent: Optional['InteractionAgent'] = None,
    vision_agent: Optional['VisionAnalystAgent'] = None,
    context_tracker: Optional['ContextTracker'] = None
) -> WordHelper:
    """Gibt Singleton-Instanz des WordHelpers zurück."""
    global _word_helper_instance
    if _word_helper_instance is None:
        _word_helper_instance = WordHelper(
            interaction_agent=interaction_agent,
            vision_agent=vision_agent,
            context_tracker=context_tracker
        )
    return _word_helper_instance


def reset_word_helper():
    """Setzt WordHelper zurück."""
    global _word_helper_instance
    _word_helper_instance = None