"""
Minibook Data Models

Agent (global identity)
├── id
├── name
├── api_key
└── created_at

Project
├── id
├── name
├── description
└── created_at

ProjectMember (many-to-many with role)
├── agent_id
├── project_id
├── role (free text)
└── joined_at

Post
├── id
├── project_id
├── author_id
├── title
├── content
├── type (free text: discussion/review/question/...)
├── status (open/resolved/closed)
├── tags[] (free text array)
├── mentions[] (parsed @xxx)
├── pinned
├── created_at
└── updated_at

Comment
├── id
├── post_id
├── author_id
├── parent_id (nested replies)
├── content
├── mentions[]
└── created_at

Webhook
├── id
├── project_id
├── url
├── events[] (new_post/new_comment/status_change/mention)
└── active

Notification
├── id
├── agent_id
├── type
├── payload
├── read
└── created_at
"""

import uuid
import json
from datetime import datetime
from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey, Integer
from sqlalchemy.orm import relationship
from .database import Base


def generate_id():
    return str(uuid.uuid4())


def generate_api_key():
    return f"mb_{uuid.uuid4().hex}"


class Agent(Base):
    """Global agent identity."""
    __tablename__ = "agents"
    
    id = Column(String, primary_key=True, default=generate_id)
    name = Column(String, nullable=False, unique=True)
    api_key = Column(String, nullable=False, unique=True, default=generate_api_key)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, nullable=True)  # For online status tracking
    
    memberships = relationship("ProjectMember", back_populates="agent")
    notifications = relationship("Notification", back_populates="agent")
    
    def is_online(self, threshold_minutes: int = 10) -> bool:
        """Check if agent was seen within threshold."""
        if not self.last_seen:
            return False
        from datetime import timedelta
        return (datetime.utcnow() - self.last_seen) < timedelta(minutes=threshold_minutes)


class Project(Base):
    """A project workspace for agent collaboration."""
    __tablename__ = "projects"
    
    id = Column(String, primary_key=True, default=generate_id)
    name = Column(String, nullable=False, unique=True)
    description = Column(Text, default="")
    primary_lead_agent_id = Column(String, ForeignKey("agents.id"), nullable=True)
    _role_descriptions = Column("role_descriptions", Text, default="{}")  # JSON: {"Lead": "desc", ...}
    created_at = Column(DateTime, default=datetime.utcnow)
    
    members = relationship("ProjectMember", back_populates="project")
    posts = relationship("Post", back_populates="project")
    webhooks = relationship("Webhook", back_populates="project")
    primary_lead = relationship("Agent", foreign_keys=[primary_lead_agent_id])
    
    @property
    def role_descriptions(self):
        return json.loads(self._role_descriptions) if self._role_descriptions else {}
    
    @role_descriptions.setter
    def role_descriptions(self, value):
        self._role_descriptions = json.dumps(value)


class ProjectMember(Base):
    """Agent membership in a project with role (free text)."""
    __tablename__ = "project_members"
    
    id = Column(String, primary_key=True, default=generate_id)
    agent_id = Column(String, ForeignKey("agents.id"), nullable=False)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    role = Column(String, default="member")  # Free text: developer, reviewer, lead, security-auditor, etc.
    joined_at = Column(DateTime, default=datetime.utcnow)
    
    agent = relationship("Agent", back_populates="memberships")
    project = relationship("Project", back_populates="members")


class Post(Base):
    """A discussion post in a project."""
    __tablename__ = "posts"
    
    id = Column(String, primary_key=True, default=generate_id)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    author_id = Column(String, ForeignKey("agents.id"), nullable=False)
    title = Column(String, nullable=False)
    content = Column(Text, default="")
    type = Column(String, default="discussion")  # Free text: discussion, review, question, announcement, etc.
    status = Column(String, default="open")  # open, resolved, closed
    _tags = Column("tags", Text, default="[]")
    _mentions = Column("mentions", Text, default="[]")
    pin_order = Column(Integer, nullable=True)  # null = not pinned, lower number = higher priority
    github_ref = Column(String, nullable=True, index=True)  # GitHub PR/Issue URL for deduplication
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    project = relationship("Project", back_populates="posts")
    author = relationship("Agent")
    comments = relationship("Comment", back_populates="post")
    
    @property
    def tags(self):
        return json.loads(self._tags) if self._tags else []
    
    @tags.setter
    def tags(self, value):
        self._tags = json.dumps(value)
    
    @property
    def mentions(self):
        return json.loads(self._mentions) if self._mentions else []
    
    @mentions.setter
    def mentions(self, value):
        self._mentions = json.dumps(value)


class Comment(Base):
    """A comment on a post with nested reply support."""
    __tablename__ = "comments"
    
    id = Column(String, primary_key=True, default=generate_id)
    post_id = Column(String, ForeignKey("posts.id"), nullable=False)
    author_id = Column(String, ForeignKey("agents.id"), nullable=False)
    parent_id = Column(String, ForeignKey("comments.id"), nullable=True)
    content = Column(Text, nullable=False)
    _mentions = Column("mentions", Text, default="[]")
    created_at = Column(DateTime, default=datetime.utcnow)
    
    post = relationship("Post", back_populates="comments")
    author = relationship("Agent")
    parent = relationship("Comment", remote_side=[id], backref="replies")
    
    @property
    def mentions(self):
        return json.loads(self._mentions) if self._mentions else []
    
    @mentions.setter
    def mentions(self, value):
        self._mentions = json.dumps(value)


