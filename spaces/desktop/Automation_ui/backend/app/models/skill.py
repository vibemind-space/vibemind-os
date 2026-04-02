"""
Skill Data Models for ClawHub.ai Integration

Pydantic models for skill metadata, installation state,
and execution parameters.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SkillCategory(str, Enum):
    """Skill categories from ClawHub."""
    AUTOMATION = "automation"
    BROWSER = "browser"
    DESKTOP = "desktop"
    FILE_MANAGEMENT = "file_management"
    DEVELOPMENT = "development"
    DATA = "data"
    COMMUNICATION = "communication"
    AI_ML = "ai_ml"
    SYSTEM = "system"
    CUSTOM = "custom"


class SkillStatus(str, Enum):
    """Local installation status."""
    AVAILABLE = "available"
    INSTALLED = "installed"
    UPDATING = "updating"
    ERROR = "error"


class SkillPermission(str, Enum):
    """Permissions a skill can request."""
    FILESYSTEM = "filesystem"
    NETWORK = "network"
    DESKTOP_CONTROL = "desktop_control"
    SHELL = "shell"
    BROWSER = "browser"
    CLIPBOARD = "clipboard"
    SCREENSHOT = "screenshot"
    OCR = "ocr"


class SkillSummary(BaseModel):
    """Compact skill representation for list views."""
    id: str
    name: str
    description: str
    version: str
    author: str
    category: SkillCategory = SkillCategory.CUSTOM
    tags: List[str] = Field(default_factory=list)
    install_count: int = 0
    rating: float = 0.0
    icon: Optional[str] = None
    installed: bool = False


class SkillDetail(SkillSummary):
    """Full skill details for detail views."""
    long_description: Optional[str] = None
    permissions: List[SkillPermission] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    code_bundle_url: Optional[str] = None
    documentation_url: Optional[str] = None
    repository_url: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    changelog: Optional[str] = None


class InstalledSkill(BaseModel):
    """Locally installed skill with runtime metadata."""
    id: str
    name: str
    description: str
    version: str
    author: str
    category: SkillCategory = SkillCategory.CUSTOM
    tags: List[str] = Field(default_factory=list)
    permissions: List[SkillPermission] = Field(default_factory=list)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    status: SkillStatus = SkillStatus.INSTALLED
    enabled: bool = True
    installed_at: datetime = Field(default_factory=datetime.utcnow)
    last_executed: Optional[datetime] = None
    execution_count: int = 0
    local_path: Optional[str] = None


class SkillSearchRequest(BaseModel):
    """Search request for ClawHub skills."""
    query: str = Field(..., min_length=1, description="Search query")
    category: Optional[SkillCategory] = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    sort_by: str = Field(default="relevance", description="relevance, rating, installs, newest")


class SkillSearchResponse(BaseModel):
    """Search response with paginated results."""
    query: str
    total: int
    skills: List[SkillSummary]
    offset: int
    limit: int


class SkillInstallRequest(BaseModel):
    """Request to install a skill."""
    skill_id: str
    version: Optional[str] = None


class SkillExecuteRequest(BaseModel):
    """Request to execute an installed skill."""
    skill_id: str
    params: Dict[str, Any] = Field(default_factory=dict)
    user_id: str = "web_user"
    platform: str = "web"


class SkillExecuteResponse(BaseModel):
    """Response from skill execution."""
    success: bool
    skill_id: str
    message: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_time_ms: float = 0
