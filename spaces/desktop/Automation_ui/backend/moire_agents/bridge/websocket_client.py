"""
WebSocket Bridge Client - Verbindung zum MoireServer (TypeScript)

Empfängt Detection-Daten, OCR-Texte und state_changed Events
und stellt sie den Python AutoGen Agents zur Verfügung.

WICHTIG: Beim Connect wird automatisch ein Background-Receiver gestartet,
sodass capture_and_wait_for_complete() korrekt funktioniert.
"""

import asyncio
import json
import logging
import base64
from io import BytesIO
from typing import Optional, Callable, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

import websockets
from websockets.client import WebSocketClientProtocol

# Optional PIL import for Vision support
try:
    from PIL import Image as PILImage
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# Logging Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CaptureState(Enum):
    """Status des Capture-Prozesses."""
    IDLE = "idle"
    CAPTURING = "capturing"
    DETECTING = "detecting"
    OCR_RUNNING = "ocr_running"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class CaptureResult:
    """Ergebnis eines vollständigen Capture+OCR Durchlaufs."""
    success: bool
    ui_context: Optional['UIContext']
    screenshot_base64: Optional[str]
    boxes_count: int
    texts_count: int
    processing_time_ms: float
    error: Optional[str] = None
    
    @property
    def has_good_ocr(self) -> bool:
        """Prüft ob OCR genug Texte gefunden hat."""
        return self.texts_count > 0 and self.texts_count >= self.boxes_count * 0.3


@dataclass
class UIElement:
    """Ein erkanntes UI-Element mit OCR-Text und Koordinaten."""
    id: str
    type: str
    bounds: Dict[str, int]
    center: Dict[str, int]
    text: Optional[str]
    confidence: float
    category: Optional[str]


@dataclass
class UIRegion:
    """Eine Region mit gruppierten UI-Elementen."""
    id: int
    bounds: Dict[str, int]
    element_count: int
    element_ids: List[str]


@dataclass
class UILine:
    """Eine Zeile von UI-Elementen."""
    id: int
    region_id: int
    orientation: str
    element_count: int
    element_ids: List[str]
    avg_spacing: float


@dataclass
class UIContext:
    """Strukturierter UI-Kontext für Agents."""
    version: int
    timestamp: int
    screen_dimensions: Dict[str, int]
    detection_mode: str
    elements: List[UIElement]
    regions: List[UIRegion]
    lines: List[UILine]
    statistics: Dict[str, Any]
    
    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> 'UIContext':
        """Erstellt UIContext aus JSON-Daten vom MoireServer."""
        elements = [
            UIElement(
                id=e['id'],
                type=e['type'],
                bounds=e['bounds'],
                center=e['center'],
                text=e.get('text'),
                confidence=e['confidence'],
                category=e.get('category')
            )
            for e in data.get('elements', [])
        ]
        
        regions = [
            UIRegion(
                id=r['id'],
                bounds=r['bounds'],
                element_count=r['elementCount'],
                element_ids=r['elementIds']
            )
            for r in data.get('regions', [])
        ]
        
        lines = [
            UILine(
                id=l['id'],
                region_id=l['regionId'],
                orientation=l['orientation'],
                element_count=l['elementCount'],
                element_ids=l['elementIds'],
                avg_spacing=l['avgSpacing']
            )
            for l in data.get('lines', [])
        ]
        
        return cls(
            version=data.get('version', 0),
            timestamp=data.get('timestamp', 0),
            screen_dimensions=data.get('screenDimensions', {'width': 1920, 'height': 1080}),
            detection_mode=data.get('detectionMode', 'unknown'),
            elements=elements,
            regions=regions,
            lines=lines,
            statistics=data.get('statistics', {})
        )


@dataclass
class StateDelta:
    """Änderungen zwischen zwei States."""
    added: List[str]
    removed: List[str]
    modified: List[str]
    text_changes: List[Dict[str, Any]]
    
    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> 'StateDelta':
        return cls(
            added=data.get('added', []),
            removed=data.get('removed', []),
            modified=data.get('modified', []),
            text_changes=data.get('textChanges', [])
        )


@dataclass
class StateChangedEvent:
    """Event wenn sich der Screen-State ändert."""
    version: int
    timestamp: int
    delta: StateDelta
    ui_context: UIContext


