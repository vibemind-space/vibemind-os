#!/usr/bin/env python3
"""
PostgreSQL MCP Agent - Database operations via custom asyncpg tools.

Provides:
- SQL query execution (SELECT, INSERT, UPDATE, DELETE)
- Schema inspection and table management
- Database diagnostics and statistics
- Index and constraint management

Follows Society of Mind pattern with EventServer broadcasting.
Uses custom asyncpg tools (no deprecated MCP server dependency).
"""
import asyncio
import json
import os
import sys
import time
from dataclasses import field
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse

# Force UTF-8 encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Load .env from project root
try:
    import dotenv
    # Path: mcp_plugins/servers/postgres/agent.py -> go up 3 levels to project root
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', '.env')
    dotenv.load_dotenv(dotenv_path=env_path)
except Exception:
    pass

# Autogen imports
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.conditions import TextMentionTermination
from autogen_core.model_context import BufferedChatCompletionContext
from pydantic import BaseModel

# Import global LLM config
from src.llm_config import get_model

# Shared module imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
from event_server import EventServer, start_ui_server
from constants import (
    MCP_EVENT_SESSION_ANNOUNCE,
    SESSION_STATE_RUNNING,
    SESSION_STATE_STOPPED,
    SESSION_STATE_ERROR,
)
from model_init import init_model_client as shared_init_model_client
from logging_utils import setup_logging
from conversation_logger import ConversationLogger, SenseCategory


class PostgresAgentConfig(BaseModel):
    """Configuration for PostgreSQL MCP Agent."""
    session_id: str
    task: str
    name: str = "postgres-session"
    model: str = field(default_factory=lambda: get_model("mcp_agent"))
    working_dir: str = "."
    database_url: Optional[str] = None


# System prompts
POSTGRES_OPERATOR_PROMPT = """You are a PostgreSQL database expert with deep knowledge of SQL, schema design, and database operations.

Your capabilities include:
- query: Execute any SQL query (SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, DROP)
- list_tables: List all tables in the database with row counts
- describe_table: Get detailed schema for a specific table
- list_indexes: Show all indexes and their definitions
- list_constraints: Show foreign keys and constraints
- get_table_stats: Get statistics about a table (size, rows, etc.)
- explain_query: Get query execution plan (EXPLAIN ANALYZE)

Guidelines:
1. Always explain what you're doing before executing queries
2. For destructive operations (DROP, DELETE, TRUNCATE), confirm the implications
3. Provide clear explanations of query results
4. Suggest optimizations when you notice inefficiencies
5. Use parameterized queries when dealing with user input
6. Handle errors gracefully and explain what went wrong

When you have completed the task, say "TASK_COMPLETE".
"""

QA_VALIDATOR_PROMPT = """You are a QA Validator for PostgreSQL operations.

Your role:
1. Verify that SQL queries are safe and correct
2. Check that results match the user's intent
3. Ensure no destructive operations without confirmation
4. Validate that the task was completed successfully

When the task is fully validated, say "TASK_COMPLETE".
"""


