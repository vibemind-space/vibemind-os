"""
Tenant models for multi-tenancy support.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class TenantRole(str, Enum):
    """Roles within a tenant."""
    OWNER = "owner"  # Full control, can delete tenant
    ADMIN = "admin"  # Manage members and settings
    DEVELOPER = "developer"  # Create and manage cells
    VIEWER = "viewer"  # Read-only access


class TenantPlan(str, Enum):
    """Subscription plans for tenants."""
    FREE = "free"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class Tenant(Base, TimestampMixin):
    """
    Multi-tenant organization.

    Tenants own cells and manage access through memberships.
    """
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Organization details
    logo_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    website_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    contact_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Billing and subscription
    plan: Mapped[TenantPlan] = mapped_column(
        SQLEnum(TenantPlan),
        default=TenantPlan.FREE,
        nullable=False,
    )
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    billing_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Limits based on plan
    max_cells: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    max_members: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    max_storage_gb: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Verification status
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    suspended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    suspension_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Settings stored as JSON
    settings: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # Relationships
    members: Mapped[List["TenantMember"]] = relationship(
        "TenantMember",
        back_populates="tenant",
        cascade="all, delete-orphan",
    )
    cells: Mapped[List["CellRegistry"]] = relationship(
        "CellRegistry",
        back_populates="tenant",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_tenants_slug", "slug"),
        Index("ix_tenants_is_active", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<Tenant(id={self.id}, name={self.name}, slug={self.slug})>"


class TenantMember(Base, TimestampMixin):
    """
    Membership linking users to tenants with specific roles.
    """
    __tablename__ = "tenant_members"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        nullable=False,  # References external auth user
    )

    # Role and permissions
    role: Mapped[TenantRole] = mapped_column(
        SQLEnum(TenantRole),
        default=TenantRole.VIEWER,
        nullable=False,
    )

    # User info (denormalized for convenience)
    user_email: Mapped[str] = mapped_column(String(255), nullable=False)
    user_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    user_avatar_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Invitation tracking
    invited_by: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        nullable=True,
    )
    invitation_token: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    invitation_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_active_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="members")

    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_tenant_member"),
        Index("ix_tenant_members_user_id", "user_id"),
        Index("ix_tenant_members_tenant_id", "tenant_id"),
        Index("ix_tenant_members_invitation_token", "invitation_token"),
    )

    def __repr__(self) -> str:
        return f"<TenantMember(tenant_id={self.tenant_id}, user_id={self.user_id}, role={self.role})>"

    @property
    def is_owner(self) -> bool:
        """Check if member is owner."""
        return self.role == TenantRole.OWNER

    @property
    def is_admin(self) -> bool:
        """Check if member is admin or higher."""
        return self.role in (TenantRole.OWNER, TenantRole.ADMIN)

    @property
    def can_edit(self) -> bool:
        """Check if member can edit resources."""
        return self.role in (TenantRole.OWNER, TenantRole.ADMIN, TenantRole.DEVELOPER)


# Avoid circular import
from .cell import CellRegistry
