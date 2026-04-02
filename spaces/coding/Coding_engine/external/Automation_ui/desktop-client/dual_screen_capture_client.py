#!/usr/bin/env python3
"""
Dual Screen Capture Client für TRAE Unity AI Platform
Erfasst ALLE Bildschirme gleichzeitig und sendet sie über WebSocket.

ULTRA-ROBUST VERSION v2.3: 
- mss Library für zuverlässige Multi-Monitor Screenshots
- Separate Tasks für unabhängige Fehlerbehandlung
- Auto-Reconnect bei Verbindungsverlust
- Command-Deduplication (keine doppelten Befehle)
- Alle Monitore werden gestreamt
- HEARTBEAT an Backend senden für Watchdog
- GRACEFUL SHUTDOWN bei SIGTERM/SIGINT

Requirements:
- pip install websockets Pillow pynput pyautogui screeninfo opencv-python numpy mss aiohttp

Usage:
python dual_screen_capture_client.py
python dual_screen_capture_client.py --server-url wss://...
"""

import argparse
import asyncio
import base64
import ctypes
import hashlib
import io
import json
import logging
import platform
import signal
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import mss
import pyautogui
import websockets
from PIL import Image
from screeninfo import get_monitors

# Optional: aiohttp für Heartbeat HTTP-Requests
try:
    import aiohttp

    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    print("[WARN] aiohttp not installed - Heartbeats only over WebSocket")


# ============================================================
# DPI-AWARENESS FIX für Multi-Monitor Screenshots
# MUSS vor jeglicher Monitor-Erkennung aktiviert werden!
# ============================================================
def enable_dpi_awareness():
    """
    Aktiviert Windows DPI-Awareness für korrekte Multi-Monitor-Screenshots.
    Ohne dies werden Koordinaten für Monitore mit unterschiedlicher Skalierung
    falsch berechnet, was zu schwarzen Screenshots führt.
    """
    if platform.system() != "Windows":
        return

    try:
        # Per-Monitor DPI Awareness v2 (Windows 10 1703+)
        # Dies ist die beste Option für Multi-Monitor-Setups
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except AttributeError:
        try:
            # Fallback: System DPI Awareness (ältere Windows-Versionen)
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    except Exception:
        try:
            # Zweiter Fallback
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


# DPI-Awareness SOFORT aktivieren, bevor irgendetwas anderes passiert
enable_dpi_awareness()

# Configure logging
log_file = Path(__file__).parent / "capture_client.log"
file_handler = logging.FileHandler(log_file, encoding="utf-8")
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[console_handler, file_handler],
)
logger = logging.getLogger(__name__)
(
    sys.stdout.reconfigure(line_buffering=True)
    if hasattr(sys.stdout, "reconfigure")
    else None
)


def get_stable_machine_id() -> str:
    config_dir = Path.home() / ".trae_desktop_client"
    config_file = config_dir / "machine_id.txt"
    if config_file.exists():
        try:
            stored_id = config_file.read_text().strip()
            if stored_id:
                return stored_id
        except Exception:
            pass
    hostname = platform.node() or "unknown_machine"
    hostname = "".join(c for c in hostname if c.isalnum() or c in "-_").lower()[:20]
    machine_hash = hashlib.sha256(
        f"{platform.machine()}{platform.processor()}".encode()
    ).hexdigest()[:8]
    machine_id = f"desktop_{hostname}_{machine_hash}"
    try:
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file.write_text(machine_id)
    except Exception:
        pass
    return machine_id


