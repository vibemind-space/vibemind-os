"""
Reinforcement Learning Memory System

Erweitert das SQLite Memory um:
1. Episodes - Vollständige Task-Durchläufe mit Total Reward
2. State-Action-Reward Transitions - (s, a, r, s') Tupel
3. Q-Table - State-Action Values für Policy Learning
4. Human Feedback - Manuelles Reward-Labeling
"""

import sqlite3
import json
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import numpy as np

logger = logging.getLogger(__name__)


class RewardSource(Enum):
    """Quelle des Rewards."""
    AUTO = "auto"           # Automatisch aus Validation
    HUMAN = "human"         # Manuelles Feedback
    GOAL_CHECK = "goal"     # Goal-Check Ergebnis
    HEURISTIC = "heuristic" # Regelbasiert


@dataclass
class Episode:
    """Eine vollständige RL-Episode (Task-Durchlauf)."""
    id: Optional[int] = None
    task_description: str = ""
    task_id: str = ""
    start_time: str = ""
    end_time: str = ""
    total_reward: float = 0.0
    total_steps: int = 0
    success: bool = False
    terminal_state: str = ""  # Finaler Screen State Hash
    exploration_rate: float = 0.1
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'task_description': self.task_description,
            'task_id': self.task_id,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'total_reward': self.total_reward,
            'total_steps': self.total_steps,
            'success': self.success,
            'terminal_state': self.terminal_state,
            'exploration_rate': self.exploration_rate,
            'metadata': self.metadata
        }


@dataclass
class Transition:
    """Eine State-Action-Reward-NextState Transition."""
    id: Optional[int] = None
    episode_id: int = 0
    step_index: int = 0
    state_hash: str = ""        # Hash des Screen States
    state_summary: str = ""     # Kurze State-Beschreibung
    action_type: str = ""       # click, type, press, etc.
    action_params: Dict[str, Any] = field(default_factory=dict)
    action_text: str = ""       # Human-readable Action
    reward: float = 0.0
    reward_source: RewardSource = RewardSource.AUTO
    next_state_hash: str = ""
    next_state_summary: str = ""
    is_terminal: bool = False
    timestamp: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'episode_id': self.episode_id,
            'step_index': self.step_index,
            'state_hash': self.state_hash,
            'state_summary': self.state_summary,
            'action_type': self.action_type,
            'action_params': self.action_params,
            'action_text': self.action_text,
            'reward': self.reward,
            'reward_source': self.reward_source.value,
            'next_state_hash': self.next_state_hash,
            'next_state_summary': self.next_state_summary,
            'is_terminal': self.is_terminal,
            'timestamp': self.timestamp
        }


@dataclass
class QTableEntry:
    """Ein Q-Table Eintrag (State-Action Value)."""
    id: Optional[int] = None
    state_hash: str = ""
    state_description: str = ""
    action_key: str = ""        # Unique Action Identifier
    action_description: str = ""
    q_value: float = 0.0
    visit_count: int = 0
    last_update: str = ""
    confidence: float = 0.0     # Wie sicher ist dieser Q-Value
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'state_hash': self.state_hash,
            'state_description': self.state_description,
            'action_key': self.action_key,
            'action_description': self.action_description,
            'q_value': self.q_value,
            'visit_count': self.visit_count,
            'last_update': self.last_update,
            'confidence': self.confidence
        }


@dataclass
class HumanFeedback:
    """Manuelles Reward-Feedback vom Benutzer."""
    id: Optional[int] = None
    transition_id: Optional[int] = None
    episode_id: Optional[int] = None
    feedback_type: str = ""     # reward_correct, reward_wrong, action_good, action_bad
    original_reward: float = 0.0
    corrected_reward: Optional[float] = None
    comment: str = ""
    timestamp: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'transition_id': self.transition_id,
            'episode_id': self.episode_id,
            'feedback_type': self.feedback_type,
            'original_reward': self.original_reward,
            'corrected_reward': self.corrected_reward,
            'comment': self.comment,
            'timestamp': self.timestamp
        }


