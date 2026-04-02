"""
DockerAgent - Spezialisiert für Docker-Operationen

Dieser Agent ist verantwortlich für:
- Container starten
- Container stoppen
- Container löschen
- Container-Logs abrufen
- Container-Status prüfen
- Images bauen
- Images löschen
- Docker Compose ausführen
- Docker Compose stoppen
- Docker Compose Logs abrufen
"""

import json
import logging
import subprocess
from typing import Any, Dict, List, Optional, Union
from datetime import datetime
from enum import Enum

# Logging konfigurieren
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ContainerState(Enum):
    """Container-Zustände"""
    RUNNING = "running"
    STOPPED = "stopped"
    PAUSED = "paused"
    RESTARTING = "restarting"
    DEAD = "dead"
    CREATED = "created"
    EXITED = "exited"


class DockerAgent:
    """Agent für Docker-Operationen"""
    
    def __init__(self):
        """Initialisiert den DockerAgent"""
        self.stats = {
            "operations": [],
            "containers_started": 0,
            "containers_stopped": 0,
            "containers_removed": 0,
            "images_built": 0,
            "images_removed": 0,
            "logs_retrieved": 0
        }
        
        logger.info("DockerAgent initialisiert")
    
    def _log_operation(
        self,
        operation: str,
        details: Optional[Dict[str, Any]] = None
    ):
        """Protokolliert eine Operation"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "operation": operation,
            "details": details or {}
        }
        
        self.stats["operations"].append(log_entry)
        logger.info(f"{operation}: {details}")
    
    def _run_command(
        self,
        command: List[str],
        capture_output: bool = True
    ) -> Dict[str, Any]:
        """
        Führt einen Befehl aus
        
        Args:
            command: Befehl als Liste
            capture_output: Output capturen
            
        Returns:
            Dict mit Status und Output
        """
        try:
            result = subprocess.run(
                command,
                capture_output=capture_output,
                text=True,
                check=False
            )
            
            return {
                "status": "success" if result.returncode == 0 else "error",
                "returncode": result.returncode,
                "stdout": result.stdout if capture_output else "",
                "stderr": result.stderr if capture_output else ""
            }
        except Exception as e:
            logger.error(f"Fehler beim Ausführen des Befehls: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def start_container(
        self,
        container_name: str
    ) -> Dict[str, Any]:
        """
        Startet einen Container
        
        Args:
            container_name: Name des Containers
            
        Returns:
            Dict mit Status
        """
        try:
            result = self._run_command(
                ["docker", "start", container_name]
            )
            
            if result["status"] == "success":
                self.stats["containers_started"] += 1
                
                self._log_operation(
                    "start_container",
                    {"container_name": container_name}
                )
            
            return result
        except Exception as e:
            logger.error(f"Fehler beim Starten des Containers: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def stop_container(
        self,
        container_name: str
    ) -> Dict[str, Any]:
        """
        Stoppt einen Container
        
        Args:
            container_name: Name des Containers
            
        Returns:
            Dict mit Status
        """
        try:
            result = self._run_command(
                ["docker", "stop", container_name]
            )
            
            if result["status"] == "success":
                self.stats["containers_stopped"] += 1
                
                self._log_operation(
                    "stop_container",
                    {"container_name": container_name}
                )
            
            return result
        except Exception as e:
            logger.error(f"Fehler beim Stoppen des Containers: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def remove_container(
        self,
        container_name: str,
        force: bool = False
    ) -> Dict[str, Any]:
        """
        Löscht einen Container
        
        Args:
            container_name: Name des Containers
            force: Force löschen
            
        Returns:
            Dict mit Status
        """
        try:
            command = ["docker", "rm"]
            if force:
                command.append("-f")
            command.append(container_name)
            
            result = self._run_command(command)
            
            if result["status"] == "success":
                self.stats["containers_removed"] += 1
                
                self._log_operation(
                    "remove_container",
                    {
                        "container_name": container_name,
                        "force": force
                    }
                )
            
            return result
        except Exception as e:
            logger.error(f"Fehler beim Löschen des Containers: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def get_container_logs(
        self,
        container_name: str,
        tail: Optional[int] = None,
        follow: bool = False
    ) -> Dict[str, Any]:
        """
        Holt Container-Logs
        
        Args:
            container_name: Name des Containers
            tail: Anzahl der letzten Zeilen
            follow: Follow logs
            
        Returns:
            Dict mit Status und Logs
        """
        try:
            command = ["docker", "logs"]
            
            if tail:
                command.extend(["--tail", str(tail)])
            
            if follow:
                command.append("-f")
            
            command.append(container_name)
            
            result = self._run_command(command)
            
            if result["status"] == "success":
                self.stats["logs_retrieved"] += 1
                
                self._log_operation(
                    "get_container_logs",
                    {
                        "container_name": container_name,
                        "tail": tail,
                        "follow": follow
                    }
                )
            
            return result
        except Exception as e:
            logger.error(f"Fehler beim Holen der Container-Logs: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def get_container_status(
        self,
        container_name: str
    ) -> Dict[str, Any]:
        """
        Holt den Status eines Containers
        
        Args:
            container_name: Name des Containers
            
        Returns:
            Dict mit Status und Container-Info
        """
        try:
            result = self._run_command(
                ["docker", "inspect", "--format", "{{json .State}}", container_name]
            )
            
            if result["status"] == "success":
                state = json.loads(result["stdout"])
                
                self._log_operation(
                    "get_container_status",
                    {"container_name": container_name}
                )
                
                return {
                    "status": "success",
                    "container_name": container_name,
                    "state": state
                }
            
            return result
        except Exception as e:
            logger.error(f"Fehler beim Holen des Container-Status: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def list_containers(
        self,
        all_containers: bool = False
    ) -> Dict[str, Any]:
        """
        Listet alle Container auf
        
        Args:
            all_containers: Alle Container (inkl. gestoppte)
            
        Returns:
            Dict mit Status und Container-Liste
        """
        try:
            command = ["docker", "ps", "--format", "{{json .}}"]
            
            if all_containers:
                command.append("-a")
            
            result = self._run_command(command)
            
            if result["status"] == "success":
                containers = []
                for line in result["stdout"].strip().split("\n"):
                    if line:
                        containers.append(json.loads(line))
                
                self._log_operation(
                    "list_containers",
                    {
                        "count": len(containers),
                        "all": all_containers
                    }
                )
                
                return {
                    "status": "success",
                    "containers": containers
                }
            
            return result
        except Exception as e:
            logger.error(f"Fehler beim Auflisten der Container: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def build_image(
        self,
        dockerfile_path: str,
        image_name: str,
        tag: str = "latest",
        build_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Baut ein Docker-Image
        
        Args:
            dockerfile_path: Pfad zum Dockerfile
            image_name: Name des Images
            tag: Tag des Images
            build_context: Build Context
            
        Returns:
            Dict mit Status
        """
        try:
            command = ["docker", "build"]
            
            if build_context:
                command.extend(["-f", dockerfile_path, build_context])
            else:
                command.extend(["-f", dockerfile_path, "."])
            
            command.extend(["-t", f"{image_name}:{tag}"])
            
            result = self._run_command(command)
            
            if result["status"] == "success":
                self.stats["images_built"] += 1
                
                self._log_operation(
                    "build_image",
                    {
                        "image_name": image_name,
                        "tag": tag,
                        "dockerfile_path": dockerfile_path
                    }
                )
            
            return result
        except Exception as e:
            logger.error(f"Fehler beim Bauen des Images: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def remove_image(
        self,
        image_name: str,
        tag: str = "latest",
        force: bool = False
    ) -> Dict[str, Any]:
        """
        Löscht ein Docker-Image
        
        Args:
            image_name: Name des Images
            tag: Tag des Images
            force: Force löschen
            
        Returns:
            Dict mit Status
        """
        try:
            command = ["docker", "rmi"]
            if force:
                command.append("-f")
            command.append(f"{image_name}:{tag}")
            
            result = self._run_command(command)
            
            if result["status"] == "success":
                self.stats["images_removed"] += 1
                
                self._log_operation(
                    "remove_image",
                    {
                        "image_name": image_name,
                        "tag": tag,
                        "force": force
                    }
                )
            
            return result
        except Exception as e:
            logger.error(f"Fehler beim Löschen des Images: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def list_images(self) -> Dict[str, Any]:
        """
        Listet alle Images auf
        
        Returns:
            Dict mit Status und Image-Liste
        """
        try:
            result = self._run_command(
                ["docker", "images", "--format", "{{json .}}"]
            )
            
            if result["status"] == "success":
                images = []
                for line in result["stdout"].strip().split("\n"):
                    if line:
                        images.append(json.loads(line))
                
                self._log_operation(
                    "list_images",
                    {"count": len(images)}
                )
                
                return {
                    "status": "success",
                    "images": images
                }
            
            return result
        except Exception as e:
            logger.error(f"Fehler beim Auflisten der Images: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def compose_up(
        self,
        compose_file: str,
        detached: bool = True
    ) -> Dict[str, Any]:
        """
        Startet Docker Compose
        
        Args:
            compose_file: Pfad zur docker-compose.yml
            detached: Detached mode
            
        Returns:
            Dict mit Status
        """
        try:
            command = ["docker-compose", "-f", compose_file, "up"]
            
            if detached:
                command.append("-d")
            
            result = self._run_command(command)
            
            self._log_operation(
                "compose_up",
                {
                    "compose_file": compose_file,
                    "detached": detached
                }
            )
            
            return result
        except Exception as e:
            logger.error(f"Fehler beim Starten von Docker Compose: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def compose_down(
        self,
        compose_file: str
    ) -> Dict[str, Any]:
        """
        Stoppt Docker Compose
        
        Args:
            compose_file: Pfad zur docker-compose.yml
            
        Returns:
            Dict mit Status
        """
        try:
            result = self._run_command(
                ["docker-compose", "-f", compose_file, "down"]
            )
            
            self._log_operation(
                "compose_down",
                {"compose_file": compose_file}
            )
            
            return result
        except Exception as e:
            logger.error(f"Fehler beim Stoppen von Docker Compose: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def compose_logs(
        self,
        compose_file: str,
        service: Optional[str] = None,
        tail: Optional[int] = None,
        follow: bool = False
    ) -> Dict[str, Any]:
        """
        Holt Docker Compose Logs
        
        Args:
            compose_file: Pfad zur docker-compose.yml
            service: Service Name
            tail: Anzahl der letzten Zeilen
            follow: Follow logs
            
        Returns:
            Dict mit Status und Logs
        """
        try:
            command = ["docker-compose", "-f", compose_file, "logs"]
            
            if tail:
                command.extend(["--tail", str(tail)])
            
            if follow:
                command.append("-f")
            
            if service:
                command.append(service)
            
            result = self._run_command(command)
            
            if result["status"] == "success":
                self.stats["logs_retrieved"] += 1
                
                self._log_operation(
                    "compose_logs",
                    {
                        "compose_file": compose_file,
                        "service": service,
                        "tail": tail,
                        "follow": follow
                    }
                )
            
            return result
        except Exception as e:
            logger.error(f"Fehler beim Holen der Docker Compose Logs: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def compose_ps(
        self,
        compose_file: str
    ) -> Dict[str, Any]:
        """
        Listet Docker Compose Services auf
        
        Args:
            compose_file: Pfad zur docker-compose.yml
            
        Returns:
            Dict mit Status und Service-Liste
        """
        try:
            result = self._run_command(
                ["docker-compose", "-f", compose_file, "ps"]
            )
            
            self._log_operation(
                "compose_ps",
                {"compose_file": compose_file}
            )
            
            return result
        except Exception as e:
            logger.error(f"Fehler beim Auflisten der Docker Compose Services: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def get_stats(self) -> Dict[str, Any]:
        """Gibt Statistiken zurück"""
        return {
            "status": "success",
            "stats": self.stats
        }
    
    def get_operations_log(
        self,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """Gibt das Operations-Log zurück"""
        operations = self.stats["operations"]
        
        if limit:
            operations = operations[-limit:]
        
        return {
            "status": "success",
            "operations": operations
        }
    
    def health_check(self) -> bool:
        """Health Check"""
        result = self._run_command(["docker", "--version"])
        return result["status"] == "success"


def main():
    """Test-Implementierung"""
    try:
        agent = DockerAgent()
        
        # Health Check
        print(f"Health Check: {agent.health_check()}")
        
        # List Containers
        containers = agent.list_containers(all_containers=True)
        print(f"Containers: {containers}")
        
        # List Images
        images = agent.list_images()
        print(f"Images: {images}")
        
        # Stats
        stats = agent.get_stats()
        print(f"Stats: {stats}")
    except Exception as e:
        print(f"Fehler: {e}")


if __name__ == "__main__":
    main()
