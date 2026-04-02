"""
AI Contract Generator - Generates interface contracts using Claude API.

Unlike the heuristic-based ContractGenerator, this module uses Claude's
semantic understanding to generate domain-specific TypeScript interfaces
from requirement descriptions.

Benefits over heuristic approach:
1. Domain-specific types (e.g., Geofence, Vehicle, Route) instead of generic Config/Result
2. Better field inference from requirement text
3. Relationship detection between types
4. API endpoint inference with proper request/response types
"""

import json
import re
from typing import Optional
import structlog

from src.engine.contracts import (
    InterfaceContracts,
    TypeDefinition,
    APIEndpoint,
    ComponentContract,
    ServiceContract,
)
from src.engine.dag_parser import RequirementsData

logger = structlog.get_logger()


class AIContractGenerator:
    """
    Generates interface contracts using Claude API for semantic understanding.

    This generator analyzes requirement descriptions to create domain-specific
    TypeScript interfaces, replacing the heuristic-based approach.
    """

    def __init__(self, api_key: Optional[str] = None, working_dir: Optional[str] = None):
        """
        Initialize the AI contract generator.

        Args:
            api_key: Anthropic API key (kept for backwards compatibility, not used with ClaudeCodeTool)
            working_dir: Working directory for Claude CLI (avoids CLAUDE.md context interference)
        """
        self.logger = logger.bind(component="ai_contract_generator")
        self.api_key = api_key  # Kept for backwards compatibility
        self.working_dir = working_dir  # Use output dir to avoid CLAUDE.md interference
        self._tool = None  # ClaudeCodeTool instance (respects LLM_BACKEND setting)

    def _get_tool(self):
        """
        Get ClaudeCodeTool which respects LLM_BACKEND setting.

        This replaces direct Anthropic API usage to support OpenRouter/Kilo backend.
        NOTE: load_context=False because contract generation doesn't need fungus indexing
        """
        if self._tool is None:
            from src.tools.claude_code_tool import ClaudeCodeTool
            # Use working_dir from constructor to avoid CLAUDE.md context interference
            # Contract generation doesn't need fungus indexing
            self._tool = ClaudeCodeTool(
                working_dir=self.working_dir or ".",
                load_context=False,  # No fungus indexing needed for contract generation
            )
        return self._tool

    async def generate(
        self,
        requirements: list[dict],
        project_name: str = "Generated Project",
        domain_hint: Optional[str] = None,
    ) -> InterfaceContracts:
        """
        Generate interface contracts from requirements using Claude API.

        Args:
            requirements: List of requirement dicts with id, name, description
            project_name: Name of the project
            domain_hint: Optional hint about the domain (e.g., "e-commerce", "transport")

        Returns:
            InterfaceContracts with domain-specific types and interfaces
        """
        self.logger.info(
            "generating_ai_contracts",
            requirements=len(requirements),
            project_name=project_name,
            domain_hint=domain_hint,
        )

        # Build requirement text for Claude
        req_text = self._format_requirements(requirements)

        # Add domain context if provided
        domain_context = ""
        if domain_hint:
            domain_context = f"\n\nDomain Context: This is a {domain_hint} application."

        # Create the prompt
        prompt = f"""Analyze these software requirements and generate TypeScript interfaces:

## Requirements
{req_text}
{domain_context}

## CRITICAL: API Endpoint Generation

For EVERY data entity/type you identify, you MUST create API endpoints:
- If requirements mention displaying/listing data → create GET /api/v1/{{resource}}s
- If requirements mention creating/submitting → create POST /api/v1/{{resource}}s
- If requirements mention updating/modifying → create PUT /api/v1/{{resource}}s/{{id}}
- If requirements mention searching/filtering → create GET /api/v1/{{resource}}s?query=value
- If requirements mention deleting → create DELETE /api/v1/{{resource}}s/{{id}}

Standard REST pattern for each entity:
- GET    /api/v1/{{resource}}s         - List all
- GET    /api/v1/{{resource}}s/{{id}}    - Get one by ID
- POST   /api/v1/{{resource}}s         - Create new
- PUT    /api/v1/{{resource}}s/{{id}}    - Update existing
- DELETE /api/v1/{{resource}}s/{{id}}    - Delete

IMPORTANT: If you generate types but 0 endpoints, that's WRONG.
Every data type needs at least GET endpoints to retrieve it.

Generate domain-specific types, API endpoints, components, and services based on these requirements.
Remember: Create specific types like Vehicle, Route, Geofence - NOT generic Config/Result types."""

        try:
            # Call Claude API
            response = await self._call_claude(prompt)

            # Parse response
            contracts = self._parse_response(response, project_name)

            self.logger.info(
                "ai_contracts_generated",
                types=len(contracts.types),
                endpoints=len(contracts.endpoints),
                components=len(contracts.components),
                services=len(contracts.services),
            )

            return contracts

        except Exception as e:
            self.logger.error("ai_contract_generation_failed", error=str(e))
            # Return empty contracts on failure (caller should use fallback)
            return InterfaceContracts(project_name=project_name)

    def _format_requirements(self, requirements: list[dict]) -> str:
        """Format requirements for the prompt."""
        lines = []
        for req in requirements:
            req_id = req.get("id") or req.get("req_id", "REQ")
            name = req.get("name") or req.get("title", "Untitled")
            description = req.get("description", "")
            priority = req.get("priority", "medium")

            # Include full description, not just ID
            if description:
                lines.append(f"- [{req_id}] {name}: {description} (priority: {priority})")
            else:
                lines.append(f"- [{req_id}] {name} (priority: {priority})")

        return "\n".join(lines)

    async def _call_claude(self, prompt: str) -> str:
        """
        Call LLM via ClaudeCodeTool (respects LLM_BACKEND setting).

        This replaces direct Anthropic API usage to support:
        - LLM_BACKEND=claude → Anthropic API (via Claude Code CLI)
        - LLM_BACKEND=kilo → OpenRouter/Kilo API

        The skill 'api-contract-design' is loaded automatically by ClaudeCodeTool
        based on agent_type="architect" (see AGENT_SKILL_MAP).
        """
        tool = self._get_tool()

        # Use architect agent type - skill is loaded automatically
        result = await tool.execute(
            prompt=prompt,
            agent_type="architect",
        )

        if result.success and result.output:
            return result.output
        elif result.files:
            # Claude CLI wrote JSON to file - read it back
            # Prioritize architect-*.json files (these have the richest contracts)
            for f in result.files:
                if hasattr(f, 'path') and f.path and 'architect' in f.path and f.path.endswith('.json'):
                    self.logger.info("reading_contract_from_file", file=f.path)
                    if hasattr(f, 'content') and f.content:
                        return f.content
            # Fallback to first JSON file
            for f in result.files:
                if hasattr(f, 'path') and f.path and f.path.endswith('.json'):
                    self.logger.info("reading_contract_from_file_fallback", file=f.path)
                    if hasattr(f, 'content') and f.content:
                        return f.content
            # Last resort: any file with content
            if result.files and hasattr(result.files[0], 'content'):
                return result.files[0].content or ""
            return ""
        else:
            # Before failing, check if architect files exist on disk
            disk_contracts = self._try_load_from_disk()
            if disk_contracts:
                return disk_contracts
            raise ValueError(f"Contract generation failed: {result.error or 'No output'}")

    def _try_load_from_disk(self) -> str | None:
        """
        Try to load contracts from existing architect_*.json files on disk.

        Claude CLI sometimes writes files to disk but doesn't include them
        in the result.files list. This fallback reads the most recent file.
        """
        import os
        from pathlib import Path

        work_dir = Path(self.working_dir) if self.working_dir else Path(".")

        # Find architect_*.json files
        architect_files = list(work_dir.glob("architect_*.json"))
        if not architect_files:
            return None

        # Sort by modification time, newest first
        architect_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

        newest = architect_files[0]
        self.logger.info("loading_contracts_from_disk", file=str(newest))

        try:
            content = newest.read_text(encoding='utf-8')
            # Validate it's valid JSON with types or endpoints
            data = json.loads(content)
            if data.get("types") or data.get("endpoints"):
                return content
        except (json.JSONDecodeError, OSError) as e:
            self.logger.warning("disk_contract_load_failed", file=str(newest), error=str(e))

        return None

    def _parse_response(self, response: str, project_name: str) -> InterfaceContracts:
        """Parse Claude's JSON response into InterfaceContracts."""
        contracts = InterfaceContracts(project_name=project_name)

        try:
            # Extract JSON from response (handle potential markdown wrapping)
            json_str = response.strip()
            if json_str.startswith("```"):
                # Remove markdown code block
                json_str = re.sub(r"^```(?:json)?\n?", "", json_str)
                json_str = re.sub(r"\n?```$", "", json_str)

            data = json.loads(json_str)

            # Parse types
            for type_data in data.get("types", []):
                try:
                    type_def = TypeDefinition(
                        name=type_data.get("name", "UnknownType"),
                        fields=type_data.get("fields", {}),
                        description=type_data.get("description", ""),
                        optional_fields=type_data.get("optional_fields", []),
                    )
                    contracts.add_type(type_def)
                except Exception as e:
                    self.logger.warning("type_parse_failed", error=str(e), data=type_data)

            # Parse endpoints
            for ep_data in data.get("endpoints", []):
                try:
                    endpoint = APIEndpoint(
                        path=ep_data.get("path", "/api/unknown"),
                        method=ep_data.get("method", "GET"),
                        request_type=ep_data.get("request_type"),
                        response_type=ep_data.get("response_type"),
                        description=ep_data.get("description", ""),
                        auth_required=ep_data.get("auth_required", True),
                        tags=ep_data.get("tags", []),
                    )
                    contracts.add_endpoint(endpoint)
                except Exception as e:
                    self.logger.warning("endpoint_parse_failed", error=str(e), data=ep_data)

            # Parse components
            for comp_data in data.get("components", []):
                try:
                    component = ComponentContract(
                        name=comp_data.get("name", "UnknownComponent"),
                        props=comp_data.get("props", {}),
                        description=comp_data.get("description", ""),
                        children=comp_data.get("children", False),
                        events=comp_data.get("events", []),
                    )
                    contracts.add_component(component)
                except Exception as e:
                    self.logger.warning("component_parse_failed", error=str(e), data=comp_data)

            # Parse services
            for svc_data in data.get("services", []):
                try:
                    service = ServiceContract(
                        name=svc_data.get("name", "UnknownService"),
                        methods=svc_data.get("methods", {}),
                        description=svc_data.get("description", ""),
                    )
                    contracts.add_service(service)
                except Exception as e:
                    self.logger.warning("service_parse_failed", error=str(e), data=svc_data)

        except json.JSONDecodeError as e:
            self.logger.error("json_parse_failed", error=str(e), response_preview=response[:500])
        except Exception as e:
            self.logger.error("response_parse_failed", error=str(e))

        return contracts

    def generate_sync(
        self,
        requirements: list[dict],
        project_name: str = "Generated Project",
        domain_hint: Optional[str] = None,
    ) -> InterfaceContracts:
        """
        Synchronous wrapper for generate().

        Args:
            requirements: List of requirement dicts with id, name, description
            project_name: Name of the project
            domain_hint: Optional hint about the domain

        Returns:
            InterfaceContracts with domain-specific types and interfaces
        """
        import asyncio

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(
            self.generate(requirements, project_name, domain_hint)
        )


