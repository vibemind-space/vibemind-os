"""
Minibook Client — REST API wrapper for Minibook collaboration platform.

Provides a clean Python interface to register agents, create projects,
post tasks, comment with code, poll notifications, and manage the
full agent-to-agent workflow via Minibook.
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

DEFAULT_MINIBOOK_URL = "http://localhost:8080"


@dataclass
class MinibookAgent:
    """Registered agent in Minibook."""
    id: str
    name: str
    api_key: str


@dataclass
class MinibookProject:
    """A Minibook project."""
    id: str
    name: str
    description: str = ""


@dataclass
class MinibookPost:
    """A post (task) in Minibook."""
    id: str
    title: str
    content: str
    type: str = "discussion"
    status: str = "open"
    tags: List[str] = field(default_factory=list)
    author_id: str = ""


@dataclass
class MinibookComment:
    """A comment on a post."""
    id: str
    content: str
    author_id: str = ""
    parent_id: Optional[str] = None


class MinibookClient:
    """
    Synchronous REST client for Minibook API.

    Usage:
        client = MinibookClient()
        agent = client.register_agent("architect")
        project = client.create_project(agent.api_key, "whatsapp-clone", "WhatsApp project")
        client.join_project(agent.api_key, project.id, role="architect")
        post = client.create_post(agent.api_key, project.id, "Design DB Schema", "...", type="plan")
        client.create_comment(agent.api_key, post.id, "Here is the schema: ...")
    """

    def __init__(self, base_url: str = DEFAULT_MINIBOOK_URL, timeout: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=timeout)
        logger.info("MinibookClient init url=%s", self.base_url)

    def _headers(self, api_key: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------
    def is_healthy(self) -> bool:
        try:
            resp = self._client.get(f"{self.base_url}/health")
            return resp.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Agents
    # ------------------------------------------------------------------
    def register_agent(self, name: str) -> MinibookAgent:
        """Register a new agent. Returns agent with api_key (shown only once!)."""
        resp = self._client.post(
            f"{self.base_url}/api/v1/agents",
            json={"name": name},
        )
        resp.raise_for_status()
        data = resp.json()
        agent = MinibookAgent(
            id=data["id"],
            name=data["name"],
            api_key=data["api_key"],
        )
        logger.info("Registered agent: %s (id=%s)", agent.name, agent.id)
        return agent

    def get_agent_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Look up an agent by name (no auth required)."""
        try:
            resp = self._client.get(f"{self.base_url}/api/v1/agents/by-name/{name}")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return None

    def heartbeat(self, api_key: str) -> bool:
        """Send heartbeat to mark agent as online."""
        try:
            resp = self._client.post(
                f"{self.base_url}/api/v1/agents/heartbeat",
                headers=self._headers(api_key),
            )
            return resp.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------
    def create_project(
        self,
        api_key: str,
        name: str,
        description: str = "",
    ) -> MinibookProject:
        """Create a new project."""
        resp = self._client.post(
            f"{self.base_url}/api/v1/projects",
            headers=self._headers(api_key),
            json={"name": name, "description": description},
        )
        resp.raise_for_status()
        data = resp.json()
        project = MinibookProject(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
        )
        logger.info("Created project: %s (id=%s)", project.name, project.id)
        return project

    def list_projects(self, api_key: str) -> List[Dict[str, Any]]:
        """List all projects."""
        resp = self._client.get(
            f"{self.base_url}/api/v1/projects",
            headers=self._headers(api_key),
        )
        resp.raise_for_status()
        return resp.json()

    def join_project(self, api_key: str, project_id: str, role: str = "developer") -> bool:
        """Join a project. Returns True if joined or already a member."""
        resp = self._client.post(
            f"{self.base_url}/api/v1/projects/{project_id}/join",
            headers=self._headers(api_key),
            json={"role": role},
        )
        # 400 = "Already a member" which is fine
        return resp.status_code in (200, 201, 400)

    def set_grand_plan(self, api_key: str, project_id: str, plan_text: str) -> Optional[MinibookPost]:
        """Set the Grand Plan by creating a pinned 'plan' type post."""
        # The PUT /plan endpoint requires admin token, so we create a plan-type post instead
        try:
            return self.create_post(
                api_key, project_id,
                title="Grand Plan",
                content=plan_text,
                post_type="plan",
                tags=["grand-plan", "roadmap"],
            )
        except Exception as e:
            logger.error("Failed to set grand plan: %s", e)
            return None

    # ------------------------------------------------------------------
    # Posts (Tasks)
    # ------------------------------------------------------------------
    def create_post(
        self,
        api_key: str,
        project_id: str,
        title: str,
        content: str,
        post_type: str = "discussion",
        tags: Optional[List[str]] = None,
    ) -> MinibookPost:
        """Create a new post (task assignment)."""
        resp = self._client.post(
            f"{self.base_url}/api/v1/projects/{project_id}/posts",
            headers=self._headers(api_key),
            json={
                "title": title,
                "content": content,
                "type": post_type,
                "tags": tags or [],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        post = MinibookPost(
            id=data["id"],
            title=data["title"],
            content=data["content"],
            type=data.get("type", post_type),
            status=data.get("status", "open"),
            tags=data.get("tags", []),
            author_id=data.get("author_id", ""),
        )
        logger.info("Created post: '%s' (id=%s)", post.title, post.id)
        return post

    def get_post(self, api_key: str, post_id: str) -> Dict[str, Any]:
        """Get a single post with all details."""
        resp = self._client.get(
            f"{self.base_url}/api/v1/posts/{post_id}",
            headers=self._headers(api_key),
        )
        resp.raise_for_status()
        return resp.json()

    def list_posts(
        self,
        api_key: str,
        project_id: str,
        status: Optional[str] = None,
        post_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List posts in a project, optionally filtered."""
        params: Dict[str, str] = {}
        if status:
            params["status"] = status
        if post_type:
            params["type"] = post_type
        resp = self._client.get(
            f"{self.base_url}/api/v1/projects/{project_id}/posts",
            headers=self._headers(api_key),
            params=params,
        )
        resp.raise_for_status()
        return resp.json()

    def update_post_status(self, api_key: str, post_id: str, status: str) -> bool:
        """Update a post's status (open, resolved, closed)."""
        resp = self._client.patch(
            f"{self.base_url}/api/v1/posts/{post_id}",
            headers=self._headers(api_key),
            json={"status": status},
        )
        return resp.status_code == 200

    def update_post_tags(self, api_key: str, post_id: str, tags: List[str]) -> bool:
        """Update a post's tags."""
        resp = self._client.patch(
            f"{self.base_url}/api/v1/posts/{post_id}",
            headers=self._headers(api_key),
            json={"tags": tags},
        )
        return resp.status_code == 200

    # ------------------------------------------------------------------
    # Comments (Code / Responses)
    # ------------------------------------------------------------------
    def create_comment(
        self,
        api_key: str,
        post_id: str,
        content: str,
        parent_id: Optional[str] = None,
    ) -> MinibookComment:
        """Add a comment to a post."""
        payload: Dict[str, Any] = {"content": content}
        if parent_id:
            payload["parent_id"] = parent_id
        resp = self._client.post(
            f"{self.base_url}/api/v1/posts/{post_id}/comments",
            headers=self._headers(api_key),
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        return MinibookComment(
            id=data["id"],
            content=data["content"],
            author_id=data.get("author_id", ""),
            parent_id=data.get("parent_id"),
        )

    def list_comments(self, api_key: str, post_id: str) -> List[Dict[str, Any]]:
        """List all comments on a post."""
        resp = self._client.get(
            f"{self.base_url}/api/v1/posts/{post_id}/comments",
            headers=self._headers(api_key),
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Notifications (Polling)
    # ------------------------------------------------------------------
    def get_notifications(
        self,
        api_key: str,
        unread_only: bool = True,
    ) -> List[Dict[str, Any]]:
        """Get notifications for the authenticated agent."""
        params = {"unread_only": str(unread_only).lower()}
        resp = self._client.get(
            f"{self.base_url}/api/v1/notifications",
            headers=self._headers(api_key),
            params=params,
        )
        resp.raise_for_status()
        return resp.json()

    def mark_notification_read(self, api_key: str, notification_id: str) -> bool:
        resp = self._client.post(
            f"{self.base_url}/api/v1/notifications/{notification_id}/read",
            headers=self._headers(api_key),
        )
        return resp.status_code == 200

    def mark_all_read(self, api_key: str) -> bool:
        resp = self._client.post(
            f"{self.base_url}/api/v1/notifications/read-all",
            headers=self._headers(api_key),
        )
        return resp.status_code == 200

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------
    def search_posts(
        self,
        api_key: str,
        keyword: Optional[str] = None,
        author: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search posts by keyword, author, or tag."""
        params: Dict[str, str] = {}
        if keyword:
            params["q"] = keyword
        if author:
            params["author"] = author
        if tag:
            params["tag"] = tag
        resp = self._client.get(
            f"{self.base_url}/api/v1/search",
            headers=self._headers(api_key),
            params=params,
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    def close(self) -> None:
        self._client.close()
