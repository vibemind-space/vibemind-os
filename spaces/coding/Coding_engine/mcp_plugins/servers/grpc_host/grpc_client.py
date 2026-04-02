"""
gRPC Client für EventFixTeam
Wird von Agents verwendet, um mit dem gRPC Server zu kommunizieren
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path

import grpc
from grpc import aio

# Importiere generierte gRPC-Klassen
import sys
sys.path.insert(0, str(Path(__file__).parent / "proto"))
import agent_service_pb2
import agent_service_pb2_grpc

logger = logging.getLogger(__name__)


class EventFixTeamClient:
    """gRPC Client für EventFixTeam"""
    
    def __init__(self, host: str = "localhost", port: int = 50051):
        """
        Client initialisieren
        
        Args:
            host: Host des gRPC Servers
            port: Port des gRPC Servers
        """
        self.host = host
        self.port = port
        self.channel = None
        self.stub = None
        self._connected = False
    
    async def connect(self):
        """Verbindung zum Server herstellen"""
        if self._connected:
            return
        
        self.channel = aio.insecure_channel(f'{self.host}:{self.port}')
        self.stub = agent_service_pb2_grpc.EventFixTeamStub(self.channel)
        self._connected = True
        logger.info(f"Verbunden mit gRPC Server {self.host}:{self.port}")
    
    async def disconnect(self):
        """Verbindung zum Server trennen"""
        if self.channel:
            await self.channel.close()
            self._connected = False
            logger.info("Verbindung zum gRPC Server getrennt")
    
    async def _ensure_connected(self):
        """Stellt sicher, dass eine Verbindung besteht"""
        if not self._connected:
            await self.connect()
    
    # File Operations
    
    async def write_file(self, filepath: str, content: str, encoding: str = "utf-8") -> Dict[str, Any]:
        """
        Datei schreiben
        
        Args:
            filepath: Pfad zur Datei
            content: Inhalt der Datei
            encoding: Encoding der Datei
        
        Returns:
            Dict mit success, output, logs, error
        """
        await self._ensure_connected()
        
        request = agent_service_pb2.WriteFileRequest(
            filepath=filepath,
            content=content,
            encoding=encoding
        )
        
        response = await self.stub.WriteFile(request)
        
        return {
            "success": response.success,
            "output": response.output,
            "logs": response.logs,
            "error": response.error
        }
    
    async def read_file(self, filepath: str, encoding: str = "utf-8") -> Dict[str, Any]:
        """
        Datei lesen
        
        Args:
            filepath: Pfad zur Datei
            encoding: Encoding der Datei
        
        Returns:
            Dict mit success, content, logs, error
        """
        await self._ensure_connected()
        
        request = agent_service_pb2.ReadFileRequest(
            filepath=filepath,
            encoding=encoding
        )
        
        response = await self.stub.ReadFile(request)
        
        return {
            "success": response.success,
            "content": response.content,
            "logs": response.logs,
            "error": response.error
        }
    
    async def list_files(self, directory: str, recursive: bool = False) -> Dict[str, Any]:
        """
        Dateien auflisten
        
        Args:
            directory: Verzeichnis
            recursive: Rekursiv auflisten
        
        Returns:
            Dict mit success, files, logs, error
        """
        await self._ensure_connected()
        
        request = agent_service_pb2.ListFilesRequest(
            directory=directory,
            recursive=recursive
        )
        
        response = await self.stub.ListFiles(request)
        
        return {
            "success": response.success,
            "files": list(response.files),
            "logs": response.logs,
            "error": response.error
        }
    
    # Docker Operations
    
    async def docker_build(self, dockerfile_path: str, context_path: str = ".", tag: Optional[str] = None) -> Dict[str, Any]:
        """
        Docker Image bauen
        
        Args:
            dockerfile_path: Pfad zum Dockerfile
            context_path: Build-Kontext
            tag: Image Tag
        
        Returns:
            Dict mit success, output, logs, error
        """
        await self._ensure_connected()
        
        request = agent_service_pb2.DockerBuildRequest(
            dockerfile_path=dockerfile_path,
            context_path=context_path,
            tag=tag if tag else ""
        )
        
        response = await self.stub.DockerBuild(request)
        
        return {
            "success": response.success,
            "output": response.output,
            "logs": response.logs,
            "error": response.error
        }
    
    async def docker_run(self, image: str, command: Optional[str] = None, ports: Optional[List[str]] = None,
                        volumes: Optional[List[str]] = None, environment: Optional[List[str]] = None,
                        detach: bool = True, name: Optional[str] = None) -> Dict[str, Any]:
        """
        Docker Container starten
        
        Args:
            image: Docker Image
            command: Command
            ports: Ports
            volumes: Volumes
            environment: Environment Variables
            detach: Detached Mode
            name: Container Name
        
        Returns:
            Dict mit success, output, logs, error
        """
        await self._ensure_connected()
        
        request = agent_service_pb2.DockerRunRequest(
            image=image,
            command=command if command else "",
            ports=ports if ports else [],
            volumes=volumes if volumes else [],
            environment=environment if environment else [],
            detach=detach,
            name=name if name else ""
        )
        
        response = await self.stub.DockerRun(request)
        
        return {
            "success": response.success,
            "output": response.output,
            "logs": response.logs,
            "error": response.error
        }
    
    async def docker_stop(self, container_id: str) -> Dict[str, Any]:
        """
        Docker Container stoppen
        
        Args:
            container_id: Container ID oder Name
        
        Returns:
            Dict mit success, output, logs, error
        """
        await self._ensure_connected()
        
        request = agent_service_pb2.DockerStopRequest(
            container_id=container_id
        )
        
        response = await self.stub.DockerStop(request)
        
        return {
            "success": response.success,
            "output": response.output,
            "logs": response.logs,
            "error": response.error
        }
    
    async def docker_logs(self, container_id: str, tail: Optional[int] = None, follow: bool = False) -> Dict[str, Any]:
        """
        Docker Logs abrufen
        
        Args:
            container_id: Container ID oder Name
            tail: Anzahl der letzten Zeilen
            follow: Follow Logs
        
        Returns:
            Dict mit success, output, logs, error
        """
        await self._ensure_connected()
        
        request = agent_service_pb2.DockerLogsRequest(
            container_id=container_id,
            tail=tail if tail else 0,
            follow=follow
        )
        
        response = await self.stub.DockerLogs(request)
        
        return {
            "success": response.success,
            "output": response.output,
            "logs": response.logs,
            "error": response.error
        }
    
    async def docker_compose_up(self, compose_file: str, detached: bool = True) -> Dict[str, Any]:
        """
        Docker Compose starten
        
        Args:
            compose_file: Pfad zur docker-compose.yml
            detached: Detached Mode
        
        Returns:
            Dict mit success, output, logs, error
        """
        await self._ensure_connected()
        
        request = agent_service_pb2.DockerComposeUpRequest(
            compose_file=compose_file,
            detached=detached
        )
        
        response = await self.stub.DockerComposeUp(request)
        
        return {
            "success": response.success,
            "output": response.output,
            "logs": response.logs,
            "error": response.error
        }
    
    async def docker_compose_down(self, compose_file: str) -> Dict[str, Any]:
        """
        Docker Compose stoppen
        
        Args:
            compose_file: Pfad zur docker-compose.yml
        
        Returns:
            Dict mit success, output, logs, error
        """
        await self._ensure_connected()
        
        request = agent_service_pb2.DockerComposeDownRequest(
            compose_file=compose_file
        )
        
        response = await self.stub.DockerComposeDown(request)
        
        return {
            "success": response.success,
            "output": response.output,
            "logs": response.logs,
            "error": response.error
        }
    
    # Redis Operations
    
    async def redis_set(self, key: str, value: str, expiry: Optional[int] = None) -> Dict[str, Any]:
        """
        Redis Set
        
        Args:
            key: Key
            value: Value
            expiry: Expiry in Sekunden
        
        Returns:
            Dict mit success, output, logs, error
        """
        await self._ensure_connected()
        
        request = agent_service_pb2.RedisSetRequest(
            key=key,
            value=value,
            expiry=expiry if expiry else 0
        )
        
        response = await self.stub.RedisSet(request)
        
        return {
            "success": response.success,
            "output": response.output,
            "logs": response.logs,
            "error": response.error
        }
    
    async def redis_get(self, key: str) -> Dict[str, Any]:
        """
        Redis Get
        
        Args:
            key: Key
        
        Returns:
            Dict mit success, value, logs, error
        """
        await self._ensure_connected()
        
        request = agent_service_pb2.RedisGetRequest(
            key=key
        )
        
        response = await self.stub.RedisGet(request)
        
        return {
            "success": response.success,
            "value": response.value,
            "logs": response.logs,
            "error": response.error
        }
    
    async def redis_delete(self, key: str) -> Dict[str, Any]:
        """
        Redis Delete
        
        Args:
            key: Key
        
        Returns:
            Dict mit success, output, logs, error
        """
        await self._ensure_connected()
        
        request = agent_service_pb2.RedisDeleteRequest(
            key=key
        )
        
        response = await self.stub.RedisDelete(request)
        
        return {
            "success": response.success,
            "output": response.output,
            "logs": response.logs,
            "error": response.error
        }
    
    async def redis_keys(self, pattern: str = "*") -> Dict[str, Any]:
        """
        Redis Keys
        
        Args:
            pattern: Pattern für Keys
        
        Returns:
            Dict mit success, keys, logs, error
        """
        await self._ensure_connected()
        
        request = agent_service_pb2.RedisKeysRequest(
            pattern=pattern
        )
        
        response = await self.stub.RedisKeys(request)
        
        return {
            "success": response.success,
            "keys": list(response.keys),
            "logs": response.logs,
            "error": response.error
        }
    
    # PostgreSQL Operations
    
    async def postgres_execute(self, query: str, params: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        PostgreSQL Execute
        
        Args:
            query: SQL Query
            params: Parameter
        
        Returns:
            Dict mit success, output, logs, error
        """
        await self._ensure_connected()
        
        request = agent_service_pb2.PostgresExecuteRequest(
            query=query,
            params=params if params else []
        )
        
        response = await self.stub.PostgresExecute(request)
        
        return {
            "success": response.success,
            "output": response.output,
            "logs": response.logs,
            "error": response.error
        }
    
    async def postgres_query(self, query: str, params: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        PostgreSQL Query
        
        Args:
            query: SQL Query
            params: Parameter
        
        Returns:
            Dict mit success, rows, columns, logs, error
        """
        await self._ensure_connected()
        
        request = agent_service_pb2.PostgresQueryRequest(
            query=query,
            params=params if params else []
        )
        
        response = await self.stub.PostgresQuery(request)
        
        return {
            "success": response.success,
            "rows": [list(row.values) for row in response.rows],
            "columns": list(response.columns),
            "logs": response.logs,
            "error": response.error
        }
    
    async def postgres_get_logs(self, log_type: str = "all", limit: int = 100) -> Dict[str, Any]:
        """
        PostgreSQL Logs abrufen
        
        Args:
            log_type: Log-Typ (all, error, slow, etc.)
            limit: Maximale Anzahl von Logs
        
        Returns:
            Dict mit success, logs, output, error
        """
        await self._ensure_connected()
        
        request = agent_service_pb2.PostgresGetLogsRequest(
            log_type=log_type,
            limit=limit
        )
        
        response = await self.stub.PostgresGetLogs(request)
        
        return {
            "success": response.success,
            "logs": response.logs,
            "output": response.output,
            "error": response.error
        }
    
    # Playwright Operations
    
    async def playwright_start(self) -> Dict[str, Any]:
        """
        Playwright starten
        
        Returns:
            Dict mit success, output, logs, error
        """
        await self._ensure_connected()
        
        request = agent_service_pb2.PlaywrightStartRequest(
            browser_type="chromium"
        )
        
        response = await self.stub.PlaywrightStart(request)
        
        return {
            "success": response.success,
            "output": response.output,
            "logs": response.logs,
            "error": response.error
        }
    
    async def playwright_stop(self) -> Dict[str, Any]:
        """
        Playwright stoppen
        
        Returns:
            Dict mit success, output, logs, error
        """
        await self._ensure_connected()
        
        request = agent_service_pb2.PlaywrightStopRequest()
        
        response = await self.stub.PlaywrightStop(request)
        
        return {
            "success": response.success,
            "output": response.output,
            "logs": response.logs,
            "error": response.error
        }
    
    async def playwright_navigate(self, url: str) -> Dict[str, Any]:
        """
        Playwright Navigate
        
        Args:
            url: URL
        
        Returns:
            Dict mit success, output, screenshot, logs, error
        """
        await self._ensure_connected()
        
        request = agent_service_pb2.PlaywrightNavigateRequest(
            url=url
        )
        
        response = await self.stub.PlaywrightNavigate(request)
        
        return {
            "success": response.success,
            "output": response.output,
            "screenshot": response.screenshot,
            "logs": response.logs,
            "error": response.error
        }
    
    async def playwright_click(self, selector: str) -> Dict[str, Any]:
        """
        Playwright Click
        
        Args:
            selector: CSS Selector
        
        Returns:
            Dict mit success, output, screenshot, logs, error
        """
        await self._ensure_connected()
        
        request = agent_service_pb2.PlaywrightClickRequest(
            selector=selector
        )
        
        response = await self.stub.PlaywrightClick(request)
        
        return {
            "success": response.success,
            "output": response.output,
            "screenshot": response.screenshot,
            "logs": response.logs,
            "error": response.error
        }
    
    async def playwright_fill(self, selector: str, value: str) -> Dict[str, Any]:
        """
        Playwright Fill
        
        Args:
            selector: CSS Selector
            value: Wert
        
        Returns:
            Dict mit success, output, screenshot, logs, error
        """
        await self._ensure_connected()
        
        request = agent_service_pb2.PlaywrightFillRequest(
            selector=selector,
            value=value
        )
        
        response = await self.stub.PlaywrightFill(request)
        
        return {
            "success": response.success,
            "output": response.output,
            "screenshot": response.screenshot,
            "logs": response.logs,
            "error": response.error
        }
    
    async def playwright_get_text(self, selector: str) -> Dict[str, Any]:
        """
        Playwright GetText
        
        Args:
            selector: CSS Selector
        
        Returns:
            Dict mit success, text, logs, error
        """
        await self._ensure_connected()
        
        request = agent_service_pb2.PlaywrightGetTextRequest(
            selector=selector
        )
        
        response = await self.stub.PlaywrightGetText(request)
        
        return {
            "success": response.success,
            "text": response.text,
            "logs": response.logs,
            "error": response.error
        }
    
    async def playwright_screenshot(self, filename: Optional[str] = None) -> Dict[str, Any]:
        """
        Playwright Screenshot
        
        Args:
            filename: Filename für Screenshot
        
        Returns:
            Dict mit success, output, screenshot, logs, error
        """
        await self._ensure_connected()
        
        request = agent_service_pb2.PlaywrightScreenshotRequest(
            filename=filename if filename else ""
        )
        
        response = await self.stub.PlaywrightScreenshot(request)
        
        return {
            "success": response.success,
            "output": response.output,
            "screenshot": response.screenshot,
            "logs": response.logs,
            "error": response.error
        }
    
    async def playwright_run_test(self, test_steps: str) -> Dict[str, Any]:
        """
        Playwright RunTest
        
        Args:
            test_steps: JSON-String mit Test-Schritten
        
        Returns:
            Dict mit success, output, report, logs, error
        """
        await self._ensure_connected()
        
        request = agent_service_pb2.PlaywrightRunTestRequest(
            test_steps=test_steps
        )
        
        response = await self.stub.PlaywrightRunTest(request)
        
        return {
            "success": response.success,
            "output": response.output,
            "report": response.report,
            "logs": response.logs,
            "error": response.error
        }


# Context Manager für automatische Verbindung

class EventFixTeamClientContext:
    """Context Manager für EventFixTeamClient"""
    
    def __init__(self, host: str = "localhost", port: int = 50051):
        self.host = host
        self.port = port
        self.client = None
    
    async def __aenter__(self):
        self.client = EventFixTeamClient(self.host, self.port)
        await self.client.connect()
        return self.client
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.disconnect()
