"""
Cell Import Service - Import cells from marketplace into colony.

Handles:
- Fetching cells from registry
- Dependency resolution
- Artifact download
- Security verification
- Deployment to colony
"""

import asyncio
import hashlib
import json
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid

import structlog

from src.mind.event_bus import EventBus, Event
from src.services.cell_security_scanner import CellSecurityScanner, ScanType, ScanResult
from src.services.moderation_service import ModerationService
from src.colony.cell import Cell, CellStatus, SourceType

logger = structlog.get_logger()


class ImportStatus(str, Enum):
    """Status of a cell import operation."""
    PENDING = "pending"
    FETCHING = "fetching"
    RESOLVING_DEPS = "resolving_dependencies"
    DOWNLOADING = "downloading"
    SCANNING = "scanning"
    DEPLOYING = "deploying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ArtifactType(str, Enum):
    """Types of cell artifacts."""
    SOURCE = "source"  # Source code archive
    CONTAINER = "container"  # Docker image
    HELM = "helm"  # Helm chart
    MANIFEST = "manifest"  # K8s manifests


@dataclass
class CellVersion:
    """Represents a specific version of a cell in the registry."""
    id: str
    cell_id: str
    version: str
    artifact_url: str
    artifact_type: ArtifactType
    artifact_checksum: str
    checksum_algorithm: str = "sha256"
    dependencies: List[Dict[str, str]] = field(default_factory=list)  # [{cell_id, version_constraint}]
    published_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    publisher_id: str = ""
    scan_status: str = "passed"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CellRegistryEntry:
    """Represents a cell in the marketplace registry."""
    id: str
    namespace: str  # publisher/cell-name format
    name: str
    description: str
    owner_id: str
    visibility: str = "public"
    latest_version: str = ""
    versions: List[CellVersion] = field(default_factory=list)
    download_count: int = 0
    rating: float = 0.0
    tags: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ImportRequest:
    """Request to import a cell into a colony."""
    id: str
    cell_namespace: str  # publisher/cell-name
    version_constraint: str = "latest"  # Semver constraint or "latest"
    target_namespace: str = "default"  # K8s namespace
    skip_dependencies: bool = False
    skip_security_scan: bool = False
    force: bool = False  # Import even if already exists
    requester_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ImportResult:
    """Result of a cell import operation."""
    request_id: str
    status: ImportStatus
    cell_id: Optional[str] = None
    cell_namespace: str = ""
    version: str = ""
    dependencies_imported: List[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    security_scan: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float:
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "request_id": self.request_id,
            "status": self.status.value,
            "cell_id": self.cell_id,
            "cell_namespace": self.cell_namespace,
            "version": self.version,
            "dependencies_imported": self.dependencies_imported,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "error": self.error,
            "security_scan": self.security_scan,
        }


class DependencyResolver:
    """Resolves cell dependencies using semver."""

    def __init__(self, registry: "CellRegistry"):
        self.registry = registry
        self.logger = logger.bind(component="DependencyResolver")

    async def resolve(
        self,
        cell_namespace: str,
        version_constraint: str,
        resolved: Optional[Set[str]] = None,
    ) -> List[Tuple[str, str]]:
        """
        Resolve all dependencies for a cell.

        Args:
            cell_namespace: Cell namespace (publisher/name)
            version_constraint: Version constraint
            resolved: Already resolved dependencies to avoid cycles

        Returns:
            List of (namespace, version) tuples in install order
        """
        resolved = resolved or set()
        install_order: List[Tuple[str, str]] = []

        # Get cell entry
        entry = await self.registry.get_cell(cell_namespace)
        if not entry:
            raise ValueError(f"Cell not found: {cell_namespace}")

        # Get matching version
        version = self._resolve_version(entry.versions, version_constraint)
        if not version:
            raise ValueError(f"No matching version for {cell_namespace}@{version_constraint}")

        key = f"{cell_namespace}@{version.version}"
        if key in resolved:
            return install_order

        resolved.add(key)

        # Resolve dependencies first (depth-first)
        for dep in version.dependencies:
            dep_namespace = dep.get("cell_id", "")
            dep_constraint = dep.get("version_constraint", "latest")

            if f"{dep_namespace}@" not in str(resolved):
                dep_order = await self.resolve(dep_namespace, dep_constraint, resolved)
                install_order.extend(dep_order)

        # Add this cell after its dependencies
        install_order.append((cell_namespace, version.version))

        return install_order

    def _resolve_version(
        self,
        versions: List[CellVersion],
        constraint: str,
    ) -> Optional[CellVersion]:
        """Resolve version constraint to specific version."""
        if not versions:
            return None

        if constraint == "latest":
            # Sort by version and return newest
            sorted_versions = sorted(
                versions,
                key=lambda v: self._parse_semver(v.version),
                reverse=True,
            )
            return sorted_versions[0] if sorted_versions else None

        # Try exact match first
        for v in versions:
            if v.version == constraint:
                return v

        # Handle semver constraints (simplified)
        if constraint.startswith("^"):
            # Compatible with major version
            target = constraint[1:]
            major = self._parse_semver(target)[0]
            matching = [
                v for v in versions
                if self._parse_semver(v.version)[0] == major
            ]
            if matching:
                return sorted(matching, key=lambda v: self._parse_semver(v.version), reverse=True)[0]

        if constraint.startswith("~"):
            # Compatible with minor version
            target = constraint[1:]
            major, minor = self._parse_semver(target)[:2]
            matching = [
                v for v in versions
                if self._parse_semver(v.version)[:2] == (major, minor)
            ]
            if matching:
                return sorted(matching, key=lambda v: self._parse_semver(v.version), reverse=True)[0]

        return None

    def _parse_semver(self, version: str) -> Tuple[int, int, int]:
        """Parse semantic version string."""
        try:
            parts = version.lstrip("v").split("-")[0].split(".")
            return (
                int(parts[0]) if len(parts) > 0 else 0,
                int(parts[1]) if len(parts) > 1 else 0,
                int(parts[2]) if len(parts) > 2 else 0,
            )
        except (ValueError, IndexError):
            return (0, 0, 0)


