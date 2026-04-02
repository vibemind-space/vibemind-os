"""
ExplorationRepository - Database operations for idea exploration.

Provides CRUD operations for exploration sessions, nodes, and discovered edges.
"""

from __future__ import annotations
import uuid
import json
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from .idea_node import IdeaNode, ConnectionType
from .idea_journal import IdeaJournal, ExplorationSession

logger = logging.getLogger(__name__)


class ExplorationRepository:
    """
    Repository for exploration-related database operations.

    Handles persistence of exploration sessions, nodes, and discovered edges.
    """

    def __init__(self, db_connection=None):
        """
        Initialize repository.

        Args:
            db_connection: SQLite database connection
        """
        self.conn = db_connection

    def set_connection(self, conn):
        """Set database connection (for lazy initialization)."""
        self.conn = conn

    # ============================================================
    # Exploration Sessions
    # ============================================================

    def create_session(
        self,
        root_bubble_id: str,
        root_bubble_title: str = "",
        exploration_query: str = "",
        metadata: Optional[Dict] = None,
    ) -> ExplorationSession:
        """Create a new exploration session."""
        session = ExplorationSession(
            id=uuid.uuid4().hex[:12],
            root_bubble_id=root_bubble_id,
            root_bubble_title=root_bubble_title,
            exploration_query=exploration_query,
            status="running",
            current_stage=1,
            metadata=metadata or {},
        )

        if self.conn:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO exploration_sessions
                (id, root_bubble_id, root_bubble_title, exploration_query, status,
                 current_stage, total_nodes_explored, best_score, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session.id,
                session.root_bubble_id,
                session.root_bubble_title,
                session.exploration_query,
                session.status,
                session.current_stage,
                session.total_nodes_explored,
                session.best_score,
                json.dumps(session.metadata),
            ))
            self.conn.commit()

        return session

    def get_session(self, session_id: str) -> Optional[ExplorationSession]:
        """Get session by ID."""
        logger.debug("get_session: session_id=%s", session_id)
        if not self.conn:
            return None

        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, root_bubble_id, root_bubble_title, exploration_query,
                   status, current_stage, created_at, completed_at,
                   total_nodes_explored, best_score, metadata
            FROM exploration_sessions
            WHERE id = ?
        """, (session_id,))

        row = cursor.fetchone()
        if not row:
            return None

        return ExplorationSession(
            id=row[0],
            root_bubble_id=row[1],
            root_bubble_title=row[2] or "",
            exploration_query=row[3] or "",
            status=row[4],
            current_stage=row[5],
            created_at=datetime.fromisoformat(row[6]).timestamp() if row[6] else 0,
            completed_at=datetime.fromisoformat(row[7]).timestamp() if row[7] else None,
            total_nodes_explored=row[8] or 0,
            best_score=row[9] or 0.0,
            metadata=json.loads(row[10]) if row[10] else {},
        )

    def update_session(self, session: ExplorationSession) -> None:
        """Update session in database."""
        if not self.conn:
            return

        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE exploration_sessions
            SET status = ?, current_stage = ?, total_nodes_explored = ?,
                best_score = ?, completed_at = ?, metadata = ?
            WHERE id = ?
        """, (
            session.status,
            session.current_stage,
            session.total_nodes_explored,
            session.best_score,
            datetime.fromtimestamp(session.completed_at).isoformat() if session.completed_at else None,
            json.dumps(session.metadata),
            session.id,
        ))
        self.conn.commit()

    def get_active_sessions(self) -> List[ExplorationSession]:
        """Get all running exploration sessions."""
        logger.debug("get_active_sessions: querying running sessions")
        if not self.conn:
            return []

        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id FROM exploration_sessions
            WHERE status = 'running'
            ORDER BY created_at DESC
        """)

        return [self.get_session(row[0]) for row in cursor.fetchall()]

    # ============================================================
    # Exploration Nodes
    # ============================================================

    def save_node(self, node: IdeaNode, session_id: str) -> None:
        """Save exploration node to database."""
        if not self.conn:
            return

        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO exploration_nodes
            (id, session_id, step, parent_node_id, source_bubble_id, source_bubble_title,
             target_bubble_id, target_bubble_title, connection_type, reasoning, edge_label,
             embedding_similarity, llm_confidence, combined_score, exploration_depth,
             is_accepted, is_rejected, is_valid, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            node.id,
            session_id,
            node.step,
            node.parent.id if node.parent else None,
            node.source_bubble_id,
            node.source_bubble_title,
            node.target_bubble_id,
            node.target_bubble_title,
            node.connection_type.value,
            node.reasoning,
            node.edge_label,
            node.embedding_similarity,
            node.llm_confidence,
            node.combined_score,
            node.exploration_depth,
            1 if node.is_accepted else 0,
            1 if node.is_rejected else 0,
            1 if node.is_valid else 0,
            json.dumps(node.metadata),
        ))
        self.conn.commit()

    def get_nodes_for_session(self, session_id: str) -> List[IdeaNode]:
        """Get all nodes for a session."""
        logger.debug("get_nodes_for_session: session_id=%s", session_id)
        if not self.conn:
            return []

        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, step, parent_node_id, source_bubble_id, source_bubble_title,
                   target_bubble_id, target_bubble_title, connection_type, reasoning,
                   edge_label, embedding_similarity, llm_confidence, combined_score,
                   exploration_depth, is_accepted, is_rejected, is_valid, created_at, metadata
            FROM exploration_nodes
            WHERE session_id = ?
            ORDER BY step
        """, (session_id,))

        nodes = []
        node_map = {}

        for row in cursor.fetchall():
            node = IdeaNode(
                id=row[0],
                step=row[1],
                source_bubble_id=row[3],
                source_bubble_title=row[4] or "",
                target_bubble_id=row[5],
                target_bubble_title=row[6] or "",
                connection_type=ConnectionType(row[7]) if row[7] else ConnectionType.SEMANTIC,
                reasoning=row[8] or "",
                edge_label=row[9] or "",
                embedding_similarity=row[10] or 0.0,
                llm_confidence=row[11] or 0.0,
                combined_score=row[12] or 0.0,
                exploration_depth=row[13] or 1,
                is_accepted=bool(row[14]),
                is_rejected=bool(row[15]),
                is_valid=bool(row[16]),
                metadata=json.loads(row[18]) if row[18] else {},
            )
            node_map[node.id] = node
            nodes.append(node)

            # Store parent_id for later linking
            node._parent_id = row[2]

        # Link parents
        for node in nodes:
            if hasattr(node, '_parent_id') and node._parent_id:
                parent = node_map.get(node._parent_id)
                if parent:
                    node.parent = parent
                    parent.children.add(node)
                delattr(node, '_parent_id')

        return nodes

    def get_best_nodes(
        self,
        session_id: Optional[str] = None,
        top_k: int = 10,
        min_score: float = 0.0,
    ) -> List[IdeaNode]:
        """Get best-scoring nodes, optionally filtered by session."""
        logger.debug("get_best_nodes: session_id=%s, top_k=%s, min_score=%s",
                     session_id, top_k, min_score)
        if not self.conn:
            return []

        cursor = self.conn.cursor()

        if session_id:
            cursor.execute("""
                SELECT id, step, source_bubble_id, source_bubble_title,
                       target_bubble_id, target_bubble_title, connection_type,
                       reasoning, edge_label, combined_score, exploration_depth
                FROM exploration_nodes
                WHERE session_id = ? AND is_valid = 1 AND is_rejected = 0
                      AND combined_score >= ?
                ORDER BY combined_score DESC
                LIMIT ?
            """, (session_id, min_score, top_k))
        else:
            cursor.execute("""
                SELECT id, step, source_bubble_id, source_bubble_title,
                       target_bubble_id, target_bubble_title, connection_type,
                       reasoning, edge_label, combined_score, exploration_depth
                FROM exploration_nodes
                WHERE is_valid = 1 AND is_rejected = 0 AND combined_score >= ?
                ORDER BY combined_score DESC
                LIMIT ?
            """, (min_score, top_k))

        nodes = []
        for row in cursor.fetchall():
            nodes.append(IdeaNode(
                id=row[0],
                step=row[1],
                source_bubble_id=row[2],
                source_bubble_title=row[3] or "",
                target_bubble_id=row[4],
                target_bubble_title=row[5] or "",
                connection_type=ConnectionType(row[6]) if row[6] else ConnectionType.SEMANTIC,
                reasoning=row[7] or "",
                edge_label=row[8] or "",
                combined_score=row[9] or 0.0,
                exploration_depth=row[10] or 1,
            ))
        return nodes

    def update_node_status(
        self,
        node_id: str,
        is_accepted: Optional[bool] = None,
        is_rejected: Optional[bool] = None,
    ) -> None:
        """Update node acceptance/rejection status."""
        logger.debug("update_node_status: node_id=%s, accepted=%s, rejected=%s",
                     node_id, is_accepted, is_rejected)
        if not self.conn:
            return

        updates = []
        params = []

        if is_accepted is not None:
            updates.append("is_accepted = ?")
            params.append(1 if is_accepted else 0)

        if is_rejected is not None:
            updates.append("is_rejected = ?")
            params.append(1 if is_rejected else 0)

        if not updates:
            return

        params.append(node_id)
        cursor = self.conn.cursor()
        cursor.execute(f"""
            UPDATE exploration_nodes
            SET {', '.join(updates)}
            WHERE id = ?
        """, params)
        self.conn.commit()

    # ============================================================
    # Discovered Edges (Permanent)
    # ============================================================

    def save_discovered_edge(self, node: IdeaNode, session_id: Optional[str] = None) -> str:
        """
        Save an accepted exploration node as a permanent discovered edge.

        Returns the edge ID.
        """
        edge_id = uuid.uuid4().hex[:12]

        if self.conn:
            cursor = self.conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO discovered_edges
                    (id, from_idea_id, to_idea_id, edge_type, edge_label, reasoning,
                     confidence, connection_type, exploration_session_id, exploration_node_id,
                     metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    edge_id,
                    node.source_bubble_id,
                    node.target_bubble_id,
                    "discovered",
                    node.edge_label,
                    node.reasoning,
                    node.combined_score,
                    node.connection_type.value,
                    session_id,
                    node.id,
                    json.dumps(node.metadata),
                ))
                self.conn.commit()
            except Exception as e:
                # Might fail on unique constraint if edge already exists
                logger.warning(f"Could not save discovered edge: {e}")

        return edge_id

    def get_discovered_edges(
        self,
        bubble_id: Optional[str] = None,
        min_confidence: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """Get discovered edges, optionally filtered by bubble."""
        logger.debug("get_discovered_edges: bubble_id=%s, min_confidence=%s",
                     bubble_id, min_confidence)
        if not self.conn:
            return []

        cursor = self.conn.cursor()

        if bubble_id:
            cursor.execute("""
                SELECT id, from_idea_id, to_idea_id, edge_type, edge_label,
                       reasoning, confidence, connection_type, created_at
                FROM discovered_edges
                WHERE (from_idea_id = ? OR to_idea_id = ?) AND confidence >= ?
                ORDER BY confidence DESC
            """, (bubble_id, bubble_id, min_confidence))
        else:
            cursor.execute("""
                SELECT id, from_idea_id, to_idea_id, edge_type, edge_label,
                       reasoning, confidence, connection_type, created_at
                FROM discovered_edges
                WHERE confidence >= ?
                ORDER BY confidence DESC
            """, (min_confidence,))

        edges = []
        for row in cursor.fetchall():
            edges.append({
                "id": row[0],
                "from_idea_id": row[1],
                "to_idea_id": row[2],
                "edge_type": row[3],
                "edge_label": row[4],
                "reasoning": row[5],
                "confidence": row[6],
                "connection_type": row[7],
                "created_at": row[8],
            })
        return edges

    def edge_exists(self, from_id: str, to_id: str) -> bool:
        """Check if an edge already exists between two bubbles."""
        if not self.conn:
            return False

        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM discovered_edges
            WHERE (from_idea_id = ? AND to_idea_id = ?)
               OR (from_idea_id = ? AND to_idea_id = ?)
        """, (from_id, to_id, to_id, from_id))

        return cursor.fetchone()[0] > 0

    # ============================================================
    # Journal Loading
    # ============================================================

    def load_journal(self, session_id: str) -> Optional[IdeaJournal]:
        """Load a complete journal from database."""
        session = self.get_session(session_id)
        if not session:
            return None

        nodes = self.get_nodes_for_session(session_id)

        journal = IdeaJournal(session=session, nodes=nodes)
        return journal

    def save_journal(self, journal: IdeaJournal) -> None:
        """Save a complete journal to database."""
        if journal.session:
            # Check if session exists, create if not
            existing = self.get_session(journal.session.id)
            if not existing and self.conn:
                # Insert session with its existing ID
                cursor = self.conn.cursor()
                cursor.execute("""
                    INSERT INTO exploration_sessions
                    (id, root_bubble_id, root_bubble_title, exploration_query, status,
                     current_stage, total_nodes_explored, best_score, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    journal.session.id,
                    journal.session.root_bubble_id,
                    journal.session.root_bubble_title,
                    journal.session.exploration_query,
                    journal.session.status,
                    journal.session.current_stage,
                    journal.session.total_nodes_explored,
                    journal.session.best_score,
                    json.dumps(journal.session.metadata),
                ))
                self.conn.commit()
            elif existing:
                self.update_session(journal.session)

        for node in journal.nodes:
            self.save_node(node, journal.session.id if journal.session else "")
