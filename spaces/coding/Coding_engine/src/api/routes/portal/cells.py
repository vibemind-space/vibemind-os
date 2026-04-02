"""
Cell CRUD API endpoints.
"""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.portal import (
    CellRegistry,
    CellVersion,
    CellVisibility,
    ValidationStatus,
    CellCategory,
)
from src.models.portal.base import get_db

router = APIRouter(prefix="/cells", tags=["cells"])


# Pydantic schemas
class CellCreate(BaseModel):
    """Schema for creating a cell."""
    name: str = Field(..., min_length=1, max_length=100)
    namespace: str = Field(..., min_length=1, max_length=100)
    display_name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=10)
    short_description: Optional[str] = Field(None, max_length=500)
    category: CellCategory = CellCategory.OTHER
    tags: List[str] = Field(default_factory=list)
    visibility: CellVisibility = CellVisibility.PRIVATE
    license: Optional[str] = None
    repository_url: Optional[str] = None
    documentation_url: Optional[str] = None
    homepage_url: Optional[str] = None


class CellUpdate(BaseModel):
    """Schema for updating a cell."""
    display_name: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    short_description: Optional[str] = Field(None, max_length=500)
    category: Optional[CellCategory] = None
    tags: Optional[List[str]] = None
    visibility: Optional[CellVisibility] = None
    icon_url: Optional[str] = None
    banner_url: Optional[str] = None
    screenshots: Optional[List[str]] = None
    repository_url: Optional[str] = None
    documentation_url: Optional[str] = None
    homepage_url: Optional[str] = None
    support_url: Optional[str] = None
    license: Optional[str] = None
    config_schema: Optional[dict] = None


class CellResponse(BaseModel):
    """Schema for cell response."""
    id: str
    tenant_id: str
    name: str
    namespace: str
    display_name: str
    description: str
    short_description: Optional[str]
    category: CellCategory
    tags: List[str]
    visibility: CellVisibility
    is_published: bool
    is_verified: bool
    is_featured: bool
    is_deprecated: bool
    icon_url: Optional[str]
    latest_version: Optional[str]
    average_rating: float
    rating_count: int
    download_count: int
    install_count: int
    license: Optional[str]
    repository_url: Optional[str]
    documentation_url: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CellListResponse(BaseModel):
    """Schema for paginated cell list."""
    items: List[CellResponse]
    total: int
    page: int
    page_size: int
    pages: int


# Dependency for getting current tenant (placeholder)
async def get_current_tenant_id() -> str:
    """Get current tenant ID from auth context."""
    # In production, extract from JWT token
    return "00000000-0000-0000-0000-000000000000"


