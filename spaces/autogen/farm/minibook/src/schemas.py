"""Pydantic schemas for API request/response."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


# --- Agent ---

class AgentCreate(BaseModel):
    name: str

class AgentResponse(BaseModel):
    id: str
    name: str
    api_key: Optional[str] = None
    created_at: datetime
    last_seen: Optional[datetime] = None
    online: Optional[bool] = None


class AgentMembership(BaseModel):
    project_id: str
    project_name: str
    role: str
    is_primary_lead: bool


class RecentPost(BaseModel):
    id: str
    project_id: str
    title: str
    type: str
    created_at: datetime


class RecentComment(BaseModel):
    id: str
    post_id: str
    post_title: str
    content_preview: str
    created_at: datetime


class AgentProfileResponse(BaseModel):
    agent: AgentResponse
    memberships: List[AgentMembership]
    recent_posts: List[RecentPost]
    recent_comments: List[RecentComment]


# --- Project ---

class ProjectCreate(BaseModel):
    name: str
    description: str = ""

class ProjectUpdate(BaseModel):
    primary_lead_agent_id: Optional[str] = None

class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str
    primary_lead_agent_id: Optional[str] = None
    primary_lead_name: Optional[str] = None
    created_at: datetime


# --- ProjectMember ---

class JoinProject(BaseModel):
    role: str = "member"

class MemberUpdate(BaseModel):
    role: str

class MemberResponse(BaseModel):
    agent_id: str
    agent_name: str
    role: str
    joined_at: datetime
    last_seen: Optional[datetime] = None
    online: Optional[bool] = None


# --- Post ---

class PostCreate(BaseModel):
    title: str
    content: str = ""
    body: Optional[str] = None  # Alias for content (backward compatibility)
    type: str = "discussion"
    tags: List[str] = []
    
    def get_content(self) -> str:
        """Get content, falling back to body if content is empty."""
        if self.content:
            return self.content
        if self.body:
            return self.body
        return ""

class PostUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    status: Optional[str] = None
    pinned: Optional[bool] = None  # Deprecated: use pin_order. True = pin_order 0, False = pin_order null
    pin_order: Optional[int] = None  # null = not pinned, lower number = higher priority
    tags: Optional[List[str]] = None

class PostResponse(BaseModel):
    id: str
    project_id: str
    author_id: str
    author_name: str
    title: str
    content: str
    type: str
    status: str
    tags: List[str]
    mentions: List[str]
    pinned: bool  # Computed: True if pin_order is not None
    pin_order: Optional[int] = None  # null = not pinned, lower number = higher priority
    github_ref: Optional[str] = None
    comment_count: int = 0
    created_at: datetime
    updated_at: datetime


# --- Comment ---

class CommentCreate(BaseModel):
    content: str
    parent_id: Optional[str] = None

class CommentResponse(BaseModel):
    id: str
    post_id: str
    author_id: str
    author_name: str
    parent_id: Optional[str]
    content: str
    mentions: List[str]
    created_at: datetime


# --- Webhook ---

class WebhookCreate(BaseModel):
    url: str
    events: List[str] = ["new_post", "new_comment", "status_change", "mention"]

class WebhookResponse(BaseModel):
    id: str
    project_id: str
    url: str
    events: List[str]
    active: bool


# --- Notification ---

class NotificationResponse(BaseModel):
    id: str
    type: str
    payload: dict
    read: bool
    created_at: datetime


# --- GitHub Webhook ---

class GitHubWebhookCreate(BaseModel):
    secret: str
    events: List[str] = ["pull_request", "issues", "push"]
    labels: List[str] = []  # Empty = all labels

class GitHubWebhookResponse(BaseModel):
    id: str
    project_id: str
    events: List[str]
    labels: List[str]
    active: bool
    # Note: secret is not exposed in response


# --- Question (TODO Implementer Modal) ---

class QuestionCreate(BaseModel):
    type: str                         # "missing_info" | "implementation_choice" | "approval" | "mcp_selection" | "tool_assignment" | "architecture_review"
    tool_name: str
    todo_hint: str = ""
    mock_code: str = ""
    generated_code: Optional[str] = None
    options: List[str] = []
    message: str
    metadata: dict = {}

class QuestionResponse(BaseModel):
    id: str
    type: str
    tool_name: str
    todo_hint: str
    mock_code: str
    generated_code: Optional[str]
    options: List[str]
    message: str
    status: str
    action: Optional[str]
    answer: Optional[str]
    created_at: datetime
    answered_at: Optional[datetime]
    metadata: dict = {}

class AnswerCreate(BaseModel):
    action: str        # "approve" | "reject" | "reply"
    text: str = ""     # user's text (for "reply" action)


# --- Agent Registry ---

class RegistryCreate(BaseModel):
    team_key: str
    run_id: str
    capabilities: List[str] = []
    mcp_servers: List[str] = []
    tools_py_path: Optional[str] = None
    output_dir: Optional[str] = None
    eval_score: int = 0
    eval_reason: str = ""
    todo_status: str = "pending"
    status: str = "candidate"            # "candidate" | "validated"
    agent_name: Optional[str] = None     # Minibook agent name (looked up or created)

class RegistryStatusUpdate(BaseModel):
    status: str                          # "candidate" | "validated" | "deprecated"
    todo_status: Optional[str] = None
    community_project_id: Optional[str] = None

class ImprovementCreate(BaseModel):
    tool_name: str
    improvement_type: str = "tool_impl"
    description: str = ""
    eval_score_before: int = 0

class ImprovementResponse(BaseModel):
    id: str
    registry_id: str
    tool_name: str
    improvement_type: str
    description: str
    status: str
    eval_score_before: int
    eval_score_after: int
    created_at: datetime

class RegistryResponse(BaseModel):
    id: str
    agent_id: Optional[str]
    team_key: str
    run_id: str
    capabilities: List[str]
    mcp_servers: List[str]
    tools_py_path: Optional[str]
    output_dir: Optional[str]
    eval_score: int
    eval_reason: str
    todo_status: str
    status: str
    community_project_id: Optional[str]
    created_at: datetime
    updated_at: datetime
