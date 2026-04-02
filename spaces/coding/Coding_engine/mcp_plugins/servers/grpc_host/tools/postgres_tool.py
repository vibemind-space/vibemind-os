"""
Postgres Tool für EventFixTeam
Bietet Funktionen zur Interaktion mit PostgreSQL für Debugging und Testing
"""

import os
import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


class PostgresTool:
    """Tool für PostgreSQL-Operationen"""
    
    def __init__(self, base_dir: str = ".", db_host: str = "localhost", db_port: int = 5432, 
                 db_name: str = "postgres", db_user: str = "postgres", db_password: str = ""):
        """
        Postgres Tool initialisieren
        
        Args:
            base_dir: Basisverzeichnis für das Projekt
            db_host: PostgreSQL-Host
            db_port: PostgreSQL-Port
            db_name: Datenbankname
            db_user: Datenbankbenutzer
            db_password: Datenbankpasswort
        """
        self.base_dir = Path(base_dir)
        self.postgres_dir = self.base_dir / "postgres"
        self.postgres_dir.mkdir(exist_ok=True)
        self.db_host = db_host
        self.db_port = db_port
        self.db_name = db_name
        self.db_user = db_user
        self.db_password = db_password
        
        logger.info(f"Postgres Tool initialisiert mit Host: {db_host}:{db_port}, DB: {db_name}")
    
    def execute_query(self, query: str, params: List[Any] = None) -> Dict[str, Any]:
        """
        SQL-Query ausführen
        
        Args:
            query: SQL-Query
            params: Parameter für die Query
        
        Returns:
            Dict mit success, output, logs, error
        """
        try:
            params = params or []
            
            # PGPASSWORD setzen
            env = os.environ.copy()
            if self.db_password:
                env["PGPASSWORD"] = self.db_password
            
            # psql-Befehl zusammenstellen
            psql_cmd = [
                "psql",
                "-h", self.db_host,
                "-p", str(self.db_port),
                "-U", self.db_user,
                "-d", self.db_name,
                "-c", query
            ]
            
            # Befehl ausführen
            logger.info(f"Postgres-Query ausführen: {query}")
            result = subprocess.run(
                psql_cmd,
                capture_output=True,
                text=True,
                env=env,
                cwd=str(self.base_dir)
            )
            
            # Logs speichern
            logs = self._save_logs(query, result.stdout, result.stderr)
            
            if result.returncode != 0:
                logger.error(f"Postgres-Query fehlgeschlagen: {result.stderr}")
                return {
                    "success": False,
                    "error": result.stderr,
                    "logs": logs
                }
            
            # Output parsen
            output = self._parse_output(result.stdout)
            
            return {
                "success": True,
                "output": output,
                "logs": logs
            }
        except Exception as e:
            logger.error(f"Fehler beim Ausführen der Postgres-Query: {e}")
            return {
                "success": False,
                "error": str(e),
                "logs": ""
            }
    
    def _parse_output(self, output: str) -> Any:
        """
        Postgres-Output parsen
        
        Args:
            output: Output des psql-Befehls
        
        Returns:
            Geparster Output
        """
        try:
            lines = output.strip().split('\n')
            
            # Prüfen, ob es sich um eine SELECT-Query handelt
            if len(lines) > 2 and '|' in lines[0]:
                # Tabellarisches Format parsen
                headers = [h.strip() for h in lines[0].split('|')]
                separator_line = lines[1]
                
                # Datenzeilen parsen
                data = []
                for line in lines[2:]:
                    if line.strip() and not line.startswith('-'):
                        values = [v.strip() for v in line.split('|')]
                        if len(values) == len(headers):
                            row = dict(zip(headers, values))
                            data.append(row)
                
                return data
            else:
                # Text-Output zurückgeben
                return output.strip()
        except Exception as e:
            logger.error(f"Fehler beim Parsen des Postgres-Outputs: {e}")
            return output.strip()
    
    def _save_logs(self, query: str, stdout: str, stderr: str) -> str:
        """
        Postgres-Logs speichern
        
        Args:
            query: SQL-Query
            stdout: Standard Output
            stderr: Standard Error
        
        Returns:
            Pfad zur Log-Datei
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_file = self.postgres_dir / f"postgres_{timestamp}.log"
            
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write(f"Query: {query}\n")
                f.write(f"Host: {self.db_host}:{self.db_port}\n")
                f.write(f"Database: {self.db_name}\n")
                f.write(f"User: {self.db_user}\n")
                f.write(f"Timestamp: {timestamp}\n")
                f.write("=" * 80 + "\n\n")
                f.write("STDOUT:\n")
                f.write(stdout)
                f.write("\n\n")
                f.write("STDERR:\n")
                f.write(stderr)
            
            logger.info(f"Postgres-Logs gespeichert: {log_file}")
            return str(log_file)
        except Exception as e:
            logger.error(f"Fehler beim Speichern der Postgres-Logs: {e}")
            return ""
    
    def select(self, table: str, columns: str = "*", where: str = None, limit: int = None) -> Dict[str, Any]:
        """
        SELECT-Query ausführen
        
        Args:
            table: Tabellenname
            columns: Spalten (default: "*")
            where: WHERE-Bedingung
            limit: LIMIT-Wert
        
        Returns:
            Dict mit success, output, logs, error
        """
        query = f"SELECT {columns} FROM {table}"
        if where:
            query += f" WHERE {where}"
        if limit:
            query += f" LIMIT {limit}"
        query += ";"
        return self.execute_query(query)
    
    def insert(self, table: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        INSERT-Query ausführen
        
        Args:
            table: Tabellenname
            data: Daten als Dict (Spalte: Wert)
        
        Returns:
            Dict mit success, output, logs, error
        """
        columns = ', '.join(data.keys())
        values = ', '.join([f"'{v}'" if isinstance(v, str) else str(v) for v in data.values()])
        query = f"INSERT INTO {table} ({columns}) VALUES ({values});"
        return self.execute_query(query)
    
    def update(self, table: str, data: Dict[str, Any], where: str) -> Dict[str, Any]:
        """
        UPDATE-Query ausführen
        
        Args:
            table: Tabellenname
            data: Daten als Dict (Spalte: Wert)
            where: WHERE-Bedingung
        
        Returns:
            Dict mit success, output, logs, error
        """
        set_clause = ', '.join([f"{k} = '{v}'" if isinstance(v, str) else f"{k} = {v}" for k, v in data.items()])
        query = f"UPDATE {table} SET {set_clause} WHERE {where};"
        return self.execute_query(query)
    
    def delete(self, table: str, where: str) -> Dict[str, Any]:
        """
        DELETE-Query ausführen
        
        Args:
            table: Tabellenname
            where: WHERE-Bedingung
        
        Returns:
            Dict mit success, output, logs, error
        """
        query = f"DELETE FROM {table} WHERE {where};"
        return self.execute_query(query)
    
    def create_table(self, table: str, columns: Dict[str, str]) -> Dict[str, Any]:
        """
        Tabelle erstellen
        
        Args:
            table: Tabellenname
            columns: Spalten als Dict (Name: Typ)
        
        Returns:
            Dict mit success, output, logs, error
        """
        columns_def = ', '.join([f"{name} {type_def}" for name, type_def in columns.items()])
        query = f"CREATE TABLE IF NOT EXISTS {table} ({columns_def});"
        return self.execute_query(query)
    
    def drop_table(self, table: str) -> Dict[str, Any]:
        """
        Tabelle löschen
        
        Args:
            table: Tabellenname
        
        Returns:
            Dict mit success, output, logs, error
        """
        query = f"DROP TABLE IF EXISTS {table};"
        return self.execute_query(query)
    
    def truncate_table(self, table: str) -> Dict[str, Any]:
        """
        Tabelle leeren
        
        Args:
            table: Tabellenname
        
        Returns:
            Dict mit success, output, logs, error
        """
        query = f"TRUNCATE TABLE {table};"
        return self.execute_query(query)
    
    def list_tables(self) -> Dict[str, Any]:
        """
        Alle Tabellen auflisten
        
        Returns:
            Dict mit success, output, logs, error
        """
        query = "SELECT tablename FROM pg_tables WHERE schemaname = 'public';"
        return self.execute_query(query)
    
    def describe_table(self, table: str) -> Dict[str, Any]:
        """
        Tabellenstruktur beschreiben
        
        Args:
            table: Tabellenname
        
        Returns:
            Dict mit success, output, logs, error
        """
        query = f"""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = '{table}'
            ORDER BY ordinal_position;
        """
        return self.execute_query(query)
    
    def count(self, table: str, where: str = None) -> Dict[str, Any]:
        """
        Zeilen zählen
        
        Args:
            table: Tabellenname
            where: WHERE-Bedingung
        
        Returns:
            Dict mit success, output, logs, error
        """
        query = f"SELECT COUNT(*) as count FROM {table}"
        if where:
            query += f" WHERE {where}"
        query += ";"
        return self.execute_query(query)
    
    def execute_script(self, script_path: str) -> Dict[str, Any]:
        """
        SQL-Skript ausführen
        
        Args:
            script_path: Pfad zum SQL-Skript
        
        Returns:
            Dict mit success, output, logs, error
        """
        try:
            # PGPASSWORD setzen
            env = os.environ.copy()
            if self.db_password:
                env["PGPASSWORD"] = self.db_password
            
            # psql-Befehl zusammenstellen
            psql_cmd = [
                "psql",
                "-h", self.db_host,
                "-p", str(self.db_port),
                "-U", self.db_user,
                "-d", self.db_name,
                "-f", script_path
            ]
            
            # Befehl ausführen
            logger.info(f"Postgres-Skript ausführen: {script_path}")
            result = subprocess.run(
                psql_cmd,
                capture_output=True,
                text=True,
                env=env,
                cwd=str(self.base_dir)
            )
            
            # Logs speichern
            logs = self._save_logs(f"Script: {script_path}", result.stdout, result.stderr)
            
            if result.returncode != 0:
                logger.error(f"Postgres-Skript fehlgeschlagen: {result.stderr}")
                return {
                    "success": False,
                    "error": result.stderr,
                    "logs": logs
                }
            
            return {
                "success": True,
                "output": result.stdout,
                "logs": logs
            }
        except Exception as e:
            logger.error(f"Fehler beim Ausführen des Postgres-Skripts: {e}")
            return {
                "success": False,
                "error": str(e),
                "logs": ""
            }
    
    def backup(self, backup_path: str) -> Dict[str, Any]:
        """
        Datenbank-Backup erstellen
        
        Args:
            backup_path: Pfad für das Backup
        
        Returns:
            Dict mit success, output, logs, error
        """
        try:
            # PGPASSWORD setzen
            env = os.environ.copy()
            if self.db_password:
                env["PGPASSWORD"] = self.db_password
            
            # pg_dump-Befehl zusammenstellen
            pg_dump_cmd = [
                "pg_dump",
                "-h", self.db_host,
                "-p", str(self.db_port),
                "-U", self.db_user,
                "-d", self.db_name,
                "-f", backup_path
            ]
            
            # Befehl ausführen
            logger.info(f"Postgres-Backup erstellen: {backup_path}")
            result = subprocess.run(
                pg_dump_cmd,
                capture_output=True,
                text=True,
                env=env,
                cwd=str(self.base_dir)
            )
            
            # Logs speichern
            logs = self._save_logs(f"Backup: {backup_path}", result.stdout, result.stderr)
            
            if result.returncode != 0:
                logger.error(f"Postgres-Backup fehlgeschlagen: {result.stderr}")
                return {
                    "success": False,
                    "error": result.stderr,
                    "logs": logs
                }
            
            return {
                "success": True,
                "output": f"Backup erstellt: {backup_path}",
                "logs": logs
            }
        except Exception as e:
            logger.error(f"Fehler beim Erstellen des Postgres-Backups: {e}")
            return {
                "success": False,
                "error": str(e),
                "logs": ""
            }
    
    def restore(self, backup_path: str) -> Dict[str, Any]:
        """
        Datenbank aus Backup wiederherstellen
        
        Args:
            backup_path: Pfad zum Backup
        
        Returns:
            Dict mit success, output, logs, error
        """
        try:
            # PGPASSWORD setzen
            env = os.environ.copy()
            if self.db_password:
                env["PGPASSWORD"] = self.db_password
            
            # psql-Befehl zusammenstellen
            psql_cmd = [
                "psql",
                "-h", self.db_host,
                "-p", str(self.db_port),
                "-U", self.db_user,
                "-d", self.db_name,
                "-f", backup_path
            ]
            
            # Befehl ausführen
            logger.info(f"Postgres-Wiederherstellung: {backup_path}")
            result = subprocess.run(
                psql_cmd,
                capture_output=True,
                text=True,
                env=env,
                cwd=str(self.base_dir)
            )
            
            # Logs speichern
            logs = self._save_logs(f"Restore: {backup_path}", result.stdout, result.stderr)
            
            if result.returncode != 0:
                logger.error(f"Postgres-Wiederherstellung fehlgeschlagen: {result.stderr}")
                return {
                    "success": False,
                    "error": result.stderr,
                    "logs": logs
                }
            
            return {
                "success": True,
                "output": f"Wiederherstellung abgeschlossen: {backup_path}",
                "logs": logs
            }
        except Exception as e:
            logger.error(f"Fehler bei der Postgres-Wiederherstellung: {e}")
            return {
                "success": False,
                "error": str(e),
                "logs": ""
            }
