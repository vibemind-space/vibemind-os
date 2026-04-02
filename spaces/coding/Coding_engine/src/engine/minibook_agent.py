"""
MinibookAgent — Base class for all AI agents in the Coding Engine.

Each agent:
  1. Has a Minibook account (registered via MinibookClient)
  2. Thinks via Ollama (qwen2.5-coder local LLM)
  3. Communicates by posting/commenting in Minibook
  4. Polls for @mentions / notifications to receive work
  5. Has a specialized system prompt for its role

Subclass this to create specialized agents (architect, generator, tester, etc.)
"""
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.engine.ollama_client import OllamaClient, OllamaResponse
from src.engine.minibook_client import MinibookClient, MinibookAgent as MBAgent

logger = logging.getLogger(__name__)


@dataclass
class AgentIdentity:
    """Agent identity in Minibook."""
    name: str
    role: str
    minibook_id: str = ""
    api_key: str = ""


@dataclass
class TaskContext:
    """Context passed to an agent when processing a task."""
    post_id: str
    post_title: str
    post_content: str
    project_id: str
    project_name: str = ""
    previous_comments: List[Dict[str, Any]] = field(default_factory=list)
    related_posts: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    """Result from an agent's work."""
    success: bool
    content: str
    files_generated: List[Dict[str, str]] = field(default_factory=list)  # [{path, content}]
    tokens_used: int = 0
    duration_ms: int = 0
    error: Optional[str] = None


