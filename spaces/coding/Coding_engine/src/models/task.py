"""Task model - represents a single coding task for an agent."""
import enum
from typing import TYPE_CHECKING, Optional
from sqlalchemy import String, Text, Integer, Float, Enum, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base

if TYPE_CHECKING:
    from src.models.job import Job


class TaskStatus(str, enum.Enum):
    """Task execution status."""
    PENDING = "pending"
    SCHEDULED = "scheduled"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"  # Waiting on dependencies
    CANCELLED = "cancelled"
    # New statuses for event-based orchestration
    TO_VERIFY = "to_verify"      # Completed, waiting for verification
    VERIFIED = "verified"        # Verification passed
    FIXING = "fixing"            # Auto-fix in progress
    PERMANENT_FAIL = "permanent_fail"  # Max retries reached, needs manual intervention


class TaskType(str, enum.Enum):
    """Type of task / agent to use."""
    FRONTEND = "frontend"
    BACKEND = "backend"
    TESTING = "testing"
    SECURITY = "security"
    DEVOPS = "devops"
    DOCUMENTATION = "documentation"
    GENERAL = "general"


class Task(Base):
    """
    Task represents a single coding unit assigned to an agent.

    A task:
    - Is derived from one or more requirements
    - Has dependencies on other tasks (from DAG)
    - Is executed by a specific agent type
    - Produces code artifacts
    """

    __tablename__ = "tasks"

    # Foreign key
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Task identity
    task_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    requirement_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    # Task type and agent assignment
    task_type: Mapped[TaskType] = mapped_column(
        Enum(TaskType),
        default=TaskType.GENERAL,
        nullable=False,
    )

    # Task content
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)

    # Dependencies (task_ids that must complete first)
    depends_on: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    depth_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Execution status
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus),
        default=TaskStatus.PENDING,
        nullable=False,
        index=True,
    )
    status_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Execution metadata
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    execution_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Agent response
    agent_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    generated_files: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Cost tracking
    cost_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Relationships
    job: Mapped["Job"] = relationship("Job", back_populates="tasks")

    def can_execute(self, completed_tasks: set[str]) -> bool:
        """Check if all dependencies are satisfied."""
        return all(dep in completed_tasks for dep in self.depends_on)

    def __repr__(self) -> str:
        return f"<Task(id={self.id}, task_id='{self.task_id}', type={self.task_type}, status={self.status})>"
