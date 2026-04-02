"""
Project Context - Shared context for all parallel agents.

This module provides:
1. Project-level configuration and architecture decisions
2. Shared types and interfaces
3. File ownership mapping (which agent owns which files)
4. Integration points between agents
"""
import json
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

from src.engine.dag_parser import RequirementsData, NodeType
from src.engine.slicer import SliceManifest, TaskSlice


@dataclass
class TechnologyStack:
    """Technology choices for the project."""
    language: str = "python"
    framework: str = "fastapi"
    frontend_framework: Optional[str] = "react"
    database: str = "postgresql"
    styling: str = "tailwind"
    testing: str = "pytest"

    def to_dict(self) -> dict:
        return {
            "language": self.language,
            "framework": self.framework,
            "frontend_framework": self.frontend_framework,
            "database": self.database,
            "styling": self.styling,
            "testing": self.testing,
        }


@dataclass
class FileOwnership:
    """Tracks which agent type owns which file patterns."""
    frontend: list[str] = field(default_factory=lambda: [
        "src/components/**",
        "src/pages/**",
        "src/styles/**",
        "src/hooks/**",
        "*.tsx", "*.jsx", "*.css",
    ])
    backend: list[str] = field(default_factory=lambda: [
        "src/api/**",
        "src/models/**",
        "src/services/**",
        "src/utils/**",
        "*.py",
    ])
    testing: list[str] = field(default_factory=lambda: [
        "tests/**",
        "*_test.py",
        "*.test.ts",
    ])
    devops: list[str] = field(default_factory=lambda: [
        "Dockerfile*",
        "docker-compose*.yml",
        ".github/**",
        "k8s/**",
        "infra/**",
    ])
    security: list[str] = field(default_factory=lambda: [
        "SECURITY.md",
        "security/**",
    ])


@dataclass
class SharedInterfaces:
    """Shared types and interfaces that all agents should know about."""
    # Data models that multiple agents need
    models: list[dict] = field(default_factory=list)
    # API endpoints that frontend needs to know
    api_endpoints: list[dict] = field(default_factory=list)
    # Shared constants
    constants: dict = field(default_factory=dict)


@dataclass
class ProjectContext:
    """
    Complete project context shared with all agents.

    This ensures:
    1. All agents understand the project architecture
    2. No file conflicts between parallel agents
    3. Consistent technology choices
    4. Proper integration points
    """
    # Project identity
    project_name: str
    project_description: str

    # Technology stack
    tech_stack: TechnologyStack = field(default_factory=TechnologyStack)

    # File ownership
    file_ownership: FileOwnership = field(default_factory=FileOwnership)

    # Shared interfaces
    shared: SharedInterfaces = field(default_factory=SharedInterfaces)

    # What's being worked on (for context)
    all_slices: list[dict] = field(default_factory=list)
    current_slice: Optional[dict] = None

    # Directory structure
    directory_structure: dict = field(default_factory=lambda: {
        "src/": "Source code",
        "src/api/": "API endpoints and routes",
        "src/models/": "Database models",
        "src/services/": "Business logic",
        "src/components/": "React components",
        "src/pages/": "Page components",
        "tests/": "Test files",
        "infra/": "Infrastructure configs",
    })

    def to_prompt_context(self, for_agent: str, slice: TaskSlice) -> str:
        """Generate context string for agent prompt."""
        context = f"""
## Project Context

**Project:** {self.project_name}
**Description:** {self.project_description}

### Technology Stack
- Language: {self.tech_stack.language}
- Backend Framework: {self.tech_stack.framework}
- Frontend Framework: {self.tech_stack.frontend_framework or 'N/A'}
- Database: {self.tech_stack.database}
- Styling: {self.tech_stack.styling}
- Testing: {self.tech_stack.testing}

### Your Role: {for_agent.upper()} Agent
You are responsible for files matching these patterns:
{self._get_ownership_patterns(for_agent)}

### Directory Structure
```
{self._format_directory_structure()}
```

### Other Work in Progress
The following slices are being worked on in parallel:
{self._format_other_slices(slice)}

### Integration Notes
- Use consistent naming conventions
- Export shared types from src/types/
- API endpoints follow REST conventions at /api/v1/
- All components should be TypeScript with proper types

### Your Current Task
Slice: {slice.slice_id}
Agent Type: {slice.agent_type}
Requirements to implement:
{self._format_requirements(slice)}
"""
        return context

    def _get_ownership_patterns(self, agent_type: str) -> str:
        ownership = getattr(self.file_ownership, agent_type, [])
        if ownership:
            return "\n".join(f"  - {p}" for p in ownership)
        return "  - General files"

    def _format_directory_structure(self) -> str:
        lines = []
        for path, desc in self.directory_structure.items():
            lines.append(f"{path:<20} # {desc}")
        return "\n".join(lines)

    def _format_other_slices(self, current: TaskSlice) -> str:
        lines = []
        for s in self.all_slices:
            if s["slice_id"] != current.slice_id:
                lines.append(f"  - [{s['agent_type']}] {s['slice_id']}: {len(s.get('requirements', []))} requirements")
        return "\n".join(lines[:10]) if lines else "  (none)"

    def _format_requirements(self, slice: TaskSlice) -> str:
        lines = []
        for req in slice.requirement_details:
            lines.append(f"  - [{req.get('id') or req.get('req_id', '')}] {req.get('title', req.get('description', ''))}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "project_name": self.project_name,
            "project_description": self.project_description,
            "tech_stack": self.tech_stack.to_dict(),
            "directory_structure": self.directory_structure,
            "all_slices": self.all_slices,
        }


