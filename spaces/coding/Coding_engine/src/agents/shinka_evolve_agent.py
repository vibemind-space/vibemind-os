"""
ShinkaEvolve Integration Agent - Evolutionary code improvement when standard fixers fail.

This agent activates when the escalation system has exhausted standard fix strategies
(after N failed fix attempts). It uses ShinkaEvolve's LLM + evolutionary algorithm
to explore a population of code variants, mutating and selecting for solutions that
pass build, tests, and verification.

Workflow:
1. Detect ESCALATION_EXHAUSTED or repeated CODE_FIX_NEEDED events
2. Extract the problematic code file and error context
3. Create a ShinkaEvolve task (initial.py + evaluate.py) on disk
4. Run the evolutionary loop with configurable generations
5. If a solution is found, emit CODE_FIXED event
6. Store results in SharedState for Minibook/DaveLovable
"""

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

from ..mind.event_bus import (
    EventBus,
    Event,
    EventType,
    agent_event,
    code_fixed_event,
    system_error_event,
)
from ..mind.shared_state import SharedState
from .autonomous_base import AutonomousAgent

logger = structlog.get_logger(__name__)

# Try importing ShinkaEvolve
try:
    from shinka.core import ShinkaEvolveRunner, EvolutionConfig
    from shinka.database import DatabaseConfig
    from shinka.launch import LocalJobConfig

    SHINKA_AVAILABLE = True
except ImportError:
    SHINKA_AVAILABLE = False
    logger.info("ShinkaEvolve not installed, evolutionary fixes disabled")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SHINKA_WORKSPACE = Path(os.environ.get(
    "SHINKA_WORKSPACE",
    str(Path.home() / ".coding_engine" / "shinka_workspace"),
))

DEFAULT_MAX_GENERATIONS = 15
DEFAULT_MAX_EVALUATION_JOBS = 2
ESCALATION_THRESHOLD = 3  # How many failed fixes before activating ShinkaEvolve


# ---------------------------------------------------------------------------
# Task Builder
# ---------------------------------------------------------------------------

@dataclass
class ShinkaTask:
    """A code evolution task prepared for ShinkaEvolve."""

    task_dir: Path
    initial_code: str
    evaluate_script: str
    error_context: str
    target_file: str
    original_code: str

    @property
    def initial_path(self) -> Path:
        return self.task_dir / "initial.py"

    @property
    def evaluate_path(self) -> Path:
        return self.task_dir / "evaluate.py"


