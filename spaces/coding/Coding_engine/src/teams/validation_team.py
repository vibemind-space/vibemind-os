"""
ValidationTeam - Parallel Test Generation, Execution und Debug Engine.

Architektur:
1. TestGenerator (Claude) - Schreibt Tests basierend auf Requirements Batches
2. TestRunner (subprocess) - Führt vitest/pytest aus, KEIN Claude
3. ValidationReport (JSON) - Strukturierte Ergebnisse mit action_items
4. DebugEngine (Claude) - Liest Report und behebt Bugs

Features:
- Docker-basiert für Port-Isolation
- Sichtbare Shell für User-Feedback
- Health Checks für App-Start
- Parallel Test Execution
"""

import asyncio
import json
import subprocess
import threading
import queue
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, List, Dict, Any, AsyncIterator
from enum import Enum
import structlog

from ..autogen.cli_wrapper import ClaudeCLI, CLIResponse
from ..tools.sandbox_tool import SandboxTool, ProjectType
from ..tools.claude_code_tool import ClaudeCodeTool
from ..infra.port_manager import get_port_manager, PortAllocation, NoAvailablePortError

logger = structlog.get_logger(__name__)


class TestStatus(str, Enum):
    """Test execution status."""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class TestCase:
    """Einzelner Test Case."""
    requirement_id: str
    name: str
    description: str
    file_path: str
    status: TestStatus = TestStatus.PENDING
    error_message: Optional[str] = None
    duration_ms: int = 0
    
    def to_dict(self) -> dict:
        return {
            "requirement_id": self.requirement_id,
            "name": self.name,
            "description": self.description,
            "file_path": self.file_path,
            "status": self.status.value,
            "error_message": self.error_message,
            "duration_ms": self.duration_ms,
        }


@dataclass
class ActionItem:
    """Aktion aus dem Test Report für die Debug Engine."""
    priority: int  # 1 = critical, 2 = high, 3 = medium
    type: str  # "fix_code", "add_export", "install_dep", "update_config"
    file_path: str
    description: str
    suggested_fix: Optional[str] = None
    related_requirement: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "priority": self.priority,
            "type": self.type,
            "file_path": self.file_path,
            "description": self.description,
            "suggested_fix": self.suggested_fix,
            "related_requirement": self.related_requirement,
        }


@dataclass
class TestReport:
    """Vollständiger Test Report für die Debug Engine."""
    job_id: str
    timestamp: datetime
    project_path: str
    
    # Summary
    total_requirements: int = 0
    requirements_with_tests: int = 0
    tests_total: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    tests_skipped: int = 0
    
    # Details
    test_cases: List[TestCase] = field(default_factory=list)
    failures: List[dict] = field(default_factory=list)
    action_items: List[ActionItem] = field(default_factory=list)
    
    # Console Output
    console_output: str = ""
    error_log: str = ""
    
    # Metrics
    execution_time_ms: int = 0
    coverage_percent: float = 0.0
    
    @property
    def success_rate(self) -> float:
        if self.tests_total == 0:
            return 0.0
        return (self.tests_passed / self.tests_total) * 100
    
    def add_failure(self, test_case: TestCase, error: str) -> None:
        """Fügt einen Failure hinzu und erstellt ActionItem."""
        self.failures.append({
            "requirement_id": test_case.requirement_id,
            "test_name": test_case.name,
            "file_path": test_case.file_path,
            "error_message": error,
        })
        
        # Auto-create action item
        self.action_items.append(ActionItem(
            priority=1 if "Error" in error else 2,
            type="fix_code",
            file_path=test_case.file_path,
            description=f"Fix failing test: {test_case.name}",
            suggested_fix=self._extract_fix_hint(error),
            related_requirement=test_case.requirement_id,
        ))
    
    def _extract_fix_hint(self, error: str) -> Optional[str]:
        """Extrahiert Hinweise aus Fehlermeldungen."""
        error_lower = error.lower()
        
        if "cannot find module" in error_lower or "no such file" in error_lower:
            return "Check import paths or create missing file"
        elif "is not a function" in error_lower:
            return "Ensure function is exported and imported correctly"
        elif "undefined" in error_lower:
            return "Variable or function not defined - check exports"
        elif "type error" in error_lower:
            return "Check TypeScript types and interfaces"
        elif "connection refused" in error_lower:
            return "Backend service not running - check health endpoints"
        
        return None
    
    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "timestamp": self.timestamp.isoformat(),
            "project_path": self.project_path,
            "summary": {
                "total_requirements": self.total_requirements,
                "requirements_with_tests": self.requirements_with_tests,
                "tests_total": self.tests_total,
                "tests_passed": self.tests_passed,
                "tests_failed": self.tests_failed,
                "tests_skipped": self.tests_skipped,
                "success_rate": self.success_rate,
            },
            "test_cases": [tc.to_dict() for tc in self.test_cases],
            "failures": self.failures,
            "action_items": [ai.to_dict() for ai in self.action_items],
            "console_output": self.console_output[-10000:],  # Last 10KB
            "error_log": self.error_log[-5000],
            "metrics": {
                "execution_time_ms": self.execution_time_ms,
                "coverage_percent": self.coverage_percent,
            },
        }
    
    def save(self, output_path: Path) -> None:
        """Speichert Report als JSON."""
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)


