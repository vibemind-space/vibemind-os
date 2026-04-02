"""
Interaction Agent - Desktop-Automation mit PyAutoGUI

Verantwortlich für:
- Mausaktionen (Klicks, Doppelklicks, Rechtsklicks)
- Tastatureingaben
- Scrollen
- Drag & Drop
- Screenshot-Verifikation
- Action Visualization via MoireServer
"""

import asyncio
import logging
import time
from typing import Optional, Dict, Any, Tuple, Union, List
from dataclasses import dataclass
from enum import Enum

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# PyAutoGUI importieren
try:
    import pyautogui
    # Sicherheitseinstellungen
    pyautogui.FAILSAFE = True  # Ecke für Notfall-Stop
    pyautogui.PAUSE = 0.1  # Kurze Pause zwischen Aktionen
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False
    logger.warning("PyAutoGUI not available. Install with: pip install pyautogui")


class MouseButton(Enum):
    """Maustaste."""
    LEFT = "left"
    RIGHT = "right"
    MIDDLE = "middle"


class ScrollDirection(Enum):
    """Scroll-Richtung."""
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"


@dataclass
class ActionResult:
    """Ergebnis einer Aktion."""
    success: bool
    action: str
    duration_ms: float
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class InteractionAgent:
    """
    Interaction Agent - Führt Desktop-Aktionen aus.
    
    Verwendet PyAutoGUI für:
    - Klicks auf Koordinaten oder Elemente
    - Tastatureingaben
    - Scrollen
    - Fenster-Navigation
    
    Reports actions to MoireServer for visualization.
    """
    
    def __init__(
        self,
        move_duration: float = 0.3,
        click_interval: float = 0.1,
        type_interval: float = 0.02,
        verify_actions: bool = True,
        moire_client: Optional[Any] = None,
        report_actions: bool = True
    ):
        """
        Initialisiert den Interaction Agent.
        
        Args:
            move_duration: Dauer für Mausbewegungen (Sekunden)
            click_interval: Mindestabstand zwischen Klicks
            type_interval: Zeit zwischen Tastenanschlägen
            verify_actions: Ob Aktionen verifiziert werden sollen
            moire_client: Optional MoireWebSocketClient for action reporting
            report_actions: Whether to report actions for visualization
        """
        self.move_duration = move_duration
        self.click_interval = click_interval
        self.type_interval = type_interval
        self.verify_actions = verify_actions
        self.moire_client = moire_client
        self.report_actions = report_actions
        
        self.last_action_time = 0
        self.action_history: list = []
        
        if not PYAUTOGUI_AVAILABLE:
            logger.error("PyAutoGUI not available - actions will fail")
    
    def set_moire_client(self, client: Any):
        """Sets the MoireWebSocketClient for action reporting."""
        self.moire_client = client
        logger.info("MoireClient set for action reporting")
    
    async def _report_to_moire(
        self,
        action_type: str,
        x: int,
        y: int,
        end_x: Optional[int] = None,
        end_y: Optional[int] = None,
        button: Optional[str] = None,
        text: Optional[str] = None
    ):
        """Reports action to MoireServer for visualization."""
        if not self.report_actions or not self.moire_client:
            return
        
        try:
            if hasattr(self.moire_client, 'report_action'):
                await self.moire_client.report_action(
                    action_type=action_type,
                    x=x,
                    y=y,
                    end_x=end_x,
                    end_y=end_y,
                    button=button,
                    text=text,
                    agent_id='interaction_agent'
                )
        except Exception as e:
            logger.debug(f"Failed to report action: {e}")
    
    def _ensure_available(self) -> bool:
        """Prüft ob PyAutoGUI verfügbar ist."""
        if not PYAUTOGUI_AVAILABLE:
            logger.error("PyAutoGUI not available")
            return False
        return True
    
    def _record_action(self, action: str, params: Dict[str, Any]):
        """Zeichnet Aktion für History auf."""
        self.action_history.append({
            'action': action,
            'params': params,
            'timestamp': time.time()
        })
        # Begrenze History
        if len(self.action_history) > 100:
            self.action_history = self.action_history[-100:]
    
    def _get_coords(
        self,
        target: Union[Tuple[int, int], Dict[str, Any], str, None]
    ) -> Optional[Tuple[int, int]]:
        """Extrahiert Koordinaten aus verschiedenen Formaten."""
        if target is None:
            return None
        
        if isinstance(target, tuple) and len(target) == 2:
            return (int(target[0]), int(target[1]))
        
        if isinstance(target, dict):
            # Element mit center
            if 'center' in target:
                center = target['center']
                if isinstance(center, tuple):
                    return (int(center[0]), int(center[1]))
                elif isinstance(center, dict):
                    return (int(center.get('x', 0)), int(center.get('y', 0)))
            # Element mit x, y
            if 'x' in target and 'y' in target:
                return (int(target['x']), int(target['y']))
        
        return None
    
    # ==================== Mouse Actions ====================
    
    async def click(
        self,
        target: Union[Tuple[int, int], Dict[str, Any], None] = None,
        button: MouseButton = MouseButton.LEFT,
        clicks: int = 1
    ) -> Dict[str, Any]:
        """
        Führt einen Klick aus.
        
        Args:
            target: Zielkoordinaten oder Element-Dict
            button: Maustaste
            clicks: Anzahl der Klicks (1=single, 2=double)
        
        Returns:
            ActionResult als Dict
        """
        if not self._ensure_available():
            return {'success': False, 'error': 'PyAutoGUI not available'}
        
        start_time = time.time()
        
        try:
            coords = self._get_coords(target)
            
            if coords:
                # Bewege Maus zu Koordinaten
                pyautogui.moveTo(coords[0], coords[1], duration=self.move_duration)
                # Kurze Pause für Stabilität
                await asyncio.sleep(0.05)
            
            # Klick ausführen
            pyautogui.click(
                x=coords[0] if coords else None,
                y=coords[1] if coords else None,
                clicks=clicks,
                interval=self.click_interval,
                button=button.value
            )
            
            duration_ms = (time.time() - start_time) * 1000
            
            self._record_action('click', {
                'coords': coords,
                'button': button.value,
                'clicks': clicks
            })
            
            logger.info(f"Click at {coords} ({button.value}, {clicks}x)")
            
            # Report to MoireServer for visualization
            if coords:
                action_type = 'double_click' if clicks == 2 else ('right_click' if button == MouseButton.RIGHT else 'click')
                await self._report_to_moire(action_type, coords[0], coords[1], button=button.value)
            
            return {
                'success': True,
                'action': 'click',
                'duration_ms': duration_ms,
                'data': {
                    'coords': coords,
                    'button': button.value,
                    'clicks': clicks
                }
            }
        
        except Exception as e:
            logger.error(f"Click failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'action': 'click'
            }
    
    async def double_click(
        self,
        target: Union[Tuple[int, int], Dict[str, Any], None] = None
    ) -> Dict[str, Any]:
        """Führt Doppelklick aus."""
        return await self.click(target, clicks=2)
    
    async def right_click(
        self,
        target: Union[Tuple[int, int], Dict[str, Any], None] = None
    ) -> Dict[str, Any]:
        """Führt Rechtsklick aus."""
        return await self.click(target, button=MouseButton.RIGHT)
    
    async def move_to(
        self,
        target: Union[Tuple[int, int], Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Bewegt Maus zu Position.
        
        Args:
            target: Zielkoordinaten
        
        Returns:
            ActionResult als Dict
        """
        if not self._ensure_available():
            return {'success': False, 'error': 'PyAutoGUI not available'}
        
        start_time = time.time()
        
        try:
            coords = self._get_coords(target)
            if not coords:
                return {'success': False, 'error': 'Invalid target coordinates'}
            
            pyautogui.moveTo(coords[0], coords[1], duration=self.move_duration)
            
            duration_ms = (time.time() - start_time) * 1000
            
            self._record_action('move', {'coords': coords})
            logger.info(f"Moved to {coords}")
            
            return {
                'success': True,
                'action': 'move',
                'duration_ms': duration_ms,
                'data': {'coords': coords}
            }
        
        except Exception as e:
            logger.error(f"Move failed: {e}")
            return {'success': False, 'error': str(e), 'action': 'move'}
    
    async def drag(
        self,
        start: Union[Tuple[int, int], Dict[str, Any]],
        end: Union[Tuple[int, int], Dict[str, Any]],
        button: MouseButton = MouseButton.LEFT,
        duration: float = 0.5
    ) -> Dict[str, Any]:
        """
        Führt Drag & Drop aus.
        
        Args:
            start: Startposition
            end: Endposition
            button: Maustaste
            duration: Dauer der Bewegung
        
        Returns:
            ActionResult als Dict
        """
        if not self._ensure_available():
            return {'success': False, 'error': 'PyAutoGUI not available'}
        
        start_time = time.time()
        
        try:
            start_coords = self._get_coords(start)
            end_coords = self._get_coords(end)
            
            if not start_coords or not end_coords:
                return {'success': False, 'error': 'Invalid coordinates'}
            
            # Bewege zu Start
            pyautogui.moveTo(start_coords[0], start_coords[1], duration=0.2)
            await asyncio.sleep(0.05)
            
            # Drag zu End
            pyautogui.drag(
                end_coords[0] - start_coords[0],
                end_coords[1] - start_coords[1],
                duration=duration,
                button=button.value
            )
            
            duration_ms = (time.time() - start_time) * 1000
            
            self._record_action('drag', {
                'start': start_coords,
                'end': end_coords,
                'button': button.value
            })
            
            logger.info(f"Dragged from {start_coords} to {end_coords}")
            
            # Report to MoireServer
            await self._report_to_moire(
                'drag', 
                start_coords[0], start_coords[1],
                end_x=end_coords[0], end_y=end_coords[1],
                button=button.value
            )
            
            return {
                'success': True,
                'action': 'drag',
                'duration_ms': duration_ms,
                'data': {
                    'start': start_coords,
                    'end': end_coords
                }
            }
        
        except Exception as e:
            logger.error(f"Drag failed: {e}")
            return {'success': False, 'error': str(e), 'action': 'drag'}
    
    # ==================== Keyboard Actions ====================
    
    async def type_text(
        self,
        text: str,
        interval: Optional[float] = None,
        use_clipboard: bool = True  # NEU: Standard auf True für Unicode-Support
    ) -> Dict[str, Any]:
        """
        Gibt Text ein.
        
        Args:
            text: Einzugebender Text
            interval: Zeit zwischen Tastenanschlägen (nur wenn use_clipboard=False)
            use_clipboard: Ob Clipboard für Unicode-Support verwendet werden soll
        
        Returns:
            ActionResult als Dict
        """
        if not self._ensure_available():
            return {'success': False, 'error': 'PyAutoGUI not available'}
        
        start_time = time.time()
        
        try:
            # Prüfe ob Text Unicode/Umlaute enthält
            has_unicode = any(ord(c) > 127 for c in text)
            
            if use_clipboard or has_unicode:
                # Clipboard-Methode für korrekte Unicode-Unterstützung
                result = await self._type_via_clipboard(text)
                if result['success']:
                    duration_ms = (time.time() - start_time) * 1000
                    self._record_action('type', {'text': text[:50], 'length': len(text), 'method': 'clipboard'})
                    logger.info(f"Typed {len(text)} characters via clipboard")
                    return {
                        'success': True,
                        'action': 'type',
                        'duration_ms': duration_ms,
                        'data': {'text_length': len(text), 'method': 'clipboard'}
                    }
                # Fallback wenn Clipboard fehlschlägt
                logger.warning("Clipboard method failed, falling back to direct typing")
            
            # Direkte Eingabe (nur ASCII)
            type_interval = interval or self.type_interval
            pyautogui.write(text, interval=type_interval)
            
            duration_ms = (time.time() - start_time) * 1000
            
            self._record_action('type', {'text': text[:50], 'length': len(text), 'method': 'direct'})
            logger.info(f"Typed {len(text)} characters directly")
            
            return {
                'success': True,
                'action': 'type',
                'duration_ms': duration_ms,
                'data': {'text_length': len(text), 'method': 'direct'}
            }
        
        except Exception as e:
            logger.error(f"Type failed: {e}")
            return {'success': False, 'error': str(e), 'action': 'type'}
    
    async def _type_via_clipboard(self, text: str) -> Dict[str, Any]:
        """
        Gibt Text via Clipboard ein (unterstützt Unicode/Umlaute).
        
        Kopiert Text in Zwischenablage und fügt mit Ctrl+V ein.
        """
        try:
            import subprocess
            import platform
            
            system = platform.system()
            
            if system == 'Windows':
                # Windows: powershell für Clipboard
                # Escapen von Sonderzeichen für PowerShell
                escaped_text = text.replace('`', '``').replace('"', '`"').replace('$', '`$')
                
                # Verwende PowerShell mit stdin für bessere Handhabung
                process = subprocess.Popen(
                    ['powershell', '-Command', 'Set-Clipboard -Value $input'],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8'
                )
                stdout, stderr = process.communicate(input=text)
                
                if process.returncode != 0:
                    logger.error(f"Clipboard set failed: {stderr}")
                    return {'success': False, 'error': f'Clipboard failed: {stderr}'}
            
            elif system == 'Darwin':
                # macOS: pbcopy
                process = subprocess.Popen(
                    ['pbcopy'],
                    stdin=subprocess.PIPE,
                    text=True,
                    encoding='utf-8'
                )
                process.communicate(input=text)
            
            else:
                # Linux: xclip oder xsel
                try:
                    process = subprocess.Popen(
                        ['xclip', '-selection', 'clipboard'],
                        stdin=subprocess.PIPE,
                        text=True,
                        encoding='utf-8'
                    )
                    process.communicate(input=text)
                except FileNotFoundError:
                    process = subprocess.Popen(
                        ['xsel', '--clipboard', '--input'],
                        stdin=subprocess.PIPE,
                        text=True,
                        encoding='utf-8'
                    )
                    process.communicate(input=text)
            
            # Kurze Pause damit Clipboard bereit ist
            await asyncio.sleep(0.05)
            
            # Ctrl+V zum Einfügen
            pyautogui.hotkey('ctrl', 'v')
            
            # Kurze Pause nach Einfügen
            await asyncio.sleep(0.1)
            
            return {'success': True}
        
        except Exception as e:
            logger.error(f"Clipboard type failed: {e}")
            return {'success': False, 'error': str(e)}
    
    async def type_text_chunked(
        self,
        text: str,
        chunk_size: int = 500,
        chunk_delay: float = 0.5
    ) -> Dict[str, Any]:
        """
        Gibt langen Text in Chunks ein (für sehr lange Texte).
        
        Args:
            text: Einzugebender Text
            chunk_size: Größe jedes Chunks
            chunk_delay: Pause zwischen Chunks
        
        Returns:
            ActionResult als Dict
        """
        if not self._ensure_available():
            return {'success': False, 'error': 'PyAutoGUI not available'}
        
        start_time = time.time()
        total_chars = 0
        
        try:
            # Teile Text in Chunks
            chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
            
            for i, chunk in enumerate(chunks):
                logger.info(f"Typing chunk {i+1}/{len(chunks)} ({len(chunk)} chars)")
                
                result = await self.type_text(chunk, use_clipboard=True)
                if not result.get('success'):
                    return result
                
                total_chars += len(chunk)
                
                # Pause zwischen Chunks
                if i < len(chunks) - 1:
                    await asyncio.sleep(chunk_delay)
            
            duration_ms = (time.time() - start_time) * 1000
            
            self._record_action('type_chunked', {
                'total_length': len(text),
                'chunks': len(chunks)
            })
            
            logger.info(f"Typed {total_chars} characters in {len(chunks)} chunks")
            
            return {
                'success': True,
                'action': 'type_chunked',
                'duration_ms': duration_ms,
                'data': {
                    'text_length': total_chars,
                    'chunks': len(chunks)
                }
            }
        
        except Exception as e:
            logger.error(f"Chunked type failed: {e}")
            return {'success': False, 'error': str(e), 'action': 'type_chunked'}
    
    async def press_key(
        self,
        key: str,
        presses: int = 1,
        interval: float = 0.1
    ) -> Dict[str, Any]:
        """
        Drückt eine Taste.
        
        Args:
            key: Tastenname (enter, tab, escape, etc.)
            presses: Anzahl der Tastendrücke
            interval: Zeit zwischen Drücken
        
        Returns:
            ActionResult als Dict
        """
        if not self._ensure_available():
            return {'success': False, 'error': 'PyAutoGUI not available'}
        
        start_time = time.time()
        
        try:
            pyautogui.press(key, presses=presses, interval=interval)
            
            duration_ms = (time.time() - start_time) * 1000
            
            self._record_action('press', {'key': key, 'presses': presses})
            logger.info(f"Pressed {key} {presses}x")
            
            return {
                'success': True,
                'action': 'press',
                'duration_ms': duration_ms,
                'data': {'key': key, 'presses': presses}
            }
        
        except Exception as e:
            logger.error(f"Press failed: {e}")
            return {'success': False, 'error': str(e), 'action': 'press'}
    
    async def hotkey(self, *keys: str) -> Dict[str, Any]:
        """
        Drückt Tastenkombination.
        
        Args:
            *keys: Tasten der Kombination (z.B. 'ctrl', 'c')
        
        Returns:
            ActionResult als Dict
        """
        if not self._ensure_available():
            return {'success': False, 'error': 'PyAutoGUI not available'}
        
        start_time = time.time()
        
        try:
            pyautogui.hotkey(*keys)
            
            duration_ms = (time.time() - start_time) * 1000
            
            key_combo = '+'.join(keys)
            self._record_action('hotkey', {'keys': key_combo})
            logger.info(f"Pressed hotkey: {key_combo}")
            
            return {
                'success': True,
                'action': 'hotkey',
                'duration_ms': duration_ms,
                'data': {'keys': key_combo}
            }
        
        except Exception as e:
            logger.error(f"Hotkey failed: {e}")
            return {'success': False, 'error': str(e), 'action': 'hotkey'}
    
    # ==================== Scroll Actions ====================
    
    async def scroll(
        self,
        direction: Union[str, ScrollDirection] = ScrollDirection.DOWN,
        amount: int = 3,
        target: Optional[Union[Tuple[int, int], Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Scrollt in eine Richtung.
        
        Args:
            direction: Scroll-Richtung (up/down/left/right)
            amount: Scroll-Menge (Zeilen)
            target: Optionale Position zum Scrollen
        
        Returns:
            ActionResult als Dict
        """
        if not self._ensure_available():
            return {'success': False, 'error': 'PyAutoGUI not available'}
        
        start_time = time.time()
        
        try:
            # Konvertiere String zu Enum
            if isinstance(direction, str):
                direction = ScrollDirection(direction.lower())
            
            coords = self._get_coords(target)
            
            # Bewege zu Position wenn angegeben
            if coords:
                pyautogui.moveTo(coords[0], coords[1], duration=0.1)
                await asyncio.sleep(0.05)
            
            # Scroll je nach Richtung
            if direction == ScrollDirection.UP:
                pyautogui.scroll(amount)
            elif direction == ScrollDirection.DOWN:
                pyautogui.scroll(-amount)
            elif direction == ScrollDirection.LEFT:
                pyautogui.hscroll(-amount)
            elif direction == ScrollDirection.RIGHT:
                pyautogui.hscroll(amount)
            
            duration_ms = (time.time() - start_time) * 1000
            
            self._record_action('scroll', {
                'direction': direction.value,
                'amount': amount,
                'coords': coords
            })
            
            logger.info(f"Scrolled {direction.value} by {amount}")
            
            return {
                'success': True,
                'action': 'scroll',
                'duration_ms': duration_ms,
                'data': {
                    'direction': direction.value,
                    'amount': amount
                }
            }
        
        except Exception as e:
            logger.error(f"Scroll failed: {e}")
            return {'success': False, 'error': str(e), 'action': 'scroll'}
    
    # ==================== Utility Actions ====================
    
    async def wait(self, seconds: float) -> Dict[str, Any]:
        """
        Wartet eine bestimmte Zeit.
        
        Args:
            seconds: Wartezeit in Sekunden
        
        Returns:
            ActionResult als Dict
        """
        start_time = time.time()
        await asyncio.sleep(seconds)
        
        self._record_action('wait', {'seconds': seconds})
        logger.info(f"Waited {seconds}s")
        
        return {
            'success': True,
            'action': 'wait',
            'duration_ms': seconds * 1000,
            'data': {'seconds': seconds}
        }
    
    def get_mouse_position(self) -> Tuple[int, int]:
        """Gibt aktuelle Mausposition zurück."""
        if PYAUTOGUI_AVAILABLE:
            pos = pyautogui.position()
            return (pos.x, pos.y)
        return (0, 0)
    
    def get_screen_size(self) -> Tuple[int, int]:
        """Gibt Bildschirmgröße zurück."""
        if PYAUTOGUI_AVAILABLE:
            size = pyautogui.size()
            return (size.width, size.height)
        return (1920, 1080)
    
    def get_action_history(self, limit: int = 10) -> list:
        """Gibt letzte Aktionen zurück."""
        return self.action_history[-limit:]
    
    # ==================== Common Shortcuts ====================
    
    async def copy(self) -> Dict[str, Any]:
        """Strg+C"""
        return await self.hotkey('ctrl', 'c')
    
    async def paste(self) -> Dict[str, Any]:
        """Strg+V"""
        return await self.hotkey('ctrl', 'v')
    
    async def cut(self) -> Dict[str, Any]:
        """Strg+X"""
        return await self.hotkey('ctrl', 'x')
    
    async def undo(self) -> Dict[str, Any]:
        """Strg+Z"""
        return await self.hotkey('ctrl', 'z')
    
    async def redo(self) -> Dict[str, Any]:
        """Strg+Y"""
        return await self.hotkey('ctrl', 'y')
    
    async def select_all(self) -> Dict[str, Any]:
        """Strg+A"""
        return await self.hotkey('ctrl', 'a')
    
    async def save(self) -> Dict[str, Any]:
        """Strg+S"""
        return await self.hotkey('ctrl', 's')
    
    async def close_window(self) -> Dict[str, Any]:
        """Alt+F4"""
        return await self.hotkey('alt', 'F4')
    
    async def switch_window(self) -> Dict[str, Any]:
        """Alt+Tab"""
        return await self.hotkey('alt', 'tab')
    
    async def open_start_menu(self) -> Dict[str, Any]:
        """Windows-Taste"""
        return await self.press_key('win')
    
    async def open_run_dialog(self) -> Dict[str, Any]:
        """Win+R"""
        return await self.hotkey('win', 'r')
    
    # ==================== Text Selection & Replacement ====================
    
    async def select_text_by_coords(
        self,
        start: Tuple[int, int],
        end: Tuple[int, int]
    ) -> Dict[str, Any]:
        """
        Markiert Text durch Drag von Start- zu End-Koordinaten.
        
        Args:
            start: Startkoordinaten (x, y) - Anfang des Texts
            end: Endkoordinaten (x, y) - Ende des Texts
        
        Returns:
            ActionResult als Dict
        """
        if not self._ensure_available():
            return {'success': False, 'error': 'PyAutoGUI not available'}
        
        start_time = time.time()
        
        try:
            # Bewege zu Startposition
            pyautogui.moveTo(start[0], start[1], duration=0.2)
            await asyncio.sleep(0.05)
            
            # Klicke und halte
            pyautogui.mouseDown(button='left')
            await asyncio.sleep(0.05)
            
            # Ziehe zu Endposition
            pyautogui.moveTo(end[0], end[1], duration=0.3)
            await asyncio.sleep(0.05)
            
            # Lasse los
            pyautogui.mouseUp(button='left')
            
            duration_ms = (time.time() - start_time) * 1000
            
            self._record_action('select_text', {
                'start': start,
                'end': end
            })
            
            logger.info(f"Selected text from {start} to {end}")
            
            return {
                'success': True,
                'action': 'select_text',
                'duration_ms': duration_ms,
                'data': {'start': start, 'end': end}
            }
        
        except Exception as e:
            logger.error(f"Text selection failed: {e}")
            return {'success': False, 'error': str(e), 'action': 'select_text'}
    
    async def select_text_by_elements(
        self,
        start_element: Dict[str, Any],
        end_element: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Markiert Text basierend auf UI-Elementen aus OCR.
        
        Args:
            start_element: Erstes Element (mit bounds oder center)
            end_element: Letztes Element (optional, wenn None wird nur start_element markiert)
        
        Returns:
            ActionResult als Dict
        """
        # Hole Start-Koordinaten (linker Rand des Elements)
        start_bounds = start_element.get('bounds', {})
        start_x = start_bounds.get('x', start_element.get('center', {}).get('x', 0))
        start_y = start_bounds.get('y', 0) + start_bounds.get('height', 0) // 2
        
        if end_element:
            # Hole End-Koordinaten (rechter Rand des Elements)
            end_bounds = end_element.get('bounds', {})
            end_x = end_bounds.get('x', 0) + end_bounds.get('width', 0)
            end_y = end_bounds.get('y', 0) + end_bounds.get('height', 0) // 2
        else:
            # Nur ein Element - markiere das ganze Element
            end_x = start_bounds.get('x', 0) + start_bounds.get('width', 0)
            end_y = start_y
        
        return await self.select_text_by_coords((start_x, start_y), (end_x, end_y))
    
    async def select_line_elements(
        self,
        elements: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Markiert eine Zeile von UI-Elementen.
        
        Elemente sollten in der gleichen Zeile liegen (ähnliche Y-Koordinaten).
        Drag geht vom linken Rand des ersten zum rechten Rand des letzten Elements.
        
        Args:
            elements: Liste von UI-Elementen (sortiert nach X)
        
        Returns:
            ActionResult als Dict
        """
        if not elements:
            return {'success': False, 'error': 'No elements provided'}
        
        # Sortiere nach X-Koordinate
        sorted_elements = sorted(
            elements,
            key=lambda e: e.get('bounds', {}).get('x', e.get('center', {}).get('x', 0))
        )
        
        first = sorted_elements[0]
        last = sorted_elements[-1]
        
        return await self.select_text_by_elements(first, last)
    
    async def replace_selected_text(
        self,
        new_text: str
    ) -> Dict[str, Any]:
        """
        Ersetzt den aktuell markierten Text.
        
        Voraussetzung: Text wurde vorher mit select_text_* markiert.
        
        Args:
            new_text: Der neue Text
        
        Returns:
            ActionResult als Dict
        """
        if not self._ensure_available():
            return {'success': False, 'error': 'PyAutoGUI not available'}
        
        start_time = time.time()
        
        try:
            # Kurze Pause nach Markierung
            await asyncio.sleep(0.1)
            
            # Tippe den neuen Text (ersetzt Markierung automatisch)
            pyautogui.write(new_text, interval=self.type_interval)
            
            duration_ms = (time.time() - start_time) * 1000
            
            self._record_action('replace_text', {
                'new_text': new_text[:50],
                'length': len(new_text)
            })
            
            logger.info(f"Replaced selected text with '{new_text[:30]}...'")
            
            return {
                'success': True,
                'action': 'replace_text',
                'duration_ms': duration_ms,
                'data': {'new_text_length': len(new_text)}
            }
        
        except Exception as e:
            logger.error(f"Text replacement failed: {e}")
            return {'success': False, 'error': str(e), 'action': 'replace_text'}    
    async def select_and_replace(
        self,
        start: Tuple[int, int],
        end: Tuple[int, int],
        new_text: str
    ) -> Dict[str, Any]:
        """
        Markiert Text und ersetzt ihn in einem Schritt.
        
        Args:
            start: Startkoordinaten der Markierung
            end: Endkoordinaten der Markierung
            new_text: Der neue Text
        
        Returns:
            ActionResult als Dict
        """
        # Erst markieren
        select_result = await self.select_text_by_coords(start, end)
        if not select_result.get('success'):
            return select_result
        
        # Dann ersetzen
        return await self.replace_selected_text(new_text)
    
    async def select_element_and_replace(
        self,
        element: Dict[str, Any],
        new_text: str
    ) -> Dict[str, Any]:
        """
        Markiert ein UI-Element und ersetzt dessen Text.
        
        Args:
            element: Das UI-Element (mit bounds)
            new_text: Der neue Text
        
        Returns:
            ActionResult als Dict
        """
        # Erst markieren
        select_result = await self.select_text_by_elements(element)
        if not select_result.get('success'):
            return select_result
        
        # Dann ersetzen
        return await self.replace_selected_text(new_text)
    
    async def triple_click_select(
        self,
        target: Union[Tuple[int, int], Dict[str, Any], None] = None
    ) -> Dict[str, Any]:
        """
        Triple-Click um eine ganze Zeile zu markieren.
        
        Args:
            target: Zielposition oder Element
        
        Returns:
            ActionResult als Dict
        """
        if not self._ensure_available():
            return {'success': False, 'error': 'PyAutoGUI not available'}
        
        start_time = time.time()
        
        try:
            coords = self._get_coords(target)
            
            if coords:
                pyautogui.moveTo(coords[0], coords[1], duration=0.2)
                await asyncio.sleep(0.05)
            
            # Triple-Click
            pyautogui.click(clicks=3, interval=0.1)
            
            duration_ms = (time.time() - start_time) * 1000
            
            self._record_action('triple_click', {'coords': coords})
            logger.info(f"Triple-clicked at {coords}")
            
            return {
                'success': True,
                'action': 'triple_click',
                'duration_ms': duration_ms,
                'data': {'coords': coords}
            }
        
        except Exception as e:
            logger.error(f"Triple-click failed: {e}")
            return {'success': False, 'error': str(e), 'action': 'triple_click'}


# Singleton
_interaction_instance: Optional[InteractionAgent] = None


def get_interaction_agent() -> InteractionAgent:
    """Gibt Singleton-Instanz des Interaction Agents zurück."""
    global _interaction_instance
    if _interaction_instance is None:
        _interaction_instance = InteractionAgent()
    return _interaction_instance