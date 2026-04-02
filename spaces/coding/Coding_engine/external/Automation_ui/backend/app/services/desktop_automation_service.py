"""
Real Desktop Automation Service for TRAE Backend

Implements the complete desktop automation workflow:
- Opens new desktop sessions
- Executes PowerShell commands  
- Opens programs
- Tracks and executes mouse clicks on real monitor
- Provides OCR periodic processing
"""

import asyncio
import json
import os
import queue
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# Lazy import pyautogui to avoid X11 issues during module loading
pyautogui = None


def _ensure_pyautogui():
    global pyautogui
    if pyautogui is None:
        try:
            import pyautogui as _pyautogui

            pyautogui = _pyautogui
        except Exception as e:
            import logging

            logging.warning(f"Failed to import pyautogui: {e}")
            pyautogui = None
    return pyautogui


import cv2
import numpy as np
import psutil
import pytesseract
from fastapi import WebSocket, WebSocketDisconnect
from PIL import Image, ImageGrab

from ..logger_config import LoggerMixin


class DesktopAutomationService(LoggerMixin):
    """Service for complete desktop automation workflow"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize desktop automation service"""
        super().__init__()
        self.config = config or {}

        # Configuration
        self.ocr_interval = self.config.get("ocr_interval", 30)  # seconds
        self.max_sessions = self.config.get("max_sessions", 3)
        self.session_timeout = self.config.get("session_timeout", 3600)  # 1 hour
        self.click_tracking_enabled = self.config.get("click_tracking", True)

        # State tracking
        self.active_sessions = {}  # session_id -> session_data
        self.ocr_enabled = False
        self.ocr_results = []
        self.click_sequences = {}  # session_id -> click_sequence
        self.websocket_clients = set()

        # OCR periodic processing
        self.ocr_task = None
        self.ocr_stop_event = threading.Event()

        self.log_info("DesktopAutomationService initialized")

    async def initialize(self):
        """Initialize the service"""
        try:
            # Test OCR capability
            try:
                test_image = ImageGrab.grab(bbox=(0, 0, 100, 100))
                test_text = pytesseract.image_to_string(test_image)
                self.log_info("OCR capability verified")
            except Exception as e:
                self.log_warning(f"OCR may not be available: {e}")

            # Test PowerShell capability
            try:
                result = subprocess.run(
                    ["powershell", "-Command", "Get-Process | Select-Object -First 1"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    self.log_info("PowerShell capability verified")
                else:
                    self.log_warning("PowerShell may not be available")
            except Exception as e:
                self.log_warning(f"PowerShell may not be available: {e}")

            self.log_info("Desktop automation service initialized successfully")
            return True
        except Exception as e:
            self.log_error(f"Failed to initialize desktop automation service: {e}")
            return False

    async def cleanup(self):
        """Cleanup the service"""
        # Stop OCR processing
        await self.stop_ocr_processing()

        # Cleanup active sessions
        for session_id in list(self.active_sessions.keys()):
            await self.close_desktop_session(session_id)

        self.log_info("Desktop automation service cleaned up")

    async def get_status(self) -> Dict[str, Any]:
        """Get desktop automation service status"""
        try:
            return {
                "service_healthy": True,
                "active_sessions": len(self.active_sessions),
                "max_sessions": self.max_sessions,
                "ocr_enabled": self.ocr_enabled,
                "ocr_interval": self.ocr_interval,
                "click_tracking_enabled": self.click_tracking_enabled,
                "recent_ocr_results": len(self.ocr_results),
                "websocket_clients": len(self.websocket_clients),
                "available_features": {
                    "powershell": await self._test_powershell(),
                    "ocr": await self._test_ocr(),
                    "desktop_access": await self._test_desktop_access(),
                },
            }
        except Exception as e:
            self.log_error(f"Error getting desktop automation status: {e}")
            return {"service_healthy": False, "error": str(e)}

    async def create_desktop_session(
        self, session_config: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Create a new desktop automation session"""
        try:
            if len(self.active_sessions) >= self.max_sessions:
                raise ValueError(f"Maximum sessions ({self.max_sessions}) reached")

            session_config = session_config or {}
            session_id = f"session_{int(time.time() * 1000)}"

            # Create session data
            session_data = {
                "id": session_id,
                "created_at": datetime.now(),
                "last_activity": datetime.now(),
                "config": session_config,
                "status": "active",
                "processes": [],
                "click_sequence": [],
                "ocr_regions": session_config.get("ocr_regions", []),
                "powershell_history": [],
                "programs_opened": [],
            }

            self.active_sessions[session_id] = session_data
            self.click_sequences[session_id] = []

            self.log_info(f"Created desktop session: {session_id}")

            return {
                "session_id": session_id,
                "status": "created",
                "capabilities": {
                    "powershell": True,
                    "program_launching": True,
                    "click_tracking": self.click_tracking_enabled,
                    "ocr_processing": True,
                },
            }

        except Exception as e:
            self.log_error(f"Error creating desktop session: {e}")
            raise

    async def execute_powershell_command(
        self, session_id: str, command: str
    ) -> Dict[str, Any]:
        """Execute PowerShell command in session context"""
        try:
            if session_id not in self.active_sessions:
                raise ValueError(f"Session {session_id} not found")

            session = self.active_sessions[session_id]
            session["last_activity"] = datetime.now()

            self.log_info(
                f"Executing PowerShell command in {session_id}: {command[:100]}..."
            )

            # Execute PowerShell command
            start_time = time.time()
            result = subprocess.run(
                ["powershell", "-Command", command],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=tempfile.gettempdir(),
            )
            execution_time = time.time() - start_time

            # Store in session history
            command_result = {
                "command": command,
                "timestamp": datetime.now().isoformat(),
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "execution_time": execution_time,
            }

            session["powershell_history"].append(command_result)

            # Limit history to last 50 commands
            if len(session["powershell_history"]) > 50:
                session["powershell_history"] = session["powershell_history"][-50:]

            self.log_info(
                f"PowerShell command completed in {execution_time:.2f}s with exit code {result.returncode}"
            )

            return {
                "success": result.returncode == 0,
                "exit_code": result.returncode,
                "output": result.stdout,
                "error": result.stderr,
                "execution_time": execution_time,
                "timestamp": command_result["timestamp"],
            }

        except subprocess.TimeoutExpired:
            self.log_warning(f"PowerShell command timed out in session {session_id}")
            return {
                "success": False,
                "error": "Command execution timed out (30s limit)",
                "exit_code": -1,
            }
        except Exception as e:
            self.log_error(f"Error executing PowerShell command: {e}")
            raise

    async def open_program(
        self, session_id: str, program_path: str, arguments: str = ""
    ) -> Dict[str, Any]:
        """Open a program through PowerShell in session context"""
        try:
            if session_id not in self.active_sessions:
                raise ValueError(f"Session {session_id} not found")

            session = self.active_sessions[session_id]
            session["last_activity"] = datetime.now()

            # Construct PowerShell command to open program
            if arguments:
                powershell_command = f'Start-Process -FilePath "{program_path}" -ArgumentList "{arguments}"'
            else:
                powershell_command = f'Start-Process -FilePath "{program_path}"'

            self.log_info(
                f"Opening program in {session_id}: {program_path} {arguments}"
            )

            # Execute command
            result = await self.execute_powershell_command(
                session_id, powershell_command
            )

            if result["success"]:
                # Track opened program
                program_info = {
                    "program_path": program_path,
                    "arguments": arguments,
                    "opened_at": datetime.now().isoformat(),
                    "status": "opened",
                }
                session["programs_opened"].append(program_info)

                self.log_info(f"Successfully opened program: {program_path}")

                return {
                    "success": True,
                    "program_path": program_path,
                    "arguments": arguments,
                    "message": "Program opened successfully",
                    "powershell_result": result,
                }
            else:
                self.log_warning(f"Failed to open program: {program_path}")
                return {
                    "success": False,
                    "error": f"Failed to open program: {result['error']}",
                    "powershell_result": result,
                }

        except Exception as e:
            self.log_error(f"Error opening program: {e}")
            raise

    async def track_mouse_click(
        self, session_id: str, click_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Track and execute mouse click on real monitor"""
        try:
            if session_id not in self.active_sessions:
                raise ValueError(f"Session {session_id} not found")

            session = self.active_sessions[session_id]
            session["last_activity"] = datetime.now()

            # Extract click information
            x = click_data.get("x", 0)
            y = click_data.get("y", 0)
            button = click_data.get("button", "left")
            clicks = click_data.get("clicks", 1)
            interval = click_data.get("interval", 0.0)

            self.log_info(
                f"Tracking mouse click in {session_id}: ({x}, {y}) {button} x{clicks}"
            )

            # Store click in sequence
            click_info = {
                "x": x,
                "y": y,
                "button": button,
                "clicks": clicks,
                "interval": interval,
                "timestamp": datetime.now().isoformat(),
                "executed": False,
            }

            self.click_sequences[session_id].append(click_info)
            session["click_sequence"].append(click_info)

            # Execute click on real monitor if enabled
            if self.click_tracking_enabled:
                try:
                    pg = _ensure_pyautogui()
                    if pg is not None:
                        # Configure pyautogui settings when actually using it
                        pg.FAILSAFE = False
                        pg.PAUSE = 0.01

                        # Ensure coordinates are within screen bounds
                        screen_width, screen_height = pg.size()
                        x = max(0, min(x, screen_width - 1))
                        y = max(0, min(y, screen_height - 1))

                        # Execute the click
                        pg.click(
                            x=x, y=y, clicks=clicks, interval=interval, button=button
                        )
                    else:
                        raise Exception("pyautogui not available")

                    click_info["executed"] = True
                    click_info["executed_at"] = datetime.now().isoformat()

                    self.log_info(f"Executed mouse click at ({x}, {y})")

                    # Notify WebSocket clients
                    await self._notify_websocket_clients(
                        {
                            "type": "click_executed",
                            "session_id": session_id,
                            "click_data": click_info,
                        }
                    )

                except Exception as e:
                    self.log_error(f"Error executing mouse click: {e}")
                    click_info["error"] = str(e)

            return {
                "success": True,
                "click_tracked": True,
                "click_executed": click_info["executed"],
                "click_data": click_info,
            }

        except Exception as e:
            self.log_error(f"Error tracking mouse click: {e}")
            raise

    async def start_ocr_processing(self, interval: int = None) -> Dict[str, Any]:
        """Start periodic OCR processing"""
        try:
            if interval:
                self.ocr_interval = interval

            if self.ocr_enabled:
                return {"success": False, "message": "OCR processing already running"}

            self.ocr_enabled = True
            self.ocr_stop_event.clear()

            # Start OCR task
            self.ocr_task = asyncio.create_task(self._ocr_processing_loop())

            self.log_info(f"Started OCR processing with {self.ocr_interval}s interval")

            return {"success": True, "ocr_enabled": True, "interval": self.ocr_interval}

        except Exception as e:
            self.log_error(f"Error starting OCR processing: {e}")
            raise

    async def stop_ocr_processing(self) -> Dict[str, Any]:
        """Stop periodic OCR processing"""
        try:
            if not self.ocr_enabled:
                return {"success": False, "message": "OCR processing not running"}

            self.ocr_enabled = False
            self.ocr_stop_event.set()

            if self.ocr_task:
                self.ocr_task.cancel()
                try:
                    await self.ocr_task
                except asyncio.CancelledError:
                    pass

            self.log_info("Stopped OCR processing")

            return {"success": True, "ocr_enabled": False}

        except Exception as e:
            self.log_error(f"Error stopping OCR processing: {e}")
            raise

    async def _ocr_processing_loop(self):
        """Main OCR processing loop"""
        try:
            while self.ocr_enabled and not self.ocr_stop_event.is_set():
                try:
                    # Take screenshot
                    screenshot = ImageGrab.grab()

                    # Perform OCR
                    ocr_text = pytesseract.image_to_string(screenshot)

                    if ocr_text.strip():
                        ocr_result = {
                            "timestamp": datetime.now().isoformat(),
                            "text": ocr_text.strip(),
                            "confidence": "unknown",  # pytesseract doesn't provide confidence easily
                            "source": "full_screen",
                        }

                        self.ocr_results.append(ocr_result)

                        # Limit OCR results to last 100
                        if len(self.ocr_results) > 100:
                            self.ocr_results = self.ocr_results[-100:]

                        # Notify WebSocket clients
                        await self._notify_websocket_clients(
                            {"type": "ocr_result", "data": ocr_result}
                        )

                        self.log_debug(
                            f"OCR detected {len(ocr_text.strip())} characters"
                        )

                except Exception as e:
                    self.log_error(f"Error in OCR processing: {e}")

                # Wait for next interval
                await asyncio.sleep(self.ocr_interval)

        except asyncio.CancelledError:
            self.log_info("OCR processing loop cancelled")
        except Exception as e:
            self.log_error(f"OCR processing loop error: {e}")
        finally:
            self.ocr_enabled = False

    async def close_desktop_session(self, session_id: str) -> Dict[str, Any]:
        """Close desktop automation session"""
        try:
            if session_id not in self.active_sessions:
                raise ValueError(f"Session {session_id} not found")

            session = self.active_sessions[session_id]

            # Cleanup session resources
            if session_id in self.click_sequences:
                del self.click_sequences[session_id]

            # Mark session as closed
            session["status"] = "closed"
            session["closed_at"] = datetime.now().isoformat()

            del self.active_sessions[session_id]

            self.log_info(f"Closed desktop session: {session_id}")

            return {"success": True, "session_id": session_id, "status": "closed"}

        except Exception as e:
            self.log_error(f"Error closing desktop session: {e}")
            raise

    async def get_session_info(self, session_id: str) -> Dict[str, Any]:
        """Get information about a specific session"""
        try:
            if session_id not in self.active_sessions:
                raise ValueError(f"Session {session_id} not found")

            session = self.active_sessions[session_id]

            return {
                "session_id": session_id,
                "created_at": session["created_at"].isoformat(),
                "last_activity": session["last_activity"].isoformat(),
                "status": session["status"],
                "click_count": len(session["click_sequence"]),
                "powershell_commands": len(session["powershell_history"]),
                "programs_opened": len(session["programs_opened"]),
                "ocr_regions": len(session["ocr_regions"]),
            }

        except Exception as e:
            self.log_error(f"Error getting session info: {e}")
            raise

    async def get_ocr_results(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent OCR results"""
        return self.ocr_results[-limit:] if self.ocr_results else []

    async def handle_websocket(self, websocket: WebSocket):
        """Handle WebSocket connection for desktop automation"""
        client_host = websocket.client.host if websocket.client else "unknown"
        self.log_info(
            f"🤖 [DesktopAutomation] Handling WebSocket connection from {client_host}"
        )

        try:
            # Add to clients
            self.websocket_clients.add(websocket)

            # Send welcome message
            welcome_msg = {
                "type": "desktop_automation_welcome",
                "message": "Desktop automation WebSocket connected",
                "capabilities": {
                    "session_management": True,
                    "powershell_execution": True,
                    "program_launching": True,
                    "click_tracking": self.click_tracking_enabled,
                    "ocr_processing": True,
                },
                "timestamp": datetime.now().isoformat(),
            }
            await websocket.send_text(json.dumps(welcome_msg))

            # Handle messages
            while True:
                try:
                    message = await websocket.receive_text()
                    await self._handle_websocket_message(
                        websocket, message, client_host
                    )
                except WebSocketDisconnect:
                    self.log_info(
                        f"🔌 [DesktopAutomation] Client {client_host} disconnected"
                    )
                    break
                except Exception as e:
                    self.log_error(
                        f"💥 [DesktopAutomation] Message handling error for {client_host}: {e}"
                    )
                    break

        except Exception as e:
            self.log_error(
                f"💥 [DesktopAutomation] WebSocket error for {client_host}: {e}"
            )
        finally:
            # Remove from clients
            self.websocket_clients.discard(websocket)
            self.log_info(
                f"🔌 [DesktopAutomation] WebSocket connection closed for {client_host}"
            )

    async def _handle_websocket_message(
        self, websocket: WebSocket, message: str, client_host: str
    ):
        """Handle incoming WebSocket messages"""
        try:
            data = json.loads(message)
            message_type = data.get("type", "unknown")

            self.log_debug(
                f"📨 [DesktopAutomation] Received {message_type} from {client_host}"
            )

            response = None

            if message_type == "create_session":
                session_config = data.get("config", {})
                result = await self.create_desktop_session(session_config)
                response = {
                    "type": "session_created",
                    "data": result,
                    "timestamp": datetime.now().isoformat(),
                }

            elif message_type == "execute_powershell":
                session_id = data.get("session_id")
                command = data.get("command")
                result = await self.execute_powershell_command(session_id, command)
                response = {
                    "type": "powershell_result",
                    "session_id": session_id,
                    "data": result,
                    "timestamp": datetime.now().isoformat(),
                }

            elif message_type == "open_program":
                session_id = data.get("session_id")
                program_path = data.get("program_path")
                arguments = data.get("arguments", "")
                result = await self.open_program(session_id, program_path, arguments)
                response = {
                    "type": "program_opened",
                    "session_id": session_id,
                    "data": result,
                    "timestamp": datetime.now().isoformat(),
                }

            elif message_type == "track_click":
                session_id = data.get("session_id")
                click_data = data.get("click_data", {})
                result = await self.track_mouse_click(session_id, click_data)
                response = {
                    "type": "click_tracked",
                    "session_id": session_id,
                    "data": result,
                    "timestamp": datetime.now().isoformat(),
                }

            elif message_type == "start_ocr":
                interval = data.get("interval", self.ocr_interval)
                result = await self.start_ocr_processing(interval)
                response = {
                    "type": "ocr_started",
                    "data": result,
                    "timestamp": datetime.now().isoformat(),
                }

            elif message_type == "stop_ocr":
                result = await self.stop_ocr_processing()
                response = {
                    "type": "ocr_stopped",
                    "data": result,
                    "timestamp": datetime.now().isoformat(),
                }

            elif message_type == "get_ocr_results":
                limit = data.get("limit", 50)
                results = await self.get_ocr_results(limit)
                response = {
                    "type": "ocr_results",
                    "data": results,
                    "timestamp": datetime.now().isoformat(),
                }

            elif message_type == "get_status":
                status = await self.get_status()
                response = {
                    "type": "status_response",
                    "data": status,
                    "timestamp": datetime.now().isoformat(),
                }

            elif message_type == "close_session":
                session_id = data.get("session_id")
                result = await self.close_desktop_session(session_id)
                response = {
                    "type": "session_closed",
                    "session_id": session_id,
                    "data": result,
                    "timestamp": datetime.now().isoformat(),
                }

            if response:
                await websocket.send_text(json.dumps(response))

        except json.JSONDecodeError:
            self.log_warning(
                f"⚠️  [DesktopAutomation] Invalid JSON from {client_host}: {message}"
            )
        except Exception as e:
            self.log_error(
                f"💥 [DesktopAutomation] Error handling message from {client_host}: {e}"
            )
            error_response = {
                "type": "error",
                "message": str(e),
                "timestamp": datetime.now().isoformat(),
            }
            await websocket.send_text(json.dumps(error_response))

    async def _notify_websocket_clients(self, message: Dict[str, Any]):
        """Notify all connected WebSocket clients"""
        if not self.websocket_clients:
            return

        message_text = json.dumps(message)
        disconnected_clients = set()

        for client in self.websocket_clients:
            try:
                await client.send_text(message_text)
            except Exception:
                disconnected_clients.add(client)

        # Remove disconnected clients
        for client in disconnected_clients:
            self.websocket_clients.discard(client)

    async def _test_powershell(self) -> bool:
        """Test if PowerShell is available"""
        try:
            result = subprocess.run(
                ["powershell", "-Command", 'echo "test"'],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except:
            return False

    async def _test_ocr(self) -> bool:
        """Test if OCR is available"""
        try:
            test_image = ImageGrab.grab(bbox=(0, 0, 100, 100))
            pytesseract.image_to_string(test_image)
            return True
        except:
            return False

    async def _test_desktop_access(self) -> bool:
        """Test if desktop access is available"""
        try:
            pg = _ensure_pyautogui()
            if pg is not None:
                pg.size()
            ImageGrab.grab(bbox=(0, 0, 100, 100))
            return True
        except:
            return False


# Global instance
_desktop_automation_service: Optional[DesktopAutomationService] = None


def get_desktop_automation_service() -> DesktopAutomationService:
    """Get or create desktop automation service instance"""
    global _desktop_automation_service
    if _desktop_automation_service is None:
        _desktop_automation_service = DesktopAutomationService()
    return _desktop_automation_service
