"""
PostgreSQLAgent - Spezialisiert für PostgreSQL-Operationen

Dieser Agent ist verantwortlich für:
- PostgreSQL-Verbindungen verwalten
- SQL-Abfragen ausführen
- Datenbank-Schema verwalten
- Transaktionen verwalten
- Backup und Restore
"""

import json
import logging
from typing import Any, Dict, List, Optional, Union
from datetime import datetime
from enum import Enum

try:
    import psycopg2
    from psycopg2 import sql, extras
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False

# Logging konfigurieren
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class QueryType(Enum):
    """Abfragetypen"""
    SELECT = "select"
    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"
    CREATE = "create"
    DROP = "drop"
    ALTER = "alter"
    TRUNCATE = "truncate"


class PostgreSQLAgent:
    """Agent für PostgreSQL-Operationen"""
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "postgres",
        user: str = "postgres",
        password: str = ""
    ):
        """
        Initialisiert den PostgreSQLAgent
        
        Args:
            host: PostgreSQL-Host
            port: PostgreSQL-Port
            database: Datenbankname
            user: Benutzername
            password: Passwort
        """
        if not PSYCOPG2_AVAILABLE:
            raise ImportError(
                "psycopg2-Paket ist nicht installiert. "
                "Installieren Sie es mit: pip install psycopg2-binary"
            )
        
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        
        self.connection = None
        self.connected = False
        
        self.stats = {
            "queries": 0,
            "rows_affected": 0,
            "errors": 0,
            "operations": []
        }
        
        self._connect()
        logger.info("PostgreSQLAgent initialisiert")
    
    def _connect(self):
        """Verbindet sich mit PostgreSQL"""
        try:
            self.connection = psycopg2.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password
            )
            
            self.connection.autocommit = False
            self.connected = True
            logger.info(
                f"Verbunden mit PostgreSQL: {self.host}:{self.port}/{self.database}"
            )
        except Exception as e:
            logger.error(f"Fehler beim Verbinden mit PostgreSQL: {e}")
            self.connected = False
    
    def _log_operation(
        self,
        query_type: str,
        details: Optional[Dict[str, Any]] = None
    ):
        """Protokolliert eine Operation"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "query_type": query_type,
            "details": details or {}
        }
        
        self.stats["operations"].append(log_entry)
        logger.info(f"{query_type}: {details}")
    
    def execute_query(
        self,
        query: str,
        params: Optional[tuple] = None,
        fetch: bool = True
    ) -> Dict[str, Any]:
        """
        Führt eine SQL-Abfrage aus
        
        Args:
            query: SQL-Abfrage
            params: Parameter für die Abfrage
            fetch: Ob Ergebnisse abgerufen werden sollen
            
        Returns:
            Dict mit Status und Ergebnissen
        """
        try:
            if not self.connected:
                return {
                    "status": "error",
                    "error": "Nicht mit PostgreSQL verbunden"
                }
            
            cursor = self.connection.cursor()
            
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            self.stats["queries"] += 1
            
            # Query-Typ bestimmen
            query_upper = query.strip().upper()
            if query_upper.startswith("SELECT"):
                query_type = QueryType.SELECT.value
            elif query_upper.startswith("INSERT"):
                query_type = QueryType.INSERT.value
            elif query_upper.startswith("UPDATE"):
                query_type = QueryType.UPDATE.value
            elif query_upper.startswith("DELETE"):
                query_type = QueryType.DELETE.value
            elif query_upper.startswith("CREATE"):
                query_type = QueryType.CREATE.value
            elif query_upper.startswith("DROP"):
                query_type = QueryType.DROP.value
            elif query_upper.startswith("ALTER"):
                query_type = QueryType.ALTER.value
            elif query_upper.startswith("TRUNCATE"):
                query_type = QueryType.TRUNCATE.value
            else:
                query_type = "unknown"
            
            # Ergebnisse abrufen
            result = None
            if fetch and query_type == QueryType.SELECT.value:
                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()
                result = {
                    "columns": columns,
                    "rows": rows,
                    "row_count": len(rows)
                }
            else:
                rows_affected = cursor.rowcount
                self.stats["rows_affected"] += rows_affected
                result = {
                    "rows_affected": rows_affected
                }
            
            self.connection.commit()
            cursor.close()
            
            self._log_operation(
                query_type,
                {"query": query[:100], "params": params}
            )
            
            return {
                "status": "success",
                "query_type": query_type,
                "result": result
            }
        except Exception as e:
            self.connection.rollback()
            self.stats["errors"] += 1
            logger.error(f"Fehler beim Ausführen der Abfrage: {e}")
            return {
                "status": "error",
                "query": query[:100],
                "error": str(e)
            }
    
    def select(
        self,
        table: str,
        columns: str = "*",
        where: Optional[str] = None,
        params: Optional[tuple] = None,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Führt eine SELECT-Abfrage aus
        
        Args:
            table: Tabellenname
            columns: Spalten (default: *)
            where: WHERE-Klausel
            params: Parameter für WHERE-Klausel
            limit: LIMIT-Wert
            
        Returns:
            Dict mit Status und Ergebnissen
        """
        query = f"SELECT {columns} FROM {table}"
        
        if where:
            query += f" WHERE {where}"
        
        if limit:
            query += f" LIMIT {limit}"
        
        return self.execute_query(query, params)
    
    def insert(
        self,
        table: str,
        data: Dict[str, Any],
        returning: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Führt eine INSERT-Abfrage aus
        
        Args:
            table: Tabellenname
            data: Daten als Dict
            returning: RETURNING-Klausel
            
        Returns:
            Dict mit Status und Ergebnissen
        """
        columns = list(data.keys())
        values = list(data.values())
        placeholders = ["%s"] * len(values)
        
        query = f"INSERT INTO {table} ({', '.join(columns)}) "
        query += f"VALUES ({', '.join(placeholders)})"
        
        if returning:
            query += f" RETURNING {returning}"
        
        return self.execute_query(query, tuple(values))
    
    def update(
        self,
        table: str,
        data: Dict[str, Any],
        where: str,
        params: Optional[tuple] = None
    ) -> Dict[str, Any]:
        """
        Führt eine UPDATE-Abfrage aus
        
        Args:
            table: Tabellenname
            data: Daten als Dict
            where: WHERE-Klausel
            params: Parameter für WHERE-Klausel
            
        Returns:
            Dict mit Status und Ergebnissen
        """
        set_clause = ", ".join([f"{k} = %s" for k in data.keys()])
        values = list(data.values())
        
        if params:
            values.extend(params)
        
        query = f"UPDATE {table} SET {set_clause} WHERE {where}"
        
        return self.execute_query(query, tuple(values))
    
    def delete(
        self,
        table: str,
        where: str,
        params: Optional[tuple] = None
    ) -> Dict[str, Any]:
        """
        Führt eine DELETE-Abfrage aus
        
        Args:
            table: Tabellenname
            where: WHERE-Klausel
            params: Parameter für WHERE-Klausel
            
        Returns:
            Dict mit Status und Ergebnissen
        """
        query = f"DELETE FROM {table} WHERE {where}"
        
        return self.execute_query(query, params)
    
    def create_table(
        self,
        table: str,
        columns: Dict[str, str],
        primary_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Erstellt eine Tabelle
        
        Args:
            table: Tabellenname
            columns: Spalten als Dict {name: type}
            primary_key: Primärschlüssel
            
        Returns:
            Dict mit Status und Ergebnissen
        """
        column_defs = [f"{name} {type_}" for name, type_ in columns.items()]
        
        if primary_key:
            column_defs.append(f"PRIMARY KEY ({primary_key})")
        
        query = f"CREATE TABLE {table} ({', '.join(column_defs)})"
        
        return self.execute_query(query)
    
    def drop_table(self, table: str) -> Dict[str, Any]:
        """
        Löscht eine Tabelle
        
        Args:
            table: Tabellenname
            
        Returns:
            Dict mit Status und Ergebnissen
        """
        query = f"DROP TABLE IF EXISTS {table}"
        
        return self.execute_query(query)
    
    def truncate_table(self, table: str) -> Dict[str, Any]:
        """
        Leert eine Tabelle
        
        Args:
            table: Tabellenname
            
        Returns:
            Dict mit Status und Ergebnissen
        """
        query = f"TRUNCATE TABLE {table}"
        
        return self.execute_query(query)
    
    def list_tables(self) -> Dict[str, Any]:
        """
        Listet alle Tabellen auf
        
        Returns:
            Dict mit Status und Tabellenliste
        """
        query = """
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """
        
        return self.execute_query(query)
    
    def describe_table(self, table: str) -> Dict[str, Any]:
        """
        Beschreibt eine Tabelle
        
        Args:
            table: Tabellenname
            
        Returns:
            Dict mit Status und Tabellenstruktur
        """
        query = """
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = %s
            ORDER BY ordinal_position
        """
        
        return self.execute_query(query, (table,))
    
    def begin_transaction(self) -> Dict[str, Any]:
        """
        Startet eine Transaktion
        
        Returns:
            Dict mit Status
        """
        try:
            if not self.connected:
                return {
                    "status": "error",
                    "error": "Nicht mit PostgreSQL verbunden"
                }
            
            self.connection.autocommit = False
            
            self._log_operation("transaction", {"action": "begin"})
            
            return {
                "status": "success",
                "action": "begin"
            }
        except Exception as e:
            logger.error(f"Fehler beim Starten der Transaktion: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def commit_transaction(self) -> Dict[str, Any]:
        """
        Commitet eine Transaktion
        
        Returns:
            Dict mit Status
        """
        try:
            if not self.connected:
                return {
                    "status": "error",
                    "error": "Nicht mit PostgreSQL verbunden"
                }
            
            self.connection.commit()
            
            self._log_operation("transaction", {"action": "commit"})
            
            return {
                "status": "success",
                "action": "commit"
            }
        except Exception as e:
            logger.error(f"Fehler beim Commit: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def rollback_transaction(self) -> Dict[str, Any]:
        """
        Rollback einer Transaktion
        
        Returns:
            Dict mit Status
        """
        try:
            if not self.connected:
                return {
                    "status": "error",
                    "error": "Nicht mit PostgreSQL verbunden"
                }
            
            self.connection.rollback()
            
            self._log_operation("transaction", {"action": "rollback"})
            
            return {
                "status": "success",
                "action": "rollback"
            }
        except Exception as e:
            logger.error(f"Fehler beim Rollback: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def backup_database(
        self,
        output_file: str
    ) -> Dict[str, Any]:
        """
        Erstellt ein Backup der Datenbank
        
        Args:
            output_file: Ausgabedatei
            
        Returns:
            Dict mit Status
        """
        try:
            import subprocess
            
            command = [
                "pg_dump",
                f"--host={self.host}",
                f"--port={self.port}",
                f"--username={self.user}",
                f"--dbname={self.database}",
                f"--file={output_file}"
            ]
            
            env = {"PGPASSWORD": self.password}
            
            result = subprocess.run(
                command,
                env=env,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                self._log_operation(
                    "backup",
                    {"file": output_file}
                )
                
                return {
                    "status": "success",
                    "file": output_file
                }
            else:
                return {
                    "status": "error",
                    "error": result.stderr
                }
        except Exception as e:
            logger.error(f"Fehler beim Backup: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def restore_database(
        self,
        input_file: str
    ) -> Dict[str, Any]:
        """
        Stellt ein Backup wieder her
        
        Args:
            input_file: Eingabedatei
            
        Returns:
            Dict mit Status
        """
        try:
            import subprocess
            
            command = [
                "psql",
                f"--host={self.host}",
                f"--port={self.port}",
                f"--username={self.user}",
                f"--dbname={self.database}",
                f"--file={input_file}"
            ]
            
            env = {"PGPASSWORD": self.password}
            
            result = subprocess.run(
                command,
                env=env,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                self._log_operation(
                    "restore",
                    {"file": input_file}
                )
                
                return {
                    "status": "success",
                    "file": input_file
                }
            else:
                return {
                    "status": "error",
                    "error": result.stderr
                }
        except Exception as e:
            logger.error(f"Fehler beim Restore: {e}")
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
        try:
            if not self.connected:
                return False
            
            cursor = self.connection.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            return True
        except Exception:
            return False
    
    def close(self):
        """Schließt die Verbindung"""
        if self.connection:
            self.connection.close()
            self.connected = False
            logger.info("PostgreSQL-Verbindung geschlossen")


def main():
    """Test-Implementierung"""
    try:
        agent = PostgreSQLAgent()
        
        # Health Check
        print(f"Health Check: {agent.health_check()}")
        
        # Tabellen auflisten
        tables = agent.list_tables()
        print(f"Tables: {tables}")
        
        # Stats
        stats = agent.get_stats()
        print(f"Stats: {stats}")
        
        # Close
        agent.close()
    except Exception as e:
        print(f"Fehler: {e}")


if __name__ == "__main__":
    main()
