"""
API Documentation Agent - Autonomous agent for OpenAPI/Swagger documentation generation.

Generates API documentation including:
- OpenAPI 3.0 specification from code
- Swagger UI integration
- Postman collection export
- API changelog generation

Publishes:
- API_DOCS_GENERATION_STARTED: Documentation generation initiated
- API_DOCS_GENERATED: Documentation successfully generated
- OPENAPI_SPEC_CREATED: OpenAPI spec file created
"""

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Optional
from datetime import datetime
import structlog

from ..mind.event_bus import (
    EventBus, Event, EventType,
    api_docs_generation_started_event,
    api_docs_generated_event,
    openapi_spec_created_event,
)
from ..mind.shared_state import SharedState
from ..tools.claude_code_tool import ClaudeCodeTool
from .autonomous_base import AutonomousAgent
from .autogen_team_mixin import AutogenTeamMixin


logger = structlog.get_logger(__name__)


# API route patterns for different frameworks
ROUTE_PATTERNS = {
    "nextjs_app": {
        "pattern": r"export\s+(?:async\s+)?function\s+(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)",
        "file_pattern": r"app/api/.*?/route\.(?:ts|js)",
    },
    "nextjs_pages": {
        "pattern": r"export\s+default\s+(?:async\s+)?function\s+handler",
        "file_pattern": r"pages/api/.*?\.(?:ts|js)",
    },
    "express": {
        "pattern": r"(?:app|router)\.(get|post|put|patch|delete|head|options)\s*\(\s*['\"`]([^'\"`]+)",
        "file_pattern": r".*?\.(?:ts|js)",
    },
    "fastapi": {
        "pattern": r"@(?:app|router)\.(get|post|put|patch|delete)\s*\(\s*['\"`]([^'\"`]+)",
        "file_pattern": r".*?\.py",
    },
    "nestjs": {
        "pattern": r"@(Get|Post|Put|Patch|Delete)\s*\(\s*['\"`]?([^'\"`\)]*)",
        "file_pattern": r".*?\.controller\.ts",
    },
}

# TypeScript type patterns for schema extraction
TYPE_PATTERNS = {
    "interface": r"(?:export\s+)?interface\s+(\w+)\s*\{([^}]+)\}",
    "type": r"(?:export\s+)?type\s+(\w+)\s*=\s*\{([^}]+)\}",
    "zod": r"(?:export\s+)?const\s+(\w+Schema)\s*=\s*z\.object\(\s*\{([^}]+)\}",
}


