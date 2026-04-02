"""
gRPC Server für EventFixTeam - MCP Version

Diese Version nutzt MCP Server statt der Custom Tools.
Die Custom Tools (file_write_tool, docker_tool, etc.) werden durch
MCP Server (filesystem, docker, redis, playwright) ersetzt.
"""

import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List

import grpc
from grpc import aio

# Importiere generierte gRPC-Klassen
import sys
sys.path.insert(0, str(Path(__file__).parent / "proto"))
import agent_service_pb2
import agent_service_pb2_grpc

# MCP Workbench für Tool-Zugriff
from mcp_workbench import get_workbench_manager, get_all_mcp_tools, AUTOGEN_MCP_AVAILABLE

# Fallback: Postgres bleibt als Custom Tool (besser als MCP)
from tools.postgres_tool import PostgresTool

logger = logging.getLogger(__name__)


class MCPToolCache:
    """Cache für MCP Tools mit lazy loading"""

    def __init__(self):
        self._tools: Dict[str, Any] = {}
        self._initialized = False
        self._lock = asyncio.Lock()

    async def initialize(self):
        """Lädt alle MCP Tools"""
        async with self._lock:
            if self._initialized:
                return

            if not AUTOGEN_MCP_AVAILABLE:
                logger.warning("AutoGen MCP nicht verfügbar - nutze Fallback")
                self._initialized = True
                return

            try:
                all_tools = await get_all_mcp_tools()
                self._tools = {t.name: t for t in all_tools}
                logger.info(f"MCP Tools geladen: {len(self._tools)}")
                self._initialized = True
            except Exception as e:
                logger.error(f"Fehler beim Laden der MCP Tools: {e}")
                self._initialized = True

    async def get_tool(self, name: str) -> Optional[Any]:
        """Holt ein Tool by name"""
        if not self._initialized:
            await self.initialize()
        return self._tools.get(name)

    def list_tools(self) -> List[str]:
        """Listet alle verfügbaren Tools"""
        return list(self._tools.keys())