class MinibookAgentBase(ABC):
    """
    Base class for all Minibook-integrated AI agents.

    Each agent registers in Minibook, receives tasks via @mentions,
    thinks using Ollama (qwen2.5-coder), and posts results back.
    """

    def __init__(
        self,
        name: str,
        role: str,
        minibook: MinibookClient,
        ollama: OllamaClient,
        project_id: Optional[str] = None,
    ) -> None:
        self.identity = AgentIdentity(name=name, role=role)
        self.minibook = minibook
        self.ollama = ollama
        self.project_id = project_id
        self._conversation_history: List[Dict[str, str]] = []
        self._max_history = 20  # Keep last N messages for context
        logger.info("MinibookAgent created: %s (role=%s)", name, role)

    # ------------------------------------------------------------------
    # Abstract: Subclasses define their personality
    # ------------------------------------------------------------------
    @abstractmethod
    def get_system_prompt(self) -> str:
        """Return the system prompt for this agent's role."""
        ...

    @abstractmethod
    def get_role_description(self) -> str:
        """Short description of what this agent does."""
        ...

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------
    def register(self) -> bool:
        """Register this agent in Minibook. Returns True on success."""
        import time as _time
        try:
            # Try registering with the base name first
            try:
                agent = self.minibook.register_agent(self.identity.name)
                self.identity.minibook_id = agent.id
                self.identity.api_key = agent.api_key
                logger.info("Agent %s registered: id=%s", self.identity.name, agent.id)
                return True
            except Exception:
                pass

            # Name taken — add timestamp suffix and retry
            unique_name = f"{self.identity.name}-{int(_time.time()) % 100000}"
            agent = self.minibook.register_agent(unique_name)
            self.identity.name = unique_name
            self.identity.minibook_id = agent.id
            self.identity.api_key = agent.api_key
            logger.info("Agent %s registered (suffixed): id=%s", unique_name, agent.id)
            return True
        except Exception as e:
            logger.error("Failed to register agent %s: %s", self.identity.name, e)
            return False

    def join_project(self, project_id: str) -> bool:
        """Join a Minibook project."""
        self.project_id = project_id
        return self.minibook.join_project(
            self.identity.api_key, project_id, role=self.identity.role
        )

    def send_heartbeat(self) -> bool:
        """Mark this agent as online."""
        return self.minibook.heartbeat(self.identity.api_key)

    # ------------------------------------------------------------------
    # Core: Think + Respond
    # ------------------------------------------------------------------
    def think(self, task: TaskContext) -> AgentResult:
        """
        Process a task: read context, think via Ollama, return result.

        This is the main entry point for agent work.
        """
        start = time.time()

        # Build the prompt with full context
        prompt = self._build_prompt(task)

        # Add to conversation history
        self._conversation_history.append({"role": "user", "content": prompt})
        self._trim_history()

        # Build system prompt with file output instructions
        system = self.get_system_prompt() + """

CRITICAL OUTPUT RULES:
1. When generating code files, you MUST wrap each file in a code block with the filepath on the opening line.
2. EVERY file must be COMPLETE — full imports, full class body, full method implementations.
3. NEVER write "// ... rest of implementation" or "// TODO" — write the ACTUAL code.

FORMAT — use exactly this pattern for each file:

```typescript filepath: src/auth/auth.module.ts
import { Module } from '@nestjs/common';
// ... full file content here
```

```python filepath: src/models/user.py
from sqlalchemy import Column
# ... full file content here
```

RULES:
- Use: ```<language> filepath: <path>
- One code block per file
- Include ALL imports at the top
- Write COMPLETE method bodies with real logic
- If a file would be very long, still write it completely"""

        # Call Ollama
        response = self.ollama.chat(
            messages=self._conversation_history,
            system=system,
        )

        if response.error:
            return AgentResult(
                success=False,
                content="",
                error=response.error,
                duration_ms=int((time.time() - start) * 1000),
            )

        # Save assistant response to history
        self._conversation_history.append({"role": "assistant", "content": response.content})

        # Parse generated files from response
        files = self._extract_files(response.content)

        duration = int((time.time() - start) * 1000)
        logger.info(
            "Agent %s thought for %dms, generated %d files",
            self.identity.name, duration, len(files),
        )

        return AgentResult(
            success=True,
            content=response.content,
            files_generated=files,
            tokens_used=response.prompt_eval_count + response.eval_count,
            duration_ms=duration,
        )

    def respond_to_post(self, task: TaskContext) -> Optional[str]:
        """
        Full cycle: think about a task and post the response as a comment.

        Returns the comment ID or None on failure.
        """
        result = self.think(task)

        if not result.success:
            logger.error("Agent %s failed: %s", self.identity.name, result.error)
            # Post error as comment so orchestrator can see it
            error_comment = self.minibook.create_comment(
                self.identity.api_key,
                task.post_id,
                f"⚠️ Error: {result.error}",
            )
            return error_comment.id if error_comment else None

        # Post the result as a comment
        comment = self.minibook.create_comment(
            self.identity.api_key,
            task.post_id,
            result.content,
        )
        logger.info(
            "Agent %s responded to post '%s' (comment=%s)",
            self.identity.name, task.post_title, comment.id,
        )
        return comment.id

    # ------------------------------------------------------------------
    # Notifications / Polling
    # ------------------------------------------------------------------
    def check_mentions(self) -> List[Dict[str, Any]]:
        """Check for unread notifications (mentions, replies)."""
        try:
            return self.minibook.get_notifications(self.identity.api_key, unread_only=True)
        except Exception as e:
            logger.error("Failed to check notifications for %s: %s", self.identity.name, e)
            return []

    def acknowledge(self, notification_id: str) -> bool:
        """Mark a notification as read."""
        return self.minibook.mark_notification_read(self.identity.api_key, notification_id)

    # ------------------------------------------------------------------
    # Posting helpers
    # ------------------------------------------------------------------
    def post_task(
        self,
        title: str,
        content: str,
        tags: Optional[List[str]] = None,
        post_type: str = "discussion",
    ) -> Optional[str]:
        """Create a new post (task). Returns post ID."""
        if not self.project_id:
            logger.error("Agent %s has no project_id set", self.identity.name)
            return None
        post = self.minibook.create_post(
            self.identity.api_key,
            self.project_id,
            title,
            content,
            post_type=post_type,
            tags=tags,
        )
        return post.id

    def comment(self, post_id: str, content: str) -> Optional[str]:
        """Post a comment. Returns comment ID."""
        c = self.minibook.create_comment(self.identity.api_key, post_id, content)
        return c.id

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _build_prompt(self, task: TaskContext) -> str:
        """Build a rich prompt from the task context."""
        parts = [
            f"# Task: {task.post_title}",
            "",
            task.post_content,
        ]

        if task.previous_comments:
            parts.append("\n## Previous Discussion:")
            for c in task.previous_comments:
                author = c.get("author_name", "unknown")
                content = c.get("content", "")
                parts.append(f"\n**{author}:**\n{content}")

        if task.related_posts:
            parts.append("\n## Related Context:")
            for p in task.related_posts:
                parts.append(f"\n### {p.get('title', 'Untitled')}")
                parts.append(p.get("content", "")[:2000])

        if task.metadata:
            parts.append(f"\n## Additional Info:\n```json\n{task.metadata}\n```")

        return "\n".join(parts)

    def _extract_files(self, content: str) -> List[Dict[str, str]]:
        """
        Extract file blocks from LLM response.

        Supports many formats:
          ```filepath: src/foo.ts           (explicit filepath)
          ```typescript                      (with // src/foo.ts as first line)
          ```ts src/foo.ts                   (path after lang)
          **File: `src/foo.ts`**             (markdown header + code block)
          ### `src/foo.ts`                   (h3 header + code block)
          // File: src/foo.ts                (comment inside code block)
        """
        import re
        files = []
        lines = content.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i].strip()

            detected_path = ""

            # Pattern 1: ```filepath: path or ```lang filepath: path
            if line.startswith("```") and "filepath:" in line.lower():
                detected_path = line.split("filepath:", 1)[1].strip().rstrip("`")

            # Pattern 2: ```lang path/to/file.ext (path with / in it after lang)
            elif line.startswith("```") and "/" in line:
                after_ticks = line[3:].strip()
                # e.g. "typescript src/auth/auth.module.ts" or just "src/foo.ts"
                parts = after_ticks.split(None, 1)
                if len(parts) == 2 and "/" in parts[1]:
                    detected_path = parts[1].strip()
                elif len(parts) == 1 and "/" in parts[0] and "." in parts[0]:
                    detected_path = parts[0].strip()

            # Pattern 3: ```lang  then first line is // path or # path
            elif line.startswith("```") and line != "```":
                # Peek at next line for a path comment
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    path_match = re.match(r'^(?://|#|/\*)\s*(?:File:\s*)?(.+\..{1,5})$', next_line)
                    if path_match and "/" in path_match.group(1):
                        detected_path = path_match.group(1).strip().rstrip(" */")

            # If we found a code block start with a path
            if detected_path and line.startswith("```"):
                i += 1
                # Skip the path comment line if it was pattern 3
                if i < len(lines) and detected_path in lines[i]:
                    i += 1
                code_lines = []
                while i < len(lines) and lines[i].strip() != "```":
                    code_lines.append(lines[i])
                    i += 1
                if detected_path:
                    files.append({"path": detected_path, "content": "\n".join(code_lines)})
                i += 1
                continue

            # Pattern 4: **File: `src/foo.ts`** or ### `src/foo.ts` or ### src/foo.ts
            header_match = re.match(
                r'^(?:\*\*File:\s*`?|#{1,4}\s+`?)([^`*]+\.[a-z]{1,5})`?\s*\**$',
                line
            )
            if header_match and "/" in header_match.group(1):
                detected_path = header_match.group(1).strip()
                # Find next code block
                i += 1
                while i < len(lines) and not lines[i].strip().startswith("```"):
                    i += 1
                if i < len(lines):
                    i += 1  # skip opening ```
                    code_lines = []
                    while i < len(lines) and lines[i].strip() != "```":
                        code_lines.append(lines[i])
                        i += 1
                    if detected_path and code_lines:
                        files.append({"path": detected_path, "content": "\n".join(code_lines)})
                i += 1
                continue

            # Pattern 5: File: src/foo.ts (plain text, no markdown)
            plain_file_match = re.match(
                r'^(?:File|Filename|Path):\s*`?([^\s`]+\.[a-z]{1,5})`?\s*$',
                line, re.IGNORECASE,
            )
            if plain_file_match and "/" in plain_file_match.group(1):
                detected_path = plain_file_match.group(1).strip()
                i += 1
                while i < len(lines) and not lines[i].strip().startswith("```"):
                    i += 1
                if i < len(lines):
                    i += 1  # skip opening ```
                    code_lines = []
                    while i < len(lines) and lines[i].strip() != "```":
                        code_lines.append(lines[i])
                        i += 1
                    if detected_path and code_lines:
                        files.append({"path": detected_path, "content": "\n".join(code_lines)})
                i += 1
                continue

            i += 1
        return files

    def _trim_history(self) -> None:
        """Keep conversation history manageable."""
        if len(self._conversation_history) > self._max_history * 2:
            # Keep system context (first 2) + last N
            self._conversation_history = self._conversation_history[-self._max_history:]

    def reset_history(self) -> None:
        """Clear conversation history."""
        self._conversation_history = []
