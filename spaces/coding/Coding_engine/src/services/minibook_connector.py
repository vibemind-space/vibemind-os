"""
Minibook Connector - Bridges Coding Engine EventBus to Minibook agent collaboration.

This service:
1. Registers all Coding Engine agents as Minibook agents
2. Creates a project in Minibook for each code generation session
3. Translates EventBus events into Minibook posts/comments
4. Watches Minibook for agent-to-agent discussion results
5. Provides webhook endpoint for Minibook notifications

Architecture:
  EventBus → MinibookConnector → Minibook API (HTTP)
  Minibook Webhooks → MinibookConnector → EventBus
"""

import asyncio
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import aiohttp
import structlog

from ..mind.event_bus import EventBus, Event, EventType
from .circuit_breaker import get_circuit_breaker, CircuitBreakerError

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MINIBOOK_URL = os.environ.get("MINIBOOK_URL", "http://localhost:3456")
MINIBOOK_ADMIN_TOKEN = os.environ.get("MINIBOOK_ADMIN_TOKEN", "")

# Map Coding Engine agents to Minibook roles
AGENT_ROLES = {
    "Builder": "build-engineer",
    "Tester": "qa-engineer",
    "Validator": "code-reviewer",
    "Fixer": "senior-developer",
    "Generator": "code-generator",
    "TreeQuestVerification": "verification-specialist",
    "ShinkaEvolve": "optimization-specialist",
    "RuntimeDebugger": "debugger",
    "DatabaseAgent": "database-architect",
    "APIAgent": "api-developer",
    "AuthAgent": "security-engineer",
    "DeploymentTeam": "devops-engineer",
    "Documentation": "technical-writer",
    "SecurityScannerAgent": "security-auditor",
    "PerformanceAgent": "performance-engineer",
    "FullstackVerifier": "fullstack-verifier",
    "ContinuousArchitect": "architect",
}