@dataclass
class ShellOutput:
    """Streaming Shell Output für User-Feedback."""
    service: str  # "frontend", "backend", "tests", "docker"
    line: str
    is_error: bool = False
    timestamp: datetime = field(default_factory=datetime.now)


class ShellStream:
    """
    Sichtbare Shell für User - streamt Output von allen Services.
    
    Features:
    - Real-time Output streaming
    - Color-coded nach Service
    - Error Detection
    - Callback für UI Updates
    """
    
    def __init__(
        self,
        on_output: Optional[Callable[[ShellOutput], None]] = None,
        buffer_size: int = 1000,
    ):
        self.on_output = on_output
        self.buffer: List[ShellOutput] = []
        self.buffer_size = buffer_size
        self._queue: queue.Queue = queue.Queue()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self.logger = logger.bind(component="shell_stream")
    
    def start(self) -> None:
        """Startet den Output-Stream."""
        self._running = True
        self._thread = threading.Thread(target=self._stream_loop, daemon=True)
        self._thread.start()
    
    def stop(self) -> None:
        """Stoppt den Output-Stream."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
    
    def add_output(self, service: str, line: str, is_error: bool = False) -> None:
        """Fügt neue Output-Zeile hinzu."""
        output = ShellOutput(
            service=service,
            line=line,
            is_error=is_error,
        )
        self._queue.put(output)
    
    def _stream_loop(self) -> None:
        """Interne Streaming-Schleife."""
        while self._running:
            try:
                output = self._queue.get(timeout=0.1)
                
                # Buffer management
                self.buffer.append(output)
                if len(self.buffer) > self.buffer_size:
                    self.buffer = self.buffer[-self.buffer_size:]
                
                # Callback
                if self.on_output:
                    self.on_output(output)
                    
            except queue.Empty:
                continue
    
    def get_recent(self, count: int = 100) -> List[ShellOutput]:
        """Holt die letzten N Outputs."""
        return self.buffer[-count:]
    
    def create_process_reader(
        self,
        process: subprocess.Popen,
        service: str,
    ) -> threading.Thread:
        """Erstellt einen Thread zum Lesen von Process-Output."""
        def read_output():
            try:
                for line in iter(process.stdout.readline, b''):
                    decoded = line.decode('utf-8', errors='replace').strip()
                    if decoded:
                        is_error = any(p in decoded.lower() for p in [
                            'error', 'fail', 'exception', 'traceback'
                        ])
                        self.add_output(service, decoded, is_error)
            except Exception as e:
                self.add_output(service, f"Read error: {e}", True)
            finally:
                try:
                    process.stdout.close()
                except:
                    pass
        
        thread = threading.Thread(target=read_output, daemon=True)
        thread.start()
        return thread


@dataclass
class ValidationConfig:
    """Konfiguration für ValidationTeam."""
    # Paths
    project_dir: str
    output_dir: str
    requirements_path: str
    
    # Test Generation
    test_framework: str = "vitest"  # "vitest", "jest", "pytest"
    generate_parallel: bool = True
    max_concurrent_tests: int = 4
    
    # Docker Settings
    use_docker: bool = True
    docker_network: str = "validation-net"
    frontend_port: int = 3100
    backend_port: int = 8100
    
    # Execution
    timeout_seconds: int = 300
    max_debug_iterations: int = 3
    
    # Shell Display
    enable_shell_stream: bool = True
    on_shell_output: Optional[Callable[[ShellOutput], None]] = None
    
    # Callbacks
    on_progress: Optional[Callable[[str, dict], None]] = None


@dataclass 
class ValidationResult:
    """Ergebnis der Validation."""
    success: bool
    report: Optional[TestReport] = None
    debug_iterations: int = 0
    total_fixes_applied: int = 0
    final_pass_rate: float = 0.0
    execution_time_ms: int = 0
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "debug_iterations": self.debug_iterations,
            "total_fixes_applied": self.total_fixes_applied,
            "final_pass_rate": self.final_pass_rate,
            "execution_time_ms": self.execution_time_ms,
            "errors": self.errors,
            "report": self.report.to_dict() if self.report else None,
        }


class TestGenerator:
    """
    Test Generator - Claude schreibt Tests basierend auf Requirements.
    
    Für jeden Requirement-Batch wird ein Test-File generiert.
    """
    
    def __init__(
        self,
        working_dir: str,
        test_framework: str = "vitest",
    ):
        self.working_dir = Path(working_dir)
        self.test_framework = test_framework
        self._claude_tool: Optional[ClaudeCodeTool] = None
        self.logger = logger.bind(component="test_generator")
    
    async def generate_tests(
        self,
        requirements: List[dict],
        project_type: ProjectType,
    ) -> List[Path]:
        """
        Generiert Tests für Requirements.
        
        Args:
            requirements: Liste von Requirement-Dicts
            project_type: Erkannter Projekttyp
            
        Returns:
            Liste von generierten Test-Datei-Pfaden
        """
        generated_files = []
        
        # Initialize Claude Code Tool with test-generation skill
        if not self._claude_tool:
            self._claude_tool = ClaudeCodeTool(
                working_dir=str(self.working_dir),
                agent_type="testing",  # Maps to test-generation skill
            )
        
        # Batch requirements by component/feature
        batches = self._batch_requirements(requirements)

        # Filter out batches that already have tests (deduplication)
        existing_tests = self._get_existing_test_batches()
        batches_to_generate = {
            name: reqs for name, reqs in batches.items()
            if name not in existing_tests
        }

        if not batches_to_generate:
            self.logger.info(
                "all_batches_have_tests",
                total_batches=len(batches),
                existing_tests=len(existing_tests),
            )
            return []

        self.logger.info(
            "test_deduplication_result",
            total_batches=len(batches),
            skipped=len(batches) - len(batches_to_generate),
            to_generate=len(batches_to_generate),
        )

        for batch_name, batch_reqs in batches_to_generate.items():
            self.logger.info(
                "generating_tests_for_batch",
                batch=batch_name,
                count=len(batch_reqs),
            )
            
            try:
                test_file = await self._generate_batch_tests(
                    batch_name,
                    batch_reqs,
                    project_type,
                )
                if test_file:
                    generated_files.append(test_file)
                    
            except Exception as e:
                self.logger.error(
                    "test_generation_failed",
                    batch=batch_name,
                    error=str(e),
                )
        
        return generated_files
    
    def _batch_requirements(self, requirements: List[dict]) -> Dict[str, List[dict]]:
        """Gruppiert Requirements nach Komponente/Feature."""
        batches = {}
        
        for req in requirements:
            # Extract component from requirement ID or category
            req_id = req.get("id", req.get("label", "unknown"))
            category = req.get("category", "general")
            
            # Use first part of ID as batch key
            if "-" in req_id:
                batch_key = req_id.split("-")[0]
            else:
                batch_key = category
            
            if batch_key not in batches:
                batches[batch_key] = []
            batches[batch_key].append(req)
        
        return batches

    def _get_existing_test_batches(self) -> set:
        """Find batch names that already have test files."""
        existing = set()

        # Check common test directories
        test_dirs = [
            self.working_dir / "tests",
            self.working_dir / "__tests__",
            self.working_dir / "test",
        ]

        for test_dir in test_dirs:
            if not test_dir.exists():
                continue

            for test_file in test_dir.rglob("*.test.*"):
                # Extract batch name from file (e.g., "REQ.test.ts" -> "REQ")
                batch_name = test_file.stem.replace(".test", "").replace(".spec", "")
                existing.add(batch_name)

            for test_file in test_dir.rglob("*.spec.*"):
                batch_name = test_file.stem.replace(".test", "").replace(".spec", "")
                existing.add(batch_name)

        return existing

    async def _generate_batch_tests(
        self,
        batch_name: str,
        requirements: List[dict],
        project_type: ProjectType,
    ) -> Optional[Path]:
        """Generiert Tests für einen Batch."""
        
        # Build prompt
        prompt = self._build_test_prompt(batch_name, requirements, project_type)
        
        # Execute via Claude Code Tool with test-generation skill
        response = await self._claude_tool.execute(
            prompt=prompt,
            agent_type="testing",  # Loads test-generation skill
        )

        if not response.success:
            self.logger.error(
                "claude_test_generation_failed",
                batch=batch_name,
                error=response.error,
            )
            return None
        
        # Determine output file path
        if self.test_framework == "vitest":
            test_file = self.working_dir / f"tests/{batch_name}.test.ts"
        elif self.test_framework == "jest":
            test_file = self.working_dir / f"__tests__/{batch_name}.test.tsx"
        else:
            test_file = self.working_dir / f"tests/test_{batch_name}.py"
        
        # File should be created by Claude
        if test_file.exists():
            return test_file
        
        return None
    
    def _build_test_prompt(
        self,
        batch_name: str,
        requirements: List[dict],
        project_type: ProjectType,
    ) -> str:
        """Erstellt den Prompt für Test-Generierung."""
        
        framework_info = {
            "vitest": "Vitest mit @testing-library/react",
            "jest": "Jest mit @testing-library/react", 
            "pytest": "pytest mit pytest-asyncio",
        }
        
        req_text = "\n".join([
            f"- {r.get('id', 'REQ')}: {r.get('label', r.get('description', str(r)))}"
            for r in requirements
        ])
        
        return f"""Erstelle Tests für folgende Requirements:

