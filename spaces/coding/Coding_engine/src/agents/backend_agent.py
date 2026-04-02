"""
Backend Agent - Specialized for API and backend development.

Capabilities:
- REST/GraphQL API design
- Database models and migrations
- Business logic implementation
- Authentication/Authorization
"""
from typing import Optional
from src.agents.base_agent import BaseAgent, AgentConfig, AgentType, GeneratedFile


class BackendAgent(BaseAgent):
    """Agent specialized for backend development."""

    def __init__(self, config: Optional[AgentConfig] = None):
        if config is None:
            config = AgentConfig(agent_type=AgentType.BACKEND)
        else:
            config.agent_type = AgentType.BACKEND
        super().__init__(config)

    def _register_tools(self):
        """Register backend-specific tools."""

        # Create API endpoint
        self.register_tool(
            name="create_endpoint",
            description="Create a REST API endpoint.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "API path (e.g., /api/users)",
                    },
                    "method": {
                        "type": "string",
                        "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"],
                    },
                    "description": {
                        "type": "string",
                        "description": "Endpoint description",
                    },
                    "request_schema": {
                        "type": "object",
                        "description": "Request body schema",
                    },
                    "response_schema": {
                        "type": "object",
                        "description": "Response schema",
                    },
                },
                "required": ["path", "method"],
            },
            handler=self._handle_create_endpoint,
        )

        # Create database model
        self.register_tool(
            name="create_model",
            description="Create a database model/schema.",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Model name",
                    },
                    "fields": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "type": {"type": "string"},
                                "nullable": {"type": "boolean"},
                                "unique": {"type": "boolean"},
                                "index": {"type": "boolean"},
                            },
                        },
                    },
                    "relationships": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "target": {"type": "string"},
                                "type": {"type": "string"},
                            },
                        },
                    },
                },
                "required": ["name", "fields"],
            },
            handler=self._handle_create_model,
        )

        # Create migration
        self.register_tool(
            name="create_migration",
            description="Create a database migration.",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Migration name",
                    },
                    "operations": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Migration operations",
                    },
                },
                "required": ["name"],
            },
            handler=self._handle_create_migration,
        )

    def get_system_prompt(self) -> str:
        return """You are an expert backend developer specializing in API design and implementation.

## Your Expertise
- Python (FastAPI, Django, Flask)
- Node.js (Express, NestJS)
- Database design (PostgreSQL, MongoDB)
- RESTful API design
- GraphQL APIs
- Authentication (JWT, OAuth)
- Message queues and async processing

## Guidelines
1. Follow RESTful conventions for API design
2. Use proper HTTP status codes
3. Implement input validation
4. Include error handling with meaningful messages
5. Design for scalability
6. Document endpoints with OpenAPI/Swagger
7. Use appropriate database indexes

## Output Format
Use the available tools to create:
1. API endpoint handlers
2. Database models
3. Migrations if needed
4. Utility functions
5. Configuration files

Always consider security implications and performance optimization."""

    def _handle_create_endpoint(
        self,
        input_data: dict,
        generated_files: list[GeneratedFile],
    ) -> dict:
        """Handle endpoint creation."""
        path = input_data.get("path", "/api/resource")
        method = input_data.get("method", "GET")

        return {
            "success": True,
            "message": f"Endpoint created: {method} {path}",
            "path": path,
            "method": method,
        }

    def _handle_create_model(
        self,
        input_data: dict,
        generated_files: list[GeneratedFile],
    ) -> dict:
        """Handle model creation."""
        name = input_data.get("name", "Model")
        fields = input_data.get("fields", [])

        return {
            "success": True,
            "message": f"Model created: {name}",
            "fields_count": len(fields),
        }

    def _handle_create_migration(
        self,
        input_data: dict,
        generated_files: list[GeneratedFile],
    ) -> dict:
        """Handle migration creation."""
        name = input_data.get("name", "migration")

        return {
            "success": True,
            "message": f"Migration created: {name}",
        }
