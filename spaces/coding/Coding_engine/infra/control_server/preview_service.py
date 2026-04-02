"""
Preview Service - API layer for managing preview deployments.

This service:
1. Manages PreviewAgent instances for different projects
2. Provides REST API endpoints for the Control Server
3. Handles 30-second timer orchestration
4. Broadcasts preview status via EventBus
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
import structlog

from src.agents.preview_agent import PreviewAgent, PreviewState, PreviewStatus
from src.mind.event_bus import EventBus, Event, EventType


logger = structlog.get_logger(__name__)


@dataclass
class PreviewInstance:
    """A managed preview instance."""
    project_id: str
    working_dir: str
    agent: PreviewAgent
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "working_dir": self.working_dir,
            "created_at": self.created_at.isoformat(),
            "status": self.agent.get_status(),
        }


class PreviewService:
    """
    Service for managing multiple preview deployments.
    
    Provides:
    - Create/start/stop preview instances
    - Status retrieval for all previews
    - Integration with EventBus for real-time updates
    - REST API compatible methods
    """
    
    def __init__(self, event_bus: Optional[EventBus] = None):
        self.event_bus = event_bus or EventBus()
        self._instances: Dict[str, PreviewInstance] = {}
        self._lock = asyncio.Lock()
        
        self.logger = logger.bind(component="preview_service")
        
        # Subscribe to preview events
        self.event_bus.subscribe(EventType.PREVIEW_READY, self._on_preview_ready)
        self.event_bus.subscribe(EventType.DEPLOY_FAILED, self._on_deploy_failed)
    
    async def _on_preview_ready(self, event: Event) -> None:
        """Handle preview ready events."""
        self.logger.info("preview_ready", data=event.data)
    
    async def _on_deploy_failed(self, event: Event) -> None:
        """Handle deployment failure events."""
        self.logger.error("deploy_failed", data=event.data)
    
    async def create_preview(
        self,
        project_id: str,
        working_dir: str,
        port: int = 3000,
        auto_deploy: bool = True,
        timer_interval: float = 30.0,
    ) -> Dict[str, Any]:
        """
        Create a new preview instance.
        
        Args:
            project_id: Unique identifier for the project
            working_dir: Project working directory
            port: Starting port for dev server
            auto_deploy: Start deployment immediately
            timer_interval: Health check interval in seconds
            
        Returns:
            Preview instance status
        """
        async with self._lock:
            # Check if instance already exists
            if project_id in self._instances:
                self.logger.warning("preview_already_exists", project_id=project_id)
                return {
                    "success": False,
                    "error": f"Preview for project {project_id} already exists",
                    "status": self._instances[project_id].to_dict(),
                }
            
            # Create preview agent
            agent = PreviewAgent(
                working_dir=working_dir,
                event_bus=self.event_bus,
                port=port,
                timer_interval=timer_interval,
                auto_start_timer=auto_deploy,
            )
            
            # Create instance
            instance = PreviewInstance(
                project_id=project_id,
                working_dir=working_dir,
                agent=agent,
            )
            
            self._instances[project_id] = instance
            
            self.logger.info(
                "preview_created",
                project_id=project_id,
                working_dir=working_dir,
            )
        
        # Start deployment if requested
        if auto_deploy:
            asyncio.create_task(self._deploy_preview(project_id))
        
        return {
            "success": True,
            "project_id": project_id,
            "status": instance.to_dict(),
        }
    
    async def _deploy_preview(self, project_id: str) -> None:
        """Background task to deploy a preview."""
        instance = self._instances.get(project_id)
        if not instance:
            return
        
        try:
            success = await instance.agent.start()
            
            if success:
                self.logger.info("preview_deployed", project_id=project_id)
            else:
                self.logger.error(
                    "preview_deploy_failed",
                    project_id=project_id,
                    error=instance.agent.status.error,
                )
        except Exception as e:
            self.logger.error("preview_deploy_error", project_id=project_id, error=str(e))
    
    async def deploy_with_claude(
        self,
        project_id: str,
        instructions: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Deploy using Claude Code CLI with custom instructions.
        
        Args:
            project_id: Project identifier
            instructions: Custom deployment instructions for Claude
            
        Returns:
            Deployment result
        """
        instance = self._instances.get(project_id)
        if not instance:
            return {
                "success": False,
                "error": f"Preview {project_id} not found",
            }
        
        try:
            success = await instance.agent.deploy_with_claude(instructions)
            
            return {
                "success": success,
                "project_id": project_id,
                "status": instance.agent.get_status(),
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }
    
    async def stop_preview(self, project_id: str) -> Dict[str, Any]:
        """
        Stop a preview instance.
        
        Args:
            project_id: Project identifier
            
        Returns:
            Result of stop operation
        """
        async with self._lock:
            instance = self._instances.get(project_id)
            if not instance:
                return {
                    "success": False,
                    "error": f"Preview {project_id} not found",
                }
            
            await instance.agent.stop()
            
            self.logger.info("preview_stopped", project_id=project_id)
            
            return {
                "success": True,
                "project_id": project_id,
                "status": instance.agent.get_status(),
            }
    
    async def delete_preview(self, project_id: str) -> Dict[str, Any]:
        """
        Stop and delete a preview instance.
        
        Args:
            project_id: Project identifier
            
        Returns:
            Result of delete operation
        """
        async with self._lock:
            instance = self._instances.get(project_id)
            if not instance:
                return {
                    "success": False,
                    "error": f"Preview {project_id} not found",
                }
            
            await instance.agent.stop()
            del self._instances[project_id]
            
            self.logger.info("preview_deleted", project_id=project_id)
            
            return {
                "success": True,
                "project_id": project_id,
            }
    
    async def restart_preview(self, project_id: str) -> Dict[str, Any]:
        """
        Restart a preview instance.
        
        Args:
            project_id: Project identifier
            
        Returns:
            Result of restart operation
        """
        instance = self._instances.get(project_id)
        if not instance:
            return {
                "success": False,
                "error": f"Preview {project_id} not found",
            }
        
        await instance.agent.stop()
        success = await instance.agent.start()
        
        return {
            "success": success,
            "project_id": project_id,
            "status": instance.agent.get_status(),
        }
    
    def get_status(self, project_id: str) -> Dict[str, Any]:
        """
        Get status of a preview instance.
        
        Args:
            project_id: Project identifier
            
        Returns:
            Preview status
        """
        instance = self._instances.get(project_id)
        if not instance:
            return {
                "found": False,
                "error": f"Preview {project_id} not found",
            }
        
        return {
            "found": True,
            "project_id": project_id,
            **instance.to_dict(),
        }
    
    def list_previews(self) -> Dict[str, Any]:
        """
        List all preview instances.
        
        Returns:
            Dictionary with all previews
        """
        return {
            "count": len(self._instances),
            "previews": [
                instance.to_dict()
                for instance in self._instances.values()
            ],
        }
    
    async def get_health(self, project_id: str) -> Dict[str, Any]:
        """
        Perform a health check on a preview.
        
        Args:
            project_id: Project identifier
            
        Returns:
            Health check result
        """
        instance = self._instances.get(project_id)
        if not instance:
            return {
                "healthy": False,
                "error": f"Preview {project_id} not found",
            }
        
        is_healthy = await instance.agent._check_health()
        
        return {
            "healthy": is_healthy,
            "project_id": project_id,
            "status": instance.agent.get_status(),
        }
    
    async def trigger_timer_check(self, project_id: str) -> Dict[str, Any]:
        """
        Manually trigger a timer health check.
        
        This can be called to force a 30-second check immediately.
        
        Args:
            project_id: Project identifier
            
        Returns:
            Result of health check
        """
        instance = self._instances.get(project_id)
        if not instance:
            return {
                "success": False,
                "error": f"Preview {project_id} not found",
            }
        
        # Perform health check
        is_healthy = await instance.agent._check_health()
        
        # Publish event
        await self.event_bus.publish(Event(
            type=EventType.CONVERGENCE_UPDATE,
            source="preview_service",
            data={
                "project_id": project_id,
                "manual_trigger": True,
                "preview_status": instance.agent.get_status(),
            },
        ))
        
        return {
            "success": True,
            "healthy": is_healthy,
            "project_id": project_id,
            "status": instance.agent.get_status(),
        }
    
    async def shutdown(self) -> None:
        """Shutdown all preview instances."""
        self.logger.info("shutting_down_all_previews", count=len(self._instances))
        
        for project_id in list(self._instances.keys()):
            await self.delete_preview(project_id)
        
        self.logger.info("all_previews_shutdown")


