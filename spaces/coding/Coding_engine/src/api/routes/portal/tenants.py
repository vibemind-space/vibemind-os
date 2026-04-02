"""
Tenant management API endpoints.
"""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.portal import Tenant, TenantMember, TenantRole, TenantPlan
from src.models.portal.base import get_db

router = APIRouter(prefix="/tenants", tags=["tenants"])


class TenantCreate(BaseModel):
    """Schema for creating a tenant."""
    name: str = Field(..., min_length=2, max_length=255)
    slug: str = Field(..., min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")
    description: Optional[str] = None


class TenantUpdate(BaseModel):
    """Schema for updating a tenant."""
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    description: Optional[str] = None
    logo_url: Optional[str] = None
    website_url: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    settings: Optional[dict] = None


class TenantResponse(BaseModel):
    """Schema for tenant response."""
    id: str
    name: str
    slug: str
    description: Optional[str]
    logo_url: Optional[str]
    website_url: Optional[str]
    plan: TenantPlan
    max_cells: int
    max_members: int
    is_verified: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MemberCreate(BaseModel):
    """Schema for inviting a member."""
    email: EmailStr
    role: TenantRole = TenantRole.VIEWER
    name: Optional[str] = None


class MemberUpdate(BaseModel):
    """Schema for updating a member."""
    role: TenantRole


class MemberResponse(BaseModel):
    """Schema for member response."""
    id: str
    tenant_id: str
    user_id: str
    user_email: str
    user_name: Optional[str]
    user_avatar_url: Optional[str]
    role: TenantRole
    is_active: bool
    accepted_at: Optional[datetime]
    last_active_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


async def get_current_user_id() -> str:
    return "00000000-0000-0000-0000-000000000001"


async def get_current_user_email() -> str:
    return "demo@example.com"


@router.post("", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    tenant: TenantCreate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
    user_email: str = Depends(get_current_user_email),
):
    """Create a new tenant organization."""
    # Check slug availability
    existing = await db.execute(
        select(Tenant).where(Tenant.slug == tenant.slug)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Slug '{tenant.slug}' is already taken",
        )

    # Create tenant
    db_tenant = Tenant(
        id=str(uuid4()),
        name=tenant.name,
        slug=tenant.slug,
        description=tenant.description,
    )
    db.add(db_tenant)
    await db.flush()

    # Add creator as owner
    owner = TenantMember(
        id=str(uuid4()),
        tenant_id=db_tenant.id,
        user_id=user_id,
        user_email=user_email,
        role=TenantRole.OWNER,
        accepted_at=datetime.now(timezone.utc),
    )
    db.add(owner)

    await db.flush()
    await db.refresh(db_tenant)
    return db_tenant


@router.get("", response_model=List[TenantResponse])
async def list_my_tenants(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """List tenants the current user belongs to."""
    result = await db.execute(
        select(Tenant)
        .join(TenantMember)
        .where(
            TenantMember.user_id == user_id,
            TenantMember.is_active == True,
            Tenant.is_active == True,
        )
    )
    return result.scalars().all()


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Get tenant details."""
    # Verify user has access
    member = await db.execute(
        select(TenantMember).where(
            TenantMember.tenant_id == tenant_id,
            TenantMember.user_id == user_id,
            TenantMember.is_active == True,
        )
    )
    if not member.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Tenant not found")

    result = await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return tenant


@router.patch("/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: str,
    tenant_update: TenantUpdate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Update tenant (admin only)."""
    # Verify user is admin
    member = await db.execute(
        select(TenantMember).where(
            TenantMember.tenant_id == tenant_id,
            TenantMember.user_id == user_id,
            TenantMember.role.in_([TenantRole.OWNER, TenantRole.ADMIN]),
        )
    )
    if not member.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    result = await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    update_data = tenant_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(tenant, field, value)

    await db.flush()
    await db.refresh(tenant)
    return tenant


@router.delete("/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tenant(
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Delete tenant (owner only)."""
    member = await db.execute(
        select(TenantMember).where(
            TenantMember.tenant_id == tenant_id,
            TenantMember.user_id == user_id,
            TenantMember.role == TenantRole.OWNER,
        )
    )
    if not member.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Only owner can delete tenant")

    result = await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    await db.delete(tenant)


# Member management
@router.get("/{tenant_id}/members", response_model=List[MemberResponse])
async def list_members(
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """List tenant members."""
    # Verify access
    access = await db.execute(
        select(TenantMember).where(
            TenantMember.tenant_id == tenant_id,
            TenantMember.user_id == user_id,
        )
    )
    if not access.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Tenant not found")

    result = await db.execute(
        select(TenantMember).where(TenantMember.tenant_id == tenant_id)
    )
    return result.scalars().all()


@router.post("/{tenant_id}/members", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
async def invite_member(
    tenant_id: str,
    member: MemberCreate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Invite a new member (admin only)."""
    # Verify admin
    admin = await db.execute(
        select(TenantMember).where(
            TenantMember.tenant_id == tenant_id,
            TenantMember.user_id == user_id,
            TenantMember.role.in_([TenantRole.OWNER, TenantRole.ADMIN]),
        )
    )
    if not admin.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    # Check limits
    tenant_result = await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )
    tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    count_result = await db.execute(
        select(func.count()).where(TenantMember.tenant_id == tenant_id)
    )
    member_count = count_result.scalar() or 0
    if member_count >= tenant.max_members:
        raise HTTPException(
            status_code=400,
            detail=f"Member limit ({tenant.max_members}) reached",
        )

    # Create invitation
    invitation_token = str(uuid4())
    db_member = TenantMember(
        id=str(uuid4()),
        tenant_id=tenant_id,
        user_id=str(uuid4()),  # Placeholder until they accept
        user_email=member.email,
        user_name=member.name,
        role=member.role,
        invited_by=user_id,
        invitation_token=invitation_token,
        invitation_sent_at=datetime.now(timezone.utc),
    )
    db.add(db_member)

    await db.flush()
    await db.refresh(db_member)

    # TODO: Send invitation email

    return db_member


@router.patch("/{tenant_id}/members/{member_id}", response_model=MemberResponse)
async def update_member(
    tenant_id: str,
    member_id: str,
    member_update: MemberUpdate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Update member role (admin only)."""
    # Verify admin
    admin = await db.execute(
        select(TenantMember).where(
            TenantMember.tenant_id == tenant_id,
            TenantMember.user_id == user_id,
            TenantMember.role.in_([TenantRole.OWNER, TenantRole.ADMIN]),
        )
    )
    if not admin.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    result = await db.execute(
        select(TenantMember).where(
            TenantMember.id == member_id,
            TenantMember.tenant_id == tenant_id,
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    # Can't change owner's role
    if member.role == TenantRole.OWNER:
        raise HTTPException(
            status_code=400,
            detail="Cannot change owner's role",
        )

    member.role = member_update.role
    await db.flush()
    await db.refresh(member)
    return member


@router.delete("/{tenant_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    tenant_id: str,
    member_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Remove a member (admin only, can't remove owner)."""
    # Verify admin
    admin = await db.execute(
        select(TenantMember).where(
            TenantMember.tenant_id == tenant_id,
            TenantMember.user_id == user_id,
            TenantMember.role.in_([TenantRole.OWNER, TenantRole.ADMIN]),
        )
    )
    if not admin.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    result = await db.execute(
        select(TenantMember).where(
            TenantMember.id == member_id,
            TenantMember.tenant_id == tenant_id,
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    if member.role == TenantRole.OWNER:
        raise HTTPException(
            status_code=400,
            detail="Cannot remove owner",
        )

    await db.delete(member)
