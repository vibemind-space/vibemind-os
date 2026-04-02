"""
media_server.py - Lokaler HTTP Fileserver fuer Video/Audio Assets
Served ~/.rowboat/Videos/ auf http://localhost:9877/

Supports HTTP Range Requests fuer sofortiges Video-Streaming.

Usage:
    # Standalone
    python media_server.py

    # Als Thread im Backend
    from spaces.video.media_server import start_media_server
    start_media_server()  # non-blocking, startet eigenen Thread
"""

import os
import socket
import threading
import logging
import mimetypes
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from functools import partial

logger = logging.getLogger(__name__)

PORT = int(os.environ.get("MEDIA_SERVER_PORT", "9877"))
MEDIA_ROOT = Path.home() / ".rowboat" / "Videos"

# Ensure video MIME types are registered
mimetypes.add_type("video/mp4", ".mp4")
mimetypes.add_type("video/webm", ".webm")
mimetypes.add_type("video/x-msvideo", ".avi")
mimetypes.add_type("video/quicktime", ".mov")
mimetypes.add_type("audio/wav", ".wav")


class MediaHandler(SimpleHTTPRequestHandler):
    """Serves files with CORS + HTTP Range Requests for video streaming."""

    def do_GET(self):
        """Override GET to support Range requests for video streaming."""
        path = self.translate_path(self.path)
        if not os.path.isfile(path):
            return super().do_GET()  # Let parent handle dirs/404

        file_size = os.path.getsize(path)
        content_type = mimetypes.guess_type(path)[0] or "application/octet-stream"

        range_header = self.headers.get("Range")
        if range_header:
            # Parse Range: bytes=START-END
            try:
                range_spec = range_header.replace("bytes=", "")
                parts = range_spec.split("-")
                start = int(parts[0]) if parts[0] else 0
                end = int(parts[1]) if parts[1] else file_size - 1
                end = min(end, file_size - 1)
                length = end - start + 1

                self.send_response(206)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(length))
                self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()

                with open(path, "rb") as f:
                    f.seek(start)
                    remaining = length
                    while remaining > 0:
                        chunk = f.read(min(65536, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
                return
            except (ValueError, IndexError):
                pass  # Fall through to normal GET

        # Normal full-file response with Accept-Ranges header
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(file_size))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        with open(path, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)

    def do_HEAD(self):
        """Support HEAD for preflight checks."""
        path = self.translate_path(self.path)
        if os.path.isfile(path):
            file_size = os.path.getsize(path)
            content_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(file_size))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        """CORS preflight."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Range")
        self.end_headers()

    def log_message(self, format, *args):
        logger.debug(f"[MediaServer] {args[0]}")


def start_media_server(port: int = None, directory: str = None) -> ThreadingHTTPServer:
    """Start media server in a daemon thread. Returns the server instance."""
    port = port or PORT
    directory = directory or str(MEDIA_ROOT)

    if not Path(directory).exists():
        Path(directory).mkdir(parents=True, exist_ok=True)

    handler = partial(MediaHandler, directory=directory)
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    ready = threading.Event()

    def serve():
        ready.set()
        server.serve_forever()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    ready.wait(timeout=5)

    logger.info(f"Media server running: http://localhost:{port}/ -> {directory}")
    return server


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(f"Serving {MEDIA_ROOT} on http://localhost:{PORT}/")
    print(f"Example: http://localhost:{PORT}/data/Felix.mp4")
    print("Press Ctrl+C to stop.")
    server = start_media_server()
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        server.shutdown()
        print("\nStopped.")