class APIDocumentationAgent(AutonomousAgent, AutogenTeamMixin):
    """
    Autonomous agent for API documentation generation.

    Triggers on:
    - API_ROUTES_GENERATED: Generate docs after API routes created
    - API_ENDPOINT_CREATED: Update docs when new endpoint added

    Generates:
    - OpenAPI 3.0 specification
    - Swagger UI HTML
    - Postman collection
    """

    def __init__(
        self,
        event_bus: EventBus,
        shared_state: SharedState,
        working_dir: str,
        claude_tool: Optional[ClaudeCodeTool] = None,
        generate_openapi: bool = True,
        generate_swagger_ui: bool = True,
        generate_postman: bool = False,
        api_title: str = "API Documentation",
        api_version: str = "1.0.0",
    ):
        """
        Initialize APIDocumentationAgent.

        Args:
            event_bus: EventBus for pub/sub
            shared_state: SharedState for metrics
            working_dir: Project directory to analyze
            claude_tool: Optional Claude tool for AI-enhanced docs
            generate_openapi: Generate OpenAPI 3.0 spec
            generate_swagger_ui: Generate Swagger UI HTML
            generate_postman: Generate Postman collection
            api_title: Title for the API documentation
            api_version: API version string
        """
        super().__init__(
            name="APIDocumentationAgent",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=working_dir,
        )
        self.working_dir = Path(working_dir)
        self.claude_tool = claude_tool
        self.generate_openapi = generate_openapi
        self.generate_swagger_ui = generate_swagger_ui
        self.generate_postman = generate_postman
        self.api_title = api_title
        self.api_version = api_version

        self._last_generation: Optional[datetime] = None
        self._discovered_routes: list[dict] = []

    @property
    def subscribed_events(self) -> list[EventType]:
        """Events this agent listens for."""
        return [
            EventType.API_ROUTES_GENERATED,
            EventType.API_ENDPOINT_CREATED,
        ]

    async def should_act(self, events: list[Event]) -> bool:
        """
        Determine if agent should act on any event.

        Acts when:
        - API routes were generated
        - New API endpoint was created
        """
        for event in events:
            if event.type not in self.subscribed_events:
                continue

            # Rate limit: Don't regenerate docs more than once per 60 seconds
            if self._last_generation:
                elapsed = (datetime.now() - self._last_generation).total_seconds()
                if elapsed < 60:
                    logger.debug(
                        "api_docs_generation_skipped",
                        reason="rate_limited",
                        seconds_since_last=elapsed,
                    )
                    continue

            return True

        return False

    async def act(self, events: list[Event]) -> None:
        """
        Generate API documentation.

        Uses autogen team if available, falls back to direct generation.
        """
        if self.is_autogen_available() and os.getenv("USE_AUTOGEN_TEAMS", "false").lower() == "true":
            return await self._act_with_autogen_team(events)
        return await self._act_legacy(events)

    async def _act_with_autogen_team(self, events: list[Event]) -> None:
        """Generate API docs using autogen DocsOperator + DocsValidator team."""
        event = next(
            (e for e in events if e.type in self.subscribed_events),
            None
        )
        if not event:
            return

        self._last_generation = datetime.now()

        await self.event_bus.publish(api_docs_generation_started_event(
            source=self.name,
            working_dir=str(self.working_dir),
            trigger=event.type.value,
        ))

        try:
            task = self.build_task_prompt(events, extra_context=f"""
## API Documentation Task

Generate comprehensive API documentation for the project at {self.working_dir}:

1. Discover all API routes (Next.js App Router, Pages Router, Express, NestJS, FastAPI)
2. Extract request/response schemas from TypeScript interfaces and Zod schemas
3. Generate OpenAPI 3.0 spec (docs/openapi.json)
4. Generate Swagger UI HTML (docs/swagger.html)
{"5. Generate Postman collection (docs/postman_collection.json)" if self.generate_postman else ""}

API Title: {self.api_title}
API Version: {self.api_version}
""")

            team = self.create_team(
                operator_name="DocsOperator",
                operator_prompt=f"""You are an API documentation expert.

Your role is to generate comprehensive API documentation:
- Discover API routes across frameworks (Next.js, Express, NestJS, FastAPI)
- Extract TypeScript interfaces, Zod schemas, and Pydantic models
- Generate OpenAPI 3.0 specification with proper schemas
- Create Swagger UI HTML page
- Include request/response examples

API Title: {self.api_title}
API Version: {self.api_version}

When done, say TASK_COMPLETE.""",
                validator_name="DocsValidator",
                validator_prompt="""You are an API documentation validator.

Review the generated API documentation and verify:
1. All discovered routes are documented
2. OpenAPI spec is valid (correct schema structure)
3. Request/response schemas are accurate
4. Path parameters are properly defined
5. HTTP methods and status codes are correct

If the documentation is complete, say TASK_COMPLETE.
If routes are missing or schemas are incorrect, describe the issues.""",
                tool_categories=["filesystem"],
                max_turns=20,
                task=task,
            )

            result = await self.run_team(team, task)

            if result["success"]:
                await self.event_bus.publish(api_docs_generated_event(
                    source=self.name,
                    routes_documented=0,
                    openapi_generated=self.generate_openapi,
                    swagger_ui_generated=self.generate_swagger_ui,
                    postman_generated=self.generate_postman,
                ))
                logger.info("api_docs_generation_complete", mode="autogen")
            else:
                logger.warning("api_docs_generation_issues", mode="autogen",
                               result=result["result_text"][:500])

        except Exception as e:
            logger.error("api_docs_autogen_error", error=str(e))

    async def _act_legacy(self, events: list[Event]) -> None:
        """Generate API docs using direct route scanning (legacy)."""
        event = next(
            (e for e in events if e.type in self.subscribed_events),
            None
        )
        if not event:
            return

        self._last_generation = datetime.now()
        self._discovered_routes = []

        logger.info(
            "api_docs_generation_started",
            working_dir=str(self.working_dir),
            trigger_event=event.type.value,
        )

        await self.event_bus.publish(api_docs_generation_started_event(
            source=self.name,
            working_dir=str(self.working_dir),
            trigger=event.type.value,
        ))

        await self._discover_routes()

        if not self._discovered_routes:
            logger.info("no_api_routes_found")
            return

        if self.generate_openapi:
            await self._generate_openapi_spec()

        if self.generate_swagger_ui:
            await self._generate_swagger_ui()

        if self.generate_postman:
            await self._generate_postman_collection()

        await self.event_bus.publish(api_docs_generated_event(
            source=self.name,
            routes_documented=len(self._discovered_routes),
            openapi_generated=self.generate_openapi,
            swagger_ui_generated=self.generate_swagger_ui,
            postman_generated=self.generate_postman,
        ))

        logger.info(
            "api_docs_generation_complete",
            routes_documented=len(self._discovered_routes),
        )

    async def _discover_routes(self) -> None:
        """Discover API routes in the codebase."""

        # Detect framework and find API files
        api_dirs = [
            self.working_dir / "app" / "api",  # Next.js App Router
            self.working_dir / "pages" / "api",  # Next.js Pages Router
            self.working_dir / "src" / "routes",  # Express/Fastify
            self.working_dir / "src" / "api",  # Generic
            self.working_dir / "src" / "controllers",  # NestJS
            self.working_dir / "api",  # Generic
        ]

        for api_dir in api_dirs:
            if api_dir.exists():
                await self._scan_directory(api_dir)

        logger.info("routes_discovered", count=len(self._discovered_routes))

    async def _scan_directory(self, directory: Path) -> None:
        """Scan a directory for API routes."""

        for file_path in directory.rglob("*"):
            if file_path.is_file() and file_path.suffix in [".ts", ".tsx", ".js", ".jsx", ".py"]:
                await self._extract_routes_from_file(file_path)

    async def _extract_routes_from_file(self, file_path: Path) -> None:
        """Extract API routes from a file."""

        try:
            content = file_path.read_text(encoding="utf-8")
            relative_path = file_path.relative_to(self.working_dir)

            # Detect Next.js App Router routes
            if "app/api" in str(relative_path) and file_path.name == "route.ts":
                await self._extract_nextjs_app_routes(content, relative_path)

            # Detect Next.js Pages Router routes
            elif "pages/api" in str(relative_path):
                await self._extract_nextjs_pages_routes(content, relative_path)

            # Detect Express routes
            elif re.search(r"express|Router\(\)", content):
                await self._extract_express_routes(content, relative_path)

            # Detect NestJS routes
            elif ".controller.ts" in str(file_path):
                await self._extract_nestjs_routes(content, relative_path)

        except Exception as e:
            logger.debug("route_extraction_error", file=str(file_path), error=str(e))

    async def _extract_nextjs_app_routes(self, content: str, file_path: Path) -> None:
        """Extract routes from Next.js App Router files."""

        # Extract path from file location
        path_parts = str(file_path).replace("\\", "/").split("app/api/")
        if len(path_parts) > 1:
            api_path = "/" + path_parts[1].replace("/route.ts", "").replace("/route.js", "")
            # Handle dynamic segments
            api_path = re.sub(r"\[(\w+)\]", r"{\1}", api_path)

            # Find HTTP methods
            methods = re.findall(
                r"export\s+(?:async\s+)?function\s+(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)",
                content
            )

            for method in methods:
                self._discovered_routes.append({
                    "path": api_path,
                    "method": method.lower(),
                    "file": str(file_path),
                    "framework": "nextjs_app",
                    "description": f"{method} {api_path}",
                })

    async def _extract_nextjs_pages_routes(self, content: str, file_path: Path) -> None:
        """Extract routes from Next.js Pages Router files."""

        path_parts = str(file_path).replace("\\", "/").split("pages/api/")
        if len(path_parts) > 1:
            api_path = "/api/" + path_parts[1].replace(".ts", "").replace(".js", "")
            api_path = re.sub(r"\[(\w+)\]", r"{\1}", api_path)

            # Check for method handling in handler
            methods = ["get", "post", "put", "patch", "delete"]
            found_methods = []

            for method in methods:
                if re.search(rf"req\.method\s*===?\s*['\"`]{method}['\"`]", content, re.IGNORECASE):
                    found_methods.append(method)

            # Default to all methods if no specific handling found
            if not found_methods:
                found_methods = ["get", "post"]

            for method in found_methods:
                self._discovered_routes.append({
                    "path": api_path,
                    "method": method,
                    "file": str(file_path),
                    "framework": "nextjs_pages",
                    "description": f"{method.upper()} {api_path}",
                })

    async def _extract_express_routes(self, content: str, file_path: Path) -> None:
        """Extract routes from Express files."""

        pattern = r"(?:app|router)\.(get|post|put|patch|delete)\s*\(\s*['\"`]([^'\"`]+)"
        matches = re.finditer(pattern, content, re.IGNORECASE)

        for match in matches:
            method = match.group(1).lower()
            path = match.group(2)

            # Convert Express params to OpenAPI format
            path = re.sub(r":(\w+)", r"{\1}", path)

            self._discovered_routes.append({
                "path": path,
                "method": method,
                "file": str(file_path),
                "framework": "express",
                "description": f"{method.upper()} {path}",
            })

    async def _extract_nestjs_routes(self, content: str, file_path: Path) -> None:
        """Extract routes from NestJS controller files."""

        # Get controller base path
        controller_match = re.search(r"@Controller\s*\(\s*['\"`]([^'\"`]*)", content)
        base_path = "/" + (controller_match.group(1) if controller_match else "")

        # Find route decorators
        pattern = r"@(Get|Post|Put|Patch|Delete)\s*\(\s*['\"`]?([^'\"`\)]*)"
        matches = re.finditer(pattern, content)

        for match in matches:
            method = match.group(1).lower()
            path = match.group(2) or ""
            full_path = f"{base_path}/{path}".replace("//", "/")

            # Convert NestJS params to OpenAPI format
            full_path = re.sub(r":(\w+)", r"{\1}", full_path)

            self._discovered_routes.append({
                "path": full_path,
                "method": method,
                "file": str(file_path),
                "framework": "nestjs",
                "description": f"{method.upper()} {full_path}",
            })

    async def _generate_openapi_spec(self) -> None:
        """Generate OpenAPI 3.0 specification."""

        # Group routes by path
        paths = {}
        for route in self._discovered_routes:
            path = route["path"]
            method = route["method"]

            if path not in paths:
                paths[path] = {}

            paths[path][method] = {
                "summary": route.get("description", f"{method.upper()} {path}"),
                "operationId": f"{method}_{path.replace('/', '_').replace('{', '').replace('}', '')}",
                "tags": [self._get_tag_from_path(path)],
                "responses": {
                    "200": {
                        "description": "Successful response",
                    },
                    "400": {
                        "description": "Bad request",
                    },
                    "500": {
                        "description": "Internal server error",
                    },
                },
            }

            # Add path parameters
            params = re.findall(r"\{(\w+)\}", path)
            if params:
                paths[path][method]["parameters"] = [
                    {
                        "name": param,
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                    for param in params
                ]

            # Add request body for POST/PUT/PATCH
            if method in ["post", "put", "patch"]:
                paths[path][method]["requestBody"] = {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"type": "object"},
                        },
                    },
                }

        # Build OpenAPI spec
        openapi_spec = {
            "openapi": "3.0.3",
            "info": {
                "title": self.api_title,
                "version": self.api_version,
                "description": "Auto-generated API documentation",
            },
            "servers": [
                {"url": "http://localhost:3000", "description": "Development server"},
            ],
            "paths": paths,
            "components": {
                "schemas": {},
            },
        }

        # Write OpenAPI spec
        docs_dir = self.working_dir / "docs"
        docs_dir.mkdir(exist_ok=True)

        spec_path = docs_dir / "openapi.json"
        spec_path.write_text(json.dumps(openapi_spec, indent=2))

        # Also write YAML version
        try:
            import yaml
            yaml_path = docs_dir / "openapi.yaml"
            yaml_path.write_text(yaml.dump(openapi_spec, default_flow_style=False))
        except ImportError:
            pass

        # Publish event
        await self.event_bus.publish(openapi_spec_created_event(
            source=self.name,
            spec_path=str(spec_path),
            routes_count=len(self._discovered_routes),
        ))

        logger.info("openapi_spec_generated", path=str(spec_path))

    def _get_tag_from_path(self, path: str) -> str:
        """Extract a tag name from the API path."""
        parts = path.strip("/").split("/")
        if len(parts) > 1:
            return parts[1] if parts[0] == "api" else parts[0]
        return "default"

    async def _generate_swagger_ui(self) -> None:
        """Generate Swagger UI HTML page."""

        swagger_html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>API Documentation</title>
    <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">
