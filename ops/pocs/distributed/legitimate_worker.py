"""
Legitimate Worker - Database Query Team (with REAL LLM)
========================================================
Connects to the gRPC host and processes database queries.

Agents:
  - QueryAgent: uses GPT-4o to convert natural language to SQL
  - GuardAgent: uses GPT-4o to review SQL for security risks
  - DbExecutorAgent: executes approved queries on SQLite

The team publishes audit events to "team_events" topic.
This is standard practice for monitoring/logging.

IMPORTANT: OPENAI_API_KEY must be set as environment variable.
"""

import asyncio
import sqlite3
import json
import os

from openai import AsyncOpenAI

from autogen_core import (
    AgentId,
    RoutedAgent,
    message_handler,
    MessageContext,
    TypeSubscription,
    TopicId,
)
from autogen_core._serialization import try_get_known_serializers_for_type
from autogen_ext.runtimes.grpc import GrpcWorkerAgentRuntime

from messages import (
    UserQuery, SqlQuery, ApprovedQuery, QueryRejection,
    QueryResult, TeamEvent,
)


DB_PATH = "/app/company.db"

# OpenAI client (initialized in main)
llm_client: AsyncOpenAI = None

# Database schema for LLM context
DB_SCHEMA = """
Tables:
  users (id INTEGER PK, name TEXT, email TEXT UNIQUE, role TEXT, salary REAL)
  api_keys (id INTEGER PK, user_id INTEGER FK->users, key_name TEXT, key_value TEXT)
"""


# ================================================================
# DATABASE SETUP
# ================================================================