class PostgresTools:
    """Custom PostgreSQL tool implementations using asyncpg."""

    def __init__(self, database_url: str):
        self.database_url = database_url
        self._pool = None

    def _parse_url(self, url: str) -> dict:
        """Parse database URL into connection params."""
        # Handle asyncpg format
        if url.startswith("postgresql+asyncpg://"):
            url = url.replace("postgresql+asyncpg://", "postgresql://")

        parsed = urlparse(url)
        return {
            "host": parsed.hostname or "localhost",
            "port": parsed.port or 5432,
            "user": parsed.username or "postgres",
            "password": parsed.password or "postgres",
            "database": parsed.path.lstrip("/") or "postgres",
        }

    async def _get_pool(self):
        """Lazy-load connection pool."""
        if self._pool is None:
            try:
                import asyncpg
                params = self._parse_url(self.database_url)
                self._pool = await asyncpg.create_pool(
                    host=params["host"],
                    port=params["port"],
                    user=params["user"],
                    password=params["password"],
                    database=params["database"],
                    min_size=1,
                    max_size=5,
                )
            except ImportError:
                raise ImportError("asyncpg not installed. Run: pip install asyncpg")
        return self._pool

    async def _execute(self, sql: str, params: list = None) -> Dict[str, Any]:
        """Execute SQL and return results."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            try:
                if sql.strip().upper().startswith("SELECT") or sql.strip().upper().startswith("WITH"):
                    rows = await conn.fetch(sql, *(params or []))
                    return {
                        "success": True,
                        "rows": [dict(row) for row in rows],
                        "row_count": len(rows),
                    }
                else:
                    result = await conn.execute(sql, *(params or []))
                    return {
                        "success": True,
                        "result": result,
                        "message": f"Query executed: {result}",
                    }
            except Exception as e:
                return {"success": False, "error": str(e)}

    async def query(self, sql: str) -> dict:
        """Execute any SQL query.

        Args:
            sql: SQL query to execute (SELECT, INSERT, UPDATE, DELETE, etc.)

        Returns:
            Dict with query results or error message

        Examples:
            query("SELECT * FROM users LIMIT 10")
            query("INSERT INTO users (name) VALUES ('John')")
            query("UPDATE users SET active = true WHERE id = 1")
        """
        return await self._execute(sql)

    async def list_tables(self) -> dict:
        """List all tables in the database with row counts.

        Returns:
            Dict with list of tables, their schemas, and row counts
        """
        sql = """
        SELECT
            schemaname as schema,
            tablename as table_name,
            pg_total_relation_size(schemaname || '.' || tablename) as size_bytes,
            (SELECT COUNT(*) FROM information_schema.columns
             WHERE table_schema = t.schemaname AND table_name = t.tablename) as column_count
        FROM pg_tables t
        WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
        ORDER BY schemaname, tablename
        """
        result = await self._execute(sql)
        if result.get("success"):
            tables = result.get("rows", [])
            # Format size
            for t in tables:
                size = t.get("size_bytes", 0)
                if size > 1024 * 1024:
                    t["size"] = f"{size / (1024*1024):.2f} MB"
                elif size > 1024:
                    t["size"] = f"{size / 1024:.2f} KB"
                else:
                    t["size"] = f"{size} B"
            return {
                "success": True,
                "tables": tables,
                "count": len(tables),
            }
        return result

    async def describe_table(self, table_name: str, schema: str = "public") -> dict:
        """Get detailed schema for a specific table.

        Args:
            table_name: Name of the table
            schema: Schema name (default: public)

        Returns:
            Dict with column definitions, types, and constraints
        """
        sql = """
        SELECT
            column_name,
            data_type,
            character_maximum_length,
            is_nullable,
            column_default,
            (SELECT EXISTS (
                SELECT 1 FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
                WHERE tc.table_name = c.table_name
                AND kcu.column_name = c.column_name
                AND tc.constraint_type = 'PRIMARY KEY'
            )) as is_primary_key
        FROM information_schema.columns c
        WHERE table_schema = $1 AND table_name = $2
        ORDER BY ordinal_position
        """
        result = await self._execute(sql, [schema, table_name])
        if result.get("success"):
            columns = result.get("rows", [])
            return {
                "success": True,
                "table": f"{schema}.{table_name}",
                "columns": columns,
                "column_count": len(columns),
            }
        return result

    async def list_indexes(self, table_name: str = None) -> dict:
        """Show all indexes and their definitions.

        Args:
            table_name: Optional table name to filter indexes

        Returns:
            Dict with index information
        """
        sql = """
        SELECT
            schemaname as schema,
            tablename as table_name,
            indexname as index_name,
            indexdef as definition
        FROM pg_indexes
        WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
        """
        if table_name:
            sql += " AND tablename = $1"
            result = await self._execute(sql, [table_name])
        else:
            result = await self._execute(sql)

        if result.get("success"):
            return {
                "success": True,
                "indexes": result.get("rows", []),
                "count": len(result.get("rows", [])),
            }
        return result

    async def list_constraints(self, table_name: str = None) -> dict:
        """Show foreign keys and constraints.

        Args:
            table_name: Optional table name to filter constraints

        Returns:
            Dict with constraint information
        """
        sql = """
        SELECT
            tc.table_schema as schema,
            tc.table_name,
            tc.constraint_name,
            tc.constraint_type,
            kcu.column_name,
            ccu.table_name AS foreign_table,
            ccu.column_name AS foreign_column
        FROM information_schema.table_constraints tc
        LEFT JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
        LEFT JOIN information_schema.constraint_column_usage ccu
            ON ccu.constraint_name = tc.constraint_name
            AND ccu.table_schema = tc.table_schema
        WHERE tc.table_schema NOT IN ('pg_catalog', 'information_schema')
        """
        if table_name:
            sql += " AND tc.table_name = $1"
            result = await self._execute(sql, [table_name])
        else:
            result = await self._execute(sql)

        if result.get("success"):
            return {
                "success": True,
                "constraints": result.get("rows", []),
                "count": len(result.get("rows", [])),
            }
        return result

    async def get_table_stats(self, table_name: str, schema: str = "public") -> dict:
        """Get statistics about a table (size, rows, etc.).

        Args:
            table_name: Name of the table
            schema: Schema name (default: public)

        Returns:
            Dict with table statistics
        """
        full_name = f"{schema}.{table_name}"
        stats_sql = f"""
        SELECT
            pg_total_relation_size('{full_name}') as total_size,
            pg_table_size('{full_name}') as table_size,
            pg_indexes_size('{full_name}') as indexes_size,
            (SELECT COUNT(*) FROM {full_name}) as row_count,
            (SELECT COUNT(*) FROM information_schema.columns
             WHERE table_schema = '{schema}' AND table_name = '{table_name}') as column_count
        """
        result = await self._execute(stats_sql)
        if result.get("success") and result.get("rows"):
            stats = result["rows"][0]
            # Format sizes
            for key in ["total_size", "table_size", "indexes_size"]:
                size = stats.get(key, 0)
                if size > 1024 * 1024:
                    stats[f"{key}_formatted"] = f"{size / (1024*1024):.2f} MB"
                elif size > 1024:
                    stats[f"{key}_formatted"] = f"{size / 1024:.2f} KB"
                else:
                    stats[f"{key}_formatted"] = f"{size} B"
            return {
                "success": True,
                "table": full_name,
                "stats": stats,
            }
        return result

    async def explain_query(self, sql: str) -> dict:
        """Get query execution plan (EXPLAIN ANALYZE).

        Args:
            sql: SQL query to analyze

        Returns:
            Dict with execution plan
        """
        explain_sql = f"EXPLAIN ANALYZE {sql}"
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            try:
                rows = await conn.fetch(explain_sql)
                plan_lines = [row[0] for row in rows]
                return {
                    "success": True,
                    "query": sql,
                    "plan": plan_lines,
                    "plan_text": "\n".join(plan_lines),
                }
            except Exception as e:
                return {"success": False, "error": str(e)}

    async def close(self):
        """Close the connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None


