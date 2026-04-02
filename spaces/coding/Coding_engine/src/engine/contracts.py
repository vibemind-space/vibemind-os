"""
Interface Contracts - Defines interfaces between parallel agents.

Contracts ensure that:
1. All agents know what interfaces to implement
2. No conflicts between parallel implementations
3. Types are consistent across the codebase
4. APIs are well-defined before implementation
"""
from dataclasses import dataclass, field
from typing import Optional, Any
from enum import Enum
import json


class ContractType(str, Enum):
    """Type of interface contract."""
    API_ENDPOINT = "api_endpoint"
    DATA_MODEL = "data_model"
    COMPONENT = "component"
    SERVICE = "service"
    EVENT = "event"
    SHARED_TYPE = "shared_type"


@dataclass
class TypeDefinition:
    """A type definition for contracts."""
    name: str
    fields: dict[str, str]  # field_name -> type
    description: str = ""
    optional_fields: list[str] = field(default_factory=list)

    def _normalize_fields(self) -> dict[str, str]:
        """Normalize fields to a dict, handling list input gracefully."""
        if isinstance(self.fields, dict):
            return self.fields
        elif isinstance(self.fields, list):
            # Convert list to dict
            # Handle list of dicts like [{"name": "id", "type": "string"}]
            result = {}
            for item in self.fields:
                if isinstance(item, dict):
                    name = item.get("name", item.get("field", f"field_{len(result)}"))
                    type_ = item.get("type", "any")
                    result[str(name)] = str(type_)
                elif isinstance(item, str):
                    # Just field names, use 'any' as type
                    result[item] = "any"
            return result
        else:
            return {}

    def to_typescript(self) -> str:
        """Generate TypeScript interface."""
        lines = [f"interface {self.name} {{"]
        normalized_fields = self._normalize_fields()
        for field_name, field_type in normalized_fields.items():
            # Ensure field_name is a string
            if not isinstance(field_name, str):
                field_name = str(field_name)
            optional = "?" if field_name in self.optional_fields else ""
            ts_type = self._python_to_ts_type(field_type)
            lines.append(f"  {field_name}{optional}: {ts_type};")
        lines.append("}")
        return "\n".join(lines)

    def to_python(self) -> str:
        """Generate Python dataclass."""
        lines = [
            "from dataclasses import dataclass",
            "from typing import Optional",
            "",
            "@dataclass",
            f"class {self.name}:",
            f'    """{self.description}"""' if self.description else "",
        ]
        normalized_fields = self._normalize_fields()
        for field_name, field_type in normalized_fields.items():
            if field_name in self.optional_fields:
                lines.append(f"    {field_name}: Optional[{field_type}] = None")
            else:
                lines.append(f"    {field_name}: {field_type}")
        return "\n".join(lines)

    def _python_to_ts_type(self, py_type) -> str:
        """Convert Python type to TypeScript type."""
        # Handle non-string types (e.g., lists from parsed JSON)
        if isinstance(py_type, list):
            # List of types - convert first element or return any[]
            if py_type:
                inner_type = self._python_to_ts_type(py_type[0])
                return f"{inner_type}[]"
            return "any[]"

        if isinstance(py_type, dict):
            return "Record<string, any>"

        if not isinstance(py_type, str):
            return "any"

        type_map = {
            "str": "string",
            "int": "number",
            "float": "number",
            "bool": "boolean",
            "list": "any[]",
            "dict": "Record<string, any>",
            "Any": "any",
            "None": "null",
            "string": "string",
            "number": "number",
            "boolean": "boolean",
        }
        return type_map.get(py_type, py_type)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "fields": self.fields,
            "description": self.description,
            "optional_fields": self.optional_fields,
        }


