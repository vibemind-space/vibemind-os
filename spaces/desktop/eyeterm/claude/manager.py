"""Multi-session Claude Code CLI manager for eyeTerm panes."""

import json
import logging
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PaneSession:
    """Tracks a Claude Code CLI session bound to a single pane."""

    pane_index: int
    workdir: str
    session_id: Optional[str] = None
    name: str = ""
    last_result: Optional[Dict[str, Any]] = None
    is_busy: bool = False
    process: Optional[subprocess.Popen] = None


class ClaudeSessionManager:
    """Manages multiple Claude Code CLI sessions, one per pane."""

    def __init__(self, panes: list, claude_cli_path: str = "claude"):
        self._sessions: Dict[int, PaneSession] = {}
        self._cli = claude_cli_path
        self._executor = ThreadPoolExecutor(max_workers=4)
        self._lock = threading.Lock()

        # Initialize sessions from panes config
        for i, pane in enumerate(panes):
            workdir = pane.get("workdir", ".") if isinstance(pane, dict) else "."
            name = pane.get("name", f"Pane {i}") if isinstance(pane, dict) else f"Pane {i}"
            self._sessions[i] = PaneSession(
                pane_index=i,
                workdir=workdir,
                name=name,
            )
        logger.info("ClaudeSessionManager initialized with %d panes", len(self._sessions))

    def send_prompt(
        self, pane_index: int, prompt: str, context: str = ""
    ) -> Dict[str, Any]:
        """Send prompt to pane's Claude session. Blocks until done.

        Runs: claude -p <prompt> --output-format json [--resume <session_id>]
        cwd: pane's workdir.
        If context is provided, it is prepended to the prompt.
        Parses JSON output, extracts session_id for future --resume.
        Returns parsed result dict.
        """
        session = self._sessions.get(pane_index)
        if session is None:
            return {"error": f"No session for pane {pane_index}", "success": False}

        if session.is_busy:
            return {"error": f"Pane {pane_index} is busy", "success": False}

        # Build the effective prompt
        effective_prompt = f"{context}\n\n{prompt}" if context else prompt

        # Build command
        cmd = [self._cli, "-p", effective_prompt, "--output-format", "json"]
        if session.session_id:
            cmd.extend(["--resume", session.session_id])

        with self._lock:
            session.is_busy = True

        try:
            logger.debug(
                "Running Claude CLI for pane %d in %s", pane_index, session.workdir
            )
            proc = subprocess.Popen(
                cmd,
                cwd=session.workdir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            session.process = proc

            stdout, stderr = proc.communicate()

            if proc.returncode != 0:
                logger.error(
                    "Claude CLI error (pane %d): %s", pane_index, stderr.strip()
                )
                result = {
                    "success": False,
                    "error": stderr.strip() or f"Exit code {proc.returncode}",
                    "raw_output": stdout,
                }
            else:
                try:
                    result = json.loads(stdout)
                    result["success"] = True
                    # Extract session_id for future --resume
                    if "session_id" in result:
                        session.session_id = result["session_id"]
                except json.JSONDecodeError:
                    result = {
                        "success": True,
                        "raw_output": stdout,
                        "parse_error": "Could not parse JSON output",
                    }

            session.last_result = result
            return result

        except FileNotFoundError:
            msg = f"Claude CLI not found at '{self._cli}'"
            logger.error(msg)
            return {"success": False, "error": msg}
        except Exception as exc:
            logger.exception("Unexpected error in send_prompt for pane %d", pane_index)
            return {"success": False, "error": str(exc)}
        finally:
            with self._lock:
                session.is_busy = False
                session.process = None

    def send_prompt_async(
        self,
        pane_index: int,
        prompt: str,
        on_done: Callable[[int, Dict[str, Any]], None],
        context: str = "",
    ) -> None:
        """Non-blocking. Runs in ThreadPoolExecutor, calls on_done(pane_index, result)."""

        def _worker():
            result = self.send_prompt(pane_index, prompt, context=context)
            try:
                on_done(pane_index, result)
            except Exception:
                logger.exception("on_done callback failed for pane %d", pane_index)

        self._executor.submit(_worker)

    def cancel(self, pane_index: int) -> bool:
        """Kill running subprocess for pane. Returns True if a process was killed."""
        session = self._sessions.get(pane_index)
        if session is None:
            return False

        proc = session.process
        if proc is not None and proc.poll() is None:
            logger.info("Cancelling Claude CLI process for pane %d", pane_index)
            proc.kill()
            with self._lock:
                session.is_busy = False
                session.process = None
            return True
        return False

    def get_status(self, pane_index: int) -> Dict[str, Any]:
        """Return pane session status."""
        logger.debug("get_status called: pane_index=%s", pane_index)
        session = self._sessions.get(pane_index)
        if session is None:
            return {"error": f"No session for pane {pane_index}"}

        last_snippet = ""
        if session.last_result:
            raw = session.last_result.get("raw_output", "")
            result_text = session.last_result.get("result", raw)
            if isinstance(result_text, str):
                last_snippet = result_text[:120]

        return {
            "pane_index": session.pane_index,
            "name": session.name,
            "workdir": session.workdir,
            "session_id": session.session_id,
            "is_busy": session.is_busy,
            "has_result": session.last_result is not None,
            "last_snippet": last_snippet,
        }

    def get_all_statuses(self) -> List[Dict[str, Any]]:
        """Return all pane statuses for UI display."""
        return [self.get_status(i) for i in sorted(self._sessions.keys())]

    def shutdown(self) -> None:
        """Cancel all running sessions and shut down the thread pool."""
        for idx in list(self._sessions.keys()):
            self.cancel(idx)
        self._executor.shutdown(wait=False)
        logger.info("ClaudeSessionManager shut down")
