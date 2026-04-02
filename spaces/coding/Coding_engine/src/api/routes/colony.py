"""
Colony Management API endpoints.

Provides REST endpoints for managing the Cell Colony cluster:
- Deploy cells to K8s
- Monitor colony health
- View cell logs
- Scale cells
- Terminate cells
"""

from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from src.colony.cell import Cell, CellStatus, SourceType, ResourceLimits
from src.colony.colony_manager import ColonyManager
from src.colony.lifecycle_controller import LifecycleController
from src.colony.k8s.kubectl_tool import KubectlTool
from src.mind.event_bus import EventBus

router = APIRouter(prefix="/colony", tags=["colony"])


# Pydantic schemas
class ResourceLimitsRequest(BaseModel):
    """Resource limits for a cell."""
    cpu_request: str = "100m"
    cpu_limit: str = "500m"
    memory_request: str = "128Mi"
    memory_limit: str = "512Mi"


class DeployCellRequest(BaseModel):
    """Request to deploy a new cell."""
    name: str = Field(..., min_length=1, max_length=63, pattern="^[a-z0-9][a-z0-9-]*[a-z0-9]$")
    namespace: str = Field(default="default", max_length=63)
    source_type: str = Field(default="llm_generated", description="llm_generated, repo_clone, template, or marketplace")
    source_ref: str = Field(..., min_length=1, description="Prompt, repo URL, template name, or marketplace namespace")
    image: Optional[str] = Field(None, description="Docker image if pre-built")
    resources: Optional[ResourceLimitsRequest] = None
    ports: List[int] = Field(default=[8080])
    env_vars: dict = Field(default_factory=dict)
    replicas: int = Field(default=1, ge=1, le=10)


class CellResponse(BaseModel):
    """Cell status response."""
    id: str
    name: str
    namespace: str
    status: str
    health_score: float
    version: str
    image: Optional[str]
    replicas: Optional[int]
    ready_replicas: Optional[int]
    created_at: str
    mutation_count: int

    class Config:
        from_attributes = True


class ColonyStatusResponse(BaseModel):
    """Colony health overview."""
    total_cells: int
    healthy_cells: int
    degraded_cells: int
    failed_cells: int
    cells_in_recovery: int
    health_ratio: float
    convergence_status: str
    cells: List[CellResponse]


class ScaleCellRequest(BaseModel):
    """Request to scale a cell."""
    replicas: int = Field(..., ge=0, le=20)


class CellLogsResponse(BaseModel):
    """Cell logs response."""
    cell_id: str
    cell_name: str
    pod_name: str
    logs: str
    since: Optional[str]


# Singleton instances (would be injected in production)
_event_bus: Optional[EventBus] = None
_kubectl: Optional[KubectlTool] = None
_lifecycle_controller: Optional[LifecycleController] = None
_colony_manager: Optional[ColonyManager] = None


def get_event_bus() -> EventBus:
    """Get or create EventBus instance."""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


def get_kubectl() -> KubectlTool:
    """Get or create KubectlTool instance."""
    global _kubectl
    if _kubectl is None:
        _kubectl = KubectlTool()
    return _kubectl


def get_lifecycle_controller() -> LifecycleController:
    """Get or create LifecycleController instance."""
    global _lifecycle_controller
    if _lifecycle_controller is None:
        _lifecycle_controller = LifecycleController(event_bus=get_event_bus())
    return _lifecycle_controller


def get_colony_manager() -> ColonyManager:
    """Get or create ColonyManager instance."""
    global _colony_manager
    if _colony_manager is None:
        # Note: In production, this would be properly initialized
        _colony_manager = ColonyManager.__new__(ColonyManager)
        _colony_manager.cells = {}
    return _colony_manager