class RLMemory:
    """
    Reinforcement Learning Memory System.
    
    Features:
    - Episode Tracking mit Total Rewards
    - State-Action-Reward Transitions
    - Q-Table für Policy Learning
    - Human Feedback Integration
    """
    
    # Default Reward Values
    REWARD_STEP_SUCCESS = 0.1
    REWARD_STEP_FAIL = -0.5
    REWARD_GOAL_ACHIEVED = 10.0
    REWARD_GOAL_FAILED = -5.0
    REWARD_STEP_NEUTRAL = 0.0
    
    def __init__(self, db_path: str = "./data/rl_memory.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection: Optional[sqlite3.Connection] = None
        self._initialized = False
        
        # Q-Learning Parameters
        self.learning_rate = 0.1      # alpha
        self.discount_factor = 0.95   # gamma
        self.exploration_rate = 0.2   # epsilon
        self.min_exploration = 0.01
        self.exploration_decay = 0.995
    
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
        """Initialisiert die RL-Datenbank-Tabellen."""
        if self._initialized:
            return
        
        conn = self._get_conn()
        cursor = conn.cursor()
        
        # Episodes Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rl_episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_description TEXT NOT NULL,
                task_id TEXT,
                start_time TEXT NOT NULL,
                end_time TEXT,
                total_reward REAL DEFAULT 0.0,
                total_steps INTEGER DEFAULT 0,
                success INTEGER DEFAULT 0,
                terminal_state TEXT,
                exploration_rate REAL DEFAULT 0.1,
                metadata TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_episode_task 
            ON rl_episodes(task_description)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_episode_success 
            ON rl_episodes(success)
        ''')
        
        # Transitions Table (SARSA Tupel)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rl_transitions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                episode_id INTEGER NOT NULL,
                step_index INTEGER NOT NULL,
                state_hash TEXT NOT NULL,
                state_summary TEXT,
                action_type TEXT NOT NULL,
                action_params TEXT,
                action_text TEXT,
                reward REAL DEFAULT 0.0,
                reward_source TEXT DEFAULT 'auto',
                next_state_hash TEXT,
                next_state_summary TEXT,
                is_terminal INTEGER DEFAULT 0,
                timestamp TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (episode_id) REFERENCES rl_episodes(id)
            )
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_transition_episode 
            ON rl_transitions(episode_id)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_transition_state 
            ON rl_transitions(state_hash)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_transition_action 
            ON rl_transitions(action_type, action_text)
        ''')
        
        # Q-Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rl_qtable (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                state_hash TEXT NOT NULL,
                state_description TEXT,
                action_key TEXT NOT NULL,
                action_description TEXT,
                q_value REAL DEFAULT 0.0,
                visit_count INTEGER DEFAULT 0,
                last_update TEXT,
                confidence REAL DEFAULT 0.0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(state_hash, action_key)
            )
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_qtable_state 
            ON rl_qtable(state_hash)
        ''')
        
        # Human Feedback Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rl_human_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transition_id INTEGER,
                episode_id INTEGER,
                feedback_type TEXT NOT NULL,
                original_reward REAL,
                corrected_reward REAL,
                comment TEXT,
                timestamp TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (transition_id) REFERENCES rl_transitions(id),
                FOREIGN KEY (episode_id) REFERENCES rl_episodes(id)
            )
        ''')
        
        # RL Stats View
        cursor.execute('''
            CREATE VIEW IF NOT EXISTS rl_stats AS
            SELECT 
                COUNT(DISTINCT e.id) as total_episodes,
                SUM(CASE WHEN e.success = 1 THEN 1 ELSE 0 END) as successful_episodes,
                AVG(e.total_reward) as avg_reward,
                AVG(e.total_steps) as avg_steps,
                COUNT(t.id) as total_transitions,
                COUNT(DISTINCT t.state_hash) as unique_states,
                COUNT(DISTINCT q.id) as qtable_entries
            FROM rl_episodes e
            LEFT JOIN rl_transitions t ON e.id = t.episode_id
            LEFT JOIN rl_qtable q ON 1=1
        ''')
        
        conn.commit()
        self._initialized = True
        logger.info(f"RLMemory initialized at {self.db_path}")
    
    def close(self):
        """Schließt die Datenbankverbindung."""
        if self._connection:
            self._connection.close()
            self._connection = None
    
    # ==================== State Hashing ====================
    
    @staticmethod
    def hash_state(state_info: Dict[str, Any]) -> str:
        """Erzeugt einen Hash für einen Bildschirm-State."""
        # Relevante Teile extrahieren
        relevant = {
            'texts': sorted([t.get('text', '')[:50] for t in state_info.get('texts', [])[:20]]),
            'box_count': len(state_info.get('boxes', [])),
            'categories': sorted(list(set(b.get('category', '') for b in state_info.get('boxes', []))))
        }
        return hashlib.md5(json.dumps(relevant, sort_keys=True).encode()).hexdigest()[:16]
    
    @staticmethod
    def action_key(action_type: str, action_params: Dict[str, Any]) -> str:
        """Erzeugt einen eindeutigen Key für eine Action."""
        if action_type == 'click':
            target = action_params.get('target', action_params.get('text', 'unknown'))
            return f"click:{target[:30]}"
        elif action_type == 'type':
            text = action_params.get('text', '')[:20]
            return f"type:{text}"
        elif action_type == 'press':
            key = action_params.get('key', 'unknown')
            return f"press:{key}"
        elif action_type == 'hotkey':
            keys = action_params.get('keys', [])
            return f"hotkey:{'+'.join(keys)}"
        else:
            return f"{action_type}:{json.dumps(action_params)[:30]}"
    
    # ==================== Episode Management ====================
    
    def start_episode(self, task_description: str, task_id: str = "") -> Episode:
        """Startet eine neue RL-Episode."""
        self.initialize()
        conn = self._get_conn()
        cursor = conn.cursor()
        
        start_time = datetime.now().isoformat()
        
        cursor.execute('''
            INSERT INTO rl_episodes 
            (task_description, task_id, start_time, exploration_rate, metadata)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            task_description,
            task_id,
            start_time,
            self.exploration_rate,
            json.dumps({})
        ))
        
        conn.commit()
        episode_id = cursor.lastrowid
        
        logger.info(f"Started RL episode {episode_id}: {task_description[:50]}")
        
        return Episode(
            id=episode_id,
            task_description=task_description,
            task_id=task_id,
            start_time=start_time,
            exploration_rate=self.exploration_rate
        )
    
    def end_episode(
        self, 
        episode_id: int, 
        success: bool, 
        terminal_state: Optional[Dict] = None
    ) -> float:
        """Beendet eine Episode und berechnet den finalen Reward."""
        self.initialize()
        conn = self._get_conn()
        cursor = conn.cursor()
        
        end_time = datetime.now().isoformat()
        terminal_hash = self.hash_state(terminal_state) if terminal_state else ""
        
        # Hole alle Transitions dieser Episode
        cursor.execute('''
            SELECT SUM(reward) as total, COUNT(*) as steps 
            FROM rl_transitions WHERE episode_id = ?
        ''', (episode_id,))
        row = cursor.fetchone()
        
        total_reward = row['total'] or 0.0
        total_steps = row['steps'] or 0
        
        # Füge Goal-Reward hinzu
        if success:
            total_reward += self.REWARD_GOAL_ACHIEVED
        else:
            total_reward += self.REWARD_GOAL_FAILED
        
        cursor.execute('''
            UPDATE rl_episodes 
            SET end_time = ?, total_reward = ?, total_steps = ?, 
                success = ?, terminal_state = ?
            WHERE id = ?
        ''', (end_time, total_reward, total_steps, 1 if success else 0, terminal_hash, episode_id))
        
        conn.commit()
        
        # Decay exploration rate
        self.exploration_rate = max(
            self.min_exploration,
            self.exploration_rate * self.exploration_decay
        )
        
        logger.info(f"Episode {episode_id} ended: success={success}, reward={total_reward:.2f}, steps={total_steps}")
        
        return total_reward
    
    def get_episode(self, episode_id: int) -> Optional[Episode]:
        """Holt eine Episode."""
        self.initialize()
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM rl_episodes WHERE id = ?', (episode_id,))
        row = cursor.fetchone()
        
        if row:
            return Episode(
                id=row['id'],
                task_description=row['task_description'],
                task_id=row['task_id'],
                start_time=row['start_time'],
                end_time=row['end_time'],
                total_reward=row['total_reward'],
                total_steps=row['total_steps'],
                success=bool(row['success']),
                terminal_state=row['terminal_state'],
                exploration_rate=row['exploration_rate'],
                metadata=json.loads(row['metadata'] or '{}')
            )
        return None
    
    def get_recent_episodes(self, limit: int = 20) -> List[Episode]:
        """Holt die letzten Episoden."""
        self.initialize()
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM rl_episodes 
            ORDER BY created_at DESC LIMIT ?
        ''', (limit,))
        
        episodes = []
        for row in cursor.fetchall():
            episodes.append(Episode(
                id=row['id'],
                task_description=row['task_description'],
                task_id=row['task_id'],
                start_time=row['start_time'],
                end_time=row['end_time'],
                total_reward=row['total_reward'],
                total_steps=row['total_steps'],
                success=bool(row['success']),
                terminal_state=row['terminal_state'],
                exploration_rate=row['exploration_rate'],
                metadata=json.loads(row['metadata'] or '{}')
            ))
        
        return episodes
    
    # ==================== Transitions ====================
    
    def record_transition(
        self,
        episode_id: int,
        step_index: int,
        state: Dict[str, Any],
        action_type: str,
        action_params: Dict[str, Any],
        action_text: str,
        reward: float,
        next_state: Optional[Dict[str, Any]] = None,
        is_terminal: bool = False,
        reward_source: RewardSource = RewardSource.AUTO
    ) -> int:
        """Zeichnet eine Transition auf."""
        self.initialize()
        conn = self._get_conn()
        cursor = conn.cursor()
        
        state_hash = self.hash_state(state)
        state_summary = self._summarize_state(state)
        next_state_hash = self.hash_state(next_state) if next_state else ""
        next_state_summary = self._summarize_state(next_state) if next_state else ""
        timestamp = datetime.now().isoformat()
        
        cursor.execute('''
            INSERT INTO rl_transitions 
            (episode_id, step_index, state_hash, state_summary, action_type, 
             action_params, action_text, reward, reward_source, 
             next_state_hash, next_state_summary, is_terminal, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            episode_id, step_index, state_hash, state_summary, action_type,
            json.dumps(action_params), action_text, reward, reward_source.value,
            next_state_hash, next_state_summary, 1 if is_terminal else 0, timestamp
        ))
        
        conn.commit()
        transition_id = cursor.lastrowid
        
        # Update Q-Table
        action_key = self.action_key(action_type, action_params)
        self._update_q_value(state_hash, state_summary, action_key, action_text, reward, next_state_hash)
        
        return transition_id
    
    def _summarize_state(self, state: Dict[str, Any]) -> str:
        """Erstellt eine kurze Zusammenfassung eines States."""
        if not state:
            return ""
        
        texts = state.get('texts', [])[:5]
        text_snippets = [t.get('text', '')[:20] for t in texts]
        
        categories = {}
        for box in state.get('boxes', []):
            cat = box.get('category', 'unknown')
            categories[cat] = categories.get(cat, 0) + 1
        
        return f"Texts: {text_snippets}, Categories: {categories}"
    
    def get_episode_transitions(self, episode_id: int) -> List[Transition]:
        """Holt alle Transitions einer Episode."""
        self.initialize()
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM rl_transitions 
            WHERE episode_id = ? 
            ORDER BY step_index
        ''', (episode_id,))
        
        transitions = []
        for row in cursor.fetchall():
            transitions.append(Transition(
                id=row['id'],
                episode_id=row['episode_id'],
                step_index=row['step_index'],
                state_hash=row['state_hash'],
                state_summary=row['state_summary'],
                action_type=row['action_type'],
                action_params=json.loads(row['action_params'] or '{}'),
                action_text=row['action_text'],
                reward=row['reward'],
                reward_source=RewardSource(row['reward_source']),
                next_state_hash=row['next_state_hash'],
                next_state_summary=row['next_state_summary'],
                is_terminal=bool(row['is_terminal']),
                timestamp=row['timestamp']
            ))
        
        return transitions
    
    # ==================== Q-Table ====================
    
    def _update_q_value(
        self,
        state_hash: str,
        state_description: str,
        action_key: str,
        action_description: str,
        reward: float,
        next_state_hash: str
    ):
        """Updated einen Q-Value mit Q-Learning."""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        # Hole aktuellen Q-Value
        cursor.execute('''
            SELECT q_value, visit_count FROM rl_qtable 
            WHERE state_hash = ? AND action_key = ?
        ''', (state_hash, action_key))
        row = cursor.fetchone()
        
        old_q = row['q_value'] if row else 0.0
        visit_count = (row['visit_count'] if row else 0) + 1
        
        # Hole max Q-Value für next_state
        max_next_q = 0.0
        if next_state_hash:
            cursor.execute('''
                SELECT MAX(q_value) as max_q FROM rl_qtable 
                WHERE state_hash = ?
            ''', (next_state_hash,))
            next_row = cursor.fetchone()
            max_next_q = next_row['max_q'] or 0.0
        
        # Q-Learning Update: Q(s,a) = Q(s,a) + α * (r + γ * max(Q(s',a')) - Q(s,a))
        new_q = old_q + self.learning_rate * (
            reward + self.discount_factor * max_next_q - old_q
        )
        
        # Confidence based on visit count
        confidence = min(1.0, visit_count / 10.0)
        now = datetime.now().isoformat()
        
        cursor.execute('''
            INSERT INTO rl_qtable 
            (state_hash, state_description, action_key, action_description, 
             q_value, visit_count, last_update, confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(state_hash, action_key) DO UPDATE SET
                q_value = excluded.q_value,
                visit_count = excluded.visit_count,
                last_update = excluded.last_update,
                confidence = excluded.confidence
        ''', (
            state_hash, state_description, action_key, action_description,
            new_q, visit_count, now, confidence
        ))
        
        conn.commit()
    
    def get_q_values(self, state_hash: str) -> List[QTableEntry]:
        """Holt alle Q-Values für einen State."""
        self.initialize()
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM rl_qtable 
            WHERE state_hash = ?
            ORDER BY q_value DESC
        ''', (state_hash,))
        
        entries = []
        for row in cursor.fetchall():
            entries.append(QTableEntry(
                id=row['id'],
                state_hash=row['state_hash'],
                state_description=row['state_description'],
                action_key=row['action_key'],
                action_description=row['action_description'],
                q_value=row['q_value'],
                visit_count=row['visit_count'],
                last_update=row['last_update'],
                confidence=row['confidence']
            ))
        
        return entries
    
    def get_best_action(self, state_hash: str) -> Optional[QTableEntry]:
        """Holt die beste Action für einen State (greedy)."""
        entries = self.get_q_values(state_hash)
        return entries[0] if entries else None
    
    def should_explore(self) -> bool:
        """Entscheidet ob exploriert werden soll (ε-greedy)."""
        return np.random.random() < self.exploration_rate
    
    # ==================== Human Feedback ====================
    
    def record_feedback(
        self,
        feedback_type: str,
        original_reward: float,
        corrected_reward: Optional[float] = None,
        comment: str = "",
        transition_id: Optional[int] = None,
        episode_id: Optional[int] = None
    ) -> int:
        """Zeichnet Human Feedback auf."""
        self.initialize()
        conn = self._get_conn()
        cursor = conn.cursor()
        
        timestamp = datetime.now().isoformat()
        
        cursor.execute('''
            INSERT INTO rl_human_feedback 
            (transition_id, episode_id, feedback_type, original_reward, 
             corrected_reward, comment, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            transition_id, episode_id, feedback_type, original_reward,
            corrected_reward, comment, timestamp
        ))
        
        conn.commit()
        feedback_id = cursor.lastrowid
        
        # Update transition reward if corrected
        if transition_id and corrected_reward is not None:
            cursor.execute('''
                UPDATE rl_transitions 
                SET reward = ?, reward_source = 'human'
                WHERE id = ?
            ''', (corrected_reward, transition_id))
            conn.commit()
            
            # Re-calculate Q-value for this transition
            cursor.execute('SELECT * FROM rl_transitions WHERE id = ?', (transition_id,))
            row = cursor.fetchone()
            if row:
                action_key = self.action_key(row['action_type'], json.loads(row['action_params'] or '{}'))
                self._update_q_value(
                    row['state_hash'], row['state_summary'],
                    action_key, row['action_text'],
                    corrected_reward, row['next_state_hash']
                )
        
        logger.info(f"Recorded feedback {feedback_id}: {feedback_type}")
        
        return feedback_id
    
    def get_pending_feedback_transitions(self, limit: int = 10) -> List[Transition]:
        """Holt Transitions die noch kein Human Feedback haben."""
        self.initialize()
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT t.* FROM rl_transitions t
            LEFT JOIN rl_human_feedback f ON t.id = f.transition_id
            WHERE f.id IS NULL
            ORDER BY t.created_at DESC
            LIMIT ?
        ''', (limit,))
        
        transitions = []
        for row in cursor.fetchall():
            transitions.append(Transition(
                id=row['id'],
                episode_id=row['episode_id'],
                step_index=row['step_index'],
                state_hash=row['state_hash'],
                state_summary=row['state_summary'],
                action_type=row['action_type'],
                action_params=json.loads(row['action_params'] or '{}'),
                action_text=row['action_text'],
                reward=row['reward'],
                reward_source=RewardSource(row['reward_source']),
                next_state_hash=row['next_state_hash'],
                next_state_summary=row['next_state_summary'],
                is_terminal=bool(row['is_terminal']),
                timestamp=row['timestamp']
            ))
        
        return transitions
    
    # ==================== Stats ====================
    
    def get_stats(self) -> Dict[str, Any]:
        """Gibt RL-Statistiken zurück."""
        self.initialize()
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) as count FROM rl_episodes')
        total_episodes = cursor.fetchone()['count']
        
        cursor.execute('SELECT COUNT(*) as count FROM rl_episodes WHERE success = 1')
        successful_episodes = cursor.fetchone()['count']
        
        cursor.execute('SELECT AVG(total_reward) as avg FROM rl_episodes WHERE end_time IS NOT NULL')
        avg_reward = cursor.fetchone()['avg'] or 0.0
        
        cursor.execute('SELECT COUNT(*) as count FROM rl_transitions')
        total_transitions = cursor.fetchone()['count']
        
        cursor.execute('SELECT COUNT(DISTINCT state_hash) as count FROM rl_transitions')
        unique_states = cursor.fetchone()['count']
        
        cursor.execute('SELECT COUNT(*) as count FROM rl_qtable')
        qtable_size = cursor.fetchone()['count']
        
        cursor.execute('SELECT COUNT(*) as count FROM rl_human_feedback')
        feedback_count = cursor.fetchone()['count']
        
        # Recent success rate
        cursor.execute('''
            SELECT AVG(CASE WHEN success = 1 THEN 1.0 ELSE 0.0 END) as rate
            FROM (SELECT success FROM rl_episodes ORDER BY created_at DESC LIMIT 20)
        ''')
        recent_success_rate = cursor.fetchone()['rate'] or 0.0
        
        return {
            'total_episodes': total_episodes,
            'successful_episodes': successful_episodes,
            'success_rate': successful_episodes / max(1, total_episodes),
            'recent_success_rate': recent_success_rate,
            'avg_reward': round(avg_reward, 2),
            'total_transitions': total_transitions,
            'unique_states': unique_states,
            'qtable_size': qtable_size,
            'feedback_count': feedback_count,
            'exploration_rate': round(self.exploration_rate, 3),
            'db_path': str(self.db_path)
        }
    
    def get_learning_curve(self, window: int = 10) -> List[Dict[str, Any]]:
        """Gibt die Learning Curve (Rewards über Zeit) zurück."""
        self.initialize()
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, total_reward, success, start_time
            FROM rl_episodes
            WHERE end_time IS NOT NULL
            ORDER BY created_at
        ''')
        
        episodes = cursor.fetchall()
        
        curve = []
        for i, row in enumerate(episodes):
            # Moving average
            start_idx = max(0, i - window + 1)
            window_episodes = episodes[start_idx:i + 1]
            avg_reward = sum(e['total_reward'] for e in window_episodes) / len(window_episodes)
            success_rate = sum(1 for e in window_episodes if e['success']) / len(window_episodes)
            
            curve.append({
                'episode': i + 1,
                'reward': row['total_reward'],
                'avg_reward': round(avg_reward, 2),
                'success': bool(row['success']),
                'success_rate': round(success_rate, 2),
                'timestamp': row['start_time']
            })
        
        return curve


