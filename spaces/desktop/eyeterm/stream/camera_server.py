"""MJPEG HTTP streaming server for eyeTerm camera feed.

Serves composited camera frames (with face mesh overlay) as an MJPEG stream
at http://localhost:{port}/stream for embedding in Electron BrowserView.
"""

import logging
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger("eyeterm.stream")


class _StreamHandler(BaseHTTPRequestHandler):
    """HTTP handler that serves MJPEG multipart stream."""

    server: "CameraStreamServer"  # type hint for our custom server

    def do_GET(self):
        if self.path == "/stream":
            self._serve_mjpeg()
        elif self.path == "/status":
            self._serve_status()
        elif self.path == "/gaze":
            self._serve_gaze()
        elif self.path == "/":
            self._serve_index()
        else:
            self.send_error(404)

    def _serve_mjpeg(self):
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        while not self.server.shutdown_flag.is_set():
            frame_bytes = self.server.get_current_jpeg()
            if frame_bytes is None:
                time.sleep(0.05)
                continue
            try:
                self.wfile.write(b"--frame\r\n")
                self.wfile.write(b"Content-Type: image/jpeg\r\n")
                self.wfile.write(f"Content-Length: {len(frame_bytes)}\r\n\r\n".encode())
                self.wfile.write(frame_bytes)
                self.wfile.write(b"\r\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                break
            time.sleep(1 / 30)  # ~30 fps cap

    def _serve_gaze(self):
        """Fast gaze position endpoint — polled at ~50ms by frontend."""
        import json
        gaze = self.server.get_gaze()
        body = json.dumps(gaze).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass

    def _serve_status(self):
        import json
        body = json.dumps({
            "status": "running",
            "has_frame": self.server.get_current_jpeg() is not None,
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass

    def _serve_index(self):
        html = b"""<!DOCTYPE html>
<html><head><title>eyeTerm Camera</title>
<style>body{margin:0;background:#000;display:flex;align-items:center;justify-content:center;height:100vh}
img{max-width:100%;max-height:100%}</style></head>
<body><img src="/stream" alt="eyeTerm Camera Feed"></body></html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)

    def log_message(self, format, *args):
        # Suppress default HTTP logging
        pass


class _ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """HTTPServer that handles each request in a new thread.

    Required because the MJPEG /stream endpoint holds the connection open,
    blocking single-threaded servers from serving /gaze or /status.
    """
    daemon_threads = True


class CameraStreamServer(_ThreadingHTTPServer):
    """MJPEG streaming server for eyeTerm camera preview.

    Usage:
        server = CameraStreamServer(port=8099)
        server.start()  # runs in background thread

        # In main loop:
        server.update_frame(cv2_frame)

        # On shutdown:
        server.stop()
    """

    def __init__(self, port: int = 8099):
        self._port = port
        self._current_jpeg: Optional[bytes] = None
        self._frame_lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self.shutdown_flag = threading.Event()
        self._gaze: dict = {"x": 0, "y": 0, "valid": False, "sw": 1920, "sh": 1080}

        self.allow_reuse_address = True  # Must be set BEFORE __init__ calls server_bind()

        # Try to kill stale process on this port before binding
        self._try_free_port(port)

        try:
            super().__init__(("127.0.0.1", port), _StreamHandler)
        except OSError as e:
            logger.warning("Port %d busy (%s), retrying after force-free...", port, e)
            self._try_free_port(port, force=True)
            super().__init__(("127.0.0.1", port), _StreamHandler)

        logger.info("Camera stream server created on port %d", port)

    @staticmethod
    def _try_free_port(port: int, force: bool = False) -> None:
        """Check if port is in use and optionally kill the holder."""
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.settimeout(0.5)
            result = sock.connect_ex(("127.0.0.1", port))
            if result == 0:
                # Port is actively in use
                logger.warning("Port %d is already in use", port)
                if force:
                    import subprocess
                    try:
                        # Find PID holding the port
                        out = subprocess.check_output(
                            ["netstat", "-ano"], text=True, timeout=5
                        )
                        for line in out.splitlines():
                            if f":{port}" in line and "ABHÖREN" in line or "LISTENING" in line:
                                pid = line.strip().split()[-1]
                                if pid.isdigit():
                                    subprocess.run(
                                        ["taskkill", "/F", "/PID", pid],
                                        timeout=5, capture_output=True,
                                    )
                                    logger.info("Killed stale process PID %s on port %d", pid, port)
                                    import time
                                    time.sleep(0.5)
                                    break
                    except Exception as e:
                        logger.debug("Port cleanup failed: %s", e)
        except Exception:
            pass
        finally:
            sock.close()

    def update_frame(self, frame: np.ndarray, quality: int = 70) -> None:
        """Push latest composited frame (BGR numpy array).

        Args:
            frame: OpenCV BGR frame.
            quality: JPEG quality (0-100). Lower = smaller = faster.
        """
        try:
            _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
            with self._frame_lock:
                self._current_jpeg = jpeg.tobytes()
        except Exception as e:
            logger.debug("Failed to encode frame: %s", e)

    def get_current_jpeg(self) -> Optional[bytes]:
        """Get the latest JPEG frame bytes."""
        with self._frame_lock:
            return self._current_jpeg

    def update_gaze(self, x: int, y: int, valid: bool, sw: int, sh: int) -> None:
        """Update current gaze screen position (called from main loop)."""
        self._gaze = {"x": x, "y": y, "valid": valid, "sw": sw, "sh": sh}

    def get_gaze(self) -> dict:
        """Get current gaze position for REST endpoint."""
        return self._gaze

    def start(self) -> None:
        """Start serving in a background daemon thread."""
        if self._thread and self._thread.is_alive():
            return

        self.shutdown_flag.clear()
        self._thread = threading.Thread(
            target=self._serve_forever,
            name="eyeterm-camera-stream",
            daemon=True,
        )
        self._thread.start()
        logger.info("Camera stream started: http://127.0.0.1:%d/stream", self._port)

    def _serve_forever(self):
        """Serve until shutdown_flag is set."""
        try:
            self.serve_forever(poll_interval=0.5)
        except Exception as e:
            logger.error("Stream server error: %s", e)

    def stop(self) -> None:
        """Stop the stream server."""
        self.shutdown_flag.set()
        try:
            self.shutdown()  # Stops serve_forever() loop
            self.server_close()
        except Exception:
            pass
        if self._thread:
            self._thread.join(timeout=2)
        logger.info("Camera stream stopped")