class RobustDualScreenCaptureClient:
    VERSION = "2.3-heartbeat"

    # Backend API URL für Heartbeats (localhost Backend)
    BACKEND_API_URL = "http://localhost:8007/api/client"
    HEARTBEAT_INTERVAL_SECONDS = 5

    def __init__(self, server_url: str, client_id: Optional[str] = None):
        self.server_url = server_url
        self.client_id = client_id or get_stable_machine_id()
        self.websocket = None
        self.is_connected = False
        self.is_capturing = False
        self.should_run = True
        self.capture_config = {"fps": 10, "quality": 75, "scale": 0.8, "format": "jpeg"}
        self.monitors: List[Dict[str, Any]] = []
        self.total_width = 0
        self.total_height = 0
        self._processed_command_ids: Set[str] = set()
        self.frame_counter = 0
        self.stats = {
            "frames_sent": 0,
            "frames_failed": 0,
            "avg_frame_size": 0,
            "start_time": time.time(),
            "reconnects": 0,
            "commands_processed": 0,
            "commands_deduplicated": 0,
            "heartbeats_sent": 0,
        }
        self._tasks: List[asyncio.Task] = []

        # mss Screenshot-Objekt für Multi-Monitor-Capture
        self._mss = mss.mss()

        # Graceful Shutdown Handling
        self._shutdown_event = asyncio.Event()
        self._setup_signal_handlers()

        self._detect_all_monitors()
        self._log_mss_monitors()  # Debug-Ausgabe für mss-Monitore
        logger.info(
            f"[INIT] Client: {self.client_id}, Monitore: {len(self.monitors)}, Version: {self.VERSION}"
        )

    def _setup_signal_handlers(self):
        """Richtet Signal-Handler für graceful shutdown ein."""

        def signal_handler(signum, frame):
            signal_name = signal.Signals(signum).name
            logger.info(
                f"[SIGNAL] {signal_name} empfangen - starte graceful shutdown..."
            )
            self.should_run = False
            self.is_capturing = False

            # Setze Event für async shutdown
            try:
                loop = asyncio.get_running_loop()
                loop.call_soon_threadsafe(self._shutdown_event.set)
            except RuntimeError:
                # Kein laufender Loop
                pass

        # Registriere Handler für SIGTERM und SIGINT
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

        # Auf Windows: zusätzlich SIGBREAK
        if sys.platform == "win32":
            try:
                signal.signal(signal.SIGBREAK, signal_handler)
            except (AttributeError, ValueError):
                pass

        logger.info("[INIT] Signal-Handler für graceful shutdown registriert")

    def _log_mss_monitors(self):
        """Loggt die erkannten mss-Monitore für Debugging."""
        logger.info("=" * 50)
        logger.info("[MSS] Erkannte mss-Monitore:")
        for i, mon in enumerate(self._mss.monitors):
            label = "ALL" if i == 0 else f"Monitor {i-1}"
            logger.info(
                f"   mss[{i}] ({label}): {mon['width']}x{mon['height']} @ ({mon['left']}, {mon['top']})"
            )

        # Vergleiche mit screeninfo
        logger.info("[MATCH] Monitor-Zuordnung (Position-basiert):")
        for idx, target in enumerate(self.monitors):
            matched_mss = self._find_mss_monitor_for_screeninfo(idx)
            if matched_mss is not None:
                mss_mon = self._mss.monitors[matched_mss]
                logger.info(
                    f"   screeninfo[{idx}] ({target['x']},{target['y']}) {target['width']}x{target['height']} -> mss[{matched_mss}] ({mss_mon['left']},{mss_mon['top']}) {mss_mon['width']}x{mss_mon['height']}"
                )
            else:
                logger.warning(
                    f"   screeninfo[{idx}] ({target['x']},{target['y']}) {target['width']}x{target['height']} -> KEIN MATCH!"
                )
        logger.info("=" * 50)

    def _find_mss_monitor_for_screeninfo(self, monitor_idx: int) -> Optional[int]:
        """
        Findet den passenden mss-Monitor-Index für einen screeninfo-Monitor.

        VERBESSERTE VERSION:
        - Toleranteres Position-Matching
        - Fallback auf Index-basiertes Matching
        - Besseres Logging für Debugging
        """
        if monitor_idx >= len(self.monitors):
            logger.warning(
                f"[MATCH] monitor_idx={monitor_idx} >= len(monitors)={len(self.monitors)}"
            )
            return None

        target = self.monitors[monitor_idx]
        target_x = target["x"]
        target_y = target["y"]
        target_w = target["width"]
        target_h = target["height"]

        # Strategie 1: Exaktes Positions-Match (mit großzügiger Toleranz)
        # DPI-Skalierung kann Koordinaten um bis zu 100 Pixel verschieben
        tolerance = 100
        for mss_idx, mss_mon in enumerate(self._mss.monitors):
            if mss_idx == 0:  # Skip "all monitors" (Index 0)
                continue

            x_match = abs(mss_mon["left"] - target_x) <= tolerance
            y_match = abs(mss_mon["top"] - target_y) <= tolerance

            if x_match and y_match:
                logger.debug(
                    f"[MATCH] Strategie 1: screeninfo[{monitor_idx}] -> mss[{mss_idx}] (Position-Match)"
                )
                return mss_idx

        # Strategie 2: Match nach Index (wenn Position nicht passt)
        # mss.monitors[0] = alle Monitore, mss.monitors[1] = erster Monitor, etc.
        # Also: screeninfo[0] -> mss[1], screeninfo[1] -> mss[2], etc.
        fallback_idx = monitor_idx + 1
        if fallback_idx < len(self._mss.monitors):
            mss_mon = self._mss.monitors[fallback_idx]
            # Prüfe ob die Größe ungefähr passt
            size_tolerance = 200  # Toleranz für DPI-Skalierung
            w_match = abs(mss_mon["width"] - target_w) <= size_tolerance
            h_match = abs(mss_mon["height"] - target_h) <= size_tolerance

            if w_match and h_match:
                logger.debug(
                    f"[MATCH] Strategie 2: screeninfo[{monitor_idx}] -> mss[{fallback_idx}] (Index+1 Fallback, Größe OK)"
                )
                return fallback_idx
            else:
                # Auch ohne Größenmatch verwenden, wenn keine bessere Option
                logger.warning(
                    f"[MATCH] Strategie 2 Fallback: screeninfo[{monitor_idx}] -> mss[{fallback_idx}] (Größe weicht ab: {mss_mon['width']}x{mss_mon['height']} vs {target_w}x{target_h})"
                )
                return fallback_idx

        # Strategie 3: Gar kein Match - letzter Fallback auf den ersten verfügbaren mss
        if len(self._mss.monitors) > 1:
            logger.warning(
                f"[MATCH] Strategie 3 Fallback: screeninfo[{monitor_idx}] -> mss[1] (letzter Fallback)"
            )
            return 1

        logger.error(
            f"[MATCH] Kein mss-Monitor verfügbar für screeninfo[{monitor_idx}]!"
        )
        return None

    def _detect_all_monitors(self):
        try:
            monitors = get_monitors()
            self.monitors = []
            min_x = min_y = float("inf")
            max_x = max_y = float("-inf")
            logger.info("=" * 50)
            logger.info("[MONITORS] Erkannte Monitore:")
            for i, mon in enumerate(monitors):
                monitor_info = {
                    "index": i,
                    "name": f"Monitor {i}",
                    "x": mon.x,
                    "y": mon.y,
                    "width": mon.width,
                    "height": mon.height,
                    "is_primary": getattr(mon, "is_primary", i == 0),
                }
                self.monitors.append(monitor_info)
                min_x = min(min_x, mon.x)
                max_x = max(max_x, mon.x + mon.width)
                min_y = min(min_y, mon.y)
                max_y = max(max_y, mon.y + mon.height)
                primary_str = " (PRIMARY)" if monitor_info["is_primary"] else ""
                logger.info(
                    f"   Monitor {i}: {mon.width}x{mon.height} @ ({mon.x}, {mon.y}){primary_str}"
                )
            self.total_width = max_x - min_x if self.monitors else 1920
            self.total_height = max_y - min_y if self.monitors else 1080
            logger.info(
                f"[MONITORS] Gesamt: {len(self.monitors)} Monitore, Desktop: {self.total_width}x{self.total_height}"
            )
            logger.info("=" * 50)
            if not self.monitors:
                self.monitors = [
                    {
                        "index": 0,
                        "name": "Monitor 0",
                        "x": 0,
                        "y": 0,
                        "width": 1920,
                        "height": 1080,
                        "is_primary": True,
                    }
                ]
        except Exception as e:
            logger.error(f"[ERROR] Monitor-Erkennung: {e}")
            self.monitors = [
                {
                    "index": 0,
                    "name": "Monitor 0",
                    "x": 0,
                    "y": 0,
                    "width": 1920,
                    "height": 1080,
                    "is_primary": True,
                }
            ]

    async def connect(self) -> bool:
        for attempt in range(5):
            if not self.should_run:
                return False
            try:
                separator = "&" if "?" in self.server_url else "?"
                url = f"{self.server_url}{separator}client_type=desktop&client_id={self.client_id}"
                logger.info(f"[CONNECT] Versuch {attempt+1}/5...")
                self.websocket = await asyncio.wait_for(
                    websockets.connect(
                        url,
                        ping_interval=15,
                        ping_timeout=10,
                        max_size=10 * 1024 * 1024,
                        close_timeout=5,
                    ),
                    timeout=15,
                )
                await self.websocket.send(
                    json.dumps(
                        {
                            "type": "handshake",
                            "clientInfo": {
                                "clientType": "dual_screen_desktop",
                                "clientId": self.client_id,
                                "monitors": self.monitors,
                                "hostname": platform.node(),
                                "version": self.VERSION,
                            },
                            "timestamp": time.time(),
                        }
                    )
                )
                response = await asyncio.wait_for(self.websocket.recv(), timeout=10)
                data = json.loads(response)
                if data.get("type") in ["connection_established", "handshake_ack"]:
                    self.is_connected = True
                    logger.info(
                        f"[OK] Verbunden! Streaming {len(self.monitors)} Monitor(e)"
                    )
                    return True
            except asyncio.TimeoutError:
                logger.warning(f"[TIMEOUT] Verbindungsversuch {attempt+1}")
            except Exception as e:
                logger.warning(f"[WARN] Fehler: {type(e).__name__}")
            await asyncio.sleep(min(2 * (attempt + 1), 8))
        return False

    def capture_screen(self, monitor_idx: int) -> Optional[Image.Image]:
        """
        Erfasst einen Screenshot des angegebenen Monitors mit mss.
        mss ist zuverlässiger für Multi-Monitor-Setups als PIL.ImageGrab.

        mss.monitors[0] = alle Monitore kombiniert
        mss.monitors[1] = erster Monitor
        mss.monitors[2] = zweiter Monitor, etc.

        WICHTIG: Wir matchen nach Position, nicht nach Index, da die Reihenfolge
        zwischen screeninfo und mss unterschiedlich sein kann!
        """
        try:
            # Finde passenden mss-Monitor
            mss_idx = self._find_mss_monitor_for_screeninfo(monitor_idx)

            if mss_idx is None:
                logger.error(
                    f"[CAPTURE] Kein mss-Monitor für screeninfo[{monitor_idx}] gefunden!"
                )
                return None

            if mss_idx >= len(self._mss.monitors):
                logger.error(
                    f"[CAPTURE] mss_idx={mss_idx} außerhalb des Bereichs (max={len(self._mss.monitors)-1})"
                )
                return None

            monitor = self._mss.monitors[mss_idx]
            screenshot = self._mss.grab(monitor)

            # Konvertiere zu PIL Image (BGRA -> RGB)
            img = Image.frombytes(
                "RGB", screenshot.size, screenshot.bgra, "raw", "BGRX"
            )

            # Debug: Prüfe ob Bild nicht komplett schwarz ist
            if self.frame_counter < 10:  # Für erste 10 Frames
                extrema = img.convert("L").getextrema()
                if extrema[1] < 10:  # Bild ist (fast) komplett schwarz
                    target = self.monitors[monitor_idx]
                    logger.warning(
                        f"[CAPTURE] Monitor {monitor_idx} liefert SCHWARZES Bild! "
                        f"screeninfo=({target['x']},{target['y']},{target['width']}x{target['height']}) "
                        f"-> mss[{mss_idx}]=({monitor['left']},{monitor['top']},{monitor['width']}x{monitor['height']})"
                    )
                elif self.frame_counter < 3:
                    logger.info(
                        f"[CAPTURE] Monitor {monitor_idx} OK: mss[{mss_idx}], brightness={extrema}"
                    )

            return img

        except Exception as e:
            logger.error(f"[CAPTURE] Fehler bei Monitor {monitor_idx}: {e}")
            import traceback

            traceback.print_exc()
            return None

    def process_image(self, image: Image.Image) -> Optional[str]:
        try:
            scale = self.capture_config.get("scale", 1.0)
            if scale != 1.0:
                new_size = (int(image.width * scale), int(image.height * scale))
                image = image.resize(new_size, Image.LANCZOS)
            buffer = io.BytesIO()
            image.save(
                buffer,
                format="JPEG",
                quality=self.capture_config.get("quality", 75),
                optimize=True,
            )
            return base64.b64encode(buffer.getvalue()).decode("utf-8")
        except Exception:
            return None

    async def send_frame(self, frame_data: str, monitor_idx: int) -> bool:
        if not self.websocket or not self.is_connected:
            return False
        try:
            self.frame_counter += 1
            frame_size = len(frame_data)
            message = {
                "type": "frame_data",
                "frameData": frame_data,
                "frameNumber": self.frame_counter,
                "timestamp": time.time(),
                "monitorId": f"monitor_{monitor_idx}",
                "metadata": {
                    "clientId": self.client_id,
                    "screenId": f"screen{monitor_idx}",
                    "format": "jpeg",
                    "quality": self.capture_config["quality"],
                    "frameSize": frame_size,
                    "monitorIndex": monitor_idx,
                    "totalMonitors": len(self.monitors),
                },
            }
            await self.websocket.send(json.dumps(message))
            self.stats["frames_sent"] += 1
            total = self.stats["frames_sent"]
            self.stats["avg_frame_size"] = (
                (self.stats["avg_frame_size"] * (total - 1)) + frame_size
            ) / total
            return True
        except websockets.exceptions.ConnectionClosed:
            self.is_connected = False
            return False
        except Exception:
            self.stats["frames_failed"] += 1
            return False

    async def capture_loop(self):
        logger.info(
            f"[CAPTURE] Starte Loop fuer {len(self.monitors)} Monitore: {[m['name'] for m in self.monitors]}"
        )
        last_stats_time = time.time()
        while self.should_run and self.is_capturing:
            if not self.is_connected:
                await asyncio.sleep(0.5)
                continue
            loop_start = time.time()
            for idx in range(len(self.monitors)):
                if (
                    not self.is_connected
                    or not self.is_capturing
                    or not self.should_run
                ):
                    break
                screen = self.capture_screen(idx)
                if screen:
                    data = self.process_image(screen)
                    if data:
                        await self.send_frame(data, idx)
            if time.time() - last_stats_time > 30:
                runtime = time.time() - self.stats["start_time"]
                fps_actual = self.stats["frames_sent"] / runtime if runtime > 0 else 0
                logger.info(
                    f"[STATS] {self.stats['frames_sent']} Frames, {fps_actual:.1f} fps, avg {self.stats['avg_frame_size']/1024:.0f}KB, "
                    + f"{self.stats['reconnects']} Reconnects, {len(self.monitors)} Mon, {self.stats['commands_deduplicated']} DupCmds, "
                    + f"{self.stats['heartbeats_sent']} Heartbeats"
                )
                last_stats_time = time.time()
            elapsed = time.time() - loop_start
            await asyncio.sleep(max(0.01, (1.0 / self.capture_config["fps"]) - elapsed))
        logger.info("[CAPTURE] Loop beendet")

    async def heartbeat_loop(self):
        """
        Sendet regelmäßig Heartbeats an das Backend API.
        Der Watchdog im Backend überwacht diese und startet den Client bei Ausfall neu.
        """
        logger.info(
            f"[HEARTBEAT] Loop gestartet ({self.HEARTBEAT_INTERVAL_SECONDS}s Intervall)"
        )

        # HTTP-Session für Heartbeats (wenn aiohttp verfügbar)
        session = None
        if AIOHTTP_AVAILABLE:
            try:
                session = aiohttp.ClientSession()
            except Exception as e:
                logger.warning(
                    f"[HEARTBEAT] aiohttp Session konnte nicht erstellt werden: {e}"
                )

        try:
            while self.should_run:
                try:
                    # Berechne aktuelle FPS
                    runtime = time.time() - self.stats["start_time"]
                    current_fps = (
                        self.stats["frames_sent"] / runtime if runtime > 0 else 0
                    )

                    heartbeat_data = {
                        "client_id": self.client_id,
                        "timestamp": time.time(),
                        "frames_sent": self.stats["frames_sent"],
                        "monitors": len(self.monitors),
                        "fps": round(current_fps, 2),
                        "status": "running" if self.is_capturing else "idle",
                        "error": None,
                    }

                    # Sende Heartbeat via HTTP an Backend API
                    if session and AIOHTTP_AVAILABLE:
                        try:
                            url = f"{self.BACKEND_API_URL}/heartbeat"
                            async with session.post(
                                url,
                                json=heartbeat_data,
                                timeout=aiohttp.ClientTimeout(total=5),
                            ) as resp:
                                if resp.status == 200:
                                    self.stats["heartbeats_sent"] += 1
                                    logger.debug(
                                        f"[HEARTBEAT] HTTP erfolgreich gesendet #{self.stats['heartbeats_sent']}"
                                    )
                                else:
                                    logger.warning(
                                        f"[HEARTBEAT] HTTP Fehler: {resp.status}"
                                    )
                        except asyncio.TimeoutError:
                            logger.debug(
                                "[HEARTBEAT] HTTP Timeout (Backend evtl. nicht erreichbar)"
                            )
                        except aiohttp.ClientError as e:
                            logger.debug(
                                f"[HEARTBEAT] HTTP Client-Fehler: {type(e).__name__}"
                            )
                        except Exception as e:
                            logger.debug(f"[HEARTBEAT] HTTP Fehler: {e}")

                    # Fallback: Sende auch über WebSocket (als Ping)
                    if self.websocket and self.is_connected:
                        try:
                            await self.websocket.send(
                                json.dumps(
                                    {
                                        "type": "client_heartbeat",
                                        "clientId": self.client_id,
                                        "stats": heartbeat_data,
                                        "timestamp": time.time(),
                                    }
                                )
                            )
                        except Exception:
                            pass

                except Exception as e:
                    logger.warning(f"[HEARTBEAT] Fehler: {e}")

                await asyncio.sleep(self.HEARTBEAT_INTERVAL_SECONDS)

        finally:
            if session:
                await session.close()

        logger.info("[HEARTBEAT] Loop beendet")

    async def message_handler(self):
        logger.info("[MESSAGE] Handler gestartet")
        while self.should_run and self.websocket and self.is_connected:
            try:
                message = await asyncio.wait_for(self.websocket.recv(), timeout=30)
                data = json.loads(message)
                msg_type = data.get("type")
                if (
                    msg_type in ["start_capture", "start_dual_screen_capture"]
                    and not self.is_capturing
                ):
                    logger.info("[CMD] START empfangen")
                    self.is_capturing = True
                elif (
                    msg_type in ["stop_capture", "stop_dual_screen_capture"]
                    and self.is_capturing
                ):
                    logger.info("[CMD] STOP empfangen")
                    self.is_capturing = False
                elif msg_type == "commands":
                    for cmd in data.get("commands", []):
                        await self._process_command(cmd)
                elif msg_type == "ping":
                    await self.websocket.send(
                        json.dumps({"type": "pong", "timestamp": time.time()})
                    )
                elif msg_type == "execute_action":
                    # Remote action from ActionRouter (Brain-in-Docker mode)
                    asyncio.create_task(self._execute_remote_action(data))
                elif msg_type == "shutdown":
                    logger.info("[CMD] SHUTDOWN empfangen von Server")
                    self.should_run = False
                    self.is_capturing = False
            except asyncio.TimeoutError:
                continue
            except websockets.exceptions.ConnectionClosed:
                self.is_connected = False
                break
            except json.JSONDecodeError:
                continue
            except Exception:
                if not self.is_connected:
                    break
        logger.info("[MESSAGE] Handler beendet")

    async def _process_command(self, cmd: Dict[str, Any]):
        cmd_id = (
            cmd.get("id")
            or cmd.get("command_id")
            or f"{cmd.get('command_type')}_{time.time()}"
        )
        if cmd_id in self._processed_command_ids:
            self.stats["commands_deduplicated"] += 1
            return
        self._processed_command_ids.add(cmd_id)
        if len(self._processed_command_ids) > 1000:
            self._processed_command_ids = set(list(self._processed_command_ids)[-500:])
        cmd_type = cmd.get("command_type")
        if cmd_type == "start_capture" and not self.is_capturing:
            logger.info(f"[CMD] start_capture")
            self.is_capturing = True
            self.stats["commands_processed"] += 1
        elif cmd_type == "stop_capture" and self.is_capturing:
            logger.info(f"[CMD] stop_capture")
            self.is_capturing = False
            self.stats["commands_processed"] += 1
        await self._acknowledge_command(cmd_id, cmd_type)

    async def _acknowledge_command(self, cmd_id: str, cmd_type: str):
        try:
            if self.websocket and self.is_connected:
                await self.websocket.send(
                    json.dumps(
                        {
                            "type": "command_ack",
                            "commandId": cmd_id,
                            "commandType": cmd_type,
                            "status": "processed",
                            "clientId": self.client_id,
                            "timestamp": time.time(),
                        }
                    )
                )
        except Exception:
            pass

    async def _execute_remote_action(self, data: Dict[str, Any]):
        """Execute a remote action from ActionRouter and send ACK back.

        Receives: {type: "execute_action", commandId, tool, arguments}
        Sends:    {type: "action_ack", commandId, success, result, executionTimeMs}
        """
        command_id = data.get("commandId", "")
        tool = data.get("tool", "")
        args = data.get("arguments", {})
        start_ts = time.time()

        logger.info(f"[ACTION] Executing remote action: {tool} (cmd={command_id})")

        result = {"success": False, "error": "Unknown tool"}
        try:
            if tool == "action_click":
                x, y = int(args.get("x", 0)), int(args.get("y", 0))
                button = args.get("button", "left")
                pyautogui.moveTo(x, y, duration=0.3)
                pyautogui.click(button=button)
                result = {"success": True, "action": "click", "x": x, "y": y, "button": button}

            elif tool == "action_type":
                text = args.get("text", "")
                try:
                    import pyperclip
                    pyperclip.copy(text)
                    pyautogui.hotkey("ctrl", "v")
                except ImportError:
                    pyautogui.write(text, interval=0.02)
                result = {"success": True, "action": "type", "text_length": len(text)}

            elif tool == "action_press":
                key = args.get("key", "enter")
                pyautogui.press(key)
                result = {"success": True, "action": "press", "key": key}

            elif tool == "action_hotkey":
                keys_str = args.get("keys", "")
                keys = [k.strip() for k in keys_str.split("+") if k.strip()]
                if keys:
                    pyautogui.hotkey(*keys)
                    result = {"success": True, "action": "hotkey", "keys": keys}
                else:
                    result = {"success": False, "error": "No keys provided"}

            elif tool == "action_scroll":
                direction = args.get("direction", "down")
                amount = int(args.get("amount", 3))
                x = args.get("x")
                y = args.get("y")
                clicks = amount if direction == "up" else -amount
                if x is not None and y is not None:
                    pyautogui.scroll(clicks, int(x), int(y))
                else:
                    pyautogui.scroll(clicks)
                result = {"success": True, "action": "scroll", "direction": direction, "amount": amount}

            elif tool == "get_focus":
                try:
                    import win32gui
                    hwnd = win32gui.GetForegroundWindow()
                    title = win32gui.GetWindowText(hwnd)
                    result = {"success": True, "title": title, "hwnd": hwnd}
                except ImportError:
                    result = {"success": False, "error": "win32gui not available"}

            elif tool == "set_focus":
                title_query = args.get("title", "")
                try:
                    import win32gui
                    found = []
                    def _enum_cb(hwnd, results):
                        if win32gui.IsWindowVisible(hwnd):
                            t = win32gui.GetWindowText(hwnd)
                            if title_query.lower() in t.lower():
                                results.append(hwnd)
                        return True
                    win32gui.EnumWindows(_enum_cb, found)
                    if found:
                        hwnd = found[0]
                        win32gui.ShowWindow(hwnd, 9)  # SW_RESTORE
                        win32gui.SetForegroundWindow(hwnd)
                        actual_title = win32gui.GetWindowText(hwnd)
                        result = {"success": True, "is_focused": True, "recovered": True, "hwnd": hwnd, "title": actual_title}
                    else:
                        result = {"success": False, "error": f"Window '{title_query}' not found"}
                except ImportError:
                    result = {"success": False, "error": "win32gui not available"}

            elif tool == "list_windows":
                try:
                    import win32gui
                    windows = []
                    def _enum_cb2(hwnd, results):
                        if win32gui.IsWindowVisible(hwnd):
                            t = win32gui.GetWindowText(hwnd)
                            if t.strip():
                                results.append({"hwnd": hwnd, "title": t})
                        return True
                    win32gui.EnumWindows(_enum_cb2, windows)
                    result = {"success": True, "windows": windows, "count": len(windows)}
                except ImportError:
                    result = {"success": False, "error": "win32gui not available"}

            elif tool == "mouse_move":
                x, y = int(args.get("x", 0)), int(args.get("y", 0))
                duration = min(float(args.get("duration", 0.5)), 2.0)
                pyautogui.moveTo(x, y, duration=duration)
                result = {"success": True, "x": x, "y": y, "duration": duration}

            elif tool == "shell_exec":
                import subprocess
                cmd = args.get("command", "")
                timeout = int(args.get("timeout", 30))
                proc = subprocess.Popen(
                    ["powershell", "-Command", cmd],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                    creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
                )
                try:
                    stdout, stderr = proc.communicate(timeout=min(timeout, 10))
                    result = {
                        "success": proc.returncode == 0,
                        "stdout": stdout[:2000] if stdout else "",
                        "stderr": stderr[:500] if stderr else "",
                        "exit_code": proc.returncode,
                    }
                except subprocess.TimeoutExpired:
                    # Process still running (GUI app) — that's OK
                    result = {
                        "success": True,
                        "pid": proc.pid,
                        "message": f"Process launched (PID {proc.pid}), still running",
                    }

            else:
                result = {"success": False, "error": f"Unsupported tool: {tool}"}

        except Exception as e:
            logger.error(f"[ACTION] Execution failed: {tool} -> {e}")
            result = {"success": False, "error": str(e)}

        elapsed_ms = int((time.time() - start_ts) * 1000)

        # Send ACK back to backend
        try:
            if self.websocket and self.is_connected:
                ack = {
                    "type": "action_ack",
                    "commandId": command_id,
                    "success": result.get("success", False),
                    "result": result,
                    "executionTimeMs": elapsed_ms,
                    "clientId": self.client_id,
                    "timestamp": time.time(),
                }
                await self.websocket.send(json.dumps(ack))
                logger.info(f"[ACTION] ACK sent: {tool} success={result.get('success')} ({elapsed_ms}ms)")
        except Exception as e:
            logger.error(f"[ACTION] Failed to send ACK: {e}")

    async def ping_loop(self):
        logger.info("[PING] Loop gestartet (5s)")
        while self.should_run and self.is_connected:
            try:
                if self.websocket and self.is_connected:
                    await self.websocket.send(
                        json.dumps(
                            {
                                "type": "ping",
                                "clientId": self.client_id,
                                "timestamp": time.time(),
                            }
                        )
                    )
                await asyncio.sleep(5)
            except Exception:
                if not self.is_connected:
                    break
        logger.info("[PING] Loop beendet")

    async def poll_commands(self):
        logger.info("[POLL] Loop gestartet (3s)")
        while self.should_run and self.is_connected:
            try:
                if self.websocket and self.is_connected:
                    await self.websocket.send(
                        json.dumps(
                            {
                                "type": "get_commands",
                                "clientId": self.client_id,
                                "timestamp": time.time(),
                            }
                        )
                    )
                await asyncio.sleep(3)
            except Exception:
                if not self.is_connected:
                    break
        logger.info("[POLL] Loop beendet")

    async def run_session(self):
        self._processed_command_ids.clear()
        if not await self.connect():
            return False
        self.is_capturing = True
        logger.info("[AUTO-START] Capture gestartet")

        # Erstelle alle Tasks inkl. Heartbeat
        tasks = [
            asyncio.create_task(self.capture_loop(), name="capture"),
            asyncio.create_task(self.message_handler(), name="message"),
            asyncio.create_task(self.ping_loop(), name="ping"),
            asyncio.create_task(self.poll_commands(), name="poll"),
            asyncio.create_task(self.heartbeat_loop(), name="heartbeat"),
        ]
        self._tasks = tasks

        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        logger.info("[SESSION] Ein Task beendet, stoppe andere...")
        self.is_capturing = False
        for task in pending:
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=2)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        if self.websocket:
            try:
                await self.websocket.close()
            except Exception:
                pass
        self.is_connected = False
        self.websocket = None
        return True

    async def run(self):
        logger.info("=" * 60)
        logger.info(f"  TRAE Desktop Capture Client - v{self.VERSION}")
        logger.info(f"  Server: {self.server_url[:50]}...")
        logger.info(f"  Client-ID: {self.client_id}")
        logger.info(f"  Monitore: {len(self.monitors)}")
        logger.info(f"  Backend-API: {self.BACKEND_API_URL}")
        logger.info("=" * 60)

        while self.should_run:
            try:
                session_ok = await self.run_session()

                if not self.should_run:
                    logger.info("[SHUTDOWN] Graceful shutdown angefordert")
                    break

                if session_ok:
                    self.stats["reconnects"] += 1
                    logger.info(f"[RECONNECT] #{self.stats['reconnects']} in 2s...")
                else:
                    logger.warning("[WARN] Retry in 5s...")
            except Exception as e:
                logger.error(f"[ERROR] {type(e).__name__}: {e}")

            if self.should_run:
                await asyncio.sleep(2 if self.stats["reconnects"] > 0 else 5)

        logger.info("[STOP] Client beendet - Cleanup...")
        self._cleanup()
        logger.info("[STOP] Cleanup abgeschlossen")

    def _cleanup(self):
        """Bereinigt Ressourcen beim Beenden."""
        try:
            # Schließe mss
            if self._mss:
                self._mss.close()
        except Exception as e:
            logger.warning(f"[CLEANUP] mss close Fehler: {e}")

    def stop(self):
        """Öffentliche Methode zum Stoppen des Clients."""
        logger.info("[STOP] Stop angefordert")
        self.should_run = False
        self.is_capturing = False
        for task in self._tasks:
            task.cancel()


