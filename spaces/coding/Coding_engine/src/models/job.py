"""Job model - represents a requirements processing run."""
import enum
from typing import TYPE_CHECKING, Optional
from sqlalchemy import String, Text, Integer, Enum, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base

if TYPE_CHECKING:
    from src.models.project import Project
    from src.models.task import Task


class JobStatus(str, enum.Enum):
    """Job processing status."""
    PENDING = "pending"
    PARSING = "parsing"
    SCHEDULING = "scheduling"
    RUNNING = "running"
    ASSEMBLING = "assembling"
    VALIDATING = "validating"
    DEPLOYING = "deploying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Job(Base):
    """
    Job represents a single requirements processing run.

    A job:
    - Takes a requirements JSON as input
    - Parses it into a DAG of tasks
    - Orchestrates agent execution
    - Assembles generated code
    """

    __tablename__ = "jobs"

    # Foreign key
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Status
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus),
        default=JobStatus.PENDING,
        nullable=False,
    )
    status_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Input
    requirements_json: Mapped[str] = mapped_column(Text, nullable=False)
    source_file: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # DAG metadata
    total_requirements: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tasks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    dag_nodes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    dag_edges: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Progress tracking
    tasks_completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tasks_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Result metadata
    result_summary: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error_log: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="jobs")
    tasks: Mapped[list["Task"]] = relationship(
        "Task",
        back_populates="job",
        cascade="all, delete-orphan",
    )

    @property
    def progress_percent(self) -> float:
        """Calculate job progress percentage."""
        if self.total_tasks == 0:
            return 0.0
        return (self.tasks_completed / self.total_tasks) * 100

    def __repr__(self) -> str:
        return f"<Job(id={self.id}, project_id={self.project_id}, status={self.status})>"
