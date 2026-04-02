"""
Universal gRPC Adapter für bestehende MCP Agents.

Ermöglicht jedem Agent, als gRPC Worker zu starten ohne
den bestehenden Code zu ändern.

Usage:
    from shared.grpc_adapter import serve_as_grpc, AgentGRPCConfig

    config = AgentGRPCConfig(
        name="filesystem",
        port=50061,
        agent_runner=run_filesystem_agent,
        config_class=FilesystemAgentConfig
    )
    asyncio.run(serve_as_grpc(config))
"""
import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Any, Dict, List, Optional

import grpc
from grpc import aio

logger = logging.getLogger(__name__)


# ============================================================================
# Proto Message Classes (inline, da wir keine kompilierten protos haben)
# ============================================================================

class TaskStatus:
    """Task Status Enum"""
    PENDING = 0
    IN_PROGRESS = 1
    COMPLETED = 2
    FAILED = 3
    CANCELLED = 4


@dataclass
class TaskRequest:
    """Task-Anfrage"""
    task_id: str = ""
    description: str = ""
    task_type: str = ""
    parameters_json: str = "{}"
    timeout_seconds: int = 0


@dataclass
class TaskResponse:
    """Task-Antwort"""
    task_id: str = ""
    status: int = TaskStatus.PENDING
    message: str = ""
    result_json: str = "{}"
    duration_ms: int = 0
    tool_calls: List[Dict] = field(default_factory=list)


@dataclass
class TaskProgress:
    """Task-Fortschritt"""
    task_id: str = ""
    status: int = TaskStatus.PENDING
    message: str = ""
    progress_percent: int = 0
    current_step: str = ""
    current_tool: Optional[Dict] = None


@dataclass
class HealthResponse:
    """Health Check Antwort"""
    healthy: bool = True
    status: str = "ready"
    active_tasks: int = 0
    version: str = "1.0.0"


@dataclass
class AgentInfo:
    """Agent-Informationen"""
    name: str = ""
    description: str = ""
    version: str = "1.0.0"
    capabilities: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    grpc_port: int = 0


# ============================================================================
# Configuration
# ============================================================================

@dataclass
class AgentGRPCConfig:
    """Konfiguration für gRPC Agent Worker"""
    name: str                      # z.B. "filesystem"
    port: int                      # z.B. 50061
    agent_runner: Callable         # z.B. run_filesystem_agent
    config_class: Any              # z.B. FilesystemAgentConfig
    description: str = ""
    capabilities: List[str] = field(default_factory=list)
    version: str = "1.0.0"


# ============================================================================
# gRPC Service Implementation
# ============================================================================

