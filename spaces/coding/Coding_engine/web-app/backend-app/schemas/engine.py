# backend/app/schemas/engine.py
from pydantic import BaseModel
from typing import Optional
from enum import Enum


class EngineProjectType(str, Enum):
    ENGINE = "engine"
    VIBE = "vibe"


class AgentStatus(str, Enum):
    RUNNING = "running"
    DONE = "done"
    QUEUED = "queued"
    FAILED = "failed"


class GenerationPhase(str, Enum):
    IDLE = "idle"
    PARSING = "parsing"
    SKELETON = "skeleton"
    GENERATION = "generation"
    VALIDATION = "validation"
    INTEGRATION = "integration"
    COMPLETE = "complete"
    FAILED = "failed"


class EngineProjectSummary(BaseModel):
    name: str
    path: str
    service_count: int = 0
    endpoint_count: int = 0
    story_count: int = 0
    type: EngineProjectType = EngineProjectType.ENGINE


class EngineProjectDetail(EngineProjectSummary):
    services: list[dict] = []
    generation_order: list[str] = []
    dependency_graph: dict[str, list[str]] = {}


class AgentInfo(BaseModel):
    name: str
    status: AgentStatus
    task: str = ""
    elapsed_seconds: float = 0


class EpicInfo(BaseModel):
    id: str
    name: str
    progress_pct: int = 0
    tasks_total: int = 0
    tasks_complete: int = 0


class GenerationStatus(BaseModel):
    project_name: str
    phase: GenerationPhase = GenerationPhase.IDLE
    progress_pct: int = 0
    agents: list[AgentInfo] = []
    epics: list[EpicInfo] = []
    service_count: int = 0
    endpoint_count: int = 0


class StartGenerationRequest(BaseModel):
    skeleton_only: bool = False
    service: Optional[str] = None
