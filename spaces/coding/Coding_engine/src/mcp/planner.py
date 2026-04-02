# -*- coding: utf-8 -*-
"""
MCP Planner - LLM-based planning for MCP tool sequences.

This module uses an LLM to analyze tasks and generate execution plans
consisting of tool call sequences.
"""
import os
import json
import re
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
import structlog

from src.llm_config import get_model

logger = structlog.get_logger()


@dataclass
class PlanStep:
    """A single step in an execution plan."""
    tool: str
    args: Dict[str, Any]
    reason: str
    depends_on: List[int] = field(default_factory=list)


@dataclass
class Plan:
    """Execution plan with ordered tool steps."""
    task: str
    steps: List[PlanStep]
    expected_outcome: str
    context: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def parse(cls, response: str, task: str) -> "Plan":
        """
        Parse LLM response into a Plan object.

        Args:
            response: LLM response string (should contain JSON)
            task: Original task description

        Returns:
            Plan object
        """
        # Try to extract JSON from response
        json_match = re.search(r'\{[\s\S]*\}', response)
        if not json_match:
            logger.warning("plan_no_json_found", response_preview=response[:200])
            return cls(
                task=task,
                steps=[],
                expected_outcome="Could not parse plan"
            )

        try:
            data = json.loads(json_match.group())

            steps = []
            for step_data in data.get("steps", []):
                steps.append(PlanStep(
                    tool=step_data.get("tool", ""),
                    args=step_data.get("args", {}),
                    reason=step_data.get("reason", ""),
                    depends_on=step_data.get("depends_on", [])
                ))

            return cls(
                task=task,
                steps=steps,
                expected_outcome=data.get("expected_outcome", "")
            )

        except json.JSONDecodeError as e:
            logger.warning("plan_json_parse_error", error=str(e))
            return cls(
                task=task,
                steps=[],
                expected_outcome=f"JSON parse error: {e}"
            )