@dataclass
class APIEndpoint:
    """Definition of an API endpoint."""
    path: str
    method: str  # GET, POST, PUT, DELETE
    request_type: Optional[str] = None  # Reference to TypeDefinition
    response_type: Optional[str] = None  # Reference to TypeDefinition
    description: str = ""
    auth_required: bool = True
    tags: list[str] = field(default_factory=list)

    def to_openapi(self) -> dict:
        """Generate OpenAPI spec for this endpoint."""
        spec = {
            "summary": self.description,
            "tags": self.tags,
            "security": [{"bearerAuth": []}] if self.auth_required else [],
            "responses": {
                "200": {
                    "description": "Successful response",
                }
            }
        }

        if self.request_type:
            spec["requestBody"] = {
                "content": {
                    "application/json": {
                        "schema": {"$ref": f"#/components/schemas/{self.request_type}"}
                    }
                }
            }

        if self.response_type:
            spec["responses"]["200"]["content"] = {
                "application/json": {
                    "schema": {"$ref": f"#/components/schemas/{self.response_type}"}
                }
            }

        return spec

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "method": self.method,
            "request_type": self.request_type,
            "response_type": self.response_type,
            "description": self.description,
            "auth_required": self.auth_required,
            "tags": self.tags,
        }


@dataclass
class ComponentContract:
    """Definition of a UI component."""
    name: str
    props: dict[str, str]  # prop_name -> type
    description: str = ""
    children: bool = False
    events: list[str] = field(default_factory=list)

    def _normalize_props(self) -> dict[str, str]:
        """Normalize props to a dict, handling list input gracefully."""
        if isinstance(self.props, dict):
            return self.props
        elif isinstance(self.props, list):
            # Convert list to dict
            result = {}
            for item in self.props:
                if isinstance(item, dict):
                    name = item.get("name", item.get("prop", f"prop_{len(result)}"))
                    type_ = item.get("type", "any")
                    result[str(name)] = str(type_)
                elif isinstance(item, str):
                    result[item] = "any"
            return result
        else:
            return {}

    def to_typescript(self) -> str:
        """Generate TypeScript component interface."""
        lines = [f"interface {self.name}Props {{"]
        normalized_props = self._normalize_props()
        for prop_name, prop_type in normalized_props.items():
            lines.append(f"  {prop_name}: {prop_type};")
        if self.children:
            lines.append("  children?: React.ReactNode;")
        for event in self.events:
            lines.append(f"  {event}?: () => void;")
        lines.append("}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "props": self.props,
            "description": self.description,
            "children": self.children,
            "events": self.events,
        }


@dataclass
class ServiceContract:
    """Definition of a service interface."""
    name: str
    methods: dict[str, dict]  # method_name -> {params, return_type, description}
    description: str = ""

    def _normalize_methods(self) -> dict[str, dict]:
        """Normalize methods to a dict, handling list input gracefully."""
        if isinstance(self.methods, dict):
            return self.methods
        elif isinstance(self.methods, list):
            # Convert list to dict
            result = {}
            for item in self.methods:
                if isinstance(item, dict):
                    name = item.get("name", item.get("method", f"method_{len(result)}"))
                    result[str(name)] = {
                        "params": item.get("params", {}),
                        "return_type": item.get("return_type", "None"),
                        "description": item.get("description", ""),
                    }
                elif isinstance(item, str):
                    result[item] = {"params": {}, "return_type": "None", "description": ""}
            return result
        else:
            return {}

    def to_python(self) -> str:
        """Generate Python abstract class."""
        lines = [
            "from abc import ABC, abstractmethod",
            "",
            f"class {self.name}(ABC):",
            f'    """{self.description}"""' if self.description else "",
        ]

        normalized_methods = self._normalize_methods()
        for method_name, method_def in normalized_methods.items():
            params = method_def.get("params", {})
            # Handle params being a list
            if isinstance(params, list):
                params = {f"arg{i}": "Any" for i, _ in enumerate(params)}
            return_type = method_def.get("return_type", "None")
            desc = method_def.get("description", "")

            param_str = ", ".join(
                f"{p}: {t}" for p, t in params.items()
            ) if isinstance(params, dict) else ""
            lines.extend([
                "",
                "    @abstractmethod",
                f"    async def {method_name}(self, {param_str}) -> {return_type}:",
                f'        """{desc}"""' if desc else '        """..."""',
                "        pass",
            ])

        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "methods": self.methods,
            "description": self.description,
        }


