"""
LogAgent - Spezialisiert auf das Sammeln von Logs
"""
import logging
import subprocess
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class LogAgent:
    """Agent für das Sammeln von Logs"""
    
    def __init__(self):
        self.name = "LogAgent"
        self.version = "1.0.0"
        self.supported_operations = [
            "collect_docker_logs",
            "collect_redis_logs",
            "collect_postgres_logs",
            "collect_application_logs",
            "collect_system_logs",
            "filter_logs",
            "analyze_logs"
        ]
    
    def execute(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sammelt Logs
        
        Args:
            parameters: Dictionary mit Logparametern
                - operation: Art der Log-Operation
                - service_name: Name des Services (z.B. docker, redis, postgres)
                - container_name: Name des Docker-Containers (optional)
                - log_file: Pfad zur Logdatei (optional)
                - lines: Anzahl der Zeilen (optional, default: 100)
                - since: Zeit seit wann Logs gesammelt werden sollen (optional)
                - filter: Filter für Logs (optional)
                - output_format: Ausgabeformat (text, json, optional, default: text)
        
        Returns:
            Dictionary mit Log-Ergebnis
        """
        operation = parameters.get('operation', 'collect_docker_logs')
        service_name = parameters.get('service_name')
        container_name = parameters.get('container_name')
        log_file = parameters.get('log_file')
        lines = parameters.get('lines', 100)
        since = parameters.get('since')
        filter_pattern = parameters.get('filter')
        output_format = parameters.get('output_format', 'text')
        
        logger.info(f"{self.name} sammelt Logs: {operation}")
        logger.info(f"Service: {service_name}")
        logger.info(f"Container: {container_name}")
        
        try:
            if operation == "collect_docker_logs":
                result = self._collect_docker_logs(container_name, lines, since, filter_pattern, output_format)
            elif operation == "collect_redis_logs":
                result = self._collect_redis_logs(lines, since, filter_pattern, output_format)
            elif operation == "collect_postgres_logs":
                result = self._collect_postgres_logs(lines, since, filter_pattern, output_format)
            elif operation == "collect_application_logs":
                result = self._collect_application_logs(log_file, lines, since, filter_pattern, output_format)
            elif operation == "collect_system_logs":
                result = self._collect_system_logs(lines, since, filter_pattern, output_format)
            elif operation == "filter_logs":
                result = self._filter_logs(parameters.get('logs', []), filter_pattern)
            elif operation == "analyze_logs":
                result = self._analyze_logs(parameters.get('logs', []))
            else:
                raise ValueError(f"Unbekannte Operation: {operation}")
            
            result['agent'] = self.name
            result['version'] = self.version
            result['timestamp'] = datetime.now().isoformat()
            
            return result
            
        except Exception as e:
            logger.error(f"Fehler beim Sammeln von Logs: {e}")
            return {
                'success': False,
                'error': str(e),
                'agent': self.name,
                'version': self.version,
                'timestamp': datetime.now().isoformat()
            }
    
    def _collect_docker_logs(self, container_name: Optional[str], lines: int,
                            since: Optional[str], filter_pattern: Optional[str],
                            output_format: str) -> Dict[str, Any]:
        """Sammelt Docker-Logs"""
        logger.info(f"Sammle Docker-Logs für Container: {container_name}")
        
        try:
            # Docker-Logs abrufen
            cmd = ['docker', 'logs']
            
            if container_name:
                cmd.extend([container_name])
            
            cmd.extend(['--tail', str(lines)])
            
            if since:
                cmd.extend(['--since', since])
            
            # Kommando ausführen
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logs = result.stdout
            
            # Logs filtern
            if filter_pattern:
                logs = self._filter_log_text(logs, filter_pattern)
            
            # Formatierung
            if output_format == 'json':
                log_lines = logs.split('\n')
                formatted_logs = [{'line': i, 'content': line} for i, line in enumerate(log_lines) if line]
            else:
                formatted_logs = logs
            
            return {
                'success': True,
                'operation': 'collect_docker_logs',
                'message': f'Docker-Logs erfolgreich gesammelt',
                'container_name': container_name,
                'lines_collected': len(formatted_logs) if isinstance(formatted_logs, list) else len(formatted_logs.split('\n')),
                'logs': formatted_logs
            }
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Fehler beim Sammeln von Docker-Logs: {e}")
            return {
                'success': False,
                'operation': 'collect_docker_logs',
                'error': str(e),
                'stderr': e.stderr
            }
        except Exception as e:
            logger.error(f"Unerwarteter Fehler: {e}")
            return {
                'success': False,
                'operation': 'collect_docker_logs',
                'error': str(e)
            }
    
    def _collect_redis_logs(self, lines: int, since: Optional[str],
                           filter_pattern: Optional[str], output_format: str) -> Dict[str, Any]:
        """Sammelt Redis-Logs"""
        logger.info("Sammle Redis-Logs")
        
        try:
            # Redis-Logs aus Docker-Container
            cmd = ['docker', 'logs', 'redis', '--tail', str(lines)]
            
            if since:
                cmd.extend(['--since', since])
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logs = result.stdout
            
            # Logs filtern
            if filter_pattern:
                logs = self._filter_log_text(logs, filter_pattern)
            
            # Formatierung
            if output_format == 'json':
                log_lines = logs.split('\n')
                formatted_logs = [{'line': i, 'content': line} for i, line in enumerate(log_lines) if line]
            else:
                formatted_logs = logs
            
            return {
                'success': True,
                'operation': 'collect_redis_logs',
                'message': 'Redis-Logs erfolgreich gesammelt',
                'lines_collected': len(formatted_logs) if isinstance(formatted_logs, list) else len(formatted_logs.split('\n')),
                'logs': formatted_logs
            }
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Fehler beim Sammeln von Redis-Logs: {e}")
            return {
                'success': False,
                'operation': 'collect_redis_logs',
                'error': str(e),
                'stderr': e.stderr
            }
    
    def _collect_postgres_logs(self, lines: int, since: Optional[str],
                              filter_pattern: Optional[str], output_format: str) -> Dict[str, Any]:
        """Sammelt PostgreSQL-Logs"""
        logger.info("Sammle PostgreSQL-Logs")
        
        try:
            # PostgreSQL-Logs aus Docker-Container
            cmd = ['docker', 'logs', 'postgres', '--tail', str(lines)]
            
            if since:
                cmd.extend(['--since', since])
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logs = result.stdout
            
            # Logs filtern
            if filter_pattern:
                logs = self._filter_log_text(logs, filter_pattern)
            
            # Formatierung
            if output_format == 'json':
                log_lines = logs.split('\n')
                formatted_logs = [{'line': i, 'content': line} for i, line in enumerate(log_lines) if line]
            else:
                formatted_logs = logs
            
            return {
                'success': True,
                'operation': 'collect_postgres_logs',
                'message': 'PostgreSQL-Logs erfolgreich gesammelt',
                'lines_collected': len(formatted_logs) if isinstance(formatted_logs, list) else len(formatted_logs.split('\n')),
                'logs': formatted_logs
            }
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Fehler beim Sammeln von PostgreSQL-Logs: {e}")
            return {
                'success': False,
                'operation': 'collect_postgres_logs',
                'error': str(e),
                'stderr': e.stderr
            }
    
    def _collect_application_logs(self, log_file: Optional[str], lines: int,
                                  since: Optional[str], filter_pattern: Optional[str],
                                  output_format: str) -> Dict[str, Any]:
        """Sammelt Anwendungs-Logs"""
        logger.info(f"Sammle Anwendungs-Logs aus: {log_file}")
        
        try:
            if not log_file:
                # Standard-Logdateien suchen
                log_paths = [
                    'logs/app.log',
                    'logs/application.log',
                    'logs/error.log',
                    'logs/debug.log'
                ]
                
                logs = ""
                for path in log_paths:
                    if Path(path).exists():
                        with open(path, 'r', encoding='utf-8') as f:
                            logs += f.read() + "\n"
            else:
                # Spezifische Logdatei lesen
                with open(log_file, 'r', encoding='utf-8') as f:
                    logs = f.read()
            
            # Letzte N Zeilen
            log_lines = logs.split('\n')
            if lines:
                log_lines = log_lines[-lines:]
            
            logs = '\n'.join(log_lines)
            
            # Logs filtern
            if filter_pattern:
                logs = self._filter_log_text(logs, filter_pattern)
            
            # Formatierung
            if output_format == 'json':
                formatted_logs = [{'line': i, 'content': line} for i, line in enumerate(log_lines) if line]
            else:
                formatted_logs = logs
            
            return {
                'success': True,
                'operation': 'collect_application_logs',
                'message': 'Anwendungs-Logs erfolgreich gesammelt',
                'log_file': log_file,
                'lines_collected': len(formatted_logs) if isinstance(formatted_logs, list) else len(formatted_logs.split('\n')),
                'logs': formatted_logs
            }
            
        except FileNotFoundError:
            logger.error(f"Logdatei nicht gefunden: {log_file}")
            return {
                'success': False,
                'operation': 'collect_application_logs',
                'error': f'Logdatei nicht gefunden: {log_file}'
            }
        except Exception as e:
            logger.error(f"Fehler beim Sammeln von Anwendungs-Logs: {e}")
            return {
                'success': False,
                'operation': 'collect_application_logs',
                'error': str(e)
            }
    
    def _collect_system_logs(self, lines: int, since: Optional[str],
                            filter_pattern: Optional[str], output_format: str) -> Dict[str, Any]:
        """Sammelt System-Logs"""
        logger.info("Sammle System-Logs")
        
        try:
            # System-Logs abrufen (Windows)
            cmd = ['wevtutil', 'qe', 'System', '/c:' + str(lines), '/rd:true', '/f:text']
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logs = result.stdout
            
            # Logs filtern
            if filter_pattern:
                logs = self._filter_log_text(logs, filter_pattern)
            
            # Formatierung
            if output_format == 'json':
                log_lines = logs.split('\n')
                formatted_logs = [{'line': i, 'content': line} for i, line in enumerate(log_lines) if line]
            else:
                formatted_logs = logs
            
            return {
                'success': True,
                'operation': 'collect_system_logs',
                'message': 'System-Logs erfolgreich gesammelt',
                'lines_collected': len(formatted_logs) if isinstance(formatted_logs, list) else len(formatted_logs.split('\n')),
                'logs': formatted_logs
            }
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Fehler beim Sammeln von System-Logs: {e}")
            return {
                'success': False,
                'operation': 'collect_system_logs',
                'error': str(e),
                'stderr': e.stderr
            }
    
    def _filter_log_text(self, logs: str, filter_pattern: str) -> str:
        """Filtert Logs nach einem Muster"""
        import re
        lines = logs.split('\n')
        filtered_lines = [line for line in lines if re.search(filter_pattern, line, re.IGNORECASE)]
        return '\n'.join(filtered_lines)
    
    def _filter_logs(self, logs: List[Dict[str, Any]], filter_pattern: Optional[str]) -> Dict[str, Any]:
        """Filtert eine Liste von Logs"""
        logger.info(f"Filtere Logs mit Muster: {filter_pattern}")
        
        if not filter_pattern:
            return {
                'success': True,
                'operation': 'filter_logs',
                'message': 'Kein Filter angegeben, alle Logs zurückgegeben',
                'filtered_logs': logs,
                'count': len(logs)
            }
        
        import re
        filtered_logs = []
        
        for log in logs:
            content = str(log.get('content', ''))
            if re.search(filter_pattern, content, re.IGNORECASE):
                filtered_logs.append(log)
        
        return {
            'success': True,
            'operation': 'filter_logs',
            'message': f'Logs gefiltert: {len(filtered_logs)}/{len(logs)} Treffer',
            'filter_pattern': filter_pattern,
            'filtered_logs': filtered_logs,
            'count': len(filtered_logs)
        }
    
    def _analyze_logs(self, logs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analysiert Logs und gibt Statistiken zurück"""
        logger.info("Analysiere Logs...")
        
        if not logs:
            return {
                'success': True,
                'operation': 'analyze_logs',
                'message': 'Keine Logs zur Analyse vorhanden',
                'statistics': {}
            }
        
        # Statistiken berechnen
        total_logs = len(logs)
        
        # Fehler zählen
        error_count = sum(1 for log in logs if 'error' in str(log.get('content', '')).lower())
        warning_count = sum(1 for log in logs if 'warning' in str(log.get('content', '')).lower())
        info_count = sum(1 for log in logs if 'info' in str(log.get('content', '')).lower())
        
        # Häufigste Muster
        import re
        from collections import Counter
        
        all_content = ' '.join([str(log.get('content', '')) for log in logs])
        words = re.findall(r'\b\w+\b', all_content.lower())
        word_counts = Counter(words)
        top_words = word_counts.most_common(10)
        
        return {
            'success': True,
            'operation': 'analyze_logs',
            'message': 'Log-Analyse abgeschlossen',
            'statistics': {
                'total_logs': total_logs,
                'error_count': error_count,
                'warning_count': warning_count,
                'info_count': info_count,
                'error_rate': f"{(error_count / total_logs * 100):.2f}%" if total_logs > 0 else "0%",
                'top_words': top_words
            }
        }
    
    def get_status(self) -> Dict[str, Any]:
        """Gibt den Status des Agenten zurück"""
        return {
            'name': self.name,
            'version': self.version,
            'supported_operations': self.supported_operations,
            'status': 'ready'
        }