class MCPPlanner:
    """
    LLM-based planner for MCP tool sequences.

    Analyzes tasks and generates execution plans using available tools.

    Usage:
        planner = MCPPlanner(tool_registry)
        plan = await planner.create_plan(
            task="Deploy the application with PostgreSQL",
            context={"output_dir": "./my-app"}
        )

        # Plan recovery after failure
        recovery = await planner.plan_recovery(
            failed_step=plan.steps[2],
            error="Container failed to start"
        )
    """

    SYSTEM_PROMPT = '''Du bist ein erfahrener DevOps-Experte der Tool-Sequenzen plant.

VERFÜGBARE TOOLS:
{tools}

AUFGABE:
Analysiere den gegebenen Task und erstelle einen JSON-Plan mit den nötigen Tool-Aufrufen.

REGELN:
1. Verwende NUR Tools aus der Liste oben
2. Gib Tool-Namen exakt an (z.B. "docker.list_containers")
3. Gib alle nötigen Args an
4. Erkläre kurz warum jeder Schritt nötig ist
5. Denke an Abhängigkeiten zwischen Schritten

OUTPUT FORMAT (JSON):
{{
  "steps": [
    {{"tool": "category.tool_name", "args": {{"key": "value"}}, "reason": "Kurze Erklärung"}},
    ...
  ],
  "expected_outcome": "Was nach Ausführung erreicht sein sollte"
}}

BEISPIEL für "Start PostgreSQL für Entwicklung":
{{
  "steps": [
    {{"tool": "docker.pull_image", "args": {{"image": "postgres:15"}}, "reason": "PostgreSQL Image laden"}},
    {{"tool": "docker.run_container", "args": {{"image": "postgres:15", "name": "dev-postgres", "ports": "5432:5432", "env": "POSTGRES_PASSWORD=dev123"}}, "reason": "PostgreSQL Container starten"}}
  ],
  "expected_outcome": "PostgreSQL läuft auf Port 5432 mit Passwort dev123"
}}

Antworte NUR mit dem JSON-Plan, keine zusätzlichen Erklärungen.'''

    RECOVERY_PROMPT = '''Ein Schritt in der Ausführung ist fehlgeschlagen.

FEHLGESCHLAGENER SCHRITT:
Tool: {tool}
Args: {args}
Fehler: {error}

KONTEXT:
{context}

VERFÜGBARE TOOLS:
{tools}

Erstelle einen Recovery-Plan um das Problem zu beheben und den ursprünglichen Schritt erneut zu versuchen.

OUTPUT FORMAT (JSON):
{{
  "steps": [
    {{"tool": "...", "args": {{...}}, "reason": "Recovery-Schritt"}}
  ],
  "expected_outcome": "Zustand nach Recovery"
}}'''

    def __init__(self, tool_registry, model: str = None):
        """
        Initialize the planner.

        Args:
            tool_registry: MCPToolRegistry instance
            model: Model to use (defaults to env or Haiku 4.5)
        """
        self.tool_registry = tool_registry
        self.model = model or os.getenv("MCP_PLANNER_MODEL") or get_model("judge")
        self._llm_client = None
        self._use_openai_format = False  # Set by _get_llm_client()

    def _get_llm_client(self):
        """Get or create LLM client."""
        if self._llm_client is None:
            # Check for OpenRouter first (uses OpenAI-compatible API)
            openrouter_key = os.getenv("OPENROUTER_API_KEY")
            if openrouter_key:
                try:
                    from openai import OpenAI
                    self._llm_client = OpenAI(
                        api_key=openrouter_key,
                        base_url="https://openrouter.ai/api/v1"
                    )
                    self._use_openai_format = True
                    logger.debug("planner_using_openrouter")
                except ImportError:
                    logger.warning("openai_sdk_not_installed")
            else:
                # Fallback to Anthropic SDK
                try:
                    from anthropic import Anthropic
                    api_key = os.getenv("ANTHROPIC_API_KEY")
                    if api_key:
                        self._llm_client = Anthropic(api_key=api_key)
                        self._use_openai_format = False
                        logger.debug("planner_using_anthropic")
                except ImportError:
                    logger.warning("anthropic_not_installed")
                    self._llm_client = None
        return self._llm_client

    def _format_tools_for_prompt(self) -> str:
        """Format tool list for LLM prompt."""
        tools = self.tool_registry.list_tools()
        lines = []
        current_category = ""

        for tool in sorted(tools, key=lambda t: t["category"]):
            if tool["category"] != current_category:
                current_category = tool["category"]
                lines.append(f"\n[{current_category.upper()}]")

            lines.append(f"  - {tool['name']}: {tool['description']}")

        return "\n".join(lines)

    async def create_plan(self, task: str, context: Dict[str, Any] = None) -> Plan:
        """
        Create an execution plan for a task.

        Args:
            task: Natural language task description
            context: Additional context (output_dir, project info, etc.)

        Returns:
            Plan with tool steps
        """
        context = context or {}
        tools_desc = self._format_tools_for_prompt()

        prompt = f"Task: {task}"
        if context:
            prompt += f"\nKontext: {json.dumps(context, indent=2)}"

        logger.info("planner_creating_plan", task=task[:50])

        # Try LLM first
        client = self._get_llm_client()
        if client:
            try:
                if self._use_openai_format:
                    # OpenRouter uses OpenAI-compatible API
                    response = client.chat.completions.create(
                        model=self.model,  # Full model name for OpenRouter
                        max_tokens=2000,
                        messages=[
                            {"role": "system", "content": self.SYSTEM_PROMPT.format(tools=tools_desc)},
                            {"role": "user", "content": prompt}
                        ]
                    )
                    response_text = response.choices[0].message.content
                else:
                    # Anthropic native API
                    response = client.messages.create(
                        model=self.model.split("/")[-1] if "/" in self.model else self.model,
                        max_tokens=2000,
                        system=self.SYSTEM_PROMPT.format(tools=tools_desc),
                        messages=[{"role": "user", "content": prompt}]
                    )
                    response_text = response.content[0].text

                plan = Plan.parse(response_text, task)
                plan.context = context

                logger.info("planner_plan_created",
                           task=task[:50],
                           steps_count=len(plan.steps))

                return plan

            except Exception as e:
                logger.warning("planner_llm_error", error=str(e)[:200])

        # Fallback: Simple rule-based planning
        return self._create_fallback_plan(task, context)

    def _create_fallback_plan(self, task: str, context: Dict[str, Any]) -> Plan:
        """Create a simple rule-based plan when LLM is unavailable."""
        task_lower = task.lower()
        steps = []

        # Docker-related tasks
        if "docker" in task_lower or "container" in task_lower:
            if "postgres" in task_lower or "postgresql" in task_lower:
                steps = [
                    PlanStep("docker.pull_image", {"image": "postgres:15"}, "Pull PostgreSQL image"),
                    PlanStep("docker.run_container", {
                        "image": "postgres:15",
                        "name": "dev-postgres",
                        "ports": "5432:5432",
                        "env": "POSTGRES_PASSWORD=dev123"
                    }, "Start PostgreSQL container"),
                ]
            elif "redis" in task_lower:
                steps = [
                    PlanStep("docker.pull_image", {"image": "redis:7"}, "Pull Redis image"),
                    PlanStep("docker.run_container", {
                        "image": "redis:7",
                        "name": "dev-redis",
                        "ports": "6379:6379"
                    }, "Start Redis container"),
                ]
            elif "list" in task_lower:
                steps = [PlanStep("docker.list_containers", {"all": True}, "List all containers")]
            elif "stop" in task_lower:
                steps = [PlanStep("docker.docker_compose_down", {}, "Stop Compose services")]
            else:
                steps = [PlanStep("docker.docker_info", {}, "Get Docker system info")]

        # Git tasks
        elif "git" in task_lower or "commit" in task_lower:
            if "commit" in task_lower:
                steps = [
                    PlanStep("git.status", {}, "Check current status"),
                    PlanStep("git.add", {"files": "."}, "Stage changes"),
                    PlanStep("git.commit", {"message": context.get("message", "Update")}, "Commit changes"),
                ]
            else:
                steps = [PlanStep("git.status", {}, "Get git status")]

        # NPM tasks
        elif "npm" in task_lower or "build" in task_lower or "test" in task_lower:
            if "install" in task_lower:
                steps = [PlanStep("npm.install", {}, "Install dependencies")]
            elif "build" in task_lower:
                steps = [PlanStep("npm.run", {"script": "build"}, "Run build")]
            elif "test" in task_lower:
                steps = [PlanStep("npm.run", {"script": "test"}, "Run tests")]
            else:
                steps = [PlanStep("npm.version", {}, "Get npm version")]

        # Default: check system status
        else:
            steps = [
                PlanStep("git.status", {}, "Check git status"),
                PlanStep("docker.docker_info", {}, "Check Docker status"),
            ]

        return Plan(
            task=task,
            steps=steps,
            expected_outcome="Task completed via fallback rules",
            context=context
        )

    async def plan_recovery(self, failed_step: PlanStep, error: str,
                           context: Dict[str, Any] = None) -> Plan:
        """
        Create a recovery plan after a step failure.

        Args:
            failed_step: The step that failed
            error: Error message
            context: Execution context

        Returns:
            Recovery plan
        """
        context = context or {}
        tools_desc = self._format_tools_for_prompt()

        logger.info("planner_recovery",
                   failed_tool=failed_step.tool,
                   error=error[:100])

        client = self._get_llm_client()
        if client:
            try:
                prompt = self.RECOVERY_PROMPT.format(
                    tool=failed_step.tool,
                    args=json.dumps(failed_step.args),
                    error=error,
                    context=json.dumps(context),
                    tools=tools_desc
                )

                if self._use_openai_format:
                    # OpenRouter uses OpenAI-compatible API
                    response = client.chat.completions.create(
                        model=self.model,
                        max_tokens=1000,
                        messages=[{"role": "user", "content": prompt}]
                    )
                    response_text = response.choices[0].message.content
                else:
                    # Anthropic native API
                    response = client.messages.create(
                        model=self.model.split("/")[-1] if "/" in self.model else self.model,
                        max_tokens=1000,
                        messages=[{"role": "user", "content": prompt}]
                    )
                    response_text = response.content[0].text

                recovery_plan = Plan.parse(response_text, f"Recovery: {failed_step.tool}")

                logger.info("planner_recovery_created", steps=len(recovery_plan.steps))
                return recovery_plan

            except Exception as e:
                logger.warning("planner_recovery_error", error=str(e)[:200])

        # Fallback recovery strategies
        return self._create_fallback_recovery(failed_step, error)

    def _create_fallback_recovery(self, failed_step: PlanStep, error: str) -> Plan:
        """Create simple recovery plan."""
        steps = []
        tool = failed_step.tool

        if "docker" in tool:
            if "not found" in error.lower() or "no such" in error.lower():
                # Container/image not found - try to pull or list
                if "container" in tool:
                    steps = [PlanStep("docker.list_containers", {"all": True}, "List available containers")]
                else:
                    image = failed_step.args.get("image", "")
                    if image:
                        steps = [PlanStep("docker.pull_image", {"image": image}, "Pull missing image")]
            elif "already" in error.lower():
                # Already exists - remove and retry
                name = failed_step.args.get("name", "")
                if name:
                    steps = [
                        PlanStep("docker.remove_container", {"container_id": name, "force": True}, "Remove existing"),
                    ]

        return Plan(
            task=f"Recovery for {tool}",
            steps=steps,
            expected_outcome="Recovery attempted"
        )


if __name__ == "__main__":
    import asyncio
    from tool_registry import MCPToolRegistry

    async def test_planner():
        print("Testing MCPPlanner...")

        registry = MCPToolRegistry()
        planner = MCPPlanner(registry)

        # Test plan creation (will use fallback if no API key)
        plan = await planner.create_plan(
            task="Start PostgreSQL und Redis für Entwicklung",
            context={"project": "test-app"}
        )

        print(f"\nPlan for: {plan.task}")
        print(f"Expected: {plan.expected_outcome}")
        print(f"Steps ({len(plan.steps)}):")
        for i, step in enumerate(plan.steps):
            print(f"  {i+1}. {step.tool}")
            print(f"     Args: {step.args}")
            print(f"     Reason: {step.reason}")

    asyncio.run(test_planner())
