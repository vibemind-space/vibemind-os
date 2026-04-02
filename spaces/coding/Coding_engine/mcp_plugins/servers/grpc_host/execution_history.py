#!/usr/bin/env python3
"""
Execution History - Iteration 5

SQLite-basierte Speicherung der Tool-Ausführungshistorie für
kontinuierliches Lernen und Optimierung.

Features:
- Persistente Speicherung aller Tool-Aufrufe
- Statistiken pro Tool (Erfolgsrate, Durchschnittsdauer)
- Pattern-Erkennung für erfolgreiche Workflows
- Empfehlungen basierend auf Historie
"""

import sqlite3
import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)


@dataclass
class ToolExecution:
    """Ein Tool-Ausführungseintrag"""
    id: Optional[int] = None
    tool_name: str = ""
    arguments: Dict[str, Any] = None
    result: str = ""
    success: bool = True
    error: Optional[str] = None
    duration_ms: int = 0
    from_cache: bool = False
    task_type: str = "general"
    session_id: str = ""
    timestamp: str = ""

    def __post_init__(self):
        if self.arguments is None:
            self.arguments = {}
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class ToolStats:
    """Statistiken für ein Tool"""
    tool_name: str
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    avg_duration_ms: float = 0.0
    success_rate: float = 0.0
    cache_hit_rate: float = 0.0
    last_used: str = ""
    common_errors: List[str] = None

    def __post_init__(self):
        if self.common_errors is None:
            self.common_errors = []


@dataclass
class WorkflowPattern:
    """Ein erkanntes Workflow-Pattern"""
    tools_sequence: List[str]
    task_type: str
    occurrence_count: int
    avg_success_rate: float
    avg_total_duration_ms: int


