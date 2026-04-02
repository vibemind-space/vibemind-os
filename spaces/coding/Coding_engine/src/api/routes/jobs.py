"""Job management endpoints."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import json

from src.models.base import get_db
from src.models.project import Project
from src.models.job import Job, JobStatus
from src.models.task import Task
from src.engine.orchestrator import Orchestrator

router = APIRouter()


# Request/Response schemas
class JobSubmit(BaseModel):
    """Schema for submitting a job."""
    project_id: int
    requirements_json: str = Field(..., description="Requirements JSON string")
    source_file: Optional[str] = None


class JobResponse(BaseModel):
    """Schema for job response."""
    id: int
    project_id: int
    status: str
    status_message: Optional[str]
    total_requirements: int
    total_tasks: int
    tasks_completed: int
    tasks_failed: int
    progress_percent: float
    dag_nodes: int
    dag_edges: int
    created_at: str
    updated_at: str


class JobDetailResponse(JobResponse):
    """Schema for detailed job response including tasks."""
    tasks: list[dict]


class JobListResponse(BaseModel):
    """Schema for job list response."""
    jobs: list[JobResponse]
    total: int


class TaskResponse(BaseModel):
    """Schema for task response."""
    id: int
    task_id: str
    title: str
    task_type: str
    status: str
    depth_level: int
    depends_on: list[str]


# Endpoints
@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def submit_job(
    data: JobSubmit,
    db: AsyncSession = Depends(get_db),
):
    """
    Submit a new job for processing.

    Takes a requirements JSON and creates tasks for each requirement.
    Tasks are scheduled based on dependency order from the knowledge graph.

    If project_id is 0, uses the first available project or creates a default one.
    """
    # Resolve project_id
    actual_project_id = data.project_id

    if data.project_id == 0:
        # Find first available project
        result = await db.execute(
            select(Project.id).order_by(Project.id).limit(1)
        )
        row = result.first()

        if row:
            actual_project_id = row[0]
        else:
            # Create default project using raw SQL to avoid greenlet issues
            from sqlalchemy import text
            result = await db.execute(
                text("""
                    INSERT INTO projects (name, description, status, git_branch, created_at, updated_at)
                    VALUES ('Auto-Generated Project', 'Default project for code generation', 'CREATED', 'main', NOW(), NOW())
                    RETURNING id
                """)
            )
            row = result.first()
            actual_project_id = row[0]
            await db.commit()
    else:
        # Verify project exists
        result = await db.execute(
            select(Project).where(Project.id == data.project_id)
        )
        project = result.scalar_one_or_none()

        if not project:
            raise HTTPException(
                status_code=404,
                detail=f"Project {data.project_id} not found",
            )

    # Validate JSON
    try:
        json.loads(data.requirements_json)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid JSON: {str(e)}",
        )

    # Create orchestrator and submit job
    orchestrator = Orchestrator(db)
    await orchestrator.initialize()

    try:
        job = await orchestrator.submit_job(
            project_id=actual_project_id,  # Use resolved project ID (handles project_id=0 case)
            requirements_json=data.requirements_json,
            source_file=data.source_file,
        )
        # Capture all needed values before shutdown to avoid lazy loading issues
        job_id = job.id
        job_project_id = job.project_id
        job_status = job.status.value
        job_status_message = job.status_message
        job_total_requirements = job.total_requirements
        job_total_tasks = job.total_tasks
        job_tasks_completed = job.tasks_completed
        job_tasks_failed = job.tasks_failed
        job_progress_percent = job.progress_percent
        job_dag_nodes = job.dag_nodes
        job_dag_edges = job.dag_edges
        job_created_at = job.created_at.isoformat()
        job_updated_at = job.updated_at.isoformat()
    finally:
        await orchestrator.shutdown()

    return JobResponse(
        id=job_id,
        project_id=job_project_id,
        status=job_status,
        status_message=job_status_message,
        total_requirements=job_total_requirements,
        total_tasks=job_total_tasks,
        tasks_completed=job_tasks_completed,
        tasks_failed=job_tasks_failed,
        progress_percent=job_progress_percent,
        dag_nodes=job_dag_nodes,
        dag_edges=job_dag_edges,
        created_at=job_created_at,
        updated_at=job_updated_at,
    )


@router.post("/upload", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def submit_job_file(
    project_id: int = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Submit a job by uploading a requirements JSON file.
    """
    # Verify project exists
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=404,
            detail=f"Project {project_id} not found",
        )

    # Read and validate file
    try:
        content = await file.read()
        requirements_json = content.decode('utf-8')
        json.loads(requirements_json)  # Validate JSON
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid JSON file: {str(e)}",
        )

    # Create orchestrator and submit job
    orchestrator = Orchestrator(db)
    await orchestrator.initialize()

    try:
        job = await orchestrator.submit_job(
            project_id=project_id,
            requirements_json=requirements_json,
            source_file=file.filename,
        )
    finally:
        await orchestrator.shutdown()

    return JobResponse(
        id=job.id,
        project_id=job.project_id,
        status=job.status.value,
        status_message=job.status_message,
        total_requirements=job.total_requirements,
        total_tasks=job.total_tasks,
        tasks_completed=job.tasks_completed,
        tasks_failed=job.tasks_failed,
        progress_percent=job.progress_percent,
        dag_nodes=job.dag_nodes,
        dag_edges=job.dag_edges,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
    )


