"""
ClawHub API Router

REST API endpoints for the ClawHub.ai Skill Marketplace integration.
Provides skill search, installation, management, and execution.

Endpoints:
- GET  /search         - Search ClawHub skills
- GET  /trending       - Get trending skills
- GET  /categories     - List skill categories
- GET  /skill/{id}     - Get skill details
- GET  /installed      - List installed skills
- POST /install        - Install a skill
- POST /uninstall      - Uninstall a skill
- POST /execute        - Execute a skill
- POST /toggle         - Enable/disable a skill
- GET  /stats          - Skill manager statistics
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..models.skill import (
    InstalledSkill,
    SkillCategory,
    SkillDetail,
    SkillExecuteRequest,
    SkillExecuteResponse,
    SkillInstallRequest,
    SkillSearchResponse,
    SkillSummary,
)
from ..services.clawhub_client import get_clawhub_client
from ..services.skill_manager import get_skill_manager

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# Request/Response Models
# ============================================================================


class UninstallRequest(BaseModel):
    skill_id: str


class ToggleRequest(BaseModel):
    skill_id: str
    enabled: bool


class InstallResponse(BaseModel):
    status: str
    skill: InstalledSkill


# ============================================================================
# Search & Discovery Endpoints
# ============================================================================


@router.get("/search", response_model=SkillSearchResponse)
async def search_skills(
    q: str = Query("", description="Search query"),
    category: Optional[SkillCategory] = Query(None, description="Filter by category"),
    limit: int = Query(20, ge=1, le=100, description="Results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    sort_by: str = Query("relevance", description="Sort: relevance, rating, installs, newest"),
):
    """
    Search ClawHub.ai skill marketplace.

    Returns skills matching the query with relevance scoring.
    Marks already-installed skills in the response.
    """
    client = get_clawhub_client()
    result = await client.search_skills(q, category, limit, offset, sort_by)

    # Mark installed skills
    manager = get_skill_manager()
    for skill in result.skills:
        skill.installed = manager.is_installed(skill.id)

    return result


@router.get("/trending", response_model=List[SkillSummary])
async def get_trending(
    limit: int = Query(10, ge=1, le=50, description="Number of trending skills"),
):
    """Get trending/popular skills from ClawHub."""
    client = get_clawhub_client()
    skills = await client.get_trending(limit)

    manager = get_skill_manager()
    for skill in skills:
        skill.installed = manager.is_installed(skill.id)

    return skills


@router.get("/categories")
async def get_categories():
    """List all skill categories with counts."""
    client = get_clawhub_client()
    return await client.get_categories()


@router.get("/skill/{skill_id}", response_model=SkillDetail)
async def get_skill_detail(skill_id: str):
    """
    Get detailed information about a specific skill.

    Returns full skill metadata including parameters, permissions, and changelog.
    """
    client = get_clawhub_client()
    skill = await client.get_skill(skill_id)

    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found")

    # Add installed flag
    manager = get_skill_manager()
    skill.installed = manager.is_installed(skill.id)

    return skill


# ============================================================================
# Installation & Management Endpoints
# ============================================================================


@router.get("/installed", response_model=List[InstalledSkill])
async def list_installed():
    """List all locally installed skills."""
    manager = get_skill_manager()
    return manager.list_installed()


@router.post("/install", response_model=InstallResponse)
async def install_skill(request: SkillInstallRequest):
    """
    Install a skill from ClawHub.

    Downloads the skill metadata and code bundle (when available)
    and registers it locally.
    """
    manager = get_skill_manager()

    # Check if already installed
    if manager.is_installed(request.skill_id):
        existing = manager.get_installed(request.skill_id)
        return InstallResponse(status="already_installed", skill=existing)

    # Fetch skill details from ClawHub
    client = get_clawhub_client()
    skill = await client.get_skill(request.skill_id)

    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{request.skill_id}' not found on ClawHub")

    # Install locally
    installed = await manager.install_skill(skill)

    logger.info(f"Skill installed: {request.skill_id}")
    return InstallResponse(status="installed", skill=installed)


@router.post("/uninstall")
async def uninstall_skill(request: UninstallRequest):
    """Uninstall a locally installed skill."""
    manager = get_skill_manager()

    if not manager.is_installed(request.skill_id):
        raise HTTPException(status_code=404, detail=f"Skill '{request.skill_id}' not installed")

    success = await manager.uninstall_skill(request.skill_id)

    if not success:
        raise HTTPException(status_code=500, detail="Uninstall failed")

    return {"status": "uninstalled", "skill_id": request.skill_id}


@router.post("/toggle")
async def toggle_skill(request: ToggleRequest):
    """Enable or disable an installed skill."""
    manager = get_skill_manager()

    skill = await manager.toggle_skill(request.skill_id, request.enabled)

    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{request.skill_id}' not installed")

    return {
        "status": "toggled",
        "skill_id": request.skill_id,
        "enabled": skill.enabled,
    }


# ============================================================================
# Execution Endpoint
# ============================================================================


@router.post("/execute", response_model=SkillExecuteResponse)
async def execute_skill(request: SkillExecuteRequest):
    """
    Execute an installed skill with given parameters.

    The skill must be installed and enabled. Parameters are passed
    to the skill's execute() function.
    """
    manager = get_skill_manager()

    result = await manager.execute_skill(request.skill_id, request.params)
    return result


# ============================================================================
# Stats Endpoint
# ============================================================================


@router.get("/stats")
async def get_stats():
    """Get skill manager statistics."""
    manager = get_skill_manager()
    return manager.get_stats()
