"""
SQLite Memory System for AutoGen Agents

Provides persistent storage for:
1. Conversation History - All agent messages
2. Task Memory - Successful/failed tasks with steps
3. UI Element Cache - Learned element positions
4. Action Patterns - Sequences that worked
"""

import sqlite3
import json
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """Status einer Task."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"


@dataclass
class ConversationMessage:
    """Eine Nachricht in der Conversation History."""
    id: Optional[int] = None
    session_id: str = ""
    agent_id: str = ""
    role: str = "user"  # user, assistant, system, tool
    content: str = ""
    tool_calls: Optional[List[Dict]] = None
    tool_results: Optional[Dict] = None
    timestamp: str = ""
    tokens_used: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'session_id': self.session_id,
            'agent_id': self.agent_id,
            'role': self.role,
            'content': self.content,
            'tool_calls': self.tool_calls,
            'tool_results': self.tool_results,
            'timestamp': self.timestamp,
            'tokens_used': self.tokens_used
        }


@dataclass
class TaskRecord:
    """Ein Task-Record mit allen Schritten."""
    id: Optional[int] = None
    task_description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    steps: List[Dict[str, Any]] = field(default_factory=list)
    total_actions: int = 0
    successful_actions: int = 0
    failed_actions: int = 0
    start_time: str = ""
    end_time: str = ""
    error_message: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'task_description': self.task_description,
            'status': self.status.value,
            'steps': self.steps,
            'total_actions': self.total_actions,
            'successful_actions': self.successful_actions,
            'failed_actions': self.failed_actions,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'error_message': self.error_message,
            'context': self.context
        }


@dataclass
class UIElementCache:
    """Cache für gelernte UI-Element Positionen."""
    id: Optional[int] = None
    application: str = ""  # z.B. "Windows Explorer", "Chrome"
    element_text: str = ""  # Text des Elements
    element_type: str = ""  # z.B. "button", "menu_item", "icon"
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    confidence: float = 0.0
    last_seen: str = ""
    hit_count: int = 0  # Wie oft wurde dieses Element erfolgreich geklickt
    miss_count: int = 0  # Wie oft wurde das Element nicht gefunden
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'application': self.application,
            'element_text': self.element_text,
            'element_type': self.element_type,
            'x': self.x,
            'y': self.y,
            'width': self.width,
            'height': self.height,
            'confidence': self.confidence,
            'last_seen': self.last_seen,
            'hit_count': self.hit_count,
            'miss_count': self.miss_count
        }


@dataclass
class ActionPattern:
    """Ein gelerntes Action-Pattern (Sequenz die funktioniert hat)."""
    id: Optional[int] = None
    pattern_name: str = ""  # z.B. "open_explorer", "save_file"
    description: str = ""
    trigger_conditions: Dict[str, Any] = field(default_factory=dict)  # Wann wird dieses Pattern genutzt
    actions: List[Dict[str, Any]] = field(default_factory=list)  # Die Aktionen
    success_rate: float = 0.0
    use_count: int = 0
    last_used: str = ""
    created_at: str = ""
    updated_at: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'pattern_name': self.pattern_name,
            'description': self.description,
            'trigger_conditions': self.trigger_conditions,
            'actions': self.actions,
            'success_rate': self.success_rate,
            'use_count': self.use_count,
            'last_used': self.last_used,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


class AgentMemory:
    """
    SQLite-basiertes Memory System für AutoGen Agents.
    
    Features:
    - Conversation History Persistence
    - Task Progress Tracking
    - UI Element Position Cache
    - Action Pattern Learning
    """
    
    def __init__(self, db_path: str = "./data/agent_memory.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection: Optional[sqlite3.Connection] = None
        self._initialized = False
    
    def _get_conn(self) -> sqlite3.Connection:
        """Gibt Connection zurück, erstellt sie falls nötig."""
        if self._connection is None:
            self._connection = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False
            )
            self._connection.row_factory = sqlite3.Row
        return self._connection
    
    def initialize(self):
        """Initialisiert die Datenbank mit allen Tabellen."""
        if self._initialized:
            return
        
        conn = self._get_conn()
        cursor = conn.cursor()
        
        # Conversation History
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversation_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                tool_calls TEXT,
                tool_results TEXT,
                timestamp TEXT NOT NULL,
                tokens_used INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_conversation_session 
            ON conversation_history(session_id)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_conversation_agent 
            ON conversation_history(agent_id)
        ''')
        
        # Task Records
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_description TEXT NOT NULL,
                task_hash TEXT UNIQUE,
                status TEXT NOT NULL,
                steps TEXT,
                total_actions INTEGER DEFAULT 0,
                successful_actions INTEGER DEFAULT 0,
                failed_actions INTEGER DEFAULT 0,
                start_time TEXT,
                end_time TEXT,
                error_message TEXT,
                context TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_task_status 
            ON tasks(status)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_task_hash 
            ON tasks(task_hash)
        ''')
        
        # UI Element Cache
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ui_element_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                application TEXT NOT NULL,
                element_text TEXT NOT NULL,
                element_type TEXT,
                x INTEGER NOT NULL,
                y INTEGER NOT NULL,
                width INTEGER DEFAULT 0,
                height INTEGER DEFAULT 0,
                confidence REAL DEFAULT 0.0,
                last_seen TEXT NOT NULL,
                hit_count INTEGER DEFAULT 0,
                miss_count INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(application, element_text, element_type)
            )
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_ui_element_app 
            ON ui_element_cache(application)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_ui_element_text 
            ON ui_element_cache(element_text)
        ''')
        
        # Action Patterns
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS action_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_name TEXT UNIQUE NOT NULL,
                description TEXT,
                trigger_conditions TEXT,
                actions TEXT NOT NULL,
                success_rate REAL DEFAULT 0.0,
                use_count INTEGER DEFAULT 0,
                last_used TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_pattern_name 
            ON action_patterns(pattern_name)
        ''')
        
        conn.commit()
        self._initialized = True
        logger.info(f"AgentMemory initialized at {self.db_path}")
    
    def close(self):
        """Schließt die Datenbankverbindung."""
        if self._connection:
            self._connection.close()
            self._connection = None
    
    # ==================== Conversation History ====================
    
    def add_message(self, message: ConversationMessage) -> int:
        """Fügt eine Nachricht zur History hinzu."""
        self.initialize()
        conn = self._get_conn()
        cursor = conn.cursor()
        
        timestamp = message.timestamp or datetime.now().isoformat()
        
        cursor.execute('''
            INSERT INTO conversation_history 
            (session_id, agent_id, role, content, tool_calls, tool_results, timestamp, tokens_used)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            message.session_id,
            message.agent_id,
            message.role,
            message.content,
            json.dumps(message.tool_calls) if message.tool_calls else None,
            json.dumps(message.tool_results) if message.tool_results else None,
            timestamp,
            message.tokens_used
        ))
        
        conn.commit()
        return cursor.lastrowid
    
    def get_session_history(
        self, 
        session_id: str, 
        limit: int = 100,
        agent_id: Optional[str] = None
    ) -> List[ConversationMessage]:
        """Holt die Conversation History für eine Session."""
        self.initialize()
        conn = self._get_conn()
        cursor = conn.cursor()
        
        if agent_id:
            cursor.execute('''
                SELECT * FROM conversation_history 
                WHERE session_id = ? AND agent_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (session_id, agent_id, limit))
        else:
            cursor.execute('''
                SELECT * FROM conversation_history 
                WHERE session_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (session_id, limit))
        
        messages = []
        for row in cursor.fetchall():
            messages.append(ConversationMessage(
                id=row['id'],
                session_id=row['session_id'],
                agent_id=row['agent_id'],
                role=row['role'],
                content=row['content'],
                tool_calls=json.loads(row['tool_calls']) if row['tool_calls'] else None,
                tool_results=json.loads(row['tool_results']) if row['tool_results'] else None,
                timestamp=row['timestamp'],
                tokens_used=row['tokens_used']
            ))
        
        return list(reversed(messages))  # Chronologische Reihenfolge
    
    def get_recent_context(
        self, 
        session_id: str, 
        max_messages: int = 20,
        max_tokens: int = 4000
    ) -> str:
        """Gibt formatierte Recent Context für Prompt Injection."""
        messages = self.get_session_history(session_id, limit=max_messages)
        
        context_parts = []
        total_tokens = 0
        
        for msg in reversed(messages):
            # Einfache Token-Schätzung (4 chars ~ 1 token)
            estimated_tokens = len(msg.content) // 4
            if total_tokens + estimated_tokens > max_tokens:
                break
            
            role_prefix = {
                'user': 'User',
                'assistant': 'Assistant',
                'system': 'System',
                'tool': 'Tool'
            }.get(msg.role, msg.role)
            
            context_parts.insert(0, f"{role_prefix}: {msg.content[:500]}")
            total_tokens += estimated_tokens
        
        return "\n".join(context_parts)
    
    # ==================== Task Memory ====================
    
    def _task_hash(self, description: str) -> str:
        """Erzeugt Hash für Task-Deduplizierung."""
        # Normalisiere den Text
        normalized = description.lower().strip()
        return hashlib.md5(normalized.encode()).hexdigest()[:16]
    
    def start_task(self, task_description: str, context: Optional[Dict] = None) -> TaskRecord:
        """Startet einen neuen Task oder findet ähnlichen."""
        self.initialize()
        conn = self._get_conn()
        cursor = conn.cursor()
        
        task_hash = self._task_hash(task_description)
        start_time = datetime.now().isoformat()
        
        # Check for existing similar task
        cursor.execute('''
            SELECT * FROM tasks WHERE task_hash = ? AND status = 'success'
            ORDER BY created_at DESC LIMIT 1
        ''', (task_hash,))
        
        existing = cursor.fetchone()
        if existing:
            logger.info(f"Found similar successful task: {existing['id']}")
        
        # Create new task
        cursor.execute('''
            INSERT INTO tasks 
            (task_description, task_hash, status, steps, start_time, context)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            task_description,
            task_hash,
            TaskStatus.IN_PROGRESS.value,
            json.dumps([]),
            start_time,
            json.dumps(context or {})
        ))
        
        conn.commit()
        task_id = cursor.lastrowid
        
        return TaskRecord(
            id=task_id,
            task_description=task_description,
            status=TaskStatus.IN_PROGRESS,
            steps=[],
            start_time=start_time,
            context=context or {}
        )
    
    def add_task_step(
        self, 
        task_id: int, 
        step_type: str, 
        description: str, 
        success: bool,
        details: Optional[Dict] = None
    ):
        """Fügt einen Schritt zu einem Task hinzu."""
        self.initialize()
        conn = self._get_conn()
        cursor = conn.cursor()
        
        # Get current steps
        cursor.execute('SELECT steps, total_actions, successful_actions, failed_actions FROM tasks WHERE id = ?', (task_id,))
        row = cursor.fetchone()
        if not row:
            return
        
        steps = json.loads(row['steps'] or '[]')
        total = row['total_actions'] + 1
        successful = row['successful_actions'] + (1 if success else 0)
        failed = row['failed_actions'] + (0 if success else 1)
        
        steps.append({
            'type': step_type,
            'description': description,
            'success': success,
            'details': details,
            'timestamp': datetime.now().isoformat()
        })
        
        cursor.execute('''
            UPDATE tasks 
            SET steps = ?, total_actions = ?, successful_actions = ?, failed_actions = ?
            WHERE id = ?
        ''', (json.dumps(steps), total, successful, failed, task_id))
        
        conn.commit()
    
    def complete_task(
        self, 
        task_id: int, 
        success: bool, 
        error_message: Optional[str] = None
    ):
        """Markiert einen Task als abgeschlossen."""
        self.initialize()
        conn = self._get_conn()
        cursor = conn.cursor()
        
        status = TaskStatus.SUCCESS if success else TaskStatus.FAILED
        end_time = datetime.now().isoformat()
        
        cursor.execute('''
            UPDATE tasks 
            SET status = ?, end_time = ?, error_message = ?
            WHERE id = ?
        ''', (status.value, end_time, error_message, task_id))
        
        conn.commit()
        logger.info(f"Task {task_id} completed: {status.value}")
    
    def get_similar_tasks(
        self, 
        task_description: str, 
        status: Optional[TaskStatus] = None,
        limit: int = 5
    ) -> List[TaskRecord]:
        """Findet ähnliche Tasks aus der History."""
        self.initialize()
        conn = self._get_conn()
        cursor = conn.cursor()
        
        task_hash = self._task_hash(task_description)
        
        if status:
            cursor.execute('''
                SELECT * FROM tasks 
                WHERE task_hash = ? AND status = ?
                ORDER BY created_at DESC
                LIMIT ?
            ''', (task_hash, status.value, limit))
        else:
            cursor.execute('''
                SELECT * FROM tasks 
                WHERE task_hash = ?
                ORDER BY created_at DESC
                LIMIT ?
            ''', (task_hash, limit))
        
        tasks = []
        for row in cursor.fetchall():
            tasks.append(TaskRecord(
                id=row['id'],
                task_description=row['task_description'],
                status=TaskStatus(row['status']),
                steps=json.loads(row['steps'] or '[]'),
                total_actions=row['total_actions'],
                successful_actions=row['successful_actions'],
                failed_actions=row['failed_actions'],
                start_time=row['start_time'],
                end_time=row['end_time'],
                error_message=row['error_message'],
                context=json.loads(row['context'] or '{}')
            ))
        
        return tasks
    
    def get_successful_steps_for_task(self, task_description: str) -> List[Dict]:
        """Gibt erfolgreiche Schritte für ähnliche Tasks zurück."""
        tasks = self.get_similar_tasks(task_description, status=TaskStatus.SUCCESS, limit=1)
        if tasks:
            return tasks[0].steps
        return []
    
    # ==================== UI Element Cache ====================
    
    def cache_ui_element(
        self,
        application: str,
        element_text: str,
        element_type: str,
        x: int,
        y: int,
        width: int = 0,
        height: int = 0,
        confidence: float = 0.0
    ) -> int:
        """Cached ein UI-Element (upsert)."""
        self.initialize()
        conn = self._get_conn()
        cursor = conn.cursor()
        
        last_seen = datetime.now().isoformat()
        
        cursor.execute('''
            INSERT INTO ui_element_cache 
            (application, element_text, element_type, x, y, width, height, confidence, last_seen, hit_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(application, element_text, element_type) DO UPDATE SET
                x = excluded.x,
                y = excluded.y,
                width = excluded.width,
                height = excluded.height,
                confidence = excluded.confidence,
                last_seen = excluded.last_seen,
                hit_count = hit_count + 1
        ''', (application, element_text, element_type, x, y, width, height, confidence, last_seen))
        
        conn.commit()
        return cursor.lastrowid
    
    def get_cached_element(
        self,
        application: str,
        element_text: str,
        element_type: Optional[str] = None
    ) -> Optional[UIElementCache]:
        """Sucht ein gecachtes UI-Element."""
        self.initialize()
        conn = self._get_conn()
        cursor = conn.cursor()
        
        if element_type:
            cursor.execute('''
                SELECT * FROM ui_element_cache 
                WHERE application = ? AND element_text LIKE ? AND element_type = ?
                ORDER BY hit_count DESC, last_seen DESC
                LIMIT 1
            ''', (application, f'%{element_text}%', element_type))
        else:
            cursor.execute('''
                SELECT * FROM ui_element_cache 
                WHERE application = ? AND element_text LIKE ?
                ORDER BY hit_count DESC, last_seen DESC
                LIMIT 1
            ''', (application, f'%{element_text}%'))
        
        row = cursor.fetchone()
        if row:
            return UIElementCache(
                id=row['id'],
                application=row['application'],
                element_text=row['element_text'],
                element_type=row['element_type'],
                x=row['x'],
                y=row['y'],
                width=row['width'],
                height=row['height'],
                confidence=row['confidence'],
                last_seen=row['last_seen'],
                hit_count=row['hit_count'],
                miss_count=row['miss_count']
            )
        return None
    
    def record_element_miss(self, application: str, element_text: str):
        """Markiert, dass ein Element nicht gefunden wurde."""
        self.initialize()
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE ui_element_cache 
            SET miss_count = miss_count + 1
            WHERE application = ? AND element_text LIKE ?
        ''', (application, f'%{element_text}%'))
        
        conn.commit()
    
    def get_reliable_elements(self, application: str, min_hit_rate: float = 0.7) -> List[UIElementCache]:
        """Gibt zuverlässige UI-Elemente für eine Anwendung zurück."""
        self.initialize()
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT *, 
                CASE WHEN (hit_count + miss_count) > 0 
                     THEN CAST(hit_count AS REAL) / (hit_count + miss_count) 
                     ELSE 0 
                END as hit_rate
            FROM ui_element_cache 
            WHERE application = ?
            HAVING hit_rate >= ?
            ORDER BY hit_count DESC
        ''', (application, min_hit_rate))
        
        elements = []
        for row in cursor.fetchall():
            elements.append(UIElementCache(
                id=row['id'],
                application=row['application'],
                element_text=row['element_text'],
                element_type=row['element_type'],
                x=row['x'],
                y=row['y'],
                width=row['width'],
                height=row['height'],
                confidence=row['confidence'],
                last_seen=row['last_seen'],
                hit_count=row['hit_count'],
                miss_count=row['miss_count']
            ))
        
        return elements
    
    # ==================== Action Patterns ====================
    
    def save_action_pattern(
        self,
        pattern_name: str,
        description: str,
        actions: List[Dict],
        trigger_conditions: Optional[Dict] = None
    ) -> int:
        """Speichert ein Action-Pattern."""
        self.initialize()
        conn = self._get_conn()
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        cursor.execute('''
            INSERT INTO action_patterns 
            (pattern_name, description, trigger_conditions, actions, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(pattern_name) DO UPDATE SET
                description = excluded.description,
                trigger_conditions = excluded.trigger_conditions,
                actions = excluded.actions,
                updated_at = excluded.updated_at
        ''', (
            pattern_name,
            description,
            json.dumps(trigger_conditions or {}),
            json.dumps(actions),
            now,
            now
        ))
        
        conn.commit()
        return cursor.lastrowid
    
    def get_action_pattern(self, pattern_name: str) -> Optional[ActionPattern]:
        """Holt ein Action-Pattern."""
        self.initialize()
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM action_patterns WHERE pattern_name = ?', (pattern_name,))
        row = cursor.fetchone()
        
        if row:
            return ActionPattern(
                id=row['id'],
                pattern_name=row['pattern_name'],
                description=row['description'],
                trigger_conditions=json.loads(row['trigger_conditions'] or '{}'),
                actions=json.loads(row['actions'] or '[]'),
                success_rate=row['success_rate'],
                use_count=row['use_count'],
                last_used=row['last_used'],
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )
        return None
    
    def record_pattern_use(self, pattern_name: str, success: bool):
        """Zeichnet die Nutzung eines Patterns auf."""
        self.initialize()
        conn = self._get_conn()
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        # Get current stats
        cursor.execute('''
            SELECT use_count, success_rate FROM action_patterns WHERE pattern_name = ?
        ''', (pattern_name,))
        row = cursor.fetchone()
        
        if row:
            use_count = row['use_count'] + 1
            old_rate = row['success_rate']
            # Exponential moving average
            alpha = 0.3
            new_rate = alpha * (1.0 if success else 0.0) + (1 - alpha) * old_rate
            
            cursor.execute('''
                UPDATE action_patterns 
                SET use_count = ?, success_rate = ?, last_used = ?
                WHERE pattern_name = ?
            ''', (use_count, new_rate, now, pattern_name))
            
            conn.commit()
    
    def find_matching_pattern(
        self, 
        goal: str, 
        current_state: Optional[Dict] = None
    ) -> Optional[ActionPattern]:
        """Findet ein passendes Action-Pattern für ein Ziel."""
        self.initialize()
        conn = self._get_conn()
        cursor = conn.cursor()
        
        # Suche nach Mustern die zum Ziel passen könnten
        goal_lower = goal.lower()
        
        # Suche in Pattern-Namen und Beschreibungen
        cursor.execute('''
            SELECT * FROM action_patterns 
            WHERE success_rate > 0.5
            ORDER BY success_rate DESC, use_count DESC
        ''')
        
        for row in cursor.fetchall():
            pattern_name = row['pattern_name'].lower()
            description = (row['description'] or '').lower()
            
            # Einfaches Keyword-Matching
            keywords = goal_lower.split()
            for keyword in keywords:
                if keyword in pattern_name or keyword in description:
                    return ActionPattern(
                        id=row['id'],
                        pattern_name=row['pattern_name'],
                        description=row['description'],
                        trigger_conditions=json.loads(row['trigger_conditions'] or '{}'),
                        actions=json.loads(row['actions'] or '[]'),
                        success_rate=row['success_rate'],
                        use_count=row['use_count'],
                        last_used=row['last_used'],
                        created_at=row['created_at'],
                        updated_at=row['updated_at']
                    )
        
        return None
    
    def get_all_patterns(self, min_success_rate: float = 0.0) -> List[ActionPattern]:
        """Gibt alle Action-Patterns zurück."""
        self.initialize()
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM action_patterns 
            WHERE success_rate >= ?
            ORDER BY success_rate DESC, use_count DESC
        ''', (min_success_rate,))
        
        patterns = []
        for row in cursor.fetchall():
            patterns.append(ActionPattern(
                id=row['id'],
                pattern_name=row['pattern_name'],
                description=row['description'],
                trigger_conditions=json.loads(row['trigger_conditions'] or '{}'),
                actions=json.loads(row['actions'] or '[]'),
                success_rate=row['success_rate'],
                use_count=row['use_count'],
                last_used=row['last_used'],
                created_at=row['created_at'],
                updated_at=row['updated_at']
            ))
        
        return patterns
    
    # ==================== Stats & Utilities ====================
    
    def get_stats(self) -> Dict[str, Any]:
        """Gibt Memory-Statistiken zurück."""
        self.initialize()
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) as count FROM conversation_history')
        msg_count = cursor.fetchone()['count']
        
        cursor.execute('SELECT COUNT(*) as count FROM tasks')
        task_count = cursor.fetchone()['count']
        
        cursor.execute('SELECT COUNT(*) as count FROM tasks WHERE status = ?', (TaskStatus.SUCCESS.value,))
        success_count = cursor.fetchone()['count']
        
        cursor.execute('SELECT COUNT(*) as count FROM ui_element_cache')
        element_count = cursor.fetchone()['count']
        
        cursor.execute('SELECT COUNT(*) as count FROM action_patterns')
        pattern_count = cursor.fetchone()['count']
        
        return {
            'conversation_messages': msg_count,
            'total_tasks': task_count,
            'successful_tasks': success_count,
            'cached_elements': element_count,
            'action_patterns': pattern_count,
            'db_path': str(self.db_path),
            'db_size_kb': self.db_path.stat().st_size / 1024 if self.db_path.exists() else 0
        }
    
    def clear_old_data(self, days: int = 30):
        """Löscht alte Daten."""
        self.initialize()
        conn = self._get_conn()
        cursor = conn.cursor()
        
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        
        cursor.execute('DELETE FROM conversation_history WHERE created_at < ?', (cutoff,))
        cursor.execute('DELETE FROM tasks WHERE created_at < ? AND status != ?', (cutoff, TaskStatus.SUCCESS.value))
        
        conn.commit()
        logger.info(f"Cleared data older than {days} days")


# Singleton-Instanz
_memory_instance: Optional[AgentMemory] = None


def get_memory(db_path: str = "./data/agent_memory.db") -> AgentMemory:
    """Gibt Singleton-Instanz des Memory Systems zurück."""
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = AgentMemory(db_path)
        _memory_instance.initialize()
    return _memory_instance


# ==================== Utility Functions ====================

def learn_from_successful_task(memory: AgentMemory, task: TaskRecord):
    """Lernt ein Action-Pattern aus einem erfolgreichen Task."""
    if task.status != TaskStatus.SUCCESS or not task.steps:
        return
    
    # Extrahiere erfolgreiche Aktionen
    successful_steps = [s for s in task.steps if s.get('success', False)]
    
    if len(successful_steps) >= 2:
        # Erstelle Pattern-Namen aus Task-Beschreibung
        pattern_name = task.task_description.lower()
        pattern_name = pattern_name.replace(' ', '_')[:50]
        
        memory.save_action_pattern(
            pattern_name=pattern_name,
            description=task.task_description,
            actions=[
                {
                    'type': s.get('type'),
                    'description': s.get('description'),
                    'details': s.get('details')
                }
                for s in successful_steps
            ]
        )
        
        logger.info(f"Learned pattern from task: {pattern_name}")


if __name__ == "__main__":
    # Test
    logging.basicConfig(level=logging.INFO)
    
    memory = get_memory("./test_memory.db")
    
    # Test Conversation
    session_id = "test_session_1"
    memory.add_message(ConversationMessage(
        session_id=session_id,
        agent_id="planner",
        role="user",
        content="Öffne den Windows Explorer"
    ))
    memory.add_message(ConversationMessage(
        session_id=session_id,
        agent_id="planner",
        role="assistant",
        content="Ich werde Win+E drücken"
    ))
    
    print("Session history:", memory.get_session_history(session_id))
    
    # Test Task
    task = memory.start_task("Öffne Windows Explorer")
    memory.add_task_step(task.id, "keyboard", "Press Win+E", True)
    memory.complete_task(task.id, True)
    
    print("Similar tasks:", memory.get_similar_tasks("Explorer öffnen"))
    
    # Test UI Cache
    memory.cache_ui_element("Windows Explorer", "Dieser PC", "icon", 100, 200)
    print("Cached element:", memory.get_cached_element("Windows Explorer", "PC"))
    
    # Test Pattern
    memory.save_action_pattern(
        "open_explorer",
        "Opens Windows Explorer",
        [{"type": "keyboard", "key": "win+e"}]
    )
    print("Pattern:", memory.get_action_pattern("open_explorer"))
    
    print("\nStats:", memory.get_stats())
    
    memory.close()