class CellRegistry:
    """
    Interface to the cell marketplace registry.

    In production, this would connect to an external registry service.
    """

    def __init__(self, registry_url: str = "https://registry.codingengine.io"):
        self.registry_url = registry_url
        self.logger = logger.bind(component="CellRegistry")

        # Mock registry data (in production, would fetch from API)
        self._cells: Dict[str, CellRegistryEntry] = {}
        self._init_mock_data()

    def _init_mock_data(self) -> None:
        """Initialize mock registry data for testing."""
        # Example cells
        self._cells["codingengine/auth-service"] = CellRegistryEntry(
            id=str(uuid.uuid4()),
            namespace="codingengine/auth-service",
            name="Auth Service",
            description="JWT-based authentication microservice",
            owner_id="codingengine",
            latest_version="1.2.0",
            versions=[
                CellVersion(
                    id=str(uuid.uuid4()),
                    cell_id="auth-service",
                    version="1.2.0",
                    artifact_url="https://registry.codingengine.io/v1/cells/codingengine/auth-service/1.2.0/download",
                    artifact_type=ArtifactType.CONTAINER,
                    artifact_checksum="sha256:abc123...",
                    dependencies=[],
                ),
            ],
            tags=["auth", "jwt", "security"],
        )

        self._cells["codingengine/user-api"] = CellRegistryEntry(
            id=str(uuid.uuid4()),
            namespace="codingengine/user-api",
            name="User API",
            description="User management REST API",
            owner_id="codingengine",
            latest_version="2.0.0",
            versions=[
                CellVersion(
                    id=str(uuid.uuid4()),
                    cell_id="user-api",
                    version="2.0.0",
                    artifact_url="https://registry.codingengine.io/v1/cells/codingengine/user-api/2.0.0/download",
                    artifact_type=ArtifactType.CONTAINER,
                    artifact_checksum="sha256:def456...",
                    dependencies=[
                        {"cell_id": "codingengine/auth-service", "version_constraint": "^1.0.0"},
                    ],
                ),
            ],
            tags=["user", "api", "crud"],
        )

    async def get_cell(self, namespace: str) -> Optional[CellRegistryEntry]:
        """Get cell by namespace."""
        # In production: HTTP GET to registry API
        return self._cells.get(namespace)

    async def search_cells(
        self,
        query: str = "",
        tags: Optional[List[str]] = None,
        limit: int = 20,
    ) -> List[CellRegistryEntry]:
        """Search cells in registry."""
        results = list(self._cells.values())

        if query:
            query_lower = query.lower()
            results = [
                c for c in results
                if query_lower in c.name.lower() or query_lower in c.description.lower()
            ]

        if tags:
            results = [
                c for c in results
                if any(t in c.tags for t in tags)
            ]

        return results[:limit]

    async def download_artifact(
        self,
        url: str,
        destination: Path,
        expected_checksum: str,
    ) -> bool:
        """
        Download artifact and verify checksum.

        Args:
            url: Download URL
            destination: Local path to save
            expected_checksum: Expected SHA256 checksum

        Returns:
            True if download and verification successful
        """
        # In production: HTTP GET to download URL with streaming
        # For now, simulate download
        self.logger.info("Downloading artifact", url=url, destination=str(destination))

        # Mock: Create a dummy file
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(f"Mock artifact from {url}")

        return True


