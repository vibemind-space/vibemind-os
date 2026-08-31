"""Pydantic models for Bridge API requests and responses."""

from typing import Optional
from pydantic import BaseModel, Field


class BridgeRequest(BaseModel):
    task: str = Field(..., description="The task to route and execute")
    context: Optional[dict] = Field(None, description="Additional context")
    event_type: Optional[str] = Field(None, description="Pre-classified event type")
    fire_and_forget: bool = Field(False, description="Return immediately with task_id")
    timeout_secs: Optional[int] = Field(None, description="Override default timeout")


class RoutingInfo(BaseModel):
    primary_space: str
    secondary_spaces: list[str] = []
    confidence: float
    routing_id: str


class BridgeResponse(BaseModel):
    task_id: str
    status: str  # pending, working, completed, failed
    result: Optional[str] = None
    routing: RoutingInfo
    agent: str
    latency_ms: float = 0.0


class TaskStatus(BaseModel):
    task_id: str
    status: str  # pending, working, completed, failed
    result: Optional[str] = None
    error: Optional[str] = None
    routing: Optional[RoutingInfo] = None
    agent: Optional[str] = None
