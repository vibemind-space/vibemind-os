"""
PostgresDebugTools - PostgreSQL-Tools für Debugging.

Verantwortlichkeiten:
- Langsame Queries identifizieren
- Tabellengrößen abrufen
- Verbindungs-Statistiken holen
- Schema-Informationen abrufen
"""

import asyncio
import json
import os
import sys
from typing import Optional, List, Dict, Any
import structlog

logger = structlog.get_logger(__name__)


class PostgresDebugTools:
    """
    PostgreSQL Debug Tools - Bietet Funktionen für PostgreSQL-Debugging.
    
    Verwendet PostgreSQL CLI für Datenbank-Analyse.
    """
    
    def __init__(self, database_url: str = "postgresql://postgres:postgres@localhost:5432/postgres"):
        self.database_url = database_url
        self.logger = logger.bind(component="postgres_debug_tools")
        
        # Connection-Parameter parsen
        self._parse_connection_params()
    
    def _parse_connection_params(self) -> None:
        """Parst die Connection-URL."""
        # Einfache URL-Parsung
        if "postgresql://" in self.database_url:
            # Format: postgresql://user:password@host:port/database
            url_without_prefix = self.database_url.replace("postgresql://", "")
            
            if "@" in url_without_prefix:
                auth_part, host_part = url_without_prefix.split("@")
                user, password = auth_part.split(":") if ":" in auth_part else (auth_part, "")
                
                if "/" in host_part:
                    host_port, database = host_part.split("/")
                    host_parts = host_port.split(":")
                    self.host = host_parts[0] if len(host_parts) > 1 else "localhost"
                    self.port = int(host_parts[1]) if len(host_parts) > 1 else 5432
                    self.database = database
                    self.user = user
                    self.password = password
                else:
                    self.host = "localhost"
                    self.port = 5432
                    self.database = url_without_prefix
                    self.user = "postgres"
                    self.password = ""
            else:
                self.host = "localhost"
                self.port = 5432
                self.database = url_without_prefix
                self.user = "postgres"
                self.password = ""
    
    async def get_slow_queries(
        self,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """
        Holt die langsamsten Queries.
        
        Args:
            limit: Maximale Anzahl von Queries
            
        Returns:
            Dict mit success, queries, metadata
        """
        self.logger.info(
            "getting_slow_queries",
            limit=limit,
        )
        
        try:
            # PostgreSQL query für langsame Queries
            query = """
                SELECT 
                    query,
                    calls,
                    total_time,
                    mean_time,
                    max_time,
                    rows
                FROM pg_stat_statements
                WHERE calls > 0
                ORDER BY mean_time DESC
                LIMIT $1;
            """
            
            # psql command
            cmd = [
                "psql",
                "-h", self.host,
                "-p", str(self.port),
                "-U", self.user,
                "-d", self.database,
                "-c", query,
                "-v", "ON_ERROR_STOP=1",
                "-t",
            ]
            
            if self.password:
                cmd.extend(["-W"])
                os.environ["PGPASSWORD"] = self.password
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                # Output parsen
                lines = stdout.decode('utf-8', errors='replace').strip().split('\n')
                queries = []
                
                for line in lines:
                    if line.strip() and not line.startswith("|") and not line.startswith("-"):
                        parts = [p.strip() for p in line.split("|")]
                        if len(parts) >= 5:
                            queries.append({
                                "query": parts[0][:200],  # Query limitieren
                                "calls": int(parts[1]) if parts[1].isdigit() else 0,
                                "total_time_ms": float(parts[2]) if parts[2].replace('.', '').isdigit() else 0.0,
                                "mean_time_ms": float(parts[3]) if parts[3].replace('.', '').isdigit() else 0.0,
                                "max_time_ms": float(parts[4]) if parts[4].replace('.', '').isdigit() else 0.0,
                                "rows": int(parts[5]) if parts[5].isdigit() else 0,
                            })
                
                return {
                    "success": True,
                    "queries": queries[:limit],
                    "count": len(queries[:limit]),
                }
            else:
                error = stderr.decode('utf-8', errors='replace')
                return {
                    "success": False,
                    "error": error,
                }
                
        except Exception as e:
            self.logger.error(
                "get_slow_queries_failed",
                error=str(e),
            )
            return {
                "success": False,
                "error": str(e),
            }
    
    async def get_table_sizes(
        self,
        schema: str = "public",
    ) -> Dict[str, Any]:
        """
        Holt Tabellengrößen.
        
        Args:
            schema: Schema-Name (default: "public")
            
        Returns:
            Dict mit success, tables, metadata
        """
        self.logger.info(
            "getting_table_sizes",
            schema=schema,
        )
        
        try:
            # PostgreSQL query für Tabellengrößen
            query = f"""
                SELECT 
                    schemaname,
                    tablename,
                    pg_size_pretty(pg_total_relation_size(schemaname::name, tablename::name)) as size,
                    pg_total_relation_size(schemaname::name, tablename::name) as size_bytes
                FROM pg_tables
                WHERE schemaname = '{schema}'
                ORDER BY pg_total_relation_size(schemaname::name, tablename::name) DESC;
            """
            
            # psql command
            cmd = [
                "psql",
                "-h", self.host,
                "-p", str(self.port),
                "-U", self.user,
                "-d", self.database,
                "-c", query,
                "-v", "ON_ERROR_STOP=1",
                "-t",
            ]
            
            if self.password:
                cmd.extend(["-W"])
                os.environ["PGPASSWORD"] = self.password
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                # Output parsen
                lines = stdout.decode('utf-8', errors='replace').strip().split('\n')
                tables = []
                
                for line in lines:
                    if line.strip() and not line.startswith("|") and not line.startswith("-"):
                        parts = [p.strip() for p in line.split("|")]
                        if len(parts) >= 4:
                            size_bytes = int(parts[3]) if parts[3].isdigit() else 0
                            
                            # Größe formatieren
                            if size_bytes > 1024 * 1024 * 1024:  # GB
                                size = f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
                            elif size_bytes > 1024 * 1024:  # MB
                                size = f"{size_bytes / (1024 * 1024):.2f} MB"
                            else:  # KB
                                size = f"{size_bytes / 1024:.2f} KB"
                            
                            tables.append({
                                "schema": parts[0],
                                "table": parts[1],
                                "size": size,
                                "size_bytes": size_bytes,
                            })
                
                return {
                    "success": True,
                    "tables": tables,
                    "count": len(tables),
                    "schema": schema,
                }
            else:
                error = stderr.decode('utf-8', errors='replace')
                return {
                    "success": False,
                    "error": error,
                }
                
        except Exception as e:
            self.logger.error(
                "get_table_sizes_failed",
                schema=schema,
                error=str(e),
            )
            return {
                "success": False,
                "error": str(e),
            }
    
    async def get_connection_stats(
        self,
    ) -> Dict[str, Any]:
        """
        Holt Verbindungs-Statistiken.
        
        Returns:
            Dict mit success, stats, metadata
        """
        self.logger.info("getting_connection_stats")
        
        try:
            # PostgreSQL query für Verbindungs-Statistiken
            query = """
                SELECT 
                    count(*) as total_connections,
                    count(*) FILTER WHERE state = 'active' as active_connections,
                    count(*) FILTER WHERE state = 'idle' as idle_connections,
                    count(*) FILTER WHERE state = 'idle in transaction' as idle_in_transaction,
                    count(*) FILTER WHERE wait_event_type = 'Lock' as waiting_for_lock
                FROM pg_stat_activity;
            """
            
            # psql command
            cmd = [
                "psql",
                "-h", self.host,
                "-p", str(self.port),
                "-U", self.user,
                "-d", self.database,
                "-c", query,
                "-v", "ON_ERROR_STOP=1",
                "-t",
            ]
            
            if self.password:
                cmd.extend(["-W"])
                os.environ["PGPASSWORD"] = self.password
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                # Output parsen
                lines = stdout.decode('utf-8', errors='replace').strip().split('\n')
                stats = {}
                
                for line in lines:
                    if line.strip() and not line.startswith("|") and not line.startswith("-"):
                        parts = [p.strip() for p in line.split("|")]
                        if len(parts) >= 2:
                            stats[parts[0].strip()] = int(parts[1]) if parts[1].isdigit() else 0
                
                return {
                    "success": True,
                    "stats": stats,
                }
            else:
                error = stderr.decode('utf-8', errors='replace')
                return {
                    "success": False,
                    "error": error,
                }
                
        except Exception as e:
            self.logger.error(
                "get_connection_stats_failed",
                error=str(e),
            )
            return {
                "success": False,
                "error": str(e),
            }
    
    async def get_schema_info(
        self,
        schema: str = "public",
    ) -> Dict[str, Any]:
        """
        Holt Schema-Informationen.
        
        Args:
            schema: Schema-Name (default: "public")
            
        Returns:
            Dict mit success, schema_info, metadata
        """
        self.logger.info(
            "getting_schema_info",
            schema=schema,
        )
        
        try:
            # PostgreSQL query für Schema-Informationen
            query = f"""
                SELECT 
                    table_name,
                    column_name,
                    data_type,
                    is_nullable,
                    column_default
                FROM information_schema.columns
                WHERE table_schema = '{schema}'
                ORDER BY table_name, ordinal_position;
            """
            
            # psql command
            cmd = [
                "psql",
                "-h", self.host,
                "-p", str(self.port),
                "-U", self.user,
                "-d", self.database,
                "-c", query,
                "-v", "ON_ERROR_STOP=1",
                "-t",
            ]
            
            if self.password:
                cmd.extend(["-W"])
                os.environ["PGPASSWORD"] = self.password
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                # Output parsen
                lines = stdout.decode('utf-8', errors='replace').strip().split('\n')
                columns = []
                
                for line in lines:
                    if line.strip() and not line.startswith("|") and not line.startswith("-"):
                        parts = [p.strip() for p in line.split("|")]
                        if len(parts) >= 5:
                            columns.append({
                                "table": parts[0],
                                "column": parts[1],
                                "type": parts[2],
                                "nullable": parts[3] == "YES",
                                "default": parts[4],
                            })
                
                return {
                    "success": True,
                    "columns": columns,
                    "count": len(columns),
                    "schema": schema,
                }
            else:
                error = stderr.decode('utf-8', errors='replace')
                return {
                    "success": False,
                    "error": error,
                }
                
        except Exception as e:
            self.logger.error(
                "get_schema_info_failed",
                schema=schema,
                error=str(e),
            )
            return {
                "success": False,
                "error": str(e),
            }
    
    async def get_index_info(
        self,
        schema: str = "public",
        table_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Holt Index-Informationen.
        
        Args:
            schema: Schema-Name (default: "public")
            table_name: Optionaler Tabellenname
            
        Returns:
            Dict mit success, indexes, metadata
        """
        self.logger.info(
            "getting_index_info",
            schema=schema,
            table=table_name,
        )
        
        try:
            # PostgreSQL query für Index-Informationen
            where_clause = f"AND schemaname = '{schema}'"
            if table_name:
                where_clause += f" AND tablename = '{table_name}'"
            
            query = f"""
                SELECT 
                    schemaname,
                    tablename,
                    indexname,
                    indexdef
                FROM pg_indexes
                WHERE {where_clause}
                ORDER BY schemaname, tablename, indexname;
            """
            
            # psql command
            cmd = [
                "psql",
                "-h", self.host,
                "-p", str(self.port),
                "-U", self.user,
                "-d", self.database,
                "-c", query,
                "-v", "ON_ERROR_STOP=1",
                "-t",
            ]
            
            if self.password:
                cmd.extend(["-W"])
                os.environ["PGPASSWORD"] = self.password
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                # Output parsen
                lines = stdout.decode('utf-8', errors='replace').strip().split('\n')
                indexes = []
                
                for line in lines:
                    if line.strip() and not line.startswith("|") and not line.startswith("-"):
                        parts = [p.strip() for p in line.split("|")]
                        if len(parts) >= 4:
                            indexes.append({
                                "schema": parts[0],
                                "table": parts[1],
                                "index": parts[2],
                                "definition": parts[3][:200],  # Limit Länge
                            })
                
                return {
                    "success": True,
                    "indexes": indexes,
                    "count": len(indexes),
                    "schema": schema,
                    "table": table_name,
                }
            else:
                error = stderr.decode('utf-8', errors='replace')
                return {
                    "success": False,
                    "error": error,
                }
                
        except Exception as e:
            self.logger.error(
                "get_index_info_failed",
                schema=schema,
                table=table_name,
                error=str(e),
            )
            return {
                "success": False,
                "error": str(e),
            }
    
    async def execute_query(
        self,
        query: str,
        params: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Führt eine Query aus.
        
        Args:
            query: Die auszuführende Query
            params: Optionale Parameter
            
        Returns:
            Dict mit success, result, metadata
        """
        self.logger.info(
            "executing_query",
            query=query[:100],  # Query limitieren für Log
        )
        
        try:
            # psql command
            cmd = [
                "psql",
                "-h", self.host,
                "-p", str(self.port),
                "-U", self.user,
                "-d", self.database,
                "-c", query,
                "-v", "ON_ERROR_STOP=1",
                "-t",
            ]
            
            if self.password:
                cmd.extend(["-W"])
                os.environ["PGPASSWORD"] = self.password
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                result = stdout.decode('utf-8', errors='replace')
                
                return {
                    "success": True,
                    "result": result,
                    "query": query[:100],
                }
            else:
                error = stderr.decode('utf-8', errors='replace')
                return {
                    "success": False,
                    "error": error,
                    "query": query[:100],
                }
                
        except Exception as e:
            self.logger.error(
                "execute_query_failed",
                query=query[:100],
                error=str(e),
            )
            return {
                "success": False,
                "error": str(e),
                "query": query[:100],
            }
