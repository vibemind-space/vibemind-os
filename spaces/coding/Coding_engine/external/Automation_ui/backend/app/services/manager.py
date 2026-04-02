"""Service Manager for TRAE Backend

Centralized service management and dependency injection.
"""

import asyncio
from typing import Any, Dict, Optional

from ..logger_config import get_logger

logger = get_logger("service_manager")


class ServiceManager:
    """Manages all backend services and their lifecycle"""

    def __init__(self):
        self.services: Dict[str, Any] = {}
        self.initialized = False

    async def initialize(self):
        """Initialize all services"""
        if self.initialized:
            logger.warning("⚠️ Service manager already initialized")
            return

        try:
            logger.info("🔧 Initializing service manager...")

            # Initialize live desktop service
            from .desktop_service import LiveDesktopService

            self.services["live_desktop"] = LiveDesktopService()
            await self.services["live_desktop"].initialize()
            logger.info("✅ LiveDesktopService initialized")

            # Initialize OCR service (optional - requires cv2/numpy/PIL)
            try:
                from .ocr_service import OCRService

                self.services["ocr"] = OCRService()
                logger.info("✅ OCRService initialized")
            except Exception as ocr_err:
                logger.warning(f"⚠️ OCRService unavailable (non-critical): {ocr_err}")

            self.initialized = True
            logger.info(
                f"✅ Service manager initialized with services: {list(self.services.keys())}"
            )

        except Exception as e:
            logger.error(f"❌ Service manager initialization failed: {e}")
            # Cleanup any partially initialized services
            await self._cleanup_partial_initialization()
            raise

    def get_service(self, service_name: str) -> Optional[Any]:
        """Get service by name"""
        if not self.initialized:
            logger.warning(
                f"⚠️ Service manager not initialized, cannot get service '{service_name}'"
            )
            return None

        service = self.services.get(service_name)
        if service is None:
            logger.warning(
                f"⚠️ Service '{service_name}' not found. Available services: {list(self.services.keys())}"
            )

        return service

    def is_service_available(self, service_name: str) -> bool:
        """Check if a service is available and initialized"""
        return self.initialized and service_name in self.services

    def get_service_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all services"""
        status = {
            "initialized": self.initialized,
            "service_count": len(self.services),
            "services": {},
        }

        for name, service in self.services.items():
            try:
                if hasattr(service, "get_status"):
                    status["services"][name] = service.get_status()
                else:
                    status["services"][name] = {
                        "status": "running",
                        "details": "No status method available",
                    }
            except Exception as e:
                status["services"][name] = {"status": "error", "error": str(e)}

        return status

    def get_health_status(self) -> Dict[str, Any]:
        """Get health status of all services"""
        health_status = {}

        for name, service in self.services.items():
            try:
                if hasattr(service, "is_healthy"):
                    health_status[name] = {
                        "healthy": service.is_healthy(),
                        "status": "operational" if service.is_healthy() else "degraded",
                    }
                else:
                    # Assume healthy if no health check method
                    health_status[name] = {"healthy": True, "status": "operational"}
            except Exception as e:
                health_status[name] = {
                    "healthy": False,
                    "status": "error",
                    "error": str(e),
                }

        return health_status

    def is_healthy(self) -> bool:
        """Check if all services are healthy"""
        if not self.initialized:
            return False

        for name, service in self.services.items():
            try:
                if hasattr(service, "is_healthy") and not service.is_healthy():
                    return False
            except Exception:
                return False

        return True

    def get_service_list(self) -> list:
        """Get list of all service names"""
        return list(self.services.keys())

    def has_service(self, service_name: str) -> bool:
        """Check if service exists"""
        return service_name in self.services

    def is_service_healthy(self, service_name: str) -> bool:
        """Check if a specific service is healthy"""
        if not self.has_service(service_name):
            return False

        service = self.services[service_name]
        try:
            if hasattr(service, "is_healthy"):
                return service.is_healthy()
            else:
                # Assume healthy if no health check method
                return True
        except Exception:
            return False

    async def _cleanup_partial_initialization(self):
        """Cleanup services that were partially initialized during a failed startup"""
        for name, service in list(self.services.items()):
            try:
                if hasattr(service, "cleanup"):
                    await service.cleanup()
                logger.info(f"✅ Cleaned up partially initialized service '{name}'")
            except Exception as e:
                logger.error(f"❌ Error cleaning up service '{name}': {e}")

        self.services.clear()

    async def cleanup(self):
        """Cleanup all services"""
        if not self.initialized:
            logger.info("ℹ️ Service manager not initialized, nothing to cleanup")
            return

        logger.info("🧹 Starting service cleanup...")

        # Cleanup services in reverse order of initialization
        service_items = list(self.services.items())
        for name, service in reversed(service_items):
            try:
                if hasattr(service, "cleanup"):
                    await service.cleanup()
                    logger.info(f"✅ Service '{name}' cleaned up")
                else:
                    logger.info(f"ℹ️ Service '{name}' has no cleanup method")
            except Exception as e:
                logger.error(f"❌ Error cleaning up service '{name}': {e}")

        self.services.clear()
        self.initialized = False
        logger.info("✅ Service manager cleanup completed")

    async def restart_service(self, service_name: str) -> bool:
        """Restart a specific service"""
        if service_name not in self.services:
            logger.error(f"❌ Cannot restart unknown service '{service_name}'")
            return False

        try:
            logger.info(f"🔄 Restarting service '{service_name}'...")

            service = self.services[service_name]

            # Cleanup existing service
            if hasattr(service, "cleanup"):
                await service.cleanup()

            # Reinitialize service
            if hasattr(service, "initialize"):
                await service.initialize()

            logger.info(f"✅ Service '{service_name}' restarted successfully")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to restart service '{service_name}': {e}")
            return False
