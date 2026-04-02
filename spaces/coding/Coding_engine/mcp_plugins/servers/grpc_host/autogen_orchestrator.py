#!/usr/bin/env python3
"""
AutoGen-basierter EventFixTeam Orchestrator

Dieser Orchestrator verwendet AutoGen 0.4 um MCP Tools via einem
Reasoning Agent zu orchestrieren. Er löst komplexe Aufgaben durch
Multi-Step Tool Calling.

Architektur:
- ReasoningAgent: Plant und führt Tool Calls aus
- ValidatorAgent: Prüft ob Aufgabe erledigt wurde
- RoundRobinGroupChat: Koordiniert die Agents
- McpWorkbench: Stellt 100+ Tools von 26 MCP Servern bereit
"""
import asyncio
import json
import os
import sys
import time
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass, field
from src.llm_config import get_model

# Force UTF-8 encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Load .env from project root
try:
    import dotenv
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', '.env')
    dotenv.load_dotenv(dotenv_path=env_path)
except Exception:
    pass

# AutoGen imports
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.conditions import TextMentionTermination
from autogen_agentchat.base import TerminationCondition, TerminatedException
from autogen_agentchat.messages import AgentEvent, ChatMessage, StopMessage
from autogen_core.model_context import BufferedChatCompletionContext
from pydantic import BaseModel


class AgentTextMentionTermination(TerminationCondition):
    """
    Terminiert nur wenn ein Agent (nicht User) den Text erwähnt.
    Verhindert false positives wenn der Text im initialen Prompt steht.
    """

    def __init__(self, text: str):
        self._text = text
        self._terminated = False

    @property
    def terminated(self) -> bool:
        return self._terminated

    async def __call__(self, messages: list[AgentEvent | ChatMessage]) -> StopMessage | None:
        if self._terminated:
            raise TerminatedException("Termination condition already triggered")

        for msg in messages:
            # Nur Agent-Messages prüfen (nicht user)
            source = getattr(msg, 'source', None)
            if source and source != 'user':
                content = getattr(msg, 'content', '')
                if isinstance(content, str) and self._text in content:
                    self._terminated = True
                    return StopMessage(
                        content=f"Agent '{source}' mentioned '{self._text}'",
                        source="AgentTextMentionTermination"
                    )
        return None

    async def reset(self) -> None:
        self._terminated = False

# Shared module imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
from event_server import EventServer
from constants import (
    SESSION_STATE_RUNNING,
    SESSION_STATE_STOPPED,
    SESSION_STATE_ERROR,
)
from model_utils import get_model_client as shared_get_model_client
from conversation_logger import ConversationLogger, SenseCategory

# Local imports
from mcp_workbench import get_workbench_manager, get_all_mcp_tools, AUTOGEN_MCP_AVAILABLE
from task_prompts import get_task_prompt, TASK_PROMPTS
from tool_execution_verifier import ToolExecutionVerifier, ToolExecutionResult
from container_validator import ContainerValidator, ValidationResult
from tool_category_filter import ToolCategoryFilter, DynamicPromptGenerator, FilteredToolSet
from smart_agent_selector import (
    SmartAgentSelector,
    SelectionResult,
    create_fix_suggestion_agent,
    FIX_SUGGESTION_AGENT_PROMPT
)
from tool_execution_cache import ToolExecutionCache, CachingToolWrapper
from parallel_executor import ParallelExecutor, detect_parallel_opportunities
from error_classifier import ErrorClassifier, ErrorType, ClassifiedError
from recovery_strategies import RecoveryOrchestrator, RecoveryContext
from circuit_breaker import ToolCircuitBreaker, CircuitOpenError
from execution_history import ExecutionHistoryStore, ToolExecution
from orchestrator_metrics import OrchestratorMetrics, get_metrics
from adaptive_prompts import AdaptivePromptGenerator

logger = logging.getLogger(__name__)


# ============================================================================
# Configuration
# ============================================================================

class OrchestratorConfig(BaseModel):
    """Konfiguration für den EventFix Orchestrator"""
    session_id: str
    task: str
    task_type: str = "general"
    parameters: Dict[str, Any] = {}
    model: str = field(default_factory=lambda: get_model("mcp_standard"))
    max_turns: int = 30
    working_dir: str = "."


# ============================================================================
# System Prompts
# ============================================================================

REASONING_AGENT_PROMPT = """Du bist ein Reasoning Agent für das EventFix Team.
Deine Aufgabe: Analysiere Anfragen und löse sie durch gezielte Tool Calls.

## Verfügbare Tool-Kategorien:

### Dateisystem
- filesystem: read_file, write_file, list_directory, delete_file, create_directory

### Container & Infrastructure
- docker: container_logs, container_stats, container_start, container_stop, compose_up
- redis: get, set, delete, keys, info

### Datenbank
- postgres: query, list_tables, describe_table, explain_query
- prisma: generate, migrate, db_push, validate, format

### Browser & Testing
- playwright: navigate, click, type, screenshot, evaluate

### Package Management
- npm: install, run, audit, list, outdated

### Version Control
- git: status, diff, log, commit, push, branch

### Web & Suche
- fetch: HTTP requests
- tavily: Web search
- brave-search: Web search

## Arbeitsweise:

1. **Analyse**: Verstehe was die Aufgabe erfordert
2. **Planung**: Identifiziere die nötigen Tools und ihre Reihenfolge
3. **Ausführung**: Rufe Tools auf und verarbeite Ergebnisse
4. **Validierung**: Prüfe ob das Ergebnis korrekt ist
5. **Abschluss**: Sage TASK_COMPLETE wenn fertig

## Regeln:

- Führe nur die nötigen Tool Calls aus
- Prüfe Ergebnisse bevor du weitermachst
- Bei Fehlern: Analysiere und versuche Alternative
- Dokumentiere wichtige Schritte
- Sage TASK_COMPLETE nur wenn die Aufgabe wirklich erledigt ist
"""

