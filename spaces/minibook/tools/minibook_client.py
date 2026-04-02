"""
Minibook Client - HTTP wrapper for Minibook REST API

Wraps the Minibook REST API (no Python SDK available).
Uses raw requests for all API calls with Bearer token auth.

API Reference:
    POST /api/v1/agents           - Register new agent (returns api_key)
    GET  /api/v1/agents           - List all agents
    POST /api/v1/projects         - Create project
    GET  /api/v1/projects         - List projects
    POST /api/v1/projects/:id/join - Join project with role
    GET  /api/v1/projects/:id/posts - Get posts in project
    POST /api/v1/projects/:id/posts - Create post (supports @mentions)
    GET  /api/v1/posts/:id/comments - Get comments on post
    POST /api/v1/posts/:id/comments - Create comment on post
    GET  /api/v1/notifications      - Get notifications for agent
    POST /api/v1/notifications/:id/read - Mark notification as read
"""

import logging
import os
from typing import Dict, Any, Optional, List

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

_logger = logging.getLogger(__name__)


def _debug_print(msg: str):
    """Log debug message."""
    _logger.debug("[MinibookClient] %s", msg)


class MinibookClient:
    """
    HTTP client wrapping the Minibook REST API.

    Each agent gets a Bearer token on registration.
    All subsequent calls for that agent use the token.
    """

    def __init__(self, url: str = None):
        self._url = (url or os.getenv("MINIBOOK_URL", "http://localhost:3480")).rstrip("/")
        self._agents: Dict[str, Dict[str, str]] = {}  # name -> {api_key, id}
        self._project_id: Optional[str] = None
        _logger.info(f"MinibookClient: target={self._url}")

    # =========================================================================
    # Agent Management
    # =========================================================================

    def register_agent(self, name: str) -> Dict[str, Any]:
        """
        Register a new agent in Minibook.

        POST /api/v1/agents
        Body: {"name": "<name>"}
        Returns: {"id": "...", "api_key": "...", "name": "..."}

        The api_key is only returned once — we store it in memory.
        """
        _logger.debug("register_agent called: name=%s", name)
        resp = requests.post(
            f"{self._url}/api/v1/agents",
            json={"name": name},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        api_key = data.get("api_key", "")
        agent_id = data.get("id", "")
        self._agents[name] = {"api_key": api_key, "id": agent_id}

        _debug_print(f"Registered agent '{name}' (id={agent_id})")
        return data

    def list_agents(self) -> List[Dict[str, Any]]:
        """
        List all registered agents.

        GET /api/v1/agents
        """
        resp = requests.get(f"{self._url}/api/v1/agents", timeout=10)
        resp.raise_for_status()
        return resp.json()

    # =========================================================================
    # Project Management
    # =========================================================================

    def create_project(
        self, name: str, description: str = "", agent_name: str = "vibemind_orchestrator"
    ) -> Dict[str, Any]:
        """
        Create a new project.

        POST /api/v1/projects
        Body: {"name": "<name>", "description": "<desc>"}
        """
        _logger.debug("create_project called: name=%s, agent=%s", name, agent_name)
        resp = requests.post(
            f"{self._url}/api/v1/projects",
            json={"name": name, "description": description},
            headers=self._auth_headers(agent_name),
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        self._project_id = data.get("id", "")
        _debug_print(f"Created project '{name}' (id={self._project_id})")
        return data

    def list_projects(self, agent_name: str = "vibemind_orchestrator") -> List[Dict[str, Any]]:
        """
        List all projects.

        GET /api/v1/projects
        """
        resp = requests.get(
            f"{self._url}/api/v1/projects",
            headers=self._auth_headers(agent_name),
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def join_project(
        self, project_id: str, agent_name: str, role: str
    ) -> Dict[str, Any]:
        """
        Join a project with a specific role.

        POST /api/v1/projects/:id/join
        Body: {"role": "<role description>"}
        """
        resp = requests.post(
            f"{self._url}/api/v1/projects/{project_id}/join",
            json={"role": role},
            headers=self._auth_headers(agent_name),
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        _debug_print(f"Agent '{agent_name}' joined project {project_id} as '{role[:50]}'")
        return data

    # =========================================================================
    # Posts (Discussions)
    # =========================================================================

    def create_post(
        self,
        project_id: str,
        content: str,
        agent_name: str = "vibemind_orchestrator",
        post_type: str = "discussion",
        title: str = "",
    ) -> Dict[str, Any]:
        """
        Create a post in a project.

        POST /api/v1/projects/:id/posts
        Body: {"title": "<title>", "content": "<content>", "type": "<type>"}

        Supports @mentions: "@vibemind_ideas bitte erstelle..."
        """
        _logger.debug("create_post called: project_id=%s, agent=%s, type=%s", project_id, agent_name, post_type)
        if not title:
            # Auto-generate title from content (first 80 chars, first line)
            first_line = content.split("\n")[0].strip()
            # Strip markdown code fences
            if first_line.startswith("```"):
                first_line = content.split("\n", 2)[-1].split("\n")[0].strip() if "\n" in content else "Task"
            title = first_line[:80] if first_line else "Task"
        body = {"title": title, "content": content, "type": post_type}
        resp = requests.post(
            f"{self._url}/api/v1/projects/{project_id}/posts",
            json=body,
            headers=self._auth_headers(agent_name),
            timeout=10,
        )
        if not resp.ok:
            _debug_print(
                f"POST /posts failed: {resp.status_code} — {resp.text[:500]}"
            )
            _debug_print(f"  body sent: content={content[:200]}... type={post_type} agent={agent_name}")
        resp.raise_for_status()
        data = resp.json()
        _debug_print(f"Created post in project {project_id} (id={data.get('id', '?')})")
        return data

    def get_posts(
        self, project_id: str, agent_name: str = "vibemind_orchestrator"
    ) -> List[Dict[str, Any]]:
        """
        Get all posts in a project.

        GET /api/v1/projects/:id/posts
        """
        resp = requests.get(
            f"{self._url}/api/v1/projects/{project_id}/posts",
            headers=self._auth_headers(agent_name),
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    # =========================================================================
    # Comments
    # =========================================================================

    def create_comment(
        self, post_id: str, content: str, agent_name: str
    ) -> Dict[str, Any]:
        """
        Create a comment on a post.

        POST /api/v1/posts/:id/comments
        Body: {"content": "<content>"}
        """
        _logger.debug("create_comment called: post_id=%s, agent=%s", post_id, agent_name)
        resp = requests.post(
            f"{self._url}/api/v1/posts/{post_id}/comments",
            json={"content": content},
            headers=self._auth_headers(agent_name),
            timeout=10,
        )
        if not resp.ok:
            _debug_print(
                f"POST /comments failed: {resp.status_code} — {resp.text[:500]}"
            )
        resp.raise_for_status()
        return resp.json()

    def get_comments(
        self, post_id: str, agent_name: str = "vibemind_orchestrator"
    ) -> List[Dict[str, Any]]:
        """
        Get all comments on a post.

        GET /api/v1/posts/:id/comments
        """
        resp = requests.get(
            f"{self._url}/api/v1/posts/{post_id}/comments",
            headers=self._auth_headers(agent_name),
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    # =========================================================================
    # Notifications
    # =========================================================================

    def get_notifications(self, agent_name: str) -> List[Dict[str, Any]]:
        """
        Get notifications for an agent (mentions, replies).

        GET /api/v1/notifications
        """
        resp = requests.get(
            f"{self._url}/api/v1/notifications",
            headers=self._auth_headers(agent_name),
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def mark_notification_read(
        self, notification_id: str, agent_name: str
    ) -> Dict[str, Any]:
        """
        Mark a notification as read.

        POST /api/v1/notifications/:id/read
        """
        resp = requests.post(
            f"{self._url}/api/v1/notifications/{notification_id}/read",
            headers=self._auth_headers(agent_name),
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    # =========================================================================
    # Health Check
    # =========================================================================

    def get_status(self) -> Dict[str, Any]:
        """Check if Minibook is reachable."""
        try:
            resp = requests.get(f"{self._url}/api/v1/agents", timeout=5)
            agent_count = len(resp.json()) if resp.ok else 0
            return {
                "success": True,
                "status": "connected",
                "url": self._url,
                "agent_count": agent_count,
                "registered_agents": list(self._agents.keys()),
            }
        except requests.exceptions.ConnectionError:
            return {
                "success": False,
                "status": "disconnected",
                "url": self._url,
                "error": "Minibook nicht erreichbar",
            }
        except Exception as e:
            return {
                "success": False,
                "status": "error",
                "url": self._url,
                "error": str(e),
            }

    # =========================================================================
    # Internal Helpers
    # =========================================================================

    @property
    def project_id(self) -> Optional[str]:
        """Current collaboration project ID."""
        return self._project_id

    @project_id.setter
    def project_id(self, value: str):
        self._project_id = value

    def has_agent(self, name: str) -> bool:
        """Check if an agent is registered locally."""
        return name in self._agents

    def _auth_headers(self, agent_name: str) -> Dict[str, str]:
        """Get auth headers for a registered agent."""
        agent_info = self._agents.get(agent_name, {})
        api_key = agent_info.get("api_key", "")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers


# =============================================================================
# Singleton
# =============================================================================

_minibook_client: Optional[MinibookClient] = None


def get_minibook_client() -> MinibookClient:
    """Get or create the global MinibookClient instance."""
    global _minibook_client
    if _minibook_client is None:
        _minibook_client = MinibookClient()
    return _minibook_client


def reset_minibook_client() -> None:
    """Reset the client (for testing)."""
    global _minibook_client
    _minibook_client = None


__all__ = ["MinibookClient", "get_minibook_client", "reset_minibook_client"]
