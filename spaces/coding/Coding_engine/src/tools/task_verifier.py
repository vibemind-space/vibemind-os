"""
Task Verifier — Verifies each generated task via browser testing.

Flow per task:
1. Code gets copied to sandbox container
2. OpenClaw browser agent tests the component
3. If PASS -> task APPROVED
4. If FAIL -> WhatsApp notification -> wait for fix -> retry

Only approves tasks when functionality actually works.
All subprocess calls use create_subprocess_exec (no shell injection).
"""

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from src.tools.openclaw_bridge_tool import OpenClawBridge, DebugResult
from src.tools.whatsapp_agent import WhatsAppAgent

logger = logging.getLogger(__name__)

SANDBOX_CONTAINER = "coding-engine-sandbox"
SANDBOX_PREVIEW_URL = "http://localhost:3100"


class VerifyStatus(str, Enum):
    APPROVED = "approved"
    FAILED = "failed"
    SKIPPED = "skipped"
    PENDING = "pending"


@dataclass
class VerifyResult:
    task_id: str
    status: VerifyStatus
    errors: list = field(default_factory=list)
    fix_applied: str = ""
    attempts: int = 0
    whatsapp_reply: str = ""


# Global flag for kill signal
_kill_signal = asyncio.Event()


def request_kill():
    """Set the kill signal to stop all verification loops."""
    _kill_signal.set()
    logger.info("Kill signal received")


def reset_kill():
    """Reset the kill signal for a new run."""
    _kill_signal.clear()


def is_killed() -> bool:
    """Check if kill signal is active."""
    return _kill_signal.is_set()


class TaskVerifier:
    """Verifies generated tasks via OpenClaw browser testing + WhatsApp loop."""

    def __init__(
        self,
        preview_url: str = SANDBOX_PREVIEW_URL,
        max_retries: int = 3,
        whatsapp_timeout: int = 300,
        enable_whatsapp: bool = True,
    ):
        self.preview_url = preview_url
        self.max_retries = max_retries
        self.whatsapp_timeout = whatsapp_timeout
        self.enable_whatsapp = enable_whatsapp
        self.bridge = OpenClawBridge()
        self.whatsapp = WhatsAppAgent()
        self.total_verified = 0
        self.total_approved = 0
        self.total_failed = 0

    async def copy_to_sandbox(
        self, source_path: str, dest_path: str = "/workspace/app"
    ) -> bool:
        """Copy generated code files to the sandbox container.
        Uses create_subprocess_exec with explicit args (no shell)."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "cp",
                source_path,
                SANDBOX_CONTAINER + ":" + dest_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            if proc.returncode != 0:
                logger.error("Copy to sandbox failed: %s", stderr.decode())
                return False
            return True
        except Exception as e:
            logger.error("Copy to sandbox error: %s", e)
            return False

    async def verify_task(
        self,
        task_id: str,
        task_name: str,
        code_path: str = "",
        requirements: str = "",
        component: str = "",
    ) -> VerifyResult:
        """
        Verify a single task:
        1. Copy code to sandbox
        2. Test via OpenClaw browser agent
        3. If fail -> WhatsApp loop
        4. Return APPROVED or FAILED
        """
        self.total_verified += 1
        result = VerifyResult(task_id=task_id, status=VerifyStatus.PENDING)

        if is_killed():
            result.status = VerifyStatus.SKIPPED
            return result

        if code_path:
            await self.copy_to_sandbox(code_path)

        component_name = component or task_name
        for attempt in range(1, self.max_retries + 1):
            if is_killed():
                result.status = VerifyStatus.SKIPPED
                return result

            result.attempts = attempt
            logger.info(
                "Verifying %s (attempt %d/%d)",
                task_id, attempt, self.max_retries,
            )

            debug_result = await self.bridge.debug_component(
                preview_url=self.preview_url,
                component=component_name,
                requirements=requirements,
            )

            if debug_result.success and not debug_result.errors:
                result.status = VerifyStatus.APPROVED
                self.total_approved += 1
                logger.info("Task %s APPROVED (attempt %d)", task_id, attempt)
                if self.enable_whatsapp:
                    await self.whatsapp.send_task_approved(task_id, task_name)
                return result

            result.errors = debug_result.errors
            logger.warning("Task %s failed: %s", task_id, debug_result.errors[:3])

            if attempt >= self.max_retries:
                break

            if self.enable_whatsapp:
                fix = await self._whatsapp_fix_loop(task_id, task_name, debug_result)
                if fix:
                    if fix.lower().strip() == "skip":
                        result.status = VerifyStatus.SKIPPED
                        return result
                    result.fix_applied = fix
                    result.whatsapp_reply = fix
                    logger.info("Fix for %s: %s", task_id, fix[:100])
            else:
                await asyncio.sleep(5)

        result.status = VerifyStatus.FAILED
        self.total_failed += 1
        logger.error("Task %s FAILED after %d attempts", task_id, self.max_retries)
        return result

    async def _whatsapp_fix_loop(
        self, task_id: str, task_name: str, debug_result: DebugResult
    ) -> Optional[str]:
        """Send failure to WhatsApp and wait for fix suggestion."""
        error_text = "\n".join(debug_result.errors[:5])
        session = await self.whatsapp.send_task_failure(
            task_id=task_id, task_name=task_name, error=error_text,
        )
        if not session:
            return None
        return await self.whatsapp.wait_for_reply(
            session, timeout=self.whatsapp_timeout
        )

    async def verify_all_tasks(self, tasks: list, on_result=None) -> list:
        """Verify a list of tasks sequentially."""
        results = []
        for task in tasks:
            if is_killed():
                break
            result = await self.verify_task(
                task_id=task.get("task_id", ""),
                task_name=task.get("task_name", ""),
                code_path=task.get("code_path", ""),
                requirements=task.get("requirements", ""),
                component=task.get("component", ""),
            )
            results.append(result)
            if on_result:
                await on_result(result)

        if self.enable_whatsapp and results:
            passed = sum(1 for r in results if r.status == VerifyStatus.APPROVED)
            failed = sum(1 for r in results if r.status == VerifyStatus.FAILED)
            await self.whatsapp.send_generation_summary(
                project="whatsapp-service",
                total=len(results), passed=passed, failed=failed,
            )
        return results

    def get_stats(self) -> dict:
        """Return verification statistics."""
        return {
            "total_verified": self.total_verified,
            "total_approved": self.total_approved,
            "total_failed": self.total_failed,
            "kill_active": is_killed(),
        }
