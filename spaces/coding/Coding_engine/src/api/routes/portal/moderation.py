"""
Moderation API endpoints for reports and quarantine.
"""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.portal import (
    CellRegistry,
    CellReport,
    CellQuarantine,
    ReportType,
    ReportStatus,
    ReportSeverity,
    QuarantineReason,
)
from src.models.portal.base import get_db

router = APIRouter(prefix="/moderation", tags=["moderation"])


class ReportCreate(BaseModel):
    """Schema for creating a report."""
    cell_id: str
    cell_version: Optional[str] = None
    report_type: ReportType
    severity: ReportSeverity = ReportSeverity.MEDIUM
    title: str = Field(..., min_length=5, max_length=200)
    description: str = Field(..., min_length=20, max_length=5000)
    evidence_urls: List[str] = Field(default_factory=list)
    reproduction_steps: Optional[str] = None
    cve_id: Optional[str] = None
    is_anonymous: bool = False


class ReportUpdate(BaseModel):
    """Schema for updating a report (moderators)."""
    status: Optional[ReportStatus] = None
    severity: Optional[ReportSeverity] = None
    priority: Optional[int] = None
    internal_notes: Optional[str] = None
    resolution_notes: Optional[str] = None


class ReportResponse(BaseModel):
    """Schema for report response."""
    id: str
    cell_id: str
    cell_version: Optional[str]
    report_type: ReportType
    severity: ReportSeverity
    title: str
    description: str
    status: ReportStatus
    priority: int
    reporter_email: Optional[str]
    is_anonymous: bool
    assigned_to: Optional[str]
    cell_quarantined: bool
    version_yanked: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class QuarantineCreate(BaseModel):
    """Schema for quarantining a cell."""
    cell_id: str
    reason: QuarantineReason
    severity: ReportSeverity
    description: str = Field(..., min_length=20)
    affected_versions: List[str] = Field(default_factory=list)
    all_versions_affected: bool = False
    public_notice: Optional[str] = None
    show_public_notice: bool = False


class QuarantineResponse(BaseModel):
    """Schema for quarantine response."""
    id: str
    cell_id: str
    reason: QuarantineReason
    severity: ReportSeverity
    description: str
    affected_versions: List[str]
    all_versions_affected: bool
    is_active: bool
    downloads_blocked: bool
    search_hidden: bool
    is_released: bool
    released_at: Optional[datetime]
    release_notes: Optional[str]
    public_notice: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


async def get_current_user_id() -> str:
    return "00000000-0000-0000-0000-000000000001"


async def get_current_user_email() -> str:
    return "demo@example.com"