@router.post("/deploy", response_model=CellResponse, status_code=status.HTTP_201_CREATED)
async def deploy_cell(
    request: DeployCellRequest,
    lifecycle: LifecycleController = Depends(get_lifecycle_controller),
    kubectl: KubectlTool = Depends(get_kubectl),
):
    """
    Deploy a new cell to the colony.

    Creates the cell and deploys it to the Kubernetes cluster.
    """
    # Parse source type
    try:
        source_type = SourceType(request.source_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid source_type: {request.source_type}. Must be one of: llm_generated, repo_clone, template, marketplace",
        )

    # Create resource limits
    resource_limits = ResourceLimits()
    if request.resources:
        resource_limits = ResourceLimits(
            cpu_request=request.resources.cpu_request,
            cpu_limit=request.resources.cpu_limit,
            memory_request=request.resources.memory_request,
            memory_limit=request.resources.memory_limit,
        )

    # Create cell
    cell = Cell(
        id=str(uuid4()),
        name=request.name,
        namespace=request.namespace,
        source_type=source_type,
        source_ref=request.source_ref,
        working_dir=f"/app/cells/{request.name}",
        image=request.image,
        resource_limits=resource_limits,
        ports=request.ports,
        env_vars=request.env_vars,
    )

    # Register with lifecycle controller
    lifecycle.register_cell(cell)

    # TODO: Trigger actual deployment via K8s operator
    # For now, just mark as deploying
    cell.status = CellStatus.DEPLOYING

    return CellResponse(
        id=cell.id,
        name=cell.name,
        namespace=cell.namespace,
        status=cell.status.value,
        health_score=cell.health_score,
        version=cell.version,
        image=cell.image,
        replicas=request.replicas,
        ready_replicas=0,
        created_at=cell.created_at.isoformat(),
        mutation_count=cell.mutation_count,
    )


@router.get("/status", response_model=ColonyStatusResponse)
async def get_colony_status(
    lifecycle: LifecycleController = Depends(get_lifecycle_controller),
):
    """
    Get colony health overview.

    Returns counts of cells in various states and overall health ratio.
    """
    all_cells = lifecycle.get_all_cells()

    healthy = [c for c in all_cells if c.status == CellStatus.HEALTHY]
    degraded = [c for c in all_cells if c.status == CellStatus.DEGRADED]
    recovering = [c for c in all_cells if c.status == CellStatus.RECOVERING]
    failed = [c for c in all_cells if c.status in (CellStatus.TERMINATING, CellStatus.TERMINATED)]

    total = len(all_cells)
    health_ratio = len(healthy) / total if total > 0 else 1.0

    convergence_status = "converged"
    if health_ratio < 0.8:
        convergence_status = "rebalancing"
    elif recovering:
        convergence_status = "recovering"

    cells = [
        CellResponse(
            id=c.id,
            name=c.name,
            namespace=c.namespace,
            status=c.status.value,
            health_score=c.health_score,
            version=c.version,
            image=c.image,
            replicas=None,
            ready_replicas=None,
            created_at=c.created_at.isoformat(),
            mutation_count=c.mutation_count,
        )
        for c in all_cells
    ]

    return ColonyStatusResponse(
        total_cells=total,
        healthy_cells=len(healthy),
        degraded_cells=len(degraded),
        failed_cells=len(failed),
        cells_in_recovery=len(recovering),
        health_ratio=health_ratio,
        convergence_status=convergence_status,
        cells=cells,
    )


@router.get("/cells", response_model=List[CellResponse])
async def list_cells(
    namespace: Optional[str] = Query(None, description="Filter by namespace"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    lifecycle: LifecycleController = Depends(get_lifecycle_controller),
):
    """
    List all cells in the colony.
    """
    all_cells = lifecycle.get_all_cells()

    if namespace:
        all_cells = [c for c in all_cells if c.namespace == namespace]

    if status_filter:
        try:
            cell_status = CellStatus(status_filter)
            all_cells = [c for c in all_cells if c.status == cell_status]
        except ValueError:
            pass

    return [
        CellResponse(
            id=c.id,
            name=c.name,
            namespace=c.namespace,
            status=c.status.value,
            health_score=c.health_score,
            version=c.version,
            image=c.image,
            replicas=None,
            ready_replicas=None,
            created_at=c.created_at.isoformat(),
            mutation_count=c.mutation_count,
        )
        for c in all_cells
    ]


@router.get("/cells/{cell_id}", response_model=CellResponse)
async def get_cell(
    cell_id: str,
    lifecycle: LifecycleController = Depends(get_lifecycle_controller),
):
    """
    Get details of a specific cell.
    """
    cell = lifecycle.get_cell(cell_id)
    if not cell:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cell {cell_id} not found",
        )

    return CellResponse(
        id=cell.id,
        name=cell.name,
        namespace=cell.namespace,
        status=cell.status.value,
        health_score=cell.health_score,
        version=cell.version,
        image=cell.image,
        replicas=None,
        ready_replicas=None,
        created_at=cell.created_at.isoformat(),
        mutation_count=cell.mutation_count,
    )


