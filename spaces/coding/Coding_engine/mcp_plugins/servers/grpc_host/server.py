"""
EventFixTeam MCP Server - gRPC-basierte verteilte Agent-Architektur

Dieser MCP Server bietet Tools für die Arbeit mit einem verteilten Agent-Team,
das über gRPC kommuniziert. Die Agents sind spezialisiert auf verschiedene Aufgaben:
- FileWriteAgent: Code-Schreiben
- DockerAgent: Container-Management
- RedisAgent: Cache-Management
- PostgresAgent: Datenbank-Operationen
- PlaywrightAgent: E2E-Testing
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
    CallToolResult,
    ListToolsResult
)

from agents.agent_manager import AgentManager
from agents.grpc_client import GrpcClient

# Logging konfigurieren
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# MCP Server erstellen
app = Server("eventfixteam-mcp-server")

# Agent Manager initialisieren
agent_manager = AgentManager()


@app.list_tools()
async def list_tools() -> ListToolsResult:
    """Listet alle verfügbaren Tools auf"""
    tools = [
        Tool(
            name="agent_status",
            description="Zeigt den Status aller registrierten Agents an",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="agent_execute",
            description="Führt einen Task auf einem spezifischen Agent aus",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_type": {
                        "type": "string",
                        "enum": ["file_write", "docker", "redis", "postgres", "playwright"],
                        "description": "Der Typ des Agents"
                    },
                    "task": {
                        "type": "string",
                        "description": "Die Aufgabe, die ausgeführt werden soll"
                    },
                    "parameters": {
                        "type": "object",
                        "description": "Parameter für die Aufgabe"
                    }
                },
                "required": ["agent_type", "task"]
            }
        ),
        Tool(
            name="agent_execute_parallel",
            description="Führt mehrere Tasks parallel auf verschiedenen Agents aus",
            inputSchema={
                "type": "object",
                "properties": {
                    "tasks": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "agent_type": {
                                    "type": "string",
                                    "enum": ["file_write", "docker", "redis", "postgres", "playwright"]
                                },
                                "task": {"type": "string"},
                                "parameters": {"type": "object"}
                            },
                            "required": ["agent_type", "task"]
                        }
                    }
                },
                "required": ["tasks"]
            }
        ),
        Tool(
            name="agent_execute_workflow",
            description="Führt einen Workflow mit mehreren Agents aus",
            inputSchema={
                "type": "object",
                "properties": {
                    "workflow_name": {
                        "type": "string",
                        "description": "Name des Workflows"
                    },
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "agent_type": {
                                    "type": "string",
                                    "enum": ["file_write", "docker", "redis", "postgres", "playwright"]
                                },
                                "task": {"type": "string"},
                                "parameters": {"type": "object"},
                                "depends_on": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "IDs der vorherigen Schritte"
                                }
                            },
                            "required": ["agent_type", "task"]
                        }
                    }
                },
                "required": ["workflow_name", "steps"]
            }
        ),
        Tool(
            name="agent_health_check",
            description="Führt einen Health Check für alle Agents durch",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="agent_get_logs",
            description="Ruft Logs von einem spezifischen Agent ab",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_type": {
                        "type": "string",
                        "enum": ["file_write", "docker", "redis", "postgres", "playwright"]
                    },
                    "lines": {
                        "type": "integer",
                        "default": 100,
                        "description": "Anzahl der Zeilen"
                    }
                },
                "required": ["agent_type"]
            }
        ),
        Tool(
            name="agent_restart",
            description="Startet einen Agent neu",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_type": {
                        "type": "string",
                        "enum": ["file_write", "docker", "redis", "postgres", "playwright"]
                    }
                },
                "required": ["agent_type"]
            }
        ),
        Tool(
            name="agent_scale",
            description="Skaliert die Anzahl der Instanzen eines Agents",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_type": {
                        "type": "string",
                        "enum": ["file_write", "docker", "redis", "postgres", "playwright"]
                    },
                    "instances": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "Anzahl der Instanzen"
                    }
                },
                "required": ["agent_type", "instances"]
            }
        ),
        Tool(
            name="agent_get_metrics",
            description="Ruft Metriken von einem Agent ab",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_type": {
                        "type": "string",
                        "enum": ["file_write", "docker", "redis", "postgres", "playwright"]
                    }
                },
                "required": ["agent_type"]
            }
        ),
        Tool(
            name="agent_create_workflow_template",
            description="Erstellt ein Workflow-Template für häufige Aufgaben",
            inputSchema={
                "type": "object",
                "properties": {
                    "template_name": {
                        "type": "string",
                        "description": "Name des Templates"
                    },
                    "description": {
                        "type": "string",
                        "description": "Beschreibung des Templates"
                    },
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "agent_type": {
                                    "type": "string",
                                    "enum": ["file_write", "docker", "redis", "postgres", "playwright"]
                                },
                                "task": {"type": "string"},
                                "parameters": {"type": "object"}
                            },
                            "required": ["agent_type", "task"]
                        }
                    }
                },
                "required": ["template_name", "steps"]
            }
        ),
        Tool(
            name="agent_list_workflow_templates",
            description="Listet alle verfügbaren Workflow-Templates auf",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="agent_execute_workflow_template",
            description="Führt ein Workflow-Template aus",
            inputSchema={
                "type": "object",
                "properties": {
                    "template_name": {
                        "type": "string",
                        "description": "Name des Templates"
                    },
                    "parameters": {
                        "type": "object",
                        "description": "Parameter für das Template"
                    }
                },
                "required": ["template_name"]
            }
        )
    ]
    
    return ListToolsResult(tools=tools)


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> List[TextContent | ImageContent | EmbeddedResource]:
    """Führt ein Tool aus"""
    
    try:
        if name == "agent_status":
            result = await agent_manager.get_agent_status()
            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2, ensure_ascii=False)
            )]
        
        elif name == "agent_execute":
            agent_type = arguments.get("agent_type")
            task = arguments.get("task")
            parameters = arguments.get("parameters", {})
            
            result = await agent_manager.execute_task(
                agent_type=agent_type,
                task=task,
                parameters=parameters
            )
            
            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2, ensure_ascii=False)
            )]
        
        elif name == "agent_execute_parallel":
            tasks = arguments.get("tasks", [])
            
            results = await agent_manager.execute_parallel_tasks(tasks)
            
            return [TextContent(
                type="text",
                text=json.dumps(results, indent=2, ensure_ascii=False)
            )]
        
        elif name == "agent_execute_workflow":
            workflow_name = arguments.get("workflow_name")
            steps = arguments.get("steps", [])
            
            result = await agent_manager.execute_workflow(workflow_name, steps)
            
            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2, ensure_ascii=False)
            )]
        
        elif name == "agent_health_check":
            result = await agent_manager.health_check()
            
            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2, ensure_ascii=False)
            )]
        
        elif name == "agent_get_logs":
            agent_type = arguments.get("agent_type")
            lines = arguments.get("lines", 100)
            
            result = await agent_manager.get_agent_logs(agent_type, lines)
            
            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2, ensure_ascii=False)
            )]
        
        elif name == "agent_restart":
            agent_type = arguments.get("agent_type")
            
            result = await agent_manager.restart_agent(agent_type)
            
            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2, ensure_ascii=False)
            )]
        
        elif name == "agent_scale":
            agent_type = arguments.get("agent_type")
            instances = arguments.get("instances", 1)
            
            result = await agent_manager.scale_agent(agent_type, instances)
            
            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2, ensure_ascii=False)
            )]
        
        elif name == "agent_get_metrics":
            agent_type = arguments.get("agent_type")
            
            result = await agent_manager.get_agent_metrics(agent_type)
            
            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2, ensure_ascii=False)
            )]
        
        elif name == "agent_create_workflow_template":
            template_name = arguments.get("template_name")
            description = arguments.get("description", "")
            steps = arguments.get("steps", [])
            
            result = await agent_manager.create_workflow_template(
                template_name, description, steps
            )
            
            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2, ensure_ascii=False)
            )]
        
        elif name == "agent_list_workflow_templates":
            result = await agent_manager.list_workflow_templates()
            
            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2, ensure_ascii=False)
            )]
        
        elif name == "agent_execute_workflow_template":
            template_name = arguments.get("template_name")
            parameters = arguments.get("parameters", {})
            
            result = await agent_manager.execute_workflow_template(
                template_name, parameters
            )
            
            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2, ensure_ascii=False)
            )]
        
        else:
            return [TextContent(
                type="text",
                text=f"Unbekanntes Tool: {name}"
            )]
    
    except Exception as e:
        logger.error(f"Fehler beim Ausführen von Tool {name}: {e}", exc_info=True)
        return [TextContent(
            type="text",
            text=f"Fehler: {str(e)}"
        )]


async def main():
    """Hauptfunktion zum Starten des MCP Servers"""
    logger.info("Starte EventFixTeam MCP Server...")
    
    # Agent Manager initialisieren
    await agent_manager.initialize()
    
    # Server starten
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