@dataclass
class InterfaceContracts:
    """
    Collection of all interface contracts for a project.

    This is the main output of the Architect Agent's pre-analysis.
    All other agents receive this to ensure consistent interfaces.
    """
    project_name: str
    types: list[TypeDefinition] = field(default_factory=list)
    endpoints: list[APIEndpoint] = field(default_factory=list)
    components: list[ComponentContract] = field(default_factory=list)
    services: list[ServiceContract] = field(default_factory=list)
    file_ownership: dict[str, str] = field(default_factory=dict)  # pattern -> agent_type

    def add_type(self, type_def: TypeDefinition):
        """Add a type definition."""
        self.types.append(type_def)

    def add_endpoint(self, endpoint: APIEndpoint):
        """Add an API endpoint."""
        self.endpoints.append(endpoint)

    def add_component(self, component: ComponentContract):
        """Add a component contract."""
        self.components.append(component)

    def add_service(self, service: ServiceContract):
        """Add a service contract."""
        self.services.append(service)

    def get_type(self, name: str) -> Optional[TypeDefinition]:
        """Get a type by name."""
        for t in self.types:
            if t.name == name:
                return t
        return None

    def to_prompt_context(self, for_agent: str) -> str:
        """Generate prompt context for a specific agent."""
        context = [f"## Interface Contracts for {self.project_name}\n"]

        # Add shared types
        if self.types:
            context.append("### Shared Types\n")
            context.append("Use these exact type definitions:\n")
            for t in self.types:
                context.append(f"```typescript\n{t.to_typescript()}\n```\n")

        # Add relevant contracts based on agent type
        if for_agent == "backend" and self.endpoints:
            context.append("### API Endpoints to Implement\n")
            for ep in self.endpoints:
                context.append(
                    f"- `{ep.method} {ep.path}` - {ep.description}\n"
                    f"  Request: {ep.request_type or 'None'}, Response: {ep.response_type or 'None'}\n"
                )

        if for_agent == "frontend" and self.components:
            context.append("### Components to Implement\n")
            for comp in self.components:
                context.append(f"- `{comp.name}` - {comp.description}\n")
                context.append(f"```typescript\n{comp.to_typescript()}\n```\n")

        if for_agent in ["backend", "testing"] and self.services:
            context.append("### Service Interfaces\n")
            for svc in self.services:
                context.append(f"- `{svc.name}` - {svc.description}\n")

        # Add file ownership
        if self.file_ownership:
            my_patterns = [
                p for p, agent in self.file_ownership.items()
                if agent == for_agent
            ]
            if my_patterns:
                context.append(f"### Your File Ownership\n")
                context.append("You are responsible for these file patterns:\n")
                for p in my_patterns:
                    context.append(f"- `{p}`\n")

        return "\n".join(context)

    def to_dict(self) -> dict:
        return {
            "project_name": self.project_name,
            "types": [t.to_dict() for t in self.types],
            "endpoints": [e.to_dict() for e in self.endpoints],
            "components": [c.to_dict() for c in self.components],
            "services": [s.to_dict() for s in self.services],
            "file_ownership": self.file_ownership,
        }

    def to_json(self) -> str:
        """Serialize to JSON."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> "InterfaceContracts":
        """Create from dictionary."""
        contracts = cls(project_name=data.get("project_name", "Unknown"))

        for t in data.get("types", []):
            contracts.add_type(TypeDefinition(**t))

        for e in data.get("endpoints", []):
            contracts.add_endpoint(APIEndpoint(**e))

        for c in data.get("components", []):
            contracts.add_component(ComponentContract(**c))

        for s in data.get("services", []):
            contracts.add_service(ServiceContract(**s))

        contracts.file_ownership = data.get("file_ownership", {})

        return contracts

    @classmethod
    def from_json(cls, json_str: str) -> "InterfaceContracts":
        """Create from JSON string."""
        return cls.from_dict(json.loads(json_str))
