"""
Document Registry - Central registry for inter-agent documents.

Manages document lifecycle, storage, and retrieval.
"""

import json
import asyncio
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Type
import structlog

from .document_types import DocumentType, DocumentStatus, DocumentMetadata, DOCUMENT_CONSUMERS
from .documents import (
    BaseDocument,
    DebugReport,
    ImplementationPlan,
    TestSpec,
    document_from_dict,
    DOCUMENT_CLASSES,
)


logger = structlog.get_logger(__name__)


class DocumentRegistry:
    """
    Central registry for inter-agent documents.

    Manages:
    - Document storage and retrieval
    - Lifecycle state transitions
    - Cross-references between documents
    - Automatic archival of expired documents
    """

    def __init__(self, output_dir: str):
        """
        Initialize the document registry.

        Args:
            output_dir: Base directory for the project output
        """
        self.output_dir = Path(output_dir)
        self.reports_dir = self.output_dir / "reports"
        self.registry_dir = self.output_dir / ".registry"
        self.registry_path = self.registry_dir / "index.json"
        self._lock = asyncio.Lock()
        self.logger = logger.bind(component="document_registry")

        # Create directories
        self._ensure_directories()

        # Load or initialize registry index
        self._index: dict[str, DocumentMetadata] = {}
        self._load_index()

    def _ensure_directories(self) -> None:
        """Create all necessary directories."""
        dirs = [
            self.reports_dir / "debug",
            self.reports_dir / "implementation",
            self.reports_dir / "tests",
            self.reports_dir / "archive",
            self.registry_dir,
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

    def _get_doc_dir(self, doc_type: DocumentType) -> Path:
        """Get the directory for a document type."""
        type_to_dir = {
            DocumentType.DEBUG_REPORT: self.reports_dir / "debug",
            DocumentType.IMPLEMENTATION_PLAN: self.reports_dir / "implementation",
            DocumentType.TEST_SPEC: self.reports_dir / "tests",
            DocumentType.QUALITY_REPORT: self.reports_dir / "quality",
        }
        doc_dir = type_to_dir[doc_type]
        # Ensure directory exists
        doc_dir.mkdir(parents=True, exist_ok=True)
        return doc_dir

    def _load_index(self) -> None:
        """Load the registry index from disk."""
        if self.registry_path.exists():
            try:
                with open(self.registry_path, "r") as f:
                    data = json.load(f)
                    for doc_id, meta_dict in data.get("documents", {}).items():
                        self._index[doc_id] = DocumentMetadata.from_dict(meta_dict)
                self.logger.info("registry_loaded", document_count=len(self._index))
            except Exception as e:
                self.logger.error("registry_load_failed", error=str(e))
                self._index = {}
        else:
            self._index = {}

    def _save_index(self) -> None:
        """Save the registry index to disk."""
        try:
            data = {
                "documents": {
                    doc_id: meta.to_dict() for doc_id, meta in self._index.items()
                },
                "updated_at": datetime.now().isoformat(),
            }
            with open(self.registry_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            self.logger.error("registry_save_failed", error=str(e))

    async def write_document(self, doc: BaseDocument, priority: int = 0) -> str:
        """
        Write a document to disk and update the registry.

        Args:
            doc: Document to write
            priority: Priority level (higher = more urgent)

        Returns:
            Document ID
        """
        async with self._lock:
            # Determine file path
            doc_dir = self._get_doc_dir(doc.document_type)
            file_name = f"{doc.id}.json"
            file_path = doc_dir / file_name

            # Write document to disk
            try:
                with open(file_path, "w") as f:
                    f.write(doc.to_json())
            except Exception as e:
                self.logger.error("document_write_failed", doc_id=doc.id, error=str(e))
                raise

            # Create metadata
            now = datetime.now()
            responds_to = None
            if hasattr(doc, "responding_to"):
                responds_to = doc.responding_to

            metadata = DocumentMetadata(
                id=doc.id,
                type=doc.document_type,
                status=DocumentStatus.PENDING,
                source_agent=doc.source_agent,
                created_at=now,
                updated_at=now,
                file_path=str(file_path.relative_to(self.output_dir)),
                priority=priority,
                responds_to=responds_to,
            )

            # Add to index
            self._index[doc.id] = metadata
            self._save_index()

            self.logger.info(
                "document_written",
                doc_id=doc.id,
                doc_type=doc.document_type.value,
                priority=priority,
            )

            return doc.id

    async def read_document(self, doc_id: str) -> Optional[BaseDocument]:
        """
        Read a document by ID.

        Args:
            doc_id: Document ID

        Returns:
            Document if found, None otherwise
        """
        metadata = self._index.get(doc_id)
        if not metadata:
            return None

        file_path = self.output_dir / metadata.file_path
        if not file_path.exists():
            self.logger.warning("document_file_missing", doc_id=doc_id)
            return None

        try:
            with open(file_path, "r") as f:
                data = json.load(f)
            return document_from_dict(data)
        except Exception as e:
            self.logger.error("document_read_failed", doc_id=doc_id, error=str(e))
            return None

    async def get_pending_for_agent(
        self,
        agent_name: str,
        doc_type: Optional[DocumentType] = None,
    ) -> list[BaseDocument]:
        """
        Get documents pending for a specific agent.

        Args:
            agent_name: Name of the consuming agent
            doc_type: Optional filter by document type

        Returns:
            List of pending documents for this agent
        """
        pending_docs = []

        # Find document types this agent consumes
        consumable_types = []
        for dtype, consumers in DOCUMENT_CONSUMERS.items():
            if agent_name in consumers:
                if doc_type is None or dtype == doc_type:
                    consumable_types.append(dtype)

        # Find pending documents of those types
        for doc_id, metadata in self._index.items():
            if metadata.type not in consumable_types:
                continue
            if metadata.status not in (DocumentStatus.PENDING, DocumentStatus.CREATED):
                continue
            if agent_name in metadata.consumed_by:
                continue
            if metadata.is_expired():
                continue

            doc = await self.read_document(doc_id)
            if doc:
                pending_docs.append(doc)

        # Sort by priority (highest first) then by creation time (oldest first)
        pending_docs.sort(key=lambda d: (-self._index[d.id].priority, self._index[d.id].created_at))

        self.logger.debug(
            "pending_docs_found",
            agent=agent_name,
            count=len(pending_docs),
        )

        return pending_docs

    async def mark_in_progress(self, doc_id: str, agent_name: str) -> bool:
        """
        Mark a document as being processed by an agent.

        Args:
            doc_id: Document ID
            agent_name: Agent processing the document

        Returns:
            True if successful
        """
        async with self._lock:
            metadata = self._index.get(doc_id)
            if not metadata:
                return False

            metadata.status = DocumentStatus.IN_PROGRESS
            metadata.updated_at = datetime.now()
            self._save_index()

            self.logger.debug("document_in_progress", doc_id=doc_id, agent=agent_name)
            return True

    async def mark_consumed(self, doc_id: str, agent_name: str) -> bool:
        """
        Mark a document as consumed by an agent.

        Args:
            doc_id: Document ID
            agent_name: Agent that consumed the document

        Returns:
            True if successful
        """
        async with self._lock:
            metadata = self._index.get(doc_id)
            if not metadata:
                return False

            if agent_name not in metadata.consumed_by:
                metadata.consumed_by.append(agent_name)

            # Update status based on consumption
            if metadata.is_fully_consumed():
                metadata.status = DocumentStatus.CONSUMED
            else:
                metadata.status = DocumentStatus.PENDING  # Still waiting for other consumers

            metadata.updated_at = datetime.now()
            self._save_index()

            self.logger.info(
                "document_consumed",
                doc_id=doc_id,
                agent=agent_name,
                fully_consumed=metadata.is_fully_consumed(),
            )
            return True

    async def get_document_chain(self, doc_id: str) -> list[BaseDocument]:
        """
        Get the chain of documents related to a given document.

        Follows responds_to links to build a chain.

        Args:
            doc_id: Starting document ID

        Returns:
            List of related documents (oldest first)
        """
        chain = []
        current_id = doc_id

        # Follow chain backwards
        while current_id:
            doc = await self.read_document(current_id)
            if doc:
                chain.insert(0, doc)
            metadata = self._index.get(current_id)
            current_id = metadata.responds_to if metadata else None

        return chain

    async def archive_expired(self) -> int:
        """
        Archive documents that have exceeded their TTL.

        Returns:
            Number of documents archived
        """
        archived = 0
        archive_dir = self.reports_dir / "archive"

        async with self._lock:
            for doc_id, metadata in list(self._index.items()):
                if not metadata.is_expired():
                    continue
                if metadata.status == DocumentStatus.ARCHIVED:
                    continue

                # Move file to archive
                src_path = self.output_dir / metadata.file_path
                if src_path.exists():
                    dst_path = archive_dir / src_path.name
                    try:
                        shutil.move(str(src_path), str(dst_path))
                        metadata.status = DocumentStatus.ARCHIVED
                        metadata.file_path = str(dst_path.relative_to(self.output_dir))
                        metadata.updated_at = datetime.now()
                        archived += 1
                    except Exception as e:
                        self.logger.error("archive_failed", doc_id=doc_id, error=str(e))

            if archived > 0:
                self._save_index()
                self.logger.info("documents_archived", count=archived)

        return archived

    async def get_latest_by_type(self, doc_type: DocumentType) -> Optional[BaseDocument]:
        """
        Get the most recent document of a given type.

        Args:
            doc_type: Type of document to find

        Returns:
            Most recent document or None
        """
        latest_id = None
        latest_time = None

        for doc_id, metadata in self._index.items():
            if metadata.type != doc_type:
                continue
            if metadata.status == DocumentStatus.ARCHIVED:
                continue
            if latest_time is None or metadata.created_at > latest_time:
                latest_id = doc_id
                latest_time = metadata.created_at

        if latest_id:
            return await self.read_document(latest_id)
        return None

    async def get_all_by_status(self, status: DocumentStatus) -> list[DocumentMetadata]:
        """
        Get metadata for all documents with a given status.

        Args:
            status: Status to filter by

        Returns:
            List of document metadata
        """
        return [
            meta for meta in self._index.values()
            if meta.status == status
        ]

    def get_stats(self) -> dict:
        """Get statistics about the registry."""
        stats = {
            "total_documents": len(self._index),
            "by_type": {},
            "by_status": {},
        }

        for metadata in self._index.values():
            # Count by type
            type_name = metadata.type.value
            stats["by_type"][type_name] = stats["by_type"].get(type_name, 0) + 1

            # Count by status
            status_name = metadata.status.value
            stats["by_status"][status_name] = stats["by_status"].get(status_name, 0) + 1

        return stats