class AgentWorkerServicer:
    """
    gRPC Service der bestehende Agent-Runner wrapped.

    Dieser Service erlaubt es, jeden bestehenden MCP Agent
    als gRPC Worker zu betreiben.
    """

    def __init__(self, config: AgentGRPCConfig):
        self.config = config
        self.active_tasks: Dict[str, Dict] = {}
        self._lock = asyncio.Lock()
        self._task_counter = 0

    async def ExecuteTask(self, request_data: Dict, context) -> Dict:
        """Führt Task via bestehenden Agent aus"""
        start_time = time.time()

        # Task ID generieren wenn nicht vorhanden
        task_id = request_data.get("task_id") or str(uuid.uuid4())
        description = request_data.get("description", "")
        parameters_json = request_data.get("parameters_json", "{}")

        logger.info(f"[{self.config.name}] Task {task_id} gestartet: {description[:100]}...")

        try:
            # Parse parameters
            try:
                parameters = json.loads(parameters_json) if parameters_json else {}
            except json.JSONDecodeError:
                parameters = {}

            # Track active task
            async with self._lock:
                self.active_tasks[task_id] = {
                    "status": TaskStatus.IN_PROGRESS,
                    "start_time": start_time
                }

            # Agent Config erstellen (passend zum Agent-Typ)
            session_id = f"{self.config.name}_{task_id}"
            agent_config = self.config.config_class(
                task=description,
                session_id=session_id,
                keepalive=False  # Task beenden nach Abschluss
            )

            # Bestehenden Agent Runner aufrufen
            await self.config.agent_runner(agent_config)

            duration_ms = int((time.time() - start_time) * 1000)

            # Clean up
            async with self._lock:
                if task_id in self.active_tasks:
                    del self.active_tasks[task_id]

            logger.info(f"[{self.config.name}] Task {task_id} abgeschlossen in {duration_ms}ms")

            return {
                "task_id": task_id,
                "status": TaskStatus.COMPLETED,
                "message": "Task erfolgreich ausgeführt",
                "result_json": json.dumps({"success": True, "session_id": session_id}),
                "duration_ms": duration_ms,
                "tool_calls": []
            }

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(f"[{self.config.name}] Task {task_id} fehlgeschlagen: {e}")

            # Clean up
            async with self._lock:
                if task_id in self.active_tasks:
                    del self.active_tasks[task_id]

            return {
                "task_id": task_id,
                "status": TaskStatus.FAILED,
                "message": str(e),
                "result_json": json.dumps({"error": str(e)}),
                "duration_ms": duration_ms,
                "tool_calls": []
            }

    async def ExecuteTaskStream(self, request_data: Dict, context):
        """Führt Task aus mit Fortschritts-Streaming"""
        task_id = request_data.get("task_id") or str(uuid.uuid4())
        description = request_data.get("description", "")

        # Initial progress
        yield {
            "task_id": task_id,
            "status": TaskStatus.IN_PROGRESS,
            "message": "Task gestartet",
            "progress_percent": 0,
            "current_step": "Initialisierung"
        }

        # Execute task (simplified - real implementation would stream from agent)
        result = await self.ExecuteTask(request_data, context)

        # Final progress
        yield {
            "task_id": task_id,
            "status": result["status"],
            "message": result["message"],
            "progress_percent": 100,
            "current_step": "Abgeschlossen"
        }

    async def HealthCheck(self, request_data: Dict, context) -> Dict:
        """Health Check"""
        return {
            "healthy": True,
            "status": "ready" if len(self.active_tasks) == 0 else "busy",
            "active_tasks": len(self.active_tasks),
            "version": self.config.version
        }

    async def GetAgentInfo(self, request_data: Dict, context) -> Dict:
        """Hole Agent-Informationen"""
        return {
            "name": self.config.name,
            "description": self.config.description or f"{self.config.name} MCP Agent",
            "version": self.config.version,
            "capabilities": self.config.capabilities,
            "tools": [],  # Könnte von Agent geladen werden
            "grpc_port": self.config.port
        }


# ============================================================================
# JSON-RPC over gRPC (simplified implementation without proto compilation)
# ============================================================================

class JsonRpcHandler:
    """
    JSON-RPC Handler für gRPC.

    Da wir die proto-Dateien nicht kompilieren wollen, verwenden wir
    ein einfaches JSON-RPC Protokoll über gRPC-Streams.
    """

    def __init__(self, servicer: AgentWorkerServicer):
        self.servicer = servicer

    async def handle_request(self, method: str, params: Dict, context) -> Dict:
        """Verarbeitet eine JSON-RPC Anfrage"""
        methods = {
            "ExecuteTask": self.servicer.ExecuteTask,
            "HealthCheck": self.servicer.HealthCheck,
            "GetAgentInfo": self.servicer.GetAgentInfo,
        }

        handler = methods.get(method)
        if not handler:
            return {"error": f"Unknown method: {method}"}

        return await handler(params, context)


# ============================================================================
# gRPC Server (using grpcio reflection for discovery)
# ============================================================================

async def serve_as_grpc(config: AgentGRPCConfig):
    """
    Startet bestehenden Agent als gRPC Worker.

    Args:
        config: AgentGRPCConfig mit Agent-Konfiguration
    """
    servicer = AgentWorkerServicer(config)
    handler = JsonRpcHandler(servicer)

    # Da wir keine kompilierten protos haben, verwenden wir
    # einen einfachen TCP-Server mit JSON-Protokoll
    server = await asyncio.start_server(
        lambda r, w: _handle_connection(r, w, handler),
        '0.0.0.0',
        config.port
    )

    addr = server.sockets[0].getsockname()
    logger.info(f"🚀 {config.name} gRPC Worker auf Port {addr[1]}")
    print(f"🚀 {config.name} gRPC Worker gestartet auf Port {addr[1]}")

    async with server:
        await server.serve_forever()


async def _handle_connection(reader: asyncio.StreamReader,
                             writer: asyncio.StreamWriter,
                             handler: JsonRpcHandler):
    """Verarbeitet eine TCP-Verbindung"""
    addr = writer.get_extra_info('peername')
    logger.debug(f"Verbindung von {addr}")

    try:
        while True:
            # Lese Nachrichtenlänge (4 bytes, big-endian)
            length_bytes = await reader.readexactly(4)
            if not length_bytes:
                break

            length = int.from_bytes(length_bytes, 'big')
            if length > 10 * 1024 * 1024:  # Max 10MB
                logger.warning(f"Nachricht zu groß: {length} bytes")
                break

            # Lese JSON-Nachricht
            data = await reader.readexactly(length)
            request = json.loads(data.decode('utf-8'))

            # Verarbeite Anfrage
            method = request.get("method", "")
            params = request.get("params", {})
            request_id = request.get("id", 1)

            result = await handler.handle_request(method, params, None)

            # Sende Antwort
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result
            }
            response_bytes = json.dumps(response).encode('utf-8')
            writer.write(len(response_bytes).to_bytes(4, 'big'))
            writer.write(response_bytes)
            await writer.drain()

    except asyncio.IncompleteReadError:
        logger.debug(f"Verbindung geschlossen von {addr}")
    except Exception as e:
        logger.error(f"Fehler bei Verbindung von {addr}: {e}")
    finally:
        writer.close()
        await writer.wait_closed()