class MoireWebSocketClient:
    """
    WebSocket Client für MoireServer.
    
    Verbindet sich zum MoireServer und empfängt:
    - state_changed: Wenn sich die Detection-Ergebnisse ändern
    - detection_result: Vollständige Detection-Ergebnisse
    - ocr_update: Inkrementelle OCR-Updates
    
    WICHTIG: Beim Connect wird automatisch ein Background-Receiver gestartet!
    """
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 8766,
        reconnect_interval: float = 2.0,
        auto_reconnect: bool = True,
        keepalive_interval: float = 15.0
    ):
        self.host = host
        self.port = port
        self.uri = f"ws://{host}:{port}"
        self.reconnect_interval = reconnect_interval
        self.auto_reconnect = auto_reconnect
        self.keepalive_interval = keepalive_interval
        
        self.websocket: Optional[WebSocketClientProtocol] = None
        self.is_connected: bool = False
        self.is_running: bool = False
        
        # Current state
        self.current_context: Optional[UIContext] = None
        self.last_screenshot: Optional[str] = None
        self.state_version: int = 0
        
        # Capture state tracking
        self._capture_state: CaptureState = CaptureState.IDLE
        self._capture_event: asyncio.Event = asyncio.Event()
        self._ocr_complete_event: asyncio.Event = asyncio.Event()
        self._last_ocr_text_count: int = 0
        self._last_boxes_count: int = 0
        
        # NEU: Background tasks
        self._receiver_task: Optional[asyncio.Task] = None
        self._keepalive_task: Optional[asyncio.Task] = None
        self._reconnect_attempts: int = 0
        self._max_reconnect_attempts: int = 10
        self._connection_lock: asyncio.Lock = asyncio.Lock()
        
        # Event handlers
        self._on_state_changed: List[Callable[[StateChangedEvent], None]] = []
        self._on_detection_result: List[Callable[[Dict[str, Any]], None]] = []
        self._on_ocr_update: List[Callable[[Dict[str, Any]], None]] = []
        self._on_connected: List[Callable[[], None]] = []
        self._on_disconnected: List[Callable[[], None]] = []
        
        # Message queue for agents
        self._message_queue: asyncio.Queue = asyncio.Queue()
    
    # ==================== Event Registration ====================
    
    def on_state_changed(self, handler: Callable[[StateChangedEvent], None]):
        """Registriert Handler für state_changed Events."""
        self._on_state_changed.append(handler)
        return self
    
    def on_detection_result(self, handler: Callable[[Dict[str, Any]], None]):
        """Registriert Handler für detection_result Events."""
        self._on_detection_result.append(handler)
        return self
    
    def on_ocr_update(self, handler: Callable[[Dict[str, Any]], None]):
        """Registriert Handler für ocr_update Events."""
        self._on_ocr_update.append(handler)
        return self
    
    def on_connected(self, handler: Callable[[], None]):
        """Registriert Handler für Verbindungsaufbau."""
        self._on_connected.append(handler)
        return self
    
    def on_disconnected(self, handler: Callable[[], None]):
        """Registriert Handler für Verbindungsabbruch."""
        self._on_disconnected.append(handler)
        return self
    
    # ==================== Connection Management ====================
    
    async def connect(self) -> bool:
        """
        Verbindet zum MoireServer.
        
        WICHTIG: Startet automatisch einen Background-Receiver Task!
        """
        async with self._connection_lock:
            if self.is_connected and self.websocket:
                return True
            
            try:
                logger.info(f"Connecting to MoireServer at {self.uri}...")
                self.websocket = await websockets.connect(
                    self.uri,
                    ping_interval=self.keepalive_interval,
                    ping_timeout=30,
                    close_timeout=10,
                    max_size=50 * 1024 * 1024,  # 50MB max für Screenshots
                )
                self.is_connected = True
                self._reconnect_attempts = 0
                
                # Handshake
                await self._send_raw({'type': 'handshake'})
                
                # NEU: Starte Background-Receiver automatisch!
                self._start_background_receiver()
                
                logger.info("Connected to MoireServer")
                for handler in self._on_connected:
                    try:
                        handler()
                    except Exception as e:
                        logger.error(f"Connected handler error: {e}")
                
                return True
            except Exception as e:
                logger.error(f"Connection failed: {e}")
                self.is_connected = False
                return False
    
    async def disconnect(self):
        """Trennt die Verbindung und stoppt alle Tasks."""
        self.is_running = False
        self.is_connected = False
        
        # Stoppe Background Tasks
        self._stop_background_tasks()
        
        if self.websocket:
            try:
                await self.websocket.close()
            except Exception:
                pass
            self.websocket = None
        
        for handler in self._on_disconnected:
            try:
                handler()
            except Exception as e:
                logger.error(f"Disconnected handler error: {e}")
        
        logger.info("Disconnected from MoireServer")
    
    # ==================== Background Tasks ====================
    
    def _start_background_receiver(self):
        """Startet den Background-Receiver Task."""
        if self._receiver_task is not None:
            self._receiver_task.cancel()
        
        self._receiver_task = asyncio.create_task(self._background_receiver())
        logger.info("Background receiver started")
    
    def _stop_background_tasks(self):
        """Stoppt alle Background Tasks."""
        if self._receiver_task is not None:
            self._receiver_task.cancel()
            self._receiver_task = None
        
        if self._keepalive_task is not None:
            self._keepalive_task.cancel()
            self._keepalive_task = None
    
    async def _background_receiver(self):
        """
        Background Task der kontinuierlich Nachrichten empfängt.
        
        Dies ist das Herzstück der Lösung - die Nachrichten werden
        unabhängig davon empfangen ob jemand auf ein Event wartet oder nicht.
        """
        logger.info("Background receiver running...")
        
        try:
            while self.is_connected and self.websocket:
                try:
                    # Empfange Nachricht mit kurzen Timeouts für schnelle Reaktion
                    message = await asyncio.wait_for(
                        self.websocket.recv(),
                        timeout=60.0  # Lange timeout, ws-ping handled keepalive
                    )
                    
                    # Verarbeite die Nachricht
                    try:
                        data = json.loads(message)
                        await self._handle_message(data)
                    except json.JSONDecodeError as e:
                        logger.error(f"Invalid JSON received: {e}")
                    
                except asyncio.TimeoutError:
                    # Keine Nachricht - check ob noch verbunden
                    if not self.is_connected:
                        break
                    continue
                    
                except websockets.exceptions.ConnectionClosed as e:
                    logger.warning(f"Connection closed: {e}")
                    break
                    
                except Exception as e:
                    logger.error(f"Receiver error: {e}")
                    await asyncio.sleep(0.1)
                    
        except asyncio.CancelledError:
            logger.info("Background receiver cancelled")
        finally:
            # Connection lost - trigger reconnect if needed
            if self.auto_reconnect and self.is_connected:
                self.is_connected = False
                asyncio.create_task(self._handle_disconnect())
    
    async def _handle_disconnect(self):
        """Behandelt Verbindungsabbruch mit Reconnect."""
        if not self.auto_reconnect:
            return
        
        for handler in self._on_disconnected:
            try:
                handler()
            except Exception as e:
                logger.error(f"Disconnected handler error: {e}")
        
        self._reconnect_attempts += 1
        
        if self._reconnect_attempts > self._max_reconnect_attempts:
            logger.error(f"Max reconnect attempts ({self._max_reconnect_attempts}) reached")
            return
        
        wait_time = min(self.reconnect_interval * self._reconnect_attempts, 30)
        logger.info(f"Reconnecting in {wait_time}s (attempt {self._reconnect_attempts}/{self._max_reconnect_attempts})...")
        
        await asyncio.sleep(wait_time)
        
        success = await self.connect()
        if not success and self.auto_reconnect:
            # Nächster Versuch
            asyncio.create_task(self._handle_disconnect())
    
    async def ensure_connected(self) -> bool:
        """Stellt sicher, dass die Verbindung besteht."""
        if self.is_connected and self.websocket:
            return True
        
        return await self.connect()
    
    async def run(self):
        """
        Optionale Hauptschleife für eigenständige Clients.
        
        HINWEIS: Wird NICHT mehr benötigt wenn man capture_and_wait_for_complete() nutzt,
        da der Background-Receiver automatisch startet!
        """
        self.is_running = True
        
        while self.is_running:
            if not self.is_connected:
                if self.auto_reconnect:
                    success = await self.connect()
                    if not success:
                        logger.info(f"Reconnecting in {self.reconnect_interval}s...")
                        await asyncio.sleep(self.reconnect_interval)
                        continue
                else:
                    break
            
            # Warte einfach - der Background Receiver handled alles
            await asyncio.sleep(1.0)
    
    async def _handle_message(self, msg: Dict[str, Any]):
        """Verarbeitet eingehende Messages."""
        msg_type = msg.get('type')
        
        if msg_type == 'handshake_ack':
            features = msg.get('features', {})
            logger.info(f"Handshake OK - Features: {features}")
        
        # Support both 'state_change' and 'state_changed' (server sends 'state_change')
        elif msg_type in ['state_changed', 'state_change']:
            event = StateChangedEvent(
                version=msg.get('version', 0),
                timestamp=msg.get('timestamp', 0),
                delta=StateDelta.from_json(msg.get('delta', {})),
                ui_context=UIContext.from_json(msg.get('uiContext', {}))
            )
            
            self.current_context = event.ui_context
            self.state_version = event.version
            
            # Zähle Texte
            texts_count = len([e for e in event.ui_context.elements if e.text])
            
            logger.info(
                f"State changed (v{event.version}): "
                f"{len(event.ui_context.elements)} elements, {texts_count} with text"
            )
            
            # Update capture state - state_changed kommt NACH OCR
            if self._capture_state in [CaptureState.CAPTURING, CaptureState.DETECTING, CaptureState.OCR_RUNNING]:
                self._last_ocr_text_count = texts_count
                self._capture_state = CaptureState.COMPLETE
                self._capture_event.set()
                logger.info(f"Capture complete! {texts_count} texts found")
            
            # Queue for agents
            await self._message_queue.put(('state_changed', event))
            
            for handler in self._on_state_changed:
                try:
                    handler(event)
                except Exception as e:
                    logger.error(f"state_changed handler error: {e}")
        
        elif msg_type == 'detection_result':
            data = msg.get('data', {})
            self.last_screenshot = data.get('backgroundImage')
            self._last_boxes_count = len(data.get('boxes', []))
            
            logger.info(f"Detection result: {self._last_boxes_count} boxes")
            
            # Update capture state
            if self._capture_state == CaptureState.CAPTURING:
                self._capture_state = CaptureState.DETECTING
            
            await self._message_queue.put(('detection_result', data))
            
            for handler in self._on_detection_result:
                try:
                    handler(data)
                except Exception as e:
                    logger.error(f"detection_result handler error: {e}")
        
        elif msg_type == 'ocr_update':
            progress = msg.get('progress', 0)
            logger.debug(f"OCR progress: {progress:.1f}%")
            
            # Update capture state
            if self._capture_state == CaptureState.DETECTING:
                self._capture_state = CaptureState.OCR_RUNNING
            
            await self._message_queue.put(('ocr_update', msg))
            
            for handler in self._on_ocr_update:
                try:
                    handler(msg)
                except Exception as e:
                    logger.error(f"ocr_update handler error: {e}")
        
        elif msg_type == 'ocr_complete':
            self._last_ocr_text_count = msg.get('textCount', 0)
            logger.info(f"OCR complete: {self._last_ocr_text_count} texts")
            
            self._ocr_complete_event.set()
            await self._message_queue.put(('ocr_complete', msg))
        
        # Handle moire_detection_result - contains all boxes with OCR texts
        elif msg_type == 'moire_detection_result':
            boxes = msg.get('boxes', [])
            background_image = msg.get('backgroundImage')
            detection_mode = msg.get('detectionMode', 'advanced')
            
            # Store screenshot
            if background_image:
                self.last_screenshot = background_image
            
            # Convert boxes to UIElements
            elements = []
            for box in boxes:
                element = UIElement(
                    id=box.get('id', ''),
                    type=box.get('type', 'box'),
                    bounds={
                        'x': box.get('x', 0),
                        'y': box.get('y', 0),
                        'width': box.get('width', 0),
                        'height': box.get('height', 0)
                    },
                    center={
                        'x': box.get('x', 0) + box.get('width', 0) // 2,
                        'y': box.get('y', 0) + box.get('height', 0) // 2
                    },
                    text=box.get('text'),
                    confidence=box.get('confidence', 0.5),
                    category=box.get('category')
                )
                elements.append(element)
            
            self._last_boxes_count = len(elements)
            self._last_ocr_text_count = len([e for e in elements if e.text])
            
            # Create UIContext from boxes
            self.current_context = UIContext(
                version=self.state_version,
                timestamp=int(datetime.now().timestamp() * 1000),
                screen_dimensions={'width': 1920, 'height': 1080},
                detection_mode=detection_mode,
                elements=elements,
                regions=[],
                lines=[],
                statistics={
                    'totalElements': len(elements),
                    'elementsWithText': self._last_ocr_text_count
                }
            )
            
            logger.info(f"moire_detection_result: {len(elements)} boxes, {self._last_ocr_text_count} with text")
            
            # Signal capture complete - moire_detection_result kommt NACH state_change
            if self._capture_state in [CaptureState.CAPTURING, CaptureState.DETECTING, CaptureState.OCR_RUNNING, CaptureState.COMPLETE]:
                self._capture_state = CaptureState.COMPLETE
                self._capture_event.set()
                logger.info(f"Capture complete! {self._last_ocr_text_count} texts found")
            
            await self._message_queue.put(('moire_detection_result', msg))
            
            for handler in self._on_detection_result:
                try:
                    handler(msg)
                except Exception as e:
                    logger.error(f"moire_detection_result handler error: {e}")
        
        elif msg_type == 'error':
            error_msg = msg.get('message', 'Unknown error')
            logger.error(f"Server error: {error_msg}")
            if self._capture_state != CaptureState.IDLE:
                self._capture_state = CaptureState.ERROR
                self._capture_event.set()

    # ==================== Commands to Server ====================

    async def _send_raw(self, data: Dict[str, Any]):
        """Sendet Message an Server ohne Reconnect-Logik."""
        if self.websocket:
            await self.websocket.send(json.dumps(data))
    
    async def _send(self, data: Dict[str, Any]):
        """Sendet Message an Server mit Reconnect-Support."""
        if not self.is_connected or not self.websocket:
            connected = await self.ensure_connected()
            if not connected:
                raise ConnectionError("Not connected to MoireServer")
        
        try:
            await self._send_raw(data)
        except websockets.exceptions.ConnectionClosed:
            logger.warning("Connection lost during send")
            self.is_connected = False
            # Trigger reconnect
            asyncio.create_task(self._handle_disconnect())
            raise
    
    async def send_message(self, data: Dict[str, Any]) -> bool:
        """
        Public wrapper for sending messages.
        
        Args:
            data: Message dict to send
            
        Returns:
            True if sent successfully
        """
        try:
            await self._send(data)
            return True
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            return False
    
    async def capture_desktop(self):
        """Triggert Desktop-Capture."""
        await self._send({'type': 'scan_desktop'})
        logger.info("Requested desktop capture")
    
    async def capture_window(self, title: str):
        """Triggert Window-Capture."""
        await self._send({'type': 'scan_window', 'title': title})
        logger.info(f"Requested window capture: {title}")
    
    async def run_ocr(self):
        """Triggert OCR auf aktuellen Boxes."""
        await self._send({'type': 'run_ocr'})
        logger.info("Requested OCR")
    
    async def run_cnn(self):
        """Triggert CNN-Klassifizierung."""
        await self._send({'type': 'run_cnn'})
        logger.info("Requested CNN classification")
    
    async def start_streaming(self):
        """Startet kontinuierliches Capturing."""
        await self._send({'type': 'start_live'})
        logger.info("Started live streaming")
    
    async def stop_streaming(self):
        """Stoppt kontinuierliches Capturing."""
        await self._send({'type': 'stop_live'})
        logger.info("Stopped live streaming")
    
    async def set_detection_mode(self, mode: str):
        """Setzt Detection-Modus (advanced/simple)."""
        await self._send({'type': 'set_detection_mode', 'mode': mode})
        logger.info(f"Set detection mode: {mode}")
    
    async def get_detection_results(self):
        """Fordert aktuelle Detection-Ergebnisse an."""
        await self._send({'type': 'get_detection_results'})
    
    async def report_action(
        self,
        action_type: str,
        x: int,
        y: int,
        end_x: Optional[int] = None,
        end_y: Optional[int] = None,
        button: Optional[str] = None,
        text: Optional[str] = None,
        agent_id: Optional[str] = None
    ) -> bool:
        """Meldet eine Action an den Server für Visualisierung."""
        message = {
            'type': 'report_action',
            'action': action_type,
            'x': x,
            'y': y,
            'agentId': agent_id or 'interaction_agent'
        }
        
        if end_x is not None:
            message['endX'] = end_x
        if end_y is not None:
            message['endY'] = end_y
        if button:
            message['button'] = button
        if text:
            message['text'] = text[:50]
        
        logger.info(f"Reporting action: {action_type} at ({x}, {y})")
        return await self.send_message(message)
    
    # ==================== Query Methods for Agents ====================

    def get_current_context(self) -> Optional[UIContext]:
        """Gibt aktuellen UI-Kontext zurück."""
        return self.current_context
    
    def get_elements_with_text(self) -> List[UIElement]:
        """Gibt alle Elemente mit erkanntem Text zurück."""
        if not self.current_context:
            return []
        return [e for e in self.current_context.elements if e.text]
    
    def find_element_by_text(self, text: str, exact: bool = False) -> Optional[UIElement]:
        """Findet Element anhand von Text."""
        if not self.current_context:
            return None
        
        text_lower = text.lower()
        for element in self.current_context.elements:
            if element.text:
                if exact and element.text == text:
                    return element
                elif not exact and text_lower in element.text.lower():
                    return element
        return None
    
    def find_elements_by_text(self, text: str, exact: bool = False) -> List[UIElement]:
        """Findet alle Elemente mit matching Text."""
        if not self.current_context:
            return []
        
        results = []
        text_lower = text.lower()
        for element in self.current_context.elements:
            if element.text:
                if exact and element.text == text:
                    results.append(element)
                elif not exact and text_lower in element.text.lower():
                    results.append(element)
        return results
    
    def find_elements_in_region(self, x: int, y: int, width: int, height: int) -> List[UIElement]:
        """Findet alle Elemente in einem Bereich."""
        if not self.current_context:
            return []
        
        results = []
        for element in self.current_context.elements:
            ex, ey = element.bounds['x'], element.bounds['y']
            ew, eh = element.bounds['width'], element.bounds['height']
            
            # Überlappung prüfen
            if (ex < x + width and ex + ew > x and
                ey < y + height and ey + eh > y):
                results.append(element)
        
        return results
    
    def get_clickable_center(self, element: UIElement) -> tuple[int, int]:
        """Gibt Klick-Koordinaten für ein Element zurück."""
        return (element.center['x'], element.center['y'])
    
    async def wait_for_state_change(self, timeout: float = 30.0) -> Optional[StateChangedEvent]:
        """Wartet auf nächste State-Änderung."""
        try:
            while True:
                msg_type, data = await asyncio.wait_for(
                    self._message_queue.get(),
                    timeout=timeout
                )
                if msg_type == 'state_changed':
                    return data
        except asyncio.TimeoutError:
            return None
    
    def get_summary(self) -> str:
        """Gibt Zusammenfassung des aktuellen States als String."""
        if not self.current_context:
            return "Keine UI-Daten verfügbar"
        
        ctx = self.current_context
        stats = ctx.statistics
        
        elements_with_text = [e for e in ctx.elements if e.text]
        
        summary = f"""UI-Kontext (v{ctx.version}):
- {stats.get('totalElements', 0)} Elemente erkannt
- {stats.get('elementsWithText', 0)} mit Text
- {len(ctx.regions)} Regionen
- {len(ctx.lines)} Zeilen
- Durchschnittliche Konfidenz: {stats.get('avgConfidence', 0):.1%}

Texte erkannt:
"""
        for elem in elements_with_text[:20]:
            summary += f"  - [{elem.id}] '{elem.text}' @ ({elem.center['x']}, {elem.center['y']})\n"
        
        if len(elements_with_text) > 20:
            summary += f"  ... und {len(elements_with_text) - 20} weitere\n"
        
        return summary

    # ==================== Advanced Capture Methods ====================

    async def capture_and_wait_for_complete(
        self,
        timeout: float = 120.0,
        min_ocr_confidence: float = 0.3
    ) -> CaptureResult:
        """
        Triggert Capture und wartet auf vollständige Detection + OCR.
        
        Dies ist die bevorzugte Methode für den Data Analyst, da sie sicherstellt,
        dass alle OCR-Worker fertig sind bevor die Analyse beginnt.
        
        WICHTIG: Der Background-Receiver muss laufen (wird bei connect() gestartet)!
        
        Args:
            timeout: Maximale Wartezeit in Sekunden (default 120s für viele Boxes)
            min_ocr_confidence: Minimaler Anteil an Elementen mit Text
        
        Returns:
            CaptureResult mit vollständigem UIContext
        """
        # Stelle sicher dass wir verbunden sind
        if not await self.ensure_connected():
            return CaptureResult(
                success=False,
                ui_context=None,
                screenshot_base64=None,
                boxes_count=0,
                texts_count=0,
                processing_time_ms=0,
                error="Not connected to MoireServer"
            )
        
        start_time = asyncio.get_event_loop().time()
        
        # Reset state
        self._capture_state = CaptureState.CAPTURING
        self._capture_event.clear()
        self._ocr_complete_event.clear()
        self._last_ocr_text_count = 0
        self._last_boxes_count = 0
        
        try:
            # Trigger capture
            await self.capture_desktop()
            
            # Warte auf state_changed Event (kommt nach Detection + OCR)
            # Der Background-Receiver setzt self._capture_event wenn state_changed kommt
            logger.info(f"Waiting up to {timeout}s for detection + OCR to complete...")
            
            try:
                await asyncio.wait_for(self._capture_event.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning(f"Timeout after {timeout}s waiting for state_changed")
                return CaptureResult(
                    success=False,
                    ui_context=self.current_context,
                    screenshot_base64=self.last_screenshot,
                    boxes_count=self._last_boxes_count,
                    texts_count=self._last_ocr_text_count,
                    processing_time_ms=(asyncio.get_event_loop().time() - start_time) * 1000,
                    error=f"Timeout after {timeout}s"
                )
            
            # Check for errors
            if self._capture_state == CaptureState.ERROR:
                return CaptureResult(
                    success=False,
                    ui_context=self.current_context,
                    screenshot_base64=self.last_screenshot,
                    boxes_count=self._last_boxes_count,
                    texts_count=self._last_ocr_text_count,
                    processing_time_ms=(asyncio.get_event_loop().time() - start_time) * 1000,
                    error="Capture failed"
                )
            
            processing_time = (asyncio.get_event_loop().time() - start_time) * 1000
            
            logger.info(f"Capture complete in {processing_time:.0f}ms: {self._last_boxes_count} boxes, {self._last_ocr_text_count} texts")
            
            return CaptureResult(
                success=True,
                ui_context=self.current_context,
                screenshot_base64=self.last_screenshot,
                boxes_count=self._last_boxes_count,
                texts_count=self._last_ocr_text_count,
                processing_time_ms=processing_time
            )
        
        except Exception as e:
            logger.error(f"capture_and_wait_for_complete failed: {e}")
            return CaptureResult(
                success=False,
                ui_context=None,
                screenshot_base64=None,
                boxes_count=0,
                texts_count=0,
                processing_time_ms=(asyncio.get_event_loop().time() - start_time) * 1000,
                error=str(e)
            )
        
        finally:
            self._capture_state = CaptureState.IDLE
    
    async def capture_with_retry(
        self,
        max_retries: int = 3,
        timeout_per_try: float = 60.0,
        min_texts: int = 1
    ) -> CaptureResult:
        """
        Capture mit automatischem Retry bei fehlgeschlagener OCR.
        
        Args:
            max_retries: Maximale Anzahl Versuche
            timeout_per_try: Timeout pro Versuch
            min_texts: Minimale Anzahl erkannter Texte
        
        Returns:
            CaptureResult
        """
        last_result = None
        for attempt in range(max_retries):
            result = await self.capture_and_wait_for_complete(timeout=timeout_per_try)
            last_result = result
            
            if result.success and result.texts_count >= min_texts:
                logger.info(f"Capture successful on attempt {attempt + 1}")
                return result
            
            if attempt < max_retries - 1:
                logger.warning(
                    f"Capture attempt {attempt + 1} insufficient: "
                    f"{result.texts_count} texts (need {min_texts}). Retrying..."
                )
                await asyncio.sleep(1.0)
        
        logger.warning(f"All {max_retries} capture attempts completed. Best result: {last_result.texts_count if last_result else 0} texts")
        return last_result or CaptureResult(
            success=False,
            ui_context=None,
            screenshot_base64=None,
            boxes_count=0,
            texts_count=0,
            processing_time_ms=0,
            error="All retries failed"
        )
    
    def get_screenshot_as_pil(self) -> Optional['PILImage.Image']:
        """Gibt aktuellen Screenshot als PIL Image zurück."""
        if not HAS_PIL:
            logger.error("PIL not available. Install with: pip install Pillow")
            return None
        
        if not self.last_screenshot:
            return None
        
        try:
            if self.last_screenshot.startswith('data:'):
                header, data = self.last_screenshot.split(',', 1)
            else:
                data = self.last_screenshot
            
            image_bytes = base64.b64decode(data)
            return PILImage.open(BytesIO(image_bytes))
        
        except Exception as e:
            logger.error(f"Failed to convert screenshot to PIL: {e}")
            return None
    
    def get_screenshot_as_bytes(self) -> Optional[bytes]:
        """Gibt aktuellen Screenshot als Bytes zurück."""
        if not self.last_screenshot:
            return None
        
        try:
            if self.last_screenshot.startswith('data:'):
                header, data = self.last_screenshot.split(',', 1)
            else:
                data = self.last_screenshot
            
            return base64.b64decode(data)
        
        except Exception as e:
            logger.error(f"Failed to decode screenshot: {e}")
            return None
    
    def get_capture_state(self) -> CaptureState:
        """Gibt aktuellen Capture-Status zurück."""
        return self._capture_state
    
    def is_capture_in_progress(self) -> bool:
        """Prüft ob gerade ein Capture läuft."""
        return self._capture_state not in [CaptureState.IDLE, CaptureState.COMPLETE, CaptureState.ERROR]

    # ==================== V2 OrchestratorV2 Integration ====================

    async def request_capture(self) -> bool:
        """Triggert Screenshot-Capture (für OrchestratorV2)."""
        try:
            await self.ensure_connected()
            await self.capture_desktop()
            return True
        except Exception as e:
            logger.error(f"request_capture failed: {e}")
            return False

    async def get_last_screenshot(self) -> Optional[bytes]:
        """Gibt letzten Screenshot als Bytes zurück."""
        return self.get_screenshot_as_bytes()

    async def get_state(self) -> Dict[str, Any]:
        """Gibt aktuellen Screen-State als Dict zurück."""
        if not self.current_context:
            return {
                "elements": [],
                "dimensions": {"width": 1920, "height": 1080},
                "timestamp": 0
            }
        
        ctx = self.current_context
        
        return {
            "elements": [
                {
                    "id": e.id,
                    "type": e.type,
                    "x": e.bounds.get("x", 0),
                    "y": e.bounds.get("y", 0),
                    "width": e.bounds.get("width", 0),
                    "height": e.bounds.get("height", 0),
                    "text": e.text,
                    "confidence": e.confidence,
                    "category": e.category,
                    "center": e.center
                }
                for e in ctx.elements
            ],
            "dimensions": ctx.screen_dimensions,
            "timestamp": ctx.timestamp,
            "version": ctx.version,
            "statistics": ctx.statistics,
            "detection_mode": ctx.detection_mode
        }

    async def wait_for_change(self, timeout: float = 5.0) -> bool:
        """Wartet auf Bildschirmänderung (für Action Validation)."""
        initial_version = self.state_version
        
        try:
            start_time = asyncio.get_event_loop().time()
            while asyncio.get_event_loop().time() - start_time < timeout:
                if self.state_version != initial_version:
                    return True
                await asyncio.sleep(0.1)
            return False
        except Exception as e:
            logger.error(f"wait_for_change failed: {e}")
            return False


# Singleton-Instanz
_client_instance: Optional[MoireWebSocketClient] = None


def get_moire_client(
    host: str = "localhost",
    port: int = 8766
) -> MoireWebSocketClient:
    """Gibt Singleton-Instanz des WebSocket Clients zurück."""
    global _client_instance
    if _client_instance is None:
        _client_instance = MoireWebSocketClient(host=host, port=port)
    return _client_instance


async def main():
    """Test-Funktion."""
    client = get_moire_client()
    
    # Event-Handler registrieren
    client.on_state_changed(lambda e: print(f"State changed: v{e.version}, {len(e.ui_context.elements)} elements"))
    client.on_connected(lambda: print("Connected!"))
    
    # Verbinden (startet automatisch Background-Receiver)
    await client.connect()
    
    # Capture mit Warten
    print("\nStarting capture...")
    result = await client.capture_and_wait_for_complete(timeout=120)
    
    print(f"\nCapture Result:")
    print(f"  Success: {result.success}")
    print(f"  Boxes: {result.boxes_count}")
    print(f"  Texts: {result.texts_count}")
    print(f"  Time: {result.processing_time_ms:.0f}ms")
    
    if result.ui_context:
        texts = [e.text for e in result.ui_context.elements if e.text]
        print(f"  Sample texts: {texts[:10]}")
    
    # Warte auf weitere Events
    print("\nWaiting for more events (Ctrl+C to exit)...")
    try:
        while True:
            await asyncio.sleep(1.0)
    except KeyboardInterrupt:
        pass
    
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())