@router.get("", response_model=JobListResponse)
async def list_jobs(
    project_id: Optional[int] = None,
    status_filter: Optional[str] = None,
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """
    List jobs with optional filtering.
    """
    query = select(Job)

    if project_id:
        query = query.where(Job.project_id == project_id)

    if status_filter:
        try:
            status_enum = JobStatus(status_filter)
            query = query.where(Job.status == status_enum)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status: {status_filter}",
            )

    # Get total count
    count_query = select(Job)
    if project_id:
        count_query = count_query.where(Job.project_id == project_id)
    count_result = await db.execute(count_query)
    total = len(count_result.scalars().all())

    # Get paginated results
    query = query.offset(skip).limit(limit).order_by(Job.created_at.desc())
    result = await db.execute(query)
    jobs = result.scalars().all()

    return JobListResponse(
        jobs=[
            JobResponse(
                id=j.id,
                project_id=j.project_id,
                status=j.status.value,
                status_message=j.status_message,
                total_requirements=j.total_requirements,
                total_tasks=j.total_tasks,
                tasks_completed=j.tasks_completed,
                tasks_failed=j.tasks_failed,
                progress_percent=j.progress_percent,
                dag_nodes=j.dag_nodes,
                dag_edges=j.dag_edges,
                created_at=j.created_at.isoformat(),
                updated_at=j.updated_at.isoformat(),
            )
            for j in jobs
        ],
        total=total,
    )


@router.get("/{job_id}", response_model=JobDetailResponse)
async def get_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get job details including tasks."""
    result = await db.execute(
        select(Job).where(Job.id == job_id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=404,
            detail=f"Job {job_id} not found",
        )

    # Get tasks
    tasks_result = await db.execute(
        select(Task).where(Task.job_id == job_id).order_by(Task.depth_level)
    )
    tasks = tasks_result.scalars().all()

    return JobDetailResponse(
        id=job.id,
        project_id=job.project_id,
        status=job.status.value,
        status_message=job.status_message,
        total_requirements=job.total_requirements,
        total_tasks=job.total_tasks,
        tasks_completed=job.tasks_completed,
        tasks_failed=job.tasks_failed,
        progress_percent=job.progress_percent,
        dag_nodes=job.dag_nodes,
        dag_edges=job.dag_edges,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
        tasks=[
            {
                "id": t.id,
                "task_id": t.task_id,
                "title": t.title,
                "task_type": t.task_type.value,
                "status": t.status.value,
                "depth_level": t.depth_level,
                "depends_on": t.depends_on,
            }
            for t in tasks
        ],
    )


@router.get("/{job_id}/status")
async def get_job_status(
    job_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get real-time job status and progress."""
    orchestrator = Orchestrator(db)
    await orchestrator.initialize()

    try:
        status = await orchestrator.get_job_status(job_id)
    finally:
        await orchestrator.shutdown()

    if not status:
        raise HTTPException(
            status_code=404,
            detail=f"Job {job_id} not found",
        )

    return status


@router.get("/{job_id}/results")
async def get_job_results(
    job_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get results for a completed job."""
    orchestrator = Orchestrator(db)

    results = await orchestrator.get_job_results(job_id)

    if not results["tasks"]:
        raise HTTPException(
            status_code=404,
            detail=f"Job {job_id} not found or has no results",
        )

    return results


@router.post("/{job_id}/cancel", status_code=status.HTTP_200_OK)
async def cancel_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Cancel a running job."""
    result = await db.execute(
        select(Job).where(Job.id == job_id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=404,
            detail=f"Job {job_id} not found",
        )

    if job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel job with status: {job.status.value}",
        )

    job.status = JobStatus.CANCELLED
    job.status_message = "Cancelled by user"
    await db.commit()

    return {"message": f"Job {job_id} cancelled"}