async def run_postgres_agent(config: PostgresAgentConfig):
    """Run the PostgreSQL MCP agent with the given configuration."""
    logger = setup_logging(f"postgres_agent_{config.session_id}")
    event_server = EventServer(session_id=config.session_id, tool_name="postgres")

    # Initialize ConversationLogger for ML-ready logs
    conv_logger = ConversationLogger(
        session_id=config.session_id,
        tool_name="postgres",
        sense_category=SenseCategory.MEMORY
    )

    pg_tools = None

    try:
        # Start the UI server with event broadcasting
        httpd, thread, host, port = start_ui_server(
            event_server,
            host="127.0.0.1",
            port=0,  # Dynamic port assignment
            tool_name="postgres"
        )
        logger.info(f"UI server started on {host}:{port}")

        # Announce session
        announce_data = {
            "session_id": config.session_id,
            "host": host,
            "port": port,
            "ui_url": f"http://{host}:{port}/"
        }
        print(f"SESSION_ANNOUNCE {json.dumps(announce_data)}", flush=True)
        event_server.broadcast(MCP_EVENT_SESSION_ANNOUNCE, announce_data)

        # Log session start
        conv_logger.log_session_start(config.task, config.model)

        # Get model client
        model_client = shared_init_model_client("postgres", config.task)
        logger.info(f"Model initialized: {config.model}")

        # Get database URL from config or environment
        database_url = config.database_url or os.getenv(
            "DATABASE_URL",
            "postgresql://postgres:postgres@localhost:5432/coding_engine"
        )

        # Initialize PostgreSQL tools
        pg_tools = PostgresTools(database_url)
        event_server.broadcast("log", f"Connecting to PostgreSQL...")

        # Create tool list
        tools = [
            pg_tools.query,
            pg_tools.list_tables,
            pg_tools.describe_table,
            pg_tools.list_indexes,
            pg_tools.list_constraints,
            pg_tools.get_table_stats,
            pg_tools.explain_query,
        ]

        logger.info(f"Loaded {len(tools)} PostgreSQL tools")
        event_server.broadcast("log", f"Loaded {len(tools)} custom PostgreSQL tools (asyncpg)")

        # Create Operator agent
        operator = AssistantAgent(
            name="PostgresOperator",
            model_client=model_client,
            tools=tools,
            system_message=POSTGRES_OPERATOR_PROMPT,
            model_context=BufferedChatCompletionContext(buffer_size=20),
        )

        # Create QA Validator agent
        qa_validator = AssistantAgent(
            name="QA_Validator",
            model_client=model_client,
            tools=[],  # No tools, just validation
            system_message=QA_VALIDATOR_PROMPT,
            model_context=BufferedChatCompletionContext(buffer_size=10),
        )

        # Create team with round-robin chat
        termination = TextMentionTermination("TASK_COMPLETE")
        team = RoundRobinGroupChat(
            participants=[operator, qa_validator],
            termination_condition=termination,
            max_turns=20,
        )

        # Send running status
        event_server.broadcast("log", f"Starting task: {config.task}")
        event_server.broadcast("status", SESSION_STATE_RUNNING)

        # Run the team
        result = await team.run(task=config.task)

        # Extract result
        result_text = ""
        if result.messages:
            result_text = str(result.messages[-1].content)
        else:
            result_text = "Task completed"

        # Log agent messages
        for msg in result.messages:
            agent_name = getattr(msg, 'source', 'Unknown')
            content = str(msg.content) if hasattr(msg, 'content') else str(msg)
            event_server.broadcast("agent.message", {
                "agent": agent_name,
                "content": content[:500],  # Truncate for broadcast
                "timestamp": time.time()
            })

        # Send completion
        event_server.broadcast("log", f"Result: {result_text[:200]}...")
        event_server.broadcast("status", SESSION_STATE_STOPPED)

        # Log conversation turn
        conv_logger.log_conversation_turn(
            agent="PostgresOperator",
            agent_response=result_text,
            final_response=result_text
        )

        # Send final result event
        event_server.broadcast("agent.completion", {
            "status": "success",
            "content": result_text,
            "tool": "postgres",
            "timestamp": time.time()
        })

        logger.info("Task completed successfully")
        return {"success": True, "result": result_text}

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error: {error_msg}", exc_info=True)
        event_server.broadcast("error", error_msg)
        event_server.broadcast("status", SESSION_STATE_ERROR)
        return {"success": False, "error": error_msg}

    finally:
        # Close PostgreSQL pool
        if pg_tools:
            await pg_tools.close()

        # Keep server running briefly so events can be consumed
        await asyncio.sleep(2)
        try:
            httpd.shutdown()
        except Exception:
            pass


