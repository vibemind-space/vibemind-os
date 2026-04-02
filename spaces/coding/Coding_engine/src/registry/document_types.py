"""
Document Types - Enums and metadata for the document registry.
"""

from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


class DocumentType(str, Enum):
    """Types of documents in the registry."""
    DEBUG_REPORT = "debug_report"
    IMPLEMENTATION_PLAN = "implementation_plan"
    TEST_SPEC = "test_spec"
    QUALITY_REPORT = "quality_report"


class DocumentStatus(str, Enum):
    """Lifecycle status of a document."""
    CREATED = "created"      # Just written by source agent
    PENDING = "pending"      # Waiting for dependent agent to process
    IN_PROGRESS = "in_progress"  # Agent is currently reading/using it
    CONSUMED = "consumed"    # Dependent agent has processed it
    ARCHIVED = "archived"    # Past TTL, moved to archive


# Mapping of document types to their consumer agents
DOCUMENT_CONSUMERS = {
    DocumentType.DEBUG_REPORT: ["Generator"],
    DocumentType.IMPLEMENTATION_PLAN: ["TesterTeam"],
    DocumentType.TEST_SPEC: ["CodeQuality"],  # CodeQualityAgent analyzes after tests
    DocumentType.QUALITY_REPORT: ["Generator"],  # Generator implements quality fixes
}


@dataclass
class DocumentMetadata:
    """Metadata for a document in the registry."""
    id: str
    type: DocumentType
    status: DocumentStatus
    source_agent: str
    created_at: datetime
    updated_at: datetime
    file_path: str  # Path to the document JSON file
    ttl_hours: int = 24
    priority: int = 0  # Higher = more urgent
    responds_to: Optional[str] = None  # Parent document ID
    consumed_by: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "type": self.type.value,
            "status": self.status.value,
            "source_agent": self.source_agent,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "file_path": self.file_path,
            "ttl_hours": self.ttl_hours,
            "priority": self.priority,
            "responds_to": self.responds_to,
            "consumed_by": self.consumed_by,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DocumentMetadata":
        """Deserialize from dictionary."""
        return cls(
            id=data["id"],
            type=DocumentType(data["type"]),
            status=DocumentStatus(data["status"]),
            source_agent=data["source_agent"],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            file_path=data["file_path"],
            ttl_hours=data.get("ttl_hours", 24),
            priority=data.get("priority", 0),
            responds_to=data.get("responds_to"),
            consumed_by=data.get("consumed_by", []),
        )

    def is_expired(self) -> bool:
        """Check if document has exceeded its TTL."""
        from datetime import timedelta
        age = datetime.now() - self.created_at
        return age > timedelta(hours=self.ttl_hours)

    def is_fully_consumed(self) -> bool:
        """Check if all expected consumers have processed this document."""
        expected = DOCUMENT_CONSUMERS.get(self.type, [])
        return all(consumer in self.consumed_by for consumer in expected)
