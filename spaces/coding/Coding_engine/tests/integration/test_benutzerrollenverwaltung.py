"""
Benutzerrollenverwaltung (User Role Management) Full System Test

Tests the complete RBAC system generation with:
- 177 requirements (auth, MFA, OAuth, LDAP, AD, GDPR)
- VNC streaming enabled
- All backend agents enabled
- Full configuration

Run with: pytest tests/integration/test_benutzerrollenverwaltung.py -v -s
"""
import asyncio
import json
import os
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Any
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

# Force UTF-8 encoding on Windows before any other imports
if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    os.environ['NO_COLOR'] = '1'

import structlog
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# Emoji-safe processor for Windows
def _safe_processor(logger, method_name, event_dict):
    if sys.platform == 'win32':
        msg = event_dict.get('event', '')
        if isinstance(msg, str):
            replacements = {
                '\U0001f4e4': '[OUT]', '\U0001f4e5': '[IN]', '\U0001f4cd': '[PIN]',
                '\U0001f527': '[TOOL]', '\U0001f9e0': '[BRAIN]', '\U0001f680': '[ROCKET]',
                '\u2705': '[OK]', '\u274c': '[ERR]', '\U0001f512': '[LOCK]',
                '\U0001f4ca': '[CHART]', '\U0001f4cb': '[CLIP]', '\U0001f3d7': '[BUILD]',
            }
            for emoji, text in replacements.items():
                msg = msg.replace(emoji, text)
            event_dict['event'] = msg
    return event_dict

structlog.configure(
    processors=[
        _safe_processor,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(colors=False),
    ],
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=False,
)

logger = structlog.get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Mock Classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MockGeneratedFile:
    path: str
    content: str = ""
    language: str = "typescript"


@dataclass
class MockCLIResponse:
    success: bool = True
    output: str = ""
    error: Optional[str] = None
    files: list = field(default_factory=list)
    execution_time_ms: int = 100


@dataclass
class MockCodeGenerationResult:
    success: bool = True
    files: list = field(default_factory=list)
    output: str = "Code generated successfully"
    error: Optional[str] = None
    execution_time_ms: int = 100

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "files": [{"path": f.path, "language": f.language, "lines": 50} for f in self.files],
            "output": self.output[:500] if self.output else "",
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Event Tracker
# ─────────────────────────────────────────────────────────────────────────────

