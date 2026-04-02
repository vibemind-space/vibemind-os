"""
Selection Manager - Tracks and manages text selection via clipboard.

Provides:
- Reading current clipboard content
- Detecting if text is selected (via Ctrl+C)
- Clipboard state tracking
- Selection history
"""

import asyncio
import logging
import subprocess
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ClipboardState(Enum):
    """Clipboard-Zustand."""
    EMPTY = "empty"
    TEXT = "text"
    IMAGE = "image"
    FILES = "files"
    UNKNOWN = "unknown"


@dataclass
class SelectionSnapshot:
    """Ein Snapshot der Selektion."""
    text: str
    timestamp: float
    source: str  # 'user' oder 'auto'
    char_count: int = 0
    word_count: int = 0
    line_count: int = 0
    
    def __post_init__(self):
        if self.text:
            self.char_count = len(self.text)
            self.word_count = len(self.text.split())
            self.line_count = len(self.text.splitlines())


@dataclass 
class ClipboardInfo:
    """Informationen über Clipboard-Inhalt."""
    state: ClipboardState
    text: Optional[str] = None
    text_length: int = 0
    timestamp: float = 0.0
    
    @property
    def has_text(self) -> bool:
        return self.state == ClipboardState.TEXT and self.text is not None


class SelectionManager:
    """
    Selection Manager - Verwaltet Text-Selektion via Clipboard.
    
    Verwendet PowerShell für Windows Clipboard-Zugriff.
    """
    
    def __init__(self, max_history: int = 20):
        self.max_history = max_history
        self.selection_history: List[SelectionSnapshot] = []
        self.last_clipboard: Optional[ClipboardInfo] = None
        self._previous_clipboard: Optional[str] = None
    
    async def read_clipboard(self) -> ClipboardInfo:
        """
        Liest aktuellen Clipboard-Inhalt.
        
        Returns:
            ClipboardInfo mit Text und Metadaten
        """
        try:
            # PowerShell: Get-Clipboard
            process = await asyncio.create_subprocess_exec(
                'powershell', '-Command', 'Get-Clipboard',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.warning(f"Clipboard read failed: {stderr.decode('utf-8', errors='ignore')}")
                return ClipboardInfo(state=ClipboardState.UNKNOWN, timestamp=time.time())
            
            text = stdout.decode('utf-8', errors='ignore').strip()
            
            if not text:
                return ClipboardInfo(
                    state=ClipboardState.EMPTY,
                    timestamp=time.time()
                )
            
            info = ClipboardInfo(
                state=ClipboardState.TEXT,
                text=text,
                text_length=len(text),
                timestamp=time.time()
            )
            
            self.last_clipboard = info
            return info
        
        except Exception as e:
            logger.error(f"Clipboard read error: {e}")
            return ClipboardInfo(state=ClipboardState.UNKNOWN, timestamp=time.time())
    
    async def write_clipboard(self, text: str) -> bool:
        """
        Schreibt Text in Clipboard.
        
        Args:
            text: Zu schreibender Text
        
        Returns:
            True bei Erfolg
        """
        try:
            process = await asyncio.create_subprocess_exec(
                'powershell', '-Command', 'Set-Clipboard -Value $input',
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate(input=text.encode('utf-8'))
            
            if process.returncode != 0:
                logger.error(f"Clipboard write failed: {stderr.decode('utf-8', errors='ignore')}")
                return False
            
            return True
        
        except Exception as e:
            logger.error(f"Clipboard write error: {e}")
            return False
    
    async def clear_clipboard(self) -> bool:
        """Leert das Clipboard."""
        try:
            process = await asyncio.create_subprocess_exec(
                'powershell', '-Command', 'Set-Clipboard -Value $null',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            return process.returncode == 0
        except Exception as e:
            logger.error(f"Clipboard clear error: {e}")
            return False
    
    async def capture_selection(
        self,
        interaction_agent: Any = None,
        source: str = 'auto'
    ) -> Optional[SelectionSnapshot]:
        """
        Erfasst aktuelle Selektion durch Kopieren (Ctrl+C).
        
        Args:
            interaction_agent: InteractionAgent für Hotkey
            source: Quelle der Erfassung ('user' oder 'auto')
        
        Returns:
            SelectionSnapshot oder None wenn nichts markiert
        """
        try:
            # Speichere vorherigen Clipboard-Inhalt
            previous = await self.read_clipboard()
            self._previous_clipboard = previous.text if previous.has_text else None
            
            # Leere Clipboard
            await self.clear_clipboard()
            await asyncio.sleep(0.05)
            
            # Kopiere Selektion
            if interaction_agent:
                await interaction_agent.hotkey('ctrl', 'c')
            else:
                # Fallback: subprocess
                subprocess.run(
                    ['powershell', '-Command', 
                     'Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait("^c")'],
                    capture_output=True
                )
            
            # Kurze Pause für Clipboard-Update
            await asyncio.sleep(0.15)
            
            # Lese neuen Clipboard-Inhalt
            current = await self.read_clipboard()
            
            if current.has_text and current.text:
                snapshot = SelectionSnapshot(
                    text=current.text,
                    timestamp=time.time(),
                    source=source
                )
                
                # Zur History hinzufügen
                self.selection_history.append(snapshot)
                if len(self.selection_history) > self.max_history:
                    self.selection_history = self.selection_history[-self.max_history:]
                
                logger.info(f"Selection captured: {snapshot.char_count} chars, {snapshot.word_count} words")
                return snapshot
            
            logger.info("No selection captured")
            return None
        
        except Exception as e:
            logger.error(f"Selection capture failed: {e}")
            return None
    
    async def restore_previous_clipboard(self) -> bool:
        """Stellt vorherigen Clipboard-Inhalt wieder her."""
        if self._previous_clipboard:
            return await self.write_clipboard(self._previous_clipboard)
        return await self.clear_clipboard()
    
    async def has_selection(self, interaction_agent: Any = None) -> bool:
        """
        Prüft ob aktuell Text markiert ist.
        
        Args:
            interaction_agent: Optional InteractionAgent
        
        Returns:
            True wenn Text markiert ist
        """
        snapshot = await self.capture_selection(interaction_agent, source='check')
        return snapshot is not None and snapshot.char_count > 0
    
    def get_last_selection(self) -> Optional[SelectionSnapshot]:
        """Gibt letzte Selektion zurück."""
        if self.selection_history:
            return self.selection_history[-1]
        return None
    
    def get_selection_history(self, limit: int = 5) -> List[SelectionSnapshot]:
        """Gibt letzte n Selektionen zurück."""
        return self.selection_history[-limit:]
    
    def clear_history(self):
        """Löscht Selection-History."""
        self.selection_history.clear()
    
    async def get_selection_stats(self) -> Dict[str, Any]:
        """
        Gibt Statistiken über aktuelle Selektion zurück.
        
        Returns:
            Dict mit char_count, word_count, line_count etc.
        """
        current = await self.read_clipboard()
        
        if not current.has_text or not current.text:
            return {
                'has_selection': False,
                'char_count': 0,
                'word_count': 0,
                'line_count': 0
            }
        
        text = current.text
        return {
            'has_selection': True,
            'char_count': len(text),
            'word_count': len(text.split()),
            'line_count': len(text.splitlines()),
            'first_line': text.splitlines()[0] if text else '',
            'preview': text[:100] + '...' if len(text) > 100 else text
        }


# Singleton
_selection_manager_instance: Optional[SelectionManager] = None


def get_selection_manager() -> SelectionManager:
    """Gibt Singleton-Instanz des SelectionManagers zurück."""
    global _selection_manager_instance
    if _selection_manager_instance is None:
        _selection_manager_instance = SelectionManager()
    return _selection_manager_instance


def reset_selection_manager():
    """Setzt SelectionManager zurück."""
    global _selection_manager_instance
    _selection_manager_instance = None


# Test
async def _test_selection_manager():
    """Test SelectionManager."""
    sm = get_selection_manager()
    
    # Test Clipboard
    print("=== Clipboard Test ===")
    result = await sm.read_clipboard()
    print(f"Current clipboard: {result}")
    
    # Test Write
    await sm.write_clipboard("Test Text für Clipboard")
    result = await sm.read_clipboard()
    print(f"After write: {result.text}")
    
    # Test Clear
    await sm.clear_clipboard()
    result = await sm.read_clipboard()
    print(f"After clear: {result.state}")


if __name__ == "__main__":
    asyncio.run(_test_selection_manager())