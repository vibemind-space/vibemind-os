"""
PostgresAgent - Spezialisiert für PostgreSQL-Operationen

Dieser Agent ist verantwortlich für:
- PostgreSQL-Verbindungen verwalten
- SQL-Abfragen ausführen
- Tabellen erstellen/löschen
- Daten einfügen/aktualisieren/löschen
- Schema-Management
- PostgreSQL-Debugging
"""

import json
import logging
from typing import Any, Dict, List, Optional, Union
from datetime import datetime
from enum import Enum

try:
    import psycopg2
    from psycopg2 import sql, extras
    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False

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
    OTHER = "other"


class PostgresAgent:
    """Agent für PostgreSQL-Operationen"""
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "postgres",
        user: str = "postgres",
        password: str = "",
        autocommit: bool = False
    ):
        if not POSTGRES_AVAILABLE:
            raise ImportError(
                "psycopg2-Paket ist nicht installiert. "
                "Installiere es mit: pip install psycopg2-binary"
            )
        
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.autocommit = autocommit
        
        self.connection = None
        self.connected = False
        
        self.stats = {
            "queries_executed": 0,
            "rows_affected": 0,
            "queries": []
        }
        
        self._connect()
        logger.info(
            f"PostgresAgent initialisiert mit host: {host}, "
            f"port: {port}, database: {database}"
        )
    
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
            
            self.connection.autocommit = self.autocommit
            self.connected = True
            logger.info(
                f"Erfolgreich mit PostgreSQL verbunden: "
                f"{self.host}:{self.port}/{self.database}"
            )
        except Exception as e:
            logger.error(f"Fehler beim Verbinden mit PostgreSQL: {e}")
            self.connected = False
    
    def _log_operation(
        self,
        query_type: str,
        query: str,
        details: Optional[Dict[str, Any]] = None
    ):
        """Protokolliert eine Operation"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "query_type": query_type,
            "query": query,
            "details": details or {}
        }
        
        self.stats["queries"].append(log_entry)
        logger.info(f"{query_type}: {query[:100]}...")
    
    def _get_cursor(self):
        """Gibt einen Cursor zurück"""
        if not self.connected:
            raise Exception("Nicht mit PostgreSQL verbunden")
        
        return self.connection.cursor()
    
    def execute_query(
        self,
        query: str,
        params: Optional[tuple] = None,
        fetch: bool = True
    ) -> Dict[str, Any]:
        """Führt eine SQL-Abfrage aus"""
        try:
            if not self.connected:
                return {
                    "status": "error",
                    "error": "Nicht mit PostgreSQL verbunden"
                }
            
            cursor = self._get_cursor()
            
            # Query-Typ bestimmen
            query_upper = query.strip().upper()
            if query_upper.startswith("SELECT"):
                query_type = QueryType.SELECT
            elif query_upper.startswith("INSERT"):
                query_type = QueryType.INSERT
            elif query_upper.startswith("UPDATE"):
                query_type = QueryType.UPDATE
            elif query_upper.startswith("DELETE"):
                query_type = QueryType.DELETE
            elif query_upper.startswith("CREATE"):
                query_type = QueryType.CREATE
            elif query_upper.startswith("DROP"):
                query_type = QueryType.DROP
            elif query_upper.startswith("ALTER"):
                query_type = QueryType.ALTER
            else:
                query_type = QueryType.OTHER
            
            # Query ausführen
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            # Ergebnisse abrufen
            result = None
            rows_affected = 0
            
            if fetch and query_type == QueryType.SELECT:
                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()
                result = {
                    "columns": columns,
                    "rows": rows,
                    "row_count": len(rows)
                }
            else:
                rows_affected = cursor.rowcount
            
            self.stats["queries_executed"] += 1
            self.stats["rows_affected"] += rows_affected
            
            self._log_operation(
                query_type.value,
                query,
                {"params": params, "rows_affected": rows_affected}
            )
            
            cursor.close()
            
            return {
                "status": "success",
                "query_type": query_type.value,
                "result": result,
                "rows_affected": rows_affected
            }
        except Exception as e:
            logger.error(f"Fehler beim Ausführen der Query: {e}")
            return {
                "status": "error",
                "query": query,
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
        """Führt eine SELECT-Abfrage aus"""
        try:
            query = f"SELECT {columns} FROM {table}"
            
            if where:
                query += f" WHERE {where}"
            
            if limit:
                query += f" LIMIT {limit}"
            
            return self.execute_query(query, params, fetch=True)
        except Exception as e:
            logger.error(f"Fehler bei SELECT: {e}")
            return {
                "status": "error",
                "table": table,
                "error": str(e)
            }
    
    def insert(
        self,
        table: str,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Fügt Daten in eine Tabelle ein"""
        try:
            columns = list(data.keys())
            values = list(data.values())
            placeholders = ["%s"] * len(values)
            
            query = f"""
                INSERT INTO {table} ({', '.join(columns)})
                VALUES ({', '.join(placeholders)})
            """
            
            return self.execute_query(query, tuple(values), fetch=False)
        except Exception as e:
            logger.error(f"Fehler bei INSERT: {e}")
            return {
                "status": "error",
                "table": table,
                "error": str(e)
            }
    
    def update(
        self,
        table: str,
        data: Dict[str, Any],
        where: str,
        params: Optional[tuple] = None
    ) -> Dict[str, Any]:
        """Aktualisiert Daten in einer Tabelle"""
        try:
            set_clause = ", ".join([f"{k} = %s" for k in data.keys()])
            values = list(data.values())
            
            if params:
                values.extend(params)
            
            query = f"""
                UPDATE {table}
                SET {set_clause}
                WHERE {where}
            """
            
            return self.execute_query(query, tuple(values), fetch=False)
        except Exception as e:
            logger.error(f"Fehler bei UPDATE: {e}")
            return {
                "status": "error",
                "table": table,
                "error": str(e)
            }
    
    def delete(
        self,
        table: str,
        where: str,
        params: Optional[tuple] = None
    ) -> Dict[str, Any]:
        """Löscht Daten aus einer Tabelle"""
        try:
            query = f"DELETE FROM {table} WHERE {where}"
            
            return self.execute_query(query, params, fetch=False)
        except Exception as e:
            logger.error(f"Fehler bei DELETE: {e}")
            return {
                "status": "error",
                "table": table,
                "error": str(e)
            }
    
    def create_table(
        self,
        table_name: str,
        columns: Dict[str, str]
    ) -> Dict[str, Any]:
        """Erstellt eine Tabelle"""
        try:
            column_defs = ", ".join([f"{name} {definition}" for name, definition in columns.items()])
            
            query = f"CREATE TABLE {table_name} ({column_defs})"
            
            return self.execute_query(query, fetch=False)
        except Exception as e:
            logger.error(f"Fehler beim Erstellen der Tabelle: {e}")
            return {
                "status": "error",
                "table": table_name,
                "error": str(e)
            }
    
    def drop_table(self, table_name: str) -> Dict[str, Any]:
        """Löscht eine Tabelle"""
        try:
            query = f"DROP TABLE IF EXISTS {table_name}"
            
            return self.execute_query(query, fetch=False)
        except Exception as e:
            logger.error(f"Fehler beim Löschen der Tabelle: {e}")
            return {
                "status": "error",
                "table": table_name,
                "error": str(e)
            }
    
    def list_tables(self) -> Dict[str, Any]:
        """Listet alle Tabellen auf"""
        try:
            query = """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
            """
            
            return self.execute_query(query, fetch=True)
        except Exception as e:
            logger.error(f"Fehler beim Auflisten der Tabellen: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def describe_table(self, table_name: str) -> Dict[str, Any]:
        """Beschreibt eine Tabelle"""
        try:
            query = """
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name = %s
                ORDER BY ordinal_position
            """
            
            return self.execute_query(query, (table_name,), fetch=True)
        except Exception as e:
            logger.error(f"Fehler beim Beschreiben der Tabelle: {e}")
            return {
                "status": "error",
                "table": table_name,
                "error": str(e)
            }
    
    def get_table_count(self, table_name: str) -> Dict[str, Any]:
        """Gibt die Anzahl der Zeilen in einer Tabelle zurück"""
        try:
            query = f"SELECT COUNT(*) as count FROM {table_name}"
            
            return self.execute_query(query, fetch=True)
        except Exception as e:
            logger.error(f"Fehler beim Zählen der Zeilen: {e}")
            return {
                "status": "error",
                "table": table_name,
                "error": str(e)
            }
    
    def get_database_info(self) -> Dict[str, Any]:
        """Gibt Informationen über die Datenbank zurück"""
        try:
            query = """
                SELECT 
                    current_database() as database,
                    current_user as user,
                    version() as version
            """
            
            return self.execute_query(query, fetch=True)
        except Exception as e:
            logger.error(f"Fehler beim Abrufen der Datenbank-Info: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def get_table_sizes(self) -> Dict[str, Any]:
        """Gibt die Größe aller Tabellen zurück"""
        try:
            query = """
                SELECT 
                    schemaname,
                    tablename,
                    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
                FROM pg_tables
                WHERE schemaname = 'public'
                ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
            """
            
            return self.execute_query(query, fetch=True)
        except Exception as e:
            logger.error(f"Fehler beim Abrufen der Tabellengrößen: {e}")
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
    
    def get_queries_log(
        self,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """Gibt das Queries-Log zurück"""
        queries = self.stats["queries"]
        
        if limit:
            queries = queries[-limit:]
        
        return {
            "status": "success",
            "queries": queries
        }
    
    def health_check(self) -> bool:
        """Health Check"""
        try:
            if not self.connected:
                return False
            
            cursor = self._get_cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            return True
        except Exception:
            return False
    
    def commit(self):
        """Commit der Transaktion"""
        if self.connection:
            self.connection.commit()
            logger.info("Transaktion committed")
    
    def rollback(self):
        """Rollback der Transaktion"""
        if self.connection:
            self.connection.rollback()
            logger.info("Transaktion rollback")
    
    def close(self):
        """Schließt die Verbindung"""
        if self.connection:
            self.connection.close()
            self.connected = False
            logger.info("PostgreSQL-Verbindung geschlossen")


def main():
    """Test-Implementierung"""
    try:
        agent = PostgresAgent(
            host="localhost",
            port=5432,
            database="testdb",
            user="postgres",
            password="password"
        )
        
        # Health Check
        print(f"Health Check: {agent.health_check()}")
        
        # Database Info
        result = agent.get_database_info()
        print(f"Database Info: {result}")
        
        # List Tables
        result = agent.list_tables()
        print(f"Tables: {result}")
        
        # Create Table
        result = agent.create_table(
            "test_table",
            {
                "id": "SERIAL PRIMARY KEY",
                "name": "VARCHAR(255)",
                "value": "INTEGER",
                "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            }
        )
        print(f"Create Table: {result}")
        
        # Insert
        result = agent.insert(
            "test_table",
            {"name": "Test", "value": 42}
        )
        print(f"Insert: {result}")
        
        # Select
        result = agent.select("test_table")
        print(f"Select: {result}")
        
        # Describe Table
        result = agent.describe_table("test_table")
        print(f"Describe Table: {result}")
        
        # Stats
        stats = agent.get_stats()
        print(f"Stats: {stats}")
        
        # Cleanup
        agent.drop_table("test_table")
        agent.close()
    except Exception as e:
        print(f"PostgreSQL ist nicht verfügbar: {e}")


if __name__ == "__main__":
    main()
