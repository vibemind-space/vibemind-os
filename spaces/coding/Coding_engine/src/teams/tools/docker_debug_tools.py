"""
DockerDebugTools - Docker-Tools für Debugging.

Verantwortlichkeiten:
- Container-Logs abrufen
- Container-Status prüfen
- Container-Statistiken abrufen
- Commands in Containern ausführen
"""

import asyncio
import json
import os
import sys
from typing import Optional, List, Dict, Any
import structlog

logger = structlog.get_logger(__name__)


class DockerDebugTools:
    """
    Docker Debug Tools - Bietet Funktionen für Docker-Debugging.
    
    Verwendet Docker CLI für Container-Management.
    """
    
    def __init__(self):
        self.logger = logger.bind(component="docker_debug_tools")
    
    async def get_container_logs(
        self,
        container_name: str,
        tail: int = 100,
        since: Optional[str] = None,
        until: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Holt Logs aus einem Container.
        
        Args:
            container_name: Name oder ID des Containers
            tail: Anzahl der letzten Zeilen (default: 100)
            since: Zeit seit wann Logs geholt werden sollen (z.B. "1h", "30m")
            until: Zeit bis wann Logs geholt werden sollen
            
        Returns:
            Dict mit success, logs, metadata
        """
        self.logger.info(
            "getting_container_logs",
            container=container_name,
            tail=tail,
        )
        
        try:
            # Docker logs command
            cmd = ["docker", "logs", "--tail", str(tail)]
            
            if since:
                cmd.extend(["--since", since])
            
            if until:
                cmd.extend(["--until", until])
            
            cmd.append(container_name)
            
            # Command ausführen
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                logs = stdout.decode('utf-8', errors='replace')
                return {
                    "success": True,
                    "logs": logs,
                    "container": container_name,
                    "tail": tail,
                    "line_count": len(logs.split('\n')),
                }
            else:
                error = stderr.decode('utf-8', errors='replace')
                return {
                    "success": False,
                    "error": error,
                    "container": container_name,
                }
                
        except Exception as e:
            self.logger.error(
                "get_container_logs_failed",
                container=container_name,
                error=str(e),
            )
            return {
                "success": False,
                "error": str(e),
                "container": container_name,
            }
    
    async def get_container_status(
        self,
        container_name: str,
    ) -> Dict[str, Any]:
        """
        Holt den Status eines Containers.
        
        Args:
            container_name: Name oder ID des Containers
            
        Returns:
            Dict mit success, status, metadata
        """
        self.logger.info(
            "getting_container_status",
            container=container_name,
        )
        
        try:
            # Docker inspect command
            cmd = ["docker", "inspect", "--format", "{{json .}}", container_name]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                data = json.loads(stdout.decode('utf-8', errors='replace'))
                
                return {
                    "success": True,
                    "status": data.get("State", {}).get("Status", "unknown"),
                    "running": data.get("State", {}).get("Running", False),
                    "container": container_name,
                    "image": data.get("Config", {}).get("Image", ""),
                    "created": data.get("Created", ""),
                    "started_at": data.get("State", {}).get("StartedAt", ""),
                }
            else:
                error = stderr.decode('utf-8', errors='replace')
                return {
                    "success": False,
                    "error": error,
                    "container": container_name,
                }
                
        except Exception as e:
            self.logger.error(
                "get_container_status_failed",
                container=container_name,
                error=str(e),
            )
            return {
                "success": False,
                "error": str(e),
                "container": container_name,
            }
    
    async def get_container_stats(
        self,
        container_name: str,
    ) -> Dict[str, Any]:
        """
        Holt Statistiken eines Containers (CPU, Memory, etc.).
        
        Args:
            container_name: Name oder ID des Containers
            
        Returns:
            Dict mit success, stats, metadata
        """
        self.logger.info(
            "getting_container_stats",
            container=container_name,
        )
        
        try:
            # Docker stats command
            cmd = ["docker", "stats", "--no-stream", "--format", "json", container_name]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                stats = json.loads(stdout.decode('utf-8', errors='replace'))
                
                if stats and len(stats) > 0:
                    container_stats = stats[0]
                    
                    # CPU-Usage berechnen
                    cpu_delta = container_stats.get("cpu_stats", {}).get("cpu_usage", {}).get("total_usage", 0)
                    cpu_system = container_stats.get("cpu_stats", {}).get("system_cpu_usage", 0)
                    cpu_percent = (cpu_delta / cpu_system * 100) if cpu_system > 0 else 0
                    
                    # Memory-Usage berechnen
                    memory_usage = container_stats.get("memory_stats", {}).get("usage", 0)
                    memory_limit = container_stats.get("memory_stats", {}).get("limit", 0)
                    memory_percent = (memory_usage / memory_limit * 100) if memory_limit > 0 else 0
                    
                    # Network-Stats
                    network_rx = container_stats.get("networks", {}).get("eth0", {}).get("rx_bytes", 0)
                    network_tx = container_stats.get("networks", {}).get("eth0", {}).get("tx_bytes", 0)
                    
                    return {
                        "success": True,
                        "stats": {
                            "cpu_percent": round(cpu_percent, 2),
                            "memory_usage_mb": round(memory_usage / (1024 * 1024), 2),
                            "memory_limit_mb": round(memory_limit / (1024 * 1024), 2),
                            "memory_percent": round(memory_percent, 2),
                            "network_rx_mb": round(network_rx / (1024 * 1024), 2),
                            "network_tx_mb": round(network_tx / (1024 * 1024), 2),
                            "block_io_mb": round(container_stats.get("blkio_stats", {}).get("io_service_bytes_recursive", 0) / (1024 * 1024), 2),
                        },
                        "container": container_name,
                    }
                else:
                    return {
                        "success": False,
                        "error": "No stats available",
                        "container": container_name,
                    }
            else:
                error = stderr.decode('utf-8', errors='replace')
                return {
                    "success": False,
                    "error": error,
                    "container": container_name,
                }
                
        except Exception as e:
            self.logger.error(
                "get_container_stats_failed",
                container=container_name,
                error=str(e),
            )
            return {
                "success": False,
                "error": str(e),
                "container": container_name,
            }
    
    async def list_containers(
        self,
        all: bool = False,
        filters: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Listet alle Container auf.
        
        Args:
            all: Auch gestoppte Container anzeigen
            filters: Filter für Container (z.B. {"name": "app-*"})
            
        Returns:
            Dict mit success, containers, metadata
        """
        self.logger.info(
            "listing_containers",
            all=all,
            filters=filters,
        )
        
        try:
            # Docker ps command
            cmd = ["docker", "ps", "--format", "json"]
            
            if all:
                cmd.append("-a")
            
            if filters:
                for key, value in filters.items():
                    cmd.extend(["--filter", f"{key}={value}"])
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                containers = json.loads(stdout.decode('utf-8', errors='replace'))
                
                return {
                    "success": True,
                    "containers": containers,
                    "count": len(containers),
                }
            else:
                error = stderr.decode('utf-8', errors='replace')
                return {
                    "success": False,
                    "error": error,
                }
                
        except Exception as e:
            self.logger.error(
                "list_containers_failed",
                error=str(e),
            )
            return {
                "success": False,
                "error": str(e),
            }
    
    async def execute_in_container(
        self,
        container_name: str,
        command: str,
        workdir: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Führt einen Command in einem Container aus.
        
        Args:
            container_name: Name oder ID des Containers
            command: Auszuführender Command
            workdir: Arbeitsverzeichnis im Container
            
        Returns:
            Dict mit success, output, metadata
        """
        self.logger.info(
            "executing_in_container",
            container=container_name,
            command=command,
        )
        
        try:
            # Docker exec command
            cmd = ["docker", "exec", container_name]
            
            if workdir:
                cmd.extend(["--workdir", workdir])
            
            cmd.extend(["sh", "-c", command])
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                output = stdout.decode('utf-8', errors='replace')
                return {
                    "success": True,
                    "output": output,
                    "container": container_name,
                    "command": command,
                }
            else:
                error = stderr.decode('utf-8', errors='replace')
                return {
                    "success": False,
                    "error": error,
                    "container": container_name,
                }
                
        except Exception as e:
            self.logger.error(
                "execute_in_container_failed",
                container=container_name,
                command=command,
                error=str(e),
            )
            return {
                "success": False,
                "error": str(e),
                "container": container_name,
            }
    
    async def get_container_processes(
        self,
        container_name: str,
    ) -> Dict[str, Any]:
        """
        Holt laufende Prozesse in einem Container.
        
        Args:
            container_name: Name oder ID des Containers
            
        Returns:
            Dict mit success, processes, metadata
        """
        self.logger.info(
            "getting_container_processes",
            container=container_name,
        )
        
        try:
            # Docker top command
            cmd = ["docker", "top", "--no-trunc", "--format", "json", container_name]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                processes = json.loads(stdout.decode('utf-8', errors='replace'))
                
                return {
                    "success": True,
                    "processes": processes,
                    "count": len(processes),
                    "container": container_name,
                }
            else:
                error = stderr.decode('utf-8', errors='replace')
                return {
                    "success": False,
                    "error": error,
                    "container": container_name,
                }
                
        except Exception as e:
            self.logger.error(
                "get_container_processes_failed",
                container=container_name,
                error=str(e),
            )
            return {
                "success": False,
                "error": str(e),
                "container": container_name,
            }
    
    async def get_container_ports(
        self,
        container_name: str,
    ) -> Dict[str, Any]:
        """
        Holt Port-Mappings eines Containers.
        
        Args:
            container_name: Name oder ID des Containers
            
        Returns:
            Dict mit success, ports, metadata
        """
        self.logger.info(
            "getting_container_ports",
            container=container_name,
        )
        
        try:
            # Docker inspect command für Ports
            cmd = ["docker", "inspect", "--format", "{{json .NetworkSettings.Ports}}", container_name]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                ports = json.loads(stdout.decode('utf-8', errors='replace'))
                
                # Ports formatieren
                formatted_ports = []
                for port, config in ports.items():
                    if config:
                        host_port = config.get("HostPort")
                        container_port = port
                        protocol = config.get("Type", "tcp")
                        ip = config.get("HostIp", "0.0.0.0")
                        
                        formatted_ports.append({
                            "container_port": container_port,
                            "host_port": host_port,
                            "protocol": protocol,
                            "host_ip": ip,
                        })
                
                return {
                    "success": True,
                    "ports": formatted_ports,
                    "count": len(formatted_ports),
                    "container": container_name,
                }
            else:
                error = stderr.decode('utf-8', errors='replace')
                return {
                    "success": False,
                    "error": error,
                    "container": container_name,
                }
                
        except Exception as e:
            self.logger.error(
                "get_container_ports_failed",
                container=container_name,
                error=str(e),
            )
            return {
                "success": False,
                "error": str(e),
                "container": container_name,
            }
