"""
Stream Frame Cache - Speichert Live-Stream Frames für MCP-Tools

Ermöglicht MCP-Tools (wie handoff_read_screen) den Zugriff auf
aktuelle Stream-Frames statt eigene Screenshots zu machen.

Usage:
    from stream_frame_cache import StreamFrameCache

    # Frame speichern (von WebSocket)
    StreamFrameCache.update_frame(
        monitor_id=0,
        frame_base64="...",
        metadata={"width": 1920, "height": 1080}
    )

    # Frame abrufen (für MCP-Tool)
    frame = StreamFrameCache.get_latest_frame(monitor_id=0)
    if frame and frame.age_ms < 1000:
        # Frame ist frisch genug
        image_data = frame.data
"""

import base64
import time
import threading
from dataclasses import dataclass, field
from typing import Dict, Optional, Any
from datetime import datetime
import io

try:
    from PIL import Image
except ImportError:
    Image = None


@dataclass
class FrameData:
    """Einzelner Frame mit Metadaten."""
    monitor_id: int
    data: str  # Base64-encoded image
    timestamp: float  # Unix timestamp when frame was received
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def age_ms(self) -> float:
        """Alter des Frames in Millisekunden."""
        return (time.time() - self.timestamp) * 1000

    @property
    def is_fresh(self) -> bool:
        """True wenn Frame weniger als 1 Sekunde alt."""
        return self.age_ms < 1000

    @property
    def width(self) -> int:
        """Breite des Frames."""
        return self.metadata.get("width", 0)

    @property
    def height(self) -> int:
        """Höhe des Frames."""
        return self.metadata.get("height", 0)

    def to_pil_image(self) -> Optional["Image.Image"]:
        """Konvertiert Base64-Daten zu PIL Image."""
        if Image is None:
            return None

        try:
            # Remove data URL prefix if present
            data = self.data
            if data.startswith("data:"):
                data = data.split(",", 1)[1]

            # Decode base64
            image_bytes = base64.b64decode(data)
            return Image.open(io.BytesIO(image_bytes))
        except Exception as e:
            print(f"[StreamFrameCache] Error converting to PIL: {e}")
            return None

    def to_bytes(self) -> Optional[bytes]:
        """Konvertiert Base64-Daten zu Bytes."""
        try:
            data = self.data
            if data.startswith("data:"):
                data = data.split(",", 1)[1]
            return base64.b64decode(data)
        except Exception as e:
            print(f"[StreamFrameCache] Error decoding base64: {e}")
            return None


