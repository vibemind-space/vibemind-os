"""
ClawHub.ai API Client

Fetches skills from ClawHub.ai marketplace. Uses a mock catalog as
fallback when the real API is unavailable or during development.

Architecture:
    ClawHubClient (abstract interface)
    ├── LiveClawHubClient  → real HTTP calls to clawhub.ai
    └── MockClawHubClient  → built-in catalog for offline/dev use

Usage:
    client = get_clawhub_client()
    results = await client.search_skills("browser automation")
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from ..models.skill import (
    SkillCategory,
    SkillDetail,
    SkillPermission,
    SkillSearchResponse,
    SkillSummary,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Abstract Interface
# ============================================================================


class ClawHubClient(ABC):
    """Abstract ClawHub API client."""

    @abstractmethod
    async def search_skills(
        self,
        query: str,
        category: Optional[SkillCategory] = None,
        limit: int = 20,
        offset: int = 0,
        sort_by: str = "relevance",
    ) -> SkillSearchResponse:
        ...

    @abstractmethod
    async def get_skill(self, skill_id: str) -> Optional[SkillDetail]:
        ...

    @abstractmethod
    async def get_categories(self) -> List[Dict[str, int]]:
        ...

    @abstractmethod
    async def get_trending(self, limit: int = 10) -> List[SkillSummary]:
        ...


# ============================================================================
# Live Client (for real ClawHub.ai API)
# ============================================================================


class LiveClawHubClient(ClawHubClient):
    """
    Real ClawHub.ai API client.

    TODO: Implement once ClawHub.ai API documentation is available.
    Currently falls back to MockClawHubClient.
    """

    BASE_URL = "https://clawhub.ai/api"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self._fallback = MockClawHubClient()

    async def search_skills(self, query, category=None, limit=20, offset=0, sort_by="relevance"):
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10) as client:
                params = {"q": query, "limit": limit, "offset": offset, "sort": sort_by}
                if category:
                    params["category"] = category.value
                headers = {}
                if self.api_key:
                    headers["Authorization"] = f"Bearer {self.api_key}"

                resp = await client.get(f"{self.BASE_URL}/skills/search", params=params, headers=headers)

                if resp.status_code == 200:
                    data = resp.json()
                    skills = [SkillSummary(**s) for s in data.get("skills", [])]
                    return SkillSearchResponse(
                        query=query,
                        total=data.get("total", len(skills)),
                        skills=skills,
                        offset=offset,
                        limit=limit,
                    )

                logger.warning(f"ClawHub API returned {resp.status_code}, using mock data")

        except ImportError:
            logger.warning("httpx not installed, using mock data")
        except Exception as e:
            logger.warning(f"ClawHub API unavailable ({e}), using mock data")

        return await self._fallback.search_skills(query, category, limit, offset, sort_by)

    async def get_skill(self, skill_id):
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10) as client:
                headers = {}
                if self.api_key:
                    headers["Authorization"] = f"Bearer {self.api_key}"

                resp = await client.get(f"{self.BASE_URL}/skills/{skill_id}", headers=headers)
                if resp.status_code == 200:
                    return SkillDetail(**resp.json())

        except Exception as e:
            logger.warning(f"ClawHub API skill fetch failed ({e}), using mock data")

        return await self._fallback.get_skill(skill_id)

    async def get_categories(self):
        return await self._fallback.get_categories()

    async def get_trending(self, limit=10):
        return await self._fallback.get_trending(limit)


# ============================================================================
# Mock Client (built-in skill catalog)
# ============================================================================


# Pre-built mock skills representing what ClawHub.ai offers
MOCK_SKILLS: List[SkillDetail] = [
    SkillDetail(
        id="browser-automation",
        name="Browser Automation",
        description="Navigate websites, fill forms, click buttons, extract data from web pages",
        long_description="Full browser automation suite using Playwright. Supports navigation, form filling, data extraction, screenshot capture, and multi-tab management.",
        version="2.1.0",
        author="openclaw",
        category=SkillCategory.BROWSER,
        tags=["browser", "web", "scraping", "playwright", "automation"],
        install_count=8432,
        rating=4.7,
        icon="globe",
        permissions=[SkillPermission.NETWORK, SkillPermission.BROWSER, SkillPermission.SCREENSHOT],
        parameters={
            "url": {"type": "string", "description": "Target URL", "required": True},
            "action": {"type": "string", "description": "Action to perform", "enum": ["navigate", "click", "fill", "extract", "screenshot"]},
        },
        created_at=datetime.utcnow() - timedelta(days=180),
        updated_at=datetime.utcnow() - timedelta(days=5),
    ),
    SkillDetail(
        id="file-organizer",
        name="File Organizer",
        description="Automatically sort, rename, and organize files by type, date, or custom rules",
        long_description="Smart file organization using pattern matching and rules. Supports date-based sorting, extension-based categorization, duplicate detection, and batch renaming.",
        version="1.4.2",
        author="community",
        category=SkillCategory.FILE_MANAGEMENT,
        tags=["files", "organize", "cleanup", "rename", "sort"],
        install_count=5621,
        rating=4.5,
        icon="folder",
        permissions=[SkillPermission.FILESYSTEM],
        parameters={
            "directory": {"type": "string", "description": "Target directory", "required": True},
            "strategy": {"type": "string", "description": "Organization strategy", "enum": ["by_type", "by_date", "by_size", "custom"]},
        },
        created_at=datetime.utcnow() - timedelta(days=120),
        updated_at=datetime.utcnow() - timedelta(days=15),
    ),
    SkillDetail(
        id="github-manager",
        name="GitHub Manager",
        description="Manage repos, create PRs, review code, handle issues via natural language",
        long_description="Complete GitHub workflow automation. Create branches, commit changes, open pull requests, manage issues, and review code - all through natural language commands.",
        version="3.0.1",
        author="openclaw",
        category=SkillCategory.DEVELOPMENT,
        tags=["github", "git", "pr", "code-review", "issues", "dev"],
        install_count=12450,
        rating=4.8,
        icon="git-branch",
        permissions=[SkillPermission.NETWORK, SkillPermission.SHELL, SkillPermission.FILESYSTEM],
        parameters={
            "command": {"type": "string", "description": "GitHub command", "required": True},
            "repo": {"type": "string", "description": "Repository (owner/name)"},
        },
        created_at=datetime.utcnow() - timedelta(days=300),
        updated_at=datetime.utcnow() - timedelta(days=2),
    ),
    SkillDetail(
        id="screenshot-ocr",
        name="Screenshot & OCR",
        description="Capture screenshots, extract text, analyze screen content with AI",
        long_description="Advanced screen capture with OCR and AI analysis. Supports region selection, multi-monitor capture, text extraction in multiple languages, and content summarization.",
        version="1.8.0",
        author="openclaw",
        category=SkillCategory.DESKTOP,
        tags=["screenshot", "ocr", "screen", "text-extraction", "vision"],
        install_count=7890,
        rating=4.6,
        icon="camera",
        permissions=[SkillPermission.SCREENSHOT, SkillPermission.OCR, SkillPermission.DESKTOP_CONTROL],
        parameters={
            "action": {"type": "string", "description": "Action", "enum": ["capture", "ocr", "analyze"]},
            "region": {"type": "object", "description": "Screen region (optional)"},
        },
        created_at=datetime.utcnow() - timedelta(days=200),
        updated_at=datetime.utcnow() - timedelta(days=10),
    ),
    SkillDetail(
        id="email-assistant",
        name="Email Assistant",
        description="Draft, send, and manage emails with AI-powered composition",
        long_description="Smart email management with AI composition. Draft professional emails, manage inbox, schedule sends, create templates, and handle attachments.",
        version="2.0.0",
        author="community",
        category=SkillCategory.COMMUNICATION,
        tags=["email", "draft", "send", "inbox", "templates"],
        install_count=4320,
        rating=4.3,
        icon="mail",
        permissions=[SkillPermission.NETWORK],
        parameters={
            "action": {"type": "string", "description": "Email action", "enum": ["draft", "send", "list", "search"]},
            "to": {"type": "string", "description": "Recipient email"},
            "subject": {"type": "string", "description": "Email subject"},
        },
        created_at=datetime.utcnow() - timedelta(days=90),
        updated_at=datetime.utcnow() - timedelta(days=20),
    ),
    SkillDetail(
        id="data-scraper",
        name="Data Scraper",
        description="Extract structured data from websites, APIs, and documents",
        long_description="Powerful data extraction toolkit. Scrape websites with CSS selectors, consume REST APIs, parse PDFs and CSVs, and export to multiple formats.",
        version="1.5.3",
        author="community",
        category=SkillCategory.DATA,
        tags=["scraping", "data", "extract", "api", "csv", "json"],
        install_count=6780,
        rating=4.4,
        icon="database",
        permissions=[SkillPermission.NETWORK, SkillPermission.FILESYSTEM],
        parameters={
            "source": {"type": "string", "description": "URL or file path", "required": True},
            "format": {"type": "string", "description": "Output format", "enum": ["json", "csv", "markdown"]},
        },
        created_at=datetime.utcnow() - timedelta(days=150),
        updated_at=datetime.utcnow() - timedelta(days=8),
    ),
    SkillDetail(
        id="shell-commander",
        name="Shell Commander",
        description="Execute shell commands safely with output capture and error handling",
        long_description="Safe shell execution with sandboxing, output capture, and command chaining. Supports bash, PowerShell, and cmd with automatic OS detection.",
        version="1.2.0",
        author="openclaw",
        category=SkillCategory.SYSTEM,
        tags=["shell", "bash", "powershell", "cmd", "terminal"],
        install_count=9100,
        rating=4.5,
        icon="terminal",
        permissions=[SkillPermission.SHELL],
        parameters={
            "command": {"type": "string", "description": "Shell command", "required": True},
            "shell": {"type": "string", "description": "Shell type", "enum": ["auto", "bash", "powershell", "cmd"]},
        },
        created_at=datetime.utcnow() - timedelta(days=250),
        updated_at=datetime.utcnow() - timedelta(days=3),
    ),
    SkillDetail(
        id="smart-home",
        name="Smart Home Control",
        description="Control smart home devices - lights, thermostats, locks, cameras",
        long_description="Universal smart home control via Home Assistant, Tuya, and Philips Hue APIs. Manage lights, thermostats, locks, cameras, and automations with natural language.",
        version="1.1.0",
        author="community",
        category=SkillCategory.AUTOMATION,
        tags=["smart-home", "iot", "lights", "thermostat", "home-assistant"],
        install_count=3200,
        rating=4.2,
        icon="home",
        permissions=[SkillPermission.NETWORK],
        parameters={
            "device": {"type": "string", "description": "Device name or ID", "required": True},
            "action": {"type": "string", "description": "Action", "enum": ["on", "off", "toggle", "set", "status"]},
            "value": {"type": "string", "description": "Value for 'set' action"},
        },
        created_at=datetime.utcnow() - timedelta(days=60),
        updated_at=datetime.utcnow() - timedelta(days=25),
    ),
    SkillDetail(
        id="text-transformer",
        name="Text Transformer",
        description="Transform, translate, summarize, and format text with AI",
        long_description="AI-powered text processing. Translate between languages, summarize long documents, reformat text, fix grammar, and convert between formats (markdown, HTML, plain text).",
        version="2.3.0",
        author="openclaw",
        category=SkillCategory.AI_ML,
        tags=["text", "translate", "summarize", "format", "ai", "nlp"],
        install_count=11200,
        rating=4.7,
        icon="type",
        permissions=[SkillPermission.NETWORK, SkillPermission.CLIPBOARD],
        parameters={
            "text": {"type": "string", "description": "Input text", "required": True},
            "action": {"type": "string", "description": "Transform action", "enum": ["translate", "summarize", "reformat", "fix_grammar"]},
            "target_lang": {"type": "string", "description": "Target language for translation"},
        },
        created_at=datetime.utcnow() - timedelta(days=100),
        updated_at=datetime.utcnow() - timedelta(days=1),
    ),
    SkillDetail(
        id="desktop-macro",
        name="Desktop Macro Recorder",
        description="Record and replay desktop actions - clicks, keystrokes, mouse movements",
        long_description="Record desktop interactions and replay them as automated macros. Supports click recording, keystroke capture, mouse movement tracking, conditional pauses, and loop execution.",
        version="1.6.0",
        author="openclaw",
        category=SkillCategory.DESKTOP,
        tags=["macro", "record", "replay", "mouse", "keyboard", "automation"],
        install_count=6540,
        rating=4.4,
        icon="play-circle",
        permissions=[SkillPermission.DESKTOP_CONTROL, SkillPermission.SCREENSHOT],
        parameters={
            "action": {"type": "string", "description": "Macro action", "enum": ["record", "replay", "list", "delete"]},
            "macro_name": {"type": "string", "description": "Name of the macro"},
            "repeat": {"type": "integer", "description": "Number of times to replay"},
        },
        created_at=datetime.utcnow() - timedelta(days=140),
        updated_at=datetime.utcnow() - timedelta(days=12),
    ),
]


class MockClawHubClient(ClawHubClient):
    """Mock client with built-in skill catalog for development."""

    def __init__(self):
        self._skills = {s.id: s for s in MOCK_SKILLS}

    async def search_skills(self, query, category=None, limit=20, offset=0, sort_by="relevance"):
        query_lower = query.lower()
        results = []

        for skill in MOCK_SKILLS:
            # Simple relevance scoring
            score = 0
            if query_lower in skill.name.lower():
                score += 10
            if query_lower in skill.description.lower():
                score += 5
            for tag in skill.tags:
                if query_lower in tag:
                    score += 3

            if category and skill.category != category:
                continue

            if score > 0 or not query.strip():
                results.append((score, skill))

        # Sort
        if sort_by == "rating":
            results.sort(key=lambda x: x[1].rating, reverse=True)
        elif sort_by == "installs":
            results.sort(key=lambda x: x[1].install_count, reverse=True)
        elif sort_by == "newest":
            results.sort(key=lambda x: x[1].created_at or datetime.min, reverse=True)
        else:
            results.sort(key=lambda x: x[0], reverse=True)

        # If no query, return all
        if not query.strip():
            results = [(0, s) for s in MOCK_SKILLS]

        skills = [
            SkillSummary(**s.model_dump(include={
                "id", "name", "description", "version", "author",
                "category", "tags", "install_count", "rating", "icon",
            }))
            for _, s in results[offset:offset + limit]
        ]

        return SkillSearchResponse(
            query=query,
            total=len(results),
            skills=skills,
            offset=offset,
            limit=limit,
        )

    async def get_skill(self, skill_id):
        return self._skills.get(skill_id)

    async def get_categories(self):
        counts: Dict[str, int] = {}
        for skill in MOCK_SKILLS:
            cat = skill.category.value
            counts[cat] = counts.get(cat, 0) + 1
        return [{"category": k, "count": v} for k, v in sorted(counts.items())]

    async def get_trending(self, limit=10):
        sorted_skills = sorted(MOCK_SKILLS, key=lambda s: s.install_count, reverse=True)
        return [
            SkillSummary(**s.model_dump(include={
                "id", "name", "description", "version", "author",
                "category", "tags", "install_count", "rating", "icon",
            }))
            for s in sorted_skills[:limit]
        ]


# ============================================================================
# Singleton
# ============================================================================

_client: Optional[ClawHubClient] = None


def get_clawhub_client(use_live: bool = True, api_key: Optional[str] = None) -> ClawHubClient:
    """Get the ClawHub client singleton."""
    global _client

    if _client is None:
        if use_live:
            _client = LiveClawHubClient(api_key=api_key)
        else:
            _client = MockClawHubClient()
        logger.info(f"ClawHub client initialized: {type(_client).__name__}")

    return _client