@router.post("", response_model=CellResponse, status_code=status.HTTP_201_CREATED)
async def create_cell(
    cell: CellCreate,
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """
    Create a new cell.
    """
    # Check if namespace already exists
    existing = await db.execute(
        select(CellRegistry).where(
            CellRegistry.tenant_id == tenant_id,
            CellRegistry.namespace == cell.namespace,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cell with namespace '{cell.namespace}' already exists",
        )

    # Create cell
    db_cell = CellRegistry(
        id=str(uuid4()),
        tenant_id=tenant_id,
        name=cell.name,
        namespace=cell.namespace,
        display_name=cell.display_name,
        description=cell.description,
        short_description=cell.short_description,
        category=cell.category,
        tags=cell.tags,
        keywords=cell.tags,  # Use tags as keywords initially
        visibility=cell.visibility,
        license=cell.license,
        repository_url=cell.repository_url,
        documentation_url=cell.documentation_url,
        homepage_url=cell.homepage_url,
    )

    db.add(db_cell)
    await db.flush()
    await db.refresh(db_cell)

    return db_cell


@router.get("", response_model=CellListResponse)
async def list_cells(
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: Optional[CellCategory] = None,
    visibility: Optional[CellVisibility] = None,
    is_published: Optional[bool] = None,
):
    """
    List cells for the current tenant.
    """
    query = select(CellRegistry).where(CellRegistry.tenant_id == tenant_id)

    if category:
        query = query.where(CellRegistry.category == category)
    if visibility:
        query = query.where(CellRegistry.visibility == visibility)
    if is_published is not None:
        query = query.where(CellRegistry.is_published == is_published)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    # Apply pagination
    query = query.offset((page - 1) * page_size).limit(page_size)
    query = query.order_by(CellRegistry.updated_at.desc())

    result = await db.execute(query)
    cells = result.scalars().all()

    return CellListResponse(
        items=cells,
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size,
    )


@router.get("/{cell_id}", response_model=CellResponse)
async def get_cell(
    cell_id: str,
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """
    Get cell by ID.
    """
    result = await db.execute(
        select(CellRegistry).where(
            CellRegistry.id == cell_id,
            CellRegistry.tenant_id == tenant_id,
        )
    )
    cell = result.scalar_one_or_none()

    if not cell:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cell not found",
        )

    return cell


@router.get("/namespace/{namespace}", response_model=CellResponse)
async def get_cell_by_namespace(
    namespace: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get cell by namespace (public endpoint).

    Only returns published and public cells.
    """
    result = await db.execute(
        select(CellRegistry).where(
            CellRegistry.namespace == namespace,
            CellRegistry.visibility == CellVisibility.PUBLIC,
            CellRegistry.is_published == True,
        )
    )
    cell = result.scalar_one_or_none()

    if not cell:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cell not found",
        )

    return cell


@router.patch("/{cell_id}", response_model=CellResponse)
async def update_cell(
    cell_id: str,
    cell_update: CellUpdate,
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """
    Update a cell.
    """
    result = await db.execute(
        select(CellRegistry).where(
            CellRegistry.id == cell_id,
            CellRegistry.tenant_id == tenant_id,
        )
    )
    cell = result.scalar_one_or_none()

    if not cell:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cell not found",
        )

    # Update fields
    update_data = cell_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(cell, field, value)

    cell.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(cell)

    return cell


@router.delete("/{cell_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cell(
    cell_id: str,
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """
    Delete a cell.
    """
    result = await db.execute(
        select(CellRegistry).where(
            CellRegistry.id == cell_id,
            CellRegistry.tenant_id == tenant_id,
        )
    )
    cell = result.scalar_one_or_none()

    if not cell:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cell not found",
        )

    await db.delete(cell)


@router.post("/{cell_id}/publish", response_model=CellResponse)
async def publish_cell(
    cell_id: str,
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """
    Publish a cell to the marketplace.

    Requires at least one validated version.
    """
    result = await db.execute(
        select(CellRegistry)
        .options(selectinload(CellRegistry.versions))
        .where(
            CellRegistry.id == cell_id,
            CellRegistry.tenant_id == tenant_id,
        )
    )
    cell = result.scalar_one_or_none()

    if not cell:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cell not found",
        )

    if cell.is_published:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cell is already published",
        )

    # Check for at least one validated version
    validated_versions = [
        v for v in cell.versions
        if v.validation_status == ValidationStatus.PASSED
    ]
    if not validated_versions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cell must have at least one validated version before publishing",
        )

    cell.is_published = True
    cell.published_at = datetime.now(timezone.utc)
    cell.visibility = CellVisibility.PUBLIC

    await db.flush()
    await db.refresh(cell)

    return cell


@router.post("/{cell_id}/unpublish", response_model=CellResponse)
async def unpublish_cell(
    cell_id: str,
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """
    Unpublish a cell from the marketplace.
    """
    result = await db.execute(
        select(CellRegistry).where(
            CellRegistry.id == cell_id,
            CellRegistry.tenant_id == tenant_id,
        )
    )
    cell = result.scalar_one_or_none()

    if not cell:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cell not found",
        )

    cell.is_published = False
    cell.visibility = CellVisibility.PRIVATE

    await db.flush()
    await db.refresh(cell)

    return cell


@router.post("/{cell_id}/deprecate", response_model=CellResponse)
async def deprecate_cell(
    cell_id: str,
    message: str = Query(..., min_length=10),
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """
    Mark a cell as deprecated.
    """
    result = await db.execute(
        select(CellRegistry).where(
            CellRegistry.id == cell_id,
            CellRegistry.tenant_id == tenant_id,
        )
    )
    cell = result.scalar_one_or_none()

    if not cell:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cell not found",
        )

    cell.is_deprecated = True
    cell.deprecation_message = message

    await db.flush()
    await db.refresh(cell)

    return cell
