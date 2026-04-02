"""
Tech Stack - Structured representation of project technology stack.

This module provides a structured way to parse and use tech stack configuration
for code generation prompts.
"""
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Any


@dataclass
class TechStackFramework:
    """Frontend or backend framework configuration."""
    name: str
    version: Optional[str] = None
    reason: Optional[str] = None


@dataclass
class TechStackDatabase:
    """Database configuration."""
    name: str
    type: str  # sql, nosql, vector, etc.
    reason: Optional[str] = None


@dataclass
class TechStackStyling:
    """Styling/CSS configuration."""
    framework: str
    approach: Optional[str] = None  # utility-first, component-based, etc.


@dataclass
class TechStack:
    """
    Complete technology stack configuration.
    
    Parsed from tech_stack.json files like:
    {
        "tech_stack": {
            "id": "01-web-app",
            "frontend": {"framework": "React", "version": "18"},
            "backend": {"framework": "FastAPI"},
            "database": {"name": "PostgreSQL", "type": "sql"},
            "styling": {"framework": "Tailwind CSS"},
            "platform": "web"
        }
    }
    """
    id: str = "01-web-app"
    
    # Frontend
    frontend_framework: Optional[str] = None
    frontend_version: Optional[str] = None
    frontend_language: str = "TypeScript"
    
    # Backend
    backend_framework: Optional[str] = None
    backend_language: str = "Python"
    
    # Database
    database_name: Optional[str] = None
    database_type: Optional[str] = None
    
    # Styling
    styling_framework: Optional[str] = None
    styling_approach: Optional[str] = None
    
    # Platform
    platform: str = "web"  # web, desktop, mobile, electron
    
    # Additional technologies
    additional_tools: list[str] = field(default_factory=list)
    
    # Raw data for custom fields
    raw_data: dict = field(default_factory=dict)
    
    @classmethod
    def from_file(cls, file_path: str) -> "TechStack":
        """Load tech stack from a JSON file."""
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)
    
    @classmethod
    def from_dict(cls, data: dict) -> "TechStack":
        """Parse tech stack from a dictionary."""
        # Handle nested tech_stack key
        tech_data = data.get("tech_stack", data)
        
        stack = cls(
            id=tech_data.get("id", "01-web-app"),
            raw_data=data,
        )
        
        # Parse frontend
        frontend = tech_data.get("frontend", {})
        if isinstance(frontend, dict):
            stack.frontend_framework = frontend.get("framework")
            stack.frontend_version = frontend.get("version")
            stack.frontend_language = frontend.get("language", "TypeScript")
        elif isinstance(frontend, str):
            stack.frontend_framework = frontend
        
        # Parse backend
        backend = tech_data.get("backend", {})
        if isinstance(backend, dict):
            stack.backend_framework = backend.get("framework")
            stack.backend_language = backend.get("language", "Python")
        elif isinstance(backend, str):
            stack.backend_framework = backend
        
        # Parse database
        database = tech_data.get("database", {})
        if isinstance(database, dict):
            stack.database_name = database.get("name")
            stack.database_type = database.get("type")
        elif isinstance(database, str):
            stack.database_name = database
        
        # Parse styling
        styling = tech_data.get("styling", {})
        if isinstance(styling, dict):
            stack.styling_framework = styling.get("framework")
            stack.styling_approach = styling.get("approach")
        elif isinstance(styling, str):
            stack.styling_framework = styling
        
        # Parse platform
        stack.platform = tech_data.get("platform", "web")
        
        # Parse additional tools
        tools = tech_data.get("tools", tech_data.get("additional_tools", []))
        if isinstance(tools, list):
            stack.additional_tools = tools
        
        return stack
    
    def to_prompt_context(self) -> str:
        """
        Generate a prompt context section describing the tech stack.
        
        This is used to inject tech stack information into code generation prompts.
        """
        lines = ["## Technology Stack\n"]
        
        # Frontend
        if self.frontend_framework:
            frontend_info = f"**Frontend:** {self.frontend_framework}"
            if self.frontend_version:
                frontend_info += f" v{self.frontend_version}"
            frontend_info += f" ({self.frontend_language})"
            lines.append(frontend_info)
        
        # Backend
        if self.backend_framework:
            lines.append(f"**Backend:** {self.backend_framework} ({self.backend_language})")
        
        # Database
        if self.database_name:
            db_info = f"**Database:** {self.database_name}"
            if self.database_type:
                db_info += f" ({self.database_type})"
            lines.append(db_info)
        
        # Styling
        if self.styling_framework:
            styling_info = f"**Styling:** {self.styling_framework}"
            if self.styling_approach:
                styling_info += f" ({self.styling_approach})"
            lines.append(styling_info)
        
        # Platform
        lines.append(f"**Platform:** {self.platform}")
        
        # Additional tools
        if self.additional_tools:
            lines.append(f"**Additional Tools:** {', '.join(self.additional_tools)}")
        
        lines.append("")
        lines.append("### Important Guidelines:")
        lines.append(self._get_framework_guidelines())
        
        return "\n".join(lines)
    
    def _get_framework_guidelines(self) -> str:
        """Get framework-specific coding guidelines."""
        guidelines = []
        
        # Frontend guidelines
        if self.frontend_framework:
            fw = self.frontend_framework.lower()
            if "react" in fw:
                guidelines.append("- Use React functional components with hooks")
                guidelines.append("- Follow React best practices for state management")
                if self.frontend_language == "TypeScript":
                    guidelines.append("- Define proper TypeScript interfaces for props and state")
            elif "vue" in fw:
                guidelines.append("- Use Vue 3 Composition API")
                guidelines.append("- Follow Vue best practices for reactivity")
            elif "svelte" in fw:
                guidelines.append("- Use Svelte reactive declarations")
            elif "angular" in fw:
                guidelines.append("- Follow Angular module and component structure")
        
        # Backend guidelines
        if self.backend_framework:
            fw = self.backend_framework.lower()
            if "fastapi" in fw:
                guidelines.append("- Use FastAPI dependency injection")
                guidelines.append("- Define Pydantic models for request/response validation")
            elif "express" in fw:
                guidelines.append("- Use Express middleware pattern")
            elif "flask" in fw:
                guidelines.append("- Use Flask blueprints for modular routing")
            elif "django" in fw:
                guidelines.append("- Follow Django's MVT architecture")
        
        # Database guidelines
        if self.database_name:
            db = self.database_name.lower()
            if "postgres" in db:
                guidelines.append("- Use PostgreSQL-specific features where beneficial")
            elif "mongodb" in db or "mongo" in db:
                guidelines.append("- Design MongoDB schemas with embedding vs referencing in mind")
            elif "sqlite" in db:
                guidelines.append("- Keep SQLite queries simple and efficient")
        
        # Styling guidelines
        if self.styling_framework:
            style = self.styling_framework.lower()
            if "tailwind" in style:
                guidelines.append("- Use Tailwind CSS utility classes for styling")
                guidelines.append("- Avoid custom CSS when Tailwind utilities suffice")
            elif "bootstrap" in style:
                guidelines.append("- Use Bootstrap components and grid system")
            elif "material" in style or "mui" in style:
                guidelines.append("- Use Material UI components consistently")
        
        # Platform guidelines
        if self.platform == "electron":
            guidelines.append("- Separate main and renderer process code")
            guidelines.append("- Use IPC for main-renderer communication")
        elif self.platform == "mobile":
            guidelines.append("- Consider mobile-first responsive design")
        
        return "\n".join(guidelines) if guidelines else "- Follow framework best practices"
    
    def get_file_extensions(self) -> dict[str, str]:
        """Get recommended file extensions based on tech stack."""
        extensions = {
            "frontend_component": ".tsx" if self.frontend_language == "TypeScript" else ".jsx",
            "frontend_util": ".ts" if self.frontend_language == "TypeScript" else ".js",
            "backend": ".py" if self.backend_language == "Python" else ".js",
            "style": ".css",
        }
        
        if self.styling_framework:
            style = self.styling_framework.lower()
            if "scss" in style or "sass" in style:
                extensions["style"] = ".scss"
            elif "less" in style:
                extensions["style"] = ".less"
        
        return extensions
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "frontend": {
                "framework": self.frontend_framework,
                "version": self.frontend_version,
                "language": self.frontend_language,
            } if self.frontend_framework else None,
            "backend": {
                "framework": self.backend_framework,
                "language": self.backend_language,
            } if self.backend_framework else None,
            "database": {
                "name": self.database_name,
                "type": self.database_type,
            } if self.database_name else None,
            "styling": {
                "framework": self.styling_framework,
                "approach": self.styling_approach,
            } if self.styling_framework else None,
            "platform": self.platform,
            "additional_tools": self.additional_tools,
        }


def load_tech_stack(file_path: Optional[str]) -> Optional[TechStack]:
    """
    Convenience function to load tech stack from file.
    
    Args:
        file_path: Path to tech_stack.json file, or None
        
    Returns:
        TechStack instance or None if file_path is None or file doesn't exist
    """
    if not file_path:
        return None
    
    path = Path(file_path)
    if not path.exists():
        return None
    
    return TechStack.from_file(str(path))