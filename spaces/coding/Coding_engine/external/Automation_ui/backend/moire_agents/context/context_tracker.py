"""
Context Tracker - Tracks cursor position, selection state, and app context.

Provides "Feingefühl" (fine-control) for text operations:
- Where is the cursor?
- What is selected?
- Which app is active?
- What's the current state after each action?
"""

import asyncio
import logging
import time
from typing import Optional, Dict, Any, List, TYPE_CHECKING
from dataclasses import dataclass, field
from enum import Enum

from .selection_manager import SelectionManager, SelectionSnapshot, get_selection_manager

if TYPE_CHECKING:
    from ..agents.interaction import InteractionAgent
    from ..agents.vision_agent import VisionAnalystAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class CursorPosition:
    """Cursor-Position im Screen und im Text."""
    # Screen-Koordinaten
    screen_x: int = 0
    screen_y: int = 0
    
    # Text-Position (wenn in Textfeld)
    line: Optional[int] = None
    column: Optional[int] = None
    
    # Relativ zum aktiven Element
    element_x: Optional[int] = None
    element_y: Optional[int] = None
    
    # Metadaten
    timestamp: float = field(default_factory=time.time)
    source: str = "unknown"  # 'mouse', 'vision', 'api'
    confidence: float = 0.0
    
    @property
    def has_text_position(self) -> bool:
        return self.line is not None and self.column is not None


@dataclass
class SelectionState:
    """Zustand der Text-Selektion."""
    is_active: bool = False
    text: Optional[str] = None
    
    # Position
    start_x: Optional[int] = None
    start_y: Optional[int] = None
    end_x: Optional[int] = None
    end_y: Optional[int] = None
    
    # Text-Metriken
    char_count: int = 0
    word_count: int = 0
    line_count: int = 0
    
    # Metadaten
    timestamp: float = field(default_factory=time.time)
    
    def __post_init__(self):
        if self.text:
            self.char_count = len(self.text)
            self.word_count = len(self.text.split())
            self.line_count = len(self.text.splitlines())
    
    @property
    def has_selection(self) -> bool:
        return self.is_active and self.char_count > 0


class AppType(Enum):
    """Bekannte Anwendungstypen."""
    WORD = "word"
    NOTEPAD = "notepad"
    EXCEL = "excel"
    CHROME = "chrome"
    VSCODE = "vscode"
    EXPLORER = "explorer"
    UNKNOWN = "unknown"


@dataclass
class AppContext:
    """Kontext der aktiven Anwendung."""
    app_type: AppType = AppType.UNKNOWN
    app_name: str = ""
    window_title: str = ""
    
    # UI-Zustand
    is_dialog_open: bool = False
    dialog_title: Optional[str] = None
    
    # Für Text-Editoren
    is_text_focused: bool = False
    has_ribbon: bool = False  # Word, Excel
    
    # Formatierungs-Zustand (Word)
    is_bold_active: bool = False
    is_italic_active: bool = False
    is_underline_active: bool = False
    font_name: Optional[str] = None
    font_size: Optional[int] = None
    
    timestamp: float = field(default_factory=time.time)
    
    @property
    def is_word(self) -> bool:
        return self.app_type == AppType.WORD
    
    @property
    def is_text_editor(self) -> bool:
        return self.app_type in [AppType.WORD, AppType.NOTEPAD, AppType.VSCODE]


