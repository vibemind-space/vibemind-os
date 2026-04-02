"""
Cell version management API endpoints.
"""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.portal import CellRegistry, CellVersion, ValidationStatus
from src.models.portal.base import get_db

router = APIRouter(prefix="/cells/{cell_id}/versions", tags=["versions"])


class VersionCreate(BaseModel):
    """Schema for creating a version."""
    version: str = Field(..., pattern=r"^\d+\.\d+\.\d+(-[\w.]+)?(\+[\w.]+)?$")
    changelog: Optional[str] = None
    release_notes: Optional[str] = None
    is_prerelease: bool = False


class VersionResponse(BaseModel):
    """Schema for version response."""
    id: str
    cell_id: str
    version: str
    is_prerelease: bool
    is_latest: bool
    is_stable: bool
    changelog: Optional[str]
    release_notes: Optional[str]
    artifact_url: str
    artifact_size: int
    artifact_checksum: str
    validation_status: ValidationStatus
    validated_at: Optional[datetime]
    download_count: int
    is_yanked: bool
    created_at: datetime

    class Config:
        from_attributes = True


class VersionListResponse(BaseModel):
    """Schema for version list."""
    items: List[VersionResponse]
    total: int


async def get_current_tenant_id() -> str:
    return "00000000-0000-0000-0000-000000000000"


@router.get("", response_model=VersionListResponse)
async def list_versions(
    cell_id: str,
    db: AsyncSession = Depends(get_db),
    include_prereleases: bool = Query(True),
    include_yanked: bool = Query(False),
):
    """List all versions of a cell."""
    query = select(CellVersion).where(CellVersion.cell_id == cell_id)

    if not include_prereleases:
        query = query.where(CellVersion.is_prerelease == False)
    if not include_yanked:
        query = query.where(CellVersion.is_yanked == False)

    query = query.order_by(CellVersion.created_at.desc())
    result = await db.execute(query)
    versions = result.scalars().all()

    return VersionListResponse(items=versions, total=len(versions))


@router.post("", response_model=VersionResponse, status_code=status.HTTP_201_CREATED)
async def create_version(
    cell_id: str,
    version_data: VersionCreate,
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Create a new version."""
    # Verify cell exists and belongs to tenant
    cell_result = await db.execute(
        select(CellRegistry).where(
            CellRegistry.id == cell_id,
            CellRegistry.tenant_id == tenant_id,
        )
    )
    cell = cell_result.scalar_one_or_none()
    if not cell:
        raise HTTPException(status_code=404, detail="Cell not found")

    # Check version doesn't exist
    existing = await db.execute(
        select(CellVersion).where(
            CellVersion.cell_id == cell_id,
            CellVersion.version == version_data.version,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"Version {version_data.version} already exists",
        )

    # Create version (artifact would be uploaded separately)
    db_version = CellVersion(
        id=str(uuid4()),
        cell_id=cell_id,
        version=version_data.version,
        changelog=version_data.changelog,
        release_notes=version_data.release_notes,
        is_prerelease=version_data.is_prerelease,
        is_stable=not version_data.is_prerelease,
        artifact_url="pending",  # Set after artifact upload
        artifact_size=0,
        artifact_checksum="pending",
        validation_status=ValidationStatus.PENDING,
    )

    # Update latest flags
    await db.execute(
        update(CellVersion)
        .where(CellVersion.cell_id == cell_id, CellVersion.is_latest == True)
        .values(is_latest=False)
    )
    db_version.is_latest = True

    db.add(db_version)
    await db.flush()

    # Update cell's latest version
    cell.latest_version = version_data.version
    if not version_data.is_prerelease:
        cell.latest_stable_version = version_data.version

    await db.refresh(db_version)
    return db_version


@router.get("/{version}", response_model=VersionResponse)
async def get_version(
    cell_id: str,
    version: str,
    db: AsyncSession = Depends(get_db),
):
    """Get a specific version."""
    result = await db.execute(
        select(CellVersion).where(
            CellVersion.cell_id == cell_id,
            CellVersion.version == version,
        )
    )
    db_version = result.scalar_one_or_none()

    if not db_version:
        raise HTTPException(status_code=404, detail="Version not found")

    return db_version


@router.post("/{version}/yank", response_model=VersionResponse)
async def yank_version(
    cell_id: str,
    version: str,
    reason: str = Query(..., min_length=10),
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """
    Yank a version (soft delete).

    Yanked versions are hidden from listings but still downloadable
    for existing users.
    """
    result = await db.execute(
        select(CellVersion)
        .join(CellRegistry)
        .where(
            CellVersion.cell_id == cell_id,
            CellVersion.version == version,
            CellRegistry.tenant_id == tenant_id,
        )
    )
    db_version = result.scalar_one_or_none()

    if not db_version:
        raise HTTPException(status_code=404, detail="Version not found")

    db_version.is_yanked = True
    db_version.yanked_at = datetime.now(timezone.utc)
    db_version.yank_reason = reason

    await db.flush()
    await db.refresh(db_version)
    return db_version


@router.delete("/{version}/yank", response_model=VersionResponse)
async def unyank_version(
    cell_id: str,
    version: str,
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Unyank a version."""
    result = await db.execute(
        select(CellVersion)
        .join(CellRegistry)
        .where(
            CellVersion.cell_id == cell_id,
            CellVersion.version == version,
            CellRegistry.tenant_id == tenant_id,
        )
    )
    db_version = result.scalar_one_or_none()

    if not db_version:
        raise HTTPException(status_code=404, detail="Version not found")

    db_version.is_yanked = False
    db_version.yanked_at = None
    db_version.yank_reason = None

    await db.flush()
    await db.refresh(db_version)
    return db_version


@router.post("/{version}/download")
async def record_download(
    cell_id: str,
    version: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Record a download and return download URL.
    """
    result = await db.execute(
        select(CellVersion).where(
            CellVersion.cell_id == cell_id,
            CellVersion.version == version,
            CellVersion.is_yanked == False,
        )
    )
    db_version = result.scalar_one_or_none()

    if not db_version:
        raise HTTPException(status_code=404, detail="Version not found")

    # Increment counters
    db_version.download_count += 1
    await db.execute(
        update(CellRegistry)
        .where(CellRegistry.id == cell_id)
        .values(download_count=CellRegistry.download_count + 1)
    )

    await db.flush()

    return {
        "download_url": db_version.artifact_url,
        "checksum": db_version.artifact_checksum,
        "size": db_version.artifact_size,
    }