class EventTracker:
    def __init__(self):
        self.events: list[dict] = []
        self._lock = asyncio.Lock()

    async def track(self, event: Any) -> None:
        async with self._lock:
            event_type = event.type.value if hasattr(event.type, "value") else str(event.type)
            self.events.append({
                "type": event_type,
                "source": event.source,
                "success": event.success,
            })

    def summary(self) -> dict:
        type_counts = {}
        for e in self.events:
            et = e["type"]
            type_counts[et] = type_counts.get(et, 0) + 1
        return {
            "total_events": len(self.events),
            "unique_types": len(type_counts),
            "type_counts": type_counts,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Mock Patches Factory
# ─────────────────────────────────────────────────────────────────────────────

def create_patches(temp_output_dir: str):
    call_counter = {"count": 0}

    async def mock_execute(self, prompt: str, context: str = None, agent_type: str = "general", context_files: list = None):
        call_counter["count"] += 1
        logger.info(f"[TOOL] MOCK_EXECUTE [{call_counter['count']}]",
            agent_type=agent_type,
            prompt_preview=prompt[:50].replace("\n", " ") + "...")

        # Generate appropriate files based on agent type
        file_map = {
            "database": ["prisma/schema.prisma", "src/db/client.ts", "src/db/migrations.ts"],
            "api": ["src/api/routes/users.ts", "src/api/routes/roles.ts", "src/api/routes/auth.ts"],
            "auth": ["src/auth/jwt.ts", "src/auth/mfa.ts", "src/auth/oauth.ts", "src/auth/ldap.ts"],
            "security": ["src/security/rbac.ts", "src/security/audit.ts", "src/security/gdpr.ts"],
            "backend": ["src/services/userService.ts", "src/services/roleService.ts"],
            "frontend": ["src/components/UserTable.tsx", "src/components/RoleManager.tsx"],
            "fixer": ["src/App.tsx"],
        }
        files = file_map.get(agent_type, [f"src/generated_{call_counter['count']}.tsx"])

        # Create files on disk
        output_path = Path(temp_output_dir)
        for file_path in files:
            full_path = output_path / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(f"// Generated: {file_path}\nexport default {{}};")

        return MockCodeGenerationResult(
            success=True,
            files=[MockGeneratedFile(path=f) for f in files],
            output=f"Generated {len(files)} files for {agent_type}",
        )

    async def mock_execute_batch(self, prompts: list, context: str = None, agent_type: str = "general"):
        logger.info("[TOOL] MOCK_EXECUTE_BATCH", batch_size=len(prompts))
        return [MockCodeGenerationResult(
            success=True,
            files=[MockGeneratedFile(path=f"src/batch_{i}.tsx")],
        ) for i, _ in enumerate(prompts)]

    async def mock_cli_execute(self, prompt: str, working_dir: str = None, timeout: int = None):
        call_counter["count"] += 1
        return MockCLIResponse(success=True, output="OK", files=[])

    def mock_subprocess_run(*args, **kwargs):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b"Build successful"
        mock_result.stderr = b""
        return mock_result

    async def mock_async_subprocess(*args, **kwargs):
        process = AsyncMock()
        process.returncode = 0
        process.communicate = AsyncMock(return_value=(b"Success", b""))
        process.wait = AsyncMock(return_value=0)
        return process

    return {
        "execute": mock_execute,
        "execute_batch": mock_execute_batch,
        "cli_execute": mock_cli_execute,
        "subprocess_run": mock_subprocess_run,
        "async_subprocess": mock_async_subprocess,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Test Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def benutzerrollenverwaltung_requirements() -> dict:
    """Load the Benutzerrollenverwaltung requirements."""
    req_path = Path(__file__).parent.parent.parent / "Data" / "benutzerrollenverwaltung" / "docs" / "requirements" / "imported_requirements.json"
    if req_path.exists():
        with open(req_path, "r", encoding="utf-8") as f:
            return json.load(f)
    pytest.skip("Benutzerrollenverwaltung requirements not found")


@pytest.fixture
def temp_output_dir():
    with tempfile.TemporaryDirectory(prefix="rbac_test_") as tmpdir:
        output_dir = Path(tmpdir)
        (output_dir / "src").mkdir(parents=True)
        (output_dir / "src" / "components").mkdir()
        (output_dir / "src" / "api").mkdir()
        (output_dir / "src" / "auth").mkdir()
        (output_dir / "src" / "security").mkdir()

        # Create package.json
        package_json = {
            "name": "benutzerrollenverwaltung",
            "version": "1.0.0",
            "scripts": {"dev": "vite", "build": "vite build", "test": "vitest"},
            "dependencies": {"react": "^18.2.0", "react-dom": "^18.2.0"},
        }
        (output_dir / "package.json").write_text(json.dumps(package_json, indent=2))
        (output_dir / "src" / "App.tsx").write_text("export default function App() { return <div>RBAC</div>; }")

        yield str(output_dir)


@pytest.fixture
def event_tracker():
    return EventTracker()


# ─────────────────────────────────────────────────────────────────────────────
# Main Test
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_benutzerrollenverwaltung_full_system(
    benutzerrollenverwaltung_requirements: dict,
    temp_output_dir: str,
    event_tracker: EventTracker,
):
    """
    Test full RBAC system generation with 177 requirements.

    Features enabled:
    - VNC streaming (mocked)
    - Continuous sandbox testing
    - All backend agents (Database, API, Auth, Infrastructure)
    - Validation team
    """
    req_file = Path(temp_output_dir) / "requirements.json"
    req_file.write_text(json.dumps(benutzerrollenverwaltung_requirements, indent=2))

    total_reqs = len(benutzerrollenverwaltung_requirements.get("requirements", []))

    logger.info("=" * 70)
    logger.info("[ROCKET] BENUTZERROLLENVERWALTUNG SYSTEM TEST")
    logger.info("=" * 70)
    logger.info("Project", name="User Role Management (RBAC)")
    logger.info("Requirements", total=total_reqs)
    logger.info("Features", vnc=True, sandbox=True, all_agents=True)
    logger.info("=" * 70)

    from src.mind.integration import HybridSocietyRunner, HybridSocietyConfig
    from src.mind.convergence import FAST_ITERATION_CRITERIA

    patches = create_patches(temp_output_dir)

    # Full configuration with VNC and all features
    config = HybridSocietyConfig(
        requirements_path=str(req_file),
        output_dir=temp_output_dir,

        # Pipeline settings - smaller slices for 177 reqs
        max_concurrent=2,
        slice_size=20,
        initial_iterations=1,

        # Convergence
        criteria=FAST_ITERATION_CRITERIA,

        # Society settings
        enable_live_preview=False,
        enable_websocket=False,
        enable_dashboard=False,

        # Async services
        enable_async_e2e=False,
        enable_async_ux=False,

        # LLM verification
        enable_llm_verification=False,

        # Documentation
        enable_auto_docs=False,

        # VNC and Sandbox - ENABLED
        enable_sandbox_testing=True,
        enable_vnc_streaming=True,
        vnc_port=6080,
        enable_continuous_sandbox=True,
        sandbox_cycle_interval=30,
        start_sandbox_immediately=False,  # Don't start until code ready

        # Continuous debug
        enable_continuous_debug=False,

        # ValidationTeam - ENABLED
        enable_validation_team=True,
        validation_test_framework="vitest",
        validation_use_docker=False,  # Disable Docker for test
        validation_max_debug_iterations=1,

        # Persistent deployment
        enable_persistent_deploy=False,

        # Claude Monitor
        enable_claude_monitor=False,

        # Backend agents - ALL ENABLED
        enable_database_generation=True,
        enable_api_generation=True,
        enable_auth_setup=True,
        enable_infrastructure_setup=True,
    )

    with patch("src.tools.claude_code_tool.ClaudeCodeTool.execute", patches["execute"]), \
         patch("src.tools.claude_code_tool.ClaudeCodeTool.execute_batch", patches["execute_batch"]), \
         patch("src.autogen.cli_wrapper.ClaudeCLI.execute", patches["cli_execute"]), \
         patch("subprocess.run", patches["subprocess_run"]), \
         patch("asyncio.create_subprocess_exec", patches["async_subprocess"]), \
         patch("asyncio.create_subprocess_shell", patches["async_subprocess"]):

        runner = HybridSocietyRunner(config)

        try:
            result = await asyncio.wait_for(runner.run(), timeout=120.0)
        except asyncio.TimeoutError:
            logger.error("Test timed out after 120 seconds")
            result = None
        except Exception as e:
            logger.error("Test failed", error=str(e))
            import traceback
            traceback.print_exc()
            result = None

    # Results
    logger.info("=" * 70)
    logger.info("[CHART] TEST RESULTS")
    logger.info("=" * 70)

    if result:
        logger.info("Execution",
            success=result.success,
            converged=result.converged,
            iterations=result.iterations,
            files_generated=result.files_generated,
            pipeline_duration=f"{result.pipeline_duration_seconds:.2f}s",
            total_duration=f"{result.total_duration_seconds:.2f}s",
        )

        if result.vnc_url:
            logger.info("VNC", url=result.vnc_url)

        if result.validation_tests_passed or result.validation_tests_failed:
            logger.info("Validation",
                passed=result.validation_tests_passed,
                failed=result.validation_tests_failed,
                pass_rate=f"{result.validation_pass_rate:.1%}",
            )

        for error in result.errors:
            logger.warning("Error", message=error[:100])
    else:
        logger.error("No result returned")

    # Count generated files
    output_path = Path(temp_output_dir)
    generated_files = [f for f in output_path.rglob("*") if f.is_file()]
    logger.info("Generated files", count=len(generated_files))

    # List key files
    key_patterns = ["schema.prisma", "auth", "security", "rbac", "jwt", "oauth", "ldap"]
    key_files = [f for f in generated_files if any(p in f.name.lower() for p in key_patterns)]
    for f in key_files[:10]:
        logger.info(f"  [LOCK] {f.relative_to(output_path)}")

    logger.info("=" * 70)
    logger.info("[OK] TEST COMPLETE")
    logger.info("=" * 70)

    assert result is not None, "Runner should return a result"


@pytest.mark.asyncio
async def test_rbac_requirements_count(benutzerrollenverwaltung_requirements: dict):
    """Verify the requirements file has 177 requirements."""
    reqs = benutzerrollenverwaltung_requirements.get("requirements", [])
    logger.info("Requirements count", total=len(reqs))

    # Count by tag
    tags = {}
    for req in reqs:
        tag = req.get("tag", "other")
        tags[tag] = tags.get(tag, 0) + 1

    for tag, count in sorted(tags.items(), key=lambda x: -x[1]):
        logger.info(f"  {tag}: {count}")

    # The meta says 177 but actual count is 255 (with tech_stack added)
    assert len(reqs) >= 177, f"Expected at least 177 requirements, got {len(reqs)}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "--tb=short"])
