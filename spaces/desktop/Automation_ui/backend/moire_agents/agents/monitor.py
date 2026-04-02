"""
Monitor Agent - Überwacht Bildschirmänderungen und hält Daten aktuell

Verantwortlich für:
- Kontinuierliche Überwachung des Bildschirms
- Change-Detection zwischen States
- Automatisches Triggern von Capture und OCR
- Benachrichtigung anderer Agents bei Änderungen
"""

import asyncio
import logging
import time
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ChangeType(Enum):
    """Typ der Änderung."""
    ELEMENT_ADDED = "element_added"
    ELEMENT_REMOVED = "element_removed"
    TEXT_CHANGED = "text_changed"
    POSITION_CHANGED = "position_changed"
    LAYOUT_CHANGED = "layout_changed"
    NO_CHANGE = "no_change"


@dataclass
class ChangeEvent:
    """Ein Änderungsevent."""
    timestamp: datetime
    change_type: ChangeType
    affected_elements: List[str]
    delta: Dict[str, Any]
    significance: float  # 0.0 bis 1.0, wie wichtig die Änderung ist


@dataclass 
class MonitorState:
    """Zustand des Monitors."""
    version: int
    timestamp: datetime
    element_count: int
    element_hashes: Dict[str, str]
    text_hash: str
    is_monitoring: bool


