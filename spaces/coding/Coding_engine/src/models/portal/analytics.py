"""
Usage analytics models for cells.
"""

from datetime import date, datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class EventType(str, Enum):
    """Types of analytics events."""
    VIEW = "view"
    DOWNLOAD = "download"
    INSTALL = "install"
    UNINSTALL = "uninstall"
    DEPLOY = "deploy"
    ERROR = "error"


class CellUsageAnalytics(Base):
    """
    Aggregated daily usage analytics for cells.

    Stores daily rollups for efficient querying.
    """
    __tablename__ = "cell_usage_analytics"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    cell_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("cells.id", ondelete="CASCADE"),
        nullable=False,
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)

    # View metrics
    page_views: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unique_visitors: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Download metrics
    downloads: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unique_downloaders: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Install metrics
    installs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    uninstalls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    net_installs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Deploy metrics
    deployments: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active_deployments: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Error metrics
    deploy_errors: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    runtime_errors: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Geographic distribution (JSON: {country_code: count})
    geo_distribution: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # Version distribution (JSON: {version: count})
    version_distribution: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # Referrer sources (JSON: {source: count})
    referrer_sources: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # Relationships
    cell: Mapped["CellRegistry"] = relationship("CellRegistry")

    __table_args__ = (
        UniqueConstraint("cell_id", "date", name="uq_analytics_cell_date"),
        Index("ix_analytics_cell_id", "cell_id"),
        Index("ix_analytics_date", "date"),
        Index("ix_analytics_cell_date", "cell_id", "date"),
    )

    def __repr__(self) -> str:
        return f"<CellUsageAnalytics(cell_id={self.cell_id}, date={self.date})>"


class DownloadRecord(Base, TimestampMixin):
    """
    Individual download record for detailed analytics.

    Kept for 90 days then rolled up into aggregates.
    """
    __tablename__ = "download_records"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    cell_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("cells.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("cell_versions.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Event info
    event_type: Mapped[EventType] = mapped_column(
        SQLEnum(EventType),
        nullable=False,
    )
    version: Mapped[str] = mapped_column(String(50), nullable=False)

    # User info (anonymized)
    user_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    tenant_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    is_anonymous: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Request info
    ip_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # Hashed IP
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    country_code: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Referrer
    referrer_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    referrer_source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Context
    install_context: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # cli, api, web

    # Relationships
    cell: Mapped["CellRegistry"] = relationship("CellRegistry")
    version_record: Mapped[Optional["CellVersion"]] = relationship("CellVersion")

    __table_args__ = (
        Index("ix_downloads_cell_id", "cell_id"),
        Index("ix_downloads_created_at", "created_at"),
        Index("ix_downloads_event_type", "event_type"),
        Index("ix_downloads_user_id", "user_id"),
        # Partitioning hint for time-based data (apply in PostgreSQL)
    )

    def __repr__(self) -> str:
        return f"<DownloadRecord(cell_id={self.cell_id}, event={self.event_type}, version={self.version})>"


# Avoid circular import
from .cell import CellRegistry, CellVersion
