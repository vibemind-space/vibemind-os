"""
Cell registry models for the marketplace.
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
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class CellVisibility(str, Enum):
    """Cell visibility levels."""
    PRIVATE = "private"  # Only visible to tenant
    INTERNAL = "internal"  # Visible to authenticated users
    PUBLIC = "public"  # Visible to everyone


class ValidationStatus(str, Enum):
    """Cell validation status."""
    PENDING = "pending"
    VALIDATING = "validating"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class CellCategory(str, Enum):
    """Cell categories for discovery."""
    API = "api"
    FRONTEND = "frontend"
    BACKEND = "backend"
    DATABASE = "database"
    AUTH = "auth"
    STORAGE = "storage"
    MESSAGING = "messaging"
    ANALYTICS = "analytics"
    AI_ML = "ai_ml"
    UTILITY = "utility"
    OTHER = "other"


class CellRegistry(Base, TimestampMixin):
    """
    Cell registry entry in the marketplace.

    Cells can be published, versioned, and installed by other tenants.
    """
    __tablename__ = "cells"

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

    # Identification
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    namespace: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g., "@myorg/auth-service"
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    short_description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Categorization
    category: Mapped[CellCategory] = mapped_column(
        SQLEnum(CellCategory),
        default=CellCategory.OTHER,
        nullable=False,
    )
    tags: Mapped[List[str]] = mapped_column(ARRAY(String(50)), default=list, nullable=False)
    keywords: Mapped[List[str]] = mapped_column(ARRAY(String(50)), default=list, nullable=False)

    # Visibility and status
    visibility: Mapped[CellVisibility] = mapped_column(
        SQLEnum(CellVisibility),
        default=CellVisibility.PRIVATE,
        nullable=False,
    )
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_deprecated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deprecation_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Media
    icon_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    banner_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    screenshots: Mapped[List[str]] = mapped_column(ARRAY(String(500)), default=list, nullable=False)

    # Links
    repository_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    documentation_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    homepage_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    support_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Metadata
    license: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    author_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    author_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Current version tracking
    latest_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    latest_stable_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Ratings and stats (denormalized for performance)
    average_rating: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    rating_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    download_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    install_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Security
    security_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_security_scan: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    has_vulnerabilities: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Configuration schema
    config_schema: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="cells")
    versions: Mapped[List["CellVersion"]] = relationship(
        "CellVersion",
        back_populates="cell",
        cascade="all, delete-orphan",
        order_by="desc(CellVersion.created_at)",
    )
    reviews: Mapped[List["CellReview"]] = relationship(
        "CellReview",
        back_populates="cell",
        cascade="all, delete-orphan",
    )
    dependencies: Mapped[List["CellDependency"]] = relationship(
        "CellDependency",
        back_populates="cell",
        foreign_keys="CellDependency.cell_id",
        cascade="all, delete-orphan",
    )
    dependents: Mapped[List["CellDependency"]] = relationship(
        "CellDependency",
        back_populates="depends_on_cell",
        foreign_keys="CellDependency.depends_on_cell_id",
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "namespace", name="uq_cell_namespace"),
        Index("ix_cells_namespace", "namespace"),
        Index("ix_cells_visibility", "visibility"),
        Index("ix_cells_category", "category"),
        Index("ix_cells_is_published", "is_published"),
        Index("ix_cells_tags", "tags", postgresql_using="gin"),
        Index("ix_cells_download_count", "download_count", postgresql_ops={"download_count": "DESC"}),
        Index("ix_cells_average_rating", "average_rating", postgresql_ops={"average_rating": "DESC"}),
    )

    def __repr__(self) -> str:
        return f"<CellRegistry(id={self.id}, namespace={self.namespace}, version={self.latest_version})>"


class CellVersion(Base, TimestampMixin):
    """
    Versioned artifact of a cell.

    Each version contains the actual deployable artifact.
    """
    __tablename__ = "cell_versions"

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

    # Version info
    version: Mapped[str] = mapped_column(String(50), nullable=False)  # semver
    is_prerelease: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_latest: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_stable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Release notes
    changelog: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    release_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Artifact storage
    artifact_url: Mapped[str] = mapped_column(String(500), nullable=False)
    artifact_size: Mapped[int] = mapped_column(Integer, nullable=False)  # bytes
    artifact_checksum: Mapped[str] = mapped_column(String(128), nullable=False)  # SHA-256
    artifact_type: Mapped[str] = mapped_column(String(50), default="tar.gz", nullable=False)

    # Container image (if applicable)
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    image_digest: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    image_signature: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Cosign signature

    # Validation
    validation_status: Mapped[ValidationStatus] = mapped_column(
        SQLEnum(ValidationStatus),
        default=ValidationStatus.PENDING,
        nullable=False,
    )
    validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    validation_errors: Mapped[List[str]] = mapped_column(ARRAY(Text), default=list, nullable=False)

    # Security scan results
    sbom_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    vulnerabilities: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    security_scan_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Requirements
    min_k8s_version: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    required_resources: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # Download stats
    download_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Publishing
    published_by: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)

    # Deprecation
    is_yanked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    yanked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    yank_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    cell: Mapped["CellRegistry"] = relationship("CellRegistry", back_populates="versions")

    __table_args__ = (
        UniqueConstraint("cell_id", "version", name="uq_cell_version"),
        Index("ix_cell_versions_cell_id", "cell_id"),
        Index("ix_cell_versions_version", "version"),
        Index("ix_cell_versions_is_latest", "is_latest"),
        Index("ix_cell_versions_validation_status", "validation_status"),
    )

    def __repr__(self) -> str:
        return f"<CellVersion(cell_id={self.cell_id}, version={self.version})>"


class CellDependency(Base, TimestampMixin):
    """
    Dependency relationship between cells.
    """
    __tablename__ = "cell_dependencies"

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
    depends_on_cell_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("cells.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Version constraint
    version_constraint: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g., "^1.0.0", ">=2.0 <3.0"
    is_optional: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_dev_dependency: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    cell: Mapped["CellRegistry"] = relationship(
        "CellRegistry",
        back_populates="dependencies",
        foreign_keys=[cell_id],
    )
    depends_on_cell: Mapped["CellRegistry"] = relationship(
        "CellRegistry",
        back_populates="dependents",
        foreign_keys=[depends_on_cell_id],
    )

    __table_args__ = (
        UniqueConstraint("cell_id", "depends_on_cell_id", name="uq_cell_dependency"),
        Index("ix_cell_dependencies_cell_id", "cell_id"),
        Index("ix_cell_dependencies_depends_on", "depends_on_cell_id"),
    )

    def __repr__(self) -> str:
        return f"<CellDependency(cell={self.cell_id}, depends_on={self.depends_on_cell_id})>"


# Avoid circular import
from .tenant import Tenant
from .review import CellReview