class HybridContractGenerator:
    """
    Hybrid contract generator that uses AI when available, with heuristic fallback.

    This provides a safe migration path from heuristic to AI-based generation.
    """

    def __init__(self, api_key: Optional[str] = None, prefer_ai: bool = True, working_dir: Optional[str] = None):
        """
        Initialize the hybrid generator.

        Args:
            api_key: Anthropic API key
            prefer_ai: Whether to prefer AI generation (True) or heuristics (False)
            working_dir: Working directory for Claude CLI (avoids CLAUDE.md context interference)
        """
        self.logger = logger.bind(component="hybrid_contract_generator")
        self.prefer_ai = prefer_ai
        self.working_dir = working_dir
        self.ai_generator = AIContractGenerator(api_key, working_dir=working_dir) if prefer_ai else None
        self._heuristic_generator = None

    def _get_heuristic_generator(self):
        """Lazy-load the heuristic generator."""
        if self._heuristic_generator is None:
            from src.engine.contract_generator import ContractGenerator
            self._heuristic_generator = ContractGenerator(working_dir=self.working_dir)
        return self._heuristic_generator

    async def generate(
        self,
        req_data: RequirementsData,
        project_name: str = "Generated Project",
        domain_hint: Optional[str] = None,
    ) -> InterfaceContracts:
        """
        Generate contracts using AI with heuristic fallback.

        Args:
            req_data: Parsed requirements data
            project_name: Name of the project
            domain_hint: Optional domain hint

        Returns:
            InterfaceContracts from AI or heuristic generator
        """
        if self.prefer_ai and self.ai_generator:
            try:
                # Extract requirements with full descriptions
                requirements = [
                    {
                        "id": req.get("id") or req.get("req_id"),
                        "name": req.get("name") or req.get("title"),
                        "description": req.get("description", ""),
                        "priority": req.get("priority", "medium"),
                    }
                    for req in req_data.requirements
                ]

                contracts = await self.ai_generator.generate(
                    requirements=requirements,
                    project_name=project_name,
                    domain_hint=domain_hint,
                )

                # Check if we got meaningful results
                if contracts.types or contracts.endpoints or contracts.components:
                    self.logger.info("using_ai_contracts")
                    return contracts
                else:
                    self.logger.warning("ai_contracts_empty_trying_disk_fallback")
                    # Try loading from existing architect_*.json files on disk
                    disk_contracts = self._try_load_from_architect_files(project_name)
                    if disk_contracts and (disk_contracts.types or disk_contracts.endpoints):
                        self.logger.info("using_disk_contracts", types=len(disk_contracts.types))
                        return disk_contracts

            except Exception as e:
                self.logger.warning("ai_generation_failed_falling_back", error=str(e))
                # Try loading from existing architect_*.json files on disk
                disk_contracts = self._try_load_from_architect_files(project_name)
                if disk_contracts and (disk_contracts.types or disk_contracts.endpoints):
                    self.logger.info("using_disk_contracts_after_error", types=len(disk_contracts.types))
                    return disk_contracts

        # Fallback to heuristic generator
        self.logger.info("using_heuristic_contracts")
        heuristic = self._get_heuristic_generator()
        return heuristic.generate(req_data, project_name)

    def _try_load_from_architect_files(self, project_name: str) -> InterfaceContracts | None:
        """
        Try to load contracts from existing architect_*.json files.

        This fallback handles the case where Claude CLI wrote files to disk
        but the result wasn't properly returned to the generator.
        """
        from pathlib import Path

        work_dir = Path(self.working_dir) if self.working_dir else Path(".")

        # Find architect_*.json files
        architect_files = list(work_dir.glob("architect_*.json"))
        if not architect_files:
            return None

        # Sort by modification time, newest first
        architect_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

        for architect_file in architect_files:
            try:
                content = architect_file.read_text(encoding='utf-8')
                data = json.loads(content)

                # Check if this file has meaningful contracts
                if not (data.get("types") or data.get("endpoints")):
                    continue

                self.logger.info("loading_from_architect_file",
                    file=str(architect_file),
                    types=len(data.get("types", [])),
                    endpoints=len(data.get("endpoints", [])))

                # Parse into InterfaceContracts using AIContractGenerator's parser
                if self.ai_generator:
                    return self.ai_generator._parse_response(content, project_name)

            except (json.JSONDecodeError, OSError) as e:
                self.logger.warning("architect_file_load_failed",
                    file=str(architect_file), error=str(e))
                continue

        return None