def create_project_context(
    req_data: RequirementsData,
    manifest: SliceManifest,
    project_name: Optional[str] = None,
) -> ProjectContext:
    """
    Create project context from requirements and manifest.

    Analyzes requirements to determine:
    - Project name and description
    - Technology stack (from requirement keywords)
    - Integration points
    """
    # Extract project info from requirements
    if not project_name:
        # Try to infer from first requirement
        if req_data.requirements:
            first_req = req_data.requirements[0].get("title", "")
            # Extract key terms
            project_name = "Generated Project"
            if "desktop application" in first_req.lower():
                project_name = "Desktop Application"
            elif "web" in first_req.lower():
                project_name = "Web Application"
            elif "api" in first_req.lower():
                project_name = "API Service"

    # Build description from requirements
    description_parts = []
    for req in req_data.requirements[:5]:
        description_parts.append(req.get("title", ""))
    description = " ".join(description_parts)[:500]

    # Determine tech stack from requirements
    tech_stack = _infer_tech_stack(req_data)

    # Create slice summaries
    all_slices = [
        {
            "slice_id": s.slice_id,
            "agent_type": s.agent_type,
            "requirements": s.requirements,
            "depth": s.depth,
        }
        for s in manifest.slices
    ]

    return ProjectContext(
        project_name=project_name or "Generated Project",
        project_description=description,
        tech_stack=tech_stack,
        all_slices=all_slices,
    )


def _infer_tech_stack(req_data: RequirementsData) -> TechnologyStack:
    """Infer technology stack from requirement keywords."""
    all_text = " ".join(
        r.get("title", "").lower()
        for r in req_data.requirements
    )

    # Detect language
    language = "python"
    if "typescript" in all_text or "react" in all_text:
        language = "typescript"
    elif "rust" in all_text:
        language = "rust"
    elif "go " in all_text or "golang" in all_text:
        language = "go"

    # Detect framework
    framework = "fastapi"
    if "django" in all_text:
        framework = "django"
    elif "express" in all_text or "node" in all_text:
        framework = "express"

    # Detect frontend
    frontend = None
    if "react" in all_text:
        frontend = "react"
    elif "vue" in all_text:
        frontend = "vue"
    elif "svelte" in all_text:
        frontend = "svelte"
    elif "desktop" in all_text or "overlay" in all_text:
        frontend = "electron"  # Desktop apps

    # Detect database
    database = "postgresql"
    if "mongodb" in all_text or "mongo" in all_text:
        database = "mongodb"
    elif "sqlite" in all_text:
        database = "sqlite"

    return TechnologyStack(
        language=language,
        framework=framework,
        frontend_framework=frontend,
        database=database,
    )