@router.get("/cells/{cell_id}/logs", response_model=CellLogsResponse)
async def get_cell_logs(
    cell_id: str,
    tail: int = Query(100, ge=1, le=5000, description="Number of log lines to return"),
    since: Optional[str] = Query(None, description="Return logs since this duration (e.g., '1h', '30m')"),
    lifecycle: LifecycleController = Depends(get_lifecycle_controller),
    kubectl: KubectlTool = Depends(get_kubectl),
):
    """
    Get logs from a cell's pod.
    """
    cell = lifecycle.get_cell(cell_id)
    if not cell:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cell {cell_id} not found",
        )

    try:
        result = await kubectl.get_pod_logs(
            pod_name=cell.k8s_pod_name or f"cell-{cell.name}",
            namespace=cell.namespace,
            tail_lines=tail,
            since=since,
        )

        if not result.success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get logs: {result.error}",
            )

        return CellLogsResponse(
            cell_id=cell.id,
            cell_name=cell.name,
            pod_name=cell.k8s_pod_name or f"cell-{cell.name}",
            logs=result.stdout,
            since=since,
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get logs: {str(e)}",
        )


@router.patch("/cells/{cell_id}/scale", response_model=CellResponse)
async def scale_cell(
    cell_id: str,
    request: ScaleCellRequest,
    lifecycle: LifecycleController = Depends(get_lifecycle_controller),
    kubectl: KubectlTool = Depends(get_kubectl),
):
    """
    Scale a cell's replicas.
    """
    cell = lifecycle.get_cell(cell_id)
    if not cell:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cell {cell_id} not found",
        )

    if cell.status not in (CellStatus.HEALTHY, CellStatus.DEGRADED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot scale cell in {cell.status.value} state",
        )

    try:
        result = await kubectl.scale_deployment(
            deployment_name=cell.k8s_deployment_name,
            namespace=cell.namespace,
            replicas=request.replicas,
        )

        if not result.success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to scale: {result.error}",
            )

        return CellResponse(
            id=cell.id,
            name=cell.name,
            namespace=cell.namespace,
            status=cell.status.value,
            health_score=cell.health_score,
            version=cell.version,
            image=cell.image,
            replicas=request.replicas,
            ready_replicas=None,
            created_at=cell.created_at.isoformat(),
            mutation_count=cell.mutation_count,
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to scale: {str(e)}",
        )


@router.delete("/cells/{cell_id}", status_code=status.HTTP_204_NO_CONTENT)
async def terminate_cell(
    cell_id: str,
    force: bool = Query(False, description="Force termination even if cell has dependents"),
    lifecycle: LifecycleController = Depends(get_lifecycle_controller),
):
    """
    Terminate a cell.

    Triggers autophagy and removes all associated K8s resources.
    """
    cell = lifecycle.get_cell(cell_id)
    if not cell:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cell {cell_id} not found",
        )

    # Check for dependents
    if cell.dependents and not force:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cell has dependents: {cell.dependents}. Use force=true to terminate anyway.",
        )

    # Trigger autophagy
    result = await lifecycle.trigger_autophagy(cell, reason="User requested termination")

    if result.value != "success":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to terminate cell: {result.value}",
        )


@router.post("/cells/{cell_id}/restart", response_model=CellResponse)
async def restart_cell(
    cell_id: str,
    lifecycle: LifecycleController = Depends(get_lifecycle_controller),
    kubectl: KubectlTool = Depends(get_kubectl),
):
    """
    Restart a cell by rolling its deployment.
    """
    cell = lifecycle.get_cell(cell_id)
    if not cell:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cell {cell_id} not found",
        )

    try:
        result = await kubectl.rollout_restart(
            resource_type="deployment",
            resource_name=cell.k8s_deployment_name,
            namespace=cell.namespace,
        )

        if not result.success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to restart: {result.error}",
            )

        return CellResponse(
            id=cell.id,
            name=cell.name,
            namespace=cell.namespace,
            status=cell.status.value,
            health_score=cell.health_score,
            version=cell.version,
            image=cell.image,
            replicas=None,
            ready_replicas=None,
            created_at=cell.created_at.isoformat(),
            mutation_count=cell.mutation_count,
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to restart: {str(e)}",
        )


@router.post("/cells/{cell_id}/recover")
async def trigger_recovery(
    cell_id: str,
    lifecycle: LifecycleController = Depends(get_lifecycle_controller),
):
    """
    Trigger recovery procedure for a degraded cell.
    """
    cell = lifecycle.get_cell(cell_id)
    if not cell:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cell {cell_id} not found",
        )

    if cell.status != CellStatus.DEGRADED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cell is not degraded (current status: {cell.status.value})",
        )

    result = await lifecycle.start_recovery(cell, reason="User triggered recovery")

    return {
        "cell_id": cell.id,
        "status": "recovery_started",
        "result": result.value,
    }