## Requirements Batch: {batch_name}
{req_text}

## Projekt-Info
- Typ: {project_type.value}
- Test Framework: {framework_info.get(self.test_framework, self.test_framework)}
- Output: tests/{batch_name}.test.ts

## Anforderungen
1. Erstelle einen Test pro Requirement
2. Verwende describe/it Pattern
3. Teste UI-Elemente mit screen.getByRole / getByText
4. Füge data-testid zu Elementen hinzu wenn sie fehlen

## CRITICAL RULES - NO MOCKS
- **NO MOCKS** - Use real implementations only
- NO vi.spyOn().mockImplementation()
- NO jest.mock() or vi.mock()
- NO fake timers unless absolutely necessary
- Test actual behavior with real HTTP calls
- Use real database connections where possible

## Beispiel-Struktur
```typescript
import {{ describe, it, expect }} from 'vitest';
import {{ render, screen, fireEvent }} from '@testing-library/react';
import {{ ComponentName }} from '../src/components/ComponentName';

describe('REQ-ID: Requirement Description', () => {{
  it('should do something specific', () => {{
    render(<ComponentName />);
    expect(screen.getByText('Expected Text')).toBeInTheDocument();
  }});
}});
```

Erstelle die Test-Datei jetzt."""


class TestRunner:
    """
    Test Runner - Führt Tests via subprocess aus (KEIN Claude).
    
    Features:
    - Vitest/Jest/Pytest Support
    - JSON Output für Report-Generierung
    - Shell Streaming für User-Feedback
    - Timeouts und Error Handling
    """
    
    def __init__(
        self,
        project_dir: str,
        test_framework: str = "vitest",
        shell_stream: Optional[ShellStream] = None,
        timeout: int = 300,
    ):
        self.project_dir = Path(project_dir)
        self.test_framework = test_framework
        self.shell = shell_stream
        self.timeout = timeout
        self.logger = logger.bind(component="test_runner")
    
    async def run_tests(self, test_files: Optional[List[Path]] = None) -> TestReport:
        """
        Führt alle oder spezifische Tests aus.
        
        Args:
            test_files: Optional liste spezifischer Test-Files
            
        Returns:
            TestReport mit Ergebnissen
        """
        start_time = datetime.now()
        
        report = TestReport(
            job_id=f"test_{start_time.strftime('%Y%m%d_%H%M%S')}",
            timestamp=start_time,
            project_path=str(self.project_dir),
        )
        
        try:
            if self.test_framework == "vitest":
                result = await self._run_vitest(test_files)
            elif self.test_framework == "jest":
                result = await self._run_jest(test_files)
            else:
                result = await self._run_pytest(test_files)
            
            # Parse results into report
            self._parse_results(result, report)
            
        except Exception as e:
            self.logger.error("test_run_failed", error=str(e))
            report.error_log = str(e)
        
        report.execution_time_ms = int(
            (datetime.now() - start_time).total_seconds() * 1000
        )
        
        return report
    
    async def _run_vitest(self, test_files: Optional[List[Path]]) -> dict:
        """Führt Vitest aus."""
        cmd = ["npx", "vitest", "run", "--reporter=json"]
        
        if test_files:
            cmd.extend([str(f) for f in test_files])
        
        return await self._execute_test_command(cmd)
    
    async def _run_jest(self, test_files: Optional[List[Path]]) -> dict:
        """Führt Jest aus."""
        cmd = ["npx", "jest", "--json", "--outputFile=jest-results.json"]
        
        if test_files:
            cmd.extend([str(f) for f in test_files])
        
        return await self._execute_test_command(cmd)
    
    async def _run_pytest(self, test_files: Optional[List[Path]]) -> dict:
        """Führt pytest aus."""
        cmd = ["python", "-m", "pytest", "--json-report", "--json-report-file=pytest-results.json"]
        
        if test_files:
            cmd.extend([str(f) for f in test_files])
        
        return await self._execute_test_command(cmd)
    
    async def _execute_test_command(self, cmd: List[str]) -> dict:
        """Führt Test-Command aus und captured Output."""
        self.logger.info("executing_tests", cmd=" ".join(cmd))
        
        if self.shell:
            self.shell.add_output("tests", f"$ {' '.join(cmd)}")
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(self.project_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        stdout_lines = []
        stderr_lines = []
        
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout,
            )
            
            stdout_text = stdout.decode('utf-8', errors='replace')
            stderr_text = stderr.decode('utf-8', errors='replace')
            
            stdout_lines = stdout_text.split('\n')
            stderr_lines = stderr_text.split('\n')
            
            # Stream to shell
            if self.shell:
                for line in stdout_lines:
                    if line.strip():
                        self.shell.add_output("tests", line)
                for line in stderr_lines:
                    if line.strip():
                        self.shell.add_output("tests", line, is_error=True)
            
            return {
                "exit_code": process.returncode,
                "stdout": stdout_text,
                "stderr": stderr_text,
            }
            
        except asyncio.TimeoutError:
            process.kill()
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Test timeout after {self.timeout}s",
            }
    
    def _parse_results(self, result: dict, report: TestReport) -> None:
        """Parsed Test-Ergebnisse in Report."""
        report.console_output = result.get("stdout", "")
        report.error_log = result.get("stderr", "")
        
        # Try to parse JSON results
        try:
            if self.test_framework == "vitest":
                self._parse_vitest_json(report)
            elif self.test_framework == "jest":
                self._parse_jest_json(report)
            else:
                self._parse_pytest_json(report)
        except Exception as e:
            self.logger.warning("json_parse_failed", error=str(e))
            # Fallback: parse from console output
            self._parse_from_console(result, report)
    
    def _parse_vitest_json(self, report: TestReport) -> None:
        """Parsed Vitest JSON Output."""
        # Vitest outputs JSON to stdout
        try:
            data = json.loads(report.console_output)
            
            report.tests_total = data.get("numTotalTests", 0)
            report.tests_passed = data.get("numPassedTests", 0)
            report.tests_failed = data.get("numFailedTests", 0)
            
            for suite in data.get("testResults", []):
                for test in suite.get("assertionResults", []):
                    tc = TestCase(
                        requirement_id=self._extract_req_id(test.get("title", "")),
                        name=test.get("title", ""),
                        description=test.get("fullName", ""),
                        file_path=suite.get("name", ""),
                        status=TestStatus.PASSED if test.get("status") == "passed" else TestStatus.FAILED,
                    )
                    
                    if tc.status == TestStatus.FAILED:
                        error_msg = "\n".join(test.get("failureMessages", []))
                        tc.error_message = error_msg
                        report.add_failure(tc, error_msg)
                    
                    report.test_cases.append(tc)
                    
        except json.JSONDecodeError:
            pass
    
    def _parse_jest_json(self, report: TestReport) -> None:
        """Parsed Jest JSON Output."""
        json_file = self.project_dir / "jest-results.json"
        if not json_file.exists():
            return
        
        with open(json_file) as f:
            data = json.load(f)
        
        report.tests_total = data.get("numTotalTests", 0)
        report.tests_passed = data.get("numPassedTests", 0)
        report.tests_failed = data.get("numFailedTests", 0)
    
    def _parse_pytest_json(self, report: TestReport) -> None:
        """Parsed pytest JSON Output."""
        json_file = self.project_dir / "pytest-results.json"
        if not json_file.exists():
            return
        
        with open(json_file) as f:
            data = json.load(f)
        
        summary = data.get("summary", {})
        report.tests_total = summary.get("total", 0)
        report.tests_passed = summary.get("passed", 0)
        report.tests_failed = summary.get("failed", 0)
    
    def _parse_from_console(self, result: dict, report: TestReport) -> None:
        """Fallback: Parse test results from console output."""
        stdout = result.get("stdout", "")
        
        # Count passed/failed from output patterns
        import re
        
        # Vitest pattern: "✓ test name" or "× test name"
        passed = len(re.findall(r'[✓✔]', stdout))
        failed = len(re.findall(r'[×✗]', stdout))
        
        report.tests_passed = passed
        report.tests_failed = failed
        report.tests_total = passed + failed
    
    def _extract_req_id(self, test_name: str) -> str:
        """Extrahiert Requirement ID aus Test-Name."""
        import re
        match = re.search(r'(REQ-[a-zA-Z0-9-]+)', test_name)
        if match:
            return match.group(1)
        return "unknown"


class DebugEngine:
    """
    Debug Engine - Claude liest Test Report und behebt Bugs.
    
    Workflow:
    1. Liest TestReport mit action_items
    2. Priorisiert Fixes nach Severity
    3. Wendet Fixes sequentiell an via Claude CLI
    4. Re-runs Tests nach Fixes
    """
    
    def __init__(
        self,
        working_dir: str,
        shell_stream: Optional[ShellStream] = None,
    ):
        self.working_dir = Path(working_dir)
        self.shell = shell_stream
        self._claude_tool: Optional[ClaudeCodeTool] = None
        self.logger = logger.bind(component="debug_engine")
    
    async def process_report(
        self,
        report: TestReport,
        max_iterations: int = 3,
    ) -> int:
        """
        Verarbeitet Test Report und wendet Fixes an.
        
        Args:
            report: Test Report mit Failures
            max_iterations: Max Fix-Iterationen
            
        Returns:
            Anzahl angewendeter Fixes
        """
        if not report.action_items:
            self.logger.info("no_action_items_to_process")
            return 0
        
        # Initialize Claude Code Tool with debugging skill
        if not self._claude_tool:
            self._claude_tool = ClaudeCodeTool(
                working_dir=str(self.working_dir),
                agent_type="fixer",  # Maps to code-generation skill for fixes
            )
        
        fixes_applied = 0
        
        # Sort by priority
        sorted_items = sorted(report.action_items, key=lambda x: x.priority)
        
        for item in sorted_items[:max_iterations * 2]:  # Limit total fixes
            self.logger.info(
                "processing_action_item",
                type=item.type,
                file=item.file_path,
                priority=item.priority,
            )
            
            if self.shell:
                self.shell.add_output(
                    "debug",
                    f"[FIX] Fixing: {item.description}",
                )
            
            try:
                success = await self._apply_fix(item)
                if success:
                    fixes_applied += 1
                    
            except Exception as e:
                self.logger.error(
                    "fix_application_failed",
                    error=str(e),
                    item=item.description,
                )
        
        return fixes_applied
    
    async def _apply_fix(self, item: ActionItem) -> bool:
        """Wendet einen einzelnen Fix an."""
        prompt = self._build_fix_prompt(item)

        response = await self._claude_tool.execute(
            prompt=prompt,
            agent_type="fixer",  # Uses code-generation skill for fixing
        )

        if response.success:
            self.logger.info(
                "fix_applied_successfully",
                type=item.type,
                file=item.file_path,
            )
            return True
        else:
            self.logger.warning(
                "fix_application_failed",
                error=response.error_message,
            )
            return False
    
    def _build_fix_prompt(self, item: ActionItem) -> str:
        """Erstellt Fix-Prompt für Claude."""
        context = ""
        if item.file_path and (self.working_dir / item.file_path).exists():
            try:
                content = (self.working_dir / item.file_path).read_text()
                context = f"\n\nAktueller Code in `{item.file_path}`:\n```\n{content[:2000]}\n```"
            except:
                pass
        
        return f"""Behebe folgenden Bug:

