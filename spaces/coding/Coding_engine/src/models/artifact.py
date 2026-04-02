"""Artifact model - represents generated code and deployment artifacts."""
import enum
from typing import TYPE_CHECKING, Optional
from sqlalchemy import String, Text, Integer, Enum, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base

if TYPE_CHECKING:
    from src.models.project import Project


class ArtifactType(str, enum.Enum):
    """Type of generated artifact."""
    SOURCE_CODE = "source_code"
    TEST_CODE = "test_code"
    CONFIG = "config"
    DOCKERFILE = "dockerfile"
    K8S_MANIFEST = "k8s_manifest"
    CI_PIPELINE = "ci_pipeline"
    DOCUMENTATION = "documentation"
    DATABASE_MIGRATION = "database_migration"
    API_SPEC = "api_spec"
    DOCKER_IMAGE = "docker_image"
    DEPLOYMENT = "deployment"
    OTHER = "other"


class Artifact(Base):
    """
    Artifact represents a generated output from the coding engine.

    An artifact can be:
    - Source code files
    - Configuration files
    - Docker images
    - Kubernetes manifests
    - Documentation
    - Deployed services
    """

    __tablename__ = "artifacts"

    # Foreign key
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    task_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Artifact identity
    artifact_type: Mapped[ArtifactType] = mapped_column(
        Enum(ArtifactType),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # File info (for file-based artifacts)
    file_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Content (for small artifacts stored inline)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Versioning
    version: Mapped[str] = mapped_column(String(64), default="1.0.0", nullable=False)
    git_commit: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    git_branch: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Deployment info (for deployed artifacts)
    deployment_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    deployment_status: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Extra metadata (renamed from 'metadata' which is reserved in SQLAlchemy)
    extra_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="artifacts")

    def __repr__(self) -> str:
        return f"<Artifact(id={self.id}, type={self.artifact_type}, name='{self.name}')>"