class EventFixTeamServicer(agent_service_pb2_grpc.EventFixTeamServicer):
    """gRPC Servicer für EventFixTeam - MCP Version"""

    def __init__(self, base_dir: str = "."):
        """
        Servicer initialisieren

        Args:
            base_dir: Basisverzeichnis für das Projekt
        """
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(exist_ok=True)

        # MCP Tool Cache
        self._mcp_cache = MCPToolCache()

        # Postgres bleibt als Custom Tool (besser als MCP)
        self.postgres_tool = PostgresTool(base_dir)

        logger.info("EventFixTeam Servicer (MCP) initialisiert")

    async def _ensure_mcp_initialized(self):
        """Stellt sicher dass MCP Tools geladen sind"""
        if not self._mcp_cache._initialized:
            await self._mcp_cache.initialize()

    # =========================================================================
    # FILE OPERATIONS - via filesystem MCP
    # =========================================================================

    async def WriteFile(self, request, context):
        """Datei schreiben via filesystem MCP"""
        try:
            logger.info(f"WriteFile (MCP): {request.filepath}")
            await self._ensure_mcp_initialized()

            # MCP Tool holen
            tool = await self._mcp_cache.get_tool("write_file")

            if tool:
                result = await tool.run(
                    path=str(self.base_dir / request.filepath),
                    content=request.content
                )
                return agent_service_pb2.WriteFileResponse(
                    success=True,
                    output=str(result),
                    logs="",
                    error=""
                )
            else:
                # Fallback: Direkt schreiben
                full_path = self.base_dir / request.filepath
                full_path.parent.mkdir(parents=True, exist_ok=True)
                encoding = request.encoding if request.encoding else "utf-8"
                full_path.write_text(request.content, encoding=encoding)

                return agent_service_pb2.WriteFileResponse(
                    success=True,
                    output=f"Datei geschrieben: {full_path}",
                    logs="Fallback: Direktes Schreiben",
                    error=""
                )

        except Exception as e:
            logger.error(f"Fehler in WriteFile: {e}")
            return agent_service_pb2.WriteFileResponse(
                success=False,
                error=str(e),
                logs=""
            )

    async def ReadFile(self, request, context):
        """Datei lesen via filesystem MCP"""
        try:
            logger.info(f"ReadFile (MCP): {request.filepath}")
            await self._ensure_mcp_initialized()

            tool = await self._mcp_cache.get_tool("read_file")

            if tool:
                result = await tool.run(
                    path=str(self.base_dir / request.filepath)
                )
                return agent_service_pb2.ReadFileResponse(
                    success=True,
                    content=str(result),
                    logs="",
                    error=""
                )
            else:
                # Fallback
                full_path = self.base_dir / request.filepath
                encoding = request.encoding if request.encoding else "utf-8"
                content = full_path.read_text(encoding=encoding)

                return agent_service_pb2.ReadFileResponse(
                    success=True,
                    content=content,
                    logs="Fallback: Direktes Lesen",
                    error=""
                )

        except Exception as e:
            logger.error(f"Fehler in ReadFile: {e}")
            return agent_service_pb2.ReadFileResponse(
                success=False,
                error=str(e),
                logs=""
            )

    async def ListFiles(self, request, context):
        """Dateien auflisten via filesystem MCP"""
        try:
            logger.info(f"ListFiles (MCP): {request.directory}")
            await self._ensure_mcp_initialized()

            tool = await self._mcp_cache.get_tool("list_directory")

            if tool:
                result = await tool.run(
                    path=str(self.base_dir / request.directory)
                )
                # Parse result to list
                files = str(result).split("\n") if result else []

                return agent_service_pb2.ListFilesResponse(
                    success=True,
                    files=files,
                    logs="",
                    error=""
                )
            else:
                # Fallback
                dir_path = self.base_dir / request.directory
                if request.recursive:
                    files = [str(f.relative_to(dir_path)) for f in dir_path.rglob("*") if f.is_file()]
                else:
                    files = [f.name for f in dir_path.iterdir() if f.is_file()]

                return agent_service_pb2.ListFilesResponse(
                    success=True,
                    files=files,
                    logs="Fallback: Direktes Listen",
                    error=""
                )

        except Exception as e:
            logger.error(f"Fehler in ListFiles: {e}")
            return agent_service_pb2.ListFilesResponse(
                success=False,
                error=str(e),
                logs=""
            )

    # =========================================================================
    # DOCKER OPERATIONS - via docker MCP
    # =========================================================================

    async def DockerBuild(self, request, context):
        """Docker Image bauen via docker MCP"""
        try:
            logger.info(f"DockerBuild (MCP): {request.dockerfile_path}")
            await self._ensure_mcp_initialized()

            tool = await self._mcp_cache.get_tool("docker_build")

            if tool:
                result = await tool.run(
                    dockerfile=request.dockerfile_path,
                    context=request.context_path or ".",
                    tag=request.tag or None
                )
                return agent_service_pb2.DockerBuildResponse(
                    success=True,
                    output=str(result),
                    logs="",
                    error=""
                )
            else:
                return agent_service_pb2.DockerBuildResponse(
                    success=False,
                    error="Docker MCP Tool nicht verfügbar",
                    logs=""
                )

        except Exception as e:
            logger.error(f"Fehler in DockerBuild: {e}")
            return agent_service_pb2.DockerBuildResponse(
                success=False,
                error=str(e),
                logs=""
            )

    async def DockerRun(self, request, context):
        """Docker Container starten via docker MCP"""
        try:
            logger.info(f"DockerRun (MCP): {request.image}")
            await self._ensure_mcp_initialized()

            tool = await self._mcp_cache.get_tool("docker_run")

            if tool:
                result = await tool.run(
                    image=request.image,
                    command=request.command or None,
                    detach=request.detach,
                    name=request.name or None
                )
                return agent_service_pb2.DockerRunResponse(
                    success=True,
                    output=str(result),
                    logs="",
                    error=""
                )
            else:
                return agent_service_pb2.DockerRunResponse(
                    success=False,
                    error="Docker MCP Tool nicht verfügbar",
                    logs=""
                )

        except Exception as e:
            logger.error(f"Fehler in DockerRun: {e}")
            return agent_service_pb2.DockerRunResponse(
                success=False,
                error=str(e),
                logs=""
            )

    async def DockerStop(self, request, context):
        """Docker Container stoppen via docker MCP"""
        try:
            logger.info(f"DockerStop (MCP): {request.container_id}")
            await self._ensure_mcp_initialized()

            tool = await self._mcp_cache.get_tool("docker_stop")

            if tool:
                result = await tool.run(container=request.container_id)
                return agent_service_pb2.DockerStopResponse(
                    success=True,
                    output=str(result),
                    logs="",
                    error=""
                )
            else:
                return agent_service_pb2.DockerStopResponse(
                    success=False,
                    error="Docker MCP Tool nicht verfügbar",
                    logs=""
                )

        except Exception as e:
            logger.error(f"Fehler in DockerStop: {e}")
            return agent_service_pb2.DockerStopResponse(
                success=False,
                error=str(e),
                logs=""
            )

    async def DockerLogs(self, request, context):
        """Docker Logs abrufen via docker MCP"""
        try:
            logger.info(f"DockerLogs (MCP): {request.container_id}")
            await self._ensure_mcp_initialized()

            tool = await self._mcp_cache.get_tool("docker_logs")

            if tool:
                result = await tool.run(
                    container=request.container_id,
                    tail=request.tail or 100
                )
                return agent_service_pb2.DockerLogsResponse(
                    success=True,
                    output=str(result),
                    logs="",
                    error=""
                )
            else:
                return agent_service_pb2.DockerLogsResponse(
                    success=False,
                    error="Docker MCP Tool nicht verfügbar",
                    logs=""
                )

        except Exception as e:
            logger.error(f"Fehler in DockerLogs: {e}")
            return agent_service_pb2.DockerLogsResponse(
                success=False,
                error=str(e),
                logs=""
            )

    async def DockerComposeUp(self, request, context):
        """Docker Compose starten via docker MCP"""
        try:
            logger.info(f"DockerComposeUp (MCP): {request.compose_file}")
            await self._ensure_mcp_initialized()

            tool = await self._mcp_cache.get_tool("docker_compose_up")

            if tool:
                result = await tool.run(
                    file=request.compose_file,
                    detach=request.detached
                )
                return agent_service_pb2.DockerComposeUpResponse(
                    success=True,
                    output=str(result),
                    logs="",
                    error=""
                )
            else:
                return agent_service_pb2.DockerComposeUpResponse(
                    success=False,
                    error="Docker Compose MCP Tool nicht verfügbar",
                    logs=""
                )

        except Exception as e:
            logger.error(f"Fehler in DockerComposeUp: {e}")
            return agent_service_pb2.DockerComposeUpResponse(
                success=False,
                error=str(e),
                logs=""
            )

    async def DockerComposeDown(self, request, context):
        """Docker Compose stoppen via docker MCP"""
        try:
            logger.info(f"DockerComposeDown (MCP): {request.compose_file}")
            await self._ensure_mcp_initialized()

            tool = await self._mcp_cache.get_tool("docker_compose_down")

            if tool:
                result = await tool.run(file=request.compose_file)
                return agent_service_pb2.DockerComposeDownResponse(
                    success=True,
                    output=str(result),
                    logs="",
                    error=""
                )
            else:
                return agent_service_pb2.DockerComposeDownResponse(
                    success=False,
                    error="Docker Compose MCP Tool nicht verfügbar",
                    logs=""
                )

        except Exception as e:
            logger.error(f"Fehler in DockerComposeDown: {e}")
            return agent_service_pb2.DockerComposeDownResponse(
                success=False,
                error=str(e),
                logs=""
            )

    # =========================================================================
    # REDIS OPERATIONS - via redis MCP
    # =========================================================================

    async def RedisSet(self, request, context):
        """Redis Set via redis MCP"""
        try:
            logger.info(f"RedisSet (MCP): {request.key}")
            await self._ensure_mcp_initialized()

            tool = await self._mcp_cache.get_tool("redis_set")

            if tool:
                result = await tool.run(
                    key=request.key,
                    value=request.value,
                    expiry=request.expiry or None
                )
                return agent_service_pb2.RedisSetResponse(
                    success=True,
                    output=str(result),
                    logs="",
                    error=""
                )
            else:
                return agent_service_pb2.RedisSetResponse(
                    success=False,
                    error="Redis MCP Tool nicht verfügbar",
                    logs=""
                )

        except Exception as e:
            logger.error(f"Fehler in RedisSet: {e}")
            return agent_service_pb2.RedisSetResponse(
                success=False,
                error=str(e),
                logs=""
            )

    async def RedisGet(self, request, context):
        """Redis Get via redis MCP"""
        try:
            logger.info(f"RedisGet (MCP): {request.key}")
            await self._ensure_mcp_initialized()

            tool = await self._mcp_cache.get_tool("redis_get")

            if tool:
                result = await tool.run(key=request.key)
                return agent_service_pb2.RedisGetResponse(
                    success=True,
                    value=str(result) if result else "",
                    logs="",
                    error=""
                )
            else:
                return agent_service_pb2.RedisGetResponse(
                    success=False,
                    error="Redis MCP Tool nicht verfügbar",
                    logs=""
                )

        except Exception as e:
            logger.error(f"Fehler in RedisGet: {e}")
            return agent_service_pb2.RedisGetResponse(
                success=False,
                error=str(e),
                logs=""
            )

    async def RedisDelete(self, request, context):
        """Redis Delete via redis MCP"""
        try:
            logger.info(f"RedisDelete (MCP): {request.key}")
            await self._ensure_mcp_initialized()

            tool = await self._mcp_cache.get_tool("redis_del")

            if tool:
                result = await tool.run(key=request.key)
                return agent_service_pb2.RedisDeleteResponse(
                    success=True,
                    output=str(result),
                    logs="",
                    error=""
                )
            else:
                return agent_service_pb2.RedisDeleteResponse(
                    success=False,
                    error="Redis MCP Tool nicht verfügbar",
                    logs=""
                )

        except Exception as e:
            logger.error(f"Fehler in RedisDelete: {e}")
            return agent_service_pb2.RedisDeleteResponse(
                success=False,
                error=str(e),
                logs=""
            )

    async def RedisKeys(self, request, context):
        """Redis Keys via redis MCP"""
        try:
            logger.info(f"RedisKeys (MCP): {request.pattern}")
            await self._ensure_mcp_initialized()

            tool = await self._mcp_cache.get_tool("redis_keys")

            if tool:
                result = await tool.run(pattern=request.pattern or "*")
                keys = str(result).split("\n") if result else []
                return agent_service_pb2.RedisKeysResponse(
                    success=True,
                    keys=keys,
                    logs="",
                    error=""
                )
            else:
                return agent_service_pb2.RedisKeysResponse(
                    success=False,
                    error="Redis MCP Tool nicht verfügbar",
                    logs=""
                )

        except Exception as e:
            logger.error(f"Fehler in RedisKeys: {e}")
            return agent_service_pb2.RedisKeysResponse(
                success=False,
                error=str(e),
                logs=""
            )

    # =========================================================================
    # POSTGRES OPERATIONS - bleibt als Custom Tool (besser)
    # =========================================================================

    async def PostgresExecute(self, request, context):
        """PostgreSQL Execute - nutzt weiterhin Custom Tool"""
        try:
            logger.info(f"PostgresExecute: {request.query[:50]}...")

            result = self.postgres_tool.execute(
                query=request.query,
                params=request.params if request.params else None
            )

            return agent_service_pb2.PostgresExecuteResponse(
                success=result.get("success", False),
                output=result.get("output", ""),
                logs=result.get("logs", ""),
                error=result.get("error", "")
            )

        except Exception as e:
            logger.error(f"Fehler in PostgresExecute: {e}")
            return agent_service_pb2.PostgresExecuteResponse(
                success=False,
                error=str(e),
                logs=""
            )

    async def PostgresQuery(self, request, context):
        """PostgreSQL Query - nutzt weiterhin Custom Tool"""
        try:
            logger.info(f"PostgresQuery: {request.query[:50]}...")

            result = self.postgres_tool.query(
                query=request.query,
                params=request.params if request.params else None
            )

            return agent_service_pb2.PostgresQueryResponse(
                success=result.get("success", False),
                rows=result.get("rows", []),
                columns=result.get("columns", []),
                logs=result.get("logs", ""),
                error=result.get("error", "")
            )

        except Exception as e:
            logger.error(f"Fehler in PostgresQuery: {e}")
            return agent_service_pb2.PostgresQueryResponse(
                success=False,
                error=str(e),
                logs=""
            )

    async def PostgresGetLogs(self, request, context):
        """PostgreSQL Logs - nutzt weiterhin Custom Tool"""
        try:
            logger.info(f"PostgresGetLogs: {request.log_type}")

            result = self.postgres_tool.get_logs(
                log_type=request.log_type,
                limit=request.limit if request.limit else 100
            )

            return agent_service_pb2.PostgresGetLogsResponse(
                success=result.get("success", False),
                logs=result.get("logs", ""),
                output=result.get("output", ""),
                error=result.get("error", "")
            )

        except Exception as e:
            logger.error(f"Fehler in PostgresGetLogs: {e}")
            return agent_service_pb2.PostgresGetLogsResponse(
                success=False,
                error=str(e),
                logs=""
            )

    # =========================================================================
    # PLAYWRIGHT OPERATIONS - via playwright MCP
    # =========================================================================

    async def PlaywrightStart(self, request, context):
        """Playwright starten via playwright MCP"""
        try:
            logger.info(f"PlaywrightStart (MCP): {request.browser_type}")
            await self._ensure_mcp_initialized()

            tool = await self._mcp_cache.get_tool("browser_launch")

            if tool:
                result = await tool.run(
                    browser=request.browser_type or "chromium"
                )
                return agent_service_pb2.PlaywrightStartResponse(
                    success=True,
                    output=str(result),
                    logs="",
                    error=""
                )
            else:
                return agent_service_pb2.PlaywrightStartResponse(
                    success=False,
                    error="Playwright MCP Tool nicht verfügbar",
                    logs=""
                )

        except Exception as e:
            logger.error(f"Fehler in PlaywrightStart: {e}")
            return agent_service_pb2.PlaywrightStartResponse(
                success=False,
                error=str(e),
                logs=""
            )

    async def PlaywrightStop(self, request, context):
        """Playwright stoppen via playwright MCP"""
        try:
            logger.info("PlaywrightStop (MCP)")
            await self._ensure_mcp_initialized()

            tool = await self._mcp_cache.get_tool("browser_close")

            if tool:
                result = await tool.run()
                return agent_service_pb2.PlaywrightStopResponse(
                    success=True,
                    output=str(result),
                    logs="",
                    error=""
                )
            else:
                return agent_service_pb2.PlaywrightStopResponse(
                    success=False,
                    error="Playwright MCP Tool nicht verfügbar",
                    logs=""
                )

        except Exception as e:
            logger.error(f"Fehler in PlaywrightStop: {e}")
            return agent_service_pb2.PlaywrightStopResponse(
                success=False,
                error=str(e),
                logs=""
            )

    async def PlaywrightNavigate(self, request, context):
        """Playwright Navigate via playwright MCP"""
        try:
            logger.info(f"PlaywrightNavigate (MCP): {request.url}")
            await self._ensure_mcp_initialized()

            tool = await self._mcp_cache.get_tool("browser_navigate")

            if tool:
                result = await tool.run(url=request.url)
                return agent_service_pb2.PlaywrightNavigateResponse(
                    success=True,
                    output=str(result),
                    screenshot="",
                    logs="",
                    error=""
                )
            else:
                return agent_service_pb2.PlaywrightNavigateResponse(
                    success=False,
                    error="Playwright MCP Tool nicht verfügbar",
                    logs=""
                )

        except Exception as e:
            logger.error(f"Fehler in PlaywrightNavigate: {e}")
            return agent_service_pb2.PlaywrightNavigateResponse(
                success=False,
                error=str(e),
                logs=""
            )

    async def PlaywrightClick(self, request, context):
        """Playwright Click via playwright MCP"""
        try:
            logger.info(f"PlaywrightClick (MCP): {request.selector}")
            await self._ensure_mcp_initialized()

            tool = await self._mcp_cache.get_tool("browser_click")

            if tool:
                result = await tool.run(selector=request.selector)
                return agent_service_pb2.PlaywrightClickResponse(
                    success=True,
                    output=str(result),
                    screenshot="",
                    logs="",
                    error=""
                )
            else:
                return agent_service_pb2.PlaywrightClickResponse(
                    success=False,
                    error="Playwright MCP Tool nicht verfügbar",
                    logs=""
                )

        except Exception as e:
            logger.error(f"Fehler in PlaywrightClick: {e}")
            return agent_service_pb2.PlaywrightClickResponse(
                success=False,
                error=str(e),
                logs=""
            )

    async def PlaywrightFill(self, request, context):
        """Playwright Fill via playwright MCP"""
        try:
            logger.info(f"PlaywrightFill (MCP): {request.selector}")
            await self._ensure_mcp_initialized()

            tool = await self._mcp_cache.get_tool("browser_type")

            if tool:
                result = await tool.run(
                    selector=request.selector,
                    text=request.value
                )
                return agent_service_pb2.PlaywrightFillResponse(
                    success=True,
                    output=str(result),
                    screenshot="",
                    logs="",
                    error=""
                )
            else:
                return agent_service_pb2.PlaywrightFillResponse(
                    success=False,
                    error="Playwright MCP Tool nicht verfügbar",
                    logs=""
                )

        except Exception as e:
            logger.error(f"Fehler in PlaywrightFill: {e}")
            return agent_service_pb2.PlaywrightFillResponse(
                success=False,
                error=str(e),
                logs=""
            )

    async def PlaywrightGetText(self, request, context):
        """Playwright GetText via playwright MCP"""
        try:
            logger.info(f"PlaywrightGetText (MCP): {request.selector}")
            await self._ensure_mcp_initialized()

            tool = await self._mcp_cache.get_tool("browser_get_text")

            if tool:
                result = await tool.run(selector=request.selector)
                return agent_service_pb2.PlaywrightGetTextResponse(
                    success=True,
                    text=str(result),
                    logs="",
                    error=""
                )
            else:
                return agent_service_pb2.PlaywrightGetTextResponse(
                    success=False,
                    error="Playwright MCP Tool nicht verfügbar",
                    logs=""
                )

        except Exception as e:
            logger.error(f"Fehler in PlaywrightGetText: {e}")
            return agent_service_pb2.PlaywrightGetTextResponse(
                success=False,
                error=str(e),
                logs=""
            )

    async def PlaywrightScreenshot(self, request, context):
        """Playwright Screenshot via playwright MCP"""
        try:
            logger.info("PlaywrightScreenshot (MCP)")
            await self._ensure_mcp_initialized()

            tool = await self._mcp_cache.get_tool("browser_screenshot")

            if tool:
                result = await tool.run(
                    name=request.filename if request.filename else "screenshot"
                )
                return agent_service_pb2.PlaywrightScreenshotResponse(
                    success=True,
                    output=str(result),
                    screenshot=str(result),
                    logs="",
                    error=""
                )
            else:
                return agent_service_pb2.PlaywrightScreenshotResponse(
                    success=False,
                    error="Playwright MCP Tool nicht verfügbar",
                    logs=""
                )

        except Exception as e:
            logger.error(f"Fehler in PlaywrightScreenshot: {e}")
            return agent_service_pb2.PlaywrightScreenshotResponse(
                success=False,
                error=str(e),
                logs=""
            )

    async def PlaywrightRunTest(self, request, context):
        """Playwright RunTest - komplexer Test via Orchestrator"""
        try:
            logger.info("PlaywrightRunTest (MCP)")
            await self._ensure_mcp_initialized()

            # Für komplexe Tests nutzen wir den AutoGen Orchestrator
            from autogen_orchestrator import EventFixOrchestrator

            orchestrator = EventFixOrchestrator()
            await orchestrator.initialize()

            result = await orchestrator.execute_task(
                task=f"Führe folgenden E2E Test aus:\n{request.test_steps}",
                task_type="playwright_tests"
            )

            return agent_service_pb2.PlaywrightRunTestResponse(
                success=result.status == "completed",
                output=str(result.result),
                report=str(result.messages) if result.messages else "",
                logs="",
                error=result.error or ""
            )

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

    logger.info(f"Starte gRPC Server (MCP) auf {listen_addr}")

    # MCP Tools vorladen
    await servicer._ensure_mcp_initialized()
    logger.info(f"MCP Tools geladen: {servicer._mcp_cache.list_tools()[:10]}...")

    await server.start()

    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Server wird gestoppt...")
        await server.stop(0)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='EventFixTeam gRPC Server (MCP)')
    parser.add_argument('--port', type=int, default=50051, help='Port für den Server')
    parser.add_argument('--base-dir', type=str, default='.', help='Basisverzeichnis')
    parser.add_argument('--log-level', type=str, default='INFO', help='Log-Level')

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    asyncio.run(serve(args.port, args.base_dir))