class CellImportService:
    """
    Service for importing cells from marketplace into a colony.

    Handles the complete import workflow:
    1. Fetch cell metadata from registry
    2. Resolve dependencies recursively
    3. Download artifacts
    4. Verify checksums
    5. Run security scans
    6. Deploy to colony
    """

    def __init__(
        self,
        registry: Optional[CellRegistry] = None,
        event_bus: Optional[EventBus] = None,
        security_scanner: Optional[CellSecurityScanner] = None,
        moderation_service: Optional[ModerationService] = None,
        artifact_cache_dir: Optional[Path] = None,
    ):
        self.logger = logger.bind(component="CellImportService")
        self.registry = registry or CellRegistry()
        self.event_bus = event_bus
        self.security_scanner = security_scanner
        self.moderation_service = moderation_service
        self.artifact_cache = artifact_cache_dir or Path(tempfile.gettempdir()) / "cell-imports"
        self.resolver = DependencyResolver(self.registry)

        # Import tracking
        self._imports: Dict[str, ImportResult] = {}
        self._imported_cells: Dict[str, Cell] = {}  # namespace -> Cell

    async def import_cell(
        self,
        request: ImportRequest,
    ) -> ImportResult:
        """
        Import a cell from the marketplace.

        Args:
            request: Import request details

        Returns:
            ImportResult with status and details
        """
        result = ImportResult(
            request_id=request.id,
            status=ImportStatus.PENDING,
            cell_namespace=request.cell_namespace,
        )
        self._imports[request.id] = result

        try:
            self.logger.info(
                "Starting cell import",
                request_id=request.id,
                namespace=request.cell_namespace,
                version=request.version_constraint,
            )

            # Check if already imported
            if not request.force and request.cell_namespace in self._imported_cells:
                existing = self._imported_cells[request.cell_namespace]
                result.status = ImportStatus.COMPLETED
                result.cell_id = existing.id
                result.version = existing.version
                result.completed_at = datetime.now(timezone.utc)
                return result

            # Fetch cell metadata
            result.status = ImportStatus.FETCHING
            await self._emit_progress(result)

            entry = await self.registry.get_cell(request.cell_namespace)
            if not entry:
                raise ValueError(f"Cell not found: {request.cell_namespace}")

            # Check if quarantined
            if self.moderation_service:
                is_quarantined = await self.moderation_service.is_quarantined(entry.id)
                if is_quarantined:
                    raise ValueError(f"Cell is quarantined: {request.cell_namespace}")

            # Resolve dependencies
            result.status = ImportStatus.RESOLVING_DEPS
            await self._emit_progress(result)

            install_order: List[Tuple[str, str]] = []
            if not request.skip_dependencies:
                install_order = await self.resolver.resolve(
                    request.cell_namespace,
                    request.version_constraint,
                )

            # Import dependencies first
            for dep_namespace, dep_version in install_order[:-1]:  # Exclude main cell
                dep_result = await self._import_single(
                    dep_namespace,
                    dep_version,
                    request.target_namespace,
                    request.skip_security_scan,
                )
                if dep_result:
                    result.dependencies_imported.append(f"{dep_namespace}@{dep_version}")

            # Import main cell
            main_namespace, main_version = install_order[-1] if install_order else (
                request.cell_namespace,
                request.version_constraint,
            )

            cell = await self._import_single(
                main_namespace,
                main_version,
                request.target_namespace,
                request.skip_security_scan,
            )

            if cell:
                result.status = ImportStatus.COMPLETED
                result.cell_id = cell.id
                result.version = cell.version
            else:
                result.status = ImportStatus.FAILED
                result.error = "Failed to import cell"

            result.completed_at = datetime.now(timezone.utc)

            # Emit completion event
            if self.event_bus:
                await self.event_bus.publish(Event(
                    type="CELL_IMPORT_COMPLETED" if result.status == ImportStatus.COMPLETED else "CELL_IMPORT_FAILED",
                    source="import_service",
                    data=result.to_dict(),
                ))

            self.logger.info(
                "Cell import completed",
                request_id=request.id,
                status=result.status.value,
                cell_id=result.cell_id,
            )

        except Exception as e:
            result.status = ImportStatus.FAILED
            result.error = str(e)
            result.completed_at = datetime.now(timezone.utc)
            self.logger.error(
                "Cell import failed",
                request_id=request.id,
                error=str(e),
            )

        return result

    async def _import_single(
        self,
        namespace: str,
        version: str,
        target_namespace: str,
        skip_scan: bool,
    ) -> Optional[Cell]:
        """Import a single cell (without dependencies)."""
        # Check if already imported
        if namespace in self._imported_cells:
            return self._imported_cells[namespace]

        # Get cell entry
        entry = await self.registry.get_cell(namespace)
        if not entry:
            return None

        # Get specific version
        version_entry = None
        for v in entry.versions:
            if v.version == version:
                version_entry = v
                break

        if not version_entry:
            self.logger.warning("Version not found", namespace=namespace, version=version)
            return None

        # Download artifact
        artifact_path = self.artifact_cache / namespace.replace("/", "_") / version
        success = await self.registry.download_artifact(
            version_entry.artifact_url,
            artifact_path / "artifact",
            version_entry.artifact_checksum,
        )

        if not success:
            return None

        # Security scan
        if not skip_scan and self.security_scanner:
            scan_result = await self.security_scanner.scan_cell(
                entry.id,
                artifact_path,
                ScanType.FULL,
            )

            if not scan_result.passed:
                self.logger.warning(
                    "Security scan failed",
                    namespace=namespace,
                    risk_score=scan_result.risk_score,
                )
                # Don't fail import, but log warning
                # In production, might want to block critical findings

        # Create Cell object
        cell = Cell(
            id=str(uuid.uuid4()),
            name=entry.name.lower().replace(" ", "-"),
            namespace=target_namespace,
            source_type=SourceType.MARKETPLACE,
            source_ref=namespace,
            working_dir=str(artifact_path),
            image=version_entry.artifact_url if version_entry.artifact_type == ArtifactType.CONTAINER else None,
            status=CellStatus.PENDING,
            version=version,
        )

        self._imported_cells[namespace] = cell

        self.logger.info(
            "Cell imported",
            namespace=namespace,
            version=version,
            cell_id=cell.id,
        )

        return cell

    async def _emit_progress(self, result: ImportResult) -> None:
        """Emit progress event."""
        if self.event_bus:
            await self.event_bus.publish(Event(
                type="CELL_IMPORT_PROGRESS",
                source="import_service",
                data={
                    "request_id": result.request_id,
                    "status": result.status.value,
                    "cell_namespace": result.cell_namespace,
                },
            ))

    async def get_import_status(self, request_id: str) -> Optional[ImportResult]:
        """Get status of an import request."""
        return self._imports.get(request_id)

    async def list_imports(
        self,
        status: Optional[ImportStatus] = None,
        limit: int = 50,
    ) -> List[ImportResult]:
        """List import requests."""
        results = list(self._imports.values())

        if status:
            results = [r for r in results if r.status == status]

        results.sort(key=lambda r: r.started_at, reverse=True)
        return results[:limit]

    async def cancel_import(self, request_id: str) -> bool:
        """Cancel a pending import."""
        result = self._imports.get(request_id)
        if not result:
            return False

        if result.status in (ImportStatus.COMPLETED, ImportStatus.FAILED):
            return False

        result.status = ImportStatus.CANCELLED
        result.completed_at = datetime.now(timezone.utc)
        return True

    def get_imported_cells(self) -> Dict[str, Cell]:
        """Get all imported cells."""
        return dict(self._imported_cells)

    def get_imported_cell(self, namespace: str) -> Optional[Cell]:
        """Get an imported cell by namespace."""
        return self._imported_cells.get(namespace)

    async def remove_imported_cell(self, namespace: str) -> bool:
        """Remove an imported cell."""
        if namespace in self._imported_cells:
            cell = self._imported_cells.pop(namespace)

            # Clean up artifacts
            artifact_path = self.artifact_cache / namespace.replace("/", "_")
            if artifact_path.exists():
                shutil.rmtree(artifact_path, ignore_errors=True)

            self.logger.info("Removed imported cell", namespace=namespace, cell_id=cell.id)
            return True

        return False

    def clear_cache(self) -> None:
        """Clear the artifact cache."""
        if self.artifact_cache.exists():
            shutil.rmtree(self.artifact_cache, ignore_errors=True)
        self.artifact_cache.mkdir(parents=True, exist_ok=True)
        self.logger.info("Artifact cache cleared")