class MonitorAgent:
    """
    Monitor Agent - Überwacht den Bildschirm kontinuierlich.
    
    Funktionen:
    - Periodisches Capture von MoireServer anfordern
    - State-Vergleiche durchführen
    - Änderungen erkennen und kategorisieren
    - Andere Agents bei relevanten Änderungen benachrichtigen
    """
    
    def __init__(
        self,
        moire_client = None,
        check_interval: float = 2.0,
        min_change_threshold: float = 0.1,
        auto_start: bool = False
    ):
        """
        Initialisiert den Monitor Agent.
        
        Args:
            moire_client: WebSocket Client zu MoireServer
            check_interval: Zeit zwischen Checks (Sekunden)
            min_change_threshold: Minimale Änderungsstärke für Events
            auto_start: Automatisch starten?
        """
        self.moire_client = moire_client
        self.check_interval = check_interval
        self.min_change_threshold = min_change_threshold
        
        # State tracking
        self.current_state: Optional[MonitorState] = None
        self.previous_states: List[MonitorState] = []
        self.change_history: List[ChangeEvent] = []
        
        # Monitoring control
        self.is_monitoring = False
        self._monitor_task: Optional[asyncio.Task] = None
        
        # Event handlers
        self._on_change: List[Callable[[ChangeEvent], None]] = []
        self._on_significant_change: List[Callable[[ChangeEvent], None]] = []
        
        # Statistics
        self.stats = {
            'checks_performed': 0,
            'changes_detected': 0,
            'significant_changes': 0,
            'last_check': None,
            'last_change': None
        }
        
        if auto_start:
            asyncio.create_task(self.start_monitoring())
    
    def set_moire_client(self, client):
        """Setzt den MoireServer Client."""
        self.moire_client = client
    
    # ==================== Event Registration ====================
    
    def on_change(self, handler: Callable[[ChangeEvent], None]):
        """Registriert Handler für alle Änderungen."""
        self._on_change.append(handler)
        return self
    
    def on_significant_change(self, handler: Callable[[ChangeEvent], None]):
        """Registriert Handler für signifikante Änderungen."""
        self._on_significant_change.append(handler)
        return self
    
    # ==================== Monitoring Control ====================
    
    async def start_monitoring(self):
        """Startet die kontinuierliche Überwachung."""
        if self.is_monitoring:
            logger.warning("Monitoring already running")
            return
        
        self.is_monitoring = True
        self._monitor_task = asyncio.create_task(self._monitoring_loop())
        logger.info(f"Monitor started (interval: {self.check_interval}s)")
    
    async def stop_monitoring(self):
        """Stoppt die Überwachung."""
        self.is_monitoring = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None
        logger.info("Monitor stopped")
    
    async def _monitoring_loop(self):
        """Haupt-Überwachungsschleife."""
        while self.is_monitoring:
            try:
                await self.check_for_changes()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitoring error: {e}")
                await asyncio.sleep(self.check_interval)
    
    # ==================== Change Detection ====================
    
    async def check_for_changes(self) -> Optional[ChangeEvent]:
        """
        Prüft auf Änderungen seit dem letzten Check.
        
        Returns:
            ChangeEvent wenn Änderung erkannt, sonst None
        """
        self.stats['checks_performed'] += 1
        self.stats['last_check'] = datetime.now()
        
        # Capture anfordern
        await self.capture()
        
        # Warte kurz auf Antwort
        await asyncio.sleep(0.5)
        
        # Hole aktuellen Kontext
        if not self.moire_client:
            return None
        
        ui_context = self.moire_client.get_current_context()
        if not ui_context:
            return None
        
        # Erstelle neuen State
        new_state = self._create_state(ui_context)
        
        # Vergleiche mit vorherigem State
        if self.current_state:
            change_event = self._compare_states(self.current_state, new_state)
            
            if change_event and change_event.change_type != ChangeType.NO_CHANGE:
                self._record_change(change_event)
                
                # Notifiziere Handler
                for handler in self._on_change:
                    try:
                        handler(change_event)
                    except Exception as e:
                        logger.error(f"Change handler error: {e}")
                
                # Signifikante Änderungen
                if change_event.significance >= self.min_change_threshold:
                    self.stats['significant_changes'] += 1
                    for handler in self._on_significant_change:
                        try:
                            handler(change_event)
                        except Exception as e:
                            logger.error(f"Significant change handler error: {e}")
                
                return change_event
        
        # Aktualisiere State
        if self.current_state:
            self.previous_states.append(self.current_state)
            # Begrenze History
            if len(self.previous_states) > 50:
                self.previous_states = self.previous_states[-50:]
        
        self.current_state = new_state
        return None
    
    def _create_state(self, ui_context) -> MonitorState:
        """Erstellt einen MonitorState aus UI-Kontext."""
        elements = ui_context.elements if hasattr(ui_context, 'elements') else []
        
        # Erstelle Hashes für Elemente
        element_hashes = {}
        all_texts = []
        
        for elem in elements:
            elem_id = elem.id if hasattr(elem, 'id') else str(elem.get('id', ''))
            
            # Hash aus Position, Größe, Text
            if hasattr(elem, 'bounds'):
                bounds = elem.bounds
            else:
                bounds = elem.get('bounds', {})
            
            text = elem.text if hasattr(elem, 'text') else elem.get('text')
            
            hash_input = f"{bounds.get('x', 0)}:{bounds.get('y', 0)}:{bounds.get('width', 0)}:{bounds.get('height', 0)}:{text or ''}"
            element_hashes[elem_id] = hash(hash_input)
            
            if text:
                all_texts.append(text)
        
        # Gesamt-Text-Hash
        text_hash = hash('|'.join(sorted(all_texts)))
        
        return MonitorState(
            version=ui_context.version if hasattr(ui_context, 'version') else 0,
            timestamp=datetime.now(),
            element_count=len(elements),
            element_hashes=element_hashes,
            text_hash=str(text_hash),
            is_monitoring=self.is_monitoring
        )
    
    def _compare_states(
        self,
        old_state: MonitorState,
        new_state: MonitorState
    ) -> ChangeEvent:
        """Vergleicht zwei States und ermittelt Änderungen."""
        affected_elements = []
        delta = {
            'added': [],
            'removed': [],
            'modified': [],
            'text_changed': False
        }
        
        old_ids = set(old_state.element_hashes.keys())
        new_ids = set(new_state.element_hashes.keys())
        
        # Neue Elemente
        added = new_ids - old_ids
        delta['added'] = list(added)
        affected_elements.extend(added)
        
        # Entfernte Elemente
        removed = old_ids - new_ids
        delta['removed'] = list(removed)
        affected_elements.extend(removed)
        
        # Geänderte Elemente (gleiche ID, anderer Hash)
        common = old_ids & new_ids
        for elem_id in common:
            if old_state.element_hashes[elem_id] != new_state.element_hashes[elem_id]:
                delta['modified'].append(elem_id)
                affected_elements.append(elem_id)
        
        # Text-Änderungen
        delta['text_changed'] = old_state.text_hash != new_state.text_hash
        
        # Bestimme Änderungstyp
        if not affected_elements and not delta['text_changed']:
            change_type = ChangeType.NO_CHANGE
        elif delta['added'] and delta['removed']:
            change_type = ChangeType.LAYOUT_CHANGED
        elif delta['added']:
            change_type = ChangeType.ELEMENT_ADDED
        elif delta['removed']:
            change_type = ChangeType.ELEMENT_REMOVED
        elif delta['text_changed']:
            change_type = ChangeType.TEXT_CHANGED
        else:
            change_type = ChangeType.POSITION_CHANGED
        
        # Berechne Signifikanz
        total_change = len(delta['added']) + len(delta['removed']) + len(delta['modified'])
        if old_state.element_count > 0:
            significance = min(1.0, total_change / old_state.element_count)
        else:
            significance = 1.0 if total_change > 0 else 0.0
        
        # Text-Änderung erhöht Signifikanz
        if delta['text_changed']:
            significance = min(1.0, significance + 0.3)
        
        return ChangeEvent(
            timestamp=datetime.now(),
            change_type=change_type,
            affected_elements=affected_elements,
            delta=delta,
            significance=significance
        )
    
    def _record_change(self, event: ChangeEvent):
        """Zeichnet Änderung auf."""
        self.change_history.append(event)
        self.stats['changes_detected'] += 1
        self.stats['last_change'] = event.timestamp
        
        # Begrenze History
        if len(self.change_history) > 100:
            self.change_history = self.change_history[-100:]
        
        logger.info(
            f"Change detected: {event.change_type.value} "
            f"(significance: {event.significance:.2f}, "
            f"affected: {len(event.affected_elements)} elements)"
        )
    
    # ==================== MoireServer Commands ====================
    
    async def capture(self) -> Dict[str, Any]:
        """Fordert ein Capture vom MoireServer an."""
        if not self.moire_client:
            return {'success': False, 'error': 'No MoireServer client'}
        
        try:
            await self.moire_client.capture_desktop()
            return {'success': True}
        except Exception as e:
            logger.error(f"Capture failed: {e}")
            return {'success': False, 'error': str(e)}
    
    async def trigger_ocr(self) -> Dict[str, Any]:
        """Fordert OCR vom MoireServer an."""
        if not self.moire_client:
            return {'success': False, 'error': 'No MoireServer client'}
        
        try:
            await self.moire_client.run_ocr()
            return {'success': True}
        except Exception as e:
            logger.error(f"OCR trigger failed: {e}")
            return {'success': False, 'error': str(e)}
    
    # ==================== Query Methods ====================
    
    def get_current_state(self) -> Optional[MonitorState]:
        """Gibt aktuellen State zurück."""
        return self.current_state
    
    def get_change_history(self, limit: int = 10) -> List[ChangeEvent]:
        """Gibt letzte Änderungen zurück."""
        return self.change_history[-limit:]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Gibt Statistiken zurück."""
        return {
            **self.stats,
            'is_monitoring': self.is_monitoring,
            'check_interval': self.check_interval,
            'change_history_size': len(self.change_history),
            'current_state_version': self.current_state.version if self.current_state else None
        }
    
    def has_recent_change(self, within_seconds: float = 5.0) -> bool:
        """Prüft ob kürzlich eine Änderung war."""
        if not self.change_history:
            return False
        
        last_change = self.change_history[-1]
        age = (datetime.now() - last_change.timestamp).total_seconds()
        return age <= within_seconds
    
    def get_change_summary(self) -> str:
        """Gibt Zusammenfassung der letzten Änderungen zurück."""
        if not self.change_history:
            return "Keine Änderungen aufgezeichnet"
        
        lines = [f"Monitor Status: {'Aktiv' if self.is_monitoring else 'Inaktiv'}"]
        lines.append(f"Checks: {self.stats['checks_performed']}, Änderungen: {self.stats['changes_detected']}")
        lines.append("")
        lines.append("Letzte Änderungen:")
        
        for event in self.change_history[-5:]:
            age = (datetime.now() - event.timestamp).total_seconds()
            lines.append(
                f"  - {event.change_type.value} vor {age:.1f}s "
                f"(Signifikanz: {event.significance:.2f})"
            )
        
        return "\n".join(lines)
    
    # ==================== Waiting Methods ====================
    
    async def wait_for_change(
        self,
        timeout: float = 30.0,
        min_significance: float = 0.0
    ) -> Optional[ChangeEvent]:
        """
        Wartet auf eine Änderung.
        
        Args:
            timeout: Maximale Wartezeit
            min_significance: Minimale Signifikanz
        
        Returns:
            ChangeEvent oder None bei Timeout
        """
        start_time = time.time()
        initial_count = len(self.change_history)
        
        while time.time() - start_time < timeout:
            if len(self.change_history) > initial_count:
                latest = self.change_history[-1]
                if latest.significance >= min_significance:
                    return latest
            
            await asyncio.sleep(0.1)
        
        return None
    
    async def wait_for_stable_state(
        self,
        stability_duration: float = 2.0,
        timeout: float = 30.0
    ) -> bool:
        """
        Wartet bis der Screen stabil ist (keine Änderungen mehr).
        
        Args:
            stability_duration: Wie lange keine Änderung für "stabil"
            timeout: Maximale Wartezeit
        
        Returns:
            True wenn stabil, False bei Timeout
        """
        start_time = time.time()
        last_change_time = time.time()
        
        while time.time() - start_time < timeout:
            if self.change_history:
                latest = self.change_history[-1]
                last_change_time = latest.timestamp.timestamp()
            
            time_since_last_change = time.time() - last_change_time
            if time_since_last_change >= stability_duration:
                return True
            
            await asyncio.sleep(0.1)
        
        return False


# Singleton
_monitor_instance: Optional[MonitorAgent] = None


def get_monitor_agent() -> MonitorAgent:
    """Gibt Singleton-Instanz des Monitor Agents zurück."""
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = MonitorAgent()
    return _monitor_instance