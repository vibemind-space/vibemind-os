"""
Custom MCP Server - Framework for building Python MCP servers.

Provides decorators and base classes for creating custom MCP tools
that can be dynamically registered with Claude Code.

Usage:
    from src.mcp.custom_server import CustomMCPServer, tool, resource

    server = CustomMCPServer("my-tools")

    @server.tool("analyze_code")
    async def analyze_code(file_path: str) -> dict:
        '''Analyze a code file for issues.'''
        # Your implementation
        return {"issues": [...]}

    @server.resource("project://files")
    async def list_files() -> list[str]:
        '''List all project files.'''
        return [...]

    # Run as MCP server
    if __name__ == "__main__":
        server.run()
"""

import asyncio
import inspect
import json
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, get_type_hints

import structlog

logger = structlog.get_logger()


@dataclass
class ToolDefinition:
    """Definition of an MCP tool."""
    name: str
    description: str
    handler: Callable
    input_schema: dict
    output_schema: Optional[dict] = None


@dataclass
class ResourceDefinition:
    """Definition of an MCP resource."""
    uri: str
    name: str
    description: str
    handler: Callable
    mime_type: str = "application/json"


def _get_json_schema_type(python_type) -> dict:
    """Convert Python type to JSON Schema type."""
    type_map = {
        str: {"type": "string"},
        int: {"type": "integer"},
        float: {"type": "number"},
        bool: {"type": "boolean"},
        list: {"type": "array"},
        dict: {"type": "object"},
        type(None): {"type": "null"},
    }

    # Handle Optional types
    origin = getattr(python_type, "__origin__", None)
    if origin is type(None):
        return {"type": "null"}

    # Handle Union (Optional)
    if origin is type(None) or str(origin) == "typing.Union":
        args = getattr(python_type, "__args__", ())
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return _get_json_schema_type(non_none[0])

    # Handle List[T]
    if origin is list:
        args = getattr(python_type, "__args__", ())
        if args:
            return {
                "type": "array",
                "items": _get_json_schema_type(args[0]),
            }
        return {"type": "array"}

    # Handle Dict[K, V]
    if origin is dict:
        return {"type": "object"}

    return type_map.get(python_type, {"type": "string"})


def _generate_input_schema(func: Callable) -> dict:
    """Generate JSON Schema from function signature."""
    sig = inspect.signature(func)
    hints = get_type_hints(func) if hasattr(func, "__annotations__") else {}

    properties = {}
    required = []

    for name, param in sig.parameters.items():
        if name in ("self", "cls"):
            continue

        # Get type hint
        python_type = hints.get(name, str)
        schema = _get_json_schema_type(python_type)

        # Get description from docstring if available
        schema["description"] = f"Parameter: {name}"

        properties[name] = schema

        # Check if required
        if param.default is inspect.Parameter.empty:
            required.append(name)

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


def tool(name: Optional[str] = None, description: Optional[str] = None):
    """
    Decorator to register a function as an MCP tool.

    Usage:
        @tool("my_tool")
        async def my_tool(arg1: str, arg2: int = 10) -> dict:
            '''Tool description here.'''
            return {"result": arg1 * arg2}
    """
    def decorator(func: Callable) -> Callable:
        func._mcp_tool = True
        func._mcp_tool_name = name or func.__name__
        func._mcp_tool_description = description or (func.__doc__ or "").strip()
        return func

    return decorator


def resource(uri: str, name: Optional[str] = None, mime_type: str = "application/json"):
    """
    Decorator to register a function as an MCP resource.

    Usage:
        @resource("project://config")
        async def get_config() -> dict:
            '''Get project configuration.'''
            return {"key": "value"}
    """
    def decorator(func: Callable) -> Callable:
        func._mcp_resource = True
        func._mcp_resource_uri = uri
        func._mcp_resource_name = name or func.__name__
        func._mcp_resource_mime_type = mime_type
        return func

    return decorator