class ShinkaTaskBuilder:
    """Builds ShinkaEvolve tasks from Coding Engine error contexts."""

    def __init__(self, workspace: Path = SHINKA_WORKSPACE):
        self.workspace = workspace
        self.workspace.mkdir(parents=True, exist_ok=True)

    def build_task(
        self,
        code: str,
        file_path: str,
        errors: List[Dict[str, Any]],
        project_dir: str,
    ) -> ShinkaTask:
        """Create a ShinkaEvolve task directory with initial.py and evaluate.py."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        task_name = Path(file_path).stem
        task_dir = self.workspace / f"evolve_{task_name}_{timestamp}"
        task_dir.mkdir(parents=True, exist_ok=True)

        # Build error context string
        error_lines = []
        for err in errors:
            error_lines.append(
                f"- {err.get('type', 'error')}: {err.get('message', 'unknown')} "
                f"(file: {err.get('file', '?')}, line: {err.get('line', '?')})"
            )
        error_context = "\n".join(error_lines) if error_lines else "Build/test failures"

        # Create initial.py with EVOLVE-BLOCK markers
        initial_code = self._wrap_evolve_block(code, file_path)

        # Create evaluate.py that checks syntax + runs build/tests
        evaluate_script = self._build_evaluate_script(file_path, project_dir, errors)

        task = ShinkaTask(
            task_dir=task_dir,
            initial_code=initial_code,
            evaluate_script=evaluate_script,
            error_context=error_context,
            target_file=file_path,
            original_code=code,
        )

        # Write files
        task.initial_path.write_text(initial_code, encoding="utf-8")
        task.evaluate_path.write_text(evaluate_script, encoding="utf-8")

        # Write metadata
        meta = {
            "target_file": file_path,
            "project_dir": project_dir,
            "errors": errors,
            "created": timestamp,
        }
        (task_dir / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

        logger.info("ShinkaEvolve task created", task_dir=str(task_dir), errors=len(errors))
        return task

    def _wrap_evolve_block(self, code: str, file_path: str) -> str:
        """Wrap code in EVOLVE-BLOCK markers for ShinkaEvolve."""
        header = f'"""\nEvolution target: {Path(file_path).name}\nOriginal file: {file_path}\n"""\n\n'
        return (
            header
            + "# EVOLVE-BLOCK-START\n"
            + code
            + "\n# EVOLVE-BLOCK-END\n"
        )

    def _build_evaluate_script(
        self,
        file_path: str,
        project_dir: str,
        errors: List[Dict[str, Any]],
    ) -> str:
        """Build an evaluate.py that scores evolved code."""
        return f'''"""Evaluation script for ShinkaEvolve task."""
import ast
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def evaluate_code(evolved_code: str) -> dict:
    """Evaluate evolved code. Returns metrics dict with combined_score."""
    scores = {{}}
    total = 0.0
    weights = {{"syntax": 0.3, "no_errors": 0.4, "structure": 0.3}}

    # 1. Syntax check (30%)
    try:
        ast.parse(evolved_code)
        scores["syntax"] = 1.0
    except SyntaxError as e:
        scores["syntax"] = 0.0
        return {{"combined_score": 0.0, "correct": False, "scores": scores,
                "text_feedback": f"Syntax error: {{e}}"}}

    # 2. Write to temp and try build (40%)
    target = Path(r"{file_path}")
    project = Path(r"{project_dir}")

    try:
        # Backup original
        backup = target.read_text(encoding="utf-8") if target.exists() else ""

        # Write evolved code
        target.write_text(evolved_code, encoding="utf-8")

        # Try building (type check or compile)
        ext = target.suffix
        if ext == ".py":
            result = subprocess.run(
                [sys.executable, "-m", "py_compile", str(target)],
                capture_output=True, text=True, timeout=30,
            )
        elif ext in (".ts", ".tsx"):
            result = subprocess.run(
                ["npx", "tsc", "--noEmit", str(target)],
                capture_output=True, text=True, timeout=60,
                cwd=str(project),
            )
        else:
            result = subprocess.CompletedProcess(args=[], returncode=0)

        if result.returncode == 0:
            scores["no_errors"] = 1.0
        else:
            error_count = result.stderr.count("error")
            scores["no_errors"] = max(0.0, 1.0 - (error_count * 0.2))

        # Restore original
        if backup:
            target.write_text(backup, encoding="utf-8")

    except Exception as e:
        scores["no_errors"] = 0.0

    # 3. Structure quality (30%) - basic heuristics
    lines = evolved_code.strip().splitlines()
    scores["structure"] = min(1.0, len(lines) / 10) if lines else 0.0
    # Penalize if too short (likely deleted code)
    if len(lines) < 5:
        scores["structure"] *= 0.3

    # Combine
    combined = sum(scores.get(k, 0) * w for k, w in weights.items())
    correct = combined > 0.7

    return {{
        "combined_score": combined,
        "correct": correct,
        "scores": scores,
        "text_feedback": "OK" if correct else "Needs improvement",
    }}


if __name__ == "__main__":
    # Read the evolved code from initial.py or stdin
    init_path = Path(__file__).parent / "initial.py"
    code = init_path.read_text(encoding="utf-8")

    # Extract EVOLVE-BLOCK content
    start_marker = "# EVOLVE-BLOCK-START"
    end_marker = "# EVOLVE-BLOCK-END"
    if start_marker in code and end_marker in code:
        start = code.index(start_marker) + len(start_marker) + 1
        end = code.index(end_marker)
        evolved = code[start:end]
    else:
        evolved = code

    result = evaluate_code(evolved)
    import json
    print(json.dumps(result))
'''


# ---------------------------------------------------------------------------
# Evolution Runner (wraps ShinkaEvolve or does simple mutations)
# ---------------------------------------------------------------------------

class EvolutionRunner:
    """Runs ShinkaEvolve on a prepared task."""

    def __init__(
        self,
        task: ShinkaTask,
        max_generations: int = DEFAULT_MAX_GENERATIONS,
        max_eval_jobs: int = DEFAULT_MAX_EVALUATION_JOBS,
    ):
        self.task = task
        self.max_generations = max_generations
        self.max_eval_jobs = max_eval_jobs

    def run(self) -> Optional[str]:
        """Run evolution and return best code, or None if no improvement."""
        if SHINKA_AVAILABLE:
            return self._run_shinka()
        else:
            return self._run_fallback()

    def _run_shinka(self) -> Optional[str]:
        """Run full ShinkaEvolve evolution."""
        try:
            evo_config = EvolutionConfig(
                init_program_path=str(self.task.initial_path),
                num_generations=self.max_generations,
                patch_types=["diff", "full"],
                patch_type_probs=[0.6, 0.4],
                task_sys_msg=(
                    f"You are fixing code that has errors.\n"
                    f"Errors:\n{self.task.error_context}\n\n"
                    f"Evolve the code to fix all errors while maintaining functionality."
                ),
            )

            db_config = DatabaseConfig(
                db_path=str(self.task.task_dir / "evolution.db"),
                num_islands=1,
                archive_size=20,
            )

            job_config = LocalJobConfig(
                eval_program_path=str(self.task.evaluate_path),
            )

            runner = ShinkaEvolveRunner(
                evo_config=evo_config,
                job_config=job_config,
                db_config=db_config,
                max_evaluation_jobs=self.max_eval_jobs,
                verbose=True,
            )

            runner.run()

            # Extract best solution from database
            from shinka.database import ProgramDatabase
            db = ProgramDatabase(db_config)
            best = db.get_best_program()
            if best and best.correct and best.combined_score > 0.7:
                return self._extract_evolved_code(best.code)

            return None

        except Exception as e:
            logger.error("ShinkaEvolve run failed", error=str(e))
            return None

    def _run_fallback(self) -> Optional[str]:
        """Simple fallback: run evaluate.py to check if current code already passes."""
        logger.info("ShinkaEvolve not available, running fallback evaluation only")
        try:
            result = subprocess.run(
                ["python", str(self.task.evaluate_path)],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(self.task.task_dir),
            )
            if result.returncode == 0:
                output = json.loads(result.stdout.strip())
                if output.get("correct", False):
                    logger.info("Current code passes evaluation")
                    return self.task.original_code
            return None
        except Exception as e:
            logger.warning("Fallback evaluation failed", error=str(e))
            return None

    def _extract_evolved_code(self, code: str) -> str:
        """Extract code from EVOLVE-BLOCK markers."""
        start_marker = "# EVOLVE-BLOCK-START"
        end_marker = "# EVOLVE-BLOCK-END"
        if start_marker in code and end_marker in code:
            start = code.index(start_marker) + len(start_marker) + 1
            end = code.index(end_marker)
            return code[start:end].strip()
        return code


# ---------------------------------------------------------------------------
# Autonomous Agent
# ---------------------------------------------------------------------------

class ShinkaEvolveAgent(AutonomousAgent):
    """Agent that uses evolutionary algorithms to fix code when standard fixers fail.

    Activates when:
    - ESCALATION_EXHAUSTED: All standard fix strategies have been tried
    - Repeated CODE_FIX_NEEDED for the same file (> ESCALATION_THRESHOLD times)
    """

    name = "ShinkaEvolveAgent"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._fix_attempt_counts: Dict[str, int] = {}
        self._task_builder = ShinkaTaskBuilder()

    @property
    def subscribed_events(self) -> list:
        return [
            EventType.ESCALATION_EXHAUSTED,
            EventType.CODE_FIX_NEEDED,
        ]

    def should_act(self, event: Event) -> bool:
        """Act on escalation exhaustion or repeated fix failures."""
        if event.event_type == EventType.ESCALATION_EXHAUSTED:
            return True

        if event.event_type == EventType.CODE_FIX_NEEDED:
            file_path = event.data.get("file", "")
            if file_path:
                self._fix_attempt_counts[file_path] = (
                    self._fix_attempt_counts.get(file_path, 0) + 1
                )
                if self._fix_attempt_counts[file_path] >= ESCALATION_THRESHOLD:
                    return True
        return False

    async def act(self, event: Event) -> None:
        """Run evolutionary code improvement."""
        shared = SharedState()
        project_dir = shared.get("project_dir", self.working_dir)
        file_path = event.data.get("file", "")

        if not file_path:
            logger.warning("ShinkaEvolveAgent: No file in event data")
            return

        logger.info(
            "ShinkaEvolveAgent activated",
            file=file_path,
            event_type=event.event_type.value,
            fix_attempts=self._fix_attempt_counts.get(file_path, 0),
        )

        # Read the current code
        try:
            code = Path(file_path).read_text(encoding="utf-8")
        except Exception as e:
            logger.error("Cannot read target file", file=file_path, error=str(e))
            return

        # Collect errors from event data and shared state
        errors = event.data.get("errors", [])
        if not errors:
            errors = [{"type": "unknown", "message": event.data.get("reason", "Fix needed")}]

        # Build ShinkaEvolve task
        task = self._task_builder.build_task(
            code=code,
            file_path=file_path,
            errors=errors,
            project_dir=project_dir,
        )

        # Emit EVOLUTION_STARTED
        bus = EventBus()
        await bus.publish(Event(
            type=EventType.EVOLUTION_STARTED,
            source=self.name,
            data={"agent": self.name, "file": file_path, "errors": len(errors)},
        ))

        # Run evolution in thread pool
        loop = asyncio.get_event_loop()
        runner = EvolutionRunner(task)
        evolved_code = await loop.run_in_executor(None, runner.run)

        if evolved_code and evolved_code != code:
            # Write the evolved code back
            try:
                Path(file_path).write_text(evolved_code, encoding="utf-8")
                logger.info("Evolved code applied", file=file_path)

                # Reset fix counter
                self._fix_attempt_counts[file_path] = 0

                # Emit CODE_FIXED and EVOLUTION_APPLIED
                await bus.publish(code_fixed_event(
                    file=file_path,
                    fix_type="shinka_evolution",
                    details=f"Evolved via ShinkaEvolve ({runner.max_generations} generations)",
                ))
                await bus.publish(Event(
                    type=EventType.EVOLUTION_APPLIED,
                    source=self.name,
                    data={
                        "agent": self.name,
                        "file": file_path,
                        "generations": runner.max_generations,
                    },
                ))

                # Store evolution result
                shared.set("shinka_last_result", {
                    "file": file_path,
                    "task_dir": str(task.task_dir),
                    "timestamp": datetime.now().isoformat(),
                    "success": True,
                })

            except Exception as e:
                logger.error("Failed to write evolved code", error=str(e))
                await bus.publish(system_error_event(
                    f"ShinkaEvolve: failed to write evolved code: {e}"
                ))
        else:
            logger.warning("ShinkaEvolve did not find improvement", file=file_path)
            await bus.publish(Event(
                type=EventType.EVOLUTION_FAILED,
                source=self.name,
                data={
                    "agent": self.name,
                    "file": file_path,
                    "generations": runner.max_generations,
                },
            ))

            shared.set("shinka_last_result", {
                "file": file_path,
                "task_dir": str(task.task_dir),
                "timestamp": datetime.now().isoformat(),
                "success": False,
            })
