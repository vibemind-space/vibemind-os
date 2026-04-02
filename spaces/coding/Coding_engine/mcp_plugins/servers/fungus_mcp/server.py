#!/usr/bin/env python3
"""
Fungus MCP Server — Provides project context tools for Kilo CLI.

Tools:
  - project_tree: Directory listing of generated project
  - get_schema: Current Prisma schema
  - get_module_template: NestJS module template with project conventions
  - find_file: Search for files by name pattern

Uses the official MCP Python SDK (mcp>=0.9) for reliable stdio transport.
"""

import os
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

PROJECT_DIR = os.environ.get(
    "FUNGUS_PROJECT_DIR",
    "/app/output/whatsapp-messaging-service_20260211_025459",
)

app = Server("fungus-mcp")


# ─── Tool Implementations ───────────────────────────────────


def tool_project_tree(args: dict) -> str:
    """Returns directory tree of the generated project src/ directory."""
    base = Path(PROJECT_DIR)
    path = args.get("path", "src/")
    target = base / path
    max_depth = args.get("max_depth", 4)

    if not target.exists():
        return f"Directory not found: {path}\n\nAvailable directories:\n" + "\n".join(
            f"  {d.name}/" for d in base.iterdir() if d.is_dir() and not d.name.startswith(".")
        )

    lines = []

    def walk(dir_path, prefix="", depth=0):
        if depth > max_depth:
            return
        try:
            items = sorted(dir_path.iterdir(), key=lambda p: (not p.is_dir(), p.name))
        except PermissionError:
            return
        for i, item in enumerate(items):
            if item.name.startswith(".") or item.name == "node_modules":
                continue
            is_last = i == len(items) - 1
            connector = "└── " if is_last else "├── "
            if item.is_dir():
                lines.append(f"{prefix}{connector}{item.name}/")
                extension = "    " if is_last else "│   "
                walk(item, prefix + extension, depth + 1)
            else:
                size = item.stat().st_size
                lines.append(f"{prefix}{connector}{item.name} ({size}B)")

    lines.append(f"{path}")
    walk(target)
    return "\n".join(lines[:200])


def tool_get_schema(args: dict) -> str:
    """Returns current Prisma schema."""
    base = Path(PROJECT_DIR)
    for schema_path in [
        base / "prisma" / "schema.prisma",
        base / "schema.prisma",
    ]:
        if schema_path.exists():
            content = schema_path.read_text(encoding="utf-8", errors="replace")
            if len(content) > 8000:
                models = [l for l in content.split("\n") if l.startswith("model ")]
                return (
                    f"Schema has {len(models)} models:\n"
                    + "\n".join(models)
                    + f"\n\n(Full schema: {len(content)} chars, truncated)"
                )
            return content
    return "No prisma/schema.prisma found. The schema needs to be generated first."


