"""
CodingEngineRunner - Bridge between VibeMind and Coding Engine

This module manages subprocess execution of the Coding Engine's
unified 3-layer engine (run_engine.py) and provides real-time
status updates to the Electron frontend.

Features:
- Multi-project support with unique VNC ports per project
- Real-time status streaming via stdout parsing (JSON progress)
- Job cancellation and cleanup
- Requirements file generation from voice commands
"""

import asyncio
import json
import os
import subprocess
import sys
import threading
import uuid
import re
import socket
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Optional, Callable, List, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Module-level instance for global access
_runner_instance: Optional['CodingEngineRunner'] = None


def get_coding_engine_runner() -> Optional['CodingEngineRunner']:
    """Get the global CodingEngineRunner instance."""
    return _runner_instance


@dataclass
class GenerationJob:
    """Represents a code generation job."""
    job_id: str
    project_name: str
    tech_stack: str
    status: str = "pending"  # pending, generating, converging, testing, completed, failed, cancelled
    progress: float = 0.0
    phase: str = ""
    phase_error: Optional[str] = None
    vnc_port: Optional[int] = None
    output_dir: Optional[str] = None
    requirements_file: Optional[str] = None
    process: Optional[subprocess.Popen] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None


class CodingEngineRunner:
    """
    Manages Coding Engine subprocess execution for VibeMind.

    This class starts run_engine.py (unified 3-layer engine) as a subprocess
    with full autonomous mode options and streams status updates back
    to the Electron frontend via callback.
    """

    # Base VNC port - each job gets a unique port starting from here
    BASE_VNC_PORT = 6080

    def __init__(
        self,
        coding_engine_path: str,
        on_status_update: Optional[Callable[[str, str, float, str, Optional[str]], None]] = None,
        on_issue_detected: Optional[Callable[[str, dict], None]] = None,
        on_quality_update: Optional[Callable[[str, dict], None]] = None,
    ):
        """
        Initialize the CodingEngineRunner.

        Args:
            coding_engine_path: Path to the Coding_engine directory
            on_status_update: Callback(job_id, status, progress, phase, error)
            on_issue_detected: Callback(job_id, issue_dict) - called per issue detected
            on_quality_update: Callback(job_id, summary_dict) - called on quality summary change
        """
        global _runner_instance

        self.coding_engine_path = Path(coding_engine_path)
        self.on_status_update = on_status_update
        self.on_issue_detected = on_issue_detected
        self.on_quality_update = on_quality_update
        self.jobs: Dict[str, GenerationJob] = {}
        self._used_ports: set = set()
        self._lock = threading.Lock()

        # Verify Coding Engine path exists
        if not self.coding_engine_path.exists():
            logger.warning(f"Coding Engine path does not exist: {self.coding_engine_path}")

        # Set as global instance
        _runner_instance = self

        logger.info(f"CodingEngineRunner initialized with path: {self.coding_engine_path}")

    def _find_available_port(self) -> int:
        """Find an available port for VNC, starting from BASE_VNC_PORT."""
        with self._lock:
            port = self.BASE_VNC_PORT
            while port in self._used_ports:
                port += 1
                if port > self.BASE_VNC_PORT + 100:  # Safety limit
                    raise RuntimeError("No available VNC ports")

            # Verify port is actually available
            while True:
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.bind(('', port))
                        self._used_ports.add(port)
                        return port
                except OSError:
                    port += 1
                    if port > self.BASE_VNC_PORT + 100:
                        raise RuntimeError("No available VNC ports")

    def _release_port(self, port: int):
        """Release a VNC port back to the pool."""
        with self._lock:
            self._used_ports.discard(port)

    def _generate_requirements_file(
        self,
        project_name: str,
        description: str,
        tech_stack: str,
        requirements: List[str],
        output_dir: Path
    ) -> str:
        """Generate a requirements JSON file for the Coding Engine."""

        # Map tech stack to detailed config
        tech_stack_configs = {
            "react": {
                "frontend": {"framework": "React", "language": "TypeScript", "build_tool": "Vite"},
                "backend": {"framework": "FastAPI", "language": "Python"},
                "database": {"type": "PostgreSQL"}
            },
            "vue": {
                "frontend": {"framework": "Vue", "language": "TypeScript", "build_tool": "Vite"},
                "backend": {"framework": "FastAPI", "language": "Python"},
                "database": {"type": "PostgreSQL"}
            },
            "nextjs": {
                "frontend": {"framework": "Next.js", "language": "TypeScript"},
                "backend": {"framework": "Next.js API Routes", "language": "TypeScript"},
                "database": {"type": "PostgreSQL"}
            },
            "electron": {
                "frontend": {"framework": "Electron", "language": "TypeScript"},
                "backend": {"framework": "Node.js", "language": "TypeScript"},
                "database": {"type": "SQLite"}
            }
        }

        tech_config = tech_stack_configs.get(tech_stack, tech_stack_configs["react"])

        # Build requirements list with IDs
        req_list = []
        for i, req in enumerate(requirements, 1):
            req_list.append({
                "id": f"REQ-{i:03d}",
                "title": req[:50] if len(req) > 50 else req,
                "description": req,
                "priority": "high" if i <= 3 else "medium",
                "category": "functional"
            })

        # Add default requirements if empty
        if not req_list:
            req_list = [
                {
                    "id": "REQ-001",
                    "title": "Basic Application Structure",
                    "description": f"Create a {tech_stack} application with proper project structure",
                    "priority": "high",
                    "category": "functional"
                },
                {
                    "id": "REQ-002",
                    "title": "User Interface",
                    "description": "Implement a clean, responsive user interface",
                    "priority": "high",
                    "category": "functional"
                }
            ]

        # Build full requirements document
        requirements_doc = {
            "project": {
                "name": project_name,
                "description": description or f"Auto-generated {tech_stack} application",
                "version": "1.0.0"
            },
            "tech_stack": tech_config,
            "requirements": req_list,
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "generator": "VibeMind CodingEngineRunner",
                "source": "voice_command"
            }
        }

        # Write to file
        req_file = output_dir / "requirements.json"
        req_file.parent.mkdir(parents=True, exist_ok=True)

        with open(req_file, 'w', encoding='utf-8') as f:
            json.dump(requirements_doc, f, indent=2)

        logger.info(f"Generated requirements file: {req_file}")
        return str(req_file)

    async def run_generate_code(
        self,
        title: str,
        description: str = "",
        tech_stack: str = "react",
        requirements: List[str] = None
    ) -> str:
        """
        Start a new code generation job.

        Args:
            title: Project title/name
            description: Project description
            tech_stack: Technology stack (react, vue, nextjs, electron)
            requirements: List of requirement strings

        Returns:
            Job ID string
        """
        requirements = requirements or []

        # Generate unique job ID
        job_id = f"job-{uuid.uuid4().hex[:8]}"

        # Sanitize project name for filesystem
        safe_name = re.sub(r'[^\w\-]', '_', title.lower())

        # Create output directory
        output_base = self.coding_engine_path / "output_vibemind"
        output_dir = output_base / f"{safe_name}_{job_id}"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Find available VNC port
        vnc_port = self._find_available_port()

        # Generate requirements file
        req_file = self._generate_requirements_file(
            title, description, tech_stack, requirements, output_dir
        )

        # Create job record
        job = GenerationJob(
            job_id=job_id,
            project_name=title,
            tech_stack=tech_stack,
            status="pending",
            vnc_port=vnc_port,
            output_dir=str(output_dir),
            requirements_file=req_file,
            started_at=datetime.now()
        )

        self.jobs[job_id] = job

        # Start subprocess in background
        asyncio.create_task(self._run_subprocess(job))

        logger.info(f"Started generation job: {job_id} for project: {title}")

        return f"Started code generation for '{title}' (Job ID: {job_id})"

    async def _run_subprocess(self, job: GenerationJob):
        """Run the Coding Engine subprocess and stream status updates."""

        try:
            job.status = "generating"
            self._notify_status(job)

            # Build command — unified 3-layer engine
            python_exe = sys.executable
            script_path = self.coding_engine_path / "run_engine.py"

            if not script_path.exists():
                raise FileNotFoundError(f"run_engine.py not found at {script_path}")

            cmd = [
                python_exe,
                str(script_path),
                job.requirements_file,
                "--autonomous",
                "--continuous-sandbox",
                "--external-sandbox",
                "--enable-vnc",
                "--vnc-port", str(job.vnc_port),
                "--enable-validation",
                "--output-dir", job.output_dir,
                "--json-progress",  # Request JSON progress output
                "--parallel", "10",
            ]

            logger.info(f"Executing: {' '.join(cmd)}")

            # Start process
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.coding_engine_path)
            )

            job.process = process

            # Stream stderr in background so errors are visible immediately
            stderr_lines = []
            async def _stream_stderr():
                async for line in process.stderr:
                    line_str = line.decode('utf-8', errors='replace').strip()
                    if line_str:
                        stderr_lines.append(line_str)
                        logger.warning(f"[CodingEngine:{job.job_id}] {line_str}")

            stderr_task = asyncio.create_task(_stream_stderr())

            # Start quality file watcher for live issue detection
            quality_watcher_task = asyncio.create_task(
                self._watch_quality_files(job)
            )

            # Stream stdout for status updates
            async for line in process.stdout:
                line_str = line.decode('utf-8', errors='replace').strip()
                if not line_str:
                    continue

                # Try to parse JSON progress updates
                if line_str.startswith('{'):
                    try:
                        progress_data = json.loads(line_str)
                        self._handle_progress_update(job, progress_data)
                    except json.JSONDecodeError:
                        pass
                else:
                    # Parse text-based status updates
                    self._parse_text_status(job, line_str)

            # Wait for process completion
            return_code = await process.wait()
            await stderr_task  # Ensure stderr is fully read

            # Stop quality file watcher
            quality_watcher_task.cancel()
            try:
                await quality_watcher_task
            except asyncio.CancelledError:
                pass

            # Do final quality file check after process completes
            await self._check_quality_file_final(job)

            stderr_str = "\n".join(stderr_lines) if stderr_lines else None
            if stderr_str:
                logger.debug(f"Stderr summary: {stderr_str[-500:]}")

            # Determine final status
            if return_code == 0:
                job.status = "completed"
                job.progress = 100.0
                job.phase = "Generation complete"
            else:
                job.status = "failed"
                job.error_message = f"Process exited with code {return_code}"
                job.phase_error = stderr_str if stderr_output else None

            job.completed_at = datetime.now()

        except asyncio.CancelledError:
            job.status = "cancelled"
            job.completed_at = datetime.now()
            if job.process:
                job.process.terminate()

        except Exception as e:
            logger.error(f"Generation error for job {job.job_id}: {e}")
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = datetime.now()

        finally:
            # Release VNC port
            if job.vnc_port:
                self._release_port(job.vnc_port)

            self._notify_status(job)

    def _handle_progress_update(self, job: GenerationJob, data: dict):
        """Handle JSON progress update from subprocess."""
        logger.debug("_handle_progress_update: job_id=%s, data=%s", job.job_id, data)
        if "status" in data:
            job.status = data["status"]
        if "progress" in data:
            job.progress = float(data["progress"])
        if "phase" in data:
            job.phase = data["phase"]
        if "error" in data:
            job.phase_error = data["error"]

        self._notify_status(job)

    def _parse_text_status(self, job: GenerationJob, line: str):
        """Parse text-based status updates from subprocess output."""
        line_lower = line.lower()

        # Phase detection patterns
        phase_patterns = [
            (r"\[phase\]\s*(.+)", lambda m: setattr(job, "phase", m.group(1))),
            (r"progress:\s*([\d.]+)%?", lambda m: setattr(job, "progress", float(m.group(1)))),
            (r"iteration\s+(\d+)/(\d+)", lambda m: setattr(job, "progress", float(m.group(1)) / float(m.group(2)) * 100)),
        ]

        for pattern, handler in phase_patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                handler(match)
                self._notify_status(job)
                break

        # Status transitions based on keywords
        if "building" in line_lower or "generating" in line_lower:
            job.status = "generating"
            self._notify_status(job)
        elif "converging" in line_lower or "convergence" in line_lower:
            job.status = "converging"
            self._notify_status(job)
        elif "testing" in line_lower or "validation" in line_lower:
            job.status = "testing"
            self._notify_status(job)
        elif "self-critique" in line_lower or "self_critique" in line_lower:
            job.phase = "Quality Analysis"
            self._notify_status(job)
        elif "quality_gate" in line_lower or "quality gate" in line_lower:
            job.phase = "Quality Gate"
            self._notify_status(job)
        elif "error" in line_lower or "failed" in line_lower:
            if job.status not in ("completed", "cancelled"):
                job.phase_error = line
                self._notify_status(job)

        # Detect inline issues from stdout
        if "[issue]" in line_lower or "critique issue" in line_lower:
            severity = "medium"
            if "critical" in line_lower:
                severity = "critical"
            elif "high" in line_lower:
                severity = "high"
            elif "low" in line_lower:
                severity = "low"

            inline_issue = {
                "id": f"LIVE-{datetime.now().strftime('%H%M%S')}",
                "severity": severity,
                "title": line.strip()[:120],
                "description": line.strip(),
                "category": "live_detection",
                "auto_fixable": False,
            }
            self._notify_issue(job, inline_issue)

    def _notify_status(self, job: GenerationJob):
        """Send status update via callback."""
        if self.on_status_update:
            try:
                self.on_status_update(
                    job.job_id,
                    job.status,
                    job.progress,
                    job.phase,
                    job.error_message or job.phase_error
                )
            except Exception as e:
                logger.warning(f"Status callback error: {e}")

    def _notify_issue(self, job: GenerationJob, issue: dict):
        """Notify about a single detected issue."""
        if self.on_issue_detected:
            try:
                self.on_issue_detected(job.job_id, issue)
            except Exception as e:
                logger.warning(f"Issue callback error: {e}")

    def _notify_quality_summary(self, job: GenerationJob, summary: dict):
        """Notify about quality summary update."""
        if self.on_quality_update:
            try:
                self.on_quality_update(job.job_id, summary)
            except Exception as e:
                logger.warning(f"Quality callback error: {e}")

    async def _watch_quality_files(self, job: GenerationJob):
        """
        Poll the output directory for quality report files during generation.
        Detects new issues and broadcasts them in real-time.
        """
        if not job.output_dir:
            return

        output_path = Path(job.output_dir)
        # Also check the Data/all_services path (where pipeline writes to)
        data_dir = self.coding_engine_path / "Data" / "all_services"
        quality_paths = [
            output_path / "quality" / "self_critique_report.json",
        ]
        # Add data dir pattern for the project
        if data_dir.exists():
            for entry in data_dir.iterdir():
                if entry.is_dir() and job.project_name.lower().replace(" ", "-") in entry.name.lower():
                    quality_paths.append(entry / "quality" / "self_critique_report.json")

        last_mtime = 0
        last_issue_count = 0

        while True:
            await asyncio.sleep(3)  # Poll every 3 seconds

            for quality_file in quality_paths:
                if not quality_file.exists():
                    continue

                try:
                    current_mtime = quality_file.stat().st_mtime
                    if current_mtime <= last_mtime:
                        continue

                    last_mtime = current_mtime

                    with open(quality_file, "r", encoding="utf-8") as f:
                        report = json.load(f)

                    issues = report.get("issues", [])
                    new_issues = issues[last_issue_count:]
                    last_issue_count = len(issues)

                    # Broadcast each new issue
                    for issue in new_issues:
                        self._notify_issue(job, issue)

                    # Broadcast summary update
                    summary = report.get("summary", {})
                    if summary:
                        self._notify_quality_summary(job, summary)

                except (json.JSONDecodeError, IOError) as e:
                    # File may be partially written — retry on next poll
                    logger.debug(f"Quality file read error (may be partial write): {e}")
                    continue

    async def _check_quality_file_final(self, job: GenerationJob):
        """Final check for quality files after process completes."""
        if not job.output_dir:
            return

        # Check all possible quality file locations
        paths_to_check = [
            Path(job.output_dir) / "quality" / "self_critique_report.json",
        ]
        data_dir = self.coding_engine_path / "Data" / "all_services"
        if data_dir.exists():
            for entry in data_dir.iterdir():
                if entry.is_dir() and job.project_name.lower().replace(" ", "-") in entry.name.lower():
                    paths_to_check.append(entry / "quality" / "self_critique_report.json")

        for quality_file in paths_to_check:
            if not quality_file.exists():
                continue
            try:
                with open(quality_file, "r", encoding="utf-8") as f:
                    report = json.load(f)
                issues = report.get("issues", [])
                for issue in issues:
                    self._notify_issue(job, issue)
                summary = report.get("summary", {})
                if summary:
                    self._notify_quality_summary(job, summary)
                break  # Only process from first found file
            except Exception as e:
                logger.warning(f"Final quality check failed: {e}")

    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the status of a generation job.

        Returns:
            Dict with status info or None if job not found
        """
        job = self.jobs.get(job_id)
        if not job:
            return None

        return {
            "job_id": job.job_id,
            "project_name": job.project_name,
            "status": job.status,
            "progress": job.progress,
            "phase": job.phase,
            "phase_error": job.phase_error,
            "vnc_port": job.vnc_port,
            "output_dir": job.output_dir,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "error": job.error_message
        }

    def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a running generation job.

        Returns:
            True if job was cancelled, False if not found or already completed
        """
        job = self.jobs.get(job_id)
        if not job:
            logger.warning(f"Job not found: {job_id}")
            return False

        if job.status in ("completed", "failed", "cancelled"):
            logger.info(f"Job {job_id} already in terminal state: {job.status}")
            return False

        # Terminate process
        if job.process and job.process.returncode is None:
            try:
                job.process.terminate()
                logger.info(f"Terminated process for job {job_id}")
            except Exception as e:
                logger.warning(f"Error terminating process: {e}")

        job.status = "cancelled"
        job.completed_at = datetime.now()
        self._notify_status(job)

        # Release port
        if job.vnc_port:
            self._release_port(job.vnc_port)

        return True

    def list_jobs(self, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List all jobs, optionally filtered by status.

        Returns:
            List of job status dicts
        """
        jobs = []
        for job_id, job in self.jobs.items():
            if status_filter and job.status != status_filter:
                continue
            jobs.append(self.get_job_status(job_id))

        return sorted(jobs, key=lambda x: x.get("started_at") or "", reverse=True)

    def cleanup_completed_jobs(self, max_age_hours: int = 24):
        """Remove completed jobs older than max_age_hours."""
        now = datetime.now()
        to_remove = []

        for job_id, job in self.jobs.items():
            if job.status in ("completed", "failed", "cancelled"):
                if job.completed_at:
                    age_hours = (now - job.completed_at).total_seconds() / 3600
                    if age_hours > max_age_hours:
                        to_remove.append(job_id)

        for job_id in to_remove:
            del self.jobs[job_id]
            logger.info(f"Cleaned up old job: {job_id}")
