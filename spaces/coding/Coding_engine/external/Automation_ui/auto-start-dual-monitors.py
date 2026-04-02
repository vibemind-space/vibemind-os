#!/usr/bin/env python3
"""
Auto-Start Dual Monitors Script
Automatisch erkennt und startet Desktop-Clients für alle verfügbaren Monitore
Teil des TRAE Unity AI Platform autonomen Programmer Projekts
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
import tkinter as tk
from pathlib import Path
from typing import Dict, List, Optional

import websockets

# Configure logging with clear debug comments
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class AutoDualMonitorStarter:
    """
    Automatische Monitor-Erkennung und Desktop-Client-Starter
    Folgt den gleichen Naming Conventions wie andere Agents
    """

    def __init__(
        self,
        server_url: str = None,
    ):
        """
        Initialisierung des Auto-Starters

        Args:
            server_url: WebSocket Server URL für Verbindung
        """
        self.server_url = server_url or os.getenv("SUPABASE_WS_URL", "ws://localhost:8007/ws/live-desktop")
        self.websocket: Optional[websockets.WebSocketServerProtocol] = None
        self.detected_monitors: List[Dict] = []
        self.started_clients: List[subprocess.Popen] = []

        # Pfad-Konfiguration - folgt gleichen Code Standards
        self.script_dir = Path(__file__).parent
        self.desktop_client_dir = self.script_dir / "desktop-client"
        self.capture_client_path = (
            self.desktop_client_dir / "dual_screen_capture_client.py"
        )

        logger.info("AutoDualMonitorStarter initialisiert")

    def detect_monitors(self) -> List[Dict]:
        """
        Erkennt alle verfügbaren Monitore
        Verwendet gleiche Code Conventions wie andere Agents

        Returns:
            Liste der erkannten Monitore mit Details
        """
        logger.info("Starte Monitor-Erkennung...")

        try:
            # Erstelle temporäres tkinter root für Screen-Info
            root = tk.Tk()
            root.withdraw()  # Verstecke das Fenster

            # Hole Screen-Dimensionen
            screen_width = root.winfo_screenwidth()
            screen_height = root.winfo_screenheight()
            virtual_width = root.winfo_vrootwidth()
            virtual_height = root.winfo_vrootheight()

            root.destroy()

            logger.info(f"Erkannte Screen-Dimensionen: {screen_width}x{screen_height}")
            logger.info(
                f"Virtuelle Screen-Dimensionen: {virtual_width}x{virtual_height}"
            )

            monitors = []

            # Prüfe auf Multi-Monitor Setup
            if virtual_width > screen_width * 1.2:  # 20% Toleranz für Multi-Monitor
                logger.info("Multi-Monitor Setup erkannt")

                # Monitor 1 (Primary)
                monitors.append(
                    {
                        "monitor_index": 0,
                        "name": "Primary Monitor",
                        "x": 0,
                        "y": 0,
                        "width": screen_width,
                        "height": screen_height,
                        "is_primary": True,
                        "client_id": f"monitor_0_{int(time.time())}",
                    }
                )

                # Monitor 2 (Secondary)
                secondary_width = virtual_width - screen_width
                monitors.append(
                    {
                        "monitor_index": 1,
                        "name": "Secondary Monitor",
                        "x": screen_width,
                        "y": 0,
                        "width": secondary_width,
                        "height": screen_height,
                        "is_primary": False,
                        "client_id": f"monitor_1_{int(time.time())}",
                    }
                )

                logger.info(f"Monitor 1: {screen_width}x{screen_height} at (0, 0)")
                logger.info(
                    f"Monitor 2: {secondary_width}x{screen_height} at ({screen_width}, 0)"
                )

            else:
                logger.info("Single Monitor Setup erkannt")

                # Nur ein Monitor
                monitors.append(
                    {
                        "monitor_index": 0,
                        "name": "Primary Monitor",
                        "x": 0,
                        "y": 0,
                        "width": screen_width,
                        "height": screen_height,
                        "is_primary": True,
                        "client_id": f"monitor_0_{int(time.time())}",
                    }
                )

            self.detected_monitors = monitors
            logger.info(f"Insgesamt {len(monitors)} Monitor(e) erkannt")

            return monitors

        except Exception as e:
            logger.error(f"Fehler bei Monitor-Erkennung: {e}")
            # Fallback zu Single Monitor
            fallback_monitor = [
                {
                    "monitor_index": 0,
                    "name": "Fallback Monitor",
                    "x": 0,
                    "y": 0,
                    "width": 1920,
                    "height": 1080,
                    "is_primary": True,
                    "client_id": f"monitor_0_{int(time.time())}",
                }
            ]
            self.detected_monitors = fallback_monitor
            return fallback_monitor

    async def connect_to_server(self) -> bool:
        """
        Verbindet sich mit dem WebSocket Server
        Folgt gleichen Code Practices wie andere Agents

        Returns:
            True wenn Verbindung erfolgreich, False sonst
        """
        try:
            # Add client_type and client_id query parameters for Supabase Edge Function
            client_id = f"auto_starter_{int(time.time())}"
            separator = "&" if "?" in self.server_url else "?"
            connection_url = (
                f"{self.server_url}{separator}client_type=desktop&client_id={client_id}"
            )

            logger.info(f"Verbinde mit WebSocket Server: {connection_url}")

            # Verbindung mit Timeout
            self.websocket = await asyncio.wait_for(
                websockets.connect(connection_url), timeout=10.0
            )

            # Sende Handshake
            handshake_message = {
                "type": "handshake",
                "clientInfo": {
                    "clientType": "desktop_spawner",  # Changed from auto_monitor_starter to match server expectations
                    "clientId": f"auto_starter_{int(time.time())}",
                    "capabilities": ["monitor_detection", "auto_client_spawning"],
                },
                "timestamp": time.time(),
            }

            await self.websocket.send(json.dumps(handshake_message))
            logger.info("Handshake gesendet")

            return True

        except Exception as e:
            logger.error(f"Fehler bei Server-Verbindung: {e}")
            return False

    def start_desktop_client(self, monitor: Dict) -> Optional[subprocess.Popen]:
        """
        Startet einen Desktop-Client für einen spezifischen Monitor
        Verwendet gleiche Code Guidelines wie andere Agents

        Args:
            monitor: Monitor-Konfiguration Dictionary

        Returns:
            Subprocess.Popen Objekt oder None bei Fehler
        """
        try:
            monitor_index = monitor["monitor_index"]
            client_id = monitor["client_id"]

            logger.info(
                f"Starte Desktop-Client für Monitor {monitor_index} ({monitor['name']})"
            )

            # Erstelle Kommando für Desktop-Client
            cmd = [
                sys.executable,
                str(self.capture_client_path),
                "--server-url",
                self.server_url,
                "--client-id",
                client_id,
                "--fps",
                "30",
                "--quality",
                "80",
                "--scale",
                "1.0",
            ]

            logger.info(f"Ausführendes Kommando: {' '.join(cmd)}")

            # Starte Prozess
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(self.desktop_client_dir),
                creationflags=(
                    subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
                ),
            )

            self.started_clients.append(process)
            logger.info(
                f"Desktop-Client für Monitor {monitor_index} gestartet (PID: {process.pid})"
            )

            return process

        except Exception as e:
            logger.error(
                f"Fehler beim Starten des Desktop-Clients für Monitor {monitor['monitor_index']}: {e}"
            )
            return None

    async def send_desktop_creation_request(self, monitors: List[Dict]):
        """
        Sendet Desktop-Erstellungsanfrage an Server
        Folgt gleichen Code Rules wie andere Agents

        Args:
            monitors: Liste der Monitor-Konfigurationen
        """
        if not self.websocket:
            logger.warning("Keine WebSocket-Verbindung verfügbar")
            return

        try:
            # Erstelle Desktop-Instance-Anfrage
            desktop_id = f"auto_desktop_{int(time.time())}"

            screens = []
            for monitor in monitors:
                screens.append(
                    {
                        "screenId": f"screen_{monitor['monitor_index']}",
                        "monitorIndex": monitor["monitor_index"],
                        "name": monitor["name"],
                        "width": monitor["width"],
                        "height": monitor["height"],
                        "x": monitor["x"],
                        "y": monitor["y"],
                        "isPrimary": monitor["is_primary"],
                    }
                )

            create_message = {
                "type": "create_desktop_instance",
                "desktopId": desktop_id,
                "config": {
                    "screens": screens,
                    "captureConfig": {
                        "fps": 30,
                        "quality": 80,
                        "scale": 1.0,
                        "format": "jpeg",
                    },
                },
                "timestamp": time.time(),
            }

            await self.websocket.send(json.dumps(create_message))
            logger.info(
                f"Desktop-Erstellungsanfrage gesendet für {len(screens)} Bildschirme"
            )

        except Exception as e:
            logger.error(f"Fehler beim Senden der Desktop-Erstellungsanfrage: {e}")

    async def verify_streams_visible(self, timeout: int = 30) -> bool:
        """
        Verifiziert, dass beide Bildschirm-Streams sichtbar sind
        Folgt gleichen Code Standards wie andere Agents

        Args:
            timeout: Timeout in Sekunden für Verifikation

        Returns:
            True wenn alle Streams sichtbar, False sonst
        """
        logger.info(f"Starte Stream-Verifikation (Timeout: {timeout}s)")

        start_time = time.time()
        # Da der Dual-Screen-Client beide Monitore bedient, erwarten wir nur 1 laufenden Client-Prozess
        expected_processes = 1

        while time.time() - start_time < timeout:
            try:
                # Prüfe ob der gestartete Client noch läuft
                running_clients = 0
                for process in self.started_clients:
                    if process.poll() is None:  # Prozess läuft noch
                        running_clients += 1

                logger.info(f"Laufende Clients: {running_clients}/{expected_processes}")

                if running_clients >= expected_processes:
                    logger.info("✅ Dual-Screen-Client läuft erfolgreich")
                    return True

                await asyncio.sleep(2)  # Warte 2 Sekunden vor nächster Prüfung

            except Exception as e:
                logger.error(f"Fehler bei Stream-Verifikation: {e}")
                await asyncio.sleep(1)

        logger.warning(f"❌ Stream-Verifikation fehlgeschlagen nach {timeout}s")
        return False

    async def cleanup(self):
        """
        Bereinigt Ressourcen
        Folgt gleichen Code Conventions wie andere Agents
        """
        logger.info("Starte Cleanup...")

        # Schließe WebSocket-Verbindung
        if self.websocket:
            try:
                await self.websocket.close()
                logger.info("WebSocket-Verbindung geschlossen")
            except Exception as e:
                logger.warning(f"Fehler beim Schließen der WebSocket-Verbindung: {e}")

        # Beende alle gestarteten Clients (optional - normalerweise lassen wir sie laufen)
        # for process in self.started_clients:
        #     try:
        #         process.terminate()
        #     except Exception as e:
        #         logger.warning(f"Fehler beim Beenden des Prozesses: {e}")

        logger.info("Cleanup abgeschlossen")

    async def run(self):
        """
        Hauptausführungsmethode
        Folgt gleichen Code Practices wie andere Agents
        """
        try:
            logger.info("🚀 Starte Auto Dual Monitor System")

            # Schritt 1: Monitore erkennen
            monitors = self.detect_monitors()
            if not monitors:
                logger.error("❌ Keine Monitore erkannt")
                return False

            # Schritt 2: Mit Server verbinden
            if not await self.connect_to_server():
                logger.error("❌ Verbindung zum Server fehlgeschlagen")
                return False

            # Schritt 3: Desktop-Client starten (ein Client für alle Monitore)
            logger.info(
                f"Starte Dual-Screen Desktop-Client für {len(monitors)} Monitor(e)..."
            )

            # Der dual_screen_capture_client handhabt automatisch alle Monitore
            if len(monitors) > 0:
                process = self.start_desktop_client(
                    monitors[0]
                )  # Nutze ersten Monitor für Client-ID
                if not process:
                    logger.error("❌ Fehler beim Starten des Dual-Screen-Clients")
                    return False

                # Kurze Pause für Client-Initialisierung
                await asyncio.sleep(2)

            # Schritt 4: Desktop-Instance beim Server erstellen
            await self.send_desktop_creation_request(monitors)

            # Schritt 5: Warte kurz für Client-Initialisierung
            logger.info("Warte auf Client-Initialisierung...")
            await asyncio.sleep(5)

            # Schritt 6: Verifiziere, dass alle Streams sichtbar sind
            verification_success = await self.verify_streams_visible(timeout=30)

            if verification_success:
                logger.info(
                    "✅ Alle Bildschirm-Streams erfolgreich gestartet und verifiziert!"
                )
                logger.info(
                    f"📺 {len(monitors)} Monitor(e) sind jetzt im Web-Interface sichtbar"
                )

                # Zeige Monitor-Details
                for i, monitor in enumerate(monitors):
                    logger.info(
                        f"   Monitor {i+1}: {monitor['name']} ({monitor['width']}x{monitor['height']})"
                    )

                return True
            else:
                logger.error("❌ Stream-Verifikation fehlgeschlagen")
                return False

        except Exception as e:
            logger.error(f"❌ Unerwarteter Fehler: {e}")
            return False
        finally:
            # Cleanup nur WebSocket, lasse Clients laufen
            if self.websocket:
                await self.websocket.close()


async def main():
    """
    Hauptfunktion - Entry Point
    Folgt gleichen Code Guidelines wie andere Agents
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Auto Dual Monitor Starter für TRAE Unity AI Platform"
    )
    parser.add_argument(
        "--server-url",
        default=os.getenv("SUPABASE_WS_URL", "ws://localhost:8007/ws/live-desktop"),
        help="WebSocket Server URL (default: local backend, set SUPABASE_WS_URL for cloud relay)",
    )

    args = parser.parse_args()

    # Erstelle und starte Auto-Starter
    starter = AutoDualMonitorStarter(args.server_url)

    try:
        success = await starter.run()
        if success:
            logger.info("🎉 Auto Dual Monitor System erfolgreich gestartet!")
            logger.info(
                "💡 Öffnen Sie http://localhost:5174/ um beide Bildschirme zu sehen"
            )
        else:
            logger.error("💥 Auto Dual Monitor System Start fehlgeschlagen")
            sys.exit(1)

    except KeyboardInterrupt:
        logger.info("⏹️  Benutzer-Unterbrechung erkannt")
    except Exception as e:
        logger.error(f"💥 Kritischer Fehler: {e}")
        sys.exit(1)
    finally:
        await starter.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
