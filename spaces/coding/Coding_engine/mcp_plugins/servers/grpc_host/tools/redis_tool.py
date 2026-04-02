"""
Redis Tool für EventFixTeam
Bietet Funktionen zur Interaktion mit Redis für Debugging und Monitoring
"""

import os
import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


class RedisTool:
    """Tool für Redis-Operationen"""
    
    def __init__(self, base_dir: str = ".", redis_host: str = "localhost", redis_port: int = 6379):
        """
        Redis Tool initialisieren
        
        Args:
            base_dir: Basisverzeichnis für das Projekt
            redis_host: Redis-Host
            redis_port: Redis-Port
        """
        self.base_dir = Path(base_dir)
        self.redis_dir = self.base_dir / "redis"
        self.redis_dir.mkdir(exist_ok=True)
        self.redis_host = redis_host
        self.redis_port = redis_port
        
        logger.info(f"Redis Tool initialisiert mit Host: {redis_host}:{redis_port}")
    
    def execute_command(self, command: str, args: List[Any] = None) -> Dict[str, Any]:
        """
        Redis-Befehl ausführen
        
        Args:
            command: Redis-Befehl (z.B. "GET", "SET", "KEYS", "HGETALL")
            args: Argumente für den Befehl
        
        Returns:
            Dict mit success, output, logs, error
        """
        try:
            args = args or []
            
            # Redis-Befehl zusammenstellen
            redis_cmd = ["redis-cli", "-h", self.redis_host, "-p", str(self.redis_port), command] + [str(arg) for arg in args]
            
            # Befehl ausführen
            logger.info(f"Redis-Befehl ausführen: {' '.join(redis_cmd)}")
            result = subprocess.run(
                redis_cmd,
                capture_output=True,
                text=True,
                cwd=str(self.base_dir)
            )
            
            # Logs speichern
            logs = self._save_logs(command, args, result.stdout, result.stderr)
            
            if result.returncode != 0:
                logger.error(f"Redis-Befehl fehlgeschlagen: {result.stderr}")
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
            logger.error(f"Fehler beim Ausführen des Redis-Befehls: {e}")
            return {
                "success": False,
                "error": str(e),
                "logs": ""
            }
    
    def _parse_output(self, command: str, output: str) -> Any:
        """
        Redis-Output parsen
        
        Args:
            command: Redis-Befehl
            output: Output des Befehls
        
        Returns:
            Geparster Output
        """
        try:
            if command.upper() in ["GET", "HGET", "LINDEX", "LPOP", "RPOP"]:
                # String-Wert zurückgeben
                return output.strip()
            elif command.upper() in ["SET", "HSET", "LPUSH", "RPUSH", "SADD", "ZADD"]:
                # OK zurückgeben
                return output.strip()
            elif command.upper() in ["KEYS", "SMEMBERS", "ZRANGE"]:
                # Liste von Keys zurückgeben
                if output.strip():
                    return [line.strip() for line in output.strip().split('\n')]
                return []
            elif command.upper() in ["HGETALL", "HKEYS", "HVALS"]:
                # Hash-Daten zurückgeben
                if output.strip():
                    lines = [line.strip() for line in output.strip().split('\n')]
                    if command.upper() == "HGETALL":
                        # Key-Value Paare
                        result = {}
                        for i in range(0, len(lines), 2):
                            if i + 1 < len(lines):
                                result[lines[i]] = lines[i + 1]
                        return result
                    return lines
                return {}
            elif command.upper() in ["DBSIZE", "SCARD", "ZCARD", "LLEN", "HLEN"]:
                # Integer-Wert zurückgeben
                return int(output.strip())
            elif command.upper() in ["INFO", "CONFIG GET"]:
                # Info-Daten zurückgeben
                return output.strip()
            else:
                # Text zurückgeben
                return output.strip()
        except Exception as e:
            logger.error(f"Fehler beim Parsen des Redis-Outputs: {e}")
            return output.strip()
    
    def _save_logs(self, command: str, args: List[Any], stdout: str, stderr: str) -> str:
        """
        Redis-Logs speichern
        
        Args:
            command: Redis-Befehl
            args: Argumente für den Befehl
            stdout: Standard Output
            stderr: Standard Error
        
        Returns:
            Pfad zur Log-Datei
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_file = self.redis_dir / f"redis_{command}_{timestamp}.log"
            
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write(f"Command: {command} {' '.join(str(arg) for arg in args)}\n")
                f.write(f"Host: {self.redis_host}:{self.redis_port}\n")
                f.write(f"Timestamp: {timestamp}\n")
                f.write("=" * 80 + "\n\n")
                f.write("STDOUT:\n")
                f.write(stdout)
                f.write("\n\n")
                f.write("STDERR:\n")
                f.write(stderr)
            
            logger.info(f"Redis-Logs gespeichert: {log_file}")
            return str(log_file)
        except Exception as e:
            logger.error(f"Fehler beim Speichern der Redis-Logs: {e}")
            return ""
    
    def get(self, key: str) -> Dict[str, Any]:
        """
        Wert aus Redis abrufen
        
        Args:
            key: Redis-Key
        
        Returns:
            Dict mit success, output, logs, error
        """
        return self.execute_command("GET", [key])
    
    def set(self, key: str, value: str, ttl: int = None) -> Dict[str, Any]:
        """
        Wert in Redis speichern
        
        Args:
            key: Redis-Key
            value: Redis-Wert
            ttl: Time-to-Live in Sekunden
        
        Returns:
            Dict mit success, output, logs, error
        """
        args = [key, value]
        if ttl:
            args.extend(["EX", str(ttl)])
        return self.execute_command("SET", args)
    
    def delete(self, key: str) -> Dict[str, Any]:
        """
        Key aus Redis löschen
        
        Args:
            key: Redis-Key
        
        Returns:
            Dict mit success, output, logs, error
        """
        return self.execute_command("DEL", [key])
    
    def keys(self, pattern: str = "*") -> Dict[str, Any]:
        """
        Keys in Redis auflisten
        
        Args:
            pattern: Pattern für Keys (z.B. "user:*")
        
        Returns:
            Dict mit success, output, logs, error
        """
        return self.execute_command("KEYS", [pattern])
    
    def exists(self, key: str) -> Dict[str, Any]:
        """
        Prüfen, ob Key existiert
        
        Args:
            key: Redis-Key
        
        Returns:
            Dict mit success, output, logs, error
        """
        return self.execute_command("EXISTS", [key])
    
    def ttl(self, key: str) -> Dict[str, Any]:
        """
        TTL eines Keys abrufen
        
        Args:
            key: Redis-Key
        
        Returns:
            Dict mit success, output, logs, error
        """
        return self.execute_command("TTL", [key])
    
    def expire(self, key: str, ttl: int) -> Dict[str, Any]:
        """
        TTL für einen Key setzen
        
        Args:
            key: Redis-Key
            ttl: Time-to-Live in Sekunden
        
        Returns:
            Dict mit success, output, logs, error
        """
        return self.execute_command("EXPIRE", [key, str(ttl)])
    
    def hget(self, key: str, field: str) -> Dict[str, Any]:
        """
        Hash-Feld abrufen
        
        Args:
            key: Redis-Key
            field: Hash-Feld
        
        Returns:
            Dict mit success, output, logs, error
        """
        return self.execute_command("HGET", [key, field])
    
    def hset(self, key: str, field: str, value: str) -> Dict[str, Any]:
        """
        Hash-Feld setzen
        
        Args:
            key: Redis-Key
            field: Hash-Feld
            value: Hash-Wert
        
        Returns:
            Dict mit success, output, logs, error
        """
        return self.execute_command("HSET", [key, field, value])
    
    def hgetall(self, key: str) -> Dict[str, Any]:
        """
        Alle Hash-Felder abrufen
        
        Args:
            key: Redis-Key
        
        Returns:
            Dict mit success, output, logs, error
        """
        return self.execute_command("HGETALL", [key])
    
    def hdel(self, key: str, field: str) -> Dict[str, Any]:
        """
        Hash-Feld löschen
        
        Args:
            key: Redis-Key
            field: Hash-Feld
        
        Returns:
            Dict mit success, output, logs, error
        """
        return self.execute_command("HDEL", [key, field])
    
    def lpush(self, key: str, value: str) -> Dict[str, Any]:
        """
        Wert an Liste vorne anhängen
        
        Args:
            key: Redis-Key
            value: Listen-Wert
        
        Returns:
            Dict mit success, output, logs, error
        """
        return self.execute_command("LPUSH", [key, value])
    
    def rpush(self, key: str, value: str) -> Dict[str, Any]:
        """
        Wert an Liste hinten anhängen
        
        Args:
            key: Redis-Key
            value: Listen-Wert
        
        Returns:
            Dict mit success, output, logs, error
        """
        return self.execute_command("RPUSH", [key, value])
    
    def lpop(self, key: str) -> Dict[str, Any]:
        """
        Wert von Liste vorne entfernen
        
        Args:
            key: Redis-Key
        
        Returns:
            Dict mit success, output, logs, error
        """
        return self.execute_command("LPOP", [key])
    
    def rpop(self, key: str) -> Dict[str, Any]:
        """
        Wert von Liste hinten entfernen
        
        Args:
            key: Redis-Key
        
        Returns:
            Dict mit success, output, logs, error
        """
        return self.execute_command("RPOP", [key])
    
    def lrange(self, key: str, start: int = 0, stop: int = -1) -> Dict[str, Any]:
        """
        Listen-Bereich abrufen
        
        Args:
            key: Redis-Key
            start: Start-Index
            stop: End-Index
        
        Returns:
            Dict mit success, output, logs, error
        """
        return self.execute_command("LRANGE", [key, str(start), str(stop)])
    
    def llen(self, key: str) -> Dict[str, Any]:
        """
        Listen-Länge abrufen
        
        Args:
            key: Redis-Key
        
        Returns:
            Dict mit success, output, logs, error
        """
        return self.execute_command("LLEN", [key])
    
    def sadd(self, key: str, member: str) -> Dict[str, Any]:
        """
        Mitglied zu Set hinzufügen
        
        Args:
            key: Redis-Key
            member: Set-Mitglied
        
        Returns:
            Dict mit success, output, logs, error
        """
        return self.execute_command("SADD", [key, member])
    
    def srem(self, key: str, member: str) -> Dict[str, Any]:
        """
        Mitglied aus Set entfernen
        
        Args:
            key: Redis-Key
            member: Set-Mitglied
        
        Returns:
            Dict mit success, output, logs, error
        """
        return self.execute_command("SREM", [key, member])
    
    def smembers(self, key: str) -> Dict[str, Any]:
        """
        Alle Set-Mitglieder abrufen
        
        Args:
            key: Redis-Key
        
        Returns:
            Dict mit success, output, logs, error
        """
        return self.execute_command("SMEMBERS", [key])
    
    def scard(self, key: str) -> Dict[str, Any]:
        """
        Set-Größe abrufen
        
        Args:
            key: Redis-Key
        
        Returns:
            Dict mit success, output, logs, error
        """
        return self.execute_command("SCARD", [key])
    
    def zadd(self, key: str, score: float, member: str) -> Dict[str, Any]:
        """
        Mitglied zu Sorted Set hinzufügen
        
        Args:
            key: Redis-Key
            score: Score
            member: Set-Mitglied
        
        Returns:
            Dict mit success, output, logs, error
        """
        return self.execute_command("ZADD", [key, str(score), member])
    
    def zrem(self, key: str, member: str) -> Dict[str, Any]:
        """
        Mitglied aus Sorted Set entfernen
        
        Args:
            key: Redis-Key
            member: Set-Mitglied
        
        Returns:
            Dict mit success, output, logs, error
        """
        return self.execute_command("ZREM", [key, member])
    
    def zrange(self, key: str, start: int = 0, stop: int = -1) -> Dict[str, Any]:
        """
        Sorted Set-Bereich abrufen
        
        Args:
            key: Redis-Key
            start: Start-Index
            stop: End-Index
        
        Returns:
            Dict mit success, output, logs, error
        """
        return self.execute_command("ZRANGE", [key, str(start), str(stop)])
    
    def zcard(self, key: str) -> Dict[str, Any]:
        """
        Sorted Set-Größe abrufen
        
        Args:
            key: Redis-Key
        
        Returns:
            Dict mit success, output, logs, error
        """
        return self.execute_command("ZCARD", [key])
    
    def dbsize(self) -> Dict[str, Any]:
        """
        Datenbankgröße abrufen
        
        Returns:
            Dict mit success, output, logs, error
        """
        return self.execute_command("DBSIZE")
    
    def flushdb(self) -> Dict[str, Any]:
        """
        Datenbank leeren
        
        Returns:
            Dict mit success, output, logs, error
        """
        return self.execute_command("FLUSHDB")
    
    def info(self, section: str = None) -> Dict[str, Any]:
        """
        Redis-Info abrufen
        
        Args:
            section: Info-Sektion (z.B. "server", "memory", "stats")
        
        Returns:
            Dict mit success, output, logs, error
        """
        if section:
            return self.execute_command("INFO", [section])
        return self.execute_command("INFO")
    
    def monitor(self, duration: int = 10) -> Dict[str, Any]:
        """
        Redis-Monitoring starten
        
        Args:
            duration: Dauer in Sekunden
        
        Returns:
            Dict mit success, output, logs, error
        """
        try:
            # Redis-Monitor-Befehl ausführen
            redis_cmd = ["redis-cli", "-h", self.redis_host, "-p", str(self.redis_port), "MONITOR"]
            
            logger.info(f"Redis-Monitoring starten für {duration} Sekunden")
            process = subprocess.Popen(
                redis_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(self.base_dir)
            )
            
            # Prozess nach duration Sekunden beenden
            import time
            time.sleep(duration)
            process.terminate()
            
            stdout, stderr = process.communicate()
            
            # Logs speichern
            logs = self._save_logs("MONITOR", [], stdout, stderr)
            
            return {
                "success": True,
                "output": stdout,
                "logs": logs
            }
        except Exception as e:
            logger.error(f"Fehler beim Redis-Monitoring: {e}")
            return {
                "success": False,
                "error": str(e),
                "logs": ""
            }
