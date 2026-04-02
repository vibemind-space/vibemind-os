"""
Minimalistic Desktop Capture Application

- Single-button UI (Start Stream)
- Silent background connection and auto-handshake with local WS server
- Efficient screen capture using mss + Pillow (JPEG encoding)
- Compatible with server message protocol (handshake, start_capture, stop_capture, frame_data)

Dependencies (install before running):
    pip install mss pillow websocket-client

Run:
    python minimal_desktop_capture.py

Notes:
- Uses environment variables WS_HOST, WS_PORT, WS_PATH to override defaults
- Defaults to ws://127.0.0.1:8084/ws/live-desktop
- Sends 'frame_data' messages with base64 JPEG payloads
- Responds to 'start_capture'/'stop_capture' commands; server may auto-start capture on handshake

This file intentionally focuses ONLY on desktop capture functionality per scope constraints.
"""

import base64
import json
import os
import socket
import threading
import time
# GUI (single-button)
import tkinter as tk
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Dict, Optional

# Efficient screen capture
from mss import mss
from PIL import Image
# WebSocket client (callback-based, lightweight)
from websocket import WebSocketApp


class MinimalDesktopCaptureClient:
    """Minimal desktop capture client with one-button UI and automated streaming."""

    def __init__(self) -> None:
        # Resolve WS endpoint
        host = os.environ.get("WS_HOST", "127.0.0.1")
        port = int(os.environ.get("WS_PORT", "8084"))
        path = os.environ.get("WS_PATH", "/ws/live-desktop")
        self.ws_url = f"ws://{host}:{port}{path}"

        # Identity and capabilities
        self.client_id = f"desktop_{socket.gethostname()}_{int(time.time())}"
        self.desktop_id = socket.gethostname()
        self.screen_id = "monitor_0"  # single-monitor identifier used in server/FE
        self.capabilities = {
            "format": "jpeg",
            "scaling": True,
            "multi_monitor": False,
            "max_fps": 30,
        }

        # Runtime state
        self.ws: Optional[WebSocketApp] = None
        self.ws_thread: Optional[threading.Thread] = None
        self.capture_thread: Optional[threading.Thread] = None
        self.capture_stop_event = threading.Event()
        self.streaming_active = False
        self.current_config: Dict[str, Any] = {
            "fps": 12,
            "quality": 80,
            "scale": 1.0,
            "format": "jpeg",
        }

        # GUI
        self.root = tk.Tk()
        self.root.title("Minimal Desktop Capture")
        self.root.geometry("320x120")
        self.root.resizable(False, False)

        self.start_button = tk.Button(
            self.root,
            text="Start Stream",
            font=("Segoe UI", 14),
            width=18,
            height=2,
            command=self.on_start_clicked,
        )
        self.start_button.pack(expand=True)

        # Ensure graceful shutdown on window close
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ------------------------------- UI Actions -------------------------------
    def on_start_clicked(self) -> None:
        """Start background connection and let server auto-start capture."""
        # Disable button to keep UI minimal and avoid duplicate starts
        self.start_button.configure(text="Connecting...", state=tk.DISABLED)

        # Launch WS connection in background to keep UI responsive
        self.ws_thread = threading.Thread(
            target=self._connect_ws, name="ws-thread", daemon=True
        )
        self.ws_thread.start()

    def on_close(self) -> None:
        """Cleanup threads and close WS before exiting UI."""
        try:
            self._stop_capture()
        except Exception:
            pass
        try:
            if self.ws is not None:
                self.ws.close()
        except Exception:
            pass
        # Small delay to allow threads to unwind
        self.root.after(100, self.root.destroy)

    # ---------------------------- WebSocket Handling ---------------------------
    def _connect_ws(self) -> None:
        """Establish WebSocket connection and register callbacks."""

        def on_open(ws: WebSocketApp) -> None:
            # Send handshake immediately on open
            handshake = {
                "type": "handshake",
                "clientInfo": {
                    "clientType": "desktop_capture",
                    "clientId": self.client_id,
                    "desktopId": self.desktop_id,
                    "screenId": self.screen_id,
                    "capabilities": self.capabilities,
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self._safe_send_json(handshake)

        def on_message(ws: WebSocketApp, message: str) -> None:
            try:
                data = json.loads(message)
            except Exception:
                return

            msg_type = data.get("type")

            if msg_type == "handshake_ack":
                # Connection is ready; server may auto-send start_capture
                # Keep UI silent per requirements
                pass

            elif msg_type == "start_capture":
                # Merge provided config with defaults and start streaming
                config = data.get("config") or {}
                self.current_config.update(
                    {
                        k: config.get(k, self.current_config.get(k))
                        for k in ("fps", "quality", "scale", "format")
                    }
                )
                self._start_capture()

            elif msg_type in ("stop_capture", "stop_desktop_stream"):
                self._stop_capture()

            elif msg_type == "ping":
                # Optional: reply with a lightweight pong to keep-alive
                self._safe_send_json(
                    {
                        "type": "pong",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "clientId": self.client_id,
                    }
                )

            # Other message types can be safely ignored by this minimal client

        def on_error(ws: WebSocketApp, error: Exception) -> None:
            # Keep silent UI; log to console for debugging
            print(f"[WS][ERROR] {error}")

        def on_close(
            ws: WebSocketApp, status_code: Optional[int], msg: Optional[str]
        ) -> None:
            print(f"[WS] Closed: code={status_code}, msg={msg}")
            # Reset UI to allow retry
            self.root.after(
                0,
                lambda: self.start_button.configure(
                    text="Start Stream", state=tk.NORMAL
                ),
            )
            # Ensure capture loop is stopped
            self._stop_capture()

        self.ws = WebSocketApp(
            self.ws_url,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )

        # Run forever until window closes
        try:
            self.ws.run_forever(ping_interval=None, ping_timeout=None, reconnect=5)
        except TypeError:
            # Some websocket-client versions don't support 'reconnect' kwarg
            self.ws.run_forever(ping_interval=None, ping_timeout=None)

    # ----------------------------- Capture Handling ----------------------------
    def _start_capture(self) -> None:
        """Start the capture thread if not already running."""
        if self.streaming_active:
            return

        self.capture_stop_event.clear()
        self.streaming_active = True

        # Notify stream status (use boolean for server compatibility)
        self._safe_send_json(
            {
                "type": "stream_status",
                "streaming": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "clientId": self.client_id,
            }
        )

        self.capture_thread = threading.Thread(
            target=self._capture_loop, name="capture-thread", daemon=True
        )
        self.capture_thread.start()

        # Update UI silently
        self.root.after(
            0,
            lambda: self.start_button.configure(text="Streaming...", state=tk.DISABLED),
        )

    def _stop_capture(self) -> None:
        """Signal the capture loop to stop and report status."""
        if not self.streaming_active:
            return
        self.capture_stop_event.set()
        self.streaming_active = False

        # Notify stream status
        self._safe_send_json(
            {
                "type": "stream_status",
                "streaming": False,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "clientId": self.client_id,
            }
        )

        # Reset UI to allow restart
        self.root.after(
            0, lambda: self.start_button.configure(text="Start Stream", state=tk.NORMAL)
        )

    def _capture_loop(self) -> None:
        """Efficient capture loop using mss + JPEG encode, throttled by desired FPS."""
        desired_fps = max(1, int(self.current_config.get("fps", 12)))
        quality = int(self.current_config.get("quality", 80))
        scale = float(self.current_config.get("scale", 1.0))
        fmt = (self.current_config.get("format", "jpeg") or "jpeg").lower()
        if fmt != "jpeg":
            fmt = "jpeg"  # enforce jpeg for compatibility and efficiency

        frame_interval = 1.0 / float(desired_fps)

        with mss() as sct:
            # Monitor 1 is primary display in mss
            monitor = sct.monitors[1]

            while not self.capture_stop_event.is_set():
                t0 = time.perf_counter()
                # Grab raw frame
                raw = sct.grab(monitor)
                img = Image.frombytes("RGB", raw.size, raw.rgb)

                # Optional downscale for bandwidth/CPU savings
                if 0.1 <= scale < 1.0:
                    new_w = max(1, int(img.width * scale))
                    new_h = max(1, int(img.height * scale))
                    img = img.resize((new_w, new_h), Image.LANCZOS)

                # Encode JPEG
                buf = BytesIO()
                img.save(buf, format="JPEG", quality=quality, optimize=True)
                jpeg_bytes = buf.getvalue()
                buf.close()

                # Base64 encode
                b64 = base64.b64encode(jpeg_bytes).decode("ascii")

                # Prepare message
                msg = {
                    "type": "frame_data",
                    "frameData": b64,
                    "width": img.width,
                    "height": img.height,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "monitorId": self.screen_id,  # 'monitor_0'
                    "metadata": {
                        "clientId": self.client_id,
                        "config": {
                            "fps": desired_fps,
                            "scale": scale,
                            "format": fmt,
                        },
                        "source": "minimal_desktop_capture",
                    },
                }

                # Send over WS
                self._safe_send_json(msg)

                # Sleep to maintain target FPS
                dt = time.perf_counter() - t0
                sleep_time = max(0.0, frame_interval - dt)
                if sleep_time > 0:
                    time.sleep(sleep_time)

    # ------------------------------ Util methods ------------------------------
    def _safe_send_json(self, data: Dict[str, Any]) -> None:
        """Send JSON if socket is open; swallow errors to keep client resilient."""
        try:
            if self.ws and self.ws.sock and self.ws.sock.connected:
                self.ws.send(json.dumps(data))
        except Exception as exc:
            print(f"[WS][SEND][ERROR] {exc}")

    # ------------------------------- Entrypoint --------------------------------
    def run(self) -> None:
        """Start the single-button UI."""
        self.root.mainloop()


if __name__ == "__main__":
    client = MinimalDesktopCaptureClient()
    client.run()
