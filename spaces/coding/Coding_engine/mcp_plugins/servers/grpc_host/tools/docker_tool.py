"""
Docker Tool für EventFixTeam
Bietet Funktionen zur Interaktion mit Docker-Containern und -Images
"""

import os
import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


class DockerTool:
    """Tool für Docker-Operationen"""
    
    def __init__(self, base_dir: str = "."):
        """
        Docker Tool initialisieren
        
        Args:
            base_dir: Basisverzeichnis für das Projekt
        """
        self.base_dir = Path(base_dir)
        self.docker_dir = self.base_dir / "docker"
        self.docker_dir.mkdir(exist_ok=True)
        
        logger.info(f"Docker Tool initialisiert mit Basisverzeichnis: {base_dir}")
    
    def execute_command(self, command: str, args: List[Any] = None, kwargs: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Docker-Befehl ausführen
        
        Args:
            command: Docker-Befehl (z.B. "ps", "logs", "exec")
            args: Argumente für den Befehl
            kwargs: Schlüsselwortargumente für den Befehl
        
        Returns:
            Dict mit success, output, logs, error
        """
        try:
            args = args or []
            kwargs = kwargs or {}
            
            # Docker-Befehl zusammenstellen
            docker_cmd = ["docker", command] + [str(arg) for arg in args]
            
            # Optionale Parameter hinzufügen
            if "container_name" in kwargs:
                docker_cmd.extend(["--name", kwargs["container_name"]])
            if "detach" in kwargs and kwargs["detach"]:
                docker_cmd.append("-d")
            if "interactive" in kwargs and kwargs["interactive"]:
                docker_cmd.append("-i")
            if "tty" in kwargs and kwargs["tty"]:
                docker_cmd.append("-t")
            if "env" in kwargs:
                for key, value in kwargs["env"].items():
                    docker_cmd.extend(["-e", f"{key}={value}"])
            if "volumes" in kwargs:
                for volume in kwargs["volumes"]:
                    docker_cmd.extend(["-v", volume])
            if "ports" in kwargs:
                for port in kwargs["ports"]:
                    docker_cmd.extend(["-p", port])
            if "workdir" in kwargs:
                docker_cmd.extend(["-w", kwargs["workdir"]])
            if "user" in kwargs:
                docker_cmd.extend(["-u", kwargs["user"]])
            if "rm" in kwargs and kwargs["rm"]:
                docker_cmd.append("--rm")
            
            # Befehl ausführen
            logger.info(f"Docker-Befehl ausführen: {' '.join(docker_cmd)}")
            result = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                cwd=str(self.base_dir)
            )
            
            # Logs speichern
            logs = self._save_logs(command, args, result.stdout, result.stderr)
            
            if result.returncode != 0:
                logger.error(f"Docker-Befehl fehlgeschlagen: {result.stderr}")
                return {
                    "success": False,
                    "error": result.stderr,
                    "logs": logs
                }
            
            # Output parsen
            output = self._parse_output(command, result.stdout)
            
            return {
                "success": True,
                "output": output,
                "logs": logs
            }
        except Exception as e:
            logger.error(f"Fehler beim Ausführen des Docker-Befehls: {e}")
            return {
                "success": False,
                "error": str(e),
                "logs": ""
            }
    
    def _parse_output(self, command: str, output: str) -> Any:
        """
        Docker-Output parsen
        
        Args:
            command: Docker-Befehl
            output: Output des Befehls
        
        Returns:
            Geparster Output
        """
        try:
            if command in ["ps", "images", "networks", "volumes"]:
                # Tabellarischen Output parsen
                lines = output.strip().split('\n')
                if len(lines) < 2:
                    return []
                
                headers = [h.lower() for h in lines[0].split()]
                rows = []
                for line in lines[1:]:
                    values = line.split()
                    row = dict(zip(headers, values))
                    rows.append(row)
                return rows
            elif command == "inspect":
                # JSON-Output parsen
                return json.loads(output)
            elif command == "logs":
                # Logs als Text zurückgeben
                return output
            else:
                # Text zurückgeben
                return output
        except Exception as e:
            logger.error(f"Fehler beim Parsen des Docker-Outputs: {e}")
            return output
    
    def _save_logs(self, command: str, args: List[Any], stdout: str, stderr: str) -> str:
        """
        Docker-Logs speichern
        
        Args:
            command: Docker-Befehl
            args: Argumente für den Befehl
            stdout: Standard Output
            stderr: Standard Error
        
        Returns:
            Pfad zur Log-Datei
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_file = self.docker_dir / f"docker_{command}_{timestamp}.log"
            
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write(f"Command: docker {command} {' '.join(str(arg) for arg in args)}\n")
                f.write(f"Timestamp: {timestamp}\n")
                f.write("=" * 80 + "\n\n")
                f.write("STDOUT:\n")
                f.write(stdout)
                f.write("\n\n")
                f.write("STDERR:\n")
                f.write(stderr)
            
            logger.info(f"Docker-Logs gespeichert: {log_file}")
            return str(log_file)
        except Exception as e:
            logger.error(f"Fehler beim Speichern der Docker-Logs: {e}")
            return ""
    
    def get_container_logs(self, container_name: str, tail: int = 100) -> Dict[str, Any]:
        """
        Container-Logs abrufen
        
        Args:
            container_name: Name des Containers
            tail: Anzahl der letzten Zeilen
        
        Returns:
            Dict mit success, output, logs, error
        """
        return self.execute_command(
            "logs",
            [container_name],
            {"tail": tail}
        )
    
    def get_container_status(self, container_name: str) -> Dict[str, Any]:
        """
        Container-Status abrufen
        
        Args:
            container_name: Name des Containers
        
        Returns:
            Dict mit success, output, logs, error
        """
        return self.execute_command(
            "inspect",
            [container_name]
        )
    
    def list_containers(self, all_containers: bool = False) -> Dict[str, Any]:
        """
        Container auflisten
        
        Args:
            all_containers: Alle Container (auch gestoppte) auflisten
        
        Returns:
            Dict mit success, output, logs, error
        """
        return self.execute_command(
            "ps",
            [],
            {"all": all_containers}
        )
    
    def start_container(self, container_name: str) -> Dict[str, Any]:
        """
        Container starten
        
        Args:
            container_name: Name des Containers
        
        Returns:
            Dict mit success, output, logs, error
        """
        return self.execute_command(
            "start",
            [container_name]
        )
    
    def stop_container(self, container_name: str) -> Dict[str, Any]:
        """
        Container stoppen
        
        Args:
            container_name: Name des Containers
        
        Returns:
            Dict mit success, output, logs, error
        """
        return self.execute_command(
            "stop",
            [container_name]
        )
    
    def restart_container(self, container_name: str) -> Dict[str, Any]:
        """
        Container neu starten
        
        Args:
            container_name: Name des Containers
        
        Returns:
            Dict mit success, output, logs, error
        """
        return self.execute_command(
            "restart",
            [container_name]
        )
    
    def exec_command(self, container_name: str, command: str) -> Dict[str, Any]:
        """
        Befehl im Container ausführen
        
        Args:
            container_name: Name des Containers
            command: Befehl, der im Container ausgeführt werden soll
        
        Returns:
            Dict mit success, output, logs, error
        """
        return self.execute_command(
            "exec",
            [container_name, command]
        )
    
    def build_image(self, dockerfile_path: str, image_name: str, build_args: Dict[str, str] = None) -> Dict[str, Any]:
        """
        Docker-Image bauen
        
        Args:
            dockerfile_path: Pfad zur Dockerfile
            image_name: Name des Images
            build_args: Build-Argumente
        
        Returns:
            Dict mit success, output, logs, error
        """
        kwargs = {"tag": image_name}
        if build_args:
            kwargs["build_args"] = build_args
        
        return self.execute_command(
            "build",
            ["-f", dockerfile_path, "."],
            kwargs
        )
    
    def run_container(self, image_name: str, command: str = None, **kwargs) -> Dict[str, Any]:
        """
        Container starten
        
        Args:
            image_name: Name des Images
            command: Befehl, der im Container ausgeführt werden soll
            **kwargs: Zusätzliche Parameter (container_name, detach, env, volumes, ports, etc.)
        
        Returns:
            Dict mit success, output, logs, error
        """
        args = [image_name]
        if command:
            args.append(command)
        
        return self.execute_command(
            "run",
            args,
            kwargs
        )
    
    def remove_container(self, container_name: str, force: bool = False) -> Dict[str, Any]:
        """
        Container entfernen
        
        Args:
            container_name: Name des Containers
            force: Container erzwingt entfernen
        
        Returns:
            Dict mit success, output, logs, error
        """
        return self.execute_command(
            "rm",
            [container_name],
            {"force": force}
        )
    
    def remove_image(self, image_name: str, force: bool = False) -> Dict[str, Any]:
        """
        Image entfernen
        
        Args:
            image_name: Name des Images
            force: Image erzwingt entfernen
        
        Returns:
            Dict mit success, output, logs, error
        """
        return self.execute_command(
            "rmi",
            [image_name],
            {"force": force}
        )
    
    def get_networks(self) -> Dict[str, Any]:
        """
        Docker-Netzwerke auflisten
        
        Returns:
            Dict mit success, output, logs, error
        """
        return self.execute_command(
            "network",
            ["ls"]
        )
    
    def get_volumes(self) -> Dict[str, Any]:
        """
        Docker-Volumes auflisten
        
        Returns:
            Dict mit success, output, logs, error
        """
        return self.execute_command(
            "volume",
            ["ls"]
        )
