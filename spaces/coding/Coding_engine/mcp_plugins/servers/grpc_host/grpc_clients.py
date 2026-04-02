"""
gRPC Clients für die Kommunikation mit den verteilten Agents
"""

import grpc
from typing import Optional, Dict, Any, List
import logging
from pathlib import Path

# Importiere die generierten gRPC Klassen
import sys
sys.path.append(str(Path(__file__).parent / "proto"))
import agent_service_pb2
import agent_service_pb2_grpc

logger = logging.getLogger(__name__)


class AgentClient:
    """Basisklasse für alle Agent-Clients"""
    
    def __init__(self, host: str = "localhost", port: int = 50051):
        self.host = host
        self.port = port
        self.channel = None
        self.stub = None
    
    def connect(self):
        """Verbindung zum gRPC Server herstellen"""
        self.channel = grpc.insecure_channel(f"{self.host}:{self.port}")
        self.stub = agent_service_pb2_grpc.AgentServiceStub(self.channel)
        logger.info(f"Verbunden mit gRPC Server unter {self.host}:{self.port}")
    
    def close(self):
        """Verbindung schließen"""
        if self.channel:
            self.channel.close()
            logger.info("gRPC Verbindung geschlossen")


class LogAgentClient(AgentClient):
    """Client für den LogAgent"""
    
    def __init__(self, host: str = "localhost", port: int = 50051):
        super().__init__(host, port)
    
    def fetch_logs(self, service_name: str, log_type: str = "application", 
                   lines: int = 100, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Logs von einem Service abrufen
        
        Args:
            service_name: Name des Services
            log_type: Typ der Logs (application, docker, system)
            lines: Anzahl der Zeilen
            filters: Zusätzliche Filter (level, time_range, etc.)
        
        Returns:
            Dictionary mit den Logs und Metadaten
        """
        if not self.stub:
            self.connect()
        
        request = agent_service_pb2.LogRequest(
            service_name=service_name,
            log_type=log_type,
            lines=lines,
            filters=str(filters) if filters else ""
        )
        
        try:
            response = self.stub.FetchLogs(request)
            return {
                "success": response.success,
                "logs": response.logs,
                "metadata": {
                    "service_name": response.metadata.service_name,
                    "log_type": response.metadata.log_type,
                    "timestamp": response.metadata.timestamp,
                    "line_count": response.metadata.line_count
                },
                "error": response.error if not response.success else None
            }
        except grpc.RpcError as e:
            logger.error(f"gRPC Fehler beim Abrufen von Logs: {e}")
            return {
                "success": False,
                "logs": "",
                "metadata": {},
                "error": str(e)
            }
    
    def search_logs(self, service_name: str, pattern: str, 
                    log_type: str = "application") -> Dict[str, Any]:
        """
        Logs nach einem Muster durchsuchen
        
        Args:
            service_name: Name des Services
            pattern: Suchmuster (Regex)
            log_type: Typ der Logs
        
        Returns:
            Dictionary mit den gefundenen Log-Einträgen
        """
        if not self.stub:
            self.connect()
        
        request = agent_service_pb2.LogSearchRequest(
            service_name=service_name,
            pattern=pattern,
            log_type=log_type
        )
        
        try:
            response = self.stub.SearchLogs(request)
            return {
                "success": response.success,
                "matches": response.matches,
                "match_count": response.match_count,
                "error": response.error if not response.success else None
            }
        except grpc.RpcError as e:
            logger.error(f"gRPC Fehler beim Suchen in Logs: {e}")
            return {
                "success": False,
                "matches": "",
                "match_count": 0,
                "error": str(e)
            }


class FixAgentClient(AgentClient):
    """Client für den FixAgent"""
    
    def __init__(self, host: str = "localhost", port: int = 50051):
        super().__init__(host, port)
    
    def analyze_issue(self, issue_description: str, 
                      context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Ein Problem analysieren
        
        Args:
            issue_description: Beschreibung des Problems
            context: Zusätzlicher Kontext (Logs, Stacktraces, etc.)
        
        Returns:
            Analyse-Ergebnis mit Ursachen und Lösungsvorschlägen
        """
        if not self.stub:
            self.connect()
        
        request = agent_service_pb2.FixRequest(
            issue_description=issue_description,
            context=str(context) if context else ""
        )
        
        try:
            response = self.stub.AnalyzeIssue(request)
            return {
                "success": response.success,
                "analysis": response.analysis,
                "root_cause": response.root_cause,
                "suggested_fixes": response.suggested_fixes,
                "confidence": response.confidence,
                "error": response.error if not response.success else None
            }
        except grpc.RpcError as e:
            logger.error(f"gRPC Fehler bei der Problemanalyse: {e}")
            return {
                "success": False,
                "analysis": "",
                "root_cause": "",
                "suggested_fixes": "",
                "confidence": 0.0,
                "error": str(e)
            }
    
    def apply_fix(self, fix_description: str, 
                  target_files: List[str]) -> Dict[str, Any]:
        """
        Eine Korrektur anwenden
        
        Args:
            fix_description: Beschreibung der Korrektur
            target_files: Liste der zu ändernden Dateien
        
        Returns:
            Ergebnis der Korrektur
        """
        if not self.stub:
            self.connect()
        
        request = agent_service_pb2.FixApplyRequest(
            fix_description=fix_description,
            target_files=target_files
        )
        
        try:
            response = self.stub.ApplyFix(request)
            return {
                "success": response.success,
                "changes": response.changes,
                "files_modified": list(response.files_modified),
                "backup_created": response.backup_created,
                "error": response.error if not response.success else None
            }
        except grpc.RpcError as e:
            logger.error(f"gRPC Fehler beim Anwenden der Korrektur: {e}")
            return {
                "success": False,
                "changes": "",
                "files_modified": [],
                "backup_created": False,
                "error": str(e)
            }


class TestAgentClient(AgentClient):
    """Client für den TestAgent"""
    
    def __init__(self, host: str = "localhost", port: int = 50051):
        super().__init__(host, port)
    
    def run_tests(self, test_type: str = "playwright", 
                  target: Optional[str] = None,
                  options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Tests ausführen
        
        Args:
            test_type: Art der Tests (playwright, unit, integration)
            target: Ziel für die Tests (URL, Pfad, etc.)
            options: Zusätzliche Optionen
        
        Returns:
            Test-Ergebnisse
        """
        if not self.stub:
            self.connect()
        
        request = agent_service_pb2.TestRequest(
            test_type=test_type,
            target=target or "",
            options=str(options) if options else ""
        )
        
        try:
            response = self.stub.RunTests(request)
            return {
                "success": response.success,
                "results": response.results,
                "test_count": response.test_count,
                "passed": response.passed,
                "failed": response.failed,
                "duration": response.duration,
                "error": response.error if not response.success else None
            }
        except grpc.RpcError as e:
            logger.error(f"gRPC Fehler beim Ausführen der Tests: {e}")
            return {
                "success": False,
                "results": "",
                "test_count": 0,
                "passed": 0,
                "failed": 0,
                "duration": 0.0,
                "error": str(e)
            }
    
    def generate_test_report(self, test_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Test-Bericht generieren
        
        Args:
            test_results: Ergebnisse der Tests
        
        Returns:
            Generierter Bericht
        """
        if not self.stub:
            self.connect()
        
        request = agent_service_pb2.TestReportRequest(
            test_results=str(test_results)
        )
        
        try:
            response = self.stub.GenerateTestReport(request)
            return {
                "success": response.success,
                "report": response.report,
                "report_path": response.report_path,
                "error": response.error if not response.success else None
            }
        except grpc.RpcError as e:
            logger.error(f"gRPC Fehler beim Generieren des Test-Berichts: {e}")
            return {
                "success": False,
                "report": "",
                "report_path": "",
                "error": str(e)
            }


class AgentClientFactory:
    """Factory für die Erstellung von Agent-Clients"""
    
    _clients: Dict[str, AgentClient] = {}
    
    @classmethod
    def get_log_client(cls, host: str = "localhost", port: int = 50051) -> LogAgentClient:
        """LogAgent Client holen oder erstellen"""
        key = f"log_{host}_{port}"
        if key not in cls._clients:
            cls._clients[key] = LogAgentClient(host, port)
        return cls._clients[key]
    
    @classmethod
    def get_fix_client(cls, host: str = "localhost", port: int = 50051) -> FixAgentClient:
        """FixAgent Client holen oder erstellen"""
        key = f"fix_{host}_{port}"
        if key not in cls._clients:
            cls._clients[key] = FixAgentClient(host, port)
        return cls._clients[key]
    
    @classmethod
    def get_test_client(cls, host: str = "localhost", port: int = 50051) -> TestAgentClient:
        """TestAgent Client holen oder erstellen"""
        key = f"test_{host}_{port}"
        if key not in cls._clients:
            cls._clients[key] = TestAgentClient(host, port)
        return cls._clients[key]
    
    @classmethod
    def close_all(cls):
        """Alle Verbindungen schließen"""
        for client in cls._clients.values():
            client.close()
        cls._clients.clear()