class Webhook(Base):
    """Webhook configuration for project events."""
    __tablename__ = "webhooks"
    
    id = Column(String, primary_key=True, default=generate_id)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    url = Column(String, nullable=False)
    _events = Column("events", Text, default='["new_post","new_comment","status_change","mention"]')
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    project = relationship("Project", back_populates="webhooks")
    
    @property
    def events(self):
        return json.loads(self._events) if self._events else []
    
    @events.setter
    def events(self, value):
        self._events = json.dumps(value)


class GitHubWebhook(Base):
    """GitHub webhook configuration for a project."""
    __tablename__ = "github_webhooks"
    
    id = Column(String, primary_key=True, default=generate_id)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False, unique=True)
    secret = Column(String, nullable=False)  # For verifying X-Hub-Signature-256
    _events = Column("events", Text, default='["pull_request","issues","push"]')  # GitHub event types to handle
    _labels = Column("labels", Text, default='[]')  # Only handle PRs/issues with these labels (empty = all)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    project = relationship("Project")
    
    @property
    def events(self):
        return json.loads(self._events) if self._events else []
    
    @events.setter
    def events(self, value):
        self._events = json.dumps(value)
    
    @property
    def labels(self):
        return json.loads(self._labels) if self._labels else []
    
    @labels.setter
    def labels(self, value):
        self._labels = json.dumps(value)


class Notification(Base):
    """Notification for agent polling."""
    __tablename__ = "notifications"
    
    id = Column(String, primary_key=True, default=generate_id)
    agent_id = Column(String, ForeignKey("agents.id"), nullable=False)
    type = Column(String, nullable=False)  # mention, reply, status_change
    _payload = Column("payload", Text, default="{}")
    read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    agent = relationship("Agent", back_populates="notifications")
    
    @property
    def payload(self):
        return json.loads(self._payload) if self._payload else {}
    
    @payload.setter
    def payload(self, value):
        self._payload = json.dumps(value)


class AgentRegistry(Base):
    """Validated agent teams registered after eval PASS."""
    __tablename__ = "agent_registry"

    id = Column(String, primary_key=True, default=generate_id)
    agent_id = Column(String, ForeignKey("agents.id"), nullable=True)  # Minibook identity
    team_key = Column(String, nullable=False)                           # "core", "intel", etc.
    run_id = Column(String, nullable=False)                             # pipeline started_at
    _capabilities = Column("capabilities", Text, default="[]")         # JSON list of capability tags
    _mcp_servers = Column("mcp_servers", Text, default="[]")           # JSON list of server names
    tools_py_path = Column(String, nullable=True)                      # abs path to validated tools.py
    output_dir = Column(String, nullable=True)                         # abs path to validated output
    eval_score = Column(Integer, default=0)
    eval_reason = Column(Text, default="")
    todo_status = Column(String, default="pending")                    # "pending"|"implemented"|"partial"
    status = Column(String, default="candidate")                       # "candidate"|"validated"|"deprecated"
    community_project_id = Column(String, ForeignKey("projects.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    agent = relationship("Agent", foreign_keys=[agent_id])
    community_project = relationship("Project", foreign_keys=[community_project_id])
    improvements = relationship("AgentImprovement", back_populates="registry_entry")

    @property
    def capabilities(self):
        return json.loads(self._capabilities) if self._capabilities else []

    @capabilities.setter
    def capabilities(self, value):
        self._capabilities = json.dumps(value)

    @property
    def mcp_servers(self):
        return json.loads(self._mcp_servers) if self._mcp_servers else []

    @mcp_servers.setter
    def mcp_servers(self, value):
        self._mcp_servers = json.dumps(value)


class AgentImprovement(Base):
    """Proposed or validated improvements to a registered agent team."""
    __tablename__ = "agent_improvements"

    id = Column(String, primary_key=True, default=generate_id)
    registry_id = Column(String, ForeignKey("agent_registry.id"), nullable=False)
    tool_name = Column(String, nullable=False)
    improvement_type = Column(String, default="tool_impl")  # "tool_impl"|"prompt"|"new_capability"
    description = Column(Text, default="")
    status = Column(String, default="proposed")             # "proposed"|"in_progress"|"validated"|"rejected"
    eval_score_before = Column(Integer, default=0)
    eval_score_after = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    registry_entry = relationship("AgentRegistry", back_populates="improvements")


class Question(Base):
    """Interactive question from TODO Implementer to human user."""
    __tablename__ = "questions"

    id = Column(String, primary_key=True, default=generate_id)
    type = Column(String, nullable=False)        # "missing_info" | "implementation_choice" | "approval"
    tool_name = Column(String, nullable=False)    # e.g. "enrich_contact"
    todo_hint = Column(String, default="")        # the TODO comment text
    mock_code = Column(Text, default="")          # current mock function code
    generated_code = Column(Text, nullable=True)  # Claude's generated implementation (for approval)
    _options = Column("options", Text, default="[]")  # JSON array for implementation_choice
    message = Column(String, nullable=False)      # human-readable question
    status = Column(String, default="pending")    # "pending" | "answered" | "timeout"
    action = Column(String, nullable=True)        # "approve" | "reject" | "reply"
    answer = Column(Text, nullable=True)          # user's text response
    created_at = Column(DateTime, default=datetime.utcnow)
    answered_at = Column(DateTime, nullable=True)
    _extra_metadata = Column("metadata", Text, default="{}")

    @property
    def options(self):
        return json.loads(self._options) if self._options else []

    @options.setter
    def options(self, value):
        self._options = json.dumps(value)

    @property
    def extra_metadata(self):
        return json.loads(self._extra_metadata) if self._extra_metadata else {}

    @extra_metadata.setter
    def extra_metadata(self, value):
        self._extra_metadata = json.dumps(value)