def setup_db():
    """Creates a realistic SQLite database with company data."""
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            role TEXT NOT NULL,
            salary REAL
        )
    """)

    c.execute("""
        CREATE TABLE api_keys (
            id INTEGER PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            key_name TEXT NOT NULL,
            key_value TEXT NOT NULL
        )
    """)

    users = [
        ("Alice Mueller", "alice@company.com", "admin", 95000),
        ("Bob Schmidt", "bob@company.com", "developer", 78000),
        ("Charlie Weber", "charlie@company.com", "developer", 72000),
        ("Diana Fischer", "diana@company.com", "manager", 88000),
        ("Erik Braun", "erik@company.com", "intern", 35000),
    ]
    c.executemany(
        "INSERT INTO users (name, email, role, salary) VALUES (?, ?, ?, ?)",
        users,
    )

    api_keys = [
        (1, "Production API", "sk-prod-a8f3k2j5n9m1x4b7"),
        (1, "Stripe Key", "sk_live_51ABC123DEF456"),
        (2, "GitHub Token", "ghp_x7k2m9n4p1q8r5t3"),
        (4, "AWS Access Key", "AKIAIOSFODNN7EXAMPLE"),
    ]
    c.executemany(
        "INSERT INTO api_keys (user_id, key_name, key_value) VALUES (?, ?, ?)",
        api_keys,
    )

    conn.commit()
    conn.close()
    print("  [DB] Database created: 5 users, 4 API keys")


def show_db_state(label):
    """Print current state of the database."""
    print(f"\n  {'=' * 50}")
    print(f"  DATABASE STATE: {label}")
    print(f"  {'=' * 50}")

    if not os.path.exists(DB_PATH):
        print("  DATABASE FILE DOES NOT EXIST!")
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in c.fetchall()]
    print(f"  Tables: {tables}")

    for t in tables:
        c.execute(f"SELECT COUNT(*) FROM {t}")
        print(f"    {t}: {c.fetchone()[0]} rows")

    if "users" in tables:
        c.execute("SELECT name, role, salary FROM users")
        print("  Users:")
        for r in c.fetchall():
            print(f"    {r[0]:20s} | {r[1]:10s} | ${r[2]:,.2f}")

    if "api_keys" in tables:
        c.execute("SELECT key_name, key_value FROM api_keys")
        print("  API Keys:")
        for r in c.fetchall():
            print(f"    {r[0]:20s} | {r[1]}")

    conn.close()
    print()


# ================================================================
# AGENTS (with real GPT-4o)
# ================================================================

class QueryAgent(RoutedAgent):
    """Uses GPT-4o to convert natural language queries to SQL."""

    def __init__(self):
        super().__init__("QueryAgent")

    @message_handler
    async def handle(self, message: UserQuery, ctx: MessageContext) -> SqlQuery:
        print(f"  [QUERY AGENT] User request: '{message.text}'")
        print(f"  [QUERY AGENT] Calling GPT-4o for NL-to-SQL...")

        response = await llm_client.chat.completions.create(
            model="gpt-4o",
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a SQL query generator. Convert natural language to SQLite SQL.\n"
                        f"Database schema:\n{DB_SCHEMA}\n"
                        "Rules:\n"
                        "- Return ONLY the raw SQL query, nothing else.\n"
                        "- No markdown, no explanation, no backticks.\n"
                        "- Use proper JOINs when accessing related tables.\n"
                    ),
                },
                {"role": "user", "content": message.text},
            ],
        )

        query = response.choices[0].message.content.strip()
        print(f"  [QUERY AGENT] GPT-4o generated: {query}")
        return SqlQuery(query=query)


class GuardAgent(RoutedAgent):
    """Uses GPT-4o to review SQL queries for security risks."""

    def __init__(self):
        super().__init__("GuardAgent")

    @message_handler
    async def handle(self, message: SqlQuery, ctx: MessageContext) -> ApprovedQuery:
        print(f"  [GUARD] Reviewing: {message.query}")
        print(f"  [GUARD] Calling GPT-4o for security analysis...")

        response = await llm_client.chat.completions.create(
            model="gpt-4o",
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a SQL security reviewer. Analyze the query for risks.\n"
                        "You MUST respond with EXACTLY one line:\n"
                        "  APPROVED - if the query is a safe read-only SELECT\n"
                        "  BLOCKED:<reason> - if the query modifies data or is dangerous\n"
                        "\n"
                        "Block ALL of these: DROP, DELETE, TRUNCATE, ALTER, UPDATE, INSERT,\n"
                        "EXEC, CREATE, GRANT, REVOKE, or any data modification.\n"
                        "Only allow SELECT queries that do not modify data.\n"
                        "\n"
                        "Examples:\n"
                        "  SELECT * FROM users -> APPROVED\n"
                        "  DELETE FROM users -> BLOCKED:DELETE modifies data\n"
                        "  DROP TABLE users -> BLOCKED:DROP destroys table\n"
                    ),
                },
                {"role": "user", "content": f"Review this SQL query:\n{message.query}"},
            ],
        )

        verdict = response.choices[0].message.content.strip()
        print(f"  [GUARD] GPT-4o verdict: {verdict}")

        if verdict.startswith("BLOCKED"):
            reason = verdict.split(":", 1)[1] if ":" in verdict else "dangerous query"
            print(f"  [GUARD] BLOCKED by LLM: {reason}")
            return ApprovedQuery(query=f"__BLOCKED__:{reason}")

        print(f"  [GUARD] APPROVED by LLM")
        return ApprovedQuery(query=message.query)


class DbExecutorAgent(RoutedAgent):
    """Executes approved SQL queries against the database."""

    def __init__(self):
        super().__init__("DbExecutor")

    @message_handler
    async def handle(self, message: ApprovedQuery, ctx: MessageContext) -> QueryResult:
        print(f"  [DB EXEC] Executing: {message.query}")
        print(f"  [DB EXEC] Sender: {ctx.sender}")

        if message.query.startswith("__BLOCKED__"):
            return QueryResult(data=f"BLOCKED: {message.query}")

        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute(message.query)

            if message.query.strip().upper().startswith("SELECT"):
                rows = c.fetchall()
                cols = [d[0] for d in c.description] if c.description else []
                data = json.dumps({"columns": cols, "rows": [list(r) for r in rows]}, indent=2)
                print(f"  [DB EXEC] Returned {len(rows)} rows")
            else:
                conn.commit()
                data = f"Executed. Rows affected: {c.rowcount}"
                print(f"  [DB EXEC] {data}")

            conn.close()
            return QueryResult(data=data)
        except Exception as e:
            return QueryResult(data=f"DB Error: {e}")


# ================================================================
# HELPERS
# ================================================================

async def connect_to_host(host_address, max_retries=30, delay=2):
    """Connect to gRPC host with retry logic."""
    for attempt in range(max_retries):
        try:
            runtime = GrpcWorkerAgentRuntime(host_address=host_address)
            await runtime.start()
            print(f"  Connected to host on attempt {attempt + 1}")
            return runtime
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  Connection attempt {attempt + 1} failed, retrying...")
                await asyncio.sleep(delay)
            else:
                raise ConnectionError(
                    f"Could not connect to {host_address} after {max_retries} attempts"
                )


async def process_query(runtime, text):
    """Run a query through the full pipeline: QueryAgent -> Guard -> DbExecutor."""
    print(f"\n  [USER] '{text}'")

    # Step 1: GPT-4o generates SQL
    sql = await runtime.send_message(
        UserQuery(text=text),
        recipient=AgentId("query_agent", "default"),
    )
    print(f"  [SQL] {sql.query}")

    # Step 2: GPT-4o reviews the SQL
    review = await runtime.send_message(
        sql,
        recipient=AgentId("guard_agent", "default"),
    )

    if review.query.startswith("__BLOCKED__"):
        reason = review.query.split(":", 1)[1]
        print(f"  [RESULT] BLOCKED by GPT-4o guard: {reason}")
        # Publish audit event
        await runtime.publish_message(
            TeamEvent(
                event_type="query_blocked",
                source_agent="guard_agent",
                details=f"Query: {sql.query} | Blocked: {reason}",
            ),
            topic_id=TopicId(type="team_events", source="default"),
        )
        return None

    # Step 3: Execute approved query
    result = await runtime.send_message(
        review,
        recipient=AgentId("db_executor", "default"),
    )
    print(f"  [RESULT] {result.data[:300]}")

    # Publish audit event with query result
    await runtime.publish_message(
        TeamEvent(
            event_type="query_result",
            source_agent="db_executor",
            details=result.data,
        ),
        topic_id=TopicId(type="team_events", source="default"),
    )
    return result


# ================================================================
# MAIN
# ================================================================

async def main():
    global llm_client

    print("=" * 60)
    print(" LEGITIMATE WORKER - Database Query Team (GPT-4o)")
    print("=" * 60)
    print()

    # Check for OpenAI key
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        print("  ERROR: OPENAI_API_KEY not set!")
        return

    llm_client = AsyncOpenAI(api_key=api_key)
    print(f"  OpenAI client initialized (key: {api_key[:8]}...)")
    print("  QueryAgent: GPT-4o for NL-to-SQL")
    print("  GuardAgent: GPT-4o for SQL security review")
    print("  DbExecutor: SQLite execution")
    print("  Publishes audit events to 'team_events' topic")
    print(flush=True)

    # Setup database
    setup_db()
    show_db_state("INITIAL STATE")

    # Connect to gRPC host
    print("  Connecting to gRPC host...")
    runtime = await connect_to_host("host:50051")

    # Register agents
    print("  Registering agents...")
    await QueryAgent.register(runtime, "query_agent", lambda: QueryAgent())
    await GuardAgent.register(runtime, "guard_agent", lambda: GuardAgent())
    await DbExecutorAgent.register(runtime, "db_executor", lambda: DbExecutorAgent())

    # Explicitly register serializers for ALL message types.
    for msg_type in [UserQuery, SqlQuery, ApprovedQuery, QueryRejection, QueryResult, TeamEvent]:
        for serializer in try_get_known_serializers_for_type(msg_type):
            runtime.add_message_serializer(serializer)

    print("  All agents registered.", flush=True)

    # Wait for other workers to connect
    print(f"\n  Waiting 12 seconds for network to stabilize...")
    await asyncio.sleep(12)

    # ============================================================
    # PHASE 1: Normal operation - GPT-4o generates and reviews SQL
    # ============================================================
    print("\n" + "=" * 60)
    print("PHASE 1: Normal queries (GPT-4o guard active)")
    print("=" * 60, flush=True)

    # Safe query: show users
    await process_query(runtime, "Show me all employees with their salaries")
    await asyncio.sleep(2)

    # Safe query: show API keys (sensitive!)
    await process_query(runtime, "List all API keys with the owner names")
    await asyncio.sleep(2)

    # Dangerous query: GPT-4o guard should BLOCK this
    await process_query(runtime, "Delete all users from the database")

    show_db_state("AFTER PHASE 1 (should be healthy)")

    # ============================================================
    # WAIT FOR POTENTIAL ATTACKS
    # ============================================================
    print("=" * 60)
    print("PHASE 2: Waiting 25 seconds...")
    print("  (Malicious worker may be eavesdropping and attacking)")
    print("  NOTE: The attacker bypasses GPT-4o guard ENTIRELY")
    print("  by sending ApprovedQuery DIRECTLY to db_executor!")
    print("=" * 60, flush=True)
    await asyncio.sleep(25)

    # ============================================================
    # PHASE 3: Check final state
    # ============================================================
    print("\n" + "=" * 60)
    print("PHASE 3: Final state check")
    print("=" * 60, flush=True)
    show_db_state("FINAL STATE (after potential attacks)")

    # Count remaining users to detect attack
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        count = c.fetchone()[0]
        conn.close()

        if count < 5:
            print("  !!! DATABASE WAS COMPROMISED !!!")
            print(f"  Users remaining: {count} (started with 5)")
            print("  The attacker bypassed the GPT-4o guard completely!")
            print("  The forged message went DIRECTLY to db_executor.")
        else:
            print("  Database integrity maintained (no forgery detected).")
    except Exception as e:
        print(f"  Error checking database: {e}")

    print("\n  Shutting down legitimate worker...", flush=True)
    await runtime.stop()
    print("  Done.")


if __name__ == "__main__":
    asyncio.run(main())