class StreamFrameCache:
    """
    Thread-safe Cache für Live-Stream Frames.

    Speichert den aktuellsten Frame pro Monitor für den Zugriff
    durch MCP-Tools und andere Backend-Komponenten.
    """

    _frames: Dict[int, FrameData] = {}
    _lock = threading.Lock()
    _listeners: Dict[str, callable] = {}

    # Statistiken
    _stats = {
        "frames_received": 0,
        "frames_served": 0,
        "cache_hits": 0,
        "cache_misses": 0,
    }

    @classmethod
    def update_frame(
        cls,
        monitor_id: int,
        frame_base64: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Aktualisiert den Frame für einen Monitor.

        Args:
            monitor_id: Monitor-Index (0, 1, ...)
            frame_base64: Base64-encoded Bilddaten
            metadata: Optionale Metadaten (width, height, format, etc.)
        """
        with cls._lock:
            frame = FrameData(
                monitor_id=monitor_id,
                data=frame_base64,
                timestamp=time.time(),
                metadata=metadata or {}
            )
            cls._frames[monitor_id] = frame
            cls._stats["frames_received"] += 1

        # Notify listeners
        for listener_id, callback in list(cls._listeners.items()):
            try:
                callback(monitor_id, frame)
            except Exception as e:
                print(f"[StreamFrameCache] Listener {listener_id} error: {e}")

    @classmethod
    def get_latest_frame(cls, monitor_id: int = 0) -> Optional[FrameData]:
        """
        Gibt den aktuellsten Frame für einen Monitor zurück.

        Args:
            monitor_id: Monitor-Index (default: 0)

        Returns:
            FrameData oder None wenn kein Frame vorhanden
        """
        with cls._lock:
            frame = cls._frames.get(monitor_id)
            if frame:
                cls._stats["frames_served"] += 1
                cls._stats["cache_hits"] += 1
            else:
                cls._stats["cache_misses"] += 1
            return frame

    @classmethod
    def get_all_frames(cls) -> Dict[int, FrameData]:
        """Gibt alle gecachten Frames zurück."""
        with cls._lock:
            return dict(cls._frames)

    @classmethod
    def get_fresh_frame(
        cls,
        monitor_id: int = 0,
        max_age_ms: float = 1000
    ) -> Optional[FrameData]:
        """
        Gibt Frame zurück, nur wenn er frisch genug ist.

        Args:
            monitor_id: Monitor-Index
            max_age_ms: Maximales Alter in Millisekunden

        Returns:
            FrameData oder None wenn zu alt oder nicht vorhanden
        """
        frame = cls.get_latest_frame(monitor_id)
        if frame and frame.age_ms <= max_age_ms:
            return frame
        return None

    @classmethod
    def clear(cls, monitor_id: Optional[int] = None) -> None:
        """
        Löscht gecachte Frames.

        Args:
            monitor_id: Spezifischer Monitor oder None für alle
        """
        with cls._lock:
            if monitor_id is not None:
                cls._frames.pop(monitor_id, None)
            else:
                cls._frames.clear()

    @classmethod
    def add_listener(cls, listener_id: str, callback: callable) -> None:
        """
        Registriert einen Listener für neue Frames.

        Args:
            listener_id: Eindeutige ID für den Listener
            callback: Funktion(monitor_id, frame_data) die aufgerufen wird
        """
        cls._listeners[listener_id] = callback

    @classmethod
    def remove_listener(cls, listener_id: str) -> None:
        """Entfernt einen Listener."""
        cls._listeners.pop(listener_id, None)

    @classmethod
    def get_stats(cls) -> Dict[str, Any]:
        """Gibt Cache-Statistiken zurück."""
        with cls._lock:
            stats = dict(cls._stats)
            stats["cached_monitors"] = list(cls._frames.keys())
            stats["frame_ages_ms"] = {
                mid: frame.age_ms
                for mid, frame in cls._frames.items()
            }
            return stats

    @classmethod
    def get_status(cls) -> Dict[str, Any]:
        """Gibt Status-Übersicht zurück."""
        with cls._lock:
            return {
                "monitors_cached": len(cls._frames),
                "monitor_ids": list(cls._frames.keys()),
                "frames_received": cls._stats["frames_received"],
                "cache_hit_rate": (
                    cls._stats["cache_hits"] /
                    max(1, cls._stats["cache_hits"] + cls._stats["cache_misses"])
                ),
                "listeners_count": len(cls._listeners),
                "frames": {
                    mid: {
                        "age_ms": frame.age_ms,
                        "is_fresh": frame.is_fresh,
                        "width": frame.width,
                        "height": frame.height,
                    }
                    for mid, frame in cls._frames.items()
                }
            }


# Convenience functions für direkten Import
def update_frame(monitor_id: int, frame_base64: str, metadata: dict = None):
    """Shortcut für StreamFrameCache.update_frame()."""
    StreamFrameCache.update_frame(monitor_id, frame_base64, metadata)


def get_frame(monitor_id: int = 0) -> Optional[FrameData]:
    """Shortcut für StreamFrameCache.get_latest_frame()."""
    return StreamFrameCache.get_latest_frame(monitor_id)


def get_fresh_frame(monitor_id: int = 0, max_age_ms: float = 1000) -> Optional[FrameData]:
    """Shortcut für StreamFrameCache.get_fresh_frame()."""
    return StreamFrameCache.get_fresh_frame(monitor_id, max_age_ms)


# Test
if __name__ == "__main__":
    import time

    print("Testing StreamFrameCache...")

    # Update frame
    StreamFrameCache.update_frame(
        monitor_id=0,
        frame_base64="dGVzdCBkYXRh",  # "test data" in base64
        metadata={"width": 1920, "height": 1080, "format": "jpeg"}
    )

    # Get frame
    frame = StreamFrameCache.get_latest_frame(0)
    print(f"Frame: monitor={frame.monitor_id}, age={frame.age_ms:.1f}ms, fresh={frame.is_fresh}")

    # Wait and check age
    time.sleep(0.5)
    frame = StreamFrameCache.get_latest_frame(0)
    print(f"After 500ms: age={frame.age_ms:.1f}ms, fresh={frame.is_fresh}")

    # Stats
    print(f"Stats: {StreamFrameCache.get_stats()}")
    print(f"Status: {StreamFrameCache.get_status()}")

    print("Test complete!")
