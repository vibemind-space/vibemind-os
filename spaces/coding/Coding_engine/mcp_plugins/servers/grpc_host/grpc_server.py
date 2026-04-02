"""
gRPC Server für EventFixTeam
Bietet RPC-Methoden für Agent-Operationen
"""

import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor

import grpc
from grpc import aio

# Importiere generierte gRPC-Klassen
import sys
sys.path.insert(0, str(Path(__file__).parent / "proto"))
import agent_service_pb2
import agent_service_pb2_grpc

# Importiere Tools
from tools.file_write_tool import FileWriteTool
from tools.docker_tool import DockerTool
from tools.redis_tool import RedisTool
from tools.postgres_tool import PostgresTool
from tools.playwright_tool import PlaywrightTool

logger = logging.getLogger(__name__)


class EventFixTeamServicer(agent_service_pb2_grpc.EventFixTeamServicer):
    """gRPC Servicer für EventFixTeam"""
    
    def __init__(self, base_dir: str = "."):
        """
        Servicer initialisieren
        
        Args:
            base_dir: Basisverzeichnis für das Projekt
        """
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(exist_ok=True)
        
        # Tools initialisieren
        self.file_write_tool = FileWriteTool(base_dir)
        self.docker_tool = DockerTool(base_dir)
        self.redis_tool = RedisTool(base_dir)
        self.postgres_tool = PostgresTool(base_dir)
        self.playwright_tool = PlaywrightTool(base_dir)
        
        logger.info("EventFixTeam Servicer initialisiert")
    
    async def WriteFile(self, request, context):
        """
        Datei schreiben
        
        Args:
            request: WriteFileRequest
            context: gRPC Context
        
        Returns:
            WriteFileResponse
        """
        try:
            logger.info(f"WriteFile: {request.filepath}")
            
            result = self.file_write_tool.write_file(
                filepath=request.filepath,
                content=request.content,
                encoding=request.encoding if request.encoding else "utf-8"
            )
            
            response = agent_service_pb2.WriteFileResponse(
                success=result.get("success", False),
                output=result.get("output", ""),
                logs=result.get("logs", ""),
                error=result.get("error", "")
            )
            
            return response
        except Exception as e:
            logger.error(f"Fehler in WriteFile: {e}")
            return agent_service_pb2.WriteFileResponse(
                success=False,
                error=str(e),
                logs=""
            )
    
    async def ReadFile(self, request, context):
        """
        Datei lesen
        
        Args:
            request: ReadFileRequest
            context: gRPC Context
        
        Returns:
            ReadFileResponse
        """
        try:
            logger.info(f"ReadFile: {request.filepath}")
            
            result = self.file_write_tool.read_file(
                filepath=request.filepath,
                encoding=request.encoding if request.encoding else "utf-8"
            )
            
            response = agent_service_pb2.ReadFileResponse(
                success=result.get("success", False),
                content=result.get("content", ""),
                logs=result.get("logs", ""),
                error=result.get("error", "")
            )
            
            return response
        except Exception as e:
            logger.error(f"Fehler in ReadFile: {e}")
            return agent_service_pb2.ReadFileResponse(
                success=False,
                error=str(e),
                logs=""
            )
    
    async def ListFiles(self, request, context):
        """
        Dateien auflisten
        
        Args:
            request: ListFilesRequest
            context: gRPC Context
        
        Returns:
            ListFilesResponse
        """
        try:
            logger.info(f"ListFiles: {request.directory}")
            
            result = self.file_write_tool.list_files(
                directory=request.directory,
                recursive=request.recursive
            )
            
            response = agent_service_pb2.ListFilesResponse(
                success=result.get("success", False),
                files=result.get("files", []),
                logs=result.get("logs", ""),
                error=result.get("error", "")
            )
            
            return response
        except Exception as e:
            logger.error(f"Fehler in ListFiles: {e}")
            return agent_service_pb2.ListFilesResponse(
                success=False,
                error=str(e),
                logs=""
            )
    
    async def DockerBuild(self, request, context):
        """
        Docker Image bauen
        
        Args:
            request: DockerBuildRequest
            context: gRPC Context
        
        Returns:
            DockerBuildResponse
        """
        try:
            logger.info(f"DockerBuild: {request.dockerfile_path}")
            
            result = self.docker_tool.build(
                dockerfile_path=request.dockerfile_path,
                context_path=request.context_path if request.context_path else ".",
                tag=request.tag if request.tag else None
            )
            
            response = agent_service_pb2.DockerBuildResponse(
                success=result.get("success", False),
                output=result.get("output", ""),
                logs=result.get("logs", ""),
                error=result.get("error", "")
            )
            
            return response
        except Exception as e:
            logger.error(f"Fehler in DockerBuild: {e}")
            return agent_service_pb2.DockerBuildResponse(
                success=False,
                error=str(e),
                logs=""
            )
    
    async def DockerRun(self, request, context):
        """
        Docker Container starten
        
        Args:
            request: DockerRunRequest
            context: gRPC Context
        
        Returns:
            DockerRunResponse
        """
        try:
            logger.info(f"DockerRun: {request.image}")
            
            result = self.docker_tool.run(
                image=request.image,
                command=request.command if request.command else None,
                ports=request.ports if request.ports else None,
                volumes=request.volumes if request.volumes else None,
                environment=request.environment if request.environment else None,
                detach=request.detach,
                name=request.name if request.name else None
            )
            
            response = agent_service_pb2.DockerRunResponse(
                success=result.get("success", False),
                output=result.get("output", ""),
                logs=result.get("logs", ""),
                error=result.get("error", "")
            )
            
            return response
        except Exception as e:
            logger.error(f"Fehler in DockerRun: {e}")
            return agent_service_pb2.DockerRunResponse(
                success=False,
                error=str(e),
                logs=""
            )
    
    async def DockerStop(self, request, context):
        """
        Docker Container stoppen
        
        Args:
            request: DockerStopRequest
            context: gRPC Context
        
        Returns:
            DockerStopResponse
        """
        try:
            logger.info(f"DockerStop: {request.container_id}")
            
            result = self.docker_tool.stop(
                container_id=request.container_id
            )
            
            response = agent_service_pb2.DockerStopResponse(
                success=result.get("success", False),
                output=result.get("output", ""),
                logs=result.get("logs", ""),
                error=result.get("error", "")
            )
            
            return response
        except Exception as e:
            logger.error(f"Fehler in DockerStop: {e}")
            return agent_service_pb2.DockerStopResponse(
                success=False,
                error=str(e),
                logs=""
            )
    
    async def DockerLogs(self, request, context):
        """
        Docker Logs abrufen
        
        Args:
            request: DockerLogsRequest
            context: gRPC Context
        
        Returns:
            DockerLogsResponse
        """
        try:
            logger.info(f"DockerLogs: {request.container_id}")
            
            result = self.docker_tool.logs(
                container_id=request.container_id,
                tail=request.tail if request.tail else None,
                follow=request.follow
            )
            
            response = agent_service_pb2.DockerLogsResponse(
                success=result.get("success", False),
                output=result.get("output", ""),
                logs=result.get("logs", ""),
                error=result.get("error", "")
            )
            
            return response
        except Exception as e:
            logger.error(f"Fehler in DockerLogs: {e}")
            return agent_service_pb2.DockerLogsResponse(
                success=False,
                error=str(e),
                logs=""
            )
    
    async def DockerComposeUp(self, request, context):
        """
        Docker Compose starten
        
        Args:
            request: DockerComposeUpRequest
            context: gRPC Context
        
        Returns:
            DockerComposeUpResponse
        """
        try:
            logger.info(f"DockerComposeUp: {request.compose_file}")
            
            result = self.docker_tool.compose_up(
                compose_file=request.compose_file,
                detached=request.detached
            )
            
            response = agent_service_pb2.DockerComposeUpResponse(
                success=result.get("success", False),
                output=result.get("output", ""),
                logs=result.get("logs", ""),
                error=result.get("error", "")
            )
            
            return response
        except Exception as e:
            logger.error(f"Fehler in DockerComposeUp: {e}")
            return agent_service_pb2.DockerComposeUpResponse(
                success=False,
                error=str(e),
                logs=""
            )
    
    async def DockerComposeDown(self, request, context):
        """
        Docker Compose stoppen
        
        Args:
            request: DockerComposeDownRequest
            context: gRPC Context
        
        Returns:
            DockerComposeDownResponse
        """
        try:
            logger.info(f"DockerComposeDown: {request.compose_file}")
            
            result = self.docker_tool.compose_down(
                compose_file=request.compose_file
            )
            
            response = agent_service_pb2.DockerComposeDownResponse(
                success=result.get("success", False),
                output=result.get("output", ""),
                logs=result.get("logs", ""),
                error=result.get("error", "")
            )
            
            return response
        except Exception as e:
            logger.error(f"Fehler in DockerComposeDown: {e}")
            return agent_service_pb2.DockerComposeDownResponse(
                success=False,
                error=str(e),
                logs=""
            )
    
    async def RedisSet(self, request, context):
        """
        Redis Set
        
        Args:
            request: RedisSetRequest
            context: gRPC Context
        
        Returns:
            RedisSetResponse
        """
        try:
            logger.info(f"RedisSet: {request.key}")
            
            result = self.redis_tool.set(
                key=request.key,
                value=request.value,
                expiry=request.expiry if request.expiry else None
            )
            
            response = agent_service_pb2.RedisSetResponse(
                success=result.get("success", False),
                output=result.get("output", ""),
                logs=result.get("logs", ""),
                error=result.get("error", "")
            )
            
            return response
        except Exception as e:
            logger.error(f"Fehler in RedisSet: {e}")
            return agent_service_pb2.RedisSetResponse(
                success=False,
                error=str(e),
                logs=""
            )
    
    async def RedisGet(self, request, context):
        """
        Redis Get
        
        Args:
            request: RedisGetRequest
            context: gRPC Context
        
        Returns:
            RedisGetResponse
        """
        try:
            logger.info(f"RedisGet: {request.key}")
            
            result = self.redis_tool.get(
                key=request.key
            )
            
            response = agent_service_pb2.RedisGetResponse(
                success=result.get("success", False),
                value=result.get("value", ""),
                logs=result.get("logs", ""),
                error=result.get("error", "")
            )
            
            return response
        except Exception as e:
            logger.error(f"Fehler in RedisGet: {e}")
            return agent_service_pb2.RedisGetResponse(
                success=False,
                error=str(e),
                logs=""
            )
    
    async def RedisDelete(self, request, context):
        """
        Redis Delete
        
        Args:
            request: RedisDeleteRequest
            context: gRPC Context
        
        Returns:
            RedisDeleteResponse
        """
        try:
            logger.info(f"RedisDelete: {request.key}")
            
            result = self.redis_tool.delete(
                key=request.key
            )
            
            response = agent_service_pb2.RedisDeleteResponse(
                success=result.get("success", False),
                output=result.get("output", ""),
                logs=result.get("logs", ""),
                error=result.get("error", "")
            )
            
            return response
        except Exception as e:
            logger.error(f"Fehler in RedisDelete: {e}")
            return agent_service_pb2.RedisDeleteResponse(
                success=False,
                error=str(e),
                logs=""
            )
    
    async def RedisKeys(self, request, context):
        """
        Redis Keys
        
        Args:
            request: RedisKeysRequest
            context: gRPC Context
        
        Returns:
            RedisKeysResponse
        """
        try:
            logger.info(f"RedisKeys: {request.pattern}")
            
            result = self.redis_tool.keys(
                pattern=request.pattern if request.pattern else "*"
            )
            
            response = agent_service_pb2.RedisKeysResponse(
                success=result.get("success", False),
                keys=result.get("keys", []),
                logs=result.get("logs", ""),
                error=result.get("error", "")
            )
            
            return response
        except Exception as e:
            logger.error(f"Fehler in RedisKeys: {e}")
            return agent_service_pb2.RedisKeysResponse(
                success=False,
                error=str(e),
                logs=""
            )
    
    async def PostgresExecute(self, request, context):
        """
        PostgreSQL Execute
        
        Args:
            request: PostgresExecuteRequest
            context: gRPC Context
        
        Returns:
            PostgresExecuteResponse
        """
        try:
            logger.info(f"PostgresExecute: {request.query[:50]}...")
            
            result = self.postgres_tool.execute(
                query=request.query,
                params=request.params if request.params else None
            )
            
            response = agent_service_pb2.PostgresExecuteResponse(
                success=result.get("success", False),
                output=result.get("output", ""),
                logs=result.get("logs", ""),
                error=result.get("error", "")
            )
            
            return response
        except Exception as e:
            logger.error(f"Fehler in PostgresExecute: {e}")
            return agent_service_pb2.PostgresExecuteResponse(
                success=False,
                error=str(e),
                logs=""
            )
    
    async def PostgresQuery(self, request, context):
        """
        PostgreSQL Query
        
        Args:
            request: PostgresQueryRequest
            context: gRPC Context
        
        Returns:
            PostgresQueryResponse
        """
        try:
            logger.info(f"PostgresQuery: {request.query[:50]}...")
            
            result = self.postgres_tool.query(
                query=request.query,
                params=request.params if request.params else None
            )
            
            response = agent_service_pb2.PostgresQueryResponse(
                success=result.get("success", False),
                rows=result.get("rows", []),
                columns=result.get("columns", []),
                logs=result.get("logs", ""),
                error=result.get("error", "")
            )
            
            return response
        except Exception as e:
            logger.error(f"Fehler in PostgresQuery: {e}")
            return agent_service_pb2.PostgresQueryResponse(
                success=False,
                error=str(e),
                logs=""
            )
    
    async def PostgresGetLogs(self, request, context):
        """
        PostgreSQL Logs abrufen
        
        Args:
            request: PostgresGetLogsRequest
            context: gRPC Context
        
        Returns:
            PostgresGetLogsResponse
        """
        try:
            logger.info(f"PostgresGetLogs: {request.log_type}")
            
            result = self.postgres_tool.get_logs(
                log_type=request.log_type,
                limit=request.limit if request.limit else 100
            )
            
            response = agent_service_pb2.PostgresGetLogsResponse(
                success=result.get("success", False),
                logs=result.get("logs", ""),
                output=result.get("output", ""),
                error=result.get("error", "")
            )
            
            return response
        except Exception as e:
            logger.error(f"Fehler in PostgresGetLogs: {e}")
            return agent_service_pb2.PostgresGetLogsResponse(
                success=False,
                error=str(e),
                logs=""
            )
    
    async def PlaywrightStart(self, request, context):
        """
        Playwright starten
        
        Args:
            request: PlaywrightStartRequest
            context: gRPC Context
        
        Returns:
            PlaywrightStartResponse
        """
        try:
            logger.info(f"PlaywrightStart: {request.browser_type}")
            
            result = await self.playwright_tool.start()
            
            response = agent_service_pb2.PlaywrightStartResponse(
                success=result.get("success", False),
                output=result.get("output", ""),
                logs=result.get("logs", ""),
                error=result.get("error", "")
            )
            
            return response
        except Exception as e:
            logger.error(f"Fehler in PlaywrightStart: {e}")
            return agent_service_pb2.PlaywrightStartResponse(
                success=False,
                error=str(e),
                logs=""
            )
    
    async def PlaywrightStop(self, request, context):
        """
        Playwright stoppen
        
        Args:
            request: PlaywrightStopRequest
            context: gRPC Context
        
        Returns:
            PlaywrightStopResponse
        """
        try:
            logger.info("PlaywrightStop")
            
            result = await self.playwright_tool.stop()
            
            response = agent_service_pb2.PlaywrightStopResponse(
                success=result.get("success", False),
                output=result.get("output", ""),
                logs=result.get("logs", ""),
                error=result.get("error", "")
            )
            
            return response
        except Exception as e:
            logger.error(f"Fehler in PlaywrightStop: {e}")
            return agent_service_pb2.PlaywrightStopResponse(
                success=False,
                error=str(e),
                logs=""
            )
    
    async def PlaywrightNavigate(self, request, context):
        """
        Playwright Navigate
        
        Args:
            request: PlaywrightNavigateRequest
            context: gRPC Context
        
        Returns:
            PlaywrightNavigateResponse
        """
        try:
            logger.info(f"PlaywrightNavigate: {request.url}")
            
            result = await self.playwright_tool.navigate(request.url)
            
            response = agent_service_pb2.PlaywrightNavigateResponse(
                success=result.get("success", False),
                output=result.get("output", ""),
                screenshot=result.get("screenshot", ""),
                logs=result.get("logs", ""),
                error=result.get("error", "")
            )
            
            return response
        except Exception as e:
            logger.error(f"Fehler in PlaywrightNavigate: {e}")
            return agent_service_pb2.PlaywrightNavigateResponse(
                success=False,
                error=str(e),
                logs=""
            )
    
    async def PlaywrightClick(self, request, context):
        """
        Playwright Click
        
        Args:
            request: PlaywrightClickRequest
            context: gRPC Context
        
        Returns:
            PlaywrightClickResponse
        """
        try:
            logger.info(f"PlaywrightClick: {request.selector}")
            
            result = await self.playwright_tool.click(request.selector)
            
            response = agent_service_pb2.PlaywrightClickResponse(
                success=result.get("success", False),
                output=result.get("output", ""),
                screenshot=result.get("screenshot", ""),
                logs=result.get("logs", ""),
                error=result.get("error", "")
            )
            
            return response
        except Exception as e:
            logger.error(f"Fehler in PlaywrightClick: {e}")
            return agent_service_pb2.PlaywrightClickResponse(
                success=False,
                error=str(e),
                logs=""
            )
    
    async def PlaywrightFill(self, request, context):
        """
        Playwright Fill
        
        Args:
            request: PlaywrightFillRequest
            context: gRPC Context
        
        Returns:
            PlaywrightFillResponse
        """
        try:
            logger.info(f"PlaywrightFill: {request.selector}")
            
            result = await self.playwright_tool.fill(request.selector, request.value)
            
            response = agent_service_pb2.PlaywrightFillResponse(
                success=result.get("success", False),
                output=result.get("output", ""),
                screenshot=result.get("screenshot", ""),
                logs=result.get("logs", ""),
                error=result.get("error", "")
            )
            
            return response
        except Exception as e:
            logger.error(f"Fehler in PlaywrightFill: {e}")
            return agent_service_pb2.PlaywrightFillResponse(
                success=False,
                error=str(e),
                logs=""
            )
    
    async def PlaywrightGetText(self, request, context):
        """
        Playwright GetText
        
        Args:
            request: PlaywrightGetTextRequest
            context: gRPC Context
        
        Returns:
            PlaywrightGetTextResponse
        """
        try:
            logger.info(f"PlaywrightGetText: {request.selector}")
            
            result = await self.playwright_tool.get_text(request.selector)
            
            response = agent_service_pb2.PlaywrightGetTextResponse(
                success=result.get("success", False),
                text=result.get("output", ""),
                logs=result.get("logs", ""),
                error=result.get("error", "")
            )
            
            return response
        except Exception as e:
            logger.error(f"Fehler in PlaywrightGetText: {e}")
            return agent_service_pb2.PlaywrightGetTextResponse(
                success=False,
                error=str(e),
                logs=""
            )
    
    async def PlaywrightScreenshot(self, request, context):
        """
        Playwright Screenshot
        
        Args:
            request: PlaywrightScreenshotRequest
            context: gRPC Context
        
        Returns:
            PlaywrightScreenshotResponse
        """
        try:
            logger.info("PlaywrightScreenshot")
            
            result = await self.playwright_tool.screenshot(request.filename if request.filename else None)
            
            response = agent_service_pb2.PlaywrightScreenshotResponse(
                success=result.get("success", False),
                output=result.get("output", ""),
                screenshot=result.get("screenshot", ""),
                logs=result.get("logs", ""),
                error=result.get("error", "")
            )
            
            return response
        except Exception as e:
            logger.error(f"Fehler in PlaywrightScreenshot: {e}")
            return agent_service_pb2.PlaywrightScreenshotResponse(
                success=False,
                error=str(e),
                logs=""
            )
    
    async def PlaywrightRunTest(self, request, context):
        """
        Playwright RunTest
        
        Args:
            request: PlaywrightRunTestRequest
            context: gRPC Context
        
        Returns:
            PlaywrightRunTestResponse
        """
        try:
            logger.info("PlaywrightRunTest")
            
            # Parse test_steps JSON
            import json
            test_steps = json.loads(request.test_steps)
            
            result = await self.playwright_tool.run_test(test_steps)
            
            response = agent_service_pb2.PlaywrightRunTestResponse(
                success=result.get("success", False),
                output=result.get("output", ""),
                report=result.get("report", ""),
                logs=result.get("logs", ""),
                error=result.get("error", "")
            )
            
            return response
        except Exception as e:
            logger.error(f"Fehler in PlaywrightRunTest: {e}")
            return agent_service_pb2.PlaywrightRunTestResponse(
                success=False,
                error=str(e),
                logs=""
            )


async def serve(port: int = 50051, base_dir: str = "."):
    """
    gRPC Server starten
    
    Args:
        port: Port für den Server
        base_dir: Basisverzeichnis für das Projekt
    """
    server = aio.server()
    
    # Servicer registrieren
    servicer = EventFixTeamServicer(base_dir)
    agent_service_pb2_grpc.add_EventFixTeamServicer_to_server(servicer, server)
    
    # Server konfigurieren
    listen_addr = f'[::]:{port}'
    server.add_insecure_port(listen_addr)
    
    logger.info(f"Starte gRPC Server auf {listen_addr}")
    await server.start()
    
    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Server wird gestoppt...")
        await server.stop(0)


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='EventFixTeam gRPC Server')
    parser.add_argument('--port', type=int, default=50051, help='Port für den Server')
    parser.add_argument('--base-dir', type=str, default='.', help='Basisverzeichnis für das Projekt')
    parser.add_argument('--log-level', type=str, default='INFO', help='Log-Level')
    
    args = parser.parse_args()
    
    # Logging konfigurieren
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Server starten
    asyncio.run(serve(args.port, args.base_dir))
