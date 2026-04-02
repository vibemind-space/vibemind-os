"""
Health Monitor for Handoff MCP Production Deployment

Monitors system health, component status, and provides metrics
for the Handoff MCP desktop automation system.
"""

import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field, asdict

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("HealthMonitor")


@dataclass
class ComponentStatus:
    """Status of a single component"""
    name: str
    status: str  # "healthy", "degraded", "unhealthy", "unknown"
    message: str = ""
    last_check: str = ""
    details: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.last_check:
            self.last_check = datetime.now().isoformat()


@dataclass
class SystemMetrics:
    """System-wide metrics"""
    uptime_seconds: float = 0
    plans_created: int = 0
    plans_executed: int = 0
    validations_performed: int = 0
    actions_executed: int = 0
    errors_count: int = 0
    last_activity: str = ""
    startup_time: str = ""

    def __post_init__(self):
        if not self.startup_time:
            self.startup_time = datetime.now().isoformat()


class HealthMonitor:
    """
    Monitors health of all Handoff MCP components:
    - MoireServer (WebSocket connection)
    - OpenRouter API (API key validity)
    - Tesseract OCR (binary availability)
    - PyAutoGUI (display access)
    - Python environment (dependencies)
    """

    def __init__(self, config=None):
        self.config = config
        self.metrics = SystemMetrics()
        self._startup_time = datetime.now()
        self._component_status: dict[str, ComponentStatus] = {}
        self._is_running = False
        self._check_interval = 30  # seconds

        if config:
            self._check_interval = config.health_check_interval

    # ==================== Component Checks ====================

    async def check_moire_server(self) -> ComponentStatus:
        """Check if MoireServer WebSocket is accessible"""
        try:
            import websockets

            host = self.config.moire_host if self.config else "localhost"
            port = self.config.moire_port if self.config else 8765
            uri = f"ws://{host}:{port}"

            try:
                async with asyncio.timeout(5):
                    async with websockets.connect(uri) as ws:
                        # Send a ping
                        await ws.ping()
                        return ComponentStatus(
                            name="MoireServer",
                            status="healthy",
                            message=f"Connected to {uri}",
                            details={"uri": uri}
                        )
            except asyncio.TimeoutError:
                return ComponentStatus(
                    name="MoireServer",
                    status="unhealthy",
                    message=f"Connection timeout to {uri}",
                    details={"uri": uri}
                )
            except Exception as e:
                return ComponentStatus(
                    name="MoireServer",
                    status="unhealthy",
                    message=f"Connection failed: {e}",
                    details={"uri": uri, "error": str(e)}
                )

        except ImportError:
            return ComponentStatus(
                name="MoireServer",
                status="unknown",
                message="websockets package not installed"
            )

    async def check_openrouter_api(self) -> ComponentStatus:
        """Check if OpenRouter API key is valid"""
        api_key = ""
        if self.config:
            api_key = self.config.openrouter_api_key
        else:
            api_key = os.getenv("OPENROUTER_API_KEY", "")

        if not api_key:
            return ComponentStatus(
                name="OpenRouter API",
                status="unhealthy",
                message="API key not configured"
            )

        # Just check if key format looks valid (don't make actual API call)
        if api_key.startswith("sk-or-") and len(api_key) > 20:
            return ComponentStatus(
                name="OpenRouter API",
                status="healthy",
                message="API key configured",
                details={"key_prefix": api_key[:10] + "..."}
            )
        else:
            return ComponentStatus(
                name="OpenRouter API",
                status="degraded",
                message="API key format may be invalid",
                details={"key_length": len(api_key)}
            )

    def check_tesseract(self) -> ComponentStatus:
        """Check if Tesseract OCR is available"""
        import shutil
        tesseract_path = os.getenv("TESSERACT_PATH") or shutil.which("tesseract")
        if self.config and self.config.tesseract_path:
            tesseract_path = self.config.tesseract_path

        if Path(tesseract_path).exists():
            # Try to get version
            try:
                result = subprocess.run(
                    [tesseract_path, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                version = result.stdout.split('\n')[0] if result.stdout else "unknown"
                return ComponentStatus(
                    name="Tesseract OCR",
                    status="healthy",
                    message=f"Installed: {version}",
                    details={"path": tesseract_path, "version": version}
                )
            except Exception as e:
                return ComponentStatus(
                    name="Tesseract OCR",
                    status="degraded",
                    message=f"Binary exists but failed to run: {e}",
                    details={"path": tesseract_path, "error": str(e)}
                )
        else:
            # Check if it's in PATH
            tesseract_in_path = shutil.which("tesseract")
            if tesseract_in_path:
                return ComponentStatus(
                    name="Tesseract OCR",
                    status="healthy",
                    message=f"Found in PATH: {tesseract_in_path}",
                    details={"path": tesseract_in_path}
                )
            return ComponentStatus(
                name="Tesseract OCR",
                status="degraded",
                message="Not installed (optional - will use MoireServer OCR)",
                details={"expected_path": tesseract_path}
            )

    def check_pyautogui(self) -> ComponentStatus:
        """Check if PyAutoGUI has display access"""
        try:
            import pyautogui

            # Try to get screen size (requires display access)
            try:
                size = pyautogui.size()
                return ComponentStatus(
                    name="PyAutoGUI",
                    status="healthy",
                    message=f"Display access OK ({size.width}x{size.height})",
                    details={"screen_width": size.width, "screen_height": size.height}
                )
            except Exception as e:
                return ComponentStatus(
                    name="PyAutoGUI",
                    status="unhealthy",
                    message=f"No display access: {e}",
                    details={"error": str(e)}
                )

        except ImportError:
            return ComponentStatus(
                name="PyAutoGUI",
                status="unhealthy",
                message="pyautogui package not installed"
            )

    def check_python_environment(self) -> ComponentStatus:
        """Check Python environment and critical dependencies"""
        issues = []
        details = {
            "python_version": sys.version,
            "platform": sys.platform
        }

        # Check critical packages
        critical_packages = [
            "pyautogui",
            "pytesseract",
            "websockets",
            "aiohttp",
            "mcp"
        ]

        missing = []
        for pkg in critical_packages:
            try:
                __import__(pkg)
            except ImportError:
                missing.append(pkg)

        if missing:
            issues.append(f"Missing packages: {', '.join(missing)}")
            details["missing_packages"] = missing

        if issues:
            return ComponentStatus(
                name="Python Environment",
                status="degraded" if len(missing) < 3 else "unhealthy",
                message="; ".join(issues),
                details=details
            )

        return ComponentStatus(
            name="Python Environment",
            status="healthy",
            message=f"Python {sys.version_info.major}.{sys.version_info.minor} with all dependencies",
            details=details
        )

    # ==================== Health Check Runner ====================

    async def check_all_components(self) -> dict[str, ComponentStatus]:
        """Run all health checks and return status"""
        checks = [
            self.check_moire_server(),
            asyncio.to_thread(self.check_tesseract),
            asyncio.to_thread(self.check_pyautogui),
            asyncio.to_thread(self.check_python_environment),
            self.check_openrouter_api(),
        ]

        results = await asyncio.gather(*checks, return_exceptions=True)

        component_names = ["MoireServer", "Tesseract", "PyAutoGUI", "Python", "OpenRouter"]

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self._component_status[component_names[i]] = ComponentStatus(
                    name=component_names[i],
                    status="unknown",
                    message=f"Check failed: {result}"
                )
            else:
                self._component_status[result.name] = result

        return self._component_status

    def get_overall_status(self) -> str:
        """Get overall system health status"""
        if not self._component_status:
            return "unknown"

        statuses = [c.status for c in self._component_status.values()]

        if all(s == "healthy" for s in statuses):
            return "healthy"
        elif any(s == "unhealthy" for s in statuses):
            return "unhealthy"
        elif any(s == "degraded" for s in statuses):
            return "degraded"
        else:
            return "unknown"

    # ==================== Metrics ====================

    def record_plan_created(self):
        """Record a plan creation"""
        self.metrics.plans_created += 1
        self.metrics.last_activity = datetime.now().isoformat()

    def record_plan_executed(self):
        """Record a plan execution"""
        self.metrics.plans_executed += 1
        self.metrics.last_activity = datetime.now().isoformat()

    def record_validation(self):
        """Record a validation"""
        self.metrics.validations_performed += 1
        self.metrics.last_activity = datetime.now().isoformat()

    def record_action(self):
        """Record an action execution"""
        self.metrics.actions_executed += 1
        self.metrics.last_activity = datetime.now().isoformat()

    def record_error(self):
        """Record an error"""
        self.metrics.errors_count += 1
        self.metrics.last_activity = datetime.now().isoformat()

    def get_metrics(self) -> dict:
        """Get current metrics"""
        self.metrics.uptime_seconds = (datetime.now() - self._startup_time).total_seconds()
        return asdict(self.metrics)

    # ==================== Structured Logging ====================

    def log_event(self, event_type: str, details: dict, level: str = "info"):
        """Log a structured event"""
        event = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "details": details,
            "metrics_snapshot": {
                "uptime": (datetime.now() - self._startup_time).total_seconds(),
                "errors": self.metrics.errors_count
            }
        }

        log_func = getattr(logger, level.lower(), logger.info)
        log_func(json.dumps(event))

    # ==================== Background Monitor ====================

    async def start_monitoring(self):
        """Start background health monitoring"""
        self._is_running = True
        logger.info("Starting health monitoring...")

        while self._is_running:
            try:
                await self.check_all_components()
                status = self.get_overall_status()

                self.log_event("health_check", {
                    "overall_status": status,
                    "components": {
                        name: {"status": c.status, "message": c.message}
                        for name, c in self._component_status.items()
                    }
                })

            except Exception as e:
                logger.error(f"Health check failed: {e}")
                self.record_error()

            await asyncio.sleep(self._check_interval)

    def stop_monitoring(self):
        """Stop background health monitoring"""
        self._is_running = False
        logger.info("Stopping health monitoring...")

    # ==================== Status Report ====================

    def get_status_report(self) -> dict:
        """Get a full status report"""
        return {
            "timestamp": datetime.now().isoformat(),
            "overall_status": self.get_overall_status(),
            "components": {
                name: asdict(status)
                for name, status in self._component_status.items()
            },
            "metrics": self.get_metrics()
        }

    def print_status_report(self):
        """Print a human-readable status report"""
        print("=" * 60)
        print("Handoff MCP Health Status")
        print("=" * 60)
        print(f"Overall Status: {self.get_overall_status().upper()}")
        print(f"Uptime: {(datetime.now() - self._startup_time).total_seconds():.0f}s")
        print("-" * 60)
        print("Components:")
        for name, status in self._component_status.items():
            icon = {
                "healthy": "[OK]",
                "degraded": "[!!]",
                "unhealthy": "[XX]",
                "unknown": "[??]"
            }.get(status.status, "[??]")
            print(f"  {icon} {name}: {status.message}")
        print("-" * 60)
        print(f"Plans Created: {self.metrics.plans_created}")
        print(f"Plans Executed: {self.metrics.plans_executed}")
        print(f"Validations: {self.metrics.validations_performed}")
        print(f"Actions: {self.metrics.actions_executed}")
        print(f"Errors: {self.metrics.errors_count}")
        print("=" * 60)


async def main():
    """Run health check from command line"""
    from config.config_loader import load_config

    config = load_config()
    monitor = HealthMonitor(config)

    print("Running health checks...")
    await monitor.check_all_components()
    monitor.print_status_report()


if __name__ == "__main__":
    asyncio.run(main())