# Singleton service instance
_preview_service: Optional[PreviewService] = None


def get_preview_service(event_bus: Optional[EventBus] = None) -> PreviewService:
    """
    Get the singleton PreviewService instance.
    
    Args:
        event_bus: Optional event bus (used on first call)
        
    Returns:
        PreviewService instance
    """
    global _preview_service
    
    if _preview_service is None:
        _preview_service = PreviewService(event_bus)
    
    return _preview_service


# FastAPI router for preview endpoints
def create_preview_router():
    """
    Create FastAPI router with preview endpoints.
    
    Usage:
        from fastapi import FastAPI
        from infra.control_server.preview_service import create_preview_router
        
        app = FastAPI()
        app.include_router(create_preview_router(), prefix="/api/preview")
    """
    from fastapi import APIRouter, HTTPException
    from pydantic import BaseModel
    
    router = APIRouter(tags=["preview"])
    
    class CreatePreviewRequest(BaseModel):
        project_id: str
        working_dir: str
        port: int = 3000
        auto_deploy: bool = True
        timer_interval: float = 30.0
    
    class DeployWithClaudeRequest(BaseModel):
        instructions: Optional[str] = None
    
    @router.post("/create")
    async def create_preview(request: CreatePreviewRequest):
        """Create a new preview instance."""
        service = get_preview_service()
        result = await service.create_preview(
            project_id=request.project_id,
            working_dir=request.working_dir,
            port=request.port,
            auto_deploy=request.auto_deploy,
            timer_interval=request.timer_interval,
        )
        return result
    
    @router.post("/{project_id}/deploy-with-claude")
    async def deploy_with_claude(project_id: str, request: DeployWithClaudeRequest):
        """Deploy using Claude Code CLI."""
        service = get_preview_service()
        result = await service.deploy_with_claude(project_id, request.instructions)
        if not result.get("success") and "not found" in str(result.get("error", "")):
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    
    @router.post("/{project_id}/stop")
    async def stop_preview(project_id: str):
        """Stop a preview instance."""
        service = get_preview_service()
        result = await service.stop_preview(project_id)
        if not result.get("success") and "not found" in str(result.get("error", "")):
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    
    @router.delete("/{project_id}")
    async def delete_preview(project_id: str):
        """Delete a preview instance."""
        service = get_preview_service()
        result = await service.delete_preview(project_id)
        if not result.get("success") and "not found" in str(result.get("error", "")):
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    
    @router.post("/{project_id}/restart")
    async def restart_preview(project_id: str):
        """Restart a preview instance."""
        service = get_preview_service()
        result = await service.restart_preview(project_id)
        if not result.get("success") and "not found" in str(result.get("error", "")):
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    
    @router.get("/{project_id}")
    async def get_preview_status(project_id: str):
        """Get status of a preview instance."""
        service = get_preview_service()
        result = service.get_status(project_id)
        if not result.get("found"):
            raise HTTPException(status_code=404, detail=result.get("error"))
        return result
    
    @router.get("/")
    async def list_previews():
        """List all preview instances."""
        service = get_preview_service()
        return service.list_previews()
    
    @router.get("/{project_id}/health")
    async def check_health(project_id: str):
        """Perform health check on a preview."""
        service = get_preview_service()
        result = await service.get_health(project_id)
        if "not found" in str(result.get("error", "")):
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    
    @router.post("/{project_id}/trigger-check")
    async def trigger_timer_check(project_id: str):
        """Manually trigger a 30-second timer check."""
        service = get_preview_service()
        result = await service.trigger_timer_check(project_id)
        if not result.get("success") and "not found" in str(result.get("error", "")):
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    
    return router