QA_VALIDATOR_PROMPT = """Du bist ein QA Validator für das EventFix Team.

## Deine Aufgabe:

1. Prüfe ob die Aufgabe vollständig erledigt wurde
2. Validiere dass keine Fehler aufgetreten sind
3. Stelle sicher dass das Ergebnis den Anforderungen entspricht

## Regeln:

- Prüfe die Tool-Outputs auf Erfolg
- Frage nach wenn etwas unklar ist
- Sage TASK_COMPLETE nur wenn:
  - Alle Schritte erfolgreich waren
  - Das Ergebnis den Anforderungen entspricht
  - Keine offenen Fehler existieren

Bei Fehlern: Beschreibe was nicht funktioniert hat und warum.
"""


# ============================================================================
# Orchestrator
# ============================================================================

@dataclass
class TaskResult:
    """Ergebnis einer Task-Ausführung"""
    task_id: str
    status: str  # "completed", "failed", "timeout"
    result: Any = None
    error: Optional[str] = None
    steps: int = 0
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    duration_ms: int = 0
    messages: List[Dict[str, Any]] = field(default_factory=list)


class EventFixOrchestrator:
    """
    Orchestriert MCP Tools via AutoGen Team

    Verwendet einen ReasoningAgent mit allen MCP Tools und einen
    ValidatorAgent zur Qualitätskontrolle.
    """

    def __init__(
        self,
        model: str = None,
        event_server: Optional[EventServer] = None,
        max_turns: int = 30,
        working_dir: str = "."
    ):
        """
        Initialisiert den Orchestrator

        Args:
            model: Model ID für die Agents
            event_server: EventServer für Broadcasts (optional)
            max_turns: Maximale Turns pro Task
            working_dir: Arbeitsverzeichnis für Dateioperationen
        """
        self.model = model or get_model("mcp_standard")
        self.event_server = event_server or EventServer()
        self.max_turns = max_turns
        self.working_dir = working_dir

        self.model_client = None
        self.reasoning_agent = None
        self.validator_agent = None
        self.team = None

        self._initialized = False
        self._mcp_tools = []

        # Tool Execution Verifier für Datei-Operationen
        self._tool_verifier = ToolExecutionVerifier(
            base_path=working_dir,
            max_retries=3,
            use_fallback=True
        )

        # Tool Category Filter für reduzierte Tool-Auswahl (Iteration 1)
        self._tool_filter = ToolCategoryFilter(max_tools=30)
        self._prompt_generator = DynamicPromptGenerator(self._tool_filter)
        self._current_task_type = "general"

        # Smart Agent Selector für dynamische Agent-Auswahl (Iteration 2)
        self._agent_selector = SmartAgentSelector(
            reasoning_agent_name="ReasoningAgent",
            fix_agent_name="FixSuggestionAgent",
            validator_agent_name="ValidatorAgent",
            max_consecutive_errors=3,
            stagnation_threshold=3
        )
        self.fix_suggestion_agent = None

        # Tool Execution Cache (Iteration 3)
        self._tool_cache = ToolExecutionCache(max_entries=500, max_memory_mb=25.0)

        # Parallel Executor (Iteration 3)
        self._parallel_executor = ParallelExecutor(max_parallel=5, cache=self._tool_cache)

        # Error Classifier und Recovery (Iteration 4)
        self._error_classifier = ErrorClassifier()
        self._recovery_orchestrator = RecoveryOrchestrator()

        # Circuit Breaker (Iteration 4)
        self._circuit_breaker = ToolCircuitBreaker(
            failure_threshold=3,
            timeout_seconds=60,
            success_threshold=1
        )

        # Execution History (Iteration 5)
        self._execution_history = ExecutionHistoryStore()

        # Orchestrator Metrics (Iteration 5)
        self._metrics = get_metrics()

        # Adaptive Prompts (Iteration 5)
        self._adaptive_prompts = AdaptivePromptGenerator(
            history_store=self._execution_history,
            tool_filter=self._tool_filter
        )

        logger.info(f"EventFixOrchestrator erstellt (model={model}, max_turns={max_turns}, working_dir={working_dir})")
        logger.info("  - Tool filtering: enabled")
        logger.info("  - Smart agent selector: enabled")
        logger.info("  - Tool cache: enabled")
        logger.info("  - Circuit breaker: enabled")
        logger.info("  - Execution history: enabled")
        logger.info("  - Metrics: enabled")

    async def initialize(self):
        """Initialisiert Agents und lädt MCP Tools"""
        if self._initialized:
            return

        logger.info("Initialisiere EventFixOrchestrator...")

        # Model Client initialisieren
        self.model_client = shared_get_model_client(self.model)

        # MCP Tools laden
        if AUTOGEN_MCP_AVAILABLE:
            try:
                self._mcp_tools = await get_all_mcp_tools()
                logger.info(f"Loaded {len(self._mcp_tools)} MCP tools")
            except Exception as e:
                logger.warning(f"Konnte MCP Tools nicht laden: {e}")
                self._mcp_tools = []
        else:
            logger.warning("AutoGen MCP nicht verfügbar - keine MCP Tools geladen")

        # Agents erstellen
        self._setup_agents()

        self._initialized = True
        logger.info("EventFixOrchestrator initialisiert")

    def _create_team(self, task_type: str = "general") -> RoundRobinGroupChat:
        """
        Create a fresh team instance for a single task execution.

        Each call returns independent agents + team, safe for concurrent use.
        Shared resources (model_client, _mcp_tools, caches) remain on self.

        Args:
            task_type: Art der Aufgabe für Tool-Filterung

        Returns:
            Fresh RoundRobinGroupChat ready for team.run()
        """
        # Tools filtern basierend auf Task-Typ (Iteration 1: Tool Filtering)
        if self._mcp_tools:
            filtered_result = self._tool_filter.filter_for_task(
                self._mcp_tools,
                task_type=task_type
            )
            filtered_tools = filtered_result.tools

            # Dynamischen Prompt generieren
            dynamic_prompt = self._prompt_generator.generate_prompt(
                filtered_result,
                task_type=task_type
            )

            logger.info(f"Tool filtering: {filtered_result.total_available} -> {filtered_result.filtered_count} tools for task_type={task_type}")
        else:
            filtered_tools = []
            dynamic_prompt = REASONING_AGENT_PROMPT

        # Reasoning Agent mit gefilterten MCP Tools
        reasoning_agent = AssistantAgent(
            name="ReasoningAgent",
            model_client=self.model_client,
            tools=filtered_tools,
            system_message=dynamic_prompt,
            model_context=BufferedChatCompletionContext(buffer_size=20),
        )

        # Validator Agent (ohne Tools)
        validator_agent = AssistantAgent(
            name="ValidatorAgent",
            model_client=self.model_client,
            system_message=QA_VALIDATOR_PROMPT,
            model_context=BufferedChatCompletionContext(buffer_size=10),
        )

        # FixSuggestionAgent mit read-only Tools (Iteration 2)
        read_only_tools = self._get_read_only_tools(filtered_tools)
        fix_suggestion_agent = AssistantAgent(
            name="FixSuggestionAgent",
            model_client=self.model_client,
            tools=read_only_tools,
            system_message=FIX_SUGGESTION_AGENT_PROMPT,
            model_context=BufferedChatCompletionContext(buffer_size=15),
        )

        # Team Setup - use custom termination that ignores user messages
        team = RoundRobinGroupChat(
            participants=[reasoning_agent, validator_agent],
            termination_condition=AgentTextMentionTermination("TASK_COMPLETE"),
            max_turns=self.max_turns,
        )

        logger.info(f"Fresh team created for task_type={task_type} ({len(filtered_tools)} tools, {len(read_only_tools)} read-only)")
        return team

    def _setup_agents(self, task_type: str = "general"):
        """Legacy wrapper: creates team and stores on self for non-concurrent use."""
        self._current_task_type = task_type
        self._agent_selector.reset()
        self.team = self._create_team(task_type)

    def _get_read_only_tools(self, tools: List[Any]) -> List[Any]:
        """
        Filtert nur read-only Tools aus einer Tool-Liste.

        Args:
            tools: Alle verfügbaren Tools

        Returns:
            Liste von read-only Tools
        """
        read_only_patterns = ['read', 'list', 'get', 'search', 'find', 'describe', 'show', 'info', 'stat']

        read_only_tools = []
        for tool in tools:
            tool_name = getattr(tool, "name", "").lower()
            if any(pattern in tool_name for pattern in read_only_patterns):
                read_only_tools.append(tool)

        return read_only_tools

    async def get_fix_suggestion(
        self,
        error_context: str,
        file_paths: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Ruft den FixSuggestionAgent für eine Fehleranalyse auf.

        Dies ist eine direkte Intervention wenn der normale Ablauf
        wiederholt Fehler produziert.

        Args:
            error_context: Beschreibung der Fehler
            file_paths: Optionale Liste relevanter Dateien

        Returns:
            Dict mit suggestion, files_analyzed, confidence
        """
        if not self.fix_suggestion_agent:
            return {"suggestion": None, "error": "FixSuggestionAgent not initialized"}

        # Prompt für FixSuggestionAgent erstellen
        files_hint = ""
        if file_paths:
            files_hint = f"\n\nRelevante Dateien:\n" + "\n".join(f"- {p}" for p in file_paths)

        prompt = f"""Analysiere diese Fehler und schlage konkrete Fixes vor:

{error_context}
{files_hint}

Nutze read_file um die relevanten Dateien zu untersuchen.
Antworte im FIX_SUGGESTION Format.
"""

        try:
            # Einzelnen Turn mit FixSuggestionAgent ausführen
            # Wir nutzen einen temporären Chat dafür
            from autogen_agentchat.teams import RoundRobinGroupChat

            temp_team = RoundRobinGroupChat(
                participants=[self.fix_suggestion_agent],
                termination_condition=AgentTextMentionTermination("FIX_SUGGESTION:"),
                max_turns=3,
            )

            result = await temp_team.run(task=prompt)

            # Suggestion extrahieren
            suggestion = None
            for msg in getattr(result, 'messages', []):
                content = getattr(msg, 'content', '')
                if isinstance(content, list):
                    content = ' '.join(str(c) for c in content)
                if "FIX_SUGGESTION:" in str(content):
                    suggestion = content
                    break

            return {
                "suggestion": suggestion,
                "files_analyzed": file_paths or [],
                "success": suggestion is not None
            }

        except Exception as e:
            logger.error(f"FixSuggestionAgent error: {e}")
            return {"suggestion": None, "error": str(e)}

    async def execute_task_stream(
        self,
        task: str,
        task_type: str = "general",
        context: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None
    ):
        """
        Führt einen Task aus und yieldet Messages live (Streaming)

        Args:
            task: Aufgabenbeschreibung
            task_type: Task-Typ
            context: Zusätzlicher Kontext
            task_id: Task ID für Tracking

        Yields:
            Dict mit type und content für jeden Schritt
        """
        # Initialisieren falls nötig
        if not self._initialized:
            await self.initialize()

        # Fresh team per call for concurrent safety (Phase 26)
        team = self._create_team(task_type=task_type)

        task_id = task_id or f"task_{int(time.time() * 1000)}"
        start_time = time.time()

        yield {
            "type": "task_started",
            "task_id": task_id,
            "task": task[:100],
            "timestamp": datetime.now().isoformat()
        }

        try:
            # Task-Prompt erstellen
            full_task = self._build_task_prompt(task, task_type, context)

            # Team mit Streaming ausführen (local team, not self.team)
            all_messages = []
            all_tool_calls = []

            async for message in team.run_stream(task=full_task):
                # Message verarbeiten
                msg_type = type(message).__name__

                if hasattr(message, 'content'):
                    content = message.content
                    if content is None:
                        content = ''
                    elif isinstance(content, list):
                        content = ' '.join(str(c) for c in content if c)
                    elif not isinstance(content, str):
                        content = str(content)

                    source = getattr(message, 'source', None) or getattr(message, 'name', 'unknown')

                    yield {
                        "type": "agent_message",
                        "source": str(source),
                        "content": content,
                        "message_type": msg_type,
                        "timestamp": datetime.now().isoformat()
                    }

                    msg_dict = {
                        "role": str(getattr(message, 'role', 'assistant')),
                        "content": content,
                        "name": str(source)
                    }
                    all_messages.append(msg_dict)

                    # Update agent selector context (Iteration 2)
                    self._agent_selector.update_context(msg_dict)

                # Tool Calls extrahieren
                if hasattr(message, 'tool_calls') and message.tool_calls:
                    for tc in message.tool_calls:
                        args = getattr(tc, 'arguments', {})
                        if hasattr(args, 'model_dump'):
                            args = args.model_dump()
                        elif hasattr(args, '__dict__'):
                            args = vars(args)
                        elif not isinstance(args, (dict, str, list, int, float, bool, type(None))):
                            args = str(args)

                        tool_call = {
                            "tool": getattr(tc, 'name', 'unknown'),
                            "arguments": args
                        }
                        all_tool_calls.append(tool_call)

                        yield {
                            "type": "tool_call",
                            "tool": tool_call["tool"],
                            "arguments": tool_call["arguments"],
                            "timestamp": datetime.now().isoformat()
                        }

                # Tool Results
                if hasattr(message, 'tool_call_id') or msg_type == 'ToolCallResultMessage':
                    result_content = getattr(message, 'content', '')
                    if isinstance(result_content, list):
                        result_content = ' '.join(str(c) for c in result_content if c)

                    full_content = str(result_content)

                    yield {
                        "type": "tool_result",
                        "content": full_content,  # Full content (not truncated)
                        "content_preview": full_content[:500] if len(full_content) > 500 else full_content,
                        "timestamp": datetime.now().isoformat()
                    }

                    # Verify write operations
                    if all_tool_calls:
                        last_tool = all_tool_calls[-1]
                        tool_name = last_tool.get("tool", "")
                        tool_args = last_tool.get("arguments", {})

                        if self._tool_verifier.is_write_operation(tool_name):
                            file_path = tool_args.get("path") or tool_args.get("file_path")
                            expected_content = tool_args.get("content") or tool_args.get("text")

                            if file_path:
                                verification = await self._tool_verifier.verify_file_write(
                                    file_path,
                                    expected_content=expected_content
                                )

                                if verification.verified:
                                    yield {
                                        "type": "verification_success",
                                        "file_path": verification.file_path,
                                        "file_size": verification.file_size,
                                        "timestamp": datetime.now().isoformat()
                                    }
                                    logger.info(f"Write verified: {file_path} ({verification.file_size} bytes)")
                                else:
                                    # Verification failed - use fallback
                                    logger.warning(f"Write verification failed: {verification.error}")

                                    if expected_content:
                                        fallback_result = await self._tool_verifier.retry_with_fallback(
                                            tool_name, tool_args, verification.error
                                        )

                                        yield {
                                            "type": "fallback_write",
                                            "success": fallback_result.success,
                                            "verified": fallback_result.verified,
                                            "file_path": fallback_result.file_path,
                                            "retry_count": fallback_result.retry_count,
                                            "error": fallback_result.error,
                                            "timestamp": datetime.now().isoformat()
                                        }

                                        if fallback_result.success:
                                            logger.info(f"Fallback write successful: {fallback_result.file_path}")
                                        else:
                                            logger.error(f"Fallback write failed: {fallback_result.error}")

            # Task abgeschlossen
            duration_ms = int((time.time() - start_time) * 1000)
            final_content = all_messages[-1].get("content", "") if all_messages else ""

            # Agent selector stats (Iteration 2)
            selector_stats = self._agent_selector.get_stats()

            yield {
                "type": "task_completed",
                "task_id": task_id,
                "status": "completed",
                "steps": len(all_messages),
                "tool_calls": len(all_tool_calls),
                "duration_ms": duration_ms,
                "result": final_content,
                "agent_selector_stats": selector_stats,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            yield {
                "type": "task_failed",
                "task_id": task_id,
                "error": str(e),
                "duration_ms": duration_ms,
                "timestamp": datetime.now().isoformat()
            }

    async def execute_task(
        self,
        task: str,
        task_type: str = "general",
        context: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None
    ) -> TaskResult:
        """
        Führt einen Task via AutoGen Team aus

        Args:
            task: Aufgabenbeschreibung
            task_type: Task-Typ (write_code, debug_docker, etc.)
            context: Zusätzlicher Kontext
            task_id: Task ID für Tracking

        Returns:
            TaskResult mit Status und Ergebnis
        """
        # Initialisieren falls nötig
        if not self._initialized:
            await self.initialize()

        # Fresh team per call for concurrent safety (Phase 26)
        team = self._create_team(task_type=task_type)

        task_id = task_id or f"task_{int(time.time() * 1000)}"
        start_time = time.time()

        # Event: Task gestartet
        self.event_server.broadcast("task.started", {
            "task_id": task_id,
            "task": task,
            "task_type": task_type,
            "context": context,
            "timestamp": datetime.now().isoformat()
        })

        try:
            # Task-Prompt erstellen
            full_task = self._build_task_prompt(task, task_type, context)

            logger.info(f"Executing task {task_id}: {task[:100]}...")

            # Team ausführen (local team, not self.team)
            result = await team.run(task=full_task)

            # Ergebnis verarbeiten
            messages = self._extract_messages(result)
            tool_calls = self._extract_tool_calls(result)
            final_content = messages[-1].get("content", "") if messages else ""

            # Event: Task abgeschlossen
            duration_ms = int((time.time() - start_time) * 1000)

            self.event_server.broadcast("task.completed", {
                "task_id": task_id,
                "status": "completed",
                "steps": len(messages),
                "tool_calls": len(tool_calls),
                "duration_ms": duration_ms,
                "timestamp": datetime.now().isoformat()
            })

            logger.info(f"Task {task_id} completed: {len(messages)} steps, {len(tool_calls)} tool calls")

            return TaskResult(
                task_id=task_id,
                status="completed",
                result=final_content,
                steps=len(messages),
                tool_calls=tool_calls,
                duration_ms=duration_ms,
                messages=messages
            )

        except asyncio.TimeoutError:
            duration_ms = int((time.time() - start_time) * 1000)

            self.event_server.broadcast("task.timeout", {
                "task_id": task_id,
                "duration_ms": duration_ms,
                "timestamp": datetime.now().isoformat()
            })

            logger.warning(f"Task {task_id} timed out after {duration_ms}ms")

            return TaskResult(
                task_id=task_id,
                status="timeout",
                error="Task timed out",
                duration_ms=duration_ms
            )

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)

            self.event_server.broadcast("task.failed", {
                "task_id": task_id,
                "error": str(e),
                "duration_ms": duration_ms,
                "timestamp": datetime.now().isoformat()
            })

            logger.error(f"Task {task_id} failed: {e}")

            return TaskResult(
                task_id=task_id,
                status="failed",
                error=str(e),
                duration_ms=duration_ms
            )

    async def execute_fix_with_validation(
        self,
        task: str,
        project_path: str,
        validation_type: str = "typescript",
        max_iterations: int = 5,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Führt iterativen Fix-Loop mit Container-Validierung aus.

        Der Orchestrator versucht den Fix, validiert das Ergebnis in einem
        isolierten Docker Container, und iteriert bis der Build erfolgreich ist.

        Args:
            task: Ursprüngliche Aufgabe
            project_path: Pfad zum Projekt
            validation_type: Art der Validierung (typescript, test, lint)
            max_iterations: Maximale Iterationen
            context: Zusätzlicher Kontext

        Returns:
            Dict mit success, iterations, final_errors, validation_results
        """
        if not self._initialized:
            await self.initialize()

        start_time = time.time()
        validator = ContainerValidator(
            project_path=project_path,
            timeout_seconds=300
        )

        all_validations = []
        current_task = task
        current_errors = []

        self.event_server.broadcast("fix_loop.started", {
            "task": task[:200],
            "project_path": project_path,
            "validation_type": validation_type,
            "max_iterations": max_iterations,
            "timestamp": datetime.now().isoformat()
        })

        for iteration in range(max_iterations):
            logger.info(f"=== Fix Iteration {iteration + 1}/{max_iterations} ===")

            self.event_server.broadcast("fix_loop.iteration", {
                "iteration": iteration + 1,
                "max_iterations": max_iterations,
                "task_preview": current_task[:200],
                "previous_errors": len(current_errors),
                "timestamp": datetime.now().isoformat()
            })

            # 1. Fix ausführen
            fix_result = await self.execute_task(
                task=current_task,
                task_type="fix_code",
                context=context
            )

            if fix_result.status != "completed":
                logger.warning(f"Fix task fehlgeschlagen: {fix_result.error}")
                # Trotzdem validieren - vielleicht wurde partial gefixt
                pass

            # 2. In Container validieren
            logger.info(f"Validating {validation_type} in container...")
            validation = await validator.validate_fix(
                validation_type=validation_type,
                install_deps=(iteration == 0)  # Nur beim ersten Mal installieren
            )

            all_validations.append({
                "iteration": iteration + 1,
                "success": validation.success,
                "error_count": validation.error_count,
                "duration_ms": validation.duration_ms
            })

            self.event_server.broadcast("fix_loop.validation", {
                "iteration": iteration + 1,
                "success": validation.success,
                "error_count": validation.error_count,
                "duration_ms": validation.duration_ms,
                "timestamp": datetime.now().isoformat()
            })

            if validation.success:
                # Erfolgreich!
                total_duration_ms = int((time.time() - start_time) * 1000)

                logger.info(f"✅ Fix erfolgreich nach {iteration + 1} Iteration(en)")

                self.event_server.broadcast("fix_loop.success", {
                    "iterations": iteration + 1,
                    "total_duration_ms": total_duration_ms,
                    "timestamp": datetime.now().isoformat()
                })

                return {
                    "success": True,
                    "iterations": iteration + 1,
                    "total_duration_ms": total_duration_ms,
                    "validations": all_validations,
                    "final_output": validation.output,
                    "verification_stats": self._tool_verifier.get_stats(),
                    "validator_stats": validator.get_stats()
                }

            # 3. Errors extrahieren und nächste Iteration vorbereiten
            current_errors = validator.extract_typescript_errors(validation)

            if not current_errors:
                # Fallback: Raw errors aus Output
                error_text = validation.errors or validation.output
                current_errors = [{"raw": error_text[:2000]}]

            # Task für nächste Iteration erstellen
            error_summary = self._format_errors_for_prompt(current_errors)

            current_task = f"""
Vorheriger Fix war nicht vollständig. Der Build hat noch {validation.error_count} Fehler.

Offene TypeScript Errors:
{error_summary}

Ursprüngliche Aufgabe:
{task}

Bitte behebe diese Errors. Nutze die filesystem Tools um Dateien zu lesen und zu schreiben.
Sage TASK_COMPLETE wenn du alle Änderungen gemacht hast.
"""

            logger.warning(f"Iteration {iteration + 1}: Noch {validation.error_count} Errors")

        # Max Iterationen erreicht
        total_duration_ms = int((time.time() - start_time) * 1000)

        logger.error(f"❌ Max Iterationen ({max_iterations}) erreicht, noch {len(current_errors)} Errors")

        self.event_server.broadcast("fix_loop.failed", {
            "iterations": max_iterations,
            "remaining_errors": len(current_errors),
            "total_duration_ms": total_duration_ms,
            "timestamp": datetime.now().isoformat()
        })

        return {
            "success": False,
            "iterations": max_iterations,
            "total_duration_ms": total_duration_ms,
            "validations": all_validations,
            "remaining_errors": current_errors,
            "verification_stats": self._tool_verifier.get_stats(),
            "validator_stats": validator.get_stats()
        }

    def _format_errors_for_prompt(self, errors: List[Dict[str, Any]]) -> str:
        """Formatiert Fehler für den Prompt"""
        lines = []

        for i, err in enumerate(errors[:20], 1):  # Max 20 Errors
            if "raw" in err:
                # Raw error text
                lines.append(f"{i}. {err['raw'][:500]}")
            else:
                # Structured error
                file = err.get("file", "unknown")
                line = err.get("line", "?")
                code = err.get("code", "")
                msg = err.get("message", "")
                lines.append(f"{i}. {file}:{line} - {code}: {msg}")

        if len(errors) > 20:
            lines.append(f"... und {len(errors) - 20} weitere Errors")

        return "\n".join(lines)

    def _build_task_prompt(
        self,
        task: str,
        task_type: str,
        context: Optional[Dict[str, Any]]
    ) -> str:
        """Erstellt den vollständigen Task-Prompt"""
        # Task-spezifischen Prompt holen
        if task_type in TASK_PROMPTS and context:
            try:
                specific_prompt = get_task_prompt(task_type, context)
                task = f"{task}\n\n{specific_prompt}"
            except KeyError:
                pass  # Fehlende Parameter ignorieren

        # Context hinzufügen
        if context:
            context_str = json.dumps(context, indent=2, ensure_ascii=False)
            task = f"{task}\n\nKontext:\n{context_str}"

        return task

    def _extract_messages(self, result) -> List[Dict[str, Any]]:
        """Extrahiert Messages aus dem Team-Ergebnis"""
        messages = []
        for msg in getattr(result, 'messages', []):
            # Extract content safely - may be string, list, or object
            content = getattr(msg, 'content', '')
            if content is None:
                content = ''
            elif isinstance(content, list):
                # Content might be a list of content blocks
                content = ' '.join(str(c) for c in content if c)
            elif not isinstance(content, str):
                content = str(content)

            message_dict = {
                "role": str(getattr(msg, 'role', 'unknown')),
                "content": content,
                "name": str(getattr(msg, 'name', None)) if getattr(msg, 'name', None) else None
            }
            messages.append(message_dict)

            # Event für jeden Schritt
            try:
                self.event_server.broadcast("agent.message", {
                    "role": message_dict["role"],
                    "name": message_dict["name"],
                    "content_preview": message_dict["content"][:200] if message_dict["content"] else "",
                    "timestamp": datetime.now().isoformat()
                })
            except Exception as e:
                logger.debug(f"Could not broadcast agent message: {e}")

        return messages

    def _extract_tool_calls(self, result) -> List[Dict[str, Any]]:
        """Extrahiert Tool Calls aus dem Team-Ergebnis"""
        tool_calls = []
        for msg in getattr(result, 'messages', []):
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tc in msg.tool_calls:
                    # Extract arguments safely - may be dict, string, or object
                    args = getattr(tc, 'arguments', {})
                    if hasattr(args, 'model_dump'):
                        # Pydantic model
                        args = args.model_dump()
                    elif hasattr(args, '__dict__'):
                        # Regular object
                        args = vars(args)
                    elif not isinstance(args, (dict, str, list, int, float, bool, type(None))):
                        # Convert unknown types to string
                        args = str(args)

                    tool_call = {
                        "tool": getattr(tc, 'name', 'unknown'),
                        "arguments": args,
                        "timestamp": datetime.now().isoformat()
                    }
                    tool_calls.append(tool_call)

                    # Event für jeden Tool Call
                    try:
                        self.event_server.broadcast("tool.called", tool_call)
                    except Exception as e:
                        logger.debug(f"Could not broadcast tool call: {e}")

        return tool_calls

    def get_status(self) -> Dict[str, Any]:
        """Gibt den Status des Orchestrators zurück"""
        # Tool-Filter Stats
        active_tools = 0
        if self.reasoning_agent and hasattr(self.reasoning_agent, '_tools'):
            active_tools = len(self.reasoning_agent._tools)

        return {
            "initialized": self._initialized,
            "model": self.model,
            "max_turns": self.max_turns,
            "working_dir": self.working_dir,
            "mcp_tools_loaded": len(self._mcp_tools),
            "mcp_tools_active": active_tools,
            "current_task_type": self._current_task_type,
            "tool_filter_max": self._tool_filter.max_tools,
            "autogen_mcp_available": AUTOGEN_MCP_AVAILABLE,
            "verification_stats": self._tool_verifier.get_stats(),
            # Iteration 2: Agent Selector
            "agent_selector_stats": self._agent_selector.get_stats(),
            # Iteration 3: Cache & Parallel
            "cache_stats": self._tool_cache.get_stats(),
            "parallel_executor_stats": self._parallel_executor.get_stats(),
            # Iteration 4: Error Recovery
            "circuit_breaker_health": self._circuit_breaker.get_health_summary(),
            # Iteration 5: Metrics & History
            "metrics": self._metrics.export_for_dashboard(),
            "history_summary": self._execution_history.get_summary(),
        }

    async def shutdown(self):
        """Fährt den Orchestrator herunter und gibt Ressourcen frei"""
        logger.info("Shutting down EventFixOrchestrator...")

        # MCP Workbench cleanup
        if AUTOGEN_MCP_AVAILABLE:
            try:
                workbench_manager = get_workbench_manager()
                await workbench_manager.shutdown()
                logger.info("MCP Workbench shutdown complete")
            except Exception as e:
                logger.warning(f"Error during MCP Workbench shutdown: {e}")

        # Reset state
        self._initialized = False
        self._mcp_tools = []
        self.reasoning_agent = None
        self.validator_agent = None
        self.team = None

        # Broadcast shutdown event
        self.event_server.broadcast("orchestrator.shutdown", {
            "timestamp": datetime.now().isoformat()
        })

        logger.info("EventFixOrchestrator shutdown complete")


# ============================================================================
# Convenience Functions
# ============================================================================

# Globale Orchestrator Instanz
_orchestrator: Optional[EventFixOrchestrator] = None


async def get_orchestrator(
    model: str = None,
    event_server: Optional[EventServer] = None,
    working_dir: str = "."
) -> EventFixOrchestrator:
    """
    Gibt die globale Orchestrator Instanz zurück (Singleton)

    Args:
        model: Model ID
        event_server: EventServer Instanz
        working_dir: Arbeitsverzeichnis für Dateioperationen

    Returns:
        EventFixOrchestrator Instanz
    """
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = EventFixOrchestrator(
            model=model or get_model("mcp_standard"),
            event_server=event_server,
            working_dir=working_dir
        )
        await _orchestrator.initialize()
    return _orchestrator


async def execute_task(
    task: str,
    task_type: str = "general",
    context: Optional[Dict[str, Any]] = None
) -> TaskResult:
    """
    Führt einen Task aus (Convenience Function)

    Args:
        task: Aufgabenbeschreibung
        task_type: Task-Typ
        context: Zusätzlicher Kontext

    Returns:
        TaskResult
    """
    orchestrator = await get_orchestrator()
    return await orchestrator.execute_task(task, task_type, context)


# ============================================================================
# Agent Runner (für standalone Ausführung)
# ============================================================================

async def run_orchestrator(config: OrchestratorConfig) -> TaskResult:
    """
    Führt den Orchestrator mit einer Konfiguration aus

    Args:
        config: OrchestratorConfig

    Returns:
        TaskResult
    """
    # EventServer starten
    event_server = EventServer()
    event_server.broadcast("session.started", {
        "session_id": config.session_id,
        "task": config.task,
        "timestamp": datetime.now().isoformat()
    })

    # Orchestrator erstellen und initialisieren
    orchestrator = EventFixOrchestrator(
        model=config.model,
        event_server=event_server,
        max_turns=config.max_turns,
        working_dir=config.working_dir
    )

    try:
        # Task ausführen
        result = await orchestrator.execute_task(
            task=config.task,
            task_type=config.task_type,
            context=config.parameters,
            task_id=config.session_id
        )

        event_server.broadcast("session.completed", {
            "session_id": config.session_id,
            "status": result.status,
            "timestamp": datetime.now().isoformat()
        })

        return result

    except Exception as e:
        event_server.broadcast("session.error", {
            "session_id": config.session_id,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        })
        raise


# ============================================================================
# gRPC Worker Integration
# ============================================================================

class WorkerRegistry:
    """
    Registry für gRPC Worker Konfigurationen.

    Lädt Worker-Ports aus servers.json und verwaltet Verbindungen.
    """

    def __init__(self, servers_json_path: Optional[str] = None):
        if servers_json_path:
            self.servers_json_path = Path(servers_json_path)
        else:
            self.servers_json_path = Path(__file__).parent.parent / "servers.json"

        self._workers: Dict[str, Dict[str, Any]] = {}
        self._clients: Dict[str, Any] = {}
        self._load_workers()

    def _load_workers(self):
        """Lädt Worker-Konfigurationen aus servers.json"""
        if not self.servers_json_path.exists():
            logger.warning(f"servers.json nicht gefunden: {self.servers_json_path}")
            return

        try:
            with open(self.servers_json_path, "r", encoding="utf-8") as f:
                config = json.load(f)

            for server in config.get("servers", []):
                if server.get("active") and server.get("grpc_port"):
                    name = server["name"]
                    self._workers[name] = {
                        "name": name,
                        "port": server["grpc_port"],
                        "type": server.get("type", "stdio"),
                        "description": server.get("description", "")
                    }

            logger.info(f"Loaded {len(self._workers)} gRPC worker configurations")

        except Exception as e:
            logger.error(f"Fehler beim Laden der Worker-Konfiguration: {e}")

    def get_worker(self, name: str) -> Optional[Dict[str, Any]]:
        """Gibt Worker-Konfiguration zurück"""
        return self._workers.get(name)

    def list_workers(self) -> List[Dict[str, Any]]:
        """Gibt alle Worker zurück"""
        return list(self._workers.values())

    async def get_client(self, name: str):
        """Gibt einen Client für einen Worker zurück (lazy initialization)"""
        if name not in self._workers:
            raise ValueError(f"Worker '{name}' nicht konfiguriert")

        if name not in self._clients:
            # Import AgentWorkerClient from shared
            try:
                sys.path.insert(0, str(Path(__file__).parent.parent / "shared"))
                from grpc_adapter import AgentWorkerClient

                worker = self._workers[name]
                client = AgentWorkerClient("localhost", worker["port"])
                await client.connect()
                self._clients[name] = client
            except Exception as e:
                logger.error(f"Konnte Client für '{name}' nicht erstellen: {e}")
                raise

        return self._clients[name]

    async def close_all(self):
        """Schließt alle Client-Verbindungen"""
        for name, client in self._clients.items():
            try:
                await client.close()
            except Exception as e:
                logger.warning(f"Fehler beim Schließen von Client '{name}': {e}")
        self._clients.clear()


# Globale Worker Registry
_worker_registry: Optional[WorkerRegistry] = None


def get_worker_registry() -> WorkerRegistry:
    """Gibt die globale Worker Registry zurück"""
    global _worker_registry
    if _worker_registry is None:
        _worker_registry = WorkerRegistry()
    return _worker_registry


async def call_grpc_worker(
    worker_name: str,
    task: str,
    task_type: str = "",
    parameters: Optional[Dict[str, Any]] = None,
    timeout_seconds: int = 0
) -> Dict[str, Any]:
    """
    Ruft einen gRPC Worker auf.

    Args:
        worker_name: Name des Workers (z.B. "filesystem", "docker")
        task: Task-Beschreibung
        task_type: Optionaler Task-Typ
        parameters: Optionale Parameter
        timeout_seconds: Timeout (0 = default)

    Returns:
        Worker-Ergebnis als Dict

    Raises:
        ValueError: Wenn Worker nicht gefunden
        ConnectionError: Bei Verbindungsproblemen
    """
    registry = get_worker_registry()

    try:
        client = await registry.get_client(worker_name)
        result = await client.execute_task(
            description=task,
            task_type=task_type,
            parameters=parameters,
            timeout_seconds=timeout_seconds
        )
        return result
    except Exception as e:
        logger.error(f"Fehler beim Aufruf von Worker '{worker_name}': {e}")
        return {
            "status": 3,  # FAILED
            "message": str(e),
            "error": True
        }


# ============================================================================
# Test
# ============================================================================

async def test_orchestrator():
    """Test-Funktion für den Orchestrator"""
    print("=== EventFix Orchestrator Test ===\n")

    # Orchestrator erstellen
    orchestrator = EventFixOrchestrator(model=get_model("mcp_standard"))

    print("Status vor Initialisierung:")
    print(json.dumps(orchestrator.get_status(), indent=2))

    print("\nInitialisiere...")
    await orchestrator.initialize()

    print("\nStatus nach Initialisierung:")
    print(json.dumps(orchestrator.get_status(), indent=2))

    # Test-Task
    print("\n=== Test Task ===")
    result = await orchestrator.execute_task(
        task="Was ist 2 + 2? Antworte kurz.",
        task_type="general"
    )

    print(f"\nStatus: {result.status}")
    print(f"Steps: {result.steps}")
    print(f"Tool Calls: {len(result.tool_calls)}")
    print(f"Duration: {result.duration_ms}ms")
    print(f"\nResult:\n{result.result}")

    # Worker Registry Test
    print("\n=== Worker Registry Test ===")
    registry = get_worker_registry()
    workers = registry.list_workers()
    print(f"Konfigurierte Workers: {len(workers)}")
    for w in workers[:5]:
        print(f"  - {w['name']}: port {w['port']}")


if __name__ == "__main__":
    import asyncio

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    asyncio.run(test_orchestrator())