</head>
<body>
    <div id="swagger-ui"></div>
    <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
    <script>
        window.onload = () => {
            SwaggerUIBundle({
                url: './openapi.json',
                dom_id: '#swagger-ui',
                presets: [
                    SwaggerUIBundle.presets.apis,
                    SwaggerUIBundle.SwaggerUIStandalonePreset
                ],
                layout: 'StandaloneLayout'
            });
        };
    </script>
</body>
</html>
"""
        docs_dir = self.working_dir / "docs"
        docs_dir.mkdir(exist_ok=True)

        swagger_path = docs_dir / "swagger.html"
        swagger_path.write_text(swagger_html)

        logger.info("swagger_ui_generated", path=str(swagger_path))

    async def _generate_postman_collection(self) -> None:
        """Generate Postman collection."""

        items = []
        for route in self._discovered_routes:
            item = {
                "name": route.get("description", f"{route['method'].upper()} {route['path']}"),
                "request": {
                    "method": route["method"].upper(),
                    "header": [
                        {"key": "Content-Type", "value": "application/json"},
                    ],
                    "url": {
                        "raw": f"{{{{base_url}}}}{route['path']}",
                        "host": ["{{base_url}}"],
                        "path": route["path"].strip("/").split("/"),
                    },
                },
            }

            # Add request body for POST/PUT/PATCH
            if route["method"] in ["post", "put", "patch"]:
                item["request"]["body"] = {
                    "mode": "raw",
                    "raw": "{}",
                }

            items.append(item)

        collection = {
            "info": {
                "name": self.api_title,
                "description": "Auto-generated Postman collection",
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            },
            "item": items,
            "variable": [
                {
                    "key": "base_url",
                    "value": "http://localhost:3000",
                },
            ],
        }

        docs_dir = self.working_dir / "docs"
        docs_dir.mkdir(exist_ok=True)

        postman_path = docs_dir / "postman_collection.json"
        postman_path.write_text(json.dumps(collection, indent=2))

        logger.info("postman_collection_generated", path=str(postman_path))

    async def cleanup(self) -> None:
        """Cleanup resources."""
        logger.info("api_documentation_agent_cleanup_complete")
