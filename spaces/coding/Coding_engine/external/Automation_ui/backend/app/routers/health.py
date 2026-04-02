"""
Health Check Router for TRAE Backend

Provides health check endpoints for service monitoring.
"""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from ..exceptions import ServiceError
from ..logger_config import get_logger, log_api_request
from ..services import get_service_manager

logger = get_logger("health")

router = APIRouter()


@router.get("/health")
@log_api_request(logger)
async def health_check(request: Request):
    """System health check"""
    try:
        # Get service manager from app state
        service_manager = request.app.state.service_manager

        # Get health status of all services
        services_status = service_manager.get_health_status()
        all_healthy = service_manager.is_healthy()

        # Get service list
        service_list = service_manager.get_service_list()

        health_data = {
            "status": "healthy" if all_healthy else "degraded",
            "services": services_status,
            "service_count": len(service_list),
            "timestamp": datetime.utcnow().isoformat(),
            "version": "1.0.0",
        }

        status_code = 200 if all_healthy else 503

        return JSONResponse(status_code=status_code, content=health_data)

    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Health check system unavailable")


@router.get("/health/detailed")
@log_api_request(logger)
async def detailed_health_check(request: Request):
    """Detailed health check with service information"""
    try:
        # Get service manager from app state
        service_manager = request.app.state.service_manager

        # Get detailed service information
        detailed_status = {}

        for service_name in service_manager.get_service_list():
            try:
                service = service_manager.get_service(service_name)
                service_health = service_manager.is_service_healthy(service_name)

                service_info = {
                    "healthy": service_health,
                    "status": "operational" if service_health else "degraded",
                }

                # Add service-specific details if available
                if hasattr(service, "get_status"):
                    try:
                        service_status = await service.get_status()
                        service_info.update(service_status)
                    except Exception:
                        pass

                detailed_status[service_name] = service_info

            except Exception as e:
                detailed_status[service_name] = {
                    "healthy": False,
                    "status": "error",
                    "error": str(e),
                }

        all_healthy = all(
            info.get("healthy", False) for info in detailed_status.values()
        )

        health_data = {
            "status": "healthy" if all_healthy else "degraded",
            "services": detailed_status,
            "service_count": len(detailed_status),
            "healthy_count": sum(
                1 for info in detailed_status.values() if info.get("healthy", False)
            ),
            "timestamp": datetime.utcnow().isoformat(),
            "version": "1.0.0",
        }

        status_code = 200 if all_healthy else 503

        return JSONResponse(status_code=status_code, content=health_data)

    except Exception as e:
        logger.error(f"Detailed health check failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Health check system unavailable")


@router.get("/health/services/{service_name}")
@log_api_request(logger)
async def service_health_check(service_name: str, request: Request):
    """Check health of a specific service"""
    try:
        # Get service manager from app state
        service_manager = request.app.state.service_manager

        if not service_manager.has_service(service_name):
            raise HTTPException(
                status_code=404, detail=f"Service '{service_name}' not found"
            )

        service = service_manager.get_service(service_name)
        service_healthy = service_manager.is_service_healthy(service_name)

        service_info = {
            "service_name": service_name,
            "healthy": service_healthy,
            "status": "operational" if service_healthy else "degraded",
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Add service-specific details if available
        if hasattr(service, "get_status"):
            try:
                service_status = await service.get_status()
                service_info.update(service_status)
            except Exception as e:
                service_info["status_error"] = str(e)

        status_code = 200 if service_healthy else 503

        return JSONResponse(status_code=status_code, content=service_info)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Service health check failed for {service_name}: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check health of service '{service_name}'",
        )


@router.post("/health/services/{service_name}/restart")
@log_api_request(logger)
async def restart_service(service_name: str, request: Request):
    """Restart a specific service"""
    try:
        # Get service manager from app state
        service_manager = request.app.state.service_manager

        if not service_manager.has_service(service_name):
            raise HTTPException(
                status_code=404, detail=f"Service '{service_name}' not found"
            )

        # Restart the service
        await service_manager.restart_service(service_name)

        # Check new health status
        service_healthy = service_manager.is_service_healthy(service_name)

        return JSONResponse(
            status_code=200,
            content={
                "service_name": service_name,
                "action": "restart",
                "success": True,
                "healthy": service_healthy,
                "message": f"Service '{service_name}' restarted successfully",
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    except HTTPException:
        raise
    except ServiceError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to restart service '{service_name}': {e.message}",
        )
    except Exception as e:
        logger.error(f"Service restart failed for {service_name}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to restart service '{service_name}'"
        )
