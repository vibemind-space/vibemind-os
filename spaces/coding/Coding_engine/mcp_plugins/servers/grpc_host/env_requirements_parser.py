#!/usr/bin/env python3
"""
Environment Requirements Parser - Phase 3.6

Erkennt benoetigte Environment-Variablen aus Projekt-Specs.

Features:
- Analysiert API-Docs fuer Auth/Storage Patterns
- Analysiert Entities fuer Database Requirements
- Erkennt Patterns wie process.env.XYZ
- Generiert .env.example Template
"""

import re
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class EnvVarType(Enum):
    """Types of environment variables"""
    SECRET = "secret"               # Sensitive (JWT_SECRET, API_KEY)
    CONNECTION_STRING = "connection_string"  # DATABASE_URL, REDIS_URL
    CONFIG = "config"               # Non-sensitive config (PORT, HOST)
    FEATURE_FLAG = "feature_flag"   # Feature toggles
    EXTERNAL_API = "external_api"   # Third-party API keys


@dataclass
class EnvRequirement:
    """Single environment variable requirement"""
    name: str                       # DATABASE_URL
    type: EnvVarType               # connection_string
    source: str                     # "api_documentation.md:Auth endpoints"
    required: bool = True
    default_value: Optional[str] = None
    description: str = ""
    user_input_needed: bool = False # True wenn kein Default
    example_value: Optional[str] = None
    validation_pattern: Optional[str] = None