class ExecutionHistoryStore:
    """
    SQLite-basierter Store für Tool-Ausführungshistorie.

    Speichert alle Tool-Aufrufe und ermöglicht Analyse
    für Optimierungen.
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Args:
            db_path: Pfad zur SQLite DB. Default: ~/.coding_engine/execution_history.db
        """
        if db_path:
            self.db_path = Path(db_path)
        else:
            self.db_path = Path.home() / ".coding_engine" / "execution_history.db"

        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_db()
        logger.info(f"ExecutionHistoryStore initialized: {self.db_path}")

    @contextmanager
    def _get_connection(self):
        """Context Manager für DB-Verbindungen"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self):
        """Initialisiert die Datenbank"""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS executions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_name TEXT NOT NULL,
                    arguments TEXT,
                    result TEXT,
                    success INTEGER NOT NULL,
                    error TEXT,
                    duration_ms INTEGER,
                    from_cache INTEGER,
                    task_type TEXT,
                    session_id TEXT,
                    timestamp TEXT NOT NULL
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tool_name ON executions(tool_name)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp ON executions(timestamp)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_session ON executions(session_id)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_task_type ON executions(task_type)
            """)

    def record(self, execution: ToolExecution) -> int:
        """
        Speichert eine Tool-Ausführung.

        Args:
            execution: Der Ausführungseintrag

        Returns:
            ID des Eintrags
        """
        with self._get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO executions
                (tool_name, arguments, result, success, error, duration_ms,
                 from_cache, task_type, session_id, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                execution.tool_name,
                json.dumps(execution.arguments),
                execution.result[:5000] if execution.result else "",  # Truncate
                1 if execution.success else 0,
                execution.error,
                execution.duration_ms,
                1 if execution.from_cache else 0,
                execution.task_type,
                execution.session_id,
                execution.timestamp,
            ))

            return cursor.lastrowid

    def get_tool_stats(self, tool_name: str, days: int = 30) -> ToolStats:
        """
        Gibt Statistiken für ein Tool zurück.

        Args:
            tool_name: Name des Tools
            days: Zeitraum in Tagen

        Returns:
            ToolStats
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        with self._get_connection() as conn:
            row = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful,
                    SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failed,
                    AVG(duration_ms) as avg_duration,
                    SUM(CASE WHEN from_cache = 1 THEN 1 ELSE 0 END) as cache_hits,
                    MAX(timestamp) as last_used
                FROM executions
                WHERE tool_name = ? AND timestamp > ?
            """, (tool_name, cutoff)).fetchone()

            # Häufige Fehler
            errors = conn.execute("""
                SELECT error, COUNT(*) as cnt
                FROM executions
                WHERE tool_name = ? AND success = 0 AND error IS NOT NULL
                  AND timestamp > ?
                GROUP BY error
                ORDER BY cnt DESC
                LIMIT 5
            """, (tool_name, cutoff)).fetchall()

            total = row["total"] or 0

            return ToolStats(
                tool_name=tool_name,
                total_calls=total,
                successful_calls=row["successful"] or 0,
                failed_calls=row["failed"] or 0,
                avg_duration_ms=row["avg_duration"] or 0.0,
                success_rate=(row["successful"] / total * 100) if total > 0 else 0.0,
                cache_hit_rate=((row["cache_hits"] or 0) / total * 100) if total > 0 else 0.0,
                last_used=row["last_used"] or "",
                common_errors=[e["error"][:100] for e in errors]
            )

    def get_all_tool_stats(self, days: int = 30) -> List[ToolStats]:
        """Gibt Statistiken für alle Tools zurück"""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        with self._get_connection() as conn:
            tools = conn.execute("""
                SELECT DISTINCT tool_name
                FROM executions
                WHERE timestamp > ?
            """, (cutoff,)).fetchall()

        return [self.get_tool_stats(t["tool_name"], days) for t in tools]

    def get_successful_patterns(
        self,
        task_type: str,
        min_occurrences: int = 3
    ) -> List[WorkflowPattern]:
        """
        Findet erfolgreiche Tool-Sequenzen für einen Task-Typ.

        Args:
            task_type: Art der Aufgabe
            min_occurrences: Mindestanzahl Vorkommen

        Returns:
            Liste von WorkflowPatterns
        """
        with self._get_connection() as conn:
            # Gruppiere nach Session und finde erfolgreiche Sequenzen
            sessions = conn.execute("""
                SELECT session_id, tool_name, success
                FROM executions
                WHERE task_type = ? AND session_id != ''
                ORDER BY session_id, timestamp
            """, (task_type,)).fetchall()

        # Sequenzen pro Session extrahieren
        session_sequences: Dict[str, Tuple[List[str], bool]] = {}
        current_session = None
        current_tools = []
        all_success = True

        for row in sessions:
            if row["session_id"] != current_session:
                if current_session and current_tools:
                    session_sequences[current_session] = (current_tools, all_success)
                current_session = row["session_id"]
                current_tools = []
                all_success = True

            current_tools.append(row["tool_name"])
            if not row["success"]:
                all_success = False

        if current_session and current_tools:
            session_sequences[current_session] = (current_tools, all_success)

        # Pattern-Zählung
        pattern_counts: Dict[str, Tuple[int, int]] = {}  # pattern -> (total, successful)

        for tools, success in session_sequences.values():
            key = ",".join(tools)
            current = pattern_counts.get(key, (0, 0))
            pattern_counts[key] = (
                current[0] + 1,
                current[1] + (1 if success else 0)
            )

        # In WorkflowPatterns konvertieren
        patterns = []
        for pattern, (total, successful) in pattern_counts.items():
            if total >= min_occurrences:
                patterns.append(WorkflowPattern(
                    tools_sequence=pattern.split(","),
                    task_type=task_type,
                    occurrence_count=total,
                    avg_success_rate=(successful / total * 100) if total > 0 else 0,
                    avg_total_duration_ms=0  # TODO: Berechnen
                ))

        # Nach Erfolgsrate sortieren
        patterns.sort(key=lambda p: p.avg_success_rate, reverse=True)

        return patterns

    def get_recommendations(
        self,
        task_type: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Gibt Tool-Empfehlungen basierend auf Historie.

        Args:
            task_type: Art der Aufgabe
            limit: Max Empfehlungen

        Returns:
            Liste von Empfehlungen
        """
        # Tools mit bester Erfolgsrate für diesen Task-Typ
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT
                    tool_name,
                    COUNT(*) as uses,
                    AVG(CASE WHEN success = 1 THEN 1.0 ELSE 0.0 END) as success_rate,
                    AVG(duration_ms) as avg_duration
                FROM executions
                WHERE task_type = ?
                GROUP BY tool_name
                HAVING uses >= 3
                ORDER BY success_rate DESC, uses DESC
                LIMIT ?
            """, (task_type, limit)).fetchall()

        return [
            {
                "tool_name": row["tool_name"],
                "uses": row["uses"],
                "success_rate": f"{row['success_rate'] * 100:.1f}%",
                "avg_duration_ms": int(row["avg_duration"] or 0),
                "recommendation": "High success rate" if row["success_rate"] > 0.9 else "Moderate success"
            }
            for row in rows
        ]

    def get_session_history(self, session_id: str) -> List[ToolExecution]:
        """Gibt alle Ausführungen einer Session zurück"""
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT * FROM executions
                WHERE session_id = ?
                ORDER BY timestamp
            """, (session_id,)).fetchall()

        return [
            ToolExecution(
                id=row["id"],
                tool_name=row["tool_name"],
                arguments=json.loads(row["arguments"]) if row["arguments"] else {},
                result=row["result"],
                success=bool(row["success"]),
                error=row["error"],
                duration_ms=row["duration_ms"],
                from_cache=bool(row["from_cache"]),
                task_type=row["task_type"],
                session_id=row["session_id"],
                timestamp=row["timestamp"],
            )
            for row in rows
        ]

    def cleanup_old_entries(self, days: int = 90):
        """Löscht alte Einträge"""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        with self._get_connection() as conn:
            result = conn.execute("""
                DELETE FROM executions WHERE timestamp < ?
            """, (cutoff,))

            logger.info(f"Cleaned up {result.rowcount} old execution entries")

    def get_summary(self) -> Dict[str, Any]:
        """Gibt eine Zusammenfassung der Historie"""
        with self._get_connection() as conn:
            row = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    COUNT(DISTINCT tool_name) as unique_tools,
                    COUNT(DISTINCT session_id) as sessions,
                    SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful,
                    AVG(duration_ms) as avg_duration
                FROM executions
            """).fetchone()

            return {
                "total_executions": row["total"],
                "unique_tools": row["unique_tools"],
                "sessions": row["sessions"],
                "overall_success_rate": f"{(row['successful'] / row['total'] * 100):.1f}%" if row["total"] > 0 else "0%",
                "avg_duration_ms": int(row["avg_duration"] or 0)
            }


