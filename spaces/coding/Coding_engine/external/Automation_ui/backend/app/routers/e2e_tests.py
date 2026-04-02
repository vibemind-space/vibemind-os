"""E2E Test Router — Autonomous testing API endpoints."""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks
from app.models.e2e_models import E2ERunRequest, E2ERunStatus, TestReport
from app.services.e2e_test_runner import get_runner

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/e2e", tags=["e2e-tests"])

# Background task ref
_run_task: Optional[asyncio.Task] = None


@router.post("/run")
async def start_e2e_run(request: E2ERunRequest, background_tasks: BackgroundTasks):
    """Start an autonomous E2E test run."""
    runner = get_runner()
    if runner.status.running:
        return {"success": False, "error": "E2E tests already running", "status": runner.status.model_dump()}

    async def _run():
        try:
            await runner.run_tests(
                project_path=request.project_path,
                app_url=request.app_url,
                max_tests=request.max_tests,
                story_filter=request.stories,
            )
        except Exception as e:
            logger.error(f"E2E run failed: {e}")

    global _run_task
    _run_task = asyncio.create_task(_run())

    return {"success": True, "message": "E2E tests started"}


@router.get("/status")
async def get_e2e_status():
    """Get current E2E test run status."""
    runner = get_runner()
    return runner.status.model_dump()


@router.get("/report")
async def get_e2e_report():
    """Get latest E2E test report."""
    runner = get_runner()
    if runner.status.report:
        return runner.status.report.model_dump()
    return {"error": "No report available. Run tests first."}


@router.post("/stop")
async def stop_e2e_run():
    """Cancel running E2E tests."""
    runner = get_runner()
    if not runner.status.running:
        return {"success": False, "error": "No tests running"}
    runner.cancel()
    return {"success": True, "message": "Cancellation requested"}
