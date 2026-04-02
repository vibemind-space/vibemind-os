"""
Database model for connection events timeline.
Stores real-time connection events for dashboard display.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, Integer, DateTime, JSON, Text, Index
from sqlalchemy.sql import func
from src.models.base import Base


class ConnectionEvent(Base):
    """
    Connection event model for real-time timeline tracking.
    Stores connection events with timestamp, type, and affected resources.
    """

    __tablename__ = "connection_events"

    # Event identification
    event_id = Column(String(100), unique=True, nullable=False, index=True)
    event_type = Column(String(50), nullable=False, index=True)

    # Timestamp (indexed for timeline queries)
    timestamp = Column(DateTime, nullable=False, default=func.now(), index=True)

    # Source information
    source = Column(String(100), nullable=False)

    # Resource details
    process_id = Column(Integer, nullable=True, index=True)
    process_name = Column(String(255), nullable=True)
    port = Column(Integer, nullable=True, index=True)
    protocol = Column(String(10), nullable=True)  # TCP/UDP

    # Connection details
    local_address = Column(String(100), nullable=True)
    remote_address = Column(String(100), nullable=True)
    connection_state = Column(String(50), nullable=True)

    # Additional data (flexible JSON field)
    data = Column(JSON, nullable=True)

    # Message/description
    message = Column(Text, nullable=True)

    # Status/severity
    severity = Column(String(20), nullable=False, default="info")  # info, warning, error
    success = Column(Integer, nullable=False, default=1)  # 1=success, 0=failure

    # Indexes for performance
    __table_args__ = (
        Index('idx_timestamp_type', 'timestamp', 'event_type'),
        Index('idx_process_timestamp', 'process_id', 'timestamp'),
        Index('idx_port_timestamp', 'port', 'timestamp'),
    )

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "source": self.source,
            "process_id": self.process_id,
            "process_name": self.process_name,
            "port": self.port,
            "protocol": self.protocol,
            "local_address": self.local_address,
            "remote_address": self.remote_address,
            "connection_state": self.connection_state,
            "data": self.data,
            "message": self.message,
            "severity": self.severity,
            "success": bool(self.success),
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

    def to_timeline_entry(self) -> dict:
        """Convert to timeline entry format for dashboard."""
        return {
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "event_type": self.event_type,
            "affected_resource": self._format_affected_resource(),
            "message": self.message or self._generate_message(),
            "severity": self.severity,
            "details": {
                "source": self.source,
                "process_id": self.process_id,
                "process_name": self.process_name,
                "port": self.port,
                "protocol": self.protocol,
                "connection_state": self.connection_state,
                "data": self.data
            }
        }

    def _format_affected_resource(self) -> str:
        """Format affected resource description."""
        parts = []
        if self.process_name:
            parts.append(f"Process: {self.process_name}")
        if self.process_id:
            parts.append(f"(PID: {self.process_id})")
        if self.port:
            parts.append(f"Port: {self.port}")
        if self.protocol:
            parts.append(f"({self.protocol})")

        return " ".join(parts) if parts else "System"

    def _generate_message(self) -> str:
        """Generate default message if none provided."""
        if self.process_name and self.port:
            return f"{self.event_type}: {self.process_name} on port {self.port}"
        elif self.process_name:
            return f"{self.event_type}: {self.process_name}"
        elif self.port:
            return f"{self.event_type}: Port {self.port}"
        return self.event_type

    @classmethod
    def from_event_bus(cls, event: dict) -> "ConnectionEvent":
        """
        Create ConnectionEvent from EventBus event.

        Args:
            event: Event dictionary from EventBus

        Returns:
            ConnectionEvent instance
        """
        import uuid
        from datetime import datetime

        # Extract data
        data = event.get("data", {})

        return cls(
            event_id=str(uuid.uuid4()),
            event_type=event.get("type", "UNKNOWN"),
            timestamp=datetime.fromisoformat(event["timestamp"]) if isinstance(event.get("timestamp"), str) else event.get("timestamp", datetime.utcnow()),
            source=event.get("source", "system"),
            process_id=data.get("process_id") or data.get("pid"),
            process_name=data.get("process_name") or data.get("name"),
            port=data.get("port"),
            protocol=data.get("protocol"),
            local_address=data.get("local_address"),
            remote_address=data.get("remote_address"),
            connection_state=data.get("connection_state") or data.get("status"),
            data=data,
            message=event.get("message") or data.get("message"),
            severity=cls._determine_severity(event),
            success=1 if event.get("success", True) else 0
        )

    @staticmethod
    def _determine_severity(event: dict) -> str:
        """Determine severity from event type."""
        event_type = event.get("type", "").upper()

        if any(x in event_type for x in ["ERROR", "FAILED", "CRASH"]):
            return "error"
        elif any(x in event_type for x in ["WARNING", "WARN"]):
            return "warning"
        elif any(x in event_type for x in ["SUCCESS", "COMPLETE", "PASSED"]):
            return "success"
        else:
            return "info"