# Report endpoints (public)
@router.post("/reports", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
async def submit_report(
    report: ReportCreate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
    user_email: str = Depends(get_current_user_email),
):
    """Submit a report about a cell."""
    # Verify cell exists
    cell_result = await db.execute(
        select(CellRegistry).where(CellRegistry.id == report.cell_id)
    )
    if not cell_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Cell not found")

    db_report = CellReport(
        id=str(uuid4()),
        cell_id=report.cell_id,
        cell_version=report.cell_version,
        reporter_user_id=None if report.is_anonymous else user_id,
        reporter_email=None if report.is_anonymous else user_email,
        is_anonymous=report.is_anonymous,
        report_type=report.report_type,
        severity=report.severity,
        title=report.title,
        description=report.description,
        evidence_urls=report.evidence_urls,
        reproduction_steps=report.reproduction_steps,
        cve_id=report.cve_id,
    )

    # Auto-escalate critical reports
    if report.severity == ReportSeverity.CRITICAL:
        db_report.priority = 100
        db_report.status = ReportStatus.ESCALATED

    db.add(db_report)
    await db.flush()
    await db.refresh(db_report)

    return db_report


@router.get("/reports/mine", response_model=List[ReportResponse])
async def list_my_reports(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List reports submitted by current user."""
    result = await db.execute(
        select(CellReport)
        .where(CellReport.reporter_user_id == user_id)
        .order_by(CellReport.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return result.scalars().all()


# Moderation endpoints (admin only)
@router.get("/reports", response_model=List[ReportResponse])
async def list_reports(
    db: AsyncSession = Depends(get_db),
    status: Optional[ReportStatus] = None,
    severity: Optional[ReportSeverity] = None,
    report_type: Optional[ReportType] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    """List all reports (moderators only)."""
    # TODO: Add moderator authentication check

    query = select(CellReport)

    if status:
        query = query.where(CellReport.status == status)
    if severity:
        query = query.where(CellReport.severity == severity)
    if report_type:
        query = query.where(CellReport.report_type == report_type)

    query = query.order_by(
        CellReport.priority.desc(),
        CellReport.created_at.desc(),
    ).offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/reports/{report_id}", response_model=ReportResponse)
async def get_report(
    report_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get report details (moderators only)."""
    result = await db.execute(
        select(CellReport).where(CellReport.id == report_id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.patch("/reports/{report_id}", response_model=ReportResponse)
async def update_report(
    report_id: str,
    report_update: ReportUpdate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Update report status (moderators only)."""
    result = await db.execute(
        select(CellReport).where(CellReport.id == report_id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    update_data = report_update.model_dump(exclude_unset=True)

    # Handle status transitions
    if "status" in update_data:
        new_status = update_data["status"]
        if new_status == ReportStatus.INVESTIGATING and not report.assigned_to:
            report.assigned_to = user_id
            report.assigned_at = datetime.now(timezone.utc)
        elif new_status == ReportStatus.RESOLVED:
            report.resolved_by = user_id
            report.resolved_at = datetime.now(timezone.utc)

    for field, value in update_data.items():
        setattr(report, field, value)

    await db.flush()
    await db.refresh(report)
    return report


# Quarantine endpoints
@router.post("/quarantine", response_model=QuarantineResponse, status_code=status.HTTP_201_CREATED)
async def quarantine_cell(
    quarantine: QuarantineCreate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Quarantine a cell (moderators only)."""
    # Verify cell exists
    cell_result = await db.execute(
        select(CellRegistry).where(CellRegistry.id == quarantine.cell_id)
    )
    cell = cell_result.scalar_one_or_none()
    if not cell:
        raise HTTPException(status_code=404, detail="Cell not found")

    # Check if already quarantined
    existing = await db.execute(
        select(CellQuarantine).where(
            CellQuarantine.cell_id == quarantine.cell_id,
            CellQuarantine.is_active == True,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail="Cell is already quarantined",
        )

    db_quarantine = CellQuarantine(
        id=str(uuid4()),
        cell_id=quarantine.cell_id,
        reason=quarantine.reason,
        severity=quarantine.severity,
        description=quarantine.description,
        affected_versions=quarantine.affected_versions,
        all_versions_affected=quarantine.all_versions_affected,
        quarantined_by=user_id,
        public_notice=quarantine.public_notice,
        show_public_notice=quarantine.show_public_notice,
    )

    # Add initial audit log entry
    db_quarantine.add_audit_entry(
        action="quarantine_created",
        user_id=user_id,
        details={"reason": quarantine.reason.value},
    )

    db.add(db_quarantine)

    # Update cell visibility
    cell.is_published = False  # Hide from marketplace

    await db.flush()
    await db.refresh(db_quarantine)
    return db_quarantine


@router.get("/quarantine", response_model=List[QuarantineResponse])
async def list_quarantined_cells(
    db: AsyncSession = Depends(get_db),
    is_active: bool = Query(True),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    """List quarantined cells (moderators only)."""
    query = select(CellQuarantine)

    if is_active is not None:
        query = query.where(CellQuarantine.is_active == is_active)

    query = query.order_by(
        CellQuarantine.severity.desc(),
        CellQuarantine.created_at.desc(),
    ).offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/quarantine/{quarantine_id}", response_model=QuarantineResponse)
async def get_quarantine(
    quarantine_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get quarantine details."""
    result = await db.execute(
        select(CellQuarantine)
        .options(selectinload(CellQuarantine.reports))
        .where(CellQuarantine.id == quarantine_id)
    )
    quarantine = result.scalar_one_or_none()
    if not quarantine:
        raise HTTPException(status_code=404, detail="Quarantine not found")
    return quarantine


@router.post("/quarantine/{quarantine_id}/release", response_model=QuarantineResponse)
async def release_quarantine(
    quarantine_id: str,
    release_notes: str = Query(..., min_length=20),
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Release a cell from quarantine (moderators only)."""
    result = await db.execute(
        select(CellQuarantine).where(
            CellQuarantine.id == quarantine_id,
            CellQuarantine.is_active == True,
        )
    )
    quarantine = result.scalar_one_or_none()
    if not quarantine:
        raise HTTPException(status_code=404, detail="Active quarantine not found")

    quarantine.is_active = False
    quarantine.is_released = True
    quarantine.released_by = user_id
    quarantine.released_at = datetime.now(timezone.utc)
    quarantine.release_notes = release_notes
    quarantine.downloads_blocked = False
    quarantine.search_hidden = False

    quarantine.add_audit_entry(
        action="quarantine_released",
        user_id=user_id,
        details={"release_notes": release_notes},
    )

    # Re-enable cell
    cell_result = await db.execute(
        select(CellRegistry).where(CellRegistry.id == quarantine.cell_id)
    )
    cell = cell_result.scalar_one()
    cell.is_published = True

    await db.flush()
    await db.refresh(quarantine)
    return quarantine


# Stats endpoint
@router.get("/stats")
async def get_moderation_stats(
    db: AsyncSession = Depends(get_db),
):
    """Get moderation statistics."""
    # Report stats by status
    status_result = await db.execute(
        select(CellReport.status, func.count())
        .group_by(CellReport.status)
    )
    status_counts = {s.value: c for s, c in status_result.all()}

    # Report stats by type
    type_result = await db.execute(
        select(CellReport.report_type, func.count())
        .group_by(CellReport.report_type)
    )
    type_counts = {t.value: c for t, c in type_result.all()}

    # Active quarantines
    quarantine_result = await db.execute(
        select(func.count()).where(CellQuarantine.is_active == True)
    )
    active_quarantines = quarantine_result.scalar() or 0

    return {
        "reports_by_status": status_counts,
        "reports_by_type": type_counts,
        "active_quarantines": active_quarantines,
        "pending_reports": status_counts.get("pending", 0),
        "escalated_reports": status_counts.get("escalated", 0),
    }