def tool_get_module_template(args: dict) -> str:
    """Returns a NestJS module template matching project conventions."""
    module_name = args.get("module_name", "example")
    base = Path(PROJECT_DIR) / "src" / "modules"

    if base.exists():
        for module_dir in sorted(base.iterdir()):
            if module_dir.is_dir():
                files = list(module_dir.glob("*.ts"))
                if len(files) >= 2:
                    template = f"## Existing Module: {module_dir.name}/\n\n"
                    for f in sorted(files)[:4]:
                        content = f.read_text(encoding="utf-8", errors="replace")[:2000]
                        template += f"```typescript:src/modules/{module_dir.name}/{f.name}\n{content}\n```\n\n"
                    return template

    camel = module_name.replace("-", " ").title().replace(" ", "")
    return f"""## NestJS Module Template for '{module_name}'

```typescript:src/modules/{module_name}/{module_name}.module.ts
import {{ Module }} from '@nestjs/common';
import {{ {camel}Controller }} from './{module_name}.controller';
import {{ {camel}Service }} from './{module_name}.service';

@Module({{
  controllers: [{camel}Controller],
  providers: [{camel}Service],
  exports: [{camel}Service],
}})
export class {camel}Module {{}}
```

```typescript:src/modules/{module_name}/{module_name}.controller.ts
import {{ Controller, Get, Post, Put, Delete, Body, Param, UseGuards }} from '@nestjs/common';
import {{ {camel}Service }} from './{module_name}.service';
import {{ JwtAuthGuard }} from '../../guards/jwt-auth.guard';

@Controller('{module_name}')
@UseGuards(JwtAuthGuard)
export class {camel}Controller {{
  constructor(private readonly service: {camel}Service) {{}}

  @Get()
  async findAll() {{ return this.service.findAll(); }}

  @Get(':id')
  async findOne(@Param('id') id: string) {{ return this.service.findOne(id); }}

  @Post()
  async create(@Body() dto: any) {{ return this.service.create(dto); }}

  @Put(':id')
  async update(@Param('id') id: string, @Body() dto: any) {{ return this.service.update(id, dto); }}

  @Delete(':id')
  async remove(@Param('id') id: string) {{ return this.service.remove(id); }}
}}
```

```typescript:src/modules/{module_name}/{module_name}.service.ts
import {{ Injectable, NotFoundException }} from '@nestjs/common';
import {{ PrismaService }} from '../../prisma/prisma.service';

@Injectable()
export class {camel}Service {{
  constructor(private prisma: PrismaService) {{}}

  async findAll() {{ return this.prisma.{module_name.replace('-', '_')}.findMany(); }}

  async findOne(id: string) {{
    const item = await this.prisma.{module_name.replace('-', '_')}.findUnique({{ where: {{ id }} }});
    if (!item) throw new NotFoundException('{camel} not found');
    return item;
  }}

  async create(dto: any) {{ return this.prisma.{module_name.replace('-', '_')}.create({{ data: dto }}); }}

  async update(id: string, dto: any) {{ return this.prisma.{module_name.replace('-', '_')}.update({{ where: {{ id }}, data: dto }}); }}

  async remove(id: string) {{ return this.prisma.{module_name.replace('-', '_')}.delete({{ where: {{ id }} }}); }}
}}
```
"""


def tool_find_file(args: dict) -> str:
    """Search for files by name pattern in the project."""
    pattern = args.get("pattern", "*.ts")
    base = Path(PROJECT_DIR)
    max_results = args.get("max_results", 20)

    results = []
    for f in base.rglob(pattern):
        if "node_modules" in str(f) or ".git" in str(f):
            continue
        rel = f.relative_to(base)
        size = f.stat().st_size
        results.append(f"  {rel} ({size}B)")
        if len(results) >= max_results:
            break

    if not results:
        return f"No files matching '{pattern}' found in {base}"
    return f"Found {len(results)} files matching '{pattern}':\n" + "\n".join(results)


# ─── MCP Tool Registration ──────────────────────────────────

TOOL_HANDLERS = {
    "project_tree": tool_project_tree,
    "get_schema": tool_get_schema,
    "get_module_template": tool_get_module_template,
    "find_file": tool_find_file,
}


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="project_tree",
            description="Returns directory tree of the generated project. Shows all files in src/modules/, frontend/, prisma/ etc.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Subdirectory to list (default: 'src/')", "default": "src/"},
                    "max_depth": {"type": "integer", "description": "Max directory depth", "default": 4},
                },
            },
        ),
        Tool(
            name="get_schema",
            description="Returns the current Prisma database schema (prisma/schema.prisma).",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="get_module_template",
            description="Returns a NestJS module template with controller, service, and module files following project conventions.",
            inputSchema={
                "type": "object",
                "properties": {
                    "module_name": {"type": "string", "description": "Module name in kebab-case (e.g., 'auth', 'user-profile')"},
                },
                "required": ["module_name"],
            },
        ),
        Tool(
            name="find_file",
            description="Search for files by glob pattern in the generated project.",
            inputSchema={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Glob pattern (e.g., '*.controller.ts', 'auth*')"},
                    "max_results": {"type": "integer", "description": "Max results to return", "default": 20},
                },
                "required": ["pattern"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    handler = TOOL_HANDLERS.get(name)
    if not handler:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]
    try:
        result = handler(arguments)
        return [TextContent(type="text", text=result)]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {e}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
