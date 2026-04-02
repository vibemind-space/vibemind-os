"""
Moderation models for cell reports and quarantine.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class ReportType(str, Enum):
    """Types of content reports."""
    MALWARE = "malware"
    VULNERABILITY = "vulnerability"
    LICENSE_VIOLATION = "license_violation"
    INAPPROPRIATE_CONTENT = "inappropriate_content"
    SPAM = "spam"
    TRADEMARK_VIOLATION = "trademark_violation"
    COPYRIGHT_VIOLATION = "copyright_violation"
    BROKEN = "broken"
    OTHER = "other"


class ReportStatus(str, Enum):
    """Report processing status."""
    PENDING = "pending"
    INVESTIGATING = "investigating"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    RESOLVED = "resolved"
    ESCALATED = "escalated"


class ReportSeverity(str, Enum):
    """Report severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class QuarantineReason(str, Enum):
    """Reasons for quarantine."""
    SECURITY_VULNERABILITY = "security_vulnerability"
    MALWARE_DETECTED = "malware_detected"
    LICENSE_ISSUE = "license_issue"
    POLICY_VIOLATION = "policy_violation"
    COMMUNITY_REPORTS = "community_reports"
    AUTOMATED_SCAN = "automated_scan"
    MANUAL_REVIEW = "manual_review"


class CellReport(Base, TimestampMixin):
    """
    User-submitted report about a cell.
    """
    __tablename__ = "cell_reports"

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
    cell_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Reporter info
    reporter_user_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    reporter_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reporter_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Report details
    report_type: Mapped[ReportType] = mapped_column(
        SQLEnum(ReportType),
        nullable=False,
    )
    severity: Mapped[ReportSeverity] = mapped_column(
        SQLEnum(ReportSeverity),
        default=ReportSeverity.MEDIUM,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # Evidence
    evidence_urls: Mapped[List[str]] = mapped_column(ARRAY(String(500)), default=list, nullable=False)
    evidence_files: Mapped[List[str]] = mapped_column(ARRAY(String(500)), default=list, nullable=False)
    reproduction_steps: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # CVE info (if vulnerability)
    cve_id: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    cvss_score: Mapped[Optional[float]] = mapped_column(nullable=True)

    # Status
    status: Mapped[ReportStatus] = mapped_column(
        SQLEnum(ReportStatus),
        default=ReportStatus.PENDING,
        nullable=False,
    )
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Assignment
    assigned_to: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    assigned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Resolution
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolved_by: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Actions taken
    cell_quarantined: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    version_yanked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    owner_notified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notification_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Duplicate tracking
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    duplicate_of: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)

    # Internal notes (not visible to reporter)
    internal_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Related quarantine
    quarantine_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("cell_quarantines.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    cell: Mapped["CellRegistry"] = relationship("CellRegistry")
    quarantine: Mapped[Optional["CellQuarantine"]] = relationship("CellQuarantine", back_populates="reports")

    __table_args__ = (
        Index("ix_reports_cell_id", "cell_id"),
        Index("ix_reports_status", "status"),
        Index("ix_reports_severity", "severity"),
        Index("ix_reports_report_type", "report_type"),
        Index("ix_reports_created_at", "created_at"),
        Index("ix_reports_priority", "priority", postgresql_ops={"priority": "DESC"}),
    )

    def __repr__(self) -> str:
        return f"<CellReport(id={self.id}, cell={self.cell_id}, type={self.report_type}, status={self.status})>"


class CellQuarantine(Base, TimestampMixin):
    """
    Quarantine record for cells under review.

    Quarantined cells are hidden from public search and
    cannot be installed until released.
    """
    __tablename__ = "cell_quarantines"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    cell_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("cells.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # One quarantine per cell at a time
    )

    # Quarantine details
    reason: Mapped[QuarantineReason] = mapped_column(
        SQLEnum(QuarantineReason),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    affected_versions: Mapped[List[str]] = mapped_column(ARRAY(String(50)), default=list, nullable=False)

    # Severity
    severity: Mapped[ReportSeverity] = mapped_column(
        SQLEnum(ReportSeverity),
        default=ReportSeverity.HIGH,
        nullable=False,
    )

    # Actions
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    all_versions_affected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    downloads_blocked: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    search_hidden: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Quarantine by
    quarantined_by: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    quarantined_by_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Review process
    review_deadline: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewer_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    review_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Release
    is_released: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    released_by: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    released_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    release_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Required actions for release
    required_actions: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    actions_completed: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # Owner communication
    owner_notified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    owner_notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    owner_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    owner_response_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Public notice
    public_notice: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    show_public_notice: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Timeline/audit log
    audit_log: Mapped[List[dict]] = mapped_column(JSONB, default=list, nullable=False)

    # Relationships
    cell: Mapped["CellRegistry"] = relationship("CellRegistry")
    reports: Mapped[List["CellReport"]] = relationship(
        "CellReport",
        back_populates="quarantine",
    )

    __table_args__ = (
        Index("ix_quarantines_cell_id", "cell_id"),
        Index("ix_quarantines_is_active", "is_active"),
        Index("ix_quarantines_severity", "severity"),
        Index("ix_quarantines_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<CellQuarantine(id={self.id}, cell={self.cell_id}, active={self.is_active})>"

    def add_audit_entry(self, action: str, user_id: str, details: Optional[dict] = None) -> None:
        """Add an entry to the audit log."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "user_id": user_id,
            "details": details or {},
        }
        self.audit_log = self.audit_log + [entry]


# Avoid circular import
from .cell import CellRegistry