def main():
    print("=" * 60, flush=True)
    print("  TRAE Desktop Capture Client - v2.3-heartbeat", flush=True)
    print("  Mit Heartbeat + Graceful Shutdown + Auto-Reconnect", flush=True)
    print("=" * 60, flush=True)
    parser = argparse.ArgumentParser(description="Robust Dual Screen Capture Client")
    parser.add_argument(
        "--server-url",
        default=os.getenv("SUPABASE_WS_URL", "ws://localhost:8007/ws/live-desktop"),
        help="WebSocket Server URL (default: local backend, set SUPABASE_WS_URL for cloud relay)",
    )
    parser.add_argument("--client-id", help="Client-ID (optional)")
    parser.add_argument("--fps", type=int, default=10, help="FPS")
    parser.add_argument("--quality", type=int, default=75, help="Qualitaet")
    parser.add_argument("--scale", type=float, default=0.8, help="Skalierung")
    parser.add_argument(
        "--backend-url",
        default="http://localhost:8007/api/client",
        help="Backend API URL für Heartbeats",
    )
    parser.add_argument("--debug", action="store_true", help="Debug-Modus")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    client = RobustDualScreenCaptureClient(
        server_url=args.server_url, client_id=args.client_id
    )
    client.capture_config.update(
        {"fps": args.fps, "quality": args.quality, "scale": args.scale}
    )
    client.BACKEND_API_URL = args.backend_url

    try:
        asyncio.run(client.run())
    except KeyboardInterrupt:
        print("\n[STOP] Gestoppt (Ctrl+C)", flush=True)
        client.stop()


if __name__ == "__main__":
    main()
