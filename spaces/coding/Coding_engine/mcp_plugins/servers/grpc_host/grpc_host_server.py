"""
gRPC Host Server Implementation

Dieser Server nutzt AutoGen 0.4 mit MCP Tool Integration für die
Orchestrierung von Multi-Step Tool Calls durch einen Reasoning Agent.
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

import grpc
from grpc_host_pb2 import (
    TaskRequest,
    TaskResponse,
    TaskStatus,
    AgentInfo,
    AgentListResponse,
    HealthCheckResponse,
    Empty
)
from grpc_host_pb2_grpc import (
    EventFixTeamServicer,
    add_EventFixTeamServicer_to_server
)

# AutoGen Orchestrator Integration
from autogen_orchestrator import EventFixOrchestrator
from task_prompts import get_task_prompt, list_task_types

logger = logging.getLogger(__name__)


class EventFixTeamServer(EventFixTeamServicer):
    """gRPC Server für EventFixTeam

    Nutzt AutoGen 0.4 Orchestrator für die Ausführung von Tasks.
    Der Reasoning Agent plant und führt Multi-Step Tool Calls aus,
    während der Validator Agent die Ergebnisse prüft.
    """

    def __init__(self, model: str = "gpt-4o"):
        self.tasks: Dict[str, Dict] = {}
        self.agents: Dict[str, Dict] = {}
        self.task_counter = 0
        self._model = model
        self._orchestrator: Optional[EventFixOrchestrator] = None
        self._orchestrator_lock = asyncio.Lock()
        self._initialize_agents()
    
    def _initialize_agents(self):
        """Initialisiere die Agenten-Metadaten

        Diese Metadaten beschreiben die logischen Agenten-Typen.
        Die tatsächliche Ausführung erfolgt durch den AutoGen Orchestrator,
        der MCP Tools dynamisch verwendet.
        """
        # Verfügbare Task-Typen aus task_prompts laden
        available_task_types = list_task_types()

        self.agents = {
            "reasoning_agent": {
                "id": "reasoning_agent",
                "name": "Reasoning Agent (AutoGen)",
                "description": "Plant und führt Multi-Step Tool Calls aus",
                "status": "ready",
                "capabilities": available_task_types
            },
            "code_writer": {
                "id": "code_writer",
                "name": "Code Writer Agent",
                "description": "Erstellt Code-Dateien basierend auf Aufgaben",
                "status": "ready",
                "capabilities": ["write_code", "create_files", "fix_code", "read_code"]
            },
            "fix_migrator": {
                "id": "fix_migrator",
                "name": "Fix Migrator Agent",
                "description": "Migriert Fixes und verwaltet Logs",
                "status": "ready",
                "capabilities": ["migrate_fixes", "manage_logs", "migrate_database"]
            },
            "debugger": {
                "id": "debugger",
                "name": "Debugger Agent",
                "description": "Debuggt Probleme mit Docker, Redis, PostgreSQL",
                "status": "ready",
                "capabilities": ["debug_docker", "debug_redis", "debug_postgres"]
            },
            "tester": {
                "id": "tester",
                "name": "Tester Agent",
                "description": "Führt Funktionstests mit Playwright durch",
                "status": "ready",
                "capabilities": ["test_functions", "playwright_tests", "run_tests"]
            }
        }
        logger.info(f"Agenten initialisiert: {list(self.agents.keys())}")

    async def _get_orchestrator(self) -> EventFixOrchestrator:
        """Lazy-Initialisierung des AutoGen Orchestrators

        Der Orchestrator wird erst beim ersten Task erstellt,
        um Ressourcen zu sparen wenn der Server nur für Health Checks läuft.
        """
        async with self._orchestrator_lock:
            if self._orchestrator is None:
                logger.info(f"Initialisiere AutoGen Orchestrator mit Model: {self._model}")
                self._orchestrator = EventFixOrchestrator(model=self._model)
                await self._orchestrator.initialize()
                logger.info("AutoGen Orchestrator bereit")
            return self._orchestrator
    
    async def SubmitTask(self, request: TaskRequest, context) -> TaskResponse:
        """Reiche eine Aufgabe ein"""
        task_id = f"task_{self.task_counter}"
        self.task_counter += 1
        
        task = {
            "id": task_id,
            "type": request.type,
            "description": request.description,
            "parameters": json.loads(request.parameters) if request.parameters else {},
            "status": TaskStatus.PENDING,
            "created_at": datetime.utcnow().isoformat(),
            "result": None,
            "error": None
        }
        
        self.tasks[task_id] = task
        logger.info(f"Task eingereicht: {task_id} - {request.type}")
        
        # Starte die asynchrone Verarbeitung
        asyncio.create_task(self._process_task(task_id))
        
        return TaskResponse(
            task_id=task_id,
            status=TaskStatus.PENDING,
            message="Task eingereicht und wird verarbeitet"
        )
    
    async def GetTaskStatus(self, request, context) -> TaskResponse:
        """Hole den Status einer Aufgabe"""
        task_id = request.task_id
        
        if task_id not in self.tasks:
            return TaskResponse(
                task_id=task_id,
                status=TaskStatus.FAILED,
                message=f"Task nicht gefunden: {task_id}"
            )
        
        task = self.tasks[task_id]
        
        return TaskResponse(
            task_id=task_id,
            status=task["status"],
            message=task.get("result", "Task wird verarbeitet"),
            result=json.dumps(task.get("result", {}))
        )
    
    async def ListAgents(self, request, context) -> AgentListResponse:
        """Liste alle verfügbaren Agenten auf"""
        agents = []
        
        for agent_id, agent_info in self.agents.items():
            agents.append(AgentInfo(
                id=agent_id,
                name=agent_info["name"],
                description=agent_info["description"],
                status=agent_info["status"],
                capabilities=agent_info["capabilities"]
            ))
        
        return AgentListResponse(agents=agents)
    
    async def HealthCheck(self, request, context) -> HealthCheckResponse:
        """Gesundheitscheck"""
        return HealthCheckResponse(
            status="healthy",
            message="EventFixTeam Server läuft",
            active_tasks=len([t for t in self.tasks.values() if t["status"] == TaskStatus.IN_PROGRESS]),
            total_tasks=len(self.tasks)
        )
    
    async def _process_task(self, task_id: str):
        """Verarbeite eine Aufgabe via AutoGen Orchestrator

        Der Reasoning Agent analysiert die Aufgabe, plant die nötigen
        Tool Calls und führt sie via MCP Server aus. Der Validator Agent
        prüft das Ergebnis.
        """
        task = self.tasks[task_id]

        try:
            task["status"] = TaskStatus.IN_PROGRESS
            task["started_at"] = datetime.utcnow().isoformat()

            # Orchestrator holen (lazy init)
            orchestrator = await self._get_orchestrator()

            # Task-spezifischen Prompt erstellen
            task_prompt = get_task_prompt(
                task_type=task["type"],
                parameters=task["parameters"]
            )

            # Vollständigen Task-Kontext zusammenstellen
            full_description = f"{task['description']}\n\n{task_prompt}"

            logger.info(f"Task {task_id}: Starte AutoGen Orchestrator für '{task['type']}'")

            # AutoGen Orchestrator aufrufen (ECHTE Ausführung!)
            result = await orchestrator.execute_task(
                task=full_description,
                context={
                    "task_id": task_id,
                    "task_type": task["type"],
                    "parameters": task["parameters"],
                    "created_at": task["created_at"]
                }
            )

            # Ergebnis auswerten
            if result.get("status") == "completed":
                task["status"] = TaskStatus.COMPLETED
                task["result"] = {
                    "output": result.get("result", ""),
                    "steps": result.get("steps", 0),
                    "tool_calls": result.get("tool_calls", []),
                    "agent": "reasoning_agent"
                }
                logger.info(
                    f"Task {task_id}: Abgeschlossen mit {result.get('steps', 0)} Schritten, "
                    f"{len(result.get('tool_calls', []))} Tool Calls"
                )
            else:
                task["status"] = TaskStatus.FAILED
                task["error"] = result.get("error", "Unbekannter Fehler")
                logger.warning(f"Task {task_id}: Fehlgeschlagen - {task['error']}")

            task["completed_at"] = datetime.utcnow().isoformat()

        except Exception as e:
            task["status"] = TaskStatus.FAILED
            task["error"] = str(e)
            task["completed_at"] = datetime.utcnow().isoformat()
            logger.error(f"Task {task_id}: Exception - {e}", exc_info=True)
    
    def _get_agent_for_task(self, task_type: str) -> Optional[Dict]:
        """Hole den passenden logischen Agenten für einen Task-Typ

        Der Reasoning Agent kann alle Task-Typen verarbeiten,
        aber für Kompatibilität ordnen wir sie auch logischen Agenten zu.
        """
        task_type_mapping = {
            # Code & File Operations
            "write_code": "code_writer",
            "read_code": "code_writer",
            "fix_code": "code_writer",
            "create_files": "code_writer",

            # Database Operations
            "migrate_database": "fix_migrator",
            "database_query": "fix_migrator",

            # Docker/Debug Operations
            "debug_docker": "debugger",
            "debug_redis": "debugger",
            "debug_postgres": "debugger",
            "container_restart": "debugger",
            "docker_compose_up": "debugger",

            # Testing Operations
            "playwright_tests": "tester",
            "run_tests": "tester",
            "test_functions": "tester",

            # Git Operations
            "git_status": "code_writer",
            "git_commit": "code_writer",

            # Package Management
            "npm_install": "code_writer",
            "npm_run": "code_writer",

            # Web/Search Operations
            "web_search": "reasoning_agent",
            "fetch_url": "reasoning_agent",

            # General/Fallback
            "general": "reasoning_agent",
            "analyze": "reasoning_agent"
        }

        agent_id = task_type_mapping.get(task_type, "reasoning_agent")
        return self.agents.get(agent_id)
    
    # NOTE: _execute_task() wurde entfernt.
    # Die Ausführung erfolgt jetzt vollständig über den AutoGen Orchestrator
    # in _process_task() via orchestrator.execute_task().
    #
    # Der Orchestrator:
    # 1. Lädt alle MCP Tools aus servers.json
    # 2. Der ReasoningAgent plant die nötigen Tool Calls
    # 3. Die Tools werden via MCP Server ausgeführt
    # 4. Der ValidatorAgent prüft das Ergebnis
    # 5. Bei "TASK_COMPLETE" ist die Aufgabe erledigt


async def serve(port: int = 50051, model: str = "gpt-4o"):
    """Starte den gRPC Server mit AutoGen Orchestrator

    Args:
        port: gRPC Server Port (default: 50051)
        model: LLM Model für den Orchestrator (default: gpt-4o)
    """
    server = grpc.aio.server()

    event_fix_team = EventFixTeamServer(model=model)
    add_EventFixTeamServicer_to_server(event_fix_team, server)

    server.add_insecure_port(f'[::]:{port}')

    logger.info(f"EventFixTeam Server gestartet auf Port {port}")
    logger.info(f"AutoGen Orchestrator Model: {model}")
    logger.info(f"Verfügbare Task-Typen: {list_task_types()}")
    await server.start()

    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Server wird heruntergefahren...")
        # Orchestrator cleanup wenn initialisiert
        if event_fix_team._orchestrator:
            await event_fix_team._orchestrator.shutdown()
        await server.stop(0)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='EventFixTeam gRPC Server')
    parser.add_argument('--port', type=int, default=50051, help='gRPC Server Port')
    parser.add_argument('--model', type=str, default='gpt-4o', help='LLM Model (gpt-4o, claude-3-opus, etc.)')
    parser.add_argument('--log-level', type=str, default='INFO', help='Log Level')
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    asyncio.run(serve(port=args.port, model=args.model))
