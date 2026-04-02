"""
ContinuousArchitectAgent - Event-driven architect that refines contracts based on verification feedback.

This agent is part of the Continuous Feedback Loop architecture:
1. Subscribes to VERIFICATION_FAILED, FULLSTACK_INCOMPLETE, E2E_TEST_FAILED events
2. Refines contracts based on failure feedback
3. Publishes CONTRACTS_UPDATED event to trigger regeneration
4. Works alongside the original ArchitectAgent (which handles Phase 1 initial contracts)

The feedback loop:
  FullstackVerifierAgent → FULLSTACK_INCOMPLETE → ContinuousArchitectAgent → CONTRACTS_UPDATED → Regeneration
"""

import asyncio
import json
from pathlib import Path
from typing import Any, Optional, Dict, List
import structlog

from .autonomous_base import AutonomousAgent
from .architect_agent import ArchitectAgent
from ..mind.event_bus import EventBus, Event, EventType
from ..mind.shared_state import SharedState
from ..engine.contracts import InterfaceContracts
from ..tools.claude_code_tool import ClaudeCodeTool

logger = structlog.get_logger(__name__)


class ContinuousArchitectAgent(AutonomousAgent):
    """
    Continuous Architect Agent that refines contracts based on verification feedback.

    This agent extends the standard ArchitectAgent functionality with event-driven
    continuous refinement. It subscribes to verification failure events and uses
    Claude to analyze what went wrong and how to update the contracts.

    Subscribed Events:
        - VERIFICATION_FAILED: General verification failure
        - FULLSTACK_INCOMPLETE: Missing fullstack components
        - E2E_TEST_FAILED: End-to-end test failures
        - CONTRACTS_REFINEMENT_NEEDED: Explicit refinement request

    Published Events:
        - CONTRACTS_UPDATED: Contracts have been refined
        - CONTRACTS_REFINEMENT_STARTED: Refinement process started
    """

    @property
    def subscribed_events(self) -> list[EventType]:
        """Events that trigger contract refinement."""
        return [
            EventType.VERIFICATION_FAILED,
            EventType.FULLSTACK_INCOMPLETE,
            EventType.E2E_TEST_FAILED,
            EventType.CONTRACTS_REFINEMENT_NEEDED,
        ]

    def __init__(
        self,
        name: str,
        event_bus: EventBus,
        shared_state: SharedState,
        working_dir: str,
        max_refinements: int = 5,  # Prevent infinite refinement loops
        **kwargs,
    ):
        super().__init__(
            name=name,
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=working_dir,
            **kwargs,
        )
        self.max_refinements = max_refinements
        self._refinement_count = 0
        self._current_contracts: Optional[InterfaceContracts] = None
        self._contracts_path = Path(working_dir) / ".contracts_cache.json"

        # Initialize tools
        self.claude_tool = ClaudeCodeTool(working_dir=working_dir)
        self.logger = logger.bind(agent=name)

    async def should_act(self, events: list[Event]) -> bool:
        """
        Act on verification failure events.

        We refine contracts when we receive failure feedback, but only if we haven't
        exceeded the maximum refinement count (to prevent infinite loops).
        """
        if not events:
            return False

        # Check if we've exceeded refinement limit
        if self._refinement_count >= self.max_refinements:
            self.logger.warning(
                "max_refinements_reached",
                count=self._refinement_count,
                max=self.max_refinements,
            )
            return False

        # Check for trigger events
        trigger_types = {
            EventType.VERIFICATION_FAILED,
            EventType.FULLSTACK_INCOMPLETE,
            EventType.E2E_TEST_FAILED,
            EventType.CONTRACTS_REFINEMENT_NEEDED,
        }

        has_trigger = any(e.type in trigger_types for e in events)

        if has_trigger:
            self.logger.info(
                "contract_refinement_triggered",
                events=[e.type.value for e in events if e.type in trigger_types],
                refinement_count=self._refinement_count,
            )
            return True

        return False

    async def act(self, events: list[Event]) -> None:
        """
        Refine contracts based on verification failure feedback.
        """
        self._refinement_count += 1

        self.logger.info(
            "starting_contract_refinement",
            refinement_number=self._refinement_count,
            events_count=len(events),
        )

        # Publish start event
        await self.event_bus.publish(Event(
            type=EventType.CONTRACTS_REFINEMENT_STARTED,
            source=self.name,
            data={"refinement_number": self._refinement_count},
        ))

        # Load current contracts
        current_contracts = await self._load_cached_contracts()
        if not current_contracts:
            self.logger.warning("no_contracts_to_refine")
            return

        # Aggregate failure data from all events
        failure_data = self._aggregate_failure_data(events)

        # Refine contracts based on failure
        try:
            refined_contracts = await self._refine_contracts(current_contracts, failure_data)

            if refined_contracts:
                # Save refined contracts
                await self._save_contracts(refined_contracts)

                # Publish CONTRACTS_UPDATED event
                await self.event_bus.publish(Event(
                    type=EventType.CONTRACTS_UPDATED,
                    source=self.name,
                    data={
                        "refinement_number": self._refinement_count,
                        "types": len(refined_contracts.types),
                        "endpoints": len(refined_contracts.endpoints),
                        "components": len(refined_contracts.components),
                        "services": len(refined_contracts.services),
                        "changes_made": self._describe_changes(current_contracts, refined_contracts),
                    },
                ))

                self.logger.info(
                    "contracts_refined_successfully",
                    types=len(refined_contracts.types),
                    endpoints=len(refined_contracts.endpoints),
                )
            else:
                self.logger.warning("contract_refinement_produced_no_changes")

        except Exception as e:
            self.logger.error(
                "contract_refinement_failed",
                error=str(e),
            )

    def _aggregate_failure_data(self, events: list[Event]) -> Dict[str, Any]:
        """
        Aggregate failure information from multiple events.
        """
        failure_data = {
            "missing_components": [],
            "failing_checks": {},
            "errors": [],
            "e2e_failures": [],
            "verification_details": {},
        }

        for event in events:
            if event.type == EventType.FULLSTACK_INCOMPLETE:
                failure_data["missing_components"].extend(
                    event.data.get("missing", [])
                )
                failure_data["failing_checks"].update(
                    event.data.get("failing", {})
                )
                failure_data["verification_details"].update(
                    event.data.get("details", {})
                )

            elif event.type == EventType.E2E_TEST_FAILED:
                failure_data["e2e_failures"].append({
                    "test": event.data.get("test_name", "unknown"),
                    "error": event.data.get("error", ""),
                    "screenshot": event.data.get("screenshot_path"),
                })

            elif event.type == EventType.VERIFICATION_FAILED:
                failure_data["errors"].append({
                    "type": event.data.get("type", "unknown"),
                    "message": event.data.get("message", ""),
                    "component": event.data.get("component"),
                })

            elif event.type == EventType.CONTRACTS_REFINEMENT_NEEDED:
                failure_data["errors"].append({
                    "type": "refinement_requested",
                    "message": event.data.get("reason", "Manual refinement requested"),
                    "suggested_changes": event.data.get("suggested_changes", []),
                })

        # Deduplicate missing components
        failure_data["missing_components"] = list(set(failure_data["missing_components"]))

        return failure_data

    async def _refine_contracts(
        self,
        current_contracts: InterfaceContracts,
        failure_data: Dict[str, Any],
    ) -> Optional[InterfaceContracts]:
        """
        Use Claude to refine contracts based on verification failure feedback.
        """
        self.logger.info(
            "refining_contracts_with_claude",
            missing_components=failure_data.get("missing_components"),
            error_count=len(failure_data.get("errors", [])),
        )

        # Build refinement prompt
        prompt = self._build_refinement_prompt(current_contracts, failure_data)

        # Call Claude for refinement
        result = await self.claude_tool.execute(
            prompt=prompt,
            agent_type="general",
        )

        if not result.success or not result.output:
            self.logger.warning("claude_refinement_failed", error=result.error)
            return None

        # Parse refined contracts
        refined_data = self._parse_claude_response(result.output)
        if not refined_data:
            return None

        # Merge refinements into current contracts
        return self._apply_refinements(current_contracts, refined_data)

    def _build_refinement_prompt(
        self,
        contracts: InterfaceContracts,
        failure_data: Dict[str, Any],
    ) -> str:
        """Build the refinement prompt for Claude."""
        current_json = contracts.to_json()

        # Build failure description
        failure_sections = []

        if failure_data.get("missing_components"):
            failure_sections.append(
                f"## Missing Components\n"
                f"The following components are incomplete or missing:\n"
                + "\n".join(f"- {c}" for c in failure_data["missing_components"])
            )

        if failure_data.get("failing_checks"):
            failing_str = json.dumps(failure_data["failing_checks"], indent=2)
            failure_sections.append(
                f"## Failing Checks\n```json\n{failing_str}\n```"
            )

        if failure_data.get("e2e_failures"):
            e2e_str = "\n".join(
                f"- {f['test']}: {f['error']}"
                for f in failure_data["e2e_failures"]
            )
            failure_sections.append(f"## E2E Test Failures\n{e2e_str}")

        if failure_data.get("errors"):
            error_str = "\n".join(
                f"- [{e['type']}] {e['message']}"
                for e in failure_data["errors"]
            )
            failure_sections.append(f"## Verification Errors\n{error_str}")

        failure_description = "\n\n".join(failure_sections)

        return f"""You are a Software Architect analyzing verification failures and refining contracts.

## Current Contracts

```json
{current_json}
```

## Verification Feedback

{failure_description}

## Your Task

Analyze the verification failures and determine what changes are needed to the contracts:

1. **Missing Components**: If frontend/backend/database/integration is incomplete, add missing contracts
2. **Type Mismatches**: If types don't match what the code needs, update type definitions
3. **Missing Endpoints**: If API endpoints are missing, add them with proper types
4. **Missing Components**: If React components are missing, add their contracts
5. **Service Gaps**: If services are incomplete, add method definitions

For each issue:
1. Identify the root cause in the contracts
2. Propose specific additions or changes
3. Ensure the refined contracts will pass verification

Output ONLY a valid JSON object with:
{{
    "analysis": "Brief analysis of what's wrong",
    "types_to_add": [
        {{"name": "TypeName", "fields": {{"field": "type"}}, "description": "..."}}
    ],
    "types_to_modify": [
        {{"name": "ExistingType", "add_fields": {{"newField": "type"}}, "reason": "..."}}
    ],
    "endpoints_to_add": [
        {{"path": "/api/...", "method": "GET|POST|PUT|DELETE", "description": "..."}}
    ],
    "components_to_add": [
        {{"name": "ComponentName", "props": {{"prop": "type"}}, "description": "..."}}
    ],
    "services_to_add": [
        {{"name": "ServiceName", "methods": {{"method": {{"params": {{}}, "return_type": "type"}}}}, "description": "..."}}
    ]
}}
"""

    def _parse_claude_response(self, output: str) -> Optional[Dict]:
        """Parse Claude's JSON response."""
        import re

        # Try to find JSON block
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", output, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try parsing whole output as JSON
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            pass

        # Try finding JSON object
        json_match = re.search(r"\{.*\}", output, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        self.logger.warning("failed_to_parse_refinement_response")
        return None

    def _apply_refinements(
        self,
        contracts: InterfaceContracts,
        refinements: Dict[str, Any],
    ) -> InterfaceContracts:
        """Apply refinements to contracts."""
        from ..engine.contracts import (
            TypeDefinition,
            APIEndpoint,
            ComponentContract,
            ServiceContract,
        )

        # Log analysis
        if refinements.get("analysis"):
            self.logger.info("refinement_analysis", analysis=refinements["analysis"])

        # Add new types
        for type_data in refinements.get("types_to_add", []):
            if isinstance(type_data, dict):
                contracts.add_type(TypeDefinition(
                    name=type_data.get("name", "Unknown"),
                    fields=type_data.get("fields", {}),
                    description=type_data.get("description", ""),
                ))

        # Modify existing types (add fields)
        for mod in refinements.get("types_to_modify", []):
            type_name = mod.get("name")
            add_fields = mod.get("add_fields", {})
            for t in contracts.types:
                if t.name == type_name:
                    t.fields.update(add_fields)
                    self.logger.info(
                        "type_modified",
                        type=type_name,
                        added_fields=list(add_fields.keys()),
                    )
                    break

        # Add new endpoints
        existing_endpoints = {(e.path, e.method) for e in contracts.endpoints}
        for ep_data in refinements.get("endpoints_to_add", []):
            if isinstance(ep_data, dict):
                key = (ep_data.get("path"), ep_data.get("method"))
                if key not in existing_endpoints:
                    contracts.add_endpoint(APIEndpoint(
                        path=ep_data.get("path", "/api/unknown"),
                        method=ep_data.get("method", "GET"),
                        description=ep_data.get("description", ""),
                    ))

        # Add new components
        existing_components = {c.name for c in contracts.components}
        for comp_data in refinements.get("components_to_add", []):
            if isinstance(comp_data, dict):
                if comp_data.get("name") not in existing_components:
                    contracts.add_component(ComponentContract(
                        name=comp_data.get("name", "Unknown"),
                        props=comp_data.get("props", {}),
                        description=comp_data.get("description", ""),
                    ))

        # Add new services
        existing_services = {s.name for s in contracts.services}
        for svc_data in refinements.get("services_to_add", []):
            if isinstance(svc_data, dict):
                if svc_data.get("name") not in existing_services:
                    contracts.add_service(ServiceContract(
                        name=svc_data.get("name", "Unknown"),
                        methods=svc_data.get("methods", {}),
                        description=svc_data.get("description", ""),
                    ))

        return contracts

    def _describe_changes(
        self,
        before: InterfaceContracts,
        after: InterfaceContracts,
    ) -> Dict[str, int]:
        """Describe what changed between contracts."""
        return {
            "types_added": len(after.types) - len(before.types),
            "endpoints_added": len(after.endpoints) - len(before.endpoints),
            "components_added": len(after.components) - len(before.components),
            "services_added": len(after.services) - len(before.services),
        }

    async def _load_cached_contracts(self) -> Optional[InterfaceContracts]:
        """Load contracts from cache file."""
        if not self._contracts_path.exists():
            self.logger.warning("no_contracts_cache_found", path=str(self._contracts_path))
            return None

        try:
            with open(self._contracts_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Reconstruct InterfaceContracts from JSON
            contracts = InterfaceContracts.from_dict(data)
            self._current_contracts = contracts
            return contracts

        except Exception as e:
            self.logger.error("failed_to_load_contracts", error=str(e))
            return None

    async def _save_contracts(self, contracts: InterfaceContracts) -> None:
        """Save refined contracts to cache file."""
        try:
            with open(self._contracts_path, "w", encoding="utf-8") as f:
                f.write(contracts.to_json())

            self._current_contracts = contracts
            self.logger.info("contracts_saved", path=str(self._contracts_path))

        except Exception as e:
            self.logger.error("failed_to_save_contracts", error=str(e))

    def get_refinement_count(self) -> int:
        """Get the current refinement iteration count."""
        return self._refinement_count

    def reset_refinement_count(self) -> None:
        """Reset refinement count (e.g., for new generation session)."""
        self._refinement_count = 0
