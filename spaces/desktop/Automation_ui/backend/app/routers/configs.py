"""
Configs Router - Live Desktop Configuration Management

CRUD API for managing desktop streaming configurations.
Replaces Supabase REST API with local PostgreSQL backend.
"""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.logger_config import get_logger
from app.models.db_models import LiveDesktopConfig

logger = get_logger("configs_router")

router = APIRouter()


# Pydantic schemas for request/response
class ConfigCreate(BaseModel):
    """Schema for creating a new configuration"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    category: Optional[str] = Field(None, max_length=100)
    configuration: dict = Field(default_factory=dict)
    is_active: bool = True
    tags: List[str] = Field(default_factory=list)
    created_by: Optional[str] = None


class ConfigUpdate(BaseModel):
    """Schema for updating a configuration"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    category: Optional[str] = Field(None, max_length=100)
    configuration: Optional[dict] = None
    is_active: Optional[bool] = None
    tags: Optional[List[str]] = None


class ConfigResponse(BaseModel):
    """Schema for configuration response"""
    id: str
    name: str
    description: Optional[str]
    category: Optional[str]
    configuration: dict
    is_active: bool
    created_at: Optional[str]
    updated_at: Optional[str]
    created_by: Optional[str]
    tags: List[str]

    class Config:
        from_attributes = True


@router.get("/", response_model=List[ConfigResponse])
async def list_configs(
    category: Optional[str] = None,
    is_active: Optional[bool] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    List all configurations with optional filtering.

    - **category**: Filter by category
    - **is_active**: Filter by active status
    """
    try:
        query = select(LiveDesktopConfig).order_by(LiveDesktopConfig.updated_at.desc())

        if category:
            query = query.where(LiveDesktopConfig.category == category)
        if is_active is not None:
            query = query.where(LiveDesktopConfig.is_active == is_active)

        result = await db.execute(query)
        configs = result.scalars().all()

        return [ConfigResponse(**config.to_dict()) for config in configs]
    except Exception as e:
        logger.error(f"Failed to list configs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list configurations: {str(e)}"
        )


@router.get("/active", response_model=List[ConfigResponse])
async def list_active_configs(db: AsyncSession = Depends(get_db)):
    """Get all active configurations"""
    try:
        result = await db.execute(
            select(LiveDesktopConfig)
            .where(LiveDesktopConfig.is_active == True)
            .order_by(LiveDesktopConfig.updated_at.desc())
        )
        configs = result.scalars().all()
        return [ConfigResponse(**config.to_dict()) for config in configs]
    except Exception as e:
        logger.error(f"Failed to list active configs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list active configurations: {str(e)}"
        )


@router.get("/{config_id}", response_model=ConfigResponse)
async def get_config(config_id: UUID, db: AsyncSession = Depends(get_db)):
    """Get a specific configuration by ID"""
    try:
        result = await db.execute(
            select(LiveDesktopConfig).where(LiveDesktopConfig.id == config_id)
        )
        config = result.scalar_one_or_none()

        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Configuration with ID {config_id} not found"
            )

        return ConfigResponse(**config.to_dict())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get config {config_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get configuration: {str(e)}"
        )


@router.post("/", response_model=ConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_config(config: ConfigCreate, db: AsyncSession = Depends(get_db)):
    """Create a new configuration"""
    try:
        db_config = LiveDesktopConfig(
            name=config.name,
            description=config.description,
            category=config.category,
            configuration=config.configuration,
            is_active=config.is_active,
            tags=config.tags,
            created_by=config.created_by
        )

        db.add(db_config)
        await db.commit()
        await db.refresh(db_config)

        logger.info(f"Created config: {db_config.id} - {db_config.name}")
        return ConfigResponse(**db_config.to_dict())
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to create config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create configuration: {str(e)}"
        )


@router.put("/{config_id}", response_model=ConfigResponse)
async def update_config(
    config_id: UUID,
    config: ConfigUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update an existing configuration"""
    try:
        # Check if config exists
        result = await db.execute(
            select(LiveDesktopConfig).where(LiveDesktopConfig.id == config_id)
        )
        existing = result.scalar_one_or_none()

        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Configuration with ID {config_id} not found"
            )

        # Update only provided fields
        update_data = {k: v for k, v in config.model_dump().items() if v is not None}

        if update_data:
            await db.execute(
                update(LiveDesktopConfig)
                .where(LiveDesktopConfig.id == config_id)
                .values(**update_data)
            )
            await db.commit()

        # Refresh and return
        await db.refresh(existing)
        logger.info(f"Updated config: {config_id}")
        return ConfigResponse(**existing.to_dict())
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to update config {config_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update configuration: {str(e)}"
        )


@router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_config(config_id: UUID, db: AsyncSession = Depends(get_db)):
    """Delete a configuration"""
    try:
        # Check if config exists
        result = await db.execute(
            select(LiveDesktopConfig).where(LiveDesktopConfig.id == config_id)
        )
        existing = result.scalar_one_or_none()

        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Configuration with ID {config_id} not found"
            )

        await db.execute(
            delete(LiveDesktopConfig).where(LiveDesktopConfig.id == config_id)
        )
        await db.commit()

        logger.info(f"Deleted config: {config_id}")
        return None
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to delete config {config_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete configuration: {str(e)}"
        )


@router.post("/{config_id}/duplicate", response_model=ConfigResponse, status_code=status.HTTP_201_CREATED)
async def duplicate_config(config_id: UUID, db: AsyncSession = Depends(get_db)):
    """Duplicate an existing configuration"""
    try:
        # Get original config
        result = await db.execute(
            select(LiveDesktopConfig).where(LiveDesktopConfig.id == config_id)
        )
        original = result.scalar_one_or_none()

        if not original:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Configuration with ID {config_id} not found"
            )

        # Create duplicate
        duplicate = LiveDesktopConfig(
            name=f"{original.name} (Copy)",
            description=original.description,
            category=original.category,
            configuration=original.configuration,
            is_active=False,  # Duplicates start as inactive
            tags=original.tags,
            created_by=original.created_by
        )

        db.add(duplicate)
        await db.commit()
        await db.refresh(duplicate)

        logger.info(f"Duplicated config {config_id} to {duplicate.id}")
        return ConfigResponse(**duplicate.to_dict())
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to duplicate config {config_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to duplicate configuration: {str(e)}"
        )