# Singleton Instance
_rl_memory_instance: Optional[RLMemory] = None


def get_rl_memory(db_path: str = "./data/rl_memory.db") -> RLMemory:
    """Gibt Singleton-Instanz des RL Memory Systems zurück."""
    global _rl_memory_instance
    if _rl_memory_instance is None:
        _rl_memory_instance = RLMemory(db_path)
        _rl_memory_instance.initialize()
    return _rl_memory_instance


# ==================== Reward Calculation Helpers ====================

def calculate_step_reward(
    action_result: str,
    verification: Dict[str, Any],
    step_text: str
) -> Tuple[float, RewardSource]:
    """Berechnet den Reward für einen Step basierend auf Validation."""
    reward = RLMemory.REWARD_STEP_NEUTRAL
    source = RewardSource.AUTO
    
    # Check for errors
    if 'error' in action_result.lower():
        reward = RLMemory.REWARD_STEP_FAIL
    elif verification.get('verified', False):
        confidence = verification.get('confidence', 50)
        # Scale reward by confidence
        reward = RLMemory.REWARD_STEP_SUCCESS * (confidence / 100)
        source = RewardSource.AUTO
    else:
        # Unverified but no error
        reward = RLMemory.REWARD_STEP_NEUTRAL
    
    return reward, source


