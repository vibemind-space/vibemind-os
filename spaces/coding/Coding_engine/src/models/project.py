"""Project model - represents a coding project workspace."""
import enum
from typing import TYPE_CHECKING, Optional
from sqlalchemy import String, Text, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base

if TYPE_CHECKING:
    from src.models.job import Job
    from src.models.artifact import Artifact


class ProjectStatus(str, enum.Enum):
    """Project lifecycle status."""
    CREATED = "created"
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"
    FAILED = "failed"


class Project(Base):
    """
    Project represents a coding workspace where AI artifacts are generated.

    A project contains:
    - Multiple jobs (requirement processing runs)
    - Generated artifacts (code, configs, docs)
    - Git repository for version control
    """

    __tablename__ = "projects"

    # Basic info
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus),
        default=ProjectStatus.CREATED,
        nullable=False,
    )

    # Git repository
    git_repo_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    git_branch: Mapped[str] = mapped_column(String(255), default="main", nullable=False)

    # Configuration
    config_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    jobs: Mapped[list["Job"]] = relationship(
        "Job",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    artifacts: Mapped[list["Artifact"]] = relationship(
        "Artifact",
        back_populates="project",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Project(id={self.id}, name='{self.name}', status={self.status})>"