## Problem
- Typ: {item.type}
- Datei: {item.file_path}
- Beschreibung: {item.description}
{f'- Hinweis: {item.suggested_fix}' if item.suggested_fix else ''}
{f'- Requirement: {item.related_requirement}' if item.related_requirement else ''}
{context}

## Anweisungen
1. Analysiere das Problem
2. Finde die Ursache im Code
3. Behebe den Bug direkt in der Datei
4. Stelle sicher dass keine neuen Bugs entstehen

Behebe den Bug jetzt."""


class DockerRunner:
    """
    Docker Runner - Isoliert Frontend/Backend mit Port-Isolation.
    
    Erstellt Docker Network und startet Services in Container.
    Verwendet PortManager für dynamische Port-Zuweisung bei parallelen_runs.
    """
    
    def __init__(
        self,
        project_dir: str,
        network_name: str = "validation-net",
        frontend_port: Optional[int] = None,
        backend_port: Optional[int] = None,
        shell_stream: Optional[ShellStream] = None,
        container_id: Optional[str] = None,
    ):
        self.project_dir = Path(project_dir)
        self.network_name = network_name
        self.shell = shell_stream
        self._containers: List[str] = []
        self.logger = logger.bind(component="docker_runner")
        
        # Port Management
        self._port_manager = get_port_manager()
        self._port_allocation: Optional[PortAllocation] = None
        
        # Generate unique container ID if not provided
        self._container_id = container_id or f"validation-{id(self)}"
        
        # If ports are explicitly provided, use them (backward compatibility)
        # Otherwise, allocate dynamically when start() is called
        self._explicit_frontend_port = frontend_port
        self._explicit_backend_port = backend_port
        self.frontend_port: Optional[int] = None
        self.backend_port: Optional[int] = None
    
    async def start(self) -> dict:
        """Startet Docker-Umgebung mit dynamischer Port-Zuweisung."""
        result = {
            "success": False,
            "frontend_url": None,
            "backend_url": None,
        }
        
        try:
            # Allocate ports - either explicit or dynamic
            if self._explicit_frontend_port and self._explicit_backend_port:
                # Use explicitly provided ports (backward compatibility)
                self.frontend_port = self._explicit_frontend_port
                self.backend_port = self._explicit_backend_port
                self.logger.info(
                    "using_explicit_ports",
                    frontend=self.frontend_port,
                    backend=self.backend_port,
                )
            else:
                # Allocate dynamically via PortManager
                try:
                    self._port_allocation = self._port_manager.allocate_ports(self._container_id)
                    self.frontend_port = self._port_allocation.frontend_port
                    self.backend_port = self._port_allocation.backend_port
                    self.logger.info(
                        "ports_allocated_dynamically",
                        container_id=self._container_id,
                        frontend=self.frontend_port,
                        backend=self.backend_port,
                    )
                except NoAvailablePortError as e:
                    self.logger.error("no_ports_available", error=str(e))
                    result["error"] = str(e)
                    return result
            
            # Create network
            await self._create_network()
            
            # Start backend
            backend_container = await self._start_backend()
            if backend_container:
                self._containers.append(backend_container)
                result["backend_url"] = f"http://localhost:{self.backend_port}"
            
            # Start frontend
            frontend_container = await self._start_frontend()
            if frontend_container:
                self._containers.append(frontend_container)
                result["frontend_url"] = f"http://localhost:{self.frontend_port}"
            
            # Health check
            result["success"] = await self._health_check()
            
            # Add port info to result
            result["frontend_port"] = self.frontend_port
            result["backend_port"] = self.backend_port
            result["container_id"] = self._container_id
            
        except Exception as e:
            self.logger.error("docker_start_failed", error=str(e))
            result["error"] = str(e)
            # Release ports on failure
            await self._release_ports()
        
        return result
    
    async def stop(self) -> None:
        """Stoppt alle Container und gibt Ports frei."""
        for container_id in self._containers:
            await self._run_command(["docker", "stop", "-t", "5", container_id])
            await self._run_command(["docker", "rm", "-f", container_id])
        
        self._containers.clear()
        
        # Release allocated ports
        await self._release_ports()
    
    async def _release_ports(self) -> None:
        """Gibt dynamisch allokierte Ports frei."""
        if self._port_allocation:
            self._port_manager.release_ports(self._port_allocation.container_id)
            self.logger.info(
                "ports_released",
                container_id=self._port_allocation.container_id,
                frontend=self.frontend_port,
                backend=self.backend_port,
            )
            self._port_allocation = None
            self.frontend_port = None
            self.backend_port = None
    
    async def _create_network(self) -> None:
        """Erstellt Docker Network."""
        await self._run_command([
            "docker", "network", "create", "--driver", "bridge", self.network_name
        ])
    
    async def _start_backend(self) -> Optional[str]:
        """Startet Backend in Container."""
        # Check if backend exists
        backend_dir = self.project_dir / "src" / "api"
        if not backend_dir.exists():
            return None
        
        # Unique container name with port for parallel runs
        container_name = f"validation-backend-{self.backend_port}"
        
        result = await self._run_command([
            "docker", "run", "-d",
            "--name", container_name,
            "--network", self.network_name,
            "-p", f"{self.backend_port}:8000",
            "-v", f"{self.project_dir}:/app",
            "-w", "/app",
            "python:3.11-slim",
            "bash", "-c", "pip install -r requirements.txt && uvicorn src.api.main:app --host 0.0.0.0 --port 8000",
        ])
        
        if result.get("exit_code") == 0:
            return result.get("stdout", "").strip()[:12]
        return None
    
    async def _start_frontend(self) -> Optional[str]:
        """Startet Frontend in Container."""
        # Unique container name with port for parallel runs
        container_name = f"validation-frontend-{self.frontend_port}"
        # Backend reference with port for inter-container communication
        backend_container_name = f"validation-backend-{self.backend_port}"
        
        result = await self._run_command([
            "docker", "run", "-d",
            "--name", container_name,
            "--network", self.network_name,
            "-p", f"{self.frontend_port}:3000",
            "-v", f"{self.project_dir}:/app",
            "-w", "/app",
            "-e", f"VITE_API_URL=http://{backend_container_name}:8000",
            "node:20-slim",
            "bash", "-c", "npm install && npm run dev -- --host 0.0.0.0 --port 3000",
        ])
        
        if result.get("exit_code") == 0:
            return result.get("stdout", "").strip()[:12]
        return None
    
    async def _health_check(self) -> bool:
        """Health Check für beide Services."""
        import httpx
        
        for _ in range(30):
            try:
                async with httpx.AsyncClient() as client:
                    # Check frontend
                    frontend_ok = False
                    try:
                        resp = await client.get(
                            f"http://localhost:{self.frontend_port}",
                            timeout=5,
                        )
                        frontend_ok = resp.status_code < 500
                    except:
                        pass
                    
                    # Check backend
                    backend_ok = False
                    try:
                        resp = await client.get(
                            f"http://localhost:{self.backend_port}/health",
                            timeout=5,
                        )
                        backend_ok = resp.status_code < 500
                    except:
                        try:
                            resp = await client.get(
                                f"http://localhost:{self.backend_port}",
                                timeout=5,
                            )
                            backend_ok = resp.status_code < 500
                        except:
                            pass
                    
                    if frontend_ok and backend_ok:
                        return True
                    
            except Exception:
                pass
            
            await asyncio.sleep(2)
        
        return False
    
    async def _run_command(self, cmd: List[str]) -> dict:
        """Führt Docker-Command aus."""
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            
            return {
                "exit_code": process.returncode,
                "stdout": stdout.decode('utf-8', errors='replace'),
                "stderr": stderr.decode('utf-8', errors='replace'),
            }
        except Exception as e:
            return {"exit_code": -1, "stdout": "", "stderr": str(e)}


class ValidationTeam:
    """
    ValidationTeam - Orchestriert den gesamten Validation-Workflow.
    
    Workflow:
    1. Docker-Umgebung starten (Port-Isolation)
    2. Tests generieren (Claude)
    3. Tests ausführen (subprocess)
    4. Report erstellen
    5. Debug Engine für Fixes (Claude)
    6. Repeat bis success oder max_iterations
    """
    
    def __init__(self, config: ValidationConfig):
        self.config = config
        self.project_dir = Path(config.project_dir)
        self.output_dir = Path(config.output_dir)
        
        # Shell Stream für User-Feedback
        self.shell: Optional[ShellStream] = None
        if config.enable_shell_stream:
            self.shell = ShellStream(on_output=config.on_shell_output)
        
        # Components
        self.test_generator = TestGenerator(
            working_dir=config.project_dir,
            test_framework=config.test_framework,
        )
        self.test_runner = TestRunner(
            project_dir=config.project_dir,
            test_framework=config.test_framework,
            shell_stream=self.shell,
            timeout=config.timeout_seconds,
        )
        self.debug_engine = DebugEngine(
            working_dir=config.project_dir,
            shell_stream=self.shell,
        )
        self.docker_runner: Optional[DockerRunner] = None
        if config.use_docker:
            self.docker_runner = DockerRunner(
                project_dir=config.project_dir,
                network_name=config.docker_network,
                frontend_port=config.frontend_port,
                backend_port=config.backend_port,
                shell_stream=self.shell,
            )
        
        self.logger = logger.bind(component="validation_team")
    
    async def run(self, requirements: List[dict]) -> ValidationResult:
        """
        Führt den kompletten Validation-Workflow aus.
        
        Args:
            requirements: Liste von Requirements
            
        Returns:
            ValidationResult mit Report und Fixes
        """
        start_time = datetime.now()
        
        result = ValidationResult(success=False)
        
        try:
            # Start shell stream
            if self.shell:
                self.shell.start()
                self._report_progress("starting", {"message": "ValidationTeam startet..."})
            
            # Phase 1: Docker Setup (optional)
            if self.docker_runner:
                self._report_progress("docker", {"status": "starting"})
                docker_result = await self.docker_runner.start()
                
                if not docker_result.get("success"):
                    result.errors.append("Docker setup failed")
                    self._report_progress("docker", {"status": "failed"})
                else:
                    self._report_progress("docker", {
                        "status": "running",
                        "frontend": docker_result.get("frontend_url"),
                        "backend": docker_result.get("backend_url"),
                    })
            
            # Detect project type
            from ..tools.sandbox_tool import ProjectType
            sandbox = SandboxTool(str(self.project_dir))
            project_type = sandbox.detect_project_type()
            
            # Phase 2: Test Generation
            self._report_progress("test_generation", {"status": "starting"})
            
            test_files = await self.test_generator.generate_tests(
                requirements,
                project_type,
            )
            
            self._report_progress("test_generation", {
                "status": "complete",
                "files_generated": len(test_files),
            })
            
            # Phase 3-5: Test → Debug Loop
            for iteration in range(self.config.max_debug_iterations + 1):
                self._report_progress("testing", {
                    "iteration": iteration + 1,
                    "status": "running",
                })
                
                # Run tests
                report = await self.test_runner.run_tests(test_files)
                result.report = report
                
                # Check success
                if report.tests_failed == 0 and report.tests_passed > 0:
                    result.success = True
                    result.final_pass_rate = 100.0
                    self._report_progress("testing", {
                        "iteration": iteration + 1,
                        "status": "success",
                        "passed": report.tests_passed,
                    })
                    break
                
                # Report current state
                self._report_progress("testing", {
                    "iteration": iteration + 1,
                    "status": "partial",
                    "passed": report.tests_passed,
                    "failed": report.tests_failed,
                })
                
                # Last iteration? No more debug
                if iteration >= self.config.max_debug_iterations:
                    break
                
                # Debug Engine
                self._report_progress("debugging", {
                    "iteration": iteration + 1,
                    "status": "starting",
                    "action_items": len(report.action_items),
                })
                
                fixes = await self.debug_engine.process_report(
                    report,
                    max_iterations=2,
                )
                
                result.total_fixes_applied += fixes
                result.debug_iterations += 1
                
                self._report_progress("debugging", {
                    "iteration": iteration + 1,
                    "status": "complete",
                    "fixes_applied": fixes,
                })
            
            # Calculate final pass rate
            if result.report:
                result.final_pass_rate = result.report.success_rate
                
                # Save report
                report_path = self.output_dir / "reports" / f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                report_path.parent.mkdir(parents=True, exist_ok=True)
                result.report.save(report_path)
            
        except Exception as e:
            self.logger.error("validation_failed", error=str(e))
            result.errors.append(str(e))
        
        finally:
            # Cleanup
            if self.docker_runner:
                await self.docker_runner.stop()
            
            if self.shell:
                self.shell.stop()
        
        result.execution_time_ms = int(
            (datetime.now() - start_time).total_seconds() * 1000
        )
        
        self._report_progress("complete", {
            "success": result.success,
            "pass_rate": result.final_pass_rate,
            "fixes_applied": result.total_fixes_applied,
        })
        
        return result
    
    def _report_progress(self, phase: str, data: dict) -> None:
        """Reportet Fortschritt."""
        if self.config.on_progress:
            self.config.on_progress(phase, data)
        
        if self.shell:
            status = data.get("status", "")
            self.shell.add_output("system", f"[{phase.upper()}] {status}")


# Convenience function
async def validate_project(
    project_dir: str,
    requirements: List[dict],
    output_dir: str = "./validation_output",
    use_docker: bool = True,
    max_iterations: int = 3,
) -> ValidationResult:
    """
    Convenience function für Projekt-Validierung.
    
    Args:
        project_dir: Pfad zum Projekt
        requirements: Liste von Requirements
        output_dir: Output-Pfad für Reports
        use_docker: Docker für Port-Isolation nutzen
        max_iterations: Max Debug-Iterationen
        
    Returns:
        ValidationResult
    """
    config = ValidationConfig(
        project_dir=project_dir,
        output_dir=output_dir,
        requirements_path="",
        use_docker=use_docker,
        max_debug_iterations=max_iterations,
    )
    
    team = ValidationTeam(config)
    return await team.run(requirements)