if __name__ == "__main__":
    # Test
    logging.basicConfig(level=logging.INFO)
    
    rl = get_rl_memory("./test_rl_memory.db")
    
    # Test Episode
    episode = rl.start_episode("Open Windows Explorer", "task_123")
    print(f"Started episode: {episode.id}")
    
    # Test Transitions
    state1 = {'texts': [{'text': 'Desktop'}], 'boxes': [{'category': 'icon'}]}
    state2 = {'texts': [{'text': 'Desktop'}, {'text': 'This PC'}], 'boxes': [{'category': 'icon'}, {'category': 'button'}]}
    
    rl.record_transition(
        episode_id=episode.id,
        step_index=0,
        state=state1,
        action_type='press',
        action_params={'key': 'win+e'},
        action_text='Press Win+E to open Explorer',
        reward=0.1,
        next_state=state2
    )
    
    # End episode
    total = rl.end_episode(episode.id, success=True, terminal_state=state2)
    print(f"Episode total reward: {total}")
    
    # Check Q-values
    state_hash = RLMemory.hash_state(state1)
    q_values = rl.get_q_values(state_hash)
    print(f"Q-values for state: {q_values}")
    
    # Stats
    print(f"\nRL Stats: {rl.get_stats()}")
    
    # Learning curve
    print(f"Learning curve: {rl.get_learning_curve()}")
    
    rl.close()