@dataclass
class ContextState:
    """Gesamter Kontext-Zustand."""
    cursor: CursorPosition
    selection: SelectionState
    app: AppContext
    
    # History
    action_history: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    version: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary für Logging/Debugging."""
        return {
            'cursor': {
                'screen': (self.cursor.screen_x, self.cursor.screen_y),
                'text_pos': (self.cursor.line, self.cursor.column) if self.cursor.has_text_position else None,
            },
            'selection': {
                'active': self.selection.is_active,
                'char_count': self.selection.char_count,
                'preview': self.selection.text[:50] + '...' if self.selection.text and len(self.selection.text) > 50 else self.selection.text,
            },
            'app': {
                'type': self.app.app_type.value,
                'title': self.app.window_title,
                'dialog': self.app.dialog_title if self.app.is_dialog_open else None,
            },
            'version': self.version,
            'timestamp': self.timestamp
        }


class ContextTracker:
    """
    Context Tracker - Verfolgt Cursor, Selektion und App-Kontext.
    
    Aktualisiert sich nach jeder Aktion für präzises "Feingefühl".
    """
    
    def __init__(
        self,
        selection_manager: Optional[SelectionManager] = None,
        interaction_agent: Optional['InteractionAgent'] = None,
        vision_agent: Optional['VisionAnalystAgent'] = None
    ):
        self.selection_manager = selection_manager or get_selection_manager()
        self.interaction_agent = interaction_agent
        self.vision_agent = vision_agent
        
        # State
        self._cursor = CursorPosition()
        self._selection = SelectionState()
        self._app = AppContext()
        self._version = 0
        self._action_history: List[str] = []
        
        # Callbacks
        self._on_selection_change: List[callable] = []
        self._on_app_change: List[callable] = []
    
    def set_interaction_agent(self, agent: 'InteractionAgent'):
        """Setzt InteractionAgent."""
        self.interaction_agent = agent
    
    def set_vision_agent(self, agent: 'VisionAnalystAgent'):
        """Setzt VisionAgent."""
        self.vision_agent = agent
    
    # ==================== State Getters ====================
    
    def get_state(self) -> ContextState:
        """Gibt aktuellen Gesamtzustand zurück."""
        return ContextState(
            cursor=self._cursor,
            selection=self._selection,
            app=self._app,
            action_history=self._action_history[-10:],
            timestamp=time.time(),
            version=self._version
        )
    
    @property
    def cursor(self) -> CursorPosition:
        return self._cursor
    
    @property
    def selection(self) -> SelectionState:
        return self._selection
    
    @property
    def app(self) -> AppContext:
        return self._app
    
    @property
    def has_selection(self) -> bool:
        return self._selection.has_selection
    
    @property
    def selected_text(self) -> Optional[str]:
        return self._selection.text if self._selection.is_active else None
    
    # ==================== State Updates ====================
    
    async def update_after_action(
        self,
        action_type: str,
        action_params: Optional[Dict[str, Any]] = None
    ) -> ContextState:
        """
        Aktualisiert Kontext nach einer Aktion.
        
        Args:
            action_type: Art der Aktion (click, type, press_key, etc.)
            action_params: Parameter der Aktion
        
        Returns:
            Aktualisierter ContextState
        """
        self._version += 1
        self._action_history.append(f"{action_type}:{time.time()}")
        
        params = action_params or {}
        
        logger.debug(f"Updating context after: {action_type}")
        
        # Update Cursor basierend auf Aktion
        if action_type == 'click':
            x = params.get('x') or params.get('coords', (0, 0))[0]
            y = params.get('y') or params.get('coords', (0, 0))[1]
            self._cursor.screen_x = x
            self._cursor.screen_y = y
            self._cursor.source = 'click'
            self._cursor.timestamp = time.time()
            
            # Click hebt möglicherweise Selektion auf
            # (außer es ist ein Shift+Click)
            if not params.get('shift', False):
                self._selection = SelectionState(is_active=False)
        
        elif action_type == 'type':
            # Nach Tippen: Selektion ist weg (Text wurde ersetzt)
            self._selection = SelectionState(is_active=False)
        
        elif action_type in ['press_key', 'hotkey']:
            key = params.get('key', params.get('keys', ''))
            
            # Bestimmte Keys ändern Selektion
            if 'ctrl+a' in str(key).lower():
                # Alles markiert - müssen wir via Clipboard prüfen
                await self._capture_selection()
            elif 'ctrl+c' in str(key).lower() or 'ctrl+x' in str(key).lower():
                # Kopiert/Ausgeschnitten - Selektion unverändert, Clipboard aktualisiert
                pass
            elif 'escape' in str(key).lower():
                # Selektion aufgehoben
                self._selection = SelectionState(is_active=False)
        
        elif action_type in ['select_text', 'triple_click']:
            # Text wurde markiert - erfasse Selektion
            await self._capture_selection()
        
        elif action_type == 'drag':
            # Drag kann Selektion erstellen
            start = params.get('start', (0, 0))
            end = params.get('end', (0, 0))
            self._selection.start_x = start[0] if isinstance(start, tuple) else start.get('x', 0)
            self._selection.start_y = start[1] if isinstance(start, tuple) else start.get('y', 0)
            self._selection.end_x = end[0] if isinstance(end, tuple) else end.get('x', 0)
            self._selection.end_y = end[1] if isinstance(end, tuple) else end.get('y', 0)
            await self._capture_selection()
        
        return self.get_state()
    
    async def _capture_selection(self) -> Optional[SelectionSnapshot]:
        """Erfasst aktuelle Selektion via Clipboard."""
        try:
            snapshot = await self.selection_manager.capture_selection(
                interaction_agent=self.interaction_agent,
                source='context_tracker'
            )
            
            if snapshot and snapshot.char_count > 0:
                self._selection = SelectionState(
                    is_active=True,
                    text=snapshot.text,
                    char_count=snapshot.char_count,
                    word_count=snapshot.word_count,
                    line_count=snapshot.line_count,
                    timestamp=snapshot.timestamp
                )
                
                # Callbacks
                for callback in self._on_selection_change:
                    try:
                        callback(self._selection)
                    except Exception as e:
                        logger.warning(f"Selection callback error: {e}")
                
                return snapshot
            else:
                self._selection = SelectionState(is_active=False)
                return None
        
        except Exception as e:
            logger.error(f"Selection capture failed: {e}")
            return None
    
    async def update_cursor_from_mouse(self) -> CursorPosition:
        """Aktualisiert Cursor von aktueller Mausposition."""
        if self.interaction_agent:
            pos = self.interaction_agent.get_mouse_position()
            self._cursor.screen_x = pos[0]
            self._cursor.screen_y = pos[1]
            self._cursor.source = 'mouse'
            self._cursor.timestamp = time.time()
        
        return self._cursor
    
    async def update_app_context_from_vision(
        self,
        screenshot_bytes: bytes
    ) -> AppContext:
        """
        Aktualisiert App-Kontext via Vision-Analyse.
        
        Args:
            screenshot_bytes: Screenshot für Analyse
        
        Returns:
            Aktualisierter AppContext
        """
        if not self.vision_agent or not self.vision_agent.is_available():
            return self._app
        
        try:
            from PIL import Image
            from io import BytesIO
            
            image = Image.open(BytesIO(screenshot_bytes))
            
            # Vision-Analyse für App-Kontext
            analysis = await self.vision_agent.analyze_screenshot(
                image,
                context="Identifiziere die aktive Anwendung und UI-Zustand"
            )
            
            if analysis.success:
                # Parse App aus Description
                desc_lower = analysis.description.lower()
                
                if 'word' in desc_lower or 'winword' in desc_lower:
                    self._app.app_type = AppType.WORD
                    self._app.app_name = "Microsoft Word"
                    self._app.has_ribbon = True
                elif 'notepad' in desc_lower or 'editor' in desc_lower:
                    self._app.app_type = AppType.NOTEPAD
                    self._app.app_name = "Notepad"
                elif 'excel' in desc_lower:
                    self._app.app_type = AppType.EXCEL
                    self._app.app_name = "Microsoft Excel"
                    self._app.has_ribbon = True
                elif 'chrome' in desc_lower or 'browser' in desc_lower:
                    self._app.app_type = AppType.CHROME
                    self._app.app_name = "Google Chrome"
                elif 'code' in desc_lower or 'vscode' in desc_lower:
                    self._app.app_type = AppType.VSCODE
                    self._app.app_name = "Visual Studio Code"
                
                # Prüfe auf Dialog
                if 'dialog' in desc_lower or 'popup' in desc_lower or 'fenster' in desc_lower:
                    self._app.is_dialog_open = True
                
                self._app.timestamp = time.time()
                
                # Callbacks
                for callback in self._on_app_change:
                    try:
                        callback(self._app)
                    except Exception as e:
                        logger.warning(f"App change callback error: {e}")
        
        except Exception as e:
            logger.error(f"App context update failed: {e}")
        
        return self._app
    
    # ==================== Selection Shortcuts ====================
    
    async def get_selected_text(self) -> Optional[str]:
        """
        Gibt aktuell markierten Text zurück.
        
        Erfasst frischen Text via Clipboard falls nötig.
        """
        # Wenn Selektion älter als 2 Sekunden, neu erfassen
        if self._selection.timestamp < time.time() - 2:
            await self._capture_selection()
        
        return self._selection.text if self._selection.is_active else None
    
    async def ensure_no_selection(self) -> bool:
        """
        Stellt sicher dass nichts markiert ist.
        
        Returns:
            True wenn keine Selektion (mehr) aktiv
        """
        if self._selection.is_active:
            if self.interaction_agent:
                await self.interaction_agent.press_key('escape')
                await asyncio.sleep(0.1)
            self._selection = SelectionState(is_active=False)
        
        return not self._selection.is_active
    
    # ==================== Callbacks ====================
    
    def on_selection_change(self, callback: callable):
        """Registriert Callback für Selektions-Änderungen."""
        self._on_selection_change.append(callback)
    
    def on_app_change(self, callback: callable):
        """Registriert Callback für App-Änderungen."""
        self._on_app_change.append(callback)
    
    # ==================== Utilities ====================
    
    def get_stats(self) -> Dict[str, Any]:
        """Gibt Statistiken zurück."""
        return {
            'version': self._version,
            'cursor': {
                'x': self._cursor.screen_x,
                'y': self._cursor.screen_y,
                'source': self._cursor.source
            },
            'selection': {
                'active': self._selection.is_active,
                'chars': self._selection.char_count,
                'words': self._selection.word_count
            },
            'app': {
                'type': self._app.app_type.value,
                'name': self._app.app_name
            },
            'action_count': len(self._action_history)
        }
    
    def reset(self):
        """Setzt Tracker zurück."""
        self._cursor = CursorPosition()
        self._selection = SelectionState()
        self._app = AppContext()
        self._version = 0
        self._action_history = []


# Singleton
_context_tracker_instance: Optional[ContextTracker] = None


def get_context_tracker(
    selection_manager: Optional[SelectionManager] = None,
    interaction_agent: Optional['InteractionAgent'] = None,
    vision_agent: Optional['VisionAnalystAgent'] = None
) -> ContextTracker:
    """Gibt Singleton-Instanz des ContextTrackers zurück."""
    global _context_tracker_instance
    if _context_tracker_instance is None:
        _context_tracker_instance = ContextTracker(
            selection_manager=selection_manager,
            interaction_agent=interaction_agent,
            vision_agent=vision_agent
        )
    return _context_tracker_instance


def reset_context_tracker():
    """Setzt ContextTracker zurück."""
    global _context_tracker_instance
    if _context_tracker_instance:
        _context_tracker_instance.reset()
    _context_tracker_instance = None