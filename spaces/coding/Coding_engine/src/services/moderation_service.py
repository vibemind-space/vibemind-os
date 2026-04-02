"""
Moderation Service - Community content moderation and safety.

Handles:
- Report submission and tracking
- Auto-escalation for critical reports
- Cell quarantine mechanism
- Release workflow after review
- Moderation queue management
- Trust scoring for contributors
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
import uuid

import structlog

from src.mind.event_bus import EventBus, Event
from src.services.cell_security_scanner import CellSecurityScanner, ScanResult

logger = structlog.get_logger()


class ReportType(str, Enum):
    """Types of content reports."""
    MALWARE = "malware"
    VULNERABILITY = "vulnerability"
    SPAM = "spam"
    INAPPROPRIATE = "inappropriate"
    COPYRIGHT = "copyright"
    LICENSE_VIOLATION = "license_violation"
    MISLEADING = "misleading"
    LOW_QUALITY = "low_quality"
    OTHER = "other"


class ReportStatus(str, Enum):
    """Status of a report."""
    PENDING = "pending"
    REVIEWING = "reviewing"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class ReportResolution(str, Enum):
    """Resolution actions for reports."""
    NO_ACTION = "no_action"
    WARNING_ISSUED = "warning_issued"
    CELL_QUARANTINED = "cell_quarantined"
    CELL_REMOVED = "cell_removed"
    USER_SUSPENDED = "user_suspended"
    USER_BANNED = "user_banned"


class QuarantineReason(str, Enum):
    """Reasons for quarantining a cell."""
    MALWARE_DETECTED = "malware_detected"
    CRITICAL_VULNERABILITY = "critical_vulnerability"
    COMMUNITY_REPORTS = "community_reports"
    AUTOMATED_SCAN = "automated_scan"
    MANUAL_REVIEW = "manual_review"
    LICENSE_VIOLATION = "license_violation"


class QuarantineStatus(str, Enum):
    """Status of quarantined cell."""
    ACTIVE = "active"  # Currently quarantined
    UNDER_REVIEW = "under_review"  # Being reviewed for release
    RELEASED = "released"  # Released from quarantine
    PERMANENTLY_REMOVED = "permanently_removed"


@dataclass
class Report:
    """A content report from the community."""
    id: str
    reporter_id: str
    cell_id: str
    cell_version: Optional[str] = None
    report_type: ReportType = ReportType.OTHER
    title: str = ""
    description: str = ""
    evidence: List[str] = field(default_factory=list)  # URLs, screenshots, etc.
    status: ReportStatus = ReportStatus.PENDING
    priority: int = 0  # 0-10, higher = more urgent
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    assigned_to: Optional[str] = None
    resolution: Optional[ReportResolution] = None
    resolution_notes: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "reporter_id": self.reporter_id,
            "cell_id": self.cell_id,
            "cell_version": self.cell_version,
            "report_type": self.report_type.value,
            "title": self.title,
            "description": self.description,
            "evidence": self.evidence,
            "status": self.status.value,
            "priority": self.priority,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "assigned_to": self.assigned_to,
            "resolution": self.resolution.value if self.resolution else None,
            "resolution_notes": self.resolution_notes,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolved_by": self.resolved_by,
        }


@dataclass
class QuarantineRecord:
    """Record of a quarantined cell."""
    id: str
    cell_id: str
    cell_name: str
    owner_id: str
    reason: QuarantineReason
    status: QuarantineStatus = QuarantineStatus.ACTIVE
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None  # Auto-release after period
    released_at: Optional[datetime] = None
    released_by: Optional[str] = None
    related_reports: List[str] = field(default_factory=list)  # Report IDs
    security_scan_id: Optional[str] = None
    notes: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        """Check if quarantine period has expired."""
        if self.expires_at:
            return datetime.now(timezone.utc) >= self.expires_at
        return False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "cell_id": self.cell_id,
            "cell_name": self.cell_name,
            "owner_id": self.owner_id,
            "reason": self.reason.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "released_at": self.released_at.isoformat() if self.released_at else None,
            "released_by": self.released_by,
            "related_reports": self.related_reports,
            "notes": self.notes,
        }


@dataclass
class TrustScore:
    """Trust score for a contributor."""
    user_id: str
    score: float = 100.0  # 0-100
    level: str = "trusted"  # new, trusted, verified, moderator
    total_cells: int = 0
    successful_cells: int = 0
    quarantined_cells: int = 0
    reports_received: int = 0
    reports_submitted: int = 0
    valid_reports: int = 0
    false_reports: int = 0
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def calculate_level(self) -> str:
        """Calculate trust level from score."""
        if self.score >= 90:
            return "verified"
        elif self.score >= 70:
            return "trusted"
        elif self.score >= 40:
            return "limited"
        elif self.score >= 20:
            return "restricted"
        return "suspended"


@dataclass
class ModerationAction:
    """Record of a moderation action taken."""
    id: str
    action_type: str  # quarantine, release, warning, ban, etc.
    moderator_id: str
    target_type: str  # cell, user, report
    target_id: str
    reason: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)


class ModerationQueue:
    """Priority queue for moderation tasks."""

    def __init__(self):
        self._queue: List[Report] = []
        self._lock = asyncio.Lock()

    async def push(self, report: Report) -> None:
        """Add report to queue with priority ordering."""
        async with self._lock:
            self._queue.append(report)
            # Sort by priority (descending) then by date (ascending)
            self._queue.sort(key=lambda r: (-r.priority, r.created_at))

    async def pop(self) -> Optional[Report]:
        """Get highest priority report."""
        async with self._lock:
            if self._queue:
                return self._queue.pop(0)
            return None

    async def peek(self) -> Optional[Report]:
        """View highest priority report without removing."""
        async with self._lock:
            return self._queue[0] if self._queue else None

    async def remove(self, report_id: str) -> bool:
        """Remove specific report from queue."""
        async with self._lock:
            for i, report in enumerate(self._queue):
                if report.id == report_id:
                    self._queue.pop(i)
                    return True
            return False

    @property
    def size(self) -> int:
        """Get queue size."""
        return len(self._queue)


class ModerationService:
    """
    Community moderation service for the Cell Colony marketplace.

    Handles:
    - Report submission and processing
    - Automated severity assessment
    - Quarantine management
    - Moderator workflow
    - Trust scoring
    - Appeals processing
    """

    # Auto-escalation thresholds
    CRITICAL_REPORT_TYPES = {ReportType.MALWARE, ReportType.VULNERABILITY}
    AUTO_QUARANTINE_THRESHOLD = 3  # Reports before auto-quarantine
    ESCALATION_THRESHOLD = 5  # Reports before escalation

    def __init__(
        self,
        event_bus: Optional[EventBus] = None,
        security_scanner: Optional[CellSecurityScanner] = None,
    ):
        self.logger = logger.bind(component="ModerationService")
        self.event_bus = event_bus
        self.security_scanner = security_scanner

        # Storage (in production, would use database)
        self._reports: Dict[str, Report] = {}
        self._quarantine: Dict[str, QuarantineRecord] = {}
        self._trust_scores: Dict[str, TrustScore] = {}
        self._actions: List[ModerationAction] = []
        self._reports_by_cell: Dict[str, List[str]] = {}  # cell_id -> [report_ids]

        # Queue for pending reports
        self._queue = ModerationQueue()

        # Callbacks for notifications
        self._notification_handlers: List[Callable[[str, Dict[str, Any]], None]] = []

        # Background task
        self._processing_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the moderation service."""
        self.logger.info("Starting Moderation Service")
        self._processing_task = asyncio.create_task(self._process_queue())

    async def stop(self) -> None:
        """Stop the moderation service."""
        if self._processing_task:
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass
        self.logger.info("Moderation Service stopped")

    # Report Management

    async def submit_report(
        self,
        reporter_id: str,
        cell_id: str,
        report_type: ReportType,
        title: str,
        description: str,
        evidence: Optional[List[str]] = None,
        cell_version: Optional[str] = None,
    ) -> Report:
        """
        Submit a new report.

        Args:
            reporter_id: ID of the user submitting report
            cell_id: ID of the reported cell
            report_type: Type of report
            title: Report title
            description: Detailed description
            evidence: List of evidence URLs
            cell_version: Specific version if applicable

        Returns:
            Created Report object
        """
        # Calculate priority based on type and reporter trust
        priority = self._calculate_priority(reporter_id, report_type)

        report = Report(
            id=str(uuid.uuid4()),
            reporter_id=reporter_id,
            cell_id=cell_id,
            cell_version=cell_version,
            report_type=report_type,
            title=title,
            description=description,
            evidence=evidence or [],
            priority=priority,
        )

        # Store report
        self._reports[report.id] = report
        if cell_id not in self._reports_by_cell:
            self._reports_by_cell[cell_id] = []
        self._reports_by_cell[cell_id].append(report.id)

        # Add to queue
        await self._queue.push(report)

        # Check for auto-escalation
        await self._check_auto_actions(report)

        # Update reporter's trust score
        await self._update_trust_score(reporter_id, "report_submitted")

        # Emit event
        if self.event_bus:
            await self.event_bus.publish(Event(
                type="REPORT_SUBMITTED",
                source="moderation",
                data=report.to_dict(),
            ))

        self.logger.info(
            "Report submitted",
            report_id=report.id,
            cell_id=cell_id,
            type=report_type.value,
            priority=priority,
        )

        return report

    async def get_report(self, report_id: str) -> Optional[Report]:
        """Get report by ID."""
        return self._reports.get(report_id)

    async def list_reports(
        self,
        cell_id: Optional[str] = None,
        status: Optional[ReportStatus] = None,
        report_type: Optional[ReportType] = None,
        limit: int = 50,
    ) -> List[Report]:
        """List reports with optional filters."""
        reports = list(self._reports.values())

        if cell_id:
            report_ids = self._reports_by_cell.get(cell_id, [])
            reports = [r for r in reports if r.id in report_ids]

        if status:
            reports = [r for r in reports if r.status == status]

        if report_type:
            reports = [r for r in reports if r.report_type == report_type]

        # Sort by priority and date
        reports.sort(key=lambda r: (-r.priority, r.created_at))

        return reports[:limit]

    async def update_report_status(
        self,
        report_id: str,
        status: ReportStatus,
        moderator_id: str,
        notes: Optional[str] = None,
    ) -> Optional[Report]:
        """Update report status."""
        report = self._reports.get(report_id)
        if not report:
            return None

        report.status = status
        report.updated_at = datetime.now(timezone.utc)
        report.assigned_to = moderator_id

        if status == ReportStatus.REVIEWING:
            await self._queue.remove(report_id)

        self.logger.info(
            "Report status updated",
            report_id=report_id,
            status=status.value,
            moderator=moderator_id,
        )

        return report

    async def resolve_report(
        self,
        report_id: str,
        resolution: ReportResolution,
        moderator_id: str,
        notes: str = "",
    ) -> Optional[Report]:
        """Resolve a report."""
        report = self._reports.get(report_id)
        if not report:
            return None

        report.status = ReportStatus.RESOLVED
        report.resolution = resolution
        report.resolution_notes = notes
        report.resolved_at = datetime.now(timezone.utc)
        report.resolved_by = moderator_id
        report.updated_at = datetime.now(timezone.utc)

        # Update reporter's trust based on resolution
        if resolution == ReportResolution.NO_ACTION:
            await self._update_trust_score(report.reporter_id, "report_dismissed")
        else:
            await self._update_trust_score(report.reporter_id, "report_validated")

        # Record action
        self._actions.append(ModerationAction(
            id=str(uuid.uuid4()),
            action_type="resolve_report",
            moderator_id=moderator_id,
            target_type="report",
            target_id=report_id,
            reason=notes,
            metadata={"resolution": resolution.value},
        ))

        # Emit event
        if self.event_bus:
            await self.event_bus.publish(Event(
                type="REPORT_RESOLVED",
                source="moderation",
                data=report.to_dict(),
            ))

        self.logger.info(
            "Report resolved",
            report_id=report_id,
            resolution=resolution.value,
            moderator=moderator_id,
        )

        return report

    # Quarantine Management

    async def quarantine_cell(
        self,
        cell_id: str,
        cell_name: str,
        owner_id: str,
        reason: QuarantineReason,
        moderator_id: Optional[str] = None,
        related_reports: Optional[List[str]] = None,
        duration_days: Optional[int] = None,
        notes: str = "",
    ) -> QuarantineRecord:
        """
        Quarantine a cell.

        Args:
            cell_id: ID of cell to quarantine
            cell_name: Name of cell
            owner_id: Owner's user ID
            reason: Reason for quarantine
            moderator_id: Moderator who initiated (None for automated)
            related_reports: Related report IDs
            duration_days: Auto-release after days (None = indefinite)
            notes: Additional notes

        Returns:
            QuarantineRecord
        """
        record = QuarantineRecord(
            id=str(uuid.uuid4()),
            cell_id=cell_id,
            cell_name=cell_name,
            owner_id=owner_id,
            reason=reason,
            related_reports=related_reports or [],
            notes=notes,
            expires_at=datetime.now(timezone.utc) + timedelta(days=duration_days) if duration_days else None,
        )

        self._quarantine[cell_id] = record

        # Update owner's trust score
        await self._update_trust_score(owner_id, "cell_quarantined")

        # Record action
        self._actions.append(ModerationAction(
            id=str(uuid.uuid4()),
            action_type="quarantine",
            moderator_id=moderator_id or "system",
            target_type="cell",
            target_id=cell_id,
            reason=reason.value,
            metadata={"notes": notes},
        ))

        # Notify owner
        await self._notify(
            "cell_quarantined",
            {
                "cell_id": cell_id,
                "cell_name": cell_name,
                "owner_id": owner_id,
                "reason": reason.value,
            },
        )

        # Emit event
        if self.event_bus:
            await self.event_bus.publish(Event(
                type="CELL_QUARANTINED",
                source="moderation",
                data=record.to_dict(),
            ))

        self.logger.warning(
            "Cell quarantined",
            cell_id=cell_id,
            reason=reason.value,
            moderator=moderator_id,
        )

        return record

    async def release_from_quarantine(
        self,
        cell_id: str,
        moderator_id: str,
        notes: str = "",
    ) -> Optional[QuarantineRecord]:
        """Release a cell from quarantine."""
        record = self._quarantine.get(cell_id)
        if not record:
            return None

        record.status = QuarantineStatus.RELEASED
        record.released_at = datetime.now(timezone.utc)
        record.released_by = moderator_id
        record.notes += f"\n[Released] {notes}"

        # Record action
        self._actions.append(ModerationAction(
            id=str(uuid.uuid4()),
            action_type="release",
            moderator_id=moderator_id,
            target_type="cell",
            target_id=cell_id,
            reason=notes,
        ))

        # Notify owner
        await self._notify(
            "cell_released",
            {
                "cell_id": cell_id,
                "cell_name": record.cell_name,
                "owner_id": record.owner_id,
            },
        )

        # Emit event
        if self.event_bus:
            await self.event_bus.publish(Event(
                type="CELL_RELEASED_FROM_QUARANTINE",
                source="moderation",
                data=record.to_dict(),
            ))

        self.logger.info(
            "Cell released from quarantine",
            cell_id=cell_id,
            moderator=moderator_id,
        )

        return record

    async def is_quarantined(self, cell_id: str) -> bool:
        """Check if a cell is quarantined."""
        record = self._quarantine.get(cell_id)
        if not record:
            return False
        return record.status == QuarantineStatus.ACTIVE

    async def get_quarantine_record(self, cell_id: str) -> Optional[QuarantineRecord]:
        """Get quarantine record for a cell."""
        return self._quarantine.get(cell_id)

    async def list_quarantined_cells(
        self,
        status: Optional[QuarantineStatus] = None,
        limit: int = 50,
    ) -> List[QuarantineRecord]:
        """List quarantined cells."""
        records = list(self._quarantine.values())

        if status:
            records = [r for r in records if r.status == status]

        records.sort(key=lambda r: r.created_at, reverse=True)
        return records[:limit]

    # Trust Score Management

    async def get_trust_score(self, user_id: str) -> TrustScore:
        """Get or create trust score for user."""
        if user_id not in self._trust_scores:
            self._trust_scores[user_id] = TrustScore(user_id=user_id)
        return self._trust_scores[user_id]

    async def _update_trust_score(self, user_id: str, event: str) -> None:
        """Update trust score based on event."""
        score = await self.get_trust_score(user_id)

        # Score adjustments based on events
        adjustments = {
            "report_submitted": 0,
            "report_validated": 2,
            "report_dismissed": -5,
            "cell_published": 1,
            "cell_quarantined": -20,
            "cell_removed": -30,
            "warning_received": -10,
        }

        adjustment = adjustments.get(event, 0)
        score.score = max(0, min(100, score.score + adjustment))
        score.level = score.calculate_level()
        score.last_updated = datetime.now(timezone.utc)

        if event == "report_submitted":
            score.reports_submitted += 1
        elif event == "report_validated":
            score.valid_reports += 1
        elif event == "report_dismissed":
            score.false_reports += 1
        elif event == "cell_quarantined":
            score.quarantined_cells += 1

    # Auto-moderation

    async def _check_auto_actions(self, report: Report) -> None:
        """Check if automatic actions should be taken."""
        # Critical reports trigger immediate scan
        if report.report_type in self.CRITICAL_REPORT_TYPES:
            report.status = ReportStatus.ESCALATED
            report.priority = max(report.priority, 8)

            if self.security_scanner:
                # Trigger security scan (would need cell path)
                self.logger.info(
                    "Critical report - security scan triggered",
                    cell_id=report.cell_id,
                )

        # Check report count for auto-quarantine
        cell_reports = self._reports_by_cell.get(report.cell_id, [])
        pending_reports = [
            self._reports[rid] for rid in cell_reports
            if self._reports.get(rid) and self._reports[rid].status == ReportStatus.PENDING
        ]

        if len(pending_reports) >= self.AUTO_QUARANTINE_THRESHOLD:
            # Get cell info (would come from database in production)
            await self.quarantine_cell(
                cell_id=report.cell_id,
                cell_name=f"cell-{report.cell_id[:8]}",
                owner_id="unknown",
                reason=QuarantineReason.COMMUNITY_REPORTS,
                related_reports=[r.id for r in pending_reports],
                notes=f"Auto-quarantined after {len(pending_reports)} reports",
            )

    def _calculate_priority(self, reporter_id: str, report_type: ReportType) -> int:
        """Calculate report priority based on type and reporter trust."""
        base_priority = {
            ReportType.MALWARE: 10,
            ReportType.VULNERABILITY: 9,
            ReportType.LICENSE_VIOLATION: 7,
            ReportType.COPYRIGHT: 6,
            ReportType.INAPPROPRIATE: 5,
            ReportType.SPAM: 4,
            ReportType.MISLEADING: 3,
            ReportType.LOW_QUALITY: 2,
            ReportType.OTHER: 1,
        }

        priority = base_priority.get(report_type, 1)

        # Adjust based on reporter trust
        if reporter_id in self._trust_scores:
            trust = self._trust_scores[reporter_id]
            if trust.level == "verified":
                priority += 2
            elif trust.level == "trusted":
                priority += 1
            elif trust.level == "restricted":
                priority -= 1
            elif trust.level == "suspended":
                priority -= 2

        return max(0, min(10, priority))

    # Background Processing

    async def _process_queue(self) -> None:
        """Background task to process moderation queue."""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute

                # Process expired quarantines
                for cell_id, record in list(self._quarantine.items()):
                    if record.is_expired and record.status == QuarantineStatus.ACTIVE:
                        await self.release_from_quarantine(
                            cell_id,
                            "system",
                            "Auto-released after expiration",
                        )

                # Log queue status
                if self._queue.size > 0:
                    self.logger.info(
                        "Moderation queue status",
                        pending=self._queue.size,
                    )

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("Queue processing error", error=str(e))

    # Notifications

    def register_notification_handler(
        self,
        handler: Callable[[str, Dict[str, Any]], None],
    ) -> None:
        """Register a notification handler."""
        self._notification_handlers.append(handler)

    async def _notify(self, event_type: str, data: Dict[str, Any]) -> None:
        """Send notification via registered handlers."""
        for handler in self._notification_handlers:
            try:
                handler(event_type, data)
            except Exception as e:
                self.logger.error("Notification handler failed", error=str(e))

    # Statistics

    def get_statistics(self) -> Dict[str, Any]:
        """Get moderation statistics."""
        reports = list(self._reports.values())
        quarantine = list(self._quarantine.values())

        return {
            "total_reports": len(reports),
            "pending_reports": len([r for r in reports if r.status == ReportStatus.PENDING]),
            "escalated_reports": len([r for r in reports if r.status == ReportStatus.ESCALATED]),
            "resolved_reports": len([r for r in reports if r.status == ReportStatus.RESOLVED]),
            "queue_size": self._queue.size,
            "active_quarantines": len([q for q in quarantine if q.status == QuarantineStatus.ACTIVE]),
            "total_quarantines": len(quarantine),
            "total_actions": len(self._actions),
        }