class CustomMCPServer:
    """
    Base class for custom Python MCP servers.

    Implements the MCP protocol over stdio, allowing Python functions
    to be exposed as tools to Claude Code.

    Usage:
        server = CustomMCPServer("my-server")

        @server.tool("greet")
        async def greet(name: str) -> str:
            return f"Hello, {name}!"

        server.run()
    """

    def __init__(self, name: str, version: str = "1.0.0"):
        self.name = name
        self.version = version
        self.tools: dict[str, ToolDefinition] = {}
        self.resources: dict[str, ResourceDefinition] = {}
        self.logger = logger.bind(component="mcp_server", server=name)

    def tool(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Callable:
        """Register a tool handler."""
        def decorator(func: Callable) -> Callable:
            tool_name = name or func.__name__
            tool_desc = description or (func.__doc__ or "").strip()
            input_schema = _generate_input_schema(func)

            self.tools[tool_name] = ToolDefinition(
                name=tool_name,
                description=tool_desc,
                handler=func,
                input_schema=input_schema,
            )

            self.logger.debug("tool_registered", name=tool_name)
            return func

        return decorator

    def resource(
        self,
        uri: str,
        name: Optional[str] = None,
        mime_type: str = "application/json",
    ) -> Callable:
        """Register a resource handler."""
        def decorator(func: Callable) -> Callable:
            res_name = name or func.__name__
            res_desc = (func.__doc__ or "").strip()

            self.resources[uri] = ResourceDefinition(
                uri=uri,
                name=res_name,
                description=res_desc,
                handler=func,
                mime_type=mime_type,
            )

            self.logger.debug("resource_registered", uri=uri)
            return func

        return decorator

    def register_tools_from_module(self, module) -> None:
        """Register all decorated tools from a module."""
        for name in dir(module):
            obj = getattr(module, name)
            if callable(obj) and hasattr(obj, "_mcp_tool"):
                self.tools[obj._mcp_tool_name] = ToolDefinition(
                    name=obj._mcp_tool_name,
                    description=obj._mcp_tool_description,
                    handler=obj,
                    input_schema=_generate_input_schema(obj),
                )

            if callable(obj) and hasattr(obj, "_mcp_resource"):
                self.resources[obj._mcp_resource_uri] = ResourceDefinition(
                    uri=obj._mcp_resource_uri,
                    name=obj._mcp_resource_name,
                    description=obj._mcp_resource_description if hasattr(obj, "_mcp_resource_description") else "",
                    handler=obj,
                    mime_type=obj._mcp_resource_mime_type,
                )

    async def handle_request(self, request: dict) -> dict:
        """Handle an incoming MCP request."""
        method = request.get("method", "")
        params = request.get("params", {})
        request_id = request.get("id")

        self.logger.debug("request_received", method=method, id=request_id)

        try:
            if method == "initialize":
                result = await self._handle_initialize(params)
            elif method == "tools/list":
                result = await self._handle_list_tools()
            elif method == "tools/call":
                result = await self._handle_call_tool(params)
            elif method == "resources/list":
                result = await self._handle_list_resources()
            elif method == "resources/read":
                result = await self._handle_read_resource(params)
            else:
                return self._error_response(request_id, -32601, f"Unknown method: {method}")

            return self._success_response(request_id, result)

        except Exception as e:
            self.logger.error("request_failed", method=method, error=str(e))
            return self._error_response(request_id, -32603, str(e))

    async def _handle_initialize(self, params: dict) -> dict:
        """Handle initialize request."""
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"listChanged": False},
            },
            "serverInfo": {
                "name": self.name,
                "version": self.version,
            },
        }

    async def _handle_list_tools(self) -> dict:
        """Handle tools/list request."""
        tools = []
        for tool_def in self.tools.values():
            tools.append({
                "name": tool_def.name,
                "description": tool_def.description,
                "inputSchema": tool_def.input_schema,
            })
        return {"tools": tools}

    async def _handle_call_tool(self, params: dict) -> dict:
        """Handle tools/call request."""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if tool_name not in self.tools:
            raise ValueError(f"Unknown tool: {tool_name}")

        tool_def = self.tools[tool_name]
        handler = tool_def.handler

        # Call handler (sync or async)
        if asyncio.iscoroutinefunction(handler):
            result = await handler(**arguments)
        else:
            result = handler(**arguments)

        # Format result
        if isinstance(result, str):
            content = [{"type": "text", "text": result}]
        elif isinstance(result, dict):
            content = [{"type": "text", "text": json.dumps(result, indent=2)}]
        else:
            content = [{"type": "text", "text": str(result)}]

        return {"content": content}

    async def _handle_list_resources(self) -> dict:
        """Handle resources/list request."""
        resources = []
        for res_def in self.resources.values():
            resources.append({
                "uri": res_def.uri,
                "name": res_def.name,
                "description": res_def.description,
                "mimeType": res_def.mime_type,
            })
        return {"resources": resources}

    async def _handle_read_resource(self, params: dict) -> dict:
        """Handle resources/read request."""
        uri = params.get("uri")

        if uri not in self.resources:
            raise ValueError(f"Unknown resource: {uri}")

        res_def = self.resources[uri]
        handler = res_def.handler

        # Call handler
        if asyncio.iscoroutinefunction(handler):
            result = await handler()
        else:
            result = handler()

        # Format result
        if isinstance(result, str):
            text = result
        else:
            text = json.dumps(result, indent=2)

        return {
            "contents": [{
                "uri": uri,
                "mimeType": res_def.mime_type,
                "text": text,
            }]
        }

    def _success_response(self, request_id: Any, result: dict) -> dict:
        """Create a success response."""
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": result,
        }

    def _error_response(self, request_id: Any, code: int, message: str) -> dict:
        """Create an error response."""
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": code,
                "message": message,
            },
        }

    async def _run_stdio(self) -> None:
        """Run the server using stdio transport."""
        self.logger.info("server_starting", name=self.name)

        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)

        await asyncio.get_event_loop().connect_read_pipe(
            lambda: protocol,
            sys.stdin,
        )

        writer_transport, writer_protocol = await asyncio.get_event_loop().connect_write_pipe(
            asyncio.streams.FlowControlMixin,
            sys.stdout,
        )
        writer = asyncio.StreamWriter(writer_transport, writer_protocol, reader, asyncio.get_event_loop())

        while True:
            try:
                line = await reader.readline()
                if not line:
                    break

                request = json.loads(line.decode("utf-8"))
                response = await self.handle_request(request)

                writer.write((json.dumps(response) + "\n").encode("utf-8"))
                await writer.drain()

            except json.JSONDecodeError as e:
                self.logger.error("json_decode_error", error=str(e))
            except Exception as e:
                self.logger.error("server_error", error=str(e))

    def run(self) -> None:
        """Run the MCP server."""
        try:
            asyncio.run(self._run_stdio())
        except KeyboardInterrupt:
            self.logger.info("server_stopped")