class EnvRequirementsParser:
    """
    Erkennt benoetigte Environment-Variablen aus Projekt-Specs.

    Analysiert:
    - api_documentation.md: Auth patterns -> JWT_SECRET
    - data_dictionary.md: Entities -> DATABASE_URL
    - user_stories.md: Features -> Feature-specific env vars
    """

    # Patterns die auf bestimmte Env-Vars hinweisen
    ENV_DETECTION_PATTERNS = {
        "JWT_SECRET": {
            "keywords": ["auth", "login", "token", "bearer", "jwt", "authentication"],
            "type": EnvVarType.SECRET,
            "required": True,
            "description": "Secret key for JWT token signing",
            "example": "your-super-secret-jwt-key-min-32-chars",
            "user_input": True,
        },
        "DATABASE_URL": {
            "keywords": ["prisma", "postgres", "entity", "model", "database", "sql"],
            "type": EnvVarType.CONNECTION_STRING,
            "required": True,
            "description": "PostgreSQL connection string",
            "example": "postgresql://user:password@localhost:5432/dbname",
            "user_input": True,
        },
        "REDIS_URL": {
            "keywords": ["cache", "session", "queue", "redis", "pub/sub"],
            "type": EnvVarType.CONNECTION_STRING,
            "required": False,
            "description": "Redis connection string for caching",
            "example": "redis://localhost:6379",
            "user_input": True,
        },
        "SMTP_HOST": {
            "keywords": ["email", "mail", "notification", "verify", "smtp"],
            "type": EnvVarType.CONFIG,
            "required": False,
            "description": "SMTP server host for emails",
            "example": "smtp.gmail.com",
            "user_input": True,
        },
        "SMTP_USER": {
            "keywords": ["email", "mail", "smtp"],
            "type": EnvVarType.SECRET,
            "required": False,
            "description": "SMTP username",
            "user_input": True,
        },
        "SMTP_PASSWORD": {
            "keywords": ["email", "mail", "smtp"],
            "type": EnvVarType.SECRET,
            "required": False,
            "description": "SMTP password",
            "user_input": True,
        },
        "S3_BUCKET": {
            "keywords": ["media", "upload", "file", "storage", "s3", "aws"],
            "type": EnvVarType.CONFIG,
            "required": False,
            "description": "AWS S3 bucket name",
            "user_input": True,
        },
        "S3_ACCESS_KEY": {
            "keywords": ["media", "upload", "s3", "aws"],
            "type": EnvVarType.SECRET,
            "required": False,
            "description": "AWS S3 access key",
            "user_input": True,
        },
        "S3_SECRET_KEY": {
            "keywords": ["media", "upload", "s3", "aws"],
            "type": EnvVarType.SECRET,
            "required": False,
            "description": "AWS S3 secret key",
            "user_input": True,
        },
        "STRIPE_SECRET_KEY": {
            "keywords": ["payment", "billing", "subscription", "stripe", "checkout"],
            "type": EnvVarType.SECRET,
            "required": False,
            "description": "Stripe secret API key",
            "user_input": True,
        },
        "STRIPE_WEBHOOK_SECRET": {
            "keywords": ["payment", "stripe", "webhook"],
            "type": EnvVarType.SECRET,
            "required": False,
            "description": "Stripe webhook signing secret",
            "user_input": True,
        },
        "TWILIO_ACCOUNT_SID": {
            "keywords": ["sms", "phone", "otp", "twilio", "verification"],
            "type": EnvVarType.CONFIG,
            "required": False,
            "description": "Twilio Account SID",
            "user_input": True,
        },
        "TWILIO_AUTH_TOKEN": {
            "keywords": ["sms", "phone", "otp", "twilio"],
            "type": EnvVarType.SECRET,
            "required": False,
            "description": "Twilio Auth Token",
            "user_input": True,
        },
        "OPENAI_API_KEY": {
            "keywords": ["ai", "gpt", "openai", "chat", "assistant", "llm"],
            "type": EnvVarType.SECRET,
            "required": False,
            "description": "OpenAI API key",
            "user_input": True,
        },
        "GOOGLE_CLIENT_ID": {
            "keywords": ["oauth", "google", "social login", "google auth"],
            "type": EnvVarType.CONFIG,
            "required": False,
            "description": "Google OAuth client ID",
            "user_input": True,
        },
        "GOOGLE_CLIENT_SECRET": {
            "keywords": ["oauth", "google", "social login"],
            "type": EnvVarType.SECRET,
            "required": False,
            "description": "Google OAuth client secret",
            "user_input": True,
        },
    }

    # Standard config vars (always needed)
    STANDARD_CONFIG = {
        "NODE_ENV": {
            "type": EnvVarType.CONFIG,
            "required": True,
            "default": "development",
            "description": "Node environment (development, production, test)",
            "user_input": False,
        },
        "PORT": {
            "type": EnvVarType.CONFIG,
            "required": True,
            "default": "3000",
            "description": "Server port",
            "user_input": False,
        },
        "API_URL": {
            "type": EnvVarType.CONFIG,
            "required": True,
            "default": "http://localhost:3000",
            "description": "Backend API URL",
            "user_input": False,
        },
        "FRONTEND_URL": {
            "type": EnvVarType.CONFIG,
            "required": True,
            "default": "http://localhost:5173",
            "description": "Frontend URL (for CORS)",
            "user_input": False,
        },
    }

    def __init__(self, project_path: str):
        """
        Args:
            project_path: Path to the project directory
        """
        self.project_path = Path(project_path)
        self._detected_keywords: Set[str] = set()
        self._requirements: List[EnvRequirement] = []
        self._parsed = False

        logger.info(f"EnvRequirementsParser initialized for: {project_path}")

    def detect_required_env_vars(self) -> List[EnvRequirement]:
        """
        Analysiert Projekt und erkennt benoetigte Env-Vars.

        Returns:
            List of detected environment variable requirements
        """
        if self._parsed:
            return self._requirements

        self._requirements = []

        # 1. Add standard config vars
        for name, config in self.STANDARD_CONFIG.items():
            self._requirements.append(EnvRequirement(
                name=name,
                type=config["type"],
                source="Standard config",
                required=config["required"],
                default_value=config.get("default"),
                description=config["description"],
                user_input_needed=config["user_input"],
            ))

        # 2. Analyze API documentation
        self._analyze_api_documentation()

        # 3. Analyze data dictionary
        self._analyze_data_dictionary()

        # 4. Analyze user stories
        self._analyze_user_stories()

        # 5. Dedupe and finalize
        self._requirements = self._dedupe_requirements(self._requirements)
        self._parsed = True

        logger.info(f"Detected {len(self._requirements)} environment variables")
        return self._requirements

    def _analyze_api_documentation(self):
        """Analyze api_documentation.md for env var patterns"""
        api_doc_path = self.project_path / "api" / "api_documentation.md"

        if not api_doc_path.exists():
            logger.warning(f"API documentation not found: {api_doc_path}")
            return

        content = api_doc_path.read_text(encoding="utf-8").lower()
        self._detect_patterns_in_content(content, "api_documentation.md")

    def _analyze_data_dictionary(self):
        """Analyze data_dictionary.md for database patterns"""
        data_dict_path = self.project_path / "data" / "data_dictionary.md"

        if not data_dict_path.exists():
            logger.warning(f"Data dictionary not found: {data_dict_path}")
            return

        content = data_dict_path.read_text(encoding="utf-8").lower()
        self._detect_patterns_in_content(content, "data_dictionary.md")

        # Always need DATABASE_URL if entities exist
        if "entity" in content or "model" in content or "table" in content:
            self._add_requirement_if_not_exists("DATABASE_URL", "data_dictionary.md: Entities detected")

    def _analyze_user_stories(self):
        """Analyze user_stories.md for feature-specific env vars"""
        user_stories_path = self.project_path / "user_stories" / "user_stories.md"

        if not user_stories_path.exists():
            logger.warning(f"User stories not found: {user_stories_path}")
            return

        content = user_stories_path.read_text(encoding="utf-8").lower()
        self._detect_patterns_in_content(content, "user_stories.md")

    def _detect_patterns_in_content(self, content: str, source: str):
        """Detect env var patterns in content"""
        for env_var, config in self.ENV_DETECTION_PATTERNS.items():
            for keyword in config["keywords"]:
                if keyword in content:
                    self._detected_keywords.add(keyword)
                    self._add_requirement_if_not_exists(env_var, f"{source}: '{keyword}' detected")
                    break

    def _add_requirement_if_not_exists(self, env_var: str, source: str):
        """Add requirement if not already in list"""
        if any(r.name == env_var for r in self._requirements):
            return

        config = self.ENV_DETECTION_PATTERNS.get(env_var)
        if not config:
            return

        self._requirements.append(EnvRequirement(
            name=env_var,
            type=config["type"],
            source=source,
            required=config.get("required", False),
            description=config.get("description", ""),
            user_input_needed=config.get("user_input", True),
            example_value=config.get("example"),
        ))

    def _dedupe_requirements(self, requirements: List[EnvRequirement]) -> List[EnvRequirement]:
        """Remove duplicate requirements, keeping most complete version"""
        seen = {}
        for req in requirements:
            if req.name not in seen:
                seen[req.name] = req
            else:
                # Keep the one with more info
                existing = seen[req.name]
                if req.user_input_needed and not existing.user_input_needed:
                    seen[req.name] = req
        return list(seen.values())

    def get_secrets_requiring_input(self) -> List[EnvRequirement]:
        """Get only the secrets that require user input"""
        if not self._parsed:
            self.detect_required_env_vars()

        return [r for r in self._requirements if r.user_input_needed and r.type == EnvVarType.SECRET]

    def get_config_vars(self) -> List[EnvRequirement]:
        """Get non-secret config variables"""
        if not self._parsed:
            self.detect_required_env_vars()

        return [r for r in self._requirements if r.type == EnvVarType.CONFIG]

    def generate_env_template(self) -> str:
        """
        Generate .env.example content.

        Returns:
            .env.example file content
        """
        if not self._parsed:
            self.detect_required_env_vars()

        lines = [
            "# Environment Variables",
            "# Generated by Coding Engine",
            "#",
            "# Copy this file to .env and fill in the values",
            "",
        ]

        # Group by type
        by_type = {}
        for req in self._requirements:
            type_name = req.type.value
            if type_name not in by_type:
                by_type[type_name] = []
            by_type[type_name].append(req)

        # Output by type
        for type_name, reqs in by_type.items():
            lines.append(f"# === {type_name.upper().replace('_', ' ')} ===")
            for req in reqs:
                if req.description:
                    lines.append(f"# {req.description}")
                if req.default_value:
                    lines.append(f"{req.name}={req.default_value}")
                elif req.example_value:
                    lines.append(f"# {req.name}={req.example_value}")
                    lines.append(f"{req.name}=")
                else:
                    lines.append(f"{req.name}=")
            lines.append("")

        return "\n".join(lines)

    def generate_user_prompts(self) -> List[Dict[str, str]]:
        """
        Generate prompts for user input.

        Returns:
            List of prompts for secrets requiring user input
        """
        secrets = self.get_secrets_requiring_input()

        prompts = []
        for secret in secrets:
            prompts.append({
                "env_var": secret.name,
                "prompt": f"Please enter {secret.name}:\n{secret.description}",
                "example": secret.example_value or "",
                "required": secret.required,
            })

        return prompts

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of detected environment requirements"""
        if not self._parsed:
            self.detect_required_env_vars()

        return {
            "total": len(self._requirements),
            "secrets": len([r for r in self._requirements if r.type == EnvVarType.SECRET]),
            "connection_strings": len([r for r in self._requirements if r.type == EnvVarType.CONNECTION_STRING]),
            "config": len([r for r in self._requirements if r.type == EnvVarType.CONFIG]),
            "requiring_input": len([r for r in self._requirements if r.user_input_needed]),
            "detected_keywords": list(self._detected_keywords),
        }


# =============================================================================
# Test
# =============================================================================

def test_env_requirements_parser():
    """Test the EnvRequirementsParser"""
    print("=== Environment Requirements Parser Test ===\n")

    # Test project path
    test_path = Path(__file__).parent.parent.parent.parent / "Data" / "all_services" / "unnamed_project_20260204_165411"

    if not test_path.exists():
        print(f"Test project not found: {test_path}")
        return

    parser = EnvRequirementsParser(str(test_path))

    # Test 1: Detect all env vars
    print("1. Detecting required environment variables:")
    requirements = parser.detect_required_env_vars()
    print(f"   Found {len(requirements)} environment variables")

    # Test 2: Summary
    print("\n2. Summary:")
    summary = parser.get_summary()
    for key, value in summary.items():
        print(f"   {key}: {value}")

    # Test 3: Show all detected vars
    print("\n3. All detected variables:")
    for req in requirements:
        user_input = "USER INPUT NEEDED" if req.user_input_needed else "has default"
        print(f"   {req.name}: {req.type.value} - {user_input}")

    # Test 4: Secrets requiring input
    print("\n4. Secrets requiring user input:")
    secrets = parser.get_secrets_requiring_input()
    for secret in secrets:
        print(f"   {secret.name}: {secret.description}")

    # Test 5: Generate .env template
    print("\n5. Generated .env.example (preview):")
    template = parser.generate_env_template()
    print(template[:500] + "...")

    # Test 6: User prompts
    print("\n6. User prompts for secrets:")
    prompts = parser.generate_user_prompts()
    for prompt in prompts[:3]:
        print(f"   - {prompt['env_var']}: {prompt['prompt'][:50]}...")

    print("\n=== Test Complete ===")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_env_requirements_parser()
