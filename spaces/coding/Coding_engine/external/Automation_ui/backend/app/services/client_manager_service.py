"""
Client Manager Service für TRAE Backend

Verwaltet den Python Desktop Capture Client Prozess mit:
- Start/Stop Funktionalität
- Heartbeat-Überwachung (Watchdog)
- Auto-Restart bei Timeout oder Crash
- Status-Reporting

Author: TRAE Development Team
Version: 1.0.0
"""

import asyncio
import subprocess
import threading
import time
import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from enum import Enum

from ..logger_config import get_logger

logger = get_logger("client_manager")


class ClientStatus(str, Enum):
    """Status des Desktop Capture Clients"""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"
    RESTARTING = "restarting"


class ClientManagerService:
    """
    Verwaltet den Python Desktop Capture Client Prozess.
    
    Features:
    - Startet/Stoppt den Client als subprocess
    - Überwacht Heartbeats mit Watchdog-Thread
    - Automatischer Neustart bei Timeout oder Crash
    - Thread-safe Status-Management
    """
    
    # Konfiguration
    HEARTBEAT_TIMEOUT_SECONDS = 30  # Wenn 30s kein Heartbeat → Restart
    AUTO_RESTART_DELAY_SECONDS = 3  # Wartezeit vor Auto-Restart
    MAX_RESTART_ATTEMPTS = 5  # Maximale automatische Neustarts
    RESTART_COOLDOWN_MINUTES = 5  # Cool-down Periode für Restart-Zähler
    
    def __init__(self):
        """Initialisiert den Client Manager"""
        self._process: Optional[subprocess.Popen] = None
        self._status = ClientStatus.STOPPED
        self._last_heartbeat: Optional[datetime] = None
        self._start_time: Optional[datetime] = None
        self._restart_count = 0
        self._last_restart_reset: datetime = datetime.now()
        
        # Thread-Safety
        self._lock = threading.Lock()
        
        # Watchdog Thread
        self._watchdog_thread: Optional[threading.Thread] = None
        self._watchdog_running = False
        
        # Client-Script Pfad
        self._script_path = self._find_client_script()
        
        # Stats
        self._stats = {
            "total_starts": 0,
            "total_stops": 0,
            "total_restarts": 0,
            "total_heartbeats": 0,
            "uptime_seconds": 0
        }
        
        logger.info(f"[ClientManager] Initialisiert. Script-Pfad: {self._script_path}")
    
    def _find_client_script(self) -> Path:
        """Findet den Pfad zum Desktop Capture Client Script"""
        # Relative zum Backend-Verzeichnis
        backend_dir = Path(__file__).parent.parent.parent.parent
        
        # Mögliche Pfade
        possible_paths = [
            backend_dir / "desktop-client" / "dual_screen_capture_client.py",
            backend_dir.parent / "desktop-client" / "dual_screen_capture_client.py",
            Path.cwd() / "desktop-client" / "dual_screen_capture_client.py",
        ]
        
        for path in possible_paths:
            if path.exists():
                logger.info(f"[ClientManager] Script gefunden: {path}")
                return path
        
        # Default-Pfad wenn nicht gefunden
        default_path = backend_dir.parent / "desktop-client" / "dual_screen_capture_client.py"
        logger.warning(f"[ClientManager] Script nicht gefunden, verwende Default: {default_path}")
        return default_path
    
    @property
    def status(self) -> ClientStatus:
        """Gibt den aktuellen Client-Status zurück"""
        with self._lock:
            return self._status
    
    @property
    def is_running(self) -> bool:
        """Prüft ob der Client läuft"""
        return self.status == ClientStatus.RUNNING
    
    def get_status_info(self) -> Dict[str, Any]:
        """Gibt detaillierte Status-Informationen zurück"""
        with self._lock:
            uptime = 0
            if self._start_time and self._status == ClientStatus.RUNNING:
                uptime = (datetime.now() - self._start_time).total_seconds()
                self._stats["uptime_seconds"] = uptime
            
            last_heartbeat_ago = None
            if self._last_heartbeat:
                last_heartbeat_ago = (datetime.now() - self._last_heartbeat).total_seconds()
            
            return {
                "status": self._status.value,
                "is_running": self._status == ClientStatus.RUNNING,
                "pid": self._process.pid if self._process else None,
                "start_time": self._start_time.isoformat() if self._start_time else None,
                "uptime_seconds": uptime,
                "last_heartbeat": self._last_heartbeat.isoformat() if self._last_heartbeat else None,
                "last_heartbeat_ago_seconds": last_heartbeat_ago,
                "restart_count": self._restart_count,
                "script_path": str(self._script_path),
                "script_exists": self._script_path.exists(),
                "watchdog_active": self._watchdog_running,
                "stats": self._stats.copy()
            }
    
    async def start_client(self, auto_restart: bool = True, server_url: str = None) -> Dict[str, Any]:
        """
        Startet den Desktop Capture Client.

        Args:
            auto_restart: Ob automatischer Neustart bei Problemen aktiviert sein soll
            server_url: WebSocket URL für den Client (Default: ws://localhost:8007/ws/live-desktop)

        Returns:
            Status-Dictionary mit Ergebnis
        """
        with self._lock:
            if self._status in [ClientStatus.RUNNING, ClientStatus.STARTING]:
                return {
                    "success": False,
                    "error": f"Client ist bereits {self._status.value}",
                    "status": self._status.value
                }

            self._status = ClientStatus.STARTING

        logger.info("[ClientManager] Starte Desktop Capture Client...")

        try:
            # Prüfe ob Script existiert
            if not self._script_path.exists():
                raise FileNotFoundError(f"Client-Script nicht gefunden: {self._script_path}")

            # Python-Interpreter finden
            python_exe = sys.executable

            # Build command with server URL
            cmd = [python_exe, str(self._script_path)]
            ws_url = server_url or "ws://localhost:8007/ws/live-desktop"
            cmd.extend(["--server-url", ws_url])

            logger.info(f"[ClientManager] Command: {' '.join(cmd)}")

            # Starte den Prozess
            self._process = subprocess.Popen(
                cmd,
                cwd=str(self._script_path.parent),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0
            )
            
            with self._lock:
                self._status = ClientStatus.RUNNING
                self._start_time = datetime.now()
                self._last_heartbeat = datetime.now()  # Initial heartbeat
                self._stats["total_starts"] += 1
            
            logger.info(f"[ClientManager] Client gestartet mit PID: {self._process.pid}")
            
            # Starte Watchdog wenn Auto-Restart aktiviert
            if auto_restart:
                self._start_watchdog()
            
            # Starte Output-Reader Thread
            self._start_output_reader()
            
            return {
                "success": True,
                "message": "Desktop Capture Client gestartet",
                "pid": self._process.pid,
                "status": ClientStatus.RUNNING.value
            }
            
        except Exception as e:
            logger.error(f"[ClientManager] Fehler beim Starten: {e}")
            with self._lock:
                self._status = ClientStatus.ERROR
            return {
                "success": False,
                "error": str(e),
                "status": ClientStatus.ERROR.value
            }
    
    async def stop_client(self, force: bool = False) -> Dict[str, Any]:
        """
        Stoppt den Desktop Capture Client.
        
        Args:
            force: Erzwingt sofortiges Beenden (SIGKILL statt SIGTERM)
            
        Returns:
            Status-Dictionary mit Ergebnis
        """
        with self._lock:
            if self._status in [ClientStatus.STOPPED, ClientStatus.STOPPING]:
                return {
                    "success": True,
                    "message": f"Client ist bereits {self._status.value}",
                    "status": self._status.value
                }
            
            self._status = ClientStatus.STOPPING
        
        logger.info(f"[ClientManager] Stoppe Client (force={force})...")
        
        # Stoppe Watchdog
        self._stop_watchdog()
        
        try:
            if self._process:
                if force:
                    self._process.kill()
                else:
                    # Graceful shutdown
                    if sys.platform == 'win32':
                        self._process.terminate()
                    else:
                        import signal
                        self._process.send_signal(signal.SIGTERM)
                    
                    # Warte max 5 Sekunden auf Beendigung
                    try:
                        self._process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        logger.warning("[ClientManager] Timeout beim Stoppen, force kill...")
                        self._process.kill()
                
                self._process = None
            
            with self._lock:
                self._status = ClientStatus.STOPPED
                self._start_time = None
                self._stats["total_stops"] += 1
            
            logger.info("[ClientManager] Client gestoppt")
            
            return {
                "success": True,
                "message": "Desktop Capture Client gestoppt",
                "status": ClientStatus.STOPPED.value
            }
            
        except Exception as e:
            logger.error(f"[ClientManager] Fehler beim Stoppen: {e}")
            with self._lock:
                self._status = ClientStatus.ERROR
            return {
                "success": False,
                "error": str(e),
                "status": ClientStatus.ERROR.value
            }
    
    def receive_heartbeat(self, client_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Empfängt einen Heartbeat vom Client.
        
        Args:
            client_info: Optionale Zusatzinformationen vom Client
            
        Returns:
            Acknowledgment-Dictionary
        """
        with self._lock:
            self._last_heartbeat = datetime.now()
            self._stats["total_heartbeats"] += 1
            
            # Wenn Client als "nicht laufend" markiert war aber Heartbeats sendet
            if self._status != ClientStatus.RUNNING and self._process:
                self._status = ClientStatus.RUNNING
                logger.info("[ClientManager] Client sendet wieder Heartbeats - Status korrigiert")
        
        logger.debug(f"[ClientManager] Heartbeat empfangen. Info: {client_info}")
        
        return {
            "acknowledged": True,
            "timestamp": datetime.now().isoformat(),
            "server_status": self.status.value
        }
    
    def _start_watchdog(self):
        """Startet den Watchdog-Thread"""
        if self._watchdog_running:
            return
        
        self._watchdog_running = True
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop,
            daemon=True,
            name="ClientWatchdog"
        )
        self._watchdog_thread.start()
        logger.info("[ClientManager] Watchdog gestartet")
    
    def _stop_watchdog(self):
        """Stoppt den Watchdog-Thread"""
        self._watchdog_running = False
        if self._watchdog_thread and self._watchdog_thread.is_alive():
            self._watchdog_thread.join(timeout=2)
        self._watchdog_thread = None
        logger.info("[ClientManager] Watchdog gestoppt")
    
    def _watchdog_loop(self):
        """Watchdog-Schleife die Heartbeats und Prozess-Status überwacht"""
        while self._watchdog_running:
            try:
                time.sleep(5)  # Prüfe alle 5 Sekunden
                
                if not self._watchdog_running:
                    break
                
                with self._lock:
                    if self._status != ClientStatus.RUNNING:
                        continue
                    
                    # Prüfe ob Prozess noch läuft
                    if self._process:
                        poll_result = self._process.poll()
                        if poll_result is not None:
                            logger.warning(f"[ClientManager] Prozess unerwartet beendet (Code: {poll_result})")
                            self._trigger_restart("Prozess beendet")
                            continue
                    
                    # Prüfe Heartbeat-Timeout
                    if self._last_heartbeat:
                        time_since_heartbeat = (datetime.now() - self._last_heartbeat).total_seconds()
                        if time_since_heartbeat > self.HEARTBEAT_TIMEOUT_SECONDS:
                            logger.warning(f"[ClientManager] Heartbeat-Timeout ({time_since_heartbeat:.1f}s)")
                            self._trigger_restart("Heartbeat Timeout")
                    
                    # Reset Restart-Counter nach Cooldown
                    if (datetime.now() - self._last_restart_reset).total_seconds() > self.RESTART_COOLDOWN_MINUTES * 60:
                        self._restart_count = 0
                        self._last_restart_reset = datetime.now()
                
            except Exception as e:
                logger.error(f"[ClientManager] Watchdog Fehler: {e}")
        
        logger.info("[ClientManager] Watchdog-Loop beendet")
    
    def _trigger_restart(self, reason: str):
        """Löst einen automatischen Neustart aus"""
        if self._restart_count >= self.MAX_RESTART_ATTEMPTS:
            logger.error(f"[ClientManager] Max Restart-Versuche erreicht ({self.MAX_RESTART_ATTEMPTS})")
            self._status = ClientStatus.ERROR
            return
        
        self._restart_count += 1
        self._stats["total_restarts"] += 1
        self._status = ClientStatus.RESTARTING
        
        logger.info(f"[ClientManager] Auto-Restart #{self._restart_count} wegen: {reason}")
        
        # Restart in separatem Thread um Deadlock zu vermeiden
        def do_restart():
            time.sleep(self.AUTO_RESTART_DELAY_SECONDS)
            
            # Stoppe alten Prozess falls noch vorhanden
            if self._process:
                try:
                    self._process.kill()
                except Exception:
                    pass
                self._process = None
            
            # Starte neu
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.start_client(auto_restart=True))
            finally:
                loop.close()
        
        restart_thread = threading.Thread(target=do_restart, daemon=True)
        restart_thread.start()
    
    def _start_output_reader(self):
        """Startet Thread zum Lesen der Prozess-Ausgabe"""
        def read_output():
            if not self._process:
                return
            
            try:
                for line in iter(self._process.stdout.readline, b''):
                    if not line:
                        break
                    try:
                        decoded = line.decode('utf-8', errors='replace').strip()
                        if decoded:
                            logger.debug(f"[Client] {decoded}")
                    except Exception:
                        pass
            except Exception:
                pass
        
        reader_thread = threading.Thread(target=read_output, daemon=True)
        reader_thread.start()
    
    async def cleanup(self):
        """Bereinigt Ressourcen beim Herunterfahren"""
        logger.info("[ClientManager] Cleanup...")
        self._stop_watchdog()
        await self.stop_client(force=True)


# Singleton-Instanz
_client_manager_instance: Optional[ClientManagerService] = None


def get_client_manager() -> ClientManagerService:
    """Gibt die Singleton-Instanz des Client-Managers zurück"""
    global _client_manager_instance
    if _client_manager_instance is None:
        _client_manager_instance = ClientManagerService()
    return _client_manager_instance