async def main():
    """Main entry point with argument parsing."""
    import argparse
    parser = argparse.ArgumentParser(description="PostgreSQL MCP Agent (asyncpg)")
    parser.add_argument('--session-id', required=False, help="Session identifier")
    parser.add_argument('--name', default='postgres-session', help="Session name")
    parser.add_argument('--model', default=get_model("mcp_agent"), help="Model to use")
    parser.add_argument('--task', default='List all tables in the database', help="Task to execute")
    parser.add_argument('--working-dir', dest='working_dir', default='.', help="Working directory")
    parser.add_argument('--database-url', default=None, help="PostgreSQL connection URL")
    parser.add_argument('config_json', nargs='?', help="JSON config (alternative to flags)")
    args = parser.parse_args()

    try:
        if args.config_json:
            config_dict = json.loads(args.config_json)
        elif args.session_id:
            config_dict = {
                'session_id': args.session_id,
                'name': args.name,
                'model': args.model,
                'task': args.task,
                'working_dir': args.working_dir,
                'database_url': args.database_url,
            }
        else:
            # Generate session ID if not provided
            import uuid
            config_dict = {
                'session_id': f"postgres_{uuid.uuid4().hex[:8]}",
                'name': args.name,
                'model': args.model,
                'task': args.task,
                'working_dir': args.working_dir,
                'database_url': args.database_url,
            }

        config = PostgresAgentConfig(**config_dict)
        result = await run_postgres_agent(config)

        if not result.get("success"):
            sys.exit(1)

    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
