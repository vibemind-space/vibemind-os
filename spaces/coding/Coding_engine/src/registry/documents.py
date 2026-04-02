"""
Documents - Dataclasses for the different document types.

Each document type carries structured data for inter-agent communication.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, Any
import json

from .document_types import DocumentType, DocumentStatus


@dataclass
class VisualIssue:
    """A visual issue found during E2E testing."""
    severity: str  # "critical", "major", "minor"
    description: str
    element: Optional[str] = None  # CSS selector or identifier
    expected: Optional[str] = None
    actual: Optional[str] = None
    screenshot_ref: Optional[str] = None  # Reference to screenshot showing issue

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "VisualIssue":
        return cls(**data)


@dataclass
class SuggestedFix:
    """A suggested fix for an issue."""
    id: str
    priority: int
    description: str
    file: str
    action: str  # "create", "modify", "delete"
    code_hint: Optional[str] = None  # Suggested code or approach

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SuggestedFix":
        return cls(**data)


@dataclass
class PlannedFix:
    """A planned fix to be implemented."""
    id: str
    description: str
    responding_to_fix_id: Optional[str] = None  # Links to SuggestedFix
    approach: Optional[str] = None
    estimated_complexity: str = "medium"  # "low", "medium", "high"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PlannedFix":
        return cls(**data)


@dataclass
class FileChange:
    """A file change made or planned."""
    action: str  # "created", "modified", "deleted"
    lines_added: int = 0
    lines_removed: int = 0
    summary: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "FileChange":
        return cls(**data)


@dataclass
class TestCase:
    """A test case specification."""
    id: str
    name: str
    description: str
    test_type: str = "e2e"  # "unit", "integration", "e2e"
    priority: int = 1
    steps: list[str] = field(default_factory=list)
    expected_result: Optional[str] = None
    target_element: Optional[str] = None  # For E2E tests

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TestCase":
        return cls(**data)


@dataclass
class TestResults:
    """Results from running tests."""
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    duration_seconds: float = 0.0
    failures: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TestResults":
        return cls(**data)


@dataclass
class DocumentationTask:
    """A documentation task to be completed."""
    id: str
    task_type: str  # "readme", "claudemd", "jsdoc", "api_docs"
    target_path: str
    scope: list[str] = field(default_factory=list)  # Files/dirs to document
    priority: int = 1
    description: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DocumentationTask":
        return cls(**data)


@dataclass
class CleanupTask:
    """A cleanup task for unused/dead code."""
    id: str
    file_path: str
    reason: str  # "unused_import", "dead_code", "orphan_file"
    confidence: float  # 0.0-1.0, higher = safer to delete
    references_found: int = 0
    last_modified: Optional[str] = None  # ISO format string
    size_bytes: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CleanupTask":
        return cls(**data)


@dataclass
class RefactorTask:
    """A refactoring task for large/complex files."""
    id: str
    file_path: str
    reason: str  # "too_large", "high_complexity", "duplicate_code"
    current_lines: int
    target_lines: int = 500  # Target after split
    suggested_splits: list[str] = field(default_factory=list)  # Suggested new file names
    complexity_score: Optional[float] = None
    description: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "RefactorTask":
        return cls(**data)


class BaseDocument:
    """Base interface for all documents - provides common utilities."""

    @property
    def document_type(self) -> DocumentType:
        """Return the type of this document. Override in subclasses."""
        raise NotImplementedError

    def to_dict(self) -> dict:
        """Serialize to dictionary. Override in subclasses."""
        raise NotImplementedError

    @classmethod
    def from_dict(cls, data: dict) -> "BaseDocument":
        """Deserialize from dictionary. Override in subclasses."""
        raise NotImplementedError

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=2, default=str)

    @classmethod
    def from_json(cls, json_str: str) -> "BaseDocument":
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(json_str))


@dataclass
class DebugReport(BaseDocument):
    """
    Debug report from PlaywrightE2EAgent.

    Contains visual analysis results, errors found, and suggested fixes
    for the GeneratorAgent to consume.
    """
    # Required fields first
    id: str
    timestamp: datetime

    # Fields with defaults
    source_agent: str = field(default="PlaywrightE2E")
    status: DocumentStatus = field(default=DocumentStatus.PENDING)

    # Visual analysis results
    screenshots: list[str] = field(default_factory=list)
    visual_issues: list[VisualIssue] = field(default_factory=list)
    console_errors: list[str] = field(default_factory=list)

    # Actionable suggestions
    suggested_fixes: list[SuggestedFix] = field(default_factory=list)
    priority_order: list[str] = field(default_factory=list)  # Fix IDs in order

    # Context for generator
    affected_files: list[str] = field(default_factory=list)
    root_cause_hypothesis: Optional[str] = None
    debugging_steps: list[str] = field(default_factory=list)

    # Optional readiness assessment
    readiness_score: Optional[int] = None  # 0-100
    test_url: Optional[str] = None

    @property
    def document_type(self) -> DocumentType:
        return DocumentType.DEBUG_REPORT

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.document_type.value,
            "timestamp": self.timestamp.isoformat(),
            "source_agent": self.source_agent,
            "status": self.status.value,
            "screenshots": self.screenshots,
            "visual_issues": [vi.to_dict() for vi in self.visual_issues],
            "console_errors": self.console_errors,
            "suggested_fixes": [sf.to_dict() for sf in self.suggested_fixes],
            "priority_order": self.priority_order,
            "affected_files": self.affected_files,
            "root_cause_hypothesis": self.root_cause_hypothesis,
            "debugging_steps": self.debugging_steps,
            "readiness_score": self.readiness_score,
            "test_url": self.test_url,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DebugReport":
        return cls(
            id=data["id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            source_agent=data.get("source_agent", "PlaywrightE2E"),
            status=DocumentStatus(data.get("status", "pending")),
            screenshots=data.get("screenshots", []),
            visual_issues=[VisualIssue.from_dict(vi) for vi in data.get("visual_issues", [])],
            console_errors=data.get("console_errors", []),
            suggested_fixes=[SuggestedFix.from_dict(sf) for sf in data.get("suggested_fixes", [])],
            priority_order=data.get("priority_order", []),
            affected_files=data.get("affected_files", []),
            root_cause_hypothesis=data.get("root_cause_hypothesis"),
            debugging_steps=data.get("debugging_steps", []),
            readiness_score=data.get("readiness_score"),
            test_url=data.get("test_url"),
        )


@dataclass
class ImplementationPlan(BaseDocument):
    """
    Implementation plan from GeneratorAgent.

    Contains planned fixes, file changes, and test focus areas
    for the TesterTeamAgent to consume.
    """
    # Required fields first
    id: str
    timestamp: datetime

    # Fields with defaults
    source_agent: str = field(default="Generator")
    status: DocumentStatus = field(default=DocumentStatus.PENDING)

    # What triggered this plan
    responding_to: Optional[str] = None  # DEBUG_REPORT id

    # Planned fixes
    fixes_planned: list[PlannedFix] = field(default_factory=list)

    # File changes made
    file_manifest: dict[str, FileChange] = field(default_factory=dict)  # path -> change

    # For tester
    test_focus_areas: list[str] = field(default_factory=list)
    expected_outcomes: list[str] = field(default_factory=list)
    verification_steps: list[str] = field(default_factory=list)

    # Summary
    summary: Optional[str] = None
    total_files_changed: int = 0

    @property
    def document_type(self) -> DocumentType:
        return DocumentType.IMPLEMENTATION_PLAN

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.document_type.value,
            "timestamp": self.timestamp.isoformat(),
            "source_agent": self.source_agent,
            "status": self.status.value,
            "responding_to": self.responding_to,
            "fixes_planned": [fp.to_dict() for fp in self.fixes_planned],
            "file_manifest": {k: v.to_dict() for k, v in self.file_manifest.items()},
            "test_focus_areas": self.test_focus_areas,
            "expected_outcomes": self.expected_outcomes,
            "verification_steps": self.verification_steps,
            "summary": self.summary,
            "total_files_changed": self.total_files_changed,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ImplementationPlan":
        file_manifest = {}
        for k, v in data.get("file_manifest", {}).items():
            file_manifest[k] = FileChange.from_dict(v)

        return cls(
            id=data["id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            source_agent=data.get("source_agent", "Generator"),
            status=DocumentStatus(data.get("status", "pending")),
            responding_to=data.get("responding_to"),
            fixes_planned=[PlannedFix.from_dict(fp) for fp in data.get("fixes_planned", [])],
            file_manifest=file_manifest,
            test_focus_areas=data.get("test_focus_areas", []),
            expected_outcomes=data.get("expected_outcomes", []),
            verification_steps=data.get("verification_steps", []),
            summary=data.get("summary"),
            total_files_changed=data.get("total_files_changed", 0),
        )


@dataclass
class TestSpec(BaseDocument):
    """
    Test specification from TesterTeamAgent.

    Contains test cases to run based on implementation plan,
    and results after execution.
    """
    # Required fields first
    id: str
    timestamp: datetime

    # Fields with defaults
    source_agent: str = field(default="TesterTeam")
    status: DocumentStatus = field(default=DocumentStatus.PENDING)

    # What triggered this spec
    responding_to: Optional[str] = None  # IMPLEMENTATION_PLAN id

    # Test cases
    test_cases: list[TestCase] = field(default_factory=list)
    coverage_targets: list[str] = field(default_factory=list)

    # Results (filled after execution)
    results: Optional[TestResults] = None
    executed_at: Optional[datetime] = None

    @property
    def document_type(self) -> DocumentType:
        return DocumentType.TEST_SPEC

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.document_type.value,
            "timestamp": self.timestamp.isoformat(),
            "source_agent": self.source_agent,
            "status": self.status.value,
            "responding_to": self.responding_to,
            "test_cases": [tc.to_dict() for tc in self.test_cases],
            "coverage_targets": self.coverage_targets,
            "results": self.results.to_dict() if self.results else None,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TestSpec":
        results = None
        if data.get("results"):
            results = TestResults.from_dict(data["results"])

        executed_at = None
        if data.get("executed_at"):
            executed_at = datetime.fromisoformat(data["executed_at"])

        return cls(
            id=data["id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            source_agent=data.get("source_agent", "TesterTeam"),
            status=DocumentStatus(data.get("status", "pending")),
            responding_to=data.get("responding_to"),
            test_cases=[TestCase.from_dict(tc) for tc in data.get("test_cases", [])],
            coverage_targets=data.get("coverage_targets", []),
            results=results,
            executed_at=executed_at,
        )


@dataclass
class QualityReport(BaseDocument):
    """
    Quality report from CodeQualityAgent.

    Contains documentation tasks, cleanup tasks for unused files,
    and refactoring tasks for large files. Generator consumes this
    to implement improvements.
    """
    # Required fields first
    id: str
    timestamp: datetime

    # Fields with defaults
    source_agent: str = field(default="CodeQuality")
    status: DocumentStatus = field(default=DocumentStatus.PENDING)

    # What triggered this report
    responding_to: Optional[str] = None  # TEST_SPEC id

    # Tasks discovered
    documentation_tasks: list[DocumentationTask] = field(default_factory=list)
    cleanup_tasks: list[CleanupTask] = field(default_factory=list)
    refactor_tasks: list[RefactorTask] = field(default_factory=list)

    # Summary statistics
    total_files_analyzed: int = 0
    unused_files_found: int = 0
    large_files_found: int = 0
    documentation_gaps: int = 0

    # Flag indicating if Generator needs to act
    requires_action: bool = False

    @property
    def document_type(self) -> DocumentType:
        return DocumentType.QUALITY_REPORT

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.document_type.value,
            "timestamp": self.timestamp.isoformat(),
            "source_agent": self.source_agent,
            "status": self.status.value,
            "responding_to": self.responding_to,
            "documentation_tasks": [dt.to_dict() for dt in self.documentation_tasks],
            "cleanup_tasks": [ct.to_dict() for ct in self.cleanup_tasks],
            "refactor_tasks": [rt.to_dict() for rt in self.refactor_tasks],
            "total_files_analyzed": self.total_files_analyzed,
            "unused_files_found": self.unused_files_found,
            "large_files_found": self.large_files_found,
            "documentation_gaps": self.documentation_gaps,
            "requires_action": self.requires_action,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "QualityReport":
        return cls(
            id=data["id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            source_agent=data.get("source_agent", "CodeQuality"),
            status=DocumentStatus(data.get("status", "pending")),
            responding_to=data.get("responding_to"),
            documentation_tasks=[DocumentationTask.from_dict(dt) for dt in data.get("documentation_tasks", [])],
            cleanup_tasks=[CleanupTask.from_dict(ct) for ct in data.get("cleanup_tasks", [])],
            refactor_tasks=[RefactorTask.from_dict(rt) for rt in data.get("refactor_tasks", [])],
            total_files_analyzed=data.get("total_files_analyzed", 0),
            unused_files_found=data.get("unused_files_found", 0),
            large_files_found=data.get("large_files_found", 0),
            documentation_gaps=data.get("documentation_gaps", 0),
            requires_action=data.get("requires_action", False),
        )


# Factory for creating documents from type
DOCUMENT_CLASSES = {
    DocumentType.DEBUG_REPORT: DebugReport,
    DocumentType.IMPLEMENTATION_PLAN: ImplementationPlan,
    DocumentType.TEST_SPEC: TestSpec,
    DocumentType.QUALITY_REPORT: QualityReport,
}


def document_from_dict(data: dict) -> BaseDocument:
    """Create the appropriate document type from a dictionary."""
    doc_type = DocumentType(data["type"])
    doc_class = DOCUMENT_CLASSES[doc_type]
    return doc_class.from_dict(data)