# Example usage and built-in tools
def create_coding_engine_server() -> CustomMCPServer:
    """Create an MCP server with Coding Engine tools."""
    server = CustomMCPServer("coding-engine-tools", "1.0.0")

    @server.tool("analyze_requirements")
    async def analyze_requirements(requirements_json: str) -> dict:
        """Analyze requirements JSON and extract features."""
        try:
            reqs = json.loads(requirements_json)
            features = reqs.get("features", [])
            return {
                "feature_count": len(features),
                "features": [f.get("name") for f in features],
                "complexity": "high" if len(features) > 10 else "medium" if len(features) > 5 else "low",
            }
        except json.JSONDecodeError:
            return {"error": "Invalid JSON"}

    @server.tool("check_build_status")
    async def check_build_status(output_dir: str) -> dict:
        """Check build status of generated project."""
        from pathlib import Path

        output_path = Path(output_dir)

        status = {
            "exists": output_path.exists(),
            "has_package_json": (output_path / "package.json").exists(),
            "has_node_modules": (output_path / "node_modules").exists(),
            "has_src": (output_path / "src").exists(),
        }

        if status["has_package_json"]:
            try:
                pkg = json.loads((output_path / "package.json").read_text())
                status["project_name"] = pkg.get("name", "unknown")
                status["has_build_script"] = "build" in pkg.get("scripts", {})
            except:
                pass

        return status

    @server.resource("project://status")
    async def project_status() -> dict:
        """Get current project status."""
        return {
            "server": "coding-engine-tools",
            "status": "running",
        }

    return server


if __name__ == "__main__":
    # Run as standalone MCP server
    server = create_coding_engine_server()
    server.run()
