"""
SQLAlchemy ORM Models for TRAE Backend

Database models for desktop streaming, configurations, and automation.
Migrated from Supabase Cloud to local PostgreSQL for full data sovereignty.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import Boolean, Column, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.sql import func

from app.database import Base


class LiveDesktopConfig(Base):
    """Desktop streaming configuration storage"""

    __tablename__ = "live_desktop_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(100), nullable=True)
    configuration = Column(JSON, default=dict, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by = Column(String(255), nullable=True)
    tags = Column(JSON, default=list, nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "configuration": self.configuration,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "created_by": self.created_by,
            "tags": self.tags
        }


class ActiveDesktopClient(Base):
    """Currently connected desktop streaming clients"""

    __tablename__ = "active_desktop_clients"

    client_id = Column(String(255), primary_key=True)
    name = Column(String(255), nullable=True)
    monitors = Column(JSON, default=list, nullable=False)
    capabilities = Column(JSON, default=dict, nullable=False)
    user_id = Column(String(255), nullable=True)
    hostname = Column(String(255), nullable=True)
    is_streaming = Column(Boolean, default=False, nullable=False)
    last_ping = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    connected_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Index for cleanup queries
    __table_args__ = (
        Index('idx_active_clients_last_ping', 'last_ping'),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "client_id": self.client_id,
            "name": self.name,
            "monitors": self.monitors,
            "capabilities": self.capabilities,
            "user_id": self.user_id,
            "hostname": self.hostname,
            "is_streaming": self.is_streaming,
            "last_ping": self.last_ping.isoformat() if self.last_ping else None,
            "connected_at": self.connected_at.isoformat() if self.connected_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


class DesktopCommand(Base):
    """Command queue for desktop clients"""

    __tablename__ = "desktop_commands"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    desktop_client_id = Column(String(255), nullable=False)
    command_type = Column(String(100), nullable=False)
    command_data = Column(JSON, default=dict, nullable=False)
    status = Column(String(50), default="pending", nullable=False)  # pending, completed, failed
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    idempotency_key = Column(String(255), nullable=True, unique=True)

    # Indexes for efficient querying
    __table_args__ = (
        Index('idx_desktop_commands_client_status', 'desktop_client_id', 'status'),
        Index('idx_desktop_commands_created', 'created_at'),
        Index('idx_desktop_commands_pending', 'desktop_client_id', 'status', 'created_at',
              postgresql_where=(status == 'pending')),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "desktop_client_id": self.desktop_client_id,
            "command_type": self.command_type,
            "command_data": self.command_data,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
            "error_message": self.error_message,
            "idempotency_key": self.idempotency_key
        }


class WorkflowRecord(Base):
    """Persistent workflow storage"""

    __tablename__ = "workflows"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    nodes = Column(JSON, default=list, nullable=False)
    connections = Column(JSON, default=list, nullable=False)
    variables = Column(JSON, default=dict, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by = Column(String(255), nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "nodes": self.nodes,
            "connections": self.connections,
            "variables": self.variables,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "created_by": self.created_by
        }


class WorkflowExecutionRecord(Base):
    """Workflow execution history"""

    __tablename__ = "workflow_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id = Column(UUID(as_uuid=True), nullable=False)
    status = Column(String(50), default="pending", nullable=False)  # pending, running, completed, failed, cancelled
    node_results = Column(JSON, default=dict, nullable=False)
    variables = Column(JSON, default=dict, nullable=False)
    logs = Column(JSON, default=list, nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index('idx_workflow_executions_workflow', 'workflow_id'),
        Index('idx_workflow_executions_status', 'status'),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "workflow_id": str(self.workflow_id),
            "status": self.status,
            "node_results": self.node_results,
            "variables": self.variables,
            "logs": self.logs,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