# =============================================================================
# Test
# =============================================================================

def test_history():
    """Test der ExecutionHistoryStore Funktionalität"""
    print("=== Execution History Test ===\n")

    # Test-DB im temp Verzeichnis
    import tempfile
    db_path = Path(tempfile.gettempdir()) / "test_execution_history.db"
    if db_path.exists():
        db_path.unlink()

    store = ExecutionHistoryStore(str(db_path))

    # Test 1: Record executions
    print("1. Recording executions:")
    session = f"test_{int(time.time())}"

    executions = [
        ToolExecution(tool_name="filesystem_read_file", success=True, duration_ms=50,
                     task_type="write_code", session_id=session),
        ToolExecution(tool_name="filesystem_write_file", success=True, duration_ms=100,
                     task_type="write_code", session_id=session),
        ToolExecution(tool_name="filesystem_read_file", success=True, duration_ms=30,
                     task_type="write_code", session_id=session, from_cache=True),
        ToolExecution(tool_name="git_commit", success=False, error="No changes to commit",
                     duration_ms=200, task_type="write_code", session_id=session),
    ]

    for ex in executions:
        id = store.record(ex)
        print(f"   Recorded: {ex.tool_name} (id={id})")

    # Test 2: Tool stats
    print("\n2. Tool stats:")
    stats = store.get_tool_stats("filesystem_read_file")
    print(f"   filesystem_read_file: {stats.total_calls} calls, {stats.success_rate:.1f}% success, "
          f"{stats.cache_hit_rate:.1f}% cache hits")

    # Test 3: All tool stats
    print("\n3. All tool stats:")
    all_stats = store.get_all_tool_stats()
    for s in all_stats:
        print(f"   {s.tool_name}: {s.total_calls} calls, {s.success_rate:.1f}% success")

    # Test 4: Session history
    print("\n4. Session history:")
    history = store.get_session_history(session)
    print(f"   Session {session[:20]}... has {len(history)} entries")

    # Test 5: Recommendations
    print("\n5. Recommendations for 'write_code':")
    recs = store.get_recommendations("write_code")
    for rec in recs:
        print(f"   {rec['tool_name']}: {rec['success_rate']} success, {rec['uses']} uses")

    # Test 6: Summary
    print("\n6. Summary:")
    summary = store.get_summary()
    print(f"   {summary}")

    # Cleanup
    db_path.unlink()
    print("\n=== Test Complete ===")


if __name__ == "__main__":
    test_history()
