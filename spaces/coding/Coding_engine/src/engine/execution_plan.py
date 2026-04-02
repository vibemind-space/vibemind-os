"""
Execution Plan Data Structures for Intelligent Chunk Planning.

These datastructures enable LLM-based requirement chunking with:
- Service grouping (auth, user, payment, etc.)
- Dependency DAG analysis
- Complexity scoring
- Wave-based parallel execution
- Load balancing across workers

Reference: Plan file - "LLM-basierter Chunk Planner für Phase 2"
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from enum import Enum


class ComplexityLevel(str, Enum):
    """Complexity levels for requirements/chunks."""
    SIMPLE = "simple"      # 1-2 files, no external APIs, standard CRUD
    MEDIUM = "medium"      # 3-5 files, simple logic, local state
    COMPLEX = "complex"    # 5+ files, external APIs, complex logic, security


class ServiceDomain(str, Enum):
    """Common service domains for grouping requirements."""
    AUTH = "auth"           # Login, Logout, Register, Password Reset
    USER = "user"           # Profile, Settings, CRUD operations
    PAYMENT = "payment"     # Checkout, History, Refunds
    DASHBOARD = "dashboard" # Layout, Widgets, Charts, Analytics
    SETTINGS = "settings"   # Theme, Language, Preferences
    NOTIFICATIONS = "notifications"  # Push, Email, In-app
    SEARCH = "search"       # Basic search, Filters, Advanced
    REPORTS = "reports"     # Export, Analytics, PDF/CSV
    ADMIN = "admin"         # User management, System config
    API = "api"             # External integrations
    STORAGE = "storage"     # File upload, Media management
    OTHER = "other"         # Uncategorized


@dataclass
class ServiceGroup:
    """
    Grouping of requirements by service/domain.

    Enables related features to be generated together for coherence.
    """
    service_name: str                    # Domain name (auth, user, etc.)
    requirements: list[str] = field(default_factory=list)  # Requirement IDs
    estimated_files: list[str] = field(default_factory=list)  # Affected file paths
    complexity: ComplexityLevel = ComplexityLevel.MEDIUM
    depends_on: list[str] = field(default_factory=list)  # Other service names
    estimated_minutes: int = 5           # Time estimate for this group

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "service_name": self.service_name,
            "requirements": self.requirements,
            "estimated_files": self.estimated_files,
            "complexity": self.complexity.value if isinstance(self.complexity, ComplexityLevel) else self.complexity,
            "depends_on": self.depends_on,
            "estimated_minutes": self.estimated_minutes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ServiceGroup":
        """Create from dictionary."""
        complexity = data.get("complexity", "medium")
        if isinstance(complexity, str):
            complexity = ComplexityLevel(complexity)
        return cls(
            service_name=data["service_name"],
            requirements=data.get("requirements", []),
            estimated_files=data.get("estimated_files", []),
            complexity=complexity,
            depends_on=data.get("depends_on", []),
            estimated_minutes=data.get("estimated_minutes", 5),
        )


@dataclass
class RequirementChunk:
    """
    A work package for a single worker.

    Contains requirements that should be generated together.
    """
    chunk_id: str                        # Unique identifier (e.g., "chunk_001")
    requirements: list[str] = field(default_factory=list)  # Requirement IDs
    service_group: str = ""              # Parent service domain
    complexity: ComplexityLevel = ComplexityLevel.MEDIUM
    depends_on_chunks: list[str] = field(default_factory=list)  # Chunk dependencies
    estimated_minutes: int = 5
    worker_id: Optional[int] = None      # Assigned worker (set during scheduling)
    wave_id: Optional[int] = None        # Execution wave (set during scheduling)

    # Runtime tracking
    status: str = "pending"              # pending, running, completed, failed
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    actual_minutes: Optional[float] = None
    error_message: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "chunk_id": self.chunk_id,
            "requirements": self.requirements,
            "service_group": self.service_group,
            "complexity": self.complexity.value if isinstance(self.complexity, ComplexityLevel) else self.complexity,
            "depends_on_chunks": self.depends_on_chunks,
            "estimated_minutes": self.estimated_minutes,
            "worker_id": self.worker_id,
            "wave_id": self.wave_id,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "actual_minutes": self.actual_minutes,
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RequirementChunk":
        """Create from dictionary."""
        complexity = data.get("complexity", "medium")
        if isinstance(complexity, str):
            complexity = ComplexityLevel(complexity)
        return cls(
            chunk_id=data["chunk_id"],
            requirements=data.get("requirements", []),
            service_group=data.get("service_group", ""),
            complexity=complexity,
            depends_on_chunks=data.get("depends_on_chunks", []),
            estimated_minutes=data.get("estimated_minutes", 5),
            worker_id=data.get("worker_id"),
            wave_id=data.get("wave_id"),
            status=data.get("status", "pending"),
        )


@dataclass
class WorkerAssignment:
    """
    Assignment of chunks to a specific worker.

    Tracks sequential work packages for load balancing.
    """
    worker_id: int
    chunks: list[RequirementChunk] = field(default_factory=list)
    estimated_duration_minutes: int = 0

    # Runtime tracking
    current_chunk_index: int = 0
    status: str = "idle"                 # idle, working, completed
    total_completed: int = 0
    total_failed: int = 0

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "worker_id": self.worker_id,
            "chunks": [c.to_dict() for c in self.chunks],
            "estimated_duration_minutes": self.estimated_duration_minutes,
            "current_chunk_index": self.current_chunk_index,
            "status": self.status,
            "total_completed": self.total_completed,
            "total_failed": self.total_failed,
        }

    def get_next_chunk(self) -> Optional[RequirementChunk]:
        """Get next pending chunk for this worker."""
        for chunk in self.chunks:
            if chunk.status == "pending":
                return chunk
        return None

    def calculate_load(self) -> int:
        """Calculate total estimated minutes for this worker."""
        return sum(c.estimated_minutes for c in self.chunks)


@dataclass
class Wave:
    """
    A parallel execution wave.

    All chunks in a wave can run concurrently.
    Next wave starts only when current wave completes.
    """
    wave_id: int
    chunks: list[str] = field(default_factory=list)  # Chunk IDs
    blocked_by: list[str] = field(default_factory=list)  # Chunk IDs that must complete first
    estimated_minutes: int = 0           # Longest chunk determines wave duration

    # Runtime tracking
    status: str = "pending"              # pending, running, completed
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "wave_id": self.wave_id,
            "chunks": self.chunks,
            "blocked_by": self.blocked_by,
            "estimated_minutes": self.estimated_minutes,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


@dataclass
class ExecutionPlan:
    """
    Complete execution plan for requirement generation.

    Contains waves, worker assignments, and optimization metrics.
    """
    # Plan structure
    waves: list[Wave] = field(default_factory=list)
    worker_assignments: list[WorkerAssignment] = field(default_factory=list)
    chunks: list[RequirementChunk] = field(default_factory=list)
    service_groups: list[ServiceGroup] = field(default_factory=list)

    # Metrics
    total_requirements: int = 0
    total_chunks: int = 0
    total_waves: int = 0
    total_workers: int = 0
    total_estimated_minutes: int = 0
    sequential_estimated_minutes: int = 0  # If done one-by-one
    parallelization_factor: float = 1.0   # Speedup vs sequential

    # LLM reasoning
    reasoning: str = ""                   # Explanation of planning decisions

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    requirements_hash: str = ""           # For cache invalidation

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "waves": [w.to_dict() for w in self.waves],
            "worker_assignments": [wa.to_dict() for wa in self.worker_assignments],
            "chunks": [c.to_dict() for c in self.chunks],
            "service_groups": [sg.to_dict() for sg in self.service_groups],
            "total_requirements": self.total_requirements,
            "total_chunks": self.total_chunks,
            "total_waves": self.total_waves,
            "total_workers": self.total_workers,
            "total_estimated_minutes": self.total_estimated_minutes,
            "sequential_estimated_minutes": self.sequential_estimated_minutes,
            "parallelization_factor": self.parallelization_factor,
            "reasoning": self.reasoning,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "requirements_hash": self.requirements_hash,
        }

    def get_wave(self, wave_id: int) -> Optional[Wave]:
        """Get wave by ID."""
        for wave in self.waves:
            if wave.wave_id == wave_id:
                return wave
        return None

    def get_chunk(self, chunk_id: str) -> Optional[RequirementChunk]:
        """Get chunk by ID."""
        for chunk in self.chunks:
            if chunk.chunk_id == chunk_id:
                return chunk
        return None

    def get_ready_chunks(self) -> list[RequirementChunk]:
        """Get chunks that are ready to execute (dependencies satisfied)."""
        completed_chunks = {c.chunk_id for c in self.chunks if c.status == "completed"}
        ready = []
        for chunk in self.chunks:
            if chunk.status == "pending":
                # Check if all dependencies are completed
                deps_satisfied = all(dep in completed_chunks for dep in chunk.depends_on_chunks)
                if deps_satisfied:
                    ready.append(chunk)
        return ready

    def get_progress(self) -> dict:
        """Get execution progress metrics."""
        completed = sum(1 for c in self.chunks if c.status == "completed")
        running = sum(1 for c in self.chunks if c.status == "running")
        failed = sum(1 for c in self.chunks if c.status == "failed")
        pending = sum(1 for c in self.chunks if c.status == "pending")

        return {
            "completed": completed,
            "running": running,
            "failed": failed,
            "pending": pending,
            "total": len(self.chunks),
            "percent_complete": (completed / len(self.chunks) * 100) if self.chunks else 0,
        }

    def print_summary(self) -> str:
        """Generate human-readable summary."""
        lines = [
            "╔═══════════════════════════════════════════════════════════════════╗",
            f"║  EXECUTION PLAN - {self.total_requirements} Requirements, {self.total_workers} Workers".ljust(68) + "║",
            "╠═══════════════════════════════════════════════════════════════════╣",
        ]

        for wave in self.waves:
            lines.append(f"║  Wave {wave.wave_id} ({wave.estimated_minutes} Min):".ljust(68) + "║")
            for chunk_id in wave.chunks:
                chunk = self.get_chunk(chunk_id)
                if chunk:
                    worker_str = f"Worker {chunk.worker_id}" if chunk.worker_id else "Unassigned"
                    req_str = ", ".join(chunk.requirements[:3])
                    if len(chunk.requirements) > 3:
                        req_str += f"... (+{len(chunk.requirements)-3})"
                    complexity_str = f"({chunk.complexity.value})" if isinstance(chunk.complexity, ComplexityLevel) else f"({chunk.complexity})"
                    line = f"    {worker_str}: [{chunk.service_group}] {req_str} {complexity_str}"
                    lines.append("║" + line.ljust(67) + "║")
            lines.append("║" + " " * 67 + "║")

        lines.append("╠═══════════════════════════════════════════════════════════════════╣")
        speedup_str = f"{self.parallelization_factor:.1f}x"
        lines.append(f"║  Total: {self.total_estimated_minutes} Min | Sequential: {self.sequential_estimated_minutes} Min | Speedup: {speedup_str}".ljust(68) + "║")
        lines.append("╚═══════════════════════════════════════════════════════════════════╝")

        return "\n".join(lines)


# Time estimates per complexity level (in minutes)
DEFAULT_TIME_ESTIMATES = {
    ComplexityLevel.SIMPLE: 3,
    ComplexityLevel.MEDIUM: 5,
    ComplexityLevel.COMPLEX: 10,
}


def estimate_chunk_time(chunk: RequirementChunk) -> int:
    """Estimate execution time for a chunk based on complexity."""
    base_time = DEFAULT_TIME_ESTIMATES.get(chunk.complexity, 5)
    # Add time for each additional requirement beyond the first
    additional_reqs = max(0, len(chunk.requirements) - 1)
    return base_time + (additional_reqs * 2)


def calculate_wave_time(wave: Wave, chunks: list[RequirementChunk]) -> int:
    """Calculate wave duration (longest chunk in wave)."""
    wave_chunks = [c for c in chunks if c.chunk_id in wave.chunks]
    if not wave_chunks:
        return 0
    return max(c.estimated_minutes for c in wave_chunks)


@dataclass
class ChunkResult:
    """
    Result of parallel code + test generation for a chunk.

    Produced by execute_chunk_with_tests() - contains both code and test
    generation results along with validation status.
    """
    chunk_id: str
    requirements: list[str] = field(default_factory=list)

    # Code generation results
    code_files: list[str] = field(default_factory=list)
    code_success: bool = False

    # Test generation results
    test_files: list[str] = field(default_factory=list)
    test_success: bool = False

    # Validation results
    tests_passed: int = 0
    tests_failed: int = 0
    validation_errors: list[str] = field(default_factory=list)

    # Mock violations (NO MOCKS policy)
    mock_violations: list[str] = field(default_factory=list)

    # Merge status
    ready_for_merge: bool = False

    # Timing
    code_gen_time_ms: int = 0
    test_gen_time_ms: int = 0
    validation_time_ms: int = 0
    total_time_ms: int = 0

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "chunk_id": self.chunk_id,
            "requirements": self.requirements,
            "code_files": self.code_files,
            "code_success": self.code_success,
            "test_files": self.test_files,
            "test_success": self.test_success,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "validation_errors": self.validation_errors,
            "mock_violations": self.mock_violations,
            "ready_for_merge": self.ready_for_merge,
            "code_gen_time_ms": self.code_gen_time_ms,
            "test_gen_time_ms": self.test_gen_time_ms,
            "validation_time_ms": self.validation_time_ms,
            "total_time_ms": self.total_time_ms,
        }

    @property
    def is_valid(self) -> bool:
        """Check if chunk passed all validation."""
        return (
            self.code_success
            and self.test_success
            and self.tests_failed == 0
            and len(self.mock_violations) == 0
            and len(self.validation_errors) == 0
        )
