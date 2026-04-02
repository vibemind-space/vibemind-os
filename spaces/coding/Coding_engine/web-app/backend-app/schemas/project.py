from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from pydantic import BaseModel

from app.models.project import ProjectStatus

if TYPE_CHECKING:
    from app.schemas.file import ProjectFile as ProjectFileType
else:
    ProjectFileType = "ProjectFile"


class ProjectBase(BaseModel):
    name: str
    description: Optional[str] = None
    template: str = "react-vite"
    framework: str = "react"


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[ProjectStatus] = None
    template: Optional[str] = None
    framework: Optional[str] = None
    is_favorite: Optional[bool] = None


class ProjectInDB(ProjectBase):
    id: int
    status: ProjectStatus
    owner_id: int
    created_at: datetime
    updated_at: datetime
    thumbnail: Optional[str] = None
    is_favorite: bool = False

    class Config:
        from_attributes = True


class Project(ProjectInDB):
    pass


class ProjectSummary(BaseModel):
    """Lightweight project schema for list views (excludes thumbnail for performance)"""
    id: int
    name: str
    description: Optional[str] = None
    status: ProjectStatus
    owner_id: int
    created_at: datetime
    updated_at: datetime
    template: str = "react-vite"
    framework: str = "react"
    is_favorite: bool = False

    class Config:
        from_attributes = True


class ProjectWithFiles(Project):
    files: List[ProjectFileType] = []