# ============================================================================
# Client für Orchestrator
# ============================================================================

class AgentWorkerClient:
    """
    Client zum Aufrufen von Agent Worker Servern.

    Usage:
        client = AgentWorkerClient("localhost", 50061)
        result = await client.execute_task("Erstelle eine Datei test.txt")
    """

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._request_id = 0

    async def connect(self):
        """Verbindet zum Server"""
        self._reader, self._writer = await asyncio.open_connection(
            self.host, self.port
        )

    async def close(self):
        """Schließt die Verbindung"""
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()
            self._writer = None
            self._reader = None

    async def _send_request(self, method: str, params: Dict) -> Dict:
        """Sendet eine JSON-RPC Anfrage"""
        if not self._writer:
            await self.connect()

        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params
        }

        # Sende Anfrage
        request_bytes = json.dumps(request).encode('utf-8')
        self._writer.write(len(request_bytes).to_bytes(4, 'big'))
        self._writer.write(request_bytes)
        await self._writer.drain()

        # Lese Antwort
        length_bytes = await self._reader.readexactly(4)
        length = int.from_bytes(length_bytes, 'big')
        response_bytes = await self._reader.readexactly(length)
        response = json.loads(response_bytes.decode('utf-8'))

        return response.get("result", {})

    async def execute_task(
        self,
        description: str,
        task_type: str = "",
        parameters: Optional[Dict] = None,
        timeout_seconds: int = 0
    ) -> Dict:
        """
        Führt einen Task aus.

        Args:
            description: Task-Beschreibung
            task_type: Optionaler Task-Typ
            parameters: Optionale Parameter
            timeout_seconds: Timeout (0 = default)

        Returns:
            Task-Ergebnis als Dict
        """
        return await self._send_request("ExecuteTask", {
            "description": description,
            "task_type": task_type,
            "parameters_json": json.dumps(parameters or {}),
            "timeout_seconds": timeout_seconds
        })

    async def health_check(self) -> Dict:
        """Health Check"""
        return await self._send_request("HealthCheck", {})

    async def get_agent_info(self) -> Dict:
        """Hole Agent-Informationen"""
        return await self._send_request("GetAgentInfo", {})


# ============================================================================
# Convenience Functions
# ============================================================================

async def start_grpc_worker(
    name: str,
    port: int,
    agent_runner: Callable,
    config_class: Any,
    description: str = "",
    capabilities: Optional[List[str]] = None
):
    """
    Convenience Function zum Starten eines gRPC Workers.

    Args:
        name: Agent-Name (z.B. "filesystem")
        port: gRPC Port
        agent_runner: Async Function zum Ausführen des Agents
        config_class: Pydantic Config-Klasse für den Agent
        description: Optionale Beschreibung
        capabilities: Optionale Liste von Fähigkeiten
    """
    config = AgentGRPCConfig(
        name=name,
        port=port,
        agent_runner=agent_runner,
        config_class=config_class,
        description=description,
        capabilities=capabilities or []
    )
    await serve_as_grpc(config)


# ============================================================================
# CLI Entry Point
# ============================================================================

if __name__ == "__main__":
    # Test-Server
    import argparse

    parser = argparse.ArgumentParser(description="gRPC Adapter Test")
    parser.add_argument("--port", type=int, default=50061, help="Port")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Dummy Agent für Test
    async def dummy_runner(config):
        print(f"Dummy Agent ausgeführt: {config.task}")
        await asyncio.sleep(1)

    class DummyConfig:
        def __init__(self, task, session_id, keepalive=False):
            self.task = task
            self.session_id = session_id
            self.keepalive = keepalive

    config = AgentGRPCConfig(
        name="test",
        port=args.port,
        agent_runner=dummy_runner,
        config_class=DummyConfig,
        description="Test Agent"
    )

    print(f"Starte Test-Server auf Port {args.port}...")
    asyncio.run(serve_as_grpc(config))
