"""Artifact management endpoints."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.models.base import get_db
from src.models.artifact import Artifact, ArtifactType

router = APIRouter()


# Response schemas
class ArtifactResponse(BaseModel):
    """Schema for artifact response."""
    id: int
    project_id: int
    job_id: Optional[int]
    task_id: Optional[str]
    artifact_type: str
    name: str
    description: Optional[str]
    file_path: Optional[str]
    file_size_bytes: Optional[int]
    version: str
    git_commit: Optional[str]
    deployment_url: Optional[str]
    deployment_status: Optional[str]
    created_at: str


class ArtifactListResponse(BaseModel):
    """Schema for artifact list response."""
    artifacts: list[ArtifactResponse]
    total: int


# Endpoints
@router.get("", response_model=ArtifactListResponse)
async def list_artifacts(
    project_id: Optional[int] = None,
    job_id: Optional[int] = None,
    artifact_type: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """
    List artifacts with optional filtering.
    """
    query = select(Artifact)

    if project_id:
        query = query.where(Artifact.project_id == project_id)

    if job_id:
        query = query.where(Artifact.job_id == job_id)

    if artifact_type:
        try:
            type_enum = ArtifactType(artifact_type)
            query = query.where(Artifact.artifact_type == type_enum)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid artifact type: {artifact_type}",
            )

    # Get total count
    count_result = await db.execute(query)
    total = len(count_result.scalars().all())

    # Get paginated results
    query = query.offset(skip).limit(limit).order_by(Artifact.created_at.desc())
    result = await db.execute(query)
    artifacts = result.scalars().all()

    return ArtifactListResponse(
        artifacts=[
            ArtifactResponse(
                id=a.id,
                project_id=a.project_id,
                job_id=a.job_id,
                task_id=a.task_id,
                artifact_type=a.artifact_type.value,
                name=a.name,
                description=a.description,
                file_path=a.file_path,
                file_size_bytes=a.file_size_bytes,
                version=a.version,
                git_commit=a.git_commit,
                deployment_url=a.deployment_url,
                deployment_status=a.deployment_status,
                created_at=a.created_at.isoformat(),
            )
            for a in artifacts
        ],
        total=total,
    )


@router.get("/{artifact_id}", response_model=ArtifactResponse)
async def get_artifact(
    artifact_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get artifact details."""
    result = await db.execute(
        select(Artifact).where(Artifact.id == artifact_id)
    )
    artifact = result.scalar_one_or_none()

    if not artifact:
        raise HTTPException(
            status_code=404,
            detail=f"Artifact {artifact_id} not found",
        )

    return ArtifactResponse(
        id=artifact.id,
        project_id=artifact.project_id,
        job_id=artifact.job_id,
        task_id=artifact.task_id,
        artifact_type=artifact.artifact_type.value,
        name=artifact.name,
        description=artifact.description,
        file_path=artifact.file_path,
        file_size_bytes=artifact.file_size_bytes,
        version=artifact.version,
        git_commit=artifact.git_commit,
        deployment_url=artifact.deployment_url,
        deployment_status=artifact.deployment_status,
        created_at=artifact.created_at.isoformat(),
    )


@router.get("/{artifact_id}/content")
async def get_artifact_content(
    artifact_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get artifact content (for inline-stored artifacts)."""
    result = await db.execute(
        select(Artifact).where(Artifact.id == artifact_id)
    )
    artifact = result.scalar_one_or_none()

    if not artifact:
        raise HTTPException(
            status_code=404,
            detail=f"Artifact {artifact_id} not found",
        )

    if artifact.content:
        return PlainTextResponse(content=artifact.content)

    if artifact.file_path:
        # In production, this would read from storage
        return {"message": "File artifacts not yet supported", "file_path": artifact.file_path}

    raise HTTPException(
        status_code=404,
        detail="Artifact has no content",
    )


@router.delete("/{artifact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_artifact(
    artifact_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete an artifact."""
    result = await db.execute(
        select(Artifact).where(Artifact.id == artifact_id)
    )
    artifact = result.scalar_one_or_none()

    if not artifact:
        raise HTTPException(
            status_code=404,
            detail=f"Artifact {artifact_id} not found",
        )

    await db.delete(artifact)
    await db.commit()


@router.get("/types/list")
async def list_artifact_types():
    """List available artifact types."""
    return {
        "types": [t.value for t in ArtifactType]
    }