# Events that should be posted to Minibook
POSTABLE_EVENTS = {
    EventType.BUILD_SUCCEEDED: ("status_update", "Build succeeded ✓"),
    EventType.BUILD_FAILED: ("issue", "Build failed ✗"),
    EventType.TEST_PASSED: ("status_update", "Tests passed ✓"),
    EventType.TEST_FAILED: ("issue", "Test failures detected"),
    EventType.CODE_GENERATED: ("discussion", "New code generated"),
    EventType.CODE_FIXED: ("discussion", "Code fix applied"),
    EventType.CODE_FIX_NEEDED: ("issue", "Fix needed"),
    EventType.VALIDATION_ERROR: ("issue", "Validation error"),
    EventType.VALIDATION_PASSED: ("status_update", "Validation passed ✓"),
    EventType.ESCALATION_EXHAUSTED: ("issue", "All fix strategies exhausted — need evolutionary approach"),
    EventType.DEPLOY_SUCCEEDED: ("status_update", "Deployment succeeded ✓"),
    EventType.DEPLOY_FAILED: ("issue", "Deployment failed"),
    EventType.TYPE_ERROR: ("issue", "Type errors detected"),
    EventType.SECURITY_VULNERABILITY: ("issue", "Security vulnerability found"),
    # Emergent system events
    EventType.PACKAGE_READY: ("status_update", "New project package ingested"),
    EventType.TREEQUEST_VERIFICATION_STARTED: ("status_update", "TreeQuest verification running"),
    EventType.TREEQUEST_VERIFICATION_COMPLETE: ("discussion", "TreeQuest verification complete"),
    EventType.TREEQUEST_FINDING_CRITICAL: ("issue", "Critical inconsistency found (TreeQuest)"),
    EventType.TREEQUEST_FINDING_WARNING: ("discussion", "Warning from TreeQuest verification"),
    EventType.EVOLUTION_REQUESTED: ("discussion", "Evolutionary improvement requested"),
    EventType.EVOLUTION_STARTED: ("status_update", "ShinkaEvolve running"),
    EventType.EVOLUTION_IMPROVED: ("status_update", "Evolved solution found ✓"),
    EventType.EVOLUTION_FAILED: ("issue", "Evolution failed — no improvement"),
    EventType.EVOLUTION_APPLIED: ("discussion", "Evolved code applied to codebase"),
    EventType.PIPELINE_STARTED: ("status_update", "Emergent pipeline started"),
    EventType.PIPELINE_COMPLETED: ("status_update", "Pipeline completed ✓"),
    EventType.PIPELINE_FAILED: ("issue", "Pipeline failed"),
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class MinibookAgent:
    """Represents a registered Minibook agent."""
    name: str
    agent_id: str
    api_key: str
    role: str


@dataclass
class MinibookProject:
    """Represents a Minibook project for a generation session."""
    project_id: str
    name: str
    description: str


# ---------------------------------------------------------------------------
# HTTP Client
# ---------------------------------------------------------------------------

class MinibookClient:
    """HTTP client for Minibook API."""

    def __init__(self, base_url: str = MINIBOOK_URL):
        self.base_url = base_url.rstrip("/")
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _request(
        self,
        method: str,
        path: str,
        api_key: Optional[str] = None,
        json_data: Any = None,
        params: Optional[Dict] = None,
        retries: int = 2,
    ) -> Optional[Dict]:
        # Circuit breaker: fast-fail if Minibook is known to be down
        breaker = get_circuit_breaker("minibook", failure_threshold=5, recovery_timeout=30)
        try:
            async with breaker:
                return await self._do_request(method, path, api_key, json_data, params, retries)
        except CircuitBreakerError:
            logger.debug("minibook_circuit_open", path=path)
            return None

    async def _do_request(
        self,
        method: str,
        path: str,
        api_key: Optional[str] = None,
        json_data: Any = None,
        params: Optional[Dict] = None,
        retries: int = 2,
    ) -> Optional[Dict]:
        """Execute the actual HTTP request (wrapped by circuit breaker)."""
        session = await self._get_session()
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        url = f"{self.base_url}{path}"
        last_error = None

        for attempt in range(retries + 1):
            try:
                async with session.request(
                    method, url, headers=headers, json=json_data, params=params
                ) as resp:
                    if resp.status >= 500 and attempt < retries:
                        # Server error — retry with backoff
                        await asyncio.sleep(0.5 * (attempt + 1))
                        continue
                    if resp.status >= 400:
                        text = await resp.text()
                        logger.warning(
                            "minibook_api_error",
                            status=resp.status,
                            path=path,
                            body=text[:200],
                        )
                        return None
                    if resp.content_type == "application/json":
                        return await resp.json()
                    return {"text": await resp.text()}
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_error = e
                if attempt < retries:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    # Recreate session on connection errors
                    try:
                        await self._session.close()
                    except:
                        pass
                    self._session = None
                    session = await self._get_session()
                    continue
            except Exception as e:
                last_error = e
                break

        logger.warning("minibook_request_failed", path=path, error=str(last_error), retries=retries)
        # Raise so circuit breaker detects the failure
        if last_error:
            raise last_error
        raise ConnectionError(f"Minibook request failed: {path}")

    # Agent endpoints
    async def register_agent(self, name: str) -> Optional[Dict]:
        return await self._request("POST", "/api/v1/agents", json_data={"name": name})

    async def heartbeat(self, api_key: str) -> Optional[Dict]:
        return await self._request("POST", "/api/v1/agents/heartbeat", api_key=api_key)

    # Project endpoints
    async def create_project(
        self, api_key: str, name: str, description: str
    ) -> Optional[Dict]:
        return await self._request(
            "POST",
            "/api/v1/projects",
            api_key=api_key,
            json_data={"name": name, "description": description},
        )

    async def join_project(
        self, api_key: str, project_id: str, role: str
    ) -> Optional[Dict]:
        return await self._request(
            "POST",
            f"/api/v1/projects/{project_id}/join",
            api_key=api_key,
            json_data={"role": role},
        )

    # Post endpoints
    async def create_post(
        self,
        api_key: str,
        project_id: str,
        title: str,
        content: str,
        post_type: str = "discussion",
        tags: Optional[List[str]] = None,
    ) -> Optional[Dict]:
        return await self._request(
            "POST",
            f"/api/v1/projects/{project_id}/posts",
            api_key=api_key,
            json_data={
                "title": title,
                "content": content,
                "type": post_type,
                "tags": tags or [],
            },
        )

    async def create_comment(
        self, api_key: str, post_id: str, content: str
    ) -> Optional[Dict]:
        return await self._request(
            "POST",
            f"/api/v1/posts/{post_id}/comments",
            api_key=api_key,
            json_data={"content": content},
        )

    async def get_notifications(
        self, api_key: str, unread_only: bool = True
    ) -> Optional[List[Dict]]:
        result = await self._request(
            "GET",
            "/api/v1/notifications",
            api_key=api_key,
            params={"unread_only": str(unread_only).lower()},
        )
        return result if isinstance(result, list) else None

    # Webhook endpoints
    async def create_webhook(
        self, api_key: str, project_id: str, url: str, events: List[str]
    ) -> Optional[Dict]:
        return await self._request(
            "POST",
            f"/api/v1/projects/{project_id}/webhooks",
            api_key=api_key,
            json_data={"url": url, "events": events},
        )

    # Health check
    async def health(self) -> bool:
        result = await self._request("GET", "/health")
        return result is not None


# ---------------------------------------------------------------------------
# Main Connector
# ---------------------------------------------------------------------------

class MinibookConnector:
    """Bridges Coding Engine EventBus to Minibook collaboration platform."""

    def __init__(
        self,
        event_bus: EventBus,
        minibook_url: str = MINIBOOK_URL,
        agent_names: Optional[List[str]] = None,
    ):
        self.event_bus = event_bus
        self.client = MinibookClient(minibook_url)
        self.agent_names = agent_names or list(AGENT_ROLES.keys())

        # State
        self._agents: Dict[str, MinibookAgent] = {}
        self._project: Optional[MinibookProject] = None
        self._post_cache: Dict[str, str] = {}  # event_key -> post_id
        self._running = False
        self._initialized = False

    async def initialize(self, session_name: Optional[str] = None) -> bool:
        """Register agents, create project, subscribe to events."""
        # Check Minibook health
        if not await self.client.health():
            logger.warning("Minibook not available, connector disabled")
            return False

        # Register agents
        for agent_name in self.agent_names:
            mb_name = f"CE_{agent_name}"
            result = await self.client.register_agent(mb_name)
            if result and "api_key" in result:
                self._agents[agent_name] = MinibookAgent(
                    name=mb_name,
                    agent_id=result["id"],
                    api_key=result["api_key"],
                    role=AGENT_ROLES.get(agent_name, "developer"),
                )
                logger.info("minibook_agent_registered", agent=mb_name)
            else:
                logger.warning("minibook_agent_registration_failed", agent=mb_name)

        if not self._agents:
            logger.error("No agents registered in Minibook")
            return False

        # Create project
        lead_agent = next(iter(self._agents.values()))
        project_name = session_name or f"CodingEngine_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        result = await self.client.create_project(
            lead_agent.api_key,
            project_name,
            "Autonomous code generation session managed by Coding Engine",
        )
        if result and "id" in result:
            self._project = MinibookProject(
                project_id=result["id"],
                name=project_name,
                description=result.get("description", ""),
            )
            logger.info("minibook_project_created", project=project_name, id=result["id"])
        else:
            logger.error("minibook_project_creation_failed")
            return False

        # Join all agents to project
        for agent_name, agent in self._agents.items():
            await self.client.join_project(
                agent.api_key, self._project.project_id, agent.role
            )

        # Subscribe to EventBus events
        for event_type in POSTABLE_EVENTS:
            self.event_bus.subscribe(event_type, self._on_event)

        self._initialized = True
        logger.info(
            "minibook_connector_initialized",
            agents=len(self._agents),
            project=self._project.name,
        )
        return True

    async def _on_event(self, event: Event) -> None:
        """Handle an EventBus event by posting to Minibook."""
        if not self._initialized or not self._project:
            return

        event_info = POSTABLE_EVENTS.get(event.type)
        if not event_info:
            return

        post_type, title_prefix = event_info

        # Determine which agent should post
        agent_name = event.data.get("agent", event.data.get("source", "Builder"))
        agent = self._agents.get(agent_name) or next(iter(self._agents.values()))

        # Build post content
        title = f"{title_prefix}"
        content_parts = [f"**Event:** `{event.type.value}`"]

        if event.data.get("file"):
            content_parts.append(f"**File:** `{event.data['file']}`")
        if event.data.get("reason"):
            content_parts.append(f"**Reason:** {event.data['reason']}")
        if event.data.get("details"):
            details = event.data["details"]
            if isinstance(details, str):
                content_parts.append(f"**Details:** {details[:500]}")
            elif isinstance(details, list):
                for d in details[:5]:
                    content_parts.append(f"- {d}")

        # Add @mentions for relevant agents
        mentions = self._get_relevant_mentions(event)
        if mentions:
            content_parts.append(f"\n**CC:** {' '.join(mentions)}")

        content = "\n\n".join(content_parts)
        tags = [event.type.value, post_type]

        # Post to Minibook
        result = await self.client.create_post(
            agent.api_key,
            self._project.project_id,
            title,
            content,
            post_type=post_type,
            tags=tags,
        )

        if result and "id" in result:
            cache_key = f"{event.type.value}_{event.data.get('file', '')}"
            self._post_cache[cache_key] = result["id"]
            logger.debug("minibook_post_created", post_id=result["id"], title=title)

    def _get_relevant_mentions(self, event: Event) -> List[str]:
        """Determine which agents should be @mentioned for an event."""
        mentions = []
        et = event.type

        if et in (EventType.BUILD_FAILED, EventType.TEST_FAILED):
            for name in ["Fixer", "RuntimeDebugger"]:
                if name in self._agents:
                    mentions.append(f"@CE_{name}")

        elif et == EventType.ESCALATION_EXHAUSTED:
            if "ShinkaEvolve" in self._agents:
                mentions.append("@CE_ShinkaEvolve")

        elif et == EventType.CODE_GENERATED:
            for name in ["TreeQuestVerification", "Validator", "Builder"]:
                if name in self._agents:
                    mentions.append(f"@CE_{name}")

        elif et == EventType.VALIDATION_ERROR:
            if "Fixer" in self._agents:
                mentions.append("@CE_Fixer")

        elif et in (EventType.TREEQUEST_FINDING_CRITICAL, EventType.TREEQUEST_FINDING_WARNING):
            for name in ["Fixer", "Builder"]:
                if name in self._agents:
                    mentions.append(f"@CE_{name}")

        elif et == EventType.EVOLUTION_IMPROVED:
            for name in ["TreeQuestVerification", "Builder"]:
                if name in self._agents:
                    mentions.append(f"@CE_{name}")

        elif et == EventType.PACKAGE_READY:
            for name in ["Builder", "TreeQuestVerification"]:
                if name in self._agents:
                    mentions.append(f"@CE_{name}")

        return mentions

    async def post_summary(self, summary: str, title: str = "Pipeline Summary") -> None:
        """Post a pipeline summary to Minibook."""
        if not self._initialized or not self._project:
            return
        lead = next(iter(self._agents.values()))
        await self.client.create_post(
            lead.api_key,
            self._project.project_id,
            title,
            summary,
            post_type="discussion",
            tags=["summary"],
        )

    async def post_verification_results(
        self, findings: List[Dict], source: str = "TreeQuest"
    ) -> None:
        """Post verification findings as a Minibook discussion thread."""
        if not self._initialized or not self._project:
            return

        agent = self._agents.get("TreeQuestVerification") or next(iter(self._agents.values()))
        title = f"{source} Verification Results"
        content_parts = [f"**{source} found {len(findings)} issues:**\n"]
        for f in findings[:10]:
            sev = f.get("severity", "?")
            desc = f.get("description", "")
            file = f.get("file", "?")
            content_parts.append(f"- [{sev.upper()}] `{file}`: {desc}")

        if len(findings) > 10:
            content_parts.append(f"\n...and {len(findings) - 10} more")

        await self.client.create_post(
            agent.api_key,
            self._project.project_id,
            title,
            "\n".join(content_parts),
            post_type="review",
            tags=["verification", source.lower()],
        )

    async def start_heartbeat(self, interval: int = 30):
        """Send periodic heartbeats to keep agents alive in Minibook."""
        self._running = True

        async def _heartbeat_loop():
            while self._running:
                for agent_name, agent in self._agents.items():
                    try:
                        await self.client.heartbeat(agent.api_key)
                    except Exception:
                        pass
                await asyncio.sleep(interval)

        self._heartbeat_task = asyncio.create_task(_heartbeat_loop())
        logger.info("minibook_heartbeat_started", interval=interval)

    async def close(self):
        """Clean up resources."""
        self._running = False
        if hasattr(self, "_heartbeat_task") and self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        await self.client.close()
        logger.info("minibook_connector_closed")


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------

async def create_minibook_connector(
    event_bus: EventBus,
    session_name: Optional[str] = None,
    minibook_url: Optional[str] = None,
) -> Optional[MinibookConnector]:
    """Create and initialize a MinibookConnector. Returns None if Minibook is unavailable."""
    connector = MinibookConnector(
        event_bus=event_bus,
        minibook_url=minibook_url or MINIBOOK_URL,
    )
    success = await connector.initialize(session_name)
    if success:
        return connector
    return None
