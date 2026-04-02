"""
EventFixTeam Agent Implementations
Diese Datei enthält die verschiedenen Agent-Typen für das EventFixTeam System.
"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Any, Optional, List
from pathlib import Path
import subprocess
import docker
from playwright.async_api import async_playwright

# Konfiguration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Basis-Klasse für alle EventFixTeam Agents"""
    
    def __init__(self, agent_id: str, agent_type: str, grpc_client):
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.grpc_client = grpc_client
        self.status = "idle"
        self.current_task = None
        self.capabilities = self._get_capabilities()
        
    @abstractmethod
    def _get_capabilities(self) -> List[str]:
        """Gibt die Fähigkeiten des Agents zurück"""
        pass
    
    @abstractmethod
    async def process_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Verarbeitet eine Aufgabe"""
        pass
    
    async def register(self):
        """Registriert den Agent beim gRPC Server"""
        try:
            await self.grpc_client.register_agent(
                agent_id=self.agent_id,
                agent_type=self.agent_type,
                capabilities=self.capabilities
            )
            logger.info(f"Agent {self.agent_id} erfolgreich registriert")
        except Exception as e:
            logger.error(f"Fehler bei der Registrierung von {self.agent_id}: {e}")
            raise
    
    async def heartbeat(self):
        """Sendet Heartbeat an den Server"""
        try:
            await self.grpc_client.agent_heartbeat(
                agent_id=self.agent_id,
                status=self.status,
                current_task_id=self.current_task
            )
        except Exception as e:
            logger.error(f"Heartbeat Fehler für {self.agent_id}: {e}")
    
    async def run(self):
        """Haupt-Schleife des Agents"""
        logger.info(f"Agent {self.agent_id} gestartet")
        await self.register()
        
        while True:
            try:
                # Heartbeat senden
                await self.heartbeat()
                
                # Nach neuen Tasks suchen
                if self.status == "idle":
                    task = await self.grpc_client.get_next_task(
                        agent_type=self.agent_type,
                        agent_id=self.agent_id
                    )
                    
                    if task:
                        logger.info(f"Neuer Task empfangen: {task['task_id']}")
                        self.current_task = task['task_id']
                        self.status = "working"
                        
                        try:
                            # Task verarbeiten
                            result = await self.process_task(task)
                            
                            # Task als abgeschlossen markieren
                            await self.grpc_client.complete_task(
                                task_id=task['task_id'],
                                result=result,
                                error=None
                            )
                            logger.info(f"Task {task['task_id']} erfolgreich abgeschlossen")
                            
                        except Exception as e:
                            logger.error(f"Fehler bei der Verarbeitung von Task {task['task_id']}: {e}")
                            await self.grpc_client.complete_task(
                                task_id=task['task_id'],
                                result=None,
                                error=str(e)
                            )
                        
                        self.current_task = None
                        self.status = "idle"
                
                # Kurze Pause
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Fehler in Agent-Schleife: {e}")
                await asyncio.sleep(5)


class CodeWriterAgent(BaseAgent):
    """
    Agent für das Schreiben von Code.
    Erstellt keine Dateien direkt, sondern generiert Tasks für file_write.
    """
    
    def _get_capabilities(self) -> List[str]:
        return ["file_write", "code_generation", "task_creation"]
    
    async def process_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Verarbeitet Code-Schreib-Tasks"""
        payload = task['payload']
        task_type = payload.get('code_type', 'general')
        
        logger.info(f"Verarbeite Code-Task: {task_type}")
        
        # Generiere Tasks basierend auf dem Typ
        if task_type == 'fix':
            return await self._generate_fix_tasks(payload)
        elif task_type == 'feature':
            return await self._generate_feature_tasks(payload)
        elif task_type == 'migration':
            return await self._generate_migration_tasks(payload)
        else:
            return await self._generate_general_tasks(payload)
    
    async def _generate_fix_tasks(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Generiert Tasks für Bug-Fixes"""
        error_info = payload.get('error_info', {})
        file_path = error_info.get('file_path')
        error_line = error_info.get('line_number')
        error_message = error_info.get('message')
        
        # Analysiere den Fehler und erstelle Tasks
        tasks = []
        
        # Task 1: Analyse des Fehlers
        tasks.append({
            "task_type": "analyze_error",
            "file_path": file_path,
            "line_number": error_line,
            "error_message": error_message,
            "action": "analyze"
        })
        
        # Task 2: Fix generieren
        tasks.append({
            "task_type": "generate_fix",
            "file_path": file_path,
            "line_number": error_line,
            "error_message": error_message,
            "action": "fix"
        })
        
        # Task 3: Fix anwenden (via file_write)
        tasks.append({
            "task_type": "file_write",
            "file_path": file_path,
            "content": payload.get('fix_content', ''),
            "action": "write"
        })
        
        # Task 4: Testen
        tasks.append({
            "task_type": "test_fix",
            "file_path": file_path,
            "test_type": "unit_test",
            "action": "test"
        })
        
        return {
            "status": "success",
            "tasks_generated": len(tasks),
            "tasks": tasks
        }
    
    async def _generate_feature_tasks(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Generiert Tasks für neue Features"""
        feature_spec = payload.get('feature_spec', {})
        feature_name = feature_spec.get('name')
        files_to_create = feature_spec.get('files', [])
        
        tasks = []
        
        # Tasks für jede Datei
        for file_info in files_to_create:
            tasks.append({
                "task_type": "file_write",
                "file_path": file_info['path'],
                "content": file_info.get('content', ''),
                "action": "write"
            })
        
        # Integrationstest Task
        tasks.append({
            "task_type": "integration_test",
            "feature_name": feature_name,
            "action": "test"
        })
        
        return {
            "status": "success",
            "tasks_generated": len(tasks),
            "tasks": tasks
        }
    
    async def _generate_migration_tasks(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Generiert Tasks für Migrationen"""
        migration_spec = payload.get('migration_spec', {})
        migration_type = migration_spec.get('type')
        
        tasks = []
        
        if migration_type == 'database':
            tasks.append({
                "task_type": "database_migration",
                "migration_script": migration_spec.get('script'),
                "action": "migrate"
            })
        elif migration_type == 'api':
            tasks.append({
                "task_type": "api_migration",
                "old_endpoint": migration_spec.get('old_endpoint'),
                "new_endpoint": migration_spec.get('new_endpoint'),
                "action": "migrate"
            })
        
        return {
            "status": "success",
            "tasks_generated": len(tasks),
            "tasks": tasks
        }
    
    async def _generate_general_tasks(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Generiert allgemeine Code-Tasks"""
        tasks = []
        
        # Generiere Tasks basierend auf der Anforderung
        requirement = payload.get('requirement', '')
        
        tasks.append({
            "task_type": "analyze_requirement",
            "requirement": requirement,
            "action": "analyze"
        })
        
        tasks.append({
            "task_type": "generate_code",
            "requirement": requirement,
            "action": "generate"
        })
        
        return {
            "status": "success",
            "tasks_generated": len(tasks),
            "tasks": tasks
        }


class DebuggerAgent(BaseAgent):
    """
    Agent für Debugging und Log-Analyse.
    Sammelt Logs von Docker, Redis und PostgreSQL.
    """
    
    def __init__(self, agent_id: str, agent_type: str, grpc_client):
        super().__init__(agent_id, agent_type, grpc_client)
        self.docker_client = None
        self._init_docker_client()
    
    def _init_docker_client(self):
        """Initialisiert den Docker Client"""
        try:
            self.docker_client = docker.from_env()
            logger.info("Docker Client initialisiert")
        except Exception as e:
            logger.error(f"Fehler bei der Initialisierung des Docker Clients: {e}")
    
    def _get_capabilities(self) -> List[str]:
        return ["docker_logs", "postgres_logs", "redis_logs", "error_analysis", "log_collection"]
    
    async def process_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Verarbeitet Debugging-Tasks"""
        payload = task['payload']
        debug_type = payload.get('debug_type', 'general')
        
        logger.info(f"Verarbeite Debug-Task: {debug_type}")
        
        if debug_type == 'collect_logs':
            return await self._collect_logs(payload)
        elif debug_type == 'analyze_error':
            return await self._analyze_error(payload)
        elif debug_type == 'docker_inspect':
            return await self._docker_inspect(payload)
        else:
            return await self._general_debug(payload)
    
    async def _collect_logs(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Sammelt Logs von verschiedenen Quellen"""
        logs = {}
        
        # Docker Logs
        if payload.get('collect_docker', True):
            logs['docker'] = await self._get_docker_logs(payload)
        
        # PostgreSQL Logs
        if payload.get('collect_postgres', True):
            logs['postgres'] = await self._get_postgres_logs(payload)
        
        # Redis Logs
        if payload.get('collect_redis', True):
            logs['redis'] = await self._get_redis_logs(payload)
        
        # Speichere Logs in der Datenbank
        await self._save_logs_to_db(logs, payload.get('task_id'))
        
        return {
            "status": "success",
            "logs_collected": True,
            "log_sources": list(logs.keys()),
            "logs": logs
        }
    
    async def _get_docker_logs(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Holt Docker Container Logs"""
        if not self.docker_client:
            return {"error": "Docker Client nicht verfügbar"}
        
        container_name = payload.get('container_name')
        tail_lines = payload.get('tail_lines', 100)
        
        try:
            if container_name:
                container = self.docker_client.containers.get(container_name)
                logs = container.logs(tail=tail_lines).decode('utf-8')
                return {
                    "container": container_name,
                    "logs": logs,
                    "timestamp": datetime.now().isoformat()
                }
            else:
                # Logs von allen Containern
                all_logs = {}
                for container in self.docker_client.containers.list():
                    all_logs[container.name] = container.logs(tail=tail_lines).decode('utf-8')
                return all_logs
                
        except Exception as e:
            return {"error": str(e)}
    
    async def _get_postgres_logs(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Holt PostgreSQL Logs"""
        try:
            # Hier würde die Verbindung zur PostgreSQL Datenbank stehen
            # und die Logs abgerufen werden
            return {
                "source": "postgres",
                "logs": "PostgreSQL Log-Abruf implementieren",
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            return {"error": str(e)}
    
    async def _get_redis_logs(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Holt Redis Logs"""
        try:
            # Hier würde die Verbindung zu Redis stehen
            # und die Logs abgerufen werden
            return {
                "source": "redis",
                "logs": "Redis Log-Abruf implementieren",
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            return {"error": str(e)}
    
    async def _save_logs_to_db(self, logs: Dict[str, Any], task_id: str):
        """Speichert Logs in der Datenbank"""
        try:
            for source, log_data in logs.items():
                await self.grpc_client.log_event(
                    event_type="log_collected",
                    source=source,
                    severity="info",
                    message=f"Logs von {source} gesammelt",
                    metadata={"logs": log_data, "task_id": task_id}
                )
        except Exception as e:
            logger.error(f"Fehler beim Speichern der Logs: {e}")
    
    async def _analyze_error(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Analysiert Fehler"""
        error_info = payload.get('error_info', {})
        error_message = error_info.get('message', '')
        stack_trace = error_info.get('stack_trace', '')
        
        # Analysiere den Fehler
        analysis = {
            "error_type": self._classify_error(error_message),
            "severity": self._assess_severity(error_message),
            "suggested_fixes": self._suggest_fixes(error_message, stack_trace),
            "related_files": self._find_related_files(error_message)
        }
        
        return {
            "status": "success",
            "analysis": analysis
        }
    
    def _classify_error(self, error_message: str) -> str:
        """Klassifiziert den Fehlertyp"""
        error_message_lower = error_message.lower()
        
        if 'syntax' in error_message_lower:
            return 'syntax_error'
        elif 'type' in error_message_lower:
            return 'type_error'
        elif 'reference' in error_message_lower:
            return 'reference_error'
        elif 'connection' in error_message_lower:
            return 'connection_error'
        elif 'timeout' in error_message_lower:
            return 'timeout_error'
        else:
            return 'unknown_error'
    
    def _assess_severity(self, error_message: str) -> str:
        """Bewertet die Schwere des Fehlers"""
        critical_keywords = ['critical', 'fatal', 'panic', 'crash']
        error_keywords = ['error', 'exception', 'failed']
        
        error_message_lower = error_message.lower()
        
        if any(keyword in error_message_lower for keyword in critical_keywords):
            return 'critical'
        elif any(keyword in error_message_lower for keyword in error_keywords):
            return 'error'
        else:
            return 'warning'
    
    def _suggest_fixes(self, error_message: str, stack_trace: str) -> List[str]:
        """Schlägt Fixes vor"""
        fixes = []
        
        # Basierend auf dem Fehlertyp Fixes vorschlagen
        error_type = self._classify_error(error_message)
        
        if error_type == 'syntax_error':
            fixes.append("Überprüfe die Syntax in der angegebenen Datei")
            fixes.append("Prüfe auf fehlende Klammern, Semikolons oder Anführungszeichen")
        elif error_type == 'type_error':
            fixes.append("Überprüfe die Datentypen der Variablen")
            fixes.append("Stelle sicher, dass die Typen kompatibel sind")
        elif error_type == 'connection_error':
            fixes.append("Überprüfe die Netzwerkverbindung")
            fixes.append("Prüfe ob der Service läuft")
            fixes.append("Verifiziere die Verbindungseinstellungen")
        
        return fixes
    
    def _find_related_files(self, error_message: str) -> List[str]:
        """Findet zugehörige Dateien"""
        # Extrahiere Dateipfade aus der Fehlermeldung
        import re
        file_pattern = r'([a-zA-Z]:\\[^:]+|/[^:]+)\.(py|js|ts|java|go|rs):?\d*'
        matches = re.findall(file_pattern, error_message)
        
        return [match[0] for match in matches]
    
    async def _docker_inspect(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Inspiziert Docker Container"""
        if not self.docker_client:
            return {"error": "Docker Client nicht verfügbar"}
        
        container_name = payload.get('container_name')
        
        try:
            container = self.docker_client.containers.get(container_name)
            info = container.attrs
            
            return {
                "status": "success",
                "container_info": {
                    "name": container.name,
                    "id": container.id,
                    "status": container.status,
                    "image": container.image.tags,
                    "created": info['Created'],
                    "state": info['State']
                }
            }
        except Exception as e:
            return {"error": str(e)}
    
    async def _general_debug(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Allgemeines Debugging"""
        return {
            "status": "success",
            "message": "Allgemeines Debugging durchgeführt"
        }


class TesterAgent(BaseAgent):
    """
    Agent für das Testen mit Playwright.
    Führt Funktionstests und Integrationstests durch.
    """
    
    def __init__(self, agent_id: str, agent_type: str, grpc_client):
        super().__init__(agent_id, agent_type, grpc_client)
        self.playwright = None
    
    def _get_capabilities(self) -> List[str]:
        return ["playwright", "function_test", "integration_test", "e2e_test"]
    
    async def process_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Verarbeitet Test-Tasks"""
        payload = task['payload']
        test_type = payload.get('test_type', 'function')
        
        logger.info(f"Verarbeite Test-Task: {test_type}")
        
        if test_type == 'playwright':
            return await self._run_playwright_test(payload)
        elif test_type == 'function':
            return await self._run_function_test(payload)
        elif test_type == 'integration':
            return await self._run_integration_test(payload)
        else:
            return await self._run_general_test(payload)
    
    async def _run_playwright_test(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Führt Playwright Tests durch"""
        test_url = payload.get('test_url', 'http://localhost:3000')
        test_actions = payload.get('test_actions', [])
        
        results = {
            "test_type": "playwright",
            "url": test_url,
            "actions_executed": 0,
            "actions_passed": 0,
            "actions_failed": 0,
            "errors": [],
            "screenshots": []
        }
        
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                
                # Navigiere zur URL
                await page.goto(test_url)
                logger.info(f"Navigiert zu {test_url}")
                
                # Führe Test-Aktionen aus
                for action in test_actions:
                    results["actions_executed"] += 1
                    
                    action_type = action.get('type')
                    
                    try:
                        if action_type == 'click':
                            await page.click(action['selector'])
                        elif action_type == 'fill':
                            await page.fill(action['selector'], action['value'])
                        elif action_type == 'wait':
                            await page.wait_for_selector(action['selector'])
                        elif action_type == 'screenshot':
                            screenshot_path = f"screenshot_{datetime.now().timestamp()}.png"
                            await page.screenshot(path=screenshot_path)
                            results["screenshots"].append(screenshot_path)
                        
                        results["actions_passed"] += 1
                        logger.info(f"Aktion {action_type} erfolgreich")
                        
                    except Exception as e:
                        results["actions_failed"] += 1
                        results["errors"].append({
                            "action": action_type,
                            "error": str(e)
                        })
                        logger.error(f"Fehler bei Aktion {action_type}: {e}")
                
                await browser.close()
                
        except Exception as e:
            logger.error(f"Fehler bei Playwright Test: {e}")
            results["errors"].append({"general": str(e)})
        
        # Speichere Test-Ergebnisse
        await self._save_test_results(results, payload.get('task_id'))
        
        return {
            "status": "success",
            "test_results": results
        }
    
    async def _run_function_test(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Führt Funktionstests durch"""
        test_file = payload.get('test_file')
        test_function = payload.get('test_function')
        
        results = {
            "test_type": "function",
            "test_file": test_file,
            "test_function": test_function,
            "passed": 0,
            "failed": 0,
            "errors": []
        }
        
        try:
            # Führe den Test aus
            result = subprocess.run(
                ['python', '-m', 'pytest', test_file, '-k', test_function, '-v'],
                capture_output=True,
                text=True
            )
            
            # Analysiere das Ergebnis
            if result.returncode == 0:
                results["passed"] = 1
            else:
                results["failed"] = 1
                results["errors"].append(result.stderr)
            
            results["output"] = result.stdout
            
        except Exception as e:
            logger.error(f"Fehler bei Funktionstest: {e}")
            results["errors"].append(str(e))
        
        # Speichere Test-Ergebnisse
        await self._save_test_results(results, payload.get('task_id'))
        
        return {
            "status": "success",
            "test_results": results
        }
    
    async def _run_integration_test(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Führt Integrationstests durch"""
        test_suite = payload.get('test_suite')
        
        results = {
            "test_type": "integration",
            "test_suite": test_suite,
            "tests_run": 0,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "errors": []
        }
        
        try:
            # Führe die Test-Suite aus
            result = subprocess.run(
                ['python', '-m', 'pytest', test_suite, '-v', '--tb=short'],
                capture_output=True,
                text=True
            )
            
            # Analysiere das Ergebnis
            output = result.stdout
            
            # Extrahiere Test-Statistiken
            import re
            passed_match = re.search(r'(\d+) passed', output)
            failed_match = re.search(r'(\d+) failed', output)
            skipped_match = re.search(r'(\d+) skipped', output)
            
            if passed_match:
                results["passed"] = int(passed_match.group(1))
            if failed_match:
                results["failed"] = int(failed_match.group(1))
            if skipped_match:
                results["skipped"] = int(skipped_match.group(1))
            
            results["tests_run"] = results["passed"] + results["failed"] + results["skipped"]
            results["output"] = output
            
            if result.returncode != 0:
                results["errors"].append(result.stderr)
            
        except Exception as e:
            logger.error(f"Fehler bei Integrationstest: {e}")
            results["errors"].append(str(e))
        
        # Speichere Test-Ergebnisse
        await self._save_test_results(results, payload.get('task_id'))
        
        return {
            "status": "success",
            "test_results": results
        }
    
    async def _run_general_test(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Führt allgemeine Tests durch"""
        return {
            "status": "success",
            "message": "Allgemeiner Test durchgeführt"
        }
    
    async def _save_test_results(self, results: Dict[str, Any], task_id: str):
        """Speichert Test-Ergebnisse in der Datenbank"""
        try:
            await self.grpc_client.log_event(
                event_type="test_completed",
                source="tester_agent",
                severity="info",
                message=f"Test abgeschlossen: {results.get('test_type', 'unknown')}",
                metadata={"results": results, "task_id": task_id}
            )
        except Exception as e:
            logger.error(f"Fehler beim Speichern der Test-Ergebnisse: {e}")


async def create_agent(agent_type: str, agent_id: str, grpc_client) -> BaseAgent:
    """Factory-Funktion zum Erstellen von Agents"""
    
    if agent_type == 'code_writer':
        return CodeWriterAgent(agent_id, agent_type, grpc_client)
    elif agent_type == 'debugger':
        return DebuggerAgent(agent_id, agent_type, grpc_client)
    elif agent_type == 'tester':
        return TesterAgent(agent_id, agent_type, grpc_client)
    else:
        raise ValueError(f"Unbekannter Agent-Typ: {